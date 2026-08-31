from typing import Optional

from extensions import db
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
from origination.services import get_customer_profile
from underwriting.services import get_loan

from collections.models import NotificationLog, PromiseToPay, CHANNELS, MESSAGE_TYPES, utcnow
from collections.notifications import dispatch, NotificationDispatchError

def _verify_staff_institution_access(user_id:int) -> None:
    #institution check, makes sure staff has access to their own institution
    institution_id = get_user_institution_id(user_id)
    if not institution_id:
        raise AuthError("No such staff user, ot user has no institution.", 400)
    verify_institution_access(user_id, institution_id)