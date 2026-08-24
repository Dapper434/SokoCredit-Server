from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, create_access_token
from marshmallow import ValidationError

from foundations.auth import (
    AuthError,
    register_user,
    authenticate_user,
    issue_tokens,
    get_current_user,
    role_required,
)

from foundations.institutions import register_institution, attach_document, add_market

from foundations.schemas import (
    InstitutionRegistrationSchema,
    RegisterUserSchema,
    LoginSchema,
    UserSchema,
    LendingInstitutionSchema,
)

foundation_bp = Blueprint("foundation", __name__)

user_schema = UserSchema()
institution_schema = LendingInstitutionSchema()

@foundation_bp.errorhandler(AuthError)
def handle_auth_error(err: AuthError):
    return jsonify({"error": err.message}), err.status_code

@foundation_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"error": "Validation failed", "details": err.messages}), 422

# onboard an organization and its admin user onto the platform
@foundation_bp.post("/organizations")
def signup_organization():
    data = InstitutionRegistrationSchema().load(request.get_json() or {})
    markets = data.pop("primary_markets", [])

    institution, admin = register_institution(**data)
    
    for market_name in markets:
        add_market(institution.id, market_name, actor_id=admin.id)
    tokens = issue_tokens(admin)
    return jsonify({
        "institution": institution_schema.dump(institution),
        "user": user_schema.dump(admin),
        **tokens,
    }), 201

@foundation_bp.post("/institutuions/<int:institution_id>/documents")
@jwt_required()
def upload_document(institution_id):
    #attach compliance document metadata
    actor = get_current_user()
    body = request.get_json() or {}
    doc = attach_document(
        lending_institution_id=institution_id,
        document_type=body.get("document_type"),
        file_url=body.get("file_url"),
        uploaded_by=actor.id,
    )
    return jsonify({"id":doc.id, "document_type": doc.document_type, "file_url": doc.file_url}), 201

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


@foundation_bp.get("/me")
@jwt_required()
def me():
    user = get_current_user()
    return jsonify(user_schema.dump(user)), 200

#Add another staff member to the caller's own organization.
@foundation_bp.post("/users")
@role_required("admin", "super_admin")
def add_teammate():
    
    data = RegisterUserSchema().load(request.get_json() or {})
    actor = get_current_user()
    new_user = register_user(
        organization_id=actor.organization_id,
        email=data["email"],
        password=data["password"],
        full_name=data["full_name"],
        role=data["role"],
        actor_id=actor.id,
    )
    return jsonify(user_schema.dump(new_user)), 201