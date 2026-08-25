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