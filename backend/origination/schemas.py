from marshmallow import Schema, fields, validate

class CustomerProfileCreateSchema(Schema):
    #POST/api/origination/sutomers

    user_id = fields.Int(required=True)
    national_id_number = fields.Str(required=True, validate=validate.Length(min=2, max=20))
    date_of_birth = fields.Date(required=False, allow_none=True)
    gender = fields.Str(required=False, allow_none=True)
    business_type = fields.Str(required=False, allow_none=True)
    monthly_income_range = fields.Str(required=False, allow_none=True)
    residential_address = fields.Str(required=False, allow_none=True)
    next_of_kin_name = fields.Str(required=False, allow_none=True)
    next_of_kin_phone = fields.Str(required=False, allow_none=True)
    next_of_kin_email = fields.Str(required=False, allow_none=True)
    market_stall_id = fields.Int(required=False, allow_none=True)

class DocumentUploadSchema(Schema):
    #POST/api/origination/customers/<id>/documents

    document_type = fields.Str(
        required=True,
        validate=validate.OneOf(
            ["national_id", "business_permit", "mpesa_statement", "profile_photo"]
        ),
    )
    file_url = fields.Str(required=True)

class BadgeAwardSchema(Schema):
    #POST/api/origination/customers/<id>/badges
    badge_id = fields.Int(required=True)

class CustomerProfileSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)
    national_id_number = fields.Str(dump_only=True)
    date_of_birth = fields.Date(dump_only=True, allow_none=True)
    gender = fields.Str(dump_only=True, allow_none=True)
    business_type = fields.Str(dump_only=True, allow_none=True)
    monthly_income_range = fields.Str(dump_only=True, allow_none=True)
    residential_address = fields.Str(dump_only=True, allow_none=True)
    next_of_kin_name = fields.Str(dump_only=True, allow_none=True)
    next_of_kin_phone = fields.Str(dump_only=True, allow_none=True)
    next_of_kin_email = fields.Str(dump_only=True, allow_none=True)
    market_stall_id = fields.Int(dump_only=True, allow_none=True)
    credit_tier = fields.Str(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)

    market_name = fields.Method("get_market_name", dump_only=True)
    stall_number = fields.Method("get_stall_number", dump_only=True)

    def get_market_name(self, obj):
        return obj.market_stall.market_name if obj.market_stall else None

    def get_stall_number(self, obj):
        return obj.market_stall.stall_number if obj.market_stall else None


class CustomerRegisterSchema(Schema):
    phone_number = fields.Str(required=True, validate=validate.Length(min=9, max=20))
    pin = fields.Str(required=True, validate=validate.Length(min=5))
    full_name = fields.Str(required=True, validate=validate.Length(min=2, max=150))
    national_id_number = fields.Str(required=True, validate=validate.Length(min=2, max=20))
    lending_institution_id = fields.Int(required=True)
    branch_id = fields.Int(required=False, allow_none=True)
    date_of_birth = fields.Date(required=False, allow_none=True)
    gender = fields.Str(required=False, allow_none=True)
    business_type = fields.Str(required=False, allow_none=True)
    monthly_income_range = fields.Str(required=False, allow_none=True)
    residential_address = fields.Str(required=False, allow_none=True)
    next_of_kin_name = fields.Str(required=False, allow_none=True)
    next_of_kin_phone = fields.Str(required=False, allow_none=True)
    next_of_kin_email = fields.Str(required=False, allow_none=True)
    market_name = fields.Str(required=False, allow_none=True)
    stall_number = fields.Str(required=False, allow_none=True)
