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
    market_stall_id = fields.Int(required=False, allow_none=True)