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


def signup_org(client, slug="test-sacco"):
    return client.post("/api/auth/organizations", json={
        "name": "Test SACCO",
        "slug": slug,
        "admin_email": f"admin@{slug}.co.ke",
        "admin_password": "SuperSecret123",
        "admin_full_name": "Test Admin",
    })


def test_organization_signup_creates_org_and_admin(client):
    r = signup_org(client)
    assert r.status_code == 201
    body = r.get_json()
    assert body["user"]["role"] == "admin"
    assert "access_token" in body


def test_duplicate_slug_rejected(client):
    signup_org(client, slug="dupe")
    r = signup_org(client, slug="dupe")
    assert r.status_code == 409


def test_login_wrong_password_rejected(client):
    signup_org(client, slug="loginfail")
    r = client.post("/api/auth/login", json={
        "email": "admin@loginfail.co.ke", "password": "wrongpass",
    })
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_admin_can_add_teammate_loan_officer_cannot(client):
    r = signup_org(client, slug="rbactest")
    admin_token = r.get_json()["access_token"]

    r = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": "officer@rbactest.co.ke", "password": "OfficerPass1",
              "full_name": "Officer One", "role": "loan_officer"},
    )
    assert r.status_code == 201

    r = client.post("/api/auth/login", json={
        "email": "officer@rbactest.co.ke", "password": "OfficerPass1",
    })
    officer_token = r.get_json()["access_token"]

    r = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {officer_token}"},
        json={"email": "another@rbactest.co.ke", "password": "AnotherPass1",
              "full_name": "Another", "role": "loan_officer"},
    )
    assert r.status_code == 403


def test_audit_log_written_on_user_creation(app, client):
    signup_org(client, slug="audittest")
    with app.app_context():
        from foundations.models import AuditLog
        logs = AuditLog.query.filter_by(entity_type="User").all()
        assert len(logs) == 1
        assert logs[0].action == "create"
        assert logs[0].after["role"] == "admin"


def test_verify_organization_access_blocks_cross_tenant(app, client):
    r1 = signup_org(client, slug="org-one")
    r2 = signup_org(client, slug="org-two")
    org1_token = r1.get_json()["access_token"]
    org2_id = r2.get_json()["organization"]["id"]

    with app.test_request_context(headers={"Authorization": f"Bearer {org1_token}"}):
        from flask_jwt_extended import verify_jwt_in_request
        from foundations.auth import verify_organization_access, AuthError

        verify_jwt_in_request()
        with pytest.raises(AuthError):
            verify_organization_access(org2_id)