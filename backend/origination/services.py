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