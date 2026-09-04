from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError

from foundations.auth import AuthError, permission_required

from servicing.schemas import (
    TransactionSchema,
    RepaymentScheduleSchema,
    RecordRepaymentSchema,
    RescheduleRequestSchema,
    RescheduleRequestOutputSchema
)

from servicing.services import (
    disburse_loan,
    process_repayment,
    get_loan_schedule,
    request_reschedule,
    initiate_repayment_stk,
    get_repayment_transaction,
    handle_stk_callback,
)

servicing_bp = Blueprint("servicing", __name__, url_prefix="/api/servicing")

transaction_schema = TransactionSchema()
repayment_schedule_schema = RepaymentScheduleSchema(many=True)
record_repayment_schema = RecordRepaymentSchema()
reschedule_request_schema = RescheduleRequestSchema()
reschedule_request_output_schema = RescheduleRequestOutputSchema()

from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

def _current_user_id() -> int:
    return int(get_jwt_identity())

def _auth_error_response(exc: AuthError):
    return jsonify({"error": exc.message}), exc.status_code

def _verify_customer_access(loan_id: int):
    claims = get_jwt()
    if claims.get("role") == "customer":
        from underwriting.services import get_loan
        loan = get_loan(loan_id)
        if loan.customer_profile_id != claims.get("customer_profile_id"):
            raise AuthError("You do not have permission to view this loan.", 403)

@servicing_bp.route("/loans/<int:loan_id>/disburse", methods=["POST"])
@permission_required("loan:disburse")
def disburse_loan_route(loan_id):
    actor_id = _current_user_id()
    try:
        loan = disburse_loan(loan_id, actor_id)
    except AuthError as exc:
        return _auth_error_response(exc)
        
    return jsonify({"status": "success", "loan_id": loan.id, "state": loan.status}), 200

@servicing_bp.route("/loans/<int:loan_id>/schedule", methods=["GET"])
@jwt_required()
def get_schedule_route(loan_id):
    try:
        _verify_customer_access(loan_id)
        schedules = get_loan_schedule(loan_id)
    except AuthError as exc:
        return _auth_error_response(exc)
        
    return jsonify(repayment_schedule_schema.dump(schedules)), 200

@servicing_bp.route("/loans/<int:loan_id>/repayment", methods=["POST"])
@jwt_required() # For manual entry by staff. Webhooks use different routes.
def record_repayment_route(loan_id):
    try:
        _verify_customer_access(loan_id)
        data = record_repayment_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400
        
    try:
        txn = process_repayment(loan_id, data["amount"], data["channel"], data["gateway_reference"])
    except AuthError as exc:
        return _auth_error_response(exc)
        
    if not txn:
        return jsonify({"message": "Payment already processed"}), 200
        
    return jsonify(transaction_schema.dump(txn)), 201

@servicing_bp.route("/loans/<int:loan_id>/reschedule", methods=["POST"])
@jwt_required()
def request_reschedule_route(loan_id):
    try:
        data = reschedule_request_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400
        
    actor_id = _current_user_id()
    try:
        req = request_reschedule(loan_id, actor_id, data["reason_category"], data["requested_mode"], data["requested_extension_days"])
    except AuthError as exc:
        return _auth_error_response(exc)
        
    return jsonify(reschedule_request_output_schema.dump(req)), 201


# =============================================================================
# M-PESA STK — initiate, poll, callback
# =============================================================================

@servicing_bp.route("/loans/<int:loan_id>/repayment/stk", methods=["POST"])
@jwt_required()
def initiate_repayment_stk_route(loan_id):
    """Customer taps 'Lipa na M-Pesa' — fire the STK push for the next installment."""
    claims = get_jwt()
    if claims.get("role") != "customer":
        return jsonify({"error": "Only customers can initiate an STK payment."}), 403
    from servicing.mpesa.config import MpesaConfigError
    try:
        txn = initiate_repayment_stk(loan_id, claims.get("customer_profile_id"))
    except MpesaConfigError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify({
        "checkout_request_id": txn.checkout_request_id,
        "status": txn.status,
        "amount": str(txn.amount),
    }), 202


@servicing_bp.route("/transactions/<checkout_request_id>", methods=["GET"])
@jwt_required()
def get_transaction_status_route(checkout_request_id):
    """Frontend polls this after initiating an STK push."""
    txn = get_repayment_transaction(checkout_request_id)
    if txn is None:
        return jsonify({"error": "Unknown transaction."}), 404

    claims = get_jwt()
    if claims.get("role") == "customer":
        from underwriting.services import get_loan
        if get_loan(txn.loan_id).customer_profile_id != claims.get("customer_profile_id"):
            return jsonify({"error": "Not your transaction."}), 403

    return jsonify({
        "checkout_request_id": txn.checkout_request_id,
        "status": txn.status,
        "amount": str(txn.amount),
        "gateway_reference": txn.gateway_reference,
        "failure_reason": txn.failure_reason,
        "loan_id": txn.loan_id,
    }), 200


@servicing_bp.route("/webhooks/mpesa/stk/<token>", methods=["POST"])
def mpesa_stk_webhook(token):
    """Safaricom posts the STK result here (repayment AND savings). No JWT —
    guarded by servicing.mpesa.security's shared-secret token + IP allowlist."""
    from servicing.mpesa.security import verify_webhook, WebhookAuthError
    try:
        verify_webhook(token)
    except WebhookAuthError as exc:
        return jsonify({"ResultCode": 1, "ResultDesc": exc.message}), 401

    ack = handle_stk_callback(request.get_json(silent=True) or {})
    return jsonify(ack), 200


@servicing_bp.route("/webhooks/mpesa/simulate", methods=["POST"])
def mpesa_simulate_webhook():
    """DEV ONLY (Phase 3C): synthesize a Daraja callback for a given
    checkout_request_id, so the live-update flow can be demoed without ngrok.
    Body: {checkout_request_id, result_code?=0, amount?, mpesa_receipt?}"""
    import os
    if os.environ.get("FLASK_ENV", "development") == "production":
        return jsonify({"error": "Disabled in production."}), 403

    from servicing.mpesa.callbacks import build_simulated_callback
    from servicing.models import Transaction
    from origination.models import SavingsDeposit

    data = request.get_json(silent=True) or {}
    crid = data.get("checkout_request_id")
    if not crid:
        return jsonify({"error": "checkout_request_id is required."}), 400

    # Fill amount from the pending record if the caller didn't specify one.
    amount = data.get("amount")
    if amount is None:
        rec = (Transaction.query.filter_by(checkout_request_id=crid).first()
               or SavingsDeposit.query.filter_by(checkout_request_id=crid).first())
        amount = str(rec.amount) if rec is not None else 0

    body = build_simulated_callback(
        merchant_request_id=data.get("merchant_request_id", "sim-merchant"),
        checkout_request_id=crid,
        result_code=int(data.get("result_code", 0)),
        amount=amount,
        mpesa_receipt=data.get("mpesa_receipt"),  # None -> a unique SIM… receipt
    )
    ack = handle_stk_callback(body)
    return jsonify({"simulated_callback": body, "handler_ack": ack}), 200


@servicing_bp.route("/webhooks/airtel", methods=["POST"])
def airtel_webhook():
    # TODO: §4.7 Airtel Money webhook integration
    return jsonify({"status": "success"}), 200

@servicing_bp.route("/loans/active", methods=["GET"])
@permission_required("loan:approve")  # Re-use a relevant permission for staff
def get_active_loans():
    from underwriting.models import Loan
    from underwriting.schemas import LoanSchema
    from foundations.auth import get_user_institution_id
    from origination.services import get_customer_display_info

    actor_id = _current_user_id()
    institution_id = get_user_institution_id(actor_id)

    # Active/Overdue loans
    loans = Loan.query.filter(Loan.lending_institution_id==institution_id, Loan.status.in_(("active", "overdue"))).order_by(Loan.disbursed_at.desc()).all()

    schema = LoanSchema(many=True)
    serialized_loans = schema.dump(loans)

    for s_loan in serialized_loans:
        s_loan.update(get_customer_display_info(s_loan.get("customer_profile_id")))

    return jsonify(serialized_loans), 200

@servicing_bp.route("/loans/paid", methods=["GET"])
@permission_required("loan:approve")
def get_paid_loans():
    from underwriting.models import Loan
    from underwriting.schemas import LoanSchema
    from foundations.auth import get_user_institution_id
    from origination.services import get_customer_display_info
    from servicing.models import Transaction

    actor_id = _current_user_id()
    institution_id = get_user_institution_id(actor_id)

    # Fully repaid loans. The loan-level status is "fully_paid" (see
    # LOAN_STATUSES); "completed" is a Transaction status and never matches here.
    loans = Loan.query.filter_by(lending_institution_id=institution_id, status="fully_paid").order_by(Loan.created_at.desc()).all()

    schema = LoanSchema(many=True)
    serialized_loans = schema.dump(loans)

    for s_loan in serialized_loans:
        s_loan.update(get_customer_display_info(s_loan.get("customer_profile_id")))

        # Attach total amount paid (sum of successful repayment transactions)
        txns = Transaction.query.filter_by(loan_id=s_loan["id"], transaction_type="repayment", status="completed").all()
        s_loan["total_repaid"] = sum(t.amount for t in txns)
        
    return jsonify(serialized_loans), 200
