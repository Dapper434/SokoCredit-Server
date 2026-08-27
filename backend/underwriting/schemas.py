from marshmallow import Schema, fields, validate

from underwriting.models import (
    CREDIT_TIERS,
    LOAN_STATUSES,
    REPAYMENT_FREQUENCIES,
    APPROVAL_DECISIONS
)

#loan

class LoanSchema(Schema):
    id = fields.Int(dump_only=True)
    lending_institution_id = fields.Int(dump_only=True)
    customer_profile_id = fields.Int(dump_only=True)

    principal = fields.Decimal(as_string=True, dump_only=True)
    interest_rate = fields.Decimal(as_string=True, dump_only=True)
    term_days = fields.Int(dump_only=True)
    repayment_frequency = fields.Str(dump_only=True)
    loan_purpose = fields.Str(dump_only=True, allow_none=True)

    status = fields.Str(dump_only=True)
    disbursed_at = fields.DateTime(dump_only=True, allow_none=True)
    maturity_date = fields.Date(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True) 


class LoanProposalSchema(Schema):
    customer_profile_id = fields.Int(required=True)

    principal = fields.Decimal(as_string=True, required=True, validate=validate.Range(min=0.01))
    interest_rate = fields.Decimal(as_string=True, required=True, validate=validate.Range(min=0))
    term_days = fields.Int(required=True, validate=validate.Range(min=1))
    repayment_frequency = fields.Str(
        required=True, validate=validate.OneOf(REPAYMENT_FREQUENCIES)
    )
    loan_purpose = fields.Str(required=False, allow_none=True)
    notes = fields.Str(required=False, allow_none=True, metadata={"description": "maker's notes"})


class LoanApprovalSchema(Schema):
    id = fields.Int(dump_only=True)
    loan_id = fields.Int(dump_only=True)
    maker_id = fields.Int(dump_only=True)
    checker_id = fields.Int(dump_only=True, allow_none=True)
    maker_notes = fields.Str(dump_only=True, allow_none=True)
    checker_notes = fields.Str(dump_only=True, allow_none=True)
    decision = fields.Str(dump_only=True, validate=validate.OneOf(APPROVAL_DECISIONS))
    maker_action_at = fields.DateTime(dump_only=True)
    checker_action_at = fields.DateTime(dump_only=True, allow_none=True)


class ApprovalDecisionSchema(Schema):
    notes = fields.Str(required=False, allow_none=True)

#credit scoring

class CreditScoreLogSchema(Schema):
    id = fields.Int(dump_only=True)
    customer_profile_id = fields.Int(dump_only=True)
    previous_tier = fields.Str(dump_only=True, allow_none=True)
    new_tier = fields.Str(dump_only=True, validate=validate.OneOf(CREDIT_TIERS))
    score_components = fields.Dict(dump_only=True, allow_none=True)
    calculated_at = fields.DateTime(dump_only=True)

class CreditScoreRecalculateSchema(Schema):
    new_tier = fields.Str(required=True, validate=validate.OneOf(CREDIT_TIERS))
    score_components = fields.Dict(required=False, allow_none=True)

class AvailableCreditSchema(Schema):
    customer_profile_id = fields.Int(dump_only=True)
    available_credit = fields.Decimal(as_string=True, dump_only=True)

#savings account

class SavingsAccountSchema(Schema):
    id = fields.Int(dump_only=True)
    customer_profile_id = fields.Int(dump_only=True)
    total_savings_balance = fields.Decimal(as_string=True, dump_only=True)
    days_saved_count = fields.Int(dump_only=True)
    savings_start_date = fields.Date(dump_only=True, allow_none=True)
    is_savings_mature = fields.Bool(dump_only=True)