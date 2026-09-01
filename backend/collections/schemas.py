from marshmallow import Schema, fields, validate

from collections.models import CHANNELS, MESSAGE_TYPES, DELIVERY_STATUSES, PROMISE_STATUSES

class NotificationLogSchema(Schema):
    id = fields.Int(dump_only=True)
    customer_profile_id = fields.Int(dump_only=True, allow_none=True)
    recipient_user_id = fields.Int(dump_only=True, allow_none=True)
    loan_id = fields.Int(dump_only=True, allow_none=True)
    channel = fields.Str(dump_only=True, validate=validate.OneOf(CHANNELS))
    message_type = fields.Str(dump_only=True, validate=validate.OneOf(MESSAGE_TYPES))
    delivery_status = fields.Str(dump_only=True, validate=validate.OneOf(DELIVERY_STATUSES))
    provider_reference = fields.Str(dump_only=True, allow_none=True)
    sent_at = fields.DateTime(dump_only=True, allow_none=True)