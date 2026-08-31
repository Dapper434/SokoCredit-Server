#Other modules (Underwriting) should only ever call functions from here
#never import origination.models directly
#file is allowed to depend on Foundation

from datetime import date
from typing import Optional
from foundations import storage

from extensions import db
from origination.models import (
    CustomerProfile,
    MarketStall,
    CustomerDocument,
    LoyaltyPoints,
    Badge,
    CustomerBadge,
    CREDIT_TIERS,
)

from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action

def _verify_profile_institution_access(profile: CustomerProfile) -> None:

    institution_id  = get_user_institution_id(profile.user_id)
    if institution_id is None:
        raise AuthError("This customer profile has no resolvable institution", 403)

    verify_institution_access(institution_id)


def create_customer_profile(
    user_id: int,
    national_id_number: str,
    actor_id: int,
    date_of_birth: Optional[date] = None,
    gender: Optional[str] = None,
    business_type: Optional[str] = None,
    monthly_income_range: Optional[str] = None,
    residential_address: Optional[str] = None,
    next_of_kin_name: Optional[str] = None,
    next_of_kin_phone: Optional[str] = None,
    market_stall_id: Optional[int] = None,   
) -> CustomerProfile:
    #creates customer profile owned bu user_id(loan officer)

    institution_id = get_user_institution_id(user_id)
    if institution_id is None:
        raise AuthError("No such staff user, or user has no institution.", 400)

    verify_institution_access(institution_id)

    if CustomerProfile.query.filter_by(national_id_number=national_id_number).first():
        raise AuthError("A customer profile with this national ID already exists." ,409)

    if market_stall_id is not None and db.session.get(MarketStall, market_stall_id) is None:
        raise AuthError("No such market stall.", 400)

    profile = CustomerProfile(
        user_id=user_id,
        national_id_number=national_id_number,
        date_of_birth=date_of_birth,
        gender=gender,
        business_type=business_type,
        monthly_income_range=monthly_income_range,
        residential_address=residential_address,
        next_of_kin_name=next_of_kin_name,
        next_of_kin_phone=next_of_kin_phone,
        market_stall_id=market_stall_id,
    )

    db.session.add(profile)
    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="CustomerProfile",
        entity_id=profile.id,
        action="create",
        before=None,
        after={"national_id_number": profile.national_id_number, "user_id": user_id},
        lending_institution_id=institution_id,
    )
    return profile


def get_customer_profile(customer_profile_id: int) -> CustomerProfile:
    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such customer profile.", 404)
    _verify_profile_institution_access(profile)
    return profile


def add_document(
    customer_profile_id: int,
    document_type: str,
    file_bytes:bytes,
    content_type: str,
    original_filename: str,
    uploaded_by: int, 
) -> CustomerDocument:
    profile = get_customer_profile(customer_profile_id)
    institution_id = get_user_institution_id(profile.user_id)

    storage.validate_upload(content_type, len(file_bytes))
    path = storage.build_object_path("customer", profile.id, original_filename)
    storage.upload_file(path, file_bytes, content_type)

    doc = CustomerDocument(
        customer_profile_id=profile.id,
        document_type=document_type,
        storage_path=path,
        content_type=content_type,
        uploaded_by=uploaded_by, 
    )

    db.session.add(doc)
    db.session.commit()

    institution_id = get_user_institution_id(profile.user_id)
    log_action(
        actor_id=uploaded_by,
        entity_type="CustomerDocument",
        entity_id=doc.id,
        action="create",
        before=None,
        after={"document_type": document_type, "storage_path": path, "customer_profile_id": profile.id},
        lending_institution_id=institution_id,
    )
    return doc

def get_document_download_url(
    document_id:int
) -> str:
    doc = db.session.get(CustomerDocument, document_id)
    if doc is None:
        raise AuthError("No such document.", 404)
    profile = db.session.get(CustomerProfile, doc.customer_profile_id)
    _verify_profile_institution_access(profile)
    return storage.generate_signed_url(doc.storage_path)


def award_badge(
    customer_profile_id: int,
    badge_id: int,
    actor_id: int
) -> CustomerBadge:
    profile = get_customer_profile(customer_profile_id)

    if db.session.get(Badge, badge_id) is None:
        raise AuthError("No such badge.", 404)

    if CustomerBadge.query.filter_by(customer_profile_id=profile.id, badge_id=badge_id).first():
        raise AuthError("this customer already has that badge.", 409)

    award = CustomerBadge(customer_profile_id=profile.id, badge_id=badge_id)

    db.session.add(award)
    db.session.commit()

    institution_id = get_user_institution_id(profile.user_id)
    log_action (
        actor_id=actor_id,
        entity_type="CustomerBadge",
        entity_id=award.id,
        action="create",
        before=None,
        after={"customer_profile_id": profile.id, "badge_id": badge_id},
        lending_institution_id=institution_id,
    )
    return award

def set_credit_tier(
    customer_profile_id:int,
    tier:str,
    actor_id:Optional[int]=None     
) -> CustomerProfile:
    #called by underwriting after every credit score recalculation

    if tier not in CREDIT_TIERS:
        raise AuthError(f"Invalid credit tier '{tier}'. Must be one of {CREDIT_TIERS}. ", 400)

    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such cutomer profile.", 404)

    institution_id = get_user_institution_id(profile.user_id)
    before_tier = profile.credit_tier
    profile.credit_tier = tier
    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="CustomerProfile",
        entity_id=profile.id,
        action="update",
        before={"credit_tier": before_tier},
        after={"credit_tier": tier},
        lending_institution_id=institution_id,
    )
    return profile
