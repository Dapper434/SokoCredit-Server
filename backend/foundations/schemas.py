from marshmallow import Schema, fields, validate

from foundations.models import ROLES

class InstitutionRegistrationSchema(Schema):
    #onboarding process covering all 3 pages

    #page 1 - Business Identity & Physical Prescence

    registered_business_name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    registration_number = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    kra_pin = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    operating_license_type = fields.Str(required=False, allow_none=True)
    cbk_license_number = fields.Str(required=False, allow_none=True)
    head_office_address = fields.Str(required=True, validate=validate.Length(min=2, max=255))
    head_office_lat = fields.Float(required=False, allow_none=True)
    head_office_lng = fields.Float(required=False, allow_none=True)

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
    collection_paybill_number = fields.Str(required=False, validate=validate.Length(min=2, max=20)) 
    airtel_paybill_number = fields.Str(required=False, allow_none=True, validate=validate.Length(max=20))
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
    lending_institution_id = fields.Int(dump_only=True)
    email = fields.Email(dump_only=True)
    full_name = fields.Str(dump_only=True)
    role = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    last_login_at = fields.DateTime(dump_only=True, allow_none=True)

class InstitutionSettingsSchema(Schema):
    id = fields.Int(dump_only=True)
    registered_business_name = fields.Str(dump_only=True)
    collection_paybill_number = fields.Str(dump_only=True, allow_none=True)
    airtel_paybill_number = fields.Str(dump_only=True, allow_none=True)
    default_interest_rate = fields.Decimal(as_string=True, dump_only=True, allow_none=True)
    default_penalty_rate = fields.Decimal(as_string=True, dump_only=True, allow_none=True)
    status = fields.Str(dump_only=True)


class InstitutionSettingRequestCreateSchema(Schema):
    field_changed = fields.Str(required=True)
    new_value = fields.Str(required=True)


class InstitutionSettingRequestSchema(Schema):
    id = fields.Int(dump_only=True)
    lending_institution_id = fields.Int(dump_only=True)
    requested_by_user_id = fields.Int(dump_only=True)
    field_changed = fields.Str(dump_only=True)
    old_value = fields.Str(dump_only=True, allow_none=True)
    new_value = fields.Str(dump_only=True)
    approved_by_user_id = fields.Int(dump_only=True, allow_none=True)
    status = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class LendingInstitutionSchema(Schema):
    id = fields.Int(dump_only=True)
    registered_business_name = fields.Str(dump_only=True)
    registration_number = fields.Str(dump_only=True)
    kra_pin = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)