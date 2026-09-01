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

notification_log_schema = NotificationLogSchema()
send_notification_schema = SendNotificationSchema()
promise_schema = PromiseToPaySchema()
log_promise_schema = LogPromiseToPaySchema()
aging_schema = AgingClassificationSchema()
 
 
def _current_user_id() -> int:
    return int(get_jwt_identity())
 
 
def _auth_error_response(exc: AuthError):
    return jsonify({"error": exc.message}), exc.status_code


@collections_bp.route("/notifications", methods=["POST"])
@jwt_required()
def send_notification_route():
    try:
        data = send_notification_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors":err.messages}), 400

    actor_id = _current_user_id()

    try:
        entry = send_notification(actor_id=actor_id, **data)
    except AuthError as exc:
        return _auth_error_response(exc)
    except NotificationDispatchError as exc:
        return jsonify({"error":str(exc)}), 502

    return jsonify(notification_log_schema.dump(entry)), 201