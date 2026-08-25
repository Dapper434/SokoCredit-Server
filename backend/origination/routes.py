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

