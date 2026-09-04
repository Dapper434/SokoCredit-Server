import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from extensions import db
from foundations.models import User, LendingInstitution
from foundations.auth import hash_password

app = create_app()

with app.app_context():
    # Ensure an active institution exists
    inst = LendingInstitution.query.first()
    if not inst:
        inst = LendingInstitution(
            registered_business_name="Jua Microfinance Ltd",
            kra_pin="P0000000000J",
            head_office_address="Nairobi",
            status="active"
        )
        db.session.add(inst)
        db.session.commit()
    else:
        # Make sure it's active
        inst.status = "active"
        db.session.commit()

    institution_id = inst.id

    # Seed Kevin Ongaro (Branch Manager)
    kevin_email = "kevin.ongaro@branchm.com"
    kevin = User.query.filter_by(email=kevin_email).first()
    if not kevin:
        kevin = User(
            lending_institution_id=institution_id,
            email=kevin_email,
            password_hash=hash_password("Kevin123!"),
            full_name="Kevin Ongaro",
            role="branch_manager",
            status="active"
        )
        db.session.add(kevin)
        print(f"Created user: {kevin_email}")
    else:
        print(f"User {kevin_email} already exists")

    # Seed Milley Cyrus (Loan Officer)
    milley_email = "milley.cyrus@loanofficer.com"
    milley = User.query.filter_by(email=milley_email).first()
    if not milley:
        milley = User(
            lending_institution_id=institution_id,
            email=milley_email,
            password_hash=hash_password("Milley123!"),
            full_name="Milley Cyrus",
            role="loan_officer",
            status="active"
        )
        db.session.add(milley)
        print(f"Created user: {milley_email}")
    else:
        print(f"User {milley_email} already exists")

    db.session.commit()
    print("Demo users seeded successfully.")
