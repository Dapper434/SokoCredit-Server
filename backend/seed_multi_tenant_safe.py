"""Safe (non-destructive) version of seed_multi_tenant.py.

The original script opens with db.drop_all() / db.create_all(), which wipes
every table before reseeding - fine for a disposable local dev db, but
catastrophic against a shared/production database like Supabase (it also
bypasses Alembic entirely, desyncing migration tracking).

This version seeds the same 5 institutions/branches/staff but checks for
existing rows first, so it's safe to run against a database that already
has data and is safe to re-run (won't create duplicates).
"""
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
    for inst_data in yaml_data["institutions"]:
        inst = LendingInstitution.query.filter_by(code=inst_data["code"]).first()
        if not inst:
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
            db.session.flush()  # get inst.id
            print(f"Created Institution: {inst.registered_business_name} ({inst.domain})")
        else:
            print(f"Institution {inst_data['code']} already exists, skipping")

        for branch_data in inst_data["branches"]:
            branch = Branch.query.filter_by(
                lending_institution_id=inst.id, code=branch_data["code"]
            ).first()
            if not branch:
                branch = Branch(
                    lending_institution_id=inst.id,
                    name=branch_data["name"],
                    code=branch_data["code"]
                )
                db.session.add(branch)
                db.session.flush()  # get branch.id
                print(f"  Created Branch: {branch.name} ({branch.code})")
            else:
                print(f"  Branch {branch_data['code']} already exists, skipping")

            for staff_data in branch_data["staff"]:
                subdomain = "bm" if staff_data["role"] == "BRANCH_MANAGER" else "lo"
                email = f"{staff_data['first']}.{staff_data['last']}@{subdomain}.{inst.domain}"
                role = "branch_manager" if staff_data["role"] == "BRANCH_MANAGER" else "loan_officer"

                user = User.query.filter_by(email=email).first()
                if not user:
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
                    print(f"    Created Staff: {email} ({role}) - Password: {staff_data['first'].capitalize()}123!")
                else:
                    print(f"    Staff {email} already exists, skipping")

    db.session.commit()
    print("Multi-tenant demo data seeded successfully (non-destructive).")
