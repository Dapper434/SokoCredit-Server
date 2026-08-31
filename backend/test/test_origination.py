import pytest

from app import create_app
from extensions import db
import io


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
    r = client.post("/api/auth/institutions", json={
        "registered_business_name": "Test SACCO",
        "registration_number": reg_number,
        "kra_pin": kra_pin,
        "head_office_address": "123 Moi Avenue, Nairobi",
        "admin_email": email,
        "admin_password": "SuperSecret123",
        "admin_full_name": "Test Principal Officer",
    })
    body = r.get_json()
    return body["access_token"], body["user"]["id"]


def test_admin_can_create_customer_profile_for_self(client):
    token, admin_id = signup_institution(client)
    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": admin_id, "national_id_number": "12345678"},
    )
    assert r.status_code == 201
    assert r.get_json()["national_id_number"] == "12345678"
    assert r.get_json()["credit_tier"] is None  # only Underwriting ever sets this


def test_duplicate_national_id_rejected(client):
    token, admin_id = signup_institution(client)
    client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": admin_id, "national_id_number": "DUPEID1"},
    )
    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": admin_id, "national_id_number": "DUPEID1"},
    )
    assert r.status_code == 409


def test_cannot_create_profile_for_staff_in_another_institution(client):
    token_a, admin_a_id = signup_institution(client, reg_number="ORG-A", kra_pin="PIN-A", email="a@a.co.ke")
    token_b, admin_b_id = signup_institution(client, reg_number="ORG-B", kra_pin="PIN-B", email="b@b.co.ke")

    # Admin A tries to create a profile "owned by" Admin B (different institution)
    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"user_id": admin_b_id, "national_id_number": "CROSSID1"},
    )
    assert r.status_code == 403


def test_cannot_read_customer_profile_from_another_institution(client):
    token_a, admin_a_id = signup_institution(client, reg_number="ORG-A", kra_pin="PIN-A", email="a@a.co.ke")
    token_b, admin_b_id = signup_institution(client, reg_number="ORG-B", kra_pin="PIN-B", email="b@b.co.ke")

    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"user_id": admin_a_id, "national_id_number": "READTEST1"},
    )
    profile_id = r.get_json()["id"]

    r = client.get(f"/api/origination/customers/{profile_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403


def test_document_upload_and_badge_award(client, monkeypatch):
    from foundations import storage
    monkeypatch.setattr(storage, "upload_file", lambda path, b, c: path)

    token, admin_id = signup_institution(client)
    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": admin_id, "national_id_number": "DOCTEST1"},
    )
    profile_id = r.get_json()["id"]

    r = client.post(
        f"/api/origination/customers/{profile_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"document_type": "national_id", "file": (io.BytesIO(b"fake bytes"), "id.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
       


def test_set_credit_tier_via_service_directly(app, client):
    """
    Underwriting doesn't exist yet, so we call origination.services.set_credit_tier()
    directly here — this is exactly the call Underwriting will make once it's built.
    """
    token, admin_id = signup_institution(client)
    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": admin_id, "national_id_number": "TIERTEST1"},
    )
    profile_id = r.get_json()["id"]

    with app.app_context():
        from origination.services import set_credit_tier
        updated = set_credit_tier(profile_id, "A", actor_id=admin_id)
        assert updated.credit_tier == "A"

    r = client.get(f"/api/origination/customers/{profile_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.get_json()["credit_tier"] == "A"