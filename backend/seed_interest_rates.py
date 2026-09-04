"""Seed each demo institution's default_interest_rate.

Stored as whole-number percentages, matching RegisterStep3.jsx's
"Default Interest Rate (%)" field (parseFloat of e.g. "15") and the
>= 1 normalization in servicing.services.normalize_interest_rate
(32.51 -> 0.3251).

Usage:  .venv/bin/python seed_interest_rates.py
"""
from decimal import Decimal

from app import create_app
from extensions import db
from foundations.models import LendingInstitution

RATES = {
    "FAULU": Decimal("32.51"),
    "KWFT": Decimal("24.00"),
    "RAFIKI": Decimal("22.00"),
    "SMEP": Decimal("18.00"),
    "CARITAS": Decimal("26.00"),
}

app = create_app()
with app.app_context():
    for code, rate in RATES.items():
        institution = LendingInstitution.query.filter_by(code=code).first()
        if institution is None:
            print(f"  SKIP {code}: no such institution")
            continue
        before = institution.default_interest_rate
        institution.default_interest_rate = rate
        print(f"  {code:<8} {str(before):>8} -> {rate}")
    db.session.commit()
    print("\nSeeded default_interest_rate for all demo institutions.")
