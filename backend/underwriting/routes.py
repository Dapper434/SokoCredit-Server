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
