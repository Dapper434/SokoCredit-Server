from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, create_access_token
from marshmallow import ValidationError

from foundations.auth import (
    AuthError,
    register_user,
    register_organization,
    authenticate_user,
    issue_tokens,
    get_current_user,
    role_required,
)

from foundations.schemas import (
    OrganizationSignupSchema,
    RegisterUserSchema,
    LoginSchema,
    UserSchema,
    OrganizationSchema,
)

foundation_bp = Blueprint("foundation", __name__)

user_schema = UserSchema()
organization_schema = OrganizationSchema()

@foundation_bp.errorhandler(AuthError)
def handle_auth_error(err: AuthError):
    return jsonify({"error": err.message}), err.status_code

@foundation_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"error": "Validation failed", "details": err.messages}), 422

# onboard an organization and its admin user onto the platform
@foundation_bp.post("/organizations")
def signup_organization():
    data = OrganizationSignupSchema().load(request.get_json() or {})
    org, admin = register_organization(
        name=data["name"],
        slug=data["slug"],
        admin_email=data["admin_email"],
        admin_password=data["admin_password"],
        admin_full_name=data["admin_full_name"],
    )
    tokens = issue_tokens(admin)
    return jsonify({
        "organization": organization_schema.dump(org),
        "user": user_schema.dump(admin),
        **tokens,
    }), 201


@foundation_bp.post("/login")
def login():
    data = LoginSchema().load(request.get_json() or {})
    user = authenticate_user(data["email"], data["password"])
    tokens = issue_tokens(user)
    return jsonify({"user": user_schema.dump(user), **tokens}), 200


#Exchange a refresh token for a new access token.
@foundation_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    claims = get_jwt()
    new_access_token = create_access_token(
        identity=identity,
        additional_claims={"organization_id": claims["organization_id"], "role": claims["role"]},
    )
    return jsonify({"access_token": new_access_token}), 200