"""Seed Faith Mauti at Faulu with exactly KES 12,000 available credit.

Scenario (Tier B, 30-day unlock reached):
    tier B (2x)  x  savings 6,000  -  outstanding 0   = 12,000
    30 distinct savings days -> institution ceiling (500,000) applies, not the
    15,000 starter cap  ->  available = min(12,000, 500,000) = 12,000

New customers are unaffected — this only creates Faith.

Usage:  .venv/bin/python seed_faith_demo.py
"""
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, "/home/pipsy/Documents/SokoCredit/SokoCredit-Server/backend")

from app import create_app
from extensions import db
from foundations.models import User, LendingInstitution
from origination.models import CustomerProfile, SavingsCheckin
from origination.services import hash_pin
from underwriting.models import SavingsAccount, CreditScoreLog

PHONE = "0742706665"
PIN = "12345"
TIER = "B"
SAVINGS_DAYS = 30
SAVINGS_BALANCE = Decimal("6000")

app = create_app()
with app.app_context():
    faulu = LendingInstitution.query.filter_by(code="FAULU").first()
    assert faulu, "Faulu institution not seeded — run seed_multi_tenant.py first"

    user = User.query.filter_by(phone_number=PHONE).first()
    if not user:
        user = User(
            email="faith.mauti@customer.faulumfi.co.ke",
            full_name="Faith Mauti",
            role="customer",
            status="active",
            phone_number=PHONE,
            national_id_number="6578744",
            lending_institution_id=faulu.id,
            password_hash="dummy",  # customers authenticate by PIN, not password
        )
        db.session.add(user)
        db.session.flush()

    profile = CustomerProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        profile = CustomerProfile(
            user_id=user.id,
            lending_institution_id=faulu.id,
            national_id_number="6578744",
            phone_number=PHONE,
            pin_hash=hash_pin(PIN),
            credit_tier=TIER,
            residential_address="Toi Market, Ngong Road, Nairobi",
            next_of_kin_name="Sascha Jones",
            next_of_kin_phone="0700111222",
        )
        db.session.add(profile)
        db.session.flush()
    else:
        profile.pin_hash = hash_pin(PIN)
        profile.credit_tier = TIER

    # Savings: 30 distinct check-in dates + a matured account at KES 6,000.
    SavingsCheckin.query.filter_by(customer_profile_id=profile.id).delete()
    start = date.today() - timedelta(days=SAVINGS_DAYS - 1)
    for i in range(SAVINGS_DAYS):
        db.session.add(SavingsCheckin(
            customer_profile_id=profile.id,
            checkin_date=start + timedelta(days=i),
        ))

    acct = SavingsAccount.query.filter_by(customer_profile_id=profile.id).first()
    if not acct:
        acct = SavingsAccount(customer_profile_id=profile.id)
        db.session.add(acct)
    acct.total_savings_balance = SAVINGS_BALANCE
    acct.days_saved_count = SAVINGS_DAYS
    acct.is_savings_mature = True

    # get_available_credit reads the tier from the latest CreditScoreLog.
    CreditScoreLog.query.filter_by(customer_profile_id=profile.id).delete()
    db.session.add(CreditScoreLog(
        customer_profile_id=profile.id,
        previous_tier=None,
        new_tier=TIER,
        score_components={"seeded": "demo — Tier B for the KES 12,000 scenario"},
    ))

    db.session.commit()

    from underwriting.services import get_available_credit, TIER_MULTIPLIERS
    avail = get_available_credit(profile.id)
    print(f"Faith Mauti seeded  (profile_id={profile.id}, user_id={user.id})")
    print(f"  login: phone {PHONE} / PIN {PIN} / Faulu (institution {faulu.id})")
    print(f"  tier {TIER} (x{TIER_MULTIPLIERS[TIER]})  savings {acct.total_savings_balance}  "
          f"days {acct.days_saved_count}  mature {acct.is_savings_mature}")
    print(f"  AVAILABLE CREDIT = KES {avail}")
    assert avail == Decimal("12000"), f"expected 12000, got {avail}"
    print("  -> exactly KES 12,000 as intended.")
