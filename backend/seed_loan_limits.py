"""Add and seed LendingInstitution.max_loan_limit.

Every institution MUST have a value: get_institution_max_loan_limit() raises
rather than falling back to a global default, so an unseeded institution fails
loudly instead of quietly lending on the wrong terms.

NOTE: only Faulu's 500,000 corresponds to a real published unsecured
micro-loan maximum. The other four are placeholder demo defaults and should
be replaced with each institution's real figure before any live use.

Usage:  .venv/bin/python seed_loan_limits.py
"""
from decimal import Decimal

from sqlalchemy import inspect as sa_inspect, text

from app import create_app
from extensions import db
from foundations.models import LendingInstitution

LIMITS = {
    "FAULU": Decimal("500000"),    # real published unsecured micro-loan max
    "KWFT": Decimal("400000"),     # placeholder
    "RAFIKI": Decimal("350000"),   # placeholder
    "SMEP": Decimal("300000"),     # placeholder
    "CARITAS": Decimal("350000"),  # placeholder
}

app = create_app()
with app.app_context():
    columns = {c["name"] for c in sa_inspect(db.engine).get_columns("lending_institutions")}
    if "max_loan_limit" not in columns:
        db.session.execute(text(
            "ALTER TABLE lending_institutions ADD COLUMN max_loan_limit NUMERIC(14,2)"))
        db.session.commit()
        print("Added column lending_institutions.max_loan_limit")

    for code, limit in LIMITS.items():
        institution = LendingInstitution.query.filter_by(code=code).first()
        if institution is None:
            print(f"  SKIP {code}: no such institution")
            continue
        before = institution.max_loan_limit
        institution.max_loan_limit = limit
        print(f"  {code:<8} {str(before):>8} -> {limit:,}")
    db.session.commit()

    missing = LendingInstitution.query.filter(
        LendingInstitution.max_loan_limit.is_(None)).all()
    if missing:
        print("\nWARNING: still unseeded ->", [i.code for i in missing])
    else:
        print("\nAll institutions have a max_loan_limit. None left NULL.")
