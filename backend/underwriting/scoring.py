from decimal import Decimal
from typing import Any

from underwriting.models import CREDIT_TIERS

ON_TIME_RATE_BANDS = (
    (Decimal("0.95"), 40),
    (Decimal("0.80"), 25),
    (Decimal("0.60"), 10),
)

COMPLETED_CYCLE_BANDS = (
    (3, 30),
    (1, 15),
)

SAVINGS_BALANCE_THRESHOLD = Decimal("5000")

RESCHEDULE_POINTS = {
    0: 10,
    1: 0,
}

RESCHEDULE_POINTS_TWO_OR_MORE = -10


TIER_A_THRESHOLD = 70
TIER_B_THRESHOLD = 40

def _on_time_rate_points(
    on_time_rate: Decimal
)-> int:
    for threshold, points in ON_TIME_RATE_BANDS:
        if on_time_rate >= threshold:
            return points
    return 0

# function to calculate completed cycle points
def _completed_cycle_points(
    completed_cycles: int
)-> int:
    for threshold, points in COMPLETED_CYCLE_BANDS:
        if completed_cycles >= threshold:
            return points
    return 0

# function to calculate savings points
def _savings_points(
    is_savings_mature: bool,
    savings_balance: Decimal
) -> int:
    if not is_savings_mature:
        return 0
    return 20 if savings_balance >= SAVINGS_BALANCE_THRESHOLD else 10

# function to calculate reschedule points
def _reschedule_points(
    reschedule_count: int  
) -> int:
    if reschedule_count >= 2:
        return RESCHEDULE_POINTS_TWO_OR_MORE
    return RESCHEDULE_POINTS.get(reschedule_count, 0)

def compute_credit_tier(
    on_time_rate: Decimal,
    completed_loan_cycles: int,
    has_defaulted_loan: bool,
    reschedule_count: int,
    is_savings_mature: bool,
    savings_balance: Decimal
) -> tuple[str, dict[str, Any]]:
    #Pure function - no DB access or cross module calls
    #takes inputs queried from Servicing module & savings_account
    #returns JSON-serializable breakdown stored in CreditScoreLog
    #tier is always explainable
    #any defaults are automatically moved to credit tier C

    if has_defaulted_loan:
        return "C", {
           "override": "defaulted_loan",
            "score": 0,
            "on_time_rate_points": 0,
            "completed_cycle_points": 0,
            "savings_points": 0,
            "reschedule_points": 0, 
        }

    on_time_pts = _on_time_rate_points(on_time_rate)
    cycle_pts = _completed_cycle_points(completed_loan_cycles)
    savings_pts = _savings_points(is_savings_mature, savings_balance)
    reschedule_pts = _reschedule_points(reschedule_count)

    score = on_time_pts + cycle_pts + savings_pts + reschedule_pts

    if score >= TIER_A_THRESHOLD:
        tier = "A"
    elif score >= TIER_B_THRESHOLD:
        tier = "B"
    else:
        tier = "C"

    assert tier in CREDIT_TIERS 

    components = {
        "score": score,
        "on_time_rate_points": on_time_pts,
        "completed_cycle_points": cycle_pts,
        "savings_points": savings_pts,
        "reschedule_points": reschedule_pts,
        "inputs": {
            "on_time_rate": str(on_time_rate),
            "completed_loan_cycles": completed_loan_cycles,
            "reschedule_count": reschedule_count,
            "is_savings_mature": is_savings_mature,
            "savings_balance": str(savings_balance),
        },
    }

    return tier, components

    
