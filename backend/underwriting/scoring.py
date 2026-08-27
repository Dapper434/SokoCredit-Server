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

def _completed_cycle_points(
    completed_cycles: int
)-> int:
    for threshold, points in COMPLETED_CYCLE_BANDS:
        if completed_cycles >= threshold:
            return points
    return 0

def savings_points(
    is_savings_mature: bool,
    savings_balance: Decimal
) -> int:
    if not is_savings_mature:
        return 0
    return 20 if savings_balance >= SAVINGS_BALANCE_THRESHOLD else 10

