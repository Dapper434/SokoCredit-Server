from app import create_app
from extensions import db
from foundations.models import LendingInstitution, User
from origination.models import CustomerProfile
from underwriting.models import SavingsAccount, CreditScoreLog
from foundations.auth import hash_password
from datetime import datetime

app = create_app()
with app.app_context():
    db.drop_all()
    db.create_all()
    
    inst = LendingInstitution(
        registered_business_name="SokoCredit Default",
        registration_number="REG-12345",
        kra_pin="KRA-12345",
        head_office_address="Nairobi",
        status="active"
    )
    db.session.add(inst)
    db.session.flush()
    
    kevin = User(
        lending_institution_id=inst.id,
        email="kevin.ongaro@sokocredit.com",
        password_hash=hash_password("password123"),
        full_name="Kevin Ongaro",
        role="branch_manager",
        status="active"
    )
    db.session.add(kevin)
    
    cust_user = User(
        lending_institution_id=inst.id,
        email="customer@sokocredit.com",
        password_hash=hash_password("1234"),
        full_name="Jane Doe",
        role="customer",
        status="active"
    )
    db.session.add(cust_user)
    db.session.flush()
    
    cust_profile = CustomerProfile(
        user_id=cust_user.id,
        national_id_number="12345678",
        phone_number="0700000000",
        credit_tier="A",
        pin_hash=hash_password("1234")
    )
    db.session.add(cust_profile)
    db.session.flush()

    savings = SavingsAccount(
        customer_profile_id=cust_profile.id,
        total_savings_balance=1000,
        days_saved_count=15,
        is_savings_mature=True
    )
    db.session.add(savings)
    db.session.flush()
    
    score_log = CreditScoreLog(
        customer_profile_id=cust_profile.id,
        previous_tier=None,
        new_tier="A",
        score_components={"base_score": 100},
        calculated_at=datetime.utcnow()
    )
    db.session.add(score_log)

    db.session.commit()
    print("Database seeded successfully with Kevin Ongaro and a test customer.")
