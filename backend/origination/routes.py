from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError
from extensions import db

from foundations.auth import AuthError, get_current_user
from origination.services import (
    create_customer_profile, get_customer_profile, update_customer_profile, add_document,
    award_badge, authenticate_customer, record_checkin, get_checkin_history,
    get_points_summary, initiate_savings_stk, get_savings_deposit,
    get_document_download_url,
)
from flask_jwt_extended import jwt_required, create_access_token
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

@origination_bp.get("/institutions")
def get_institutions():
    from foundations.models import LendingInstitution
    institutions = LendingInstitution.query.filter_by(status="active").all()
    result = []
    for inst in institutions:
        branches = [{"id": b.id, "name": b.name, "code": b.code} for b in inst.branches]
        result.append({
            "id": inst.id,
            "name": inst.registered_business_name,
            "code": inst.code,
            "domain": inst.domain,
            "branches": branches
        })
    return jsonify(result), 200


@origination_bp.post("/customers/login")
def login_customer():
    data = request.get_json() or {}
    phone_number = data.get("phone_number")
    pin = data.get("pin")
    lending_institution_id = data.get("lending_institution_id")
    if not phone_number or not pin or not lending_institution_id:
        return jsonify({"error": "phone_number, pin, and lending_institution_id are required"}), 400
    
    try:
        profile = authenticate_customer(phone_number, pin, lending_institution_id)
    except AuthError as e:
        return jsonify({"error": e.message}), e.status_code

    from foundations.auth import get_user_institution_id
    institution_id = get_user_institution_id(profile.user_id)

    # Create a JWT token for the customer
    token = create_access_token(
        identity=str(profile.user_id),
        additional_claims={
            "role": "customer", 
            "customer_profile_id": profile.id,
            "lending_institution_id": institution_id
        }
    )
    
    from foundations.models import User
    user = db.session.get(User, profile.user_id)
    full_name = user.full_name if user else "Customer"

    return jsonify({
        "access_token": token,
        "customer_profile_id": profile.id,
        "national_id_number": profile.national_id_number,
        "phone_number": profile.phone_number,
        "full_name": full_name,
        "role": "customer"
    }), 200

@origination_bp.post("/customers/register")
def register_customer_route():
    from origination.schemas import CustomerRegisterSchema
    from origination.services import register_customer
    data = CustomerRegisterSchema().load(request.get_json() or {})
    
    try:
        profile = register_customer(data)
    except AuthError as e:
        return jsonify({"error": e.message}), e.status_code

    return jsonify(profile_schema.dump(profile)), 201

@origination_bp.post("/customers")
@jwt_required()
def create_customer():
    data = CustomerProfileCreateSchema().load(request.get_json() or {})
    actor = get_current_user()
    profile = create_customer_profile(actor_id=actor.id, **data)
    return jsonify(profile_schema.dump(profile)), 201


@origination_bp.get("/customers")
@jwt_required()
def get_customers():
    from origination.models import CustomerProfile
    from foundations.models import User
    actor = get_current_user()
    
    profiles = db.session.query(CustomerProfile, User).join(
        User, CustomerProfile.user_id == User.id
    ).filter(
        CustomerProfile.lending_institution_id == actor.lending_institution_id
    ).all()
    
    result = []
    for profile, user in profiles:
        market_name = profile.market_stall.market_name if profile.market_stall else "General"
        stall_num = profile.market_stall.stall_number if profile.market_stall else "N/A"
        result.append({
            "id": profile.id,
            "fullName": user.full_name,
            "displayName": user.full_name.split()[0] if user.full_name else "Unknown",
            "initials": "".join([n[0] for n in (user.full_name or "U").split()][:2]).upper(),
            "market": market_name, 
            "stall": stall_num,
            "phone": profile.phone_number,
            "tier": profile.credit_tier or "C",
            "status": "paid", 
            "balance": 0,
            "inHouseScore": 70,
            "nationalId": profile.national_id_number,
            "gender": profile.gender,
            "dob": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
            "monthlyTurnover": profile.monthly_income_range,
            "nextOfKin": f"{profile.next_of_kin_name or ''} {profile.next_of_kin_phone or ''}".strip(),
            "nextOfKinEmail": profile.next_of_kin_email or "N/A",
            "address": profile.residential_address
        })
    return jsonify(result), 200


@origination_bp.get("/customers/<int:customer_id>")
@jwt_required()
def get_customer(customer_id):
    profile = get_customer_profile(customer_id)
    return jsonify(profile_schema.dump(profile)), 200

@origination_bp.patch("/customers/<int:customer_id>")
@jwt_required()
def patch_customer(customer_id):
    data = request.get_json() or {}
    actor = get_current_user()
    try:
        profile = update_customer_profile(customer_id, actor.id, **data)
        return jsonify(profile_schema.dump(profile)), 200
    except AuthError as e:
        return jsonify({"error": e.message}), e.status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@origination_bp.post("/customers/<int:customer_id>/documents")
@jwt_required()
def upload_document(customer_id):
    """KYC document.
    multipart/form-data `file` -> Supabase upload; JSON `file_url` -> metadata only.
    """
    actor = get_current_user()
    if "file" in request.files:
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
    else:
        data = DocumentUploadSchema().load(request.get_json() or {})
        doc = add_document(
            customer_profile_id=customer_id,
            document_type=data["document_type"],
            file_url=data["file_url"],
            uploaded_by=actor.id,
        )
    return jsonify({
        "id": doc.id, "document_type": doc.document_type,
        "file_url": doc.file_url, "storage_path": doc.storage_path,
    }), 201


@origination_bp.get("/customers/<int:customer_id>/documents/<int:document_id>/download")
@jwt_required()
def download_document(customer_id, document_id):
    url = get_document_download_url(document_id)
    return jsonify({"url": url}), 200

@origination_bp.post("/customers/<int:customer_id>/badges")
@jwt_required()
def add_badge(customer_id):
    data = BadgeAwardSchema().load(request.get_json() or {})
    actor = get_current_user()
    award = award_badge(customer_id, data["badge_id"], actor_id=actor.id)
    return jsonify({"id": award.id, "customer_profile_id": award.customer_profile_id, "badge_id": award.badge_id}), 201


# ── Savings Check-in Endpoints ─────────────────────────────────────────

@origination_bp.post("/customers/checkin")
@jwt_required()
def checkin_customer():
    """Record a daily check-in for the authenticated customer."""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    customer_profile_id = claims.get("customer_profile_id")
    if not customer_profile_id:
        return jsonify({"error": "Not a customer account."}), 403

    try:
        checkin = record_checkin(customer_profile_id)
    except AuthError as e:
        return jsonify({"error": e.message}), e.status_code

    return jsonify({
        "checkin_date": checkin.checkin_date.isoformat(),
        "message": "Check-in recorded!",
    }), 201


@origination_bp.get("/customers/checkins")
@jwt_required()
def get_checkins():
    """Return the authenticated customer's check-in history."""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    customer_profile_id = claims.get("customer_profile_id")
    if not customer_profile_id:
        return jsonify({"error": "Not a customer account."}), 403

    history = get_checkin_history(customer_profile_id)
    return jsonify(history), 200


@origination_bp.get("/customers/points")
@jwt_required()
def get_points():
    """Return the authenticated customer's SokoPoints balance and badge progress."""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    customer_profile_id = claims.get("customer_profile_id")
    if not customer_profile_id:
        return jsonify({"error": "Not a customer account."}), 403

    return jsonify(get_points_summary(customer_profile_id)), 200


@origination_bp.post("/customers/savings/stk")
@jwt_required()
def initiate_savings_stk_route():
    """Customer taps 'Save KES 200 (M-Pesa)' — fire the STK push."""
    from flask_jwt_extended import get_jwt
    from servicing.mpesa.config import MpesaConfigError

    claims = get_jwt()
    customer_profile_id = claims.get("customer_profile_id")
    if not customer_profile_id:
        return jsonify({"error": "Not a customer account."}), 403

    try:
        deposit = initiate_savings_stk(customer_profile_id)
    except MpesaConfigError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify({
        "checkout_request_id": deposit.checkout_request_id,
        "status": deposit.status,
        "amount": str(deposit.amount),
    }), 202


@origination_bp.get("/customers/savings/deposits/<checkout_request_id>")
@jwt_required()
def get_savings_deposit_route(checkout_request_id):
    """Frontend polls this after initiating a savings STK push."""
    from flask_jwt_extended import get_jwt

    deposit = get_savings_deposit(checkout_request_id)
    if deposit is None:
        return jsonify({"error": "Unknown deposit."}), 404

    claims = get_jwt()
    if claims.get("customer_profile_id") not in (deposit.customer_profile_id, None):
        if claims.get("role") == "customer":
            return jsonify({"error": "Not your deposit."}), 403

    return jsonify({
        "checkout_request_id": deposit.checkout_request_id,
        "status": deposit.status,
        "amount": str(deposit.amount),
        "gateway_reference": deposit.gateway_reference,
        "failure_reason": deposit.failure_reason,
    }), 200


@origination_bp.get("/savings/activity")
@jwt_required()
def savings_activity_route():
    """Staff view: per-customer savings activity for the caller's institution."""
    from origination.services import get_savings_activity
    actor = get_current_user()
    if actor is None or not actor.lending_institution_id:
        return jsonify({"error": "Staff account required."}), 403
    return jsonify(get_savings_activity(actor.lending_institution_id)), 200
