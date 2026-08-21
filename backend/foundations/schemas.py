from marshmallow import Schema, fields, validate

from foundations.models import ROLES

class OrganizationSignupSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=2, max=150))
    slug = fields.Str(
        required=True,
        # make sure the slug is unique and only contains lowercase letters, numbers, and hyphens
        validate=validate.Regexp(r"^[a-z0-9-]+$", error="Slug must be lowercase letters, numbers, hyphens only."),
    )
    admin_email = fields.Email(required=True)
    admin_password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))
    admin_full_name = fields.Str(required=True, validate=validate.Length(min=2, max=150))


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