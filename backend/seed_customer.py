import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from extensions import db
from foundations.models import User, LendingInstitution
from origination.models import CustomerProfile
from origination.services import hash_pin
from underwriting.models import Loan
from servicing.models import RepaymentSchedule
from datetime import date, timedelta

app = create_app()

with app.app_context():
    # Find or create institution
    inst = LendingInstitution.query.first()
    if not inst:
        inst = LendingInstitution(
            registered_business_name="Test Inst",
            registration_number="REG123",
            kra_pin="A123456789Z",
            head_office_address="Nairobi",
            status="active"
        )
        db.session.add(inst)
        db.session.commit()

    # Find or create a user for the customer
    user = User.query.filter_by(email="customer@example.com").first()
    if not user:
        user = User(
            email="customer@example.com",
            full_name="Test Customer",
            role="loan_officer", # dummy role to pass constraint
            status="active",
            lending_institution_id=inst.id,
            password_hash="dummy"
        )
        db.session.add(user)
        db.session.commit()

    # Find or create customer profile
    profile = CustomerProfile.query.filter_by(phone_number="0712345678").first()
    if not profile:
        profile = CustomerProfile(
            user_id=user.id,
            national_id_number="12345678",
            phone_number="0712345678",
            pin_hash=hash_pin("12345")
        )
        db.session.add(profile)
        db.session.commit()
    else:
        profile.pin_hash = hash_pin("12345")
        db.session.commit()

    # Create dummy loan and schedule
    loan = Loan.query.filter_by(customer_profile_id=profile.id).first()
    if not loan:
        loan = Loan(
            lending_institution_id=inst.id,
            customer_profile_id=profile.id,
            principal=10000,
            interest_rate=10,
            term_days=30,
            repayment_frequency="weekly",
            status="active",
            disbursed_at=db.func.now()
        )
        db.session.add(loan)
        db.session.commit()
        
        # Schedule
        sched = RepaymentSchedule(
            loan_id=loan.id,
            installment_number=1,
            due_date=date.today() + timedelta(days=15),
            principal_due=5000,
            interest_due=500,
            total_due=5500,
            status="pending"
        )
        sched2 = RepaymentSchedule(
            loan_id=loan.id,
            installment_number=2,
            due_date=date.today() + timedelta(days=30),
            principal_due=5000,
            interest_due=500,
            total_due=5500,
            status="pending"
        )
        db.session.add_all([sched, sched2])
        db.session.commit()

    print(f"Customer Profile ID: {profile.id}")
    print("Seeded customer with phone 0712345678 and PIN 12345")
