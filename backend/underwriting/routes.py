from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError

from foundations.auth import AuthError, permission_required

from underwriting.schemas import (
    LoanSchema,
    LoanProposalSchema,
    LoanApplicationSchema,
    LoanApprovalSchema,
    ApprovalDecisionSchema,
    CreditScoreLogSchema,
    CreditScoreRecalculateSchema,
    AvailableCreditSchema,
)

from underwriting.services import (
    propose_loan,
    apply_for_loan,
    approve_loan,
    reject_loan,
    disburse_loan,
    get_available_credit,
    recalculate_credit_score,
    get_loans_due,
    list_loans_for_institution,
    get_loan as fetch_loan,
    list_loan_approvals as fetch_loan_approvals,
)

underwriting_bp = Blueprint("underwriting", __name__, url_prefix="/api/underwriting")

loan_schema = LoanSchema()
loan_proposal_schema = LoanProposalSchema()
loan_application_schema = LoanApplicationSchema()
loan_approval_schema = LoanApprovalSchema()
approval_decision_schema = ApprovalDecisionSchema()
credit_score_log_schema = CreditScoreLogSchema()
credit_score_recalculate_schema = CreditScoreRecalculateSchema()
available_credit_schema = AvailableCreditSchema()

def _current_user_id()-> int:
    return int(get_jwt_identity())

def _auth_error_response(exc:AuthError):
    return jsonify({"error": exc.message}), exc.status_code

@underwriting_bp.route("/applications", methods=["POST"])
@jwt_required()
def apply_for_loan_route():
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    if claims.get("role") != "customer":
        return jsonify({"error": "Only customers can apply for loans via this route."}), 403

    try:
        data = loan_application_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

    actor_id = _current_user_id()
    customer_profile_id = claims.get("customer_profile_id")
    
    try:
        loan = apply_for_loan(actor_id, customer_profile_id=customer_profile_id, **data)
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 201

@underwriting_bp.route("/loan-terms", methods=["GET"])
@jwt_required()
def get_loan_terms_route():
    """The lending terms quoted to the authenticated customer before applying.

    Returns the same rate apply_for_loan will stamp on the loan, plus the
    normalized decimal the repayment schedule will actually charge, so the
    wizard's quote cannot drift from the amount billed.
    """
    from decimal import Decimal, InvalidOperation
    from flask_jwt_extended import get_jwt
    from underwriting.services import get_default_interest_rate
    from servicing.services import (
        normalize_interest_rate,
        calculate_loan_totals,
        _installment_count,
    )

    claims = get_jwt()
    if claims.get("role") != "customer":
        return jsonify({"error": "Only customers can view their loan terms."}), 403

    institution_id = claims.get("lending_institution_id")
    if not institution_id:
        return jsonify({"error": "No institution on this account."}), 403

    from underwriting.services import (
        get_available_credit,
        get_institution_max_loan_limit,
    )

    rate = get_default_interest_rate(institution_id)
    # Both limits come from the same functions used to gate the application, and
    # are recomputed on every call so newly-saved KES 200 check-ins show up here
    # without the customer reloading.
    profile_id = claims.get("customer_profile_id")
    terms = {
        "interest_rate": str(rate),
        "interest_rate_decimal": str(normalize_interest_rate(rate)),
        "available_credit": str(get_available_credit(profile_id)) if profile_id else None,
        "max_loan_limit": str(get_institution_max_loan_limit(institution_id)),
    }

    # Optional quote: with amount + term_days, price the loan through the very
    # same function that generates the repayment schedule.
    amount = request.args.get("amount")
    term_days = request.args.get("term_days")
    if amount is not None and term_days is not None:
        try:
            principal = Decimal(str(amount))
            days = int(term_days)
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({"error": "amount and term_days must be numeric."}), 400
        if principal <= 0 or days <= 0:
            return jsonify({"error": "amount and term_days must be positive."}), 400

        frequency = request.args.get("repayment_frequency", "weekly")
        totals = calculate_loan_totals(
            principal=principal,
            annual_rate=rate,
            term_days=days,
            num_installments=_installment_count(frequency, days),
        )
        terms["quote"] = {key: str(value) for key, value in totals.items()}
        terms["quote"]["num_installments"] = totals["num_installments"]
        terms["quote"]["repayment_frequency"] = frequency
        terms["quote"]["term_days"] = days

    return jsonify(terms), 200


@underwriting_bp.route("/applications/pending", methods=["GET"])
@permission_required("loan:approve")
def get_pending_applications_route():
    # Only branch managers / authorized personnel can view pending applications for their org
    from underwriting.models import Loan
    from foundations.auth import get_user_institution_id
    from origination.services import get_customer_display_info

    actor_id = _current_user_id()
    institution_id = get_user_institution_id(actor_id)

    loans = Loan.query.filter_by(lending_institution_id=institution_id, status="pending").order_by(Loan.created_at.asc()).all()

    serialized_loans = loan_schema.dump(loans, many=True)

    # Enrich with the applicant's name and tier (owned by Origination), and flag
    # requests that exceeded the customer's limit so reviewers can see them.
    for s_loan, loan in zip(serialized_loans, loans):
        s_loan.update(get_customer_display_info(s_loan.get("customer_profile_id")))

        limit_then = loan.available_credit_at_application
        s_loan["available_credit_at_application"] = (
            str(limit_then) if limit_then is not None else None
        )
        s_loan["exceeds_available_credit"] = (
            limit_then is not None and loan.principal > limit_then
        )

    return jsonify(serialized_loans), 200

@underwriting_bp.route("/loans", methods=["POST"])
@permission_required("loan:create")
def create_loan_proposal():
    #granted to loan_officer & branch_manager
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
        from flask_jwt_extended import get_jwt
        claims = get_jwt()
        if claims.get("role") == "customer" and loan.customer_profile_id != claims.get("customer_profile_id"):
             return jsonify({"error": "You do not have permission to view this loan."}), 403
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 200

@underwriting_bp.route("/loans/my", methods=["GET"])
@jwt_required()
def get_my_loans_route():
    from flask_jwt_extended import get_jwt
    from underwriting.models import Loan, LoanApproval
    claims = get_jwt()
    if claims.get("role") != "customer":
        return jsonify({"error": "Only customers can access this route"}), 403

    loans = Loan.query.filter_by(
        customer_profile_id=claims.get("customer_profile_id")
    ).order_by(Loan.id.desc()).all()

    serialized = loan_schema.dump(loans, many=True)

    # Attach the latest maker-checker outcome so the customer portal can show a
    # rejection (with the reviewer's note) rather than a loan stuck at "pending".
    for row, loan in zip(serialized, loans):
        approval = (
            LoanApproval.query.filter_by(loan_id=loan.id)
            .order_by(LoanApproval.maker_action_at.desc())
            .first()
        )
        row["approval_decision"] = approval.decision if approval else None
        row["approval_notes"] = approval.checker_notes if approval else None
        row["approval_action_at"] = (
            approval.checker_action_at.isoformat()
            if approval and approval.checker_action_at else None
        )

    return jsonify(serialized), 200

@underwriting_bp.route("/loans/<int:loan_id>/approve", methods=["POST"])
@permission_required("loan:approve")
def approve_loan_route(loan_id):
    #granted to branch_manager

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
    #revisited once real scoring engine exisits
    try:
        data = credit_score_recalculate_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400
 
    actor_id = _current_user_id()
 
    try:
        entry = recalculate_credit_score(
            customer_profile_id=customer_profile_id,
            new_tier=data["new_tier"],
            score_components=data.get("score_components"),
            actor_id=actor_id,
        )
    except AuthError as exc:
        return _auth_error_response(exc)

# ── Teammate additions: due-loan worklists + full-book reporting ──────────────

@underwriting_bp.route("/loans/<int:loan_id>/approvals", methods=["GET"])
@jwt_required()
def list_loan_approvals_route(loan_id):
    """Full maker-checker history for a loan."""
    try:
        approvals = fetch_loan_approvals(loan_id)
    except AuthError as exc:
        return _auth_error_response(exc)
    return jsonify(loan_approval_schema.dump(approvals, many=True)), 200


@underwriting_bp.route("/loans/due/mine", methods=["GET"])
@jwt_required()
def get_my_due_loans_route():
    """An authenticated officer's assigned customers' due loans."""
    actor_id = _current_user_id()
    try:
        loans = get_loans_due(actor_id=actor_id, only_mine=True)
    except AuthError as exc:
        return _auth_error_response(exc)
    return jsonify(loan_schema.dump(loans, many=True)), 200


@underwriting_bp.route("/loans/due/institution", methods=["GET"])
@permission_required("reports:view")
def get_institution_due_loans_route():
    """Institution-wide due loans (oversight)."""
    actor_id = _current_user_id()
    try:
        loans = get_loans_due(actor_id=actor_id, only_mine=False)
    except AuthError as exc:
        return _auth_error_response(exc)
    return jsonify(loan_schema.dump(loans, many=True)), 200


@underwriting_bp.route("/loans", methods=["GET"])
@permission_required("reports:view")
def list_institution_loans_route():
    """Full portfolio for Analytics/Collections reporting (GLP, PAR, composition)."""
    status_filter = request.args.get("status")
    actor_id = _current_user_id()
    try:
        loans = list_loans_for_institution(actor_id=actor_id, status_filter=status_filter)
    except AuthError as exc:
        return _auth_error_response(exc)
    return jsonify(loan_schema.dump(loans, many=True)), 200
