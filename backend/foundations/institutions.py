#handles institutions onboarding and compliance workflow

from typing import Optional

import re
import uuid
from sqlalchemy.exc import IntegrityError
from extensions import db
from foundations.models import LendingInstitution, InstitutionDocument, InstitutionMarket, User
from foundations.auth import AuthError, register_user
from foundations.audit import log_action
from foundations import storage

MAX_MARKETS_PER_INSTITUTION = 6

def register_institution(
    registered_business_name: str,
    registration_number: str,
    kra_pin: str,
    head_office_address:str,
    admin_email:str,
    admin_password:str,
    admin_full_name: str,
    admin_national_id_number: Optional[str] = None,
    operating_license_type: Optional[str] = None,
    cbk_license_number: Optional[str] = None,
    county_business_permit_number: Optional[str] = None,
    odpc_registration_number: Optional[str] = None,
    estimated_staff_count: Optional[int] = None,
    head_office_lat: Optional[float] = None,
    head_office_lng: Optional[float] = None,
    collection_paybill_number: Optional[str] = None,
    airtel_paybill_number: Optional[str] = None,
    default_interest_rate: Optional[float] = None,
    default_penalty_rate: Optional[float] = None,
) -> tuple[LendingInstitution, User]:
    #Onboards an brand new lending institution plus its founding admin
    #institutions are auto approved for now 

    if LendingInstitution.query.filter_by(registration_number=registration_number).first():
        raise AuthError("A lending institution with this registration number already exists.", 409)

    if LendingInstitution.query.filter_by(kra_pin=kra_pin).first():
        raise AuthError("An institution with this KRA PIN already exists.", 409)

    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', registered_business_name).strip()
    words = clean_name.split()
    base_code = "".join([w[0] for w in words]).upper() if len(words) > 1 else clean_name[:3].upper()
    unique_suffix = str(uuid.uuid4())[:4].upper()
    code = f"{base_code}-{unique_suffix}"
    domain = f"{clean_name.replace(' ', '').lower()}-{unique_suffix.lower()}.sokocredit.com"

    institution = LendingInstitution(
        registered_business_name=registered_business_name,
        code=code,
        domain=domain,
        registration_number=registration_number,
        kra_pin=kra_pin,
        operating_license_type=operating_license_type,
        cbk_license_number=cbk_license_number,
        county_business_permit_number=county_business_permit_number,
        odpc_registration_number=odpc_registration_number,
        estimated_staff_count=estimated_staff_count,
        head_office_address=head_office_address,
        head_office_lat=head_office_lat,
        head_office_lng=head_office_lng,
        collection_paybill_number=collection_paybill_number,
        airtel_paybill_number=airtel_paybill_number,
        default_interest_rate=default_interest_rate,
        default_penalty_rate=default_penalty_rate,
        status="pending_review",
    )
    try:
        db.session.add(institution)
        db.session.flush() #assign institution.id without commiting

        admin = register_user(
            lending_institution_id=institution.id,
            email=admin_email,
            password=admin_password,
            full_name=admin_full_name,
            role="branch_manager",
            national_id_number=admin_national_id_number,
            is_founding_admin=True,
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        error_msg = str(e).lower()
        if "unique" in error_msg and "cbk_license_number" in error_msg:
            raise AuthError("An institution with this CBK license number already exists.", 409)
        if "unique" in error_msg and "email" in error_msg:
            raise AuthError("A user with this email address is already registered.", 409)
        raise AuthError("Registration failed: an account with these details already exists or missing required fields.", 409)

    log_action(
        actor_id=admin.id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="create",
        before=None,
        after={"registration_number": registration_number, "status":"pending_review"},
        lending_institution_id=institution.id,
    )

    #auto approve for now
    approve_institution(institution.id,actor_id=None)

    db.session.refresh(institution)
    db.session.refresh(admin)
    return institution, admin

def attach_document(
    lending_institution_id: int,
    document_type: str,
    uploaded_by: int,
    file_url: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    content_type: Optional[str] = None,
    original_filename: Optional[str] = None,
) -> InstitutionDocument:
    """Record a compliance document.

    Two strategies (merge of Dev + teammate work):
      * file_url         — client uploaded elsewhere, just pass the URL (Dev)
      * file_bytes + content_type + original_filename — server-side Supabase
        upload via foundations.storage (teammate)
    """
    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)

    storage_path = None
    if file_bytes is not None:
        storage.validate_upload(content_type, len(file_bytes))
        storage_path = storage.build_object_path(
            "institution", lending_institution_id, original_filename or "file"
        )
        storage.upload_file(storage_path, file_bytes, content_type)
    elif not file_url:
        raise AuthError("Provide either file_url or an uploaded file.", 400)

    doc = InstitutionDocument(
        lending_institution_id=lending_institution_id,
        document_type=document_type,
        file_url=file_url,
        storage_path=storage_path,
        content_type=content_type,
        uploaded_by=uploaded_by,
    )
    db.session.add(doc)
    db.session.commit()

    log_action(
        actor_id=uploaded_by,
        entity_type="InstitutionDocument",
        entity_id=doc.id,
        action="create",
        before=None,
        after={"document_type": document_type, "file_url": file_url, "storage_path": storage_path},
        lending_institution_id=lending_institution_id,
    )
    return doc


def get_document_download_url(document_id: int, requester_institution_id: int) -> str:
    """Signed Supabase URL for an institution document. Institution-scoped."""
    doc = db.session.get(InstitutionDocument, document_id)
    if doc is None:
        raise AuthError("No such document.", 404)
    if doc.lending_institution_id != requester_institution_id:
        raise AuthError("This document does not belong to your institution.", 403)
    if not doc.storage_path:
        raise AuthError("This document has no Supabase storage object.", 400)
    return storage.generate_signed_url(doc.storage_path)


def add_market(
    lending_institution_id:str,
    market_name:str,
    actor_id:int
) -> InstitutionMarket:
    #adds institution's operaing markets
    existing_count = InstitutionMarket.query.filter_by(
        lending_institution_id=lending_institution_id
    ).count()
    if existing_count >= MAX_MARKETS_PER_INSTITUTION:
        raise AuthError(f"An institution may list only {MAX_MARKETS_PER_INSTITUTION} markets.", 400)

    market = InstitutionMarket(
        lending_institution_id=lending_institution_id,
        market_name=market_name,
    )
    db.session.add(market)
    db.session.commit()

    log_action(
        actor_id = actor_id,
        entity_type="InstitutionMarket",
        entity_id=market.id,
        action="create",
        before=None,
        after={"market_name":market_name},
        lending_institution_id=lending_institution_id
    )
    return market

def submit_for_compliance_review(
     lending_institution_id:int,
     actor_id:int,
    ) -> LendingInstitution:

    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)

    log_action(
        actor_id=actor_id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="update",
        before={"status": institution.status},
        after={"status": institution.status, "submitted_for_review":True},
        lending_institution_id=institution.id,
    )
    return institution


def approve_institution(
    lending_institution_id:int,
    actor_id:Optional[int]=None,
) -> LendingInstitution:
    #flips institution from pending to active

    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)

    before_status = institution.status
    institution.status = "active"
    
    pending_admins = User.query.filter_by(
        lending_institution_id = lending_institution_id, status="pending"      
    ).all()

    for admin in pending_admins:
        admin.status = "active"

    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="update",
        before={"status": before_status},
        after={"status": "active"},
        lending_institution_id=institution.id,
    )
    return institution

"""
 To remove approve institution auto call:
  -> Remove auto call from inside register institution
  -> Expose this function behind a route restricted to a platform admin
     in foundation.routes.py that passes the reviewer's real actor_id
"""

from foundations.models import InstitutionSettingRequest, SETTLEMENT_FIELDS


def get_institution_settings(lending_institution_id: int) -> LendingInstitution:
    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)
    return institution


def request_setting_change(
    lending_institution_id: int,
    requested_by_user_id: int,
    field_changed: str,
    new_value: str,
) -> InstitutionSettingRequest:
    if field_changed not in SETTLEMENT_FIELDS:
        raise AuthError(
            f"Field '{field_changed}' is not a Four-Eyes settlement field. "
            f"Allowed: {SETTLEMENT_FIELDS}.",
            400,
        )

    institution = get_institution_settings(lending_institution_id)
    old_value = getattr(institution, field_changed)
    old_str = None if old_value is None else str(old_value)

    req = InstitutionSettingRequest(
        lending_institution_id=lending_institution_id,
        requested_by_user_id=requested_by_user_id,
        field_changed=field_changed,
        old_value=old_str,
        new_value=str(new_value),
        status="pending",
    )
    db.session.add(req)
    db.session.commit()

    log_action(
        actor_id=requested_by_user_id,
        entity_type="InstitutionSettingRequest",
        entity_id=req.id,
        action="create",
        before={"field": field_changed, "value": old_str},
        after={"field": field_changed, "value": str(new_value)},
        lending_institution_id=lending_institution_id,
    )
    return req


def approve_setting_change(
    request_id: int,
    approver_id: int,
) -> InstitutionSettingRequest:
    req = db.session.get(InstitutionSettingRequest, request_id)
    if req is None:
        raise AuthError("No such setting request.", 404)
    if req.status != "pending":
        raise AuthError("Setting request is not pending.", 400)
    if approver_id == req.requested_by_user_id:
        raise AuthError("Four-Eyes: a second authorized admin must approve this change.", 403)
    approver = db.session.get(User, approver_id)
    if approver is None or approver.lending_institution_id != req.lending_institution_id:
        raise AuthError("This resource does not belong to your organization.", 403)

    institution = get_institution_settings(req.lending_institution_id)
    field = req.field_changed
    before = {field: req.old_value}

    raw = req.new_value
    if field in ("default_interest_rate", "default_penalty_rate"):
        setattr(institution, field, raw)
    else:
        setattr(institution, field, raw)

    req.approved_by_user_id = approver_id
    req.status = "approved"
    db.session.commit()

    log_action(
        actor_id=approver_id,
        entity_type="InstitutionSettingRequest",
        entity_id=req.id,
        action="update",
        before=before,
        after={field: raw, "status": "approved"},
        lending_institution_id=req.lending_institution_id,
    )
    return req


def list_setting_requests(lending_institution_id: int, status: Optional[str] = None):
    q = InstitutionSettingRequest.query.filter_by(lending_institution_id=lending_institution_id)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(InstitutionSettingRequest.created_at.desc()).all()


def get_default_institution_id() -> Optional[int]:
    # Returns the first available lending institution
    # Allows other modules to pick an institution without importing LendingInstitution model
    inst = LendingInstitution.query.first()
    return inst.id if inst else None

