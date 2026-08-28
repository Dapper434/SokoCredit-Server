from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError

from foundations.auth import AuthError, permission_required

from underwriting.schemas import (
    LoanSchema,
    LoanProposalSchema,
    LoanApprovalSchema,
    ApprovalDecisionSchema,
    CreditScoreLogSchema,
    CreditScoreRecalculateSchema,
    AvailableCreditSchema,
)

from underwriting.services import (
    propose_loan,
    approve_loan,
    reject_loan,
    disburse_loan,
    get_available_credit,
    recalculate_credit_score,
    get_loan as fetch_loan,
    list_loan_approvals as fetch_loan_approvals,
)

underwriting_bp = Blueprint("underwriting", __name__, url_prefix="/api/underwriting")

loan_schema = LoanSchema()
loan_proposal_schema = LoanProposalSchema()
loan_approval_schema = LoanApprovalSchema()
approval_decision_schema = ApprovalDecisionSchema()
credit_score_log_schema = CreditScoreLogSchema()
credit_score_recalculate_schema = CreditScoreRecalculateSchema()
available_credit_schema = AvailableCreditSchema()

def _current_user_id()-> int:
    return int(get_jwt_identity())

def _auth_error_response(exc:AuthError):
    return jsonify({"error": exc.message}), exc.status_code

@underwriting_bp.route("/loans", methods=["POST"])
@permission_required("loan:create")
def create_loan_proposal():
    #granted to loan_officer, manager & admin 
    try:
        data = loan_proposal_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors":err.messages}), 400

    actor_id = _current_user_id()
    notes = data.pop("notes", None)

    try:
        loan = propose_loan(actor_id, **data, notes=notes)
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 201

@underwriting_bp.route("/loans/<int:loan_id>", methods=["GET"])
@jwt_required()
def get_loan_route(loan_id):
    try:
        loan = fetch_loan(loan_id)
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 200

@underwriting_bp.route("/loans/<int:loan_id>/approvals", methods=["GET"])
@jwt_required()
def list_loan_approvals_route(loan_id):
    """full maker checker history for a loan"""
    try:
        approvals = fetch_loan_approvals(loan_id)
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_approval_schema.dump(approvals, many=True)), 200


@underwriting_bp.route("/loans/<int:loan_id>/approve", methods=["POST"])
@permission_required("loan:approve")
def approve_loan_route(loan_id):
    #granted to manager admin & super_admin

    try:
        data = approval_decision_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify ({"errors": err.messages}), 400

    checker_id = _current_user_id()

    try:
        loan = approve_loan(loan_id=loan_id, checker_id=checker_id, notes=data.get("notes"))
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 200


@underwriting_bp.route("/loans/<int:loan_id>/reject", methods=["POST"])
@permission_required("loan:approve")
def reject_loan_route(loan_id):
    try:
        data = approval_decision_schema.load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

    checker_id = _current_user_id()

    try:
        loan = reject_loan(loan_id=loan_id, checker_id=checker_id, notes=data.get("notes"))
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 200

@underwriting_bp.route("/loans/<int:loan_id>/disburse", methods=["POST"])
@permission_required("loan:disburse")
def disburse_loan_route(loan_id):
    actor_id = _current_user_id()
    try:
        loan = disburse_loan(loan_id=loan_id, actor_id=actor_id)
    except NotImplementedError as exc:
        return jsonify({"error": str(exc)}), 501
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 200

@underwriting_bp.route("/customers/<int:customer_profile_id>/available-credit", methods=["GET"])
@jwt_required()
def get_available_credit_route(customer_profile_id):
    try:
        available = get_available_credit(customer_profile_id)
    except AuthError as exc:
        return _auth_error_response(exc)
 
    payload = {"customer_profile_id": customer_profile_id, "available_credit": available}
    return jsonify(available_credit_schema.dump(payload)), 200

@underwriting_bp.route("/customers/<int:customer_profile_id>/credit-score", methods=["POST"])
@jwt_required()
def recalculate_credit_score_route(customer_profile_id):
    #revisited once real scoring engine exists
    try:
        data = credit_score_recalculate_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400
 
    actor_id = _current_user_id()
 
    try:
        entry = recalculate_credit_score(
            customer_profile_id=customer_profile_id,
            on_time_rate=data["on_time_rate"],
            completed_loan_cycles=data["completed_loan_cycles"],
            has_defaulted_loan=data["has_defaulted_loan"],
            reschedule_count=data["reschedule_count"],
            actor_id=actor_id,
        )
    except AuthError as exc:
        return _auth_error_response(exc)
 
    return jsonify(credit_score_log_schema.dump(entry)), 201