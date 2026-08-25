#Other modules (Underwriting) should only ever call functions from here
#never import origination.models directly
#file is allowed to depend on Foundation

from datetime import date
from typing import Optional

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

from foundations.auth import AuthError, get_user_intitution_id, verify_institution_access
from foundations.audit import log_action

def _verify_profile_institution_access(profile: CustomerProfile) -> None:

    institution_id  = get_user_intitution_id(profile.user_id)
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

    institution_id = get_user_intitution_id(user_id)
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