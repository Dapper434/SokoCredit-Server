from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError

from foundations.auth import AuthError, get_current_user
from origination.services import create_customer_profile, get_customer_profile, add_document,award_badge
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
    return jsonify({"error":err.message}, err.status_code)


@origination_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"error": "Validation failed", "details": err.messages}), 422


@origination_bp.post("/customers")
@jwt_required
def create_customer():
    data = CustomerProfileSchema().load(request.get_json() or {})
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
    data = DocumentUploadSchema().load(request.get_json() or {})
    actor = get_current_user()
    doc = add_document(
        customer_profile_id=customer_id,
        document_type=data["document_type"],
        file_url=data["file_url"],
        uploaded_by=actor.id,
    )
    return jsonify({"id": doc.id, "document_type": doc.document_type, "file_url": doc.file_url}), 201

@origination_bp.post("/customers/<int:customer_id>/badges")
@jwt_required()
def add_badge(customer_id):
    data = BadgeAwardSchema().load(request.get_json() or {})
    actor = get_current_user()
    award = award_badge(customer_id, data["badge_id"], actor_id=actor.id)
    return jsonify({"id": award.id, "customer_profile_id": award.customer_profile_id, "badge_id": award.badge_id}), 201