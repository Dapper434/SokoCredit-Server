from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError

from foundations.auth import AuthError, get_current_user
from origination.services import create_customer_profile, get_customer_profile, add_document,award_badge, get_document_download_url
from origination.schemas import (
    CustomerProfileCreateSchema,
    DocumentUploadSchema,
    BadgeAwardSchema,
    CustomerProfileSchema,
)

origination_bp = Blueprint("origination", __name__)

profile_schema = CustomerProfileSchema()

@origination_bp.errorhandler(AuthError)
def handle_auth_error(err:AuthError):
    response = jsonify({"error": err.message})
    response.status_code = err.status_code
    return response


@origination_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    response = jsonify({"error": "Validation failed", "details": err.messages})
    response.status_code = 422
    return response


@origination_bp.post("/customers")
@jwt_required()
def create_customer():
    data = CustomerProfileCreateSchema().load(request.get_json() or {})
    actor = get_current_user()
    profile = create_customer_profile(actor_id=actor.id, **data)
    return jsonify(profile_schema.dump(profile)), 201


@origination_bp.get("/customers/<int:customer_id>")
@jwt_required()
def get_customer(customer_id):
    profile = get_customer_profile(customer_id)
    return jsonify(profile_schema.dump(profile)), 200

@origination_bp.post("/customers/<int:customer_id>/documents")
@jwt_required()
def upload_document(customer_id):
    actor = get_current_user()
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400
    file = request.files["file"]
    document_type = request.form.get("document_type")
    if not document_type:
        return jsonify({"error": "document_type is required."}), 400

    doc = add_document(
        customer_profile_id=customer_id,
        document_type=document_type,
        file_bytes=file.read(),
        content_type=file.content_type,
        original_filename=file.filename,
        uploaded_by=actor.id,
    )
    return jsonify({"id": doc.id, "document_type": doc.document_type}), 201

origination_bp.get("/customers/<int:customer_id>/documents/<int:document_id>/download")
@jwt_required()
def download_document(customer_id,document_id):
    url = get_document_download_url(document_id)
    return jsonify({"url": url}), 200

@origination_bp.post("/customers/<int:customer_id>/badges")
@jwt_required()
def add_badge(customer_id):
    data = BadgeAwardSchema().load(request.get_json() or {})
    actor = get_current_user()
    award = award_badge(customer_id, data["badge_id"], actor_id=actor.id)
    return jsonify({"id": award.id, "customer_profile_id": award.customer_profile_id, "badge_id": award.badge_id}), 201
