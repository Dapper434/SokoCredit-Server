import io
import pytest

from app import create_app
from extensions import db
from foundations import storage


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
    return body["access_token"], body["user"]["id"], body["institution"]["id"]


# ---------------------------------------------------------------------------
# Pure-logic tests — no network, no mocking needed. These test OUR code
# (path building, validation rules), not Supabase itself.
# ---------------------------------------------------------------------------

def test_build_object_path_is_prefixed_and_unique():
    path1 = storage.build_object_path("institution", 7, "kra_cert.pdf")
    path2 = storage.build_object_path("institution", 7, "kra_cert.pdf")
    assert path1.startswith("institution/7/")
    assert path1.endswith("kra_cert.pdf")
    assert path1 != path2  # the UUID prefix must make repeat uploads collision-free


def test_build_object_path_sanitizes_dangerous_filename():
    path = storage.build_object_path("customer", 3, "../../etc/passwd")
    assert ".." not in path
    assert "/etc/" not in path


def test_validate_upload_rejects_disallowed_content_type():
    with pytest.raises(storage.StorageError):
        storage.validate_upload("application/x-msdownload", 1000)


def test_validate_upload_rejects_oversized_file():
    with pytest.raises(storage.StorageError):
        storage.validate_upload("application/pdf", storage.MAX_FILE_SIZE_BYTES + 1)


def test_validate_upload_accepts_valid_pdf():
    storage.validate_upload("application/pdf", 1000)  # should not raise


# ---------------------------------------------------------------------------
# Mocked integration tests — real route, real database, real RBAC checks,
# but the actual Supabase network calls are replaced with fakes via
# monkeypatch. This tests OUR wiring (does the route call upload_file with
# the right arguments? does the download route check institution access
# BEFORE calling generate_signed_url?) without needing real credentials or
# a real network call.
# ---------------------------------------------------------------------------

def test_institution_document_upload_and_download(app, client, monkeypatch):
    uploaded = {}

    def fake_upload_file(path, file_bytes, content_type):
        uploaded["path"] = path
        uploaded["bytes"] = file_bytes
        uploaded["content_type"] = content_type
        return path

    def fake_generate_signed_url(path, expires_in=None):
        return f"https://fake-supabase.test/{path}?token=fake"

    monkeypatch.setattr(storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(storage, "generate_signed_url", fake_generate_signed_url)

    token, admin_id, institution_id = signup_institution(client)

    r = client.post(
        f"/api/auth/institutions/{institution_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"document_type": "kra_tax_compliance", "file": (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "cert.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
    document_id = r.get_json()["id"]

    # Confirm OUR code called upload_file with the right shape of data —
    # this is checking our wiring, not Supabase's behavior.
    assert uploaded["content_type"] == "application/pdf"
    assert uploaded["path"].startswith(f"institution/{institution_id}/")

    r = client.get(
        f"/api/auth/institutions/{institution_id}/documents/{document_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.get_json()["url"].startswith("https://fake-supabase.test/")


def test_institution_document_download_blocked_cross_tenant(app, client, monkeypatch):
    monkeypatch.setattr(storage, "upload_file", lambda path, b, c: path)
    monkeypatch.setattr(storage, "generate_signed_url", lambda path, expires_in=None: "https://should-not-be-reached")

    token_a, _, institution_a = signup_institution(client, reg_number="ORG-A", kra_pin="PIN-A", email="a@a.co.ke")
    token_b, _, institution_b = signup_institution(client, reg_number="ORG-B", kra_pin="PIN-B", email="b@b.co.ke")

    r = client.post(
        f"/api/auth/institutions/{institution_a}/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"document_type": "kra_tax_compliance", "file": (io.BytesIO(b"fake bytes"), "cert.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    document_id = r.get_json()["id"]

    # Institution B's admin tries to download Institution A's document
    r = client.get(
        f"/api/auth/institutions/{institution_a}/documents/{document_id}/download",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


def test_customer_document_upload_and_download(app, client, monkeypatch):
    monkeypatch.setattr(storage, "upload_file", lambda path, b, c: path)
    monkeypatch.setattr(storage, "generate_signed_url", lambda path, expires_in=None: f"https://fake-supabase.test/{path}")

    token, admin_id, _ = signup_institution(client)
    r = client.post(
        "/api/origination/customers",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": admin_id, "national_id_number": "STORAGETEST1"},
    )
    profile_id = r.get_json()["id"]

    r = client.post(
        f"/api/origination/customers/{profile_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"document_type": "national_id", "file": (io.BytesIO(b"fake id photo bytes"), "id.jpg", "image/jpeg")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201
    document_id = r.get_json()["id"]

    r = client.get(
        f"/api/origination/customers/{profile_id}/documents/{document_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "url" in r.get_json()