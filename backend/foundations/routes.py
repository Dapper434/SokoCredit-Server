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
    verify_institution_access,
)

from foundations.institutions import (
    register_institution,
    attach_document,
    add_market,
    get_institution_settings,
    request_setting_change,
    approve_setting_change,
    list_setting_requests,
    get_document_download_url,
)

from foundations.schemas import (
    InstitutionRegistrationSchema,
    RegisterUserSchema,
    LoginSchema,
    UserSchema,
    LendingInstitutionSchema,
    InstitutionSettingsSchema,
    InstitutionSettingRequestCreateSchema,
    InstitutionSettingRequestSchema,
)

foundation_bp = Blueprint("foundation", __name__)

user_schema = UserSchema()
institution_schema = LendingInstitutionSchema()

@foundation_bp.errorhandler(AuthError)
def handle_auth_error(err: AuthError):
    return jsonify({"status": "error", "message": err.message}), err.status_code

@foundation_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"error": "Validation failed", "details": err.messages}), 422

# onboard an organization and its admin user onto the platform
@foundation_bp.post("/institutions")
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
        "role": admin.role,
        **tokens,
    }), 201

@foundation_bp.post("/institutions/<int:institution_id>/documents")
@jwt_required()
def upload_document(institution_id):
    """Attach a compliance document.

    multipart/form-data with a `file` field  -> server-side Supabase upload
    application/json with `file_url`          -> metadata-only (client uploaded)
    """
    actor = get_current_user()

    if "file" in request.files:
        file = request.files["file"]
        document_type = request.form.get("document_type")
        if not document_type:
            return jsonify({"error": "document_type is required."}), 400
        doc = attach_document(
            lending_institution_id=institution_id,
            document_type=document_type,
            file_bytes=file.read(),
            content_type=file.content_type,
            original_filename=file.filename,
            uploaded_by=actor.id,
        )
    else:
        body = request.get_json() or {}
        doc = attach_document(
            lending_institution_id=institution_id,
            document_type=body.get("document_type"),
            file_url=body.get("file_url"),
            uploaded_by=actor.id,
        )
    return jsonify({
        "id": doc.id, "document_type": doc.document_type,
        "file_url": doc.file_url, "storage_path": doc.storage_path,
    }), 201


@foundation_bp.get("/institutions/<int:institution_id>/documents/<int:document_id>/download")
@jwt_required()
def download_document(institution_id, document_id):
    verify_institution_access(institution_id)
    url = get_document_download_url(document_id, institution_id)
    return jsonify({"url": url}), 200

@foundation_bp.post("/lender/login")
def login():
    data = LoginSchema().load(request.get_json() or {})
    user = authenticate_user(data["email"], data["password"])
    tokens = issue_tokens(user)
    
    return jsonify({
        "status": "success",
        "token": tokens["access_token"],
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "institution_id": user.lending_institution_id,
            "institution_name": user.lending_institution.registered_business_name if user.lending_institution else None
        }
    }), 200


#Exchange a refresh token for a new access token.
@foundation_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    claims = get_jwt()
    new_access_token = create_access_token(
        identity=identity,
        additional_claims={"lending_institution_id": claims["lending_institution_id"], "role": claims["role"]},
    )
    return jsonify({"access_token": new_access_token}), 200


@foundation_bp.get("/me")
@jwt_required()
def me():
    user = get_current_user()
    return jsonify(user_schema.dump(user)), 200

#Add another staff member to the caller's own organization.
@foundation_bp.post("/users")
@role_required("branch_manager")
def add_teammate():
    
    data = RegisterUserSchema().load(request.get_json() or {})
    actor = get_current_user()
    new_user = register_user(
        lending_institution_id=actor.lending_institution_id,
        email=data["email"],
        password=data["password"],
        full_name=data["full_name"],
        role=data["role"],
        phone_number=data.get("phone_number"),
        national_id_number=data.get("national_id_number"),
        actor_id=actor.id,
    )
    return jsonify(user_schema.dump(new_user)), 201

# Get all staff members for the caller's organization
@foundation_bp.get("/users")
@role_required("branch_manager")
def get_teammates():
    from foundations.models import User
    actor = get_current_user()
    users = User.query.filter(
        User.lending_institution_id == actor.lending_institution_id,
        User.role.in_(['branch_manager', 'loan_officer'])
    ).all()
    return jsonify(user_schema.dump(users, many=True)), 200


@foundation_bp.patch("/users/<int:user_id>/status")
@role_required("branch_manager")
def update_teammate_status(user_id):
    from foundations.models import User
    from extensions import db
    actor = get_current_user()
    
    user = db.session.get(User, user_id)
    if not user or user.lending_institution_id != actor.lending_institution_id:
        return jsonify({"message": "User not found"}), 404
        
    data = request.get_json() or {}
    new_status = data.get("status")
    
    if new_status not in ["active", "suspended"]:
        return jsonify({"message": "Invalid status"}), 400
        
    user.status = new_status
    db.session.commit()
    
    return jsonify(user_schema.dump(user)), 200

@foundation_bp.post("/users/<int:user_id>/edit-request")
@role_required("branch_manager")
def submit_teammate_edit_request(user_id):
    from foundations.models import User
    from extensions import db
    actor = get_current_user()
    
    user = db.session.get(User, user_id)
    if not user or user.lending_institution_id != actor.lending_institution_id:
        return jsonify({"message": "User not found"}), 404
        
    # In a real app, this would create an InstitutionChangeRequest or similar model.
    # For now, it simulates success as requested.
    return jsonify({
        "message": "SokoCredit Team will review the request and reach out to confirm."
    }), 200


institution_settings_schema = InstitutionSettingsSchema()
setting_request_create_schema = InstitutionSettingRequestCreateSchema()
setting_request_schema = InstitutionSettingRequestSchema()


@foundation_bp.get("/institution-settings")
@role_required("branch_manager")
def get_settings():
    actor = get_current_user()
    institution = get_institution_settings(actor.lending_institution_id)
    return jsonify(institution_settings_schema.dump(institution)), 200


@foundation_bp.get("/institution-setting-requests")
@role_required("branch_manager")
def list_settings_requests():
    actor = get_current_user()
    status = request.args.get("status")
    rows = list_setting_requests(actor.lending_institution_id, status=status)
    return jsonify(setting_request_schema.dump(rows, many=True)), 200


@foundation_bp.post("/institution-setting-requests")
@role_required("branch_manager")
def create_setting_request():
    data = setting_request_create_schema.load(request.get_json() or {})
    actor = get_current_user()
    req = request_setting_change(
        lending_institution_id=actor.lending_institution_id,
        requested_by_user_id=actor.id,
        field_changed=data["field_changed"],
        new_value=data["new_value"],
    )
    return jsonify(setting_request_schema.dump(req)), 201


@foundation_bp.post("/institution-setting-requests/<int:request_id>/approve")
@role_required("branch_manager")
def approve_setting_request(request_id):
    actor = get_current_user()
    req = approve_setting_change(request_id=request_id, approver_id=actor.id)
    if req.lending_institution_id != actor.lending_institution_id:
        return jsonify({"error": "This resource does not belong to your organization."}), 403
    return jsonify(setting_request_schema.dump(req)), 200