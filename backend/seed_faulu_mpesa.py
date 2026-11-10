"""Seed Faulu's Daraja Sandbox M-Pesa credentials (encrypted).

This is the credential-seeding step extracted from migrate_mpesa_integration.py
(part 4 of that script) - the schema-rebuilding parts (1-3) there are raw
SQLite DDL left over from before the Alembic migrations existed and are no
longer needed; the schema (transactions.status='pending', lending_institutions
mpesa_* columns) is now created by migrations/versions/28cf0752fd5c_*.py.

Reads the consumer key/secret from env (FAULU_MPESA_CONSUMER_KEY /
FAULU_MPESA_CONSUMER_SECRET); requires MPESA_ENC_KEY to be set (the Fernet
key used to encrypt them at rest - must match whatever the running server
uses to decrypt, e.g. Render's MPESA_ENC_KEY env var).

Only Faulu is configured, matching the rest of the demo data - every other
institution stays unconfigured on purpose.

Usage:
    export FAULU_MPESA_CONSUMER_KEY=...
    export FAULU_MPESA_CONSUMER_SECRET=...
    .venv/bin/python seed_faulu_mpesa.py
"""
import os

from app import create_app
from extensions import db
from foundations.models import LendingInstitution
from servicing.mpesa.config import encrypt_secret

# Safaricom's public Sandbox values (shared test shortcode/passkey).
SANDBOX_SHORTCODE = "174379"

def sandbox_passkey():
    """Safaricom published sandbox passkey for test shortcode 174379, read from env."""
    pk = os.environ.get("FAULU_MPESA_PASSKEY") or os.environ.get("MPESA_SANDBOX_PASSKEY")
    if not pk:
        raise SystemExit(
            "Set MPESA_SANDBOX_PASSKEY (Safaricom published sandbox passkey "
            "for shortcode 174379) or FAULU_MPESA_PASSKEY."
        )
    return pk

app = create_app()
with app.app_context():
    if not os.environ.get("MPESA_ENC_KEY"):
        raise SystemExit(
            "MPESA_ENC_KEY is not set. This must match the MPESA_ENC_KEY the "
            "running server uses to decrypt these credentials later - set it "
            "in this shell to the same value as on Render before running this."
        )

    faulu = LendingInstitution.query.filter_by(code="FAULU").first()
    if faulu is None:
        raise SystemExit("FAULU institution not found — run seed_multi_tenant_safe.py first.")

    ck = os.environ.get("FAULU_MPESA_CONSUMER_KEY")
    cs = os.environ.get("FAULU_MPESA_CONSUMER_SECRET")
    if not ck or not cs:
        raise SystemExit(
            "Set FAULU_MPESA_CONSUMER_KEY and FAULU_MPESA_CONSUMER_SECRET in "
            "this shell before running this script."
        )

    # Passkey/shortcode: default to Safaricom's shared sandbox test values;
    # override only if your Daraja app was assigned its own.
    pk = sandbox_passkey()
    sc = os.environ.get("FAULU_MPESA_SHORTCODE", SANDBOX_SHORTCODE)

    faulu.mpesa_consumer_key = encrypt_secret(ck)
    faulu.mpesa_consumer_secret = encrypt_secret(cs)
    faulu.mpesa_passkey = encrypt_secret(pk)
    faulu.mpesa_stk_shortcode = sc
    faulu.mpesa_environment = "sandbox"
    db.session.commit()

    print(f"FAULU: seeded sandbox M-Pesa credentials  shortcode={sc}  "
          f"passkey={'custom' if os.environ.get('FAULU_MPESA_PASSKEY') else 'public-sandbox'}  "
          f"consumer_key={'*' * (len(ck) - 4)}{ck[-4:]}")

    others = LendingInstitution.query.filter(
        LendingInstitution.code != "FAULU",
        LendingInstitution.mpesa_stk_shortcode.isnot(None),
    ).all()
    print("Non-Faulu institutions left unconfigured:",
          "OK" if not others else [i.code for i in others])
