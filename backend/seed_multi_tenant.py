import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from extensions import db
from foundations.models import User, LendingInstitution, Branch
from foundations.auth import hash_password

yaml_data = {
    "institutions": [
        {
            "name": "Kenya Women Microfinance Bank",
            "code": "KWFT",
            "domain": "kwft.co.ke",
            "reg_number": "KWFT-001",
            "branches": [
                {
                    "code": "KWFT-HQ",
                    "name": "Nairobi HQ",
                    "staff": [
                        {"role": "BRANCH_MANAGER", "first": "jane", "last": "wairimu"},
                        {"role": "LOAN_OFFICER", "first": "peter", "last": "kamau"}
                    ]
                }
            ]
        },
        {
            "name": "Faulu Microfinance Bank",
            "code": "FAULU",
            "domain": "faulumfi.co.ke",
            "reg_number": "FAULU-002",
            "branches": [
                {
                    "code": "FAULU-NRB",
                    "name": "Nairobi Branch",
                    "staff": [
                        {"role": "BRANCH_MANAGER", "first": "david", "last": "mutiso"},
                        {"role": "LOAN_OFFICER", "first": "sarah", "last": "ochieng"}
                    ]
                }
            ]
        },
        {
            "name": "Rafiki Microfinance Bank",
            "code": "RAFIKI",
            "domain": "rafiki.co.ke",
            "reg_number": "RAF-003",
            "branches": [
                {
                    "code": "RAF-MSA",
                    "name": "Mombasa Branch",
                    "staff": [
                        {"role": "BRANCH_MANAGER", "first": "ali", "last": "hassan"},
                        {"role": "LOAN_OFFICER", "first": "fatuma", "last": "juma"}
                    ]
                }
            ]
        },
        {
            "name": "SMEP Microfinance Bank",
            "code": "SMEP",
            "domain": "smep.co.ke",
            "reg_number": "SMEP-004",
            "branches": [
                {
                    "code": "SMEP-KSM",
                    "name": "Kisumu Branch",
                    "staff": [
                        {"role": "BRANCH_MANAGER", "first": "john", "last": "otieno"},
                        {"role": "LOAN_OFFICER", "first": "mary", "last": "akinyi"}
                    ]
                }
            ]
        },
        {
            "name": "Caritas Microfinance Bank",
            "code": "CARITAS",
            "domain": "caritas-mfi.co.ke",
            "reg_number": "CAR-005",
            "branches": [
                {
                    "code": "CAR-NKR",
                    "name": "Nakuru Branch",
                    "staff": [
                        {"role": "BRANCH_MANAGER", "first": "lucy", "last": "njeri"},
                        {"role": "LOAN_OFFICER", "first": "samuel", "last": "kinuthia"}
                    ]
                }
            ]
        }
    ]
}

app = create_app()

with app.app_context():
    print("Dropping all tables to reset schema...")
    db.drop_all()
    print("Creating all tables with new schema...")
    db.create_all()

    for inst_data in yaml_data["institutions"]:
        inst = LendingInstitution(
            registered_business_name=inst_data["name"],
            registration_number=inst_data["reg_number"],
            kra_pin=f"P{inst_data['code']}KRA",
            head_office_address="Nairobi",
            status="active",
            code=inst_data["code"],
            domain=inst_data["domain"]
        )
        db.session.add(inst)
        db.session.flush() # get inst.id
        
        print(f"Created Institution: {inst.registered_business_name} ({inst.domain})")

        for branch_data in inst_data["branches"]:
            branch = Branch(
                lending_institution_id=inst.id,
                name=branch_data["name"],
                code=branch_data["code"]
            )
            db.session.add(branch)
            db.session.flush() # get branch.id
            
            for staff_data in branch_data["staff"]:
                subdomain = "bm" if staff_data["role"] == "BRANCH_MANAGER" else "lo"
                email = f"{staff_data['first']}.{staff_data['last']}@{subdomain}.{inst.domain}"
                role = "branch_manager" if staff_data["role"] == "BRANCH_MANAGER" else "loan_officer"
                
                user = User(
                    lending_institution_id=inst.id,
                    branch_id=branch.id,
                    email=email,
                    password_hash=hash_password(f"{staff_data['first'].capitalize()}123!"),
                    full_name=f"{staff_data['first'].capitalize()} {staff_data['last'].capitalize()}",
                    role=role,
                    status="active"
                )
                db.session.add(user)
                print(f"  -> Created Staff: {email} ({role}) - Password: {staff_data['first'].capitalize()}123!")

    db.session.commit()
    print("Multi-tenant demo users seeded successfully.")
