from marshmallow import Schema, fields, validate

from foundations.models import ROLES

class InstitutionRegistrationSchema(Schema):
    #onboarding process covering all 3 pages

    #page 1 - Business Identity & Physical Prescence

    registered_business_name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    registration_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    kra_pin = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    operating_liscence_type = fields.Str(required=False, allow_none=True)
    cbk_liscence_number = fields.Str(required=False, allow_none=True)
    head_office_address = fields.Str(required=True, validate=validate.Length(min=2, max=255))
    head_office_lat = fields.Float(required=False, allow_none=True)
    head_office_long = fields.Float(required=False, allow_none=True)

    #page 2 - Regulatory Compliance & Operation Footprint

    county_business_permit_number = fields.Str(required=False, allow_none=True)
    odpc_registration_number = fields.Str(required=False, allow_none=True)
    estimated_staff_count = fields.Int(required=False, allow_none=True, validate=validate.Range(min=0))

    #admin founder details

    admin_full_name= fields.Str(required=True, validate=validate.Length(min=2, max=150))
    admin_national_id_number = fields.Str(required=False, allow_none=True)
    admin_email = fields.Email(required=True)
    admin_password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))

    #page 3 - Operational Settlement

    bank_name = fields.Str(required=False, allow_none=True)
    bank_account_number = fields.Str(required=False, allow_none=True)
    collection_paybill_number = fields.Str(required=True, validate=validate.Length(min=2, max=20)) 
    default_interest_rate = fields.Float(required=False, allow_none=True)
    default_penalty_rate = fields.Float(required=False, allow_none=True)

    primary_markets = fields.List(
        fields.Str(), required=False, load_default=list, validate=validate.Length(max=6)
    )



class RegisterUserSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))
    full_name = fields.Str(required=True, validate=validate.Length(min=2, max=150))
    phone_number = fields.Str(required=False, allow_none=True)
    national_id_number = fields.Str(required=False, allow_none=True)
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