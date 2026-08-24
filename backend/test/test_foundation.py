import pytest

from app import create_app
from extensions import db


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


def signup_institution(client, reg_number="BRS-0001", kra_pin="P000111222A", email="admin@sacco.co.ke"):
    return client.post("/api/auth/institutions", json={
        "registered_business_name": "Test SACCO",
        "registration_number": reg_number,
        "kra_pin": kra_pin,
        "head_office_address": "123 Moi Avenue, Nairobi",
        "admin_email": email,
        "admin_password": "SuperSecret123",
        "admin_full_name": "Test Principal Officer",
    })


def test_institution_signup_creates_institution_and_founding_admin(client):
    r = signup_institution(client)
    assert r.status_code == 201
    body = r.get_json()
    assert body["user"]["role"] == "super_admin"
    assert body["institution"]["status"] == "active"  # auto-approved
    assert "access_token" in body


def test_founding_admin_can_log_in_immediately_since_auto_approved(client):
    signup_institution(client, email="canlogin@sacco.co.ke")
    r = client.post("/api/auth/login", json={
        "email": "canlogin@sacco.co.ke", "password": "SuperSecret123",
    })
    assert r.status_code == 200
    assert r.get_json()["user"]["status"] == "active"


def test_duplicate_registration_number_rejected(client):
    signup_institution(client, reg_number="DUPE-1", email="a@sacco.co.ke")
    r = signup_institution(client, reg_number="DUPE-1", kra_pin="DIFFERENTPIN", email="b@sacco.co.ke")
    assert r.status_code == 409


def test_duplicate_kra_pin_rejected(client):
    signup_institution(client, reg_number="REG-A", kra_pin="SAMEPIN", email="a@sacco.co.ke")
    r = signup_institution(client, reg_number="REG-B", kra_pin="SAMEPIN", email="b@sacco.co.ke")
    assert r.status_code == 409


def test_login_wrong_password_rejected(client):
    signup_institution(client, email="loginfail@sacco.co.ke")
    r = client.post("/api/auth/login", json={
        "email": "loginfail@sacco.co.ke", "password": "wrongpass",
    })
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_admin_can_add_teammate_loan_officer_cannot(client):
    r = signup_institution(client, email="rbac-admin@sacco.co.ke")
    admin_token = r.get_json()["access_token"]

    r = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": "officer@sacco.co.ke", "password": "OfficerPass1",
              "full_name": "Officer One", "role": "loan_officer"},
    )
    assert r.status_code == 201
    assert r.get_json()["status"] == "active"  # teammates start active, unlike the founding admin

    r = client.post("/api/auth/login", json={
        "email": "officer@sacco.co.ke", "password": "OfficerPass1",
    })
    officer_token = r.get_json()["access_token"]

    r = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {officer_token}"},
        json={"email": "another@sacco.co.ke", "password": "AnotherPass1",
              "full_name": "Another", "role": "loan_officer"},
    )
    assert r.status_code == 403


def test_audit_log_written_on_institution_and_admin_creation(app, client):
    signup_institution(client, email="audit@sacco.co.ke")
    with app.app_context():
        from foundations.models import AuditLog
        institution_logs = AuditLog.query.filter_by(entity_type="LendingInstitution").all()
        user_logs = AuditLog.query.filter_by(entity_type="User").all()
        assert len(institution_logs) >= 2  # create (pending_review) + approve (active)
        assert len(user_logs) == 1
        assert user_logs[0].after["role"] == "super_admin"


def test_verify_institution_access_blocks_cross_tenant(app, client):
    r1 = signup_institution(client, reg_number="ORG-1", kra_pin="PIN-1", email="a@org1.co.ke")
    r2 = signup_institution(client, reg_number="ORG-2", kra_pin="PIN-2", email="a@org2.co.ke")
    org1_token = r1.get_json()["access_token"]
    org2_id = r2.get_json()["institution"]["id"]

    with app.test_request_context(headers={"Authorization": f"Bearer {org1_token}"}):
        from flask_jwt_extended import verify_jwt_in_request
        from foundations.auth import verify_institution_access, AuthError

        verify_jwt_in_request()
        with pytest.raises(AuthError):
            verify_institution_access(org2_id)


def test_primary_markets_capped_at_six(client):
    r = client.post("/api/auth/institutions", json={
        "registered_business_name": "Market Heavy SACCO",
        "registration_number": "MKT-001",
        "kra_pin": "MKTPIN001",
        "head_office_address": "456 Kenyatta Ave, Nairobi",
        "admin_email": "markets@sacco.co.ke",
        "admin_password": "SuperSecret123",
        "admin_full_name": "Markets Admin",
        "primary_markets": ["Gikomba", "Muthurwa", "Kariokor", "Wakulima", "Toi", "City", "Kongowea"],
    })
    assert r.status_code == 422  # schema rejects more than 6 before it even reaches the service layer