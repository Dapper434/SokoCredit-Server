from marshmallow import Schema, fields, validate
from .models import CHANNELS, RESCHEDULE_MODES

class RepaymentScheduleSchema(Schema):
    id = fields.Int(dump_only=True)
    loan_id = fields.Int(dump_only=True)
    installment_number = fields.Int(dump_only=True)
    due_date = fields.Date(dump_only=True)
    principal_due = fields.Decimal(as_string=True, dump_only=True)
    interest_due = fields.Decimal(as_string=True, dump_only=True)
    total_due = fields.Decimal(as_string=True, dump_only=True)
    amount_paid = fields.Decimal(as_string=True, dump_only=True)
    status = fields.Str(dump_only=True)
    paid_at = fields.DateTime(dump_only=True)

class TransactionSchema(Schema):
    id = fields.Int(dump_only=True)
    loan_id = fields.Int(dump_only=True)
    repayment_schedule_id = fields.Int(dump_only=True)
    amount = fields.Decimal(as_string=True, dump_only=True)
    channel = fields.Str(dump_only=True)
    gateway_reference = fields.Str(dump_only=True)
    transaction_type = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    allocation_breakdown = fields.List(fields.Dict(), dump_only=True)
    created_at = fields.DateTime(dump_only=True)

class RecordRepaymentSchema(Schema):
    amount = fields.Decimal(required=True)
    channel = fields.Str(required=True, validate=validate.OneOf(CHANNELS))
    gateway_reference = fields.Str(required=True, validate=validate.Length(min=1, max=255))

class RescheduleRequestSchema(Schema):
    reason_category = fields.Str(required=True, validate=validate.Length(min=5))
    requested_mode = fields.Str(required=True, validate=validate.OneOf(RESCHEDULE_MODES))
    requested_extension_days = fields.Int(required=True)

class RescheduleRequestOutputSchema(Schema):
    id = fields.Int(dump_only=True)
    loan_id = fields.Int(dump_only=True)
    requested_by = fields.Int(dump_only=True)
    reason_category = fields.Str(dump_only=True)
    requested_mode = fields.Str(dump_only=True)
    requested_extension_days = fields.Int(dump_only=True)
    admin_decision = fields.Str(dump_only=True)
    reviewed_by_user_id = fields.Int(dump_only=True)
    reviewed_at = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

