import pytest
from decimal import Decimal
from app import create_app
from extensions import db
from foundations.models import LendingInstitution, User
from origination.models import CustomerProfile
from underwriting.models import Loan, SavingsAccount, LoanApproval
from servicing.models import RepaymentSchedule, Transaction

@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def signup_institution(client):
    r = client.post("/api/auth/institutions", json={
        "registered_business_name": "Test SACCO",
        "registration_number": "BRS-0001",
        "kra_pin": "P000111222A",
        "head_office_address": "123 Moi Avenue, Nairobi",
        "admin_email": "admin@sacco.co.ke",
        "admin_password": "SuperSecret123",
        "admin_full_name": "Test Principal Officer",
    })
    body = r.get_json()
    if r.status_code != 201:
        print("SIGNUP FAILED:", body)
    return body["access_token"], body["user"]["id"]

def create_test_data(client, app):
    token, admin_id = signup_institution(client)
    
    with app.app_context():
        inst = LendingInstitution.query.first()
        customer = CustomerProfile(
            user_id=admin_id,
            national_id_number="12345678",
            credit_tier="A"
        )
        db.session.add(customer)
        db.session.commit()
        
        savings = SavingsAccount(
            customer_profile_id=customer.id,
            total_savings_balance=Decimal("1000.00"),
            is_savings_mature=True
        )
        db.session.add(savings)
        db.session.commit()
        
        loan = Loan(
            customer_profile_id=customer.id,
            lending_institution_id=inst.id,
            principal=Decimal("1000.00"),
            interest_rate=Decimal("0.10"),
            term_days=30,
            repayment_frequency="weekly",
            status="pending"
        )
        db.session.add(loan)
        db.session.commit()
        
        approval = LoanApproval(
            loan_id=loan.id,
            maker_id=admin_id,
            checker_id=admin_id,
            decision="approved"
        )
        db.session.add(approval)
        db.session.commit()
        
        return token, loan.id

def test_disburse_loan(app, client):
    token, loan_id = create_test_data(client, app)
    
    r = client.post(
        f"/api/servicing/loans/{loan_id}/disburse",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    
    with app.app_context():
        loan = Loan.query.get(loan_id)
        assert loan.status == "active"
        assert loan.disbursed_at is not None
        
        txn = Transaction.query.filter_by(loan_id=loan.id).first()
        assert txn.transaction_type == "disbursement"
        assert txn.amount == Decimal("1000.00")
        
        schedules = RepaymentSchedule.query.filter_by(loan_id=loan.id).all()
        assert len(schedules) == 4 # 30 days // 7

def test_process_repayment(app, client):
    token, loan_id = create_test_data(client, app)
    
    client.post(
        f"/api/servicing/loans/{loan_id}/disburse",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    r = client.post(
        f"/api/servicing/loans/{loan_id}/repayment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "amount": "300.00",
            "channel": "mpesa",
            "gateway_reference": "REF123"
        }
    )
    assert r.status_code == 201
    
    with app.app_context():
        schedules = RepaymentSchedule.query.filter_by(loan_id=loan_id).order_by(RepaymentSchedule.installment_number.asc()).all()
        assert schedules[0].status == "paid"
        assert schedules[0].amount_paid == schedules[0].total_due # 275.00
        
        assert schedules[1].status == "partial"
        assert schedules[1].amount_paid == Decimal("25.00")

