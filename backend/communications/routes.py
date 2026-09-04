from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
 
from foundations.auth import AuthError, permission_required
 
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
    get_notification_summary,
    get_broken_promise_counts,
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


@collections_bp.route("/loans/<int:loan_id>/receipt", methods=["POST"])
@jwt_required()
def dispatch_receipt_route(loan_id):
    actor_id = _current_user_id
    try:
        entry = dispatch_receipt(loan_id=loan_id, actor_id=actor_id)
    except AuthError as exc:
        return _auth_error_response(exc)
    except NotificationDispatchError as exc:
        return jsonify({"error": str(exc)}), 502
 
    return jsonify(notification_log_schema.dump(entry)), 201

@collections_bp.route("/aging-bucket", methods=["GET"])
@jwt_required()
def get_aging_bucket_route():
    days_overdue = request.args.get("days_overdue", type=int)
    broken_promise_count = request.args.get("broken_promise_count", default=0, type=int)
    if days_overdue is None:
        return jsonify({"error": "days_overdue query parameter is required."}), 400
 
    bucket = classify_aging_bucket(days_overdue)
    payload = {
        "days_overdue": days_overdue,
        "aging_bucket": bucket,
        "is_high_risk": is_high_risk(bucket, broken_promise_count),
    }
    return jsonify(aging_schema.dump(payload)), 200


@collections_bp.route("/loans/<int:loan_id/promises",methods=["POST"])
@jwt_required()
def log_promise_route(loan_id):
    try:
        data=log_promise_schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"errors":err.messages}),400

    actor_id = _current_user_id()

    try:
        promise = log_promise_to_pay(
            loan_id=loan_id, promised_date=data["promised_date"], actor_id=actor_id
        )
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(promise_schema.dump(promise)), 201

@collections_bp.route("/loans/<int:loan_id>/promises", methods=["GET"])
@jwt_required()
def list_promises_route(loan_id):
    try:
        promises = list_promises_for_loan(loan_id)
    except AuthError as exc:
        return _auth_error_response(exc)
 
    return jsonify(promise_schema.dump(promises, many=True)), 200

@collections_bp.route("/promises/<int:promise_id>/kept", methods=["POST"])
@jwt_required()
def mark_promise_kept_route(promise_id):
    actor_id = _current_user_id()
    try:
        promise = mark_promise_kept(promise_id, actor_id)
    except AuthError as exc:
        return _auth_error_response(exc)
 
    return jsonify(promise_schema.dump(promise)), 200

@collections_bp.route("/promises/<int:promise_id>/broken", methods=["POST"])
@jwt_required()
def mark_promise_broken_route(promise_id):
    actor_id = _current_user_id()
    try:
        promise = mark_promise_broken(promise_id, actor_id)
    except AuthError as exc:
        return _auth_error_response(exc)
 
    return jsonify(promise_schema.dump(promise)), 200

@collections_bp.route("/notifications/summary", methods=["GET"])
@permission_required("reports:view")
def notification_summary_route():
    """
    For Analytics/reporting. Only counts loan-linked notifications
    """
    try:
        summary = get_notification_summary()
    except AuthError as exc:
        return _auth_error_response(exc)

    return jsonify(summary), 200

@collections_bp.route("/promises/broken-counts", methods=["GET"])
@permission_required("reports:view")
def broken_promise_counts_route():
    actor_id = _current_user_id()
    try:
        counts = get_broken_promise_counts(actor_id)
    except AuthError as exc:
        return _auth_error_response(exc)
    
    return jsonify(counts), 200