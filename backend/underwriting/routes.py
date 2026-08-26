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

@underwriting_bp.route("/loans/<int:loan_id", methods=["GET"])
@jwt_required()
def get_loan_route(loan_id):
    try:
        loan = fetch_loan(loan_id)
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(loan_schema.dump(loan)), 200
