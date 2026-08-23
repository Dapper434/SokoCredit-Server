from marshmallow import Schema, fields, validate

from foundations.models import ROLES

class InstitutionRegistrationSchema(Schema):
    #onboarding process covering all 3 pages

    #page 1 - Business Identity & Physical Prescence
    registered_business_name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    registration_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    kra_pin = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    operating_liscence_type = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    cbk_liscence_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    head_office_address = fields.Str(required=True, validate=validate.Length(min=2, max=255))
    head_office_lat = fields.Float(required=True, allow_none=True)
    head_office_long = fields.Float(required=True, allow_none=True)

    #page 2 - Regulatory Compliance & Operation Footprint
    county_business_permit_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    odpc_registration_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    estimated_staff_count = fields.Int(required=True, allow_none=True, validate=validate.Range(min=0))

    #page 3 - Operational Settlement
    bank_name = fields.Str(required=True, validate=validate.Length(min=2, max=255))
    bank_account_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    collection_paybill_number = fields.Str(required=True, validate=validate.Length(min=2, max=20)) 
    default_interest_rate = fields.Float(required=True, validate=validate.Range(min=0, max=100))
    default_penalty_rate = fields.Float(required=True, validate=validate.Range(min=0, max=100))

    primary_markets = fields.List(
        fields.Str(), required=False, load_default=list, validate=validate.Length(max=6)
    )



class RegisterUserSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))
    full_name = fields.Str(required=True, validate=validate.Length(min=2, max=150))
    role = fields.Str(required=True, validate=validate.OneOf(ROLES))

class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True,load_only=True)


class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    organization_id = fields.Int(dump_only=True)
    email = fields.Email(dump_only=True)
    full_name = fields.Str(dump_only=True)
    role = fields.Str(dump_only=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    last_login_at = fields.DateTime(dump_only=True, allow_none=True)

class OrganizationSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(dump_only=True)
    slug = fields.Str(dump_only=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)