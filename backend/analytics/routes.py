from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from foundations.auth import permission_required, get_user_institution_id
from analytics.schemas import (
    PortfolioSummarySchema,
    DashboardFeedSchema,
    CustomerDashboardFeedSchema
)
from analytics.services import (
    get_portfolio_summary,
    get_lender_dashboard_feed,
    get_customer_dashboard_feed
)

analytics_bp = Blueprint("analytics", __name__)

portfolio_summary_schema = PortfolioSummarySchema()
dashboard_feed_schema = DashboardFeedSchema()
customer_dashboard_feed_schema = CustomerDashboardFeedSchema()

def _current_user_id() -> int:
    return int(get_jwt_identity())

@analytics_bp.route("/lender/portfolio", methods=["GET"])
@jwt_required()
def portfolio_summary_route():
    # Typically requires a role like branch_manager or loan_officer
    claims = get_jwt()
    if claims.get("role") not in ["branch_manager", "loan_officer"]:
        return jsonify({"error": "Unauthorized"}), 403
        
    actor_id = _current_user_id()
    institution_id = get_user_institution_id(actor_id)
    
    summary = get_portfolio_summary(institution_id)
    return jsonify(portfolio_summary_schema.dump(summary)), 200

@analytics_bp.route("/lender/dashboard", methods=["GET"])
@jwt_required()
def lender_dashboard_route():
    claims = get_jwt()
    if claims.get("role") not in ["branch_manager", "loan_officer"]:
        return jsonify({"error": "Unauthorized"}), 403
        
    actor_id = _current_user_id()
    institution_id = get_user_institution_id(actor_id)
    
    feed = get_lender_dashboard_feed(institution_id)
    return jsonify(dashboard_feed_schema.dump(feed)), 200

@analytics_bp.route("/customer/dashboard", methods=["GET"])
@jwt_required()
def customer_dashboard_route():
    claims = get_jwt()
    if claims.get("role") != "customer":
        return jsonify({"error": "Unauthorized"}), 403
        
    customer_profile_id = claims.get("customer_profile_id")
    feed = get_customer_dashboard_feed(customer_profile_id)
    return jsonify(customer_dashboard_feed_schema.dump(feed)), 200
