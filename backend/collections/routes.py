from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
 
from foundations.auth import AuthError
 
from collections.schemas import (
    NotificationLogSchema,
    SendNotificationSchema,
    PromiseToPaySchema,
    LogPromiseToPaySchema,
    AgingClassificationSchema,
)
from collections.services import (
    send_notification,
    classify_aging_bucket,
    is_high_risk,
    dispatch_receipt,
    log_promise_to_pay,
    mark_promise_kept,
    mark_promise_broken,
    list_promises_for_loan,
)
from collections.notifications import NotificationDispatchError

collections_bp = Blueprint("collections_communications", __name__, url_prefix="/api/collections")
