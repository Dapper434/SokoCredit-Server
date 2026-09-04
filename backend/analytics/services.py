from foundations.auth import AuthError
from sqlalchemy import func
from extensions import db
from underwriting.models import Loan
from servicing.models import Transaction, RepaymentSchedule

# All functions here MUST be strictly read-only.
# NO db.session.commit() or db.session.add() is permitted.

def get_portfolio_summary(institution_id: int) -> dict:
    # Stub: Return aggregated metrics for the portfolio
    # Real implementation would query the Loan, Transaction, RepaymentSchedule tables
    return {
        "total_active_loans": 0,
        "gross_loan_portfolio": 0.0,
        "portfolio_at_risk_30": 0.0,
        "collection_rate": 0.0
    }

def calculate_collection_rate(institution_id: int, timeframe: str = "30d") -> float:
    # Stub: Calculate collection rate (amount collected / amount due) over a timeframe
    return 0.0

def calculate_par(institution_id: int, days_past_due: int = 30) -> float:
    # Stub: Calculate Portfolio At Risk (PAR)
    # The total principal outstanding of all loans that have at least one installment past due by X days.
    return 0.0

def calculate_glp(institution_id: int) -> float:
    # Stub: Calculate Gross Loan Portfolio (GLP)
    # The total principal outstanding across all active loans.
    return 0.0

def get_lender_dashboard_feed(institution_id: int) -> dict:
    # Stub: Return data structures optimized for frontend charting libraries
    return {
        "disbursements_over_time": [
            {"label": "Jan", "value": 0.0},
            {"label": "Feb", "value": 0.0}
        ],
        "collections_over_time": [
            {"label": "Jan", "value": 0.0},
            {"label": "Feb", "value": 0.0}
        ],
        "portfolio_status_distribution": [
            {"label": "Active", "value": 0.0},
            {"label": "Defaulted", "value": 0.0},
            {"label": "Completed", "value": 0.0}
        ]
    }

def get_customer_dashboard_feed(customer_profile_id: int) -> dict:
    # Stub: Return customer-specific analytics
    return {
        "total_borrowed": 0.0,
        "total_repaid": 0.0,
        "current_outstanding": 0.0,
        "loan_history_summary": [
             {"label": "Loan 1", "value": 0.0}
        ]
    }
