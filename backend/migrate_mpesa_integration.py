"""Schema + seed for the Daraja Sandbox STK integration.

1. Rebuilds `transactions` to allow status='pending' and adds M-Pesa columns.
2. Creates `savings_deposits` (via create_all).
3. Adds mpesa_* columns to `lending_institutions`.
4. Seeds Faulu's Sandbox credentials (encrypted). Only Faulu — every other
   institution stays unconfigured on purpose.

Idempotent. Usage:  .venv/bin/python migrate_mpesa_integration.py

Faulu's consumer key/secret are read from env FAULU_MPESA_CONSUMER_KEY /
FAULU_MPESA_CONSUMER_SECRET if set (paste your own Daraja Sandbox app pair for
a real STK call). Otherwise a placeholder is stored and only the Phase 3C
simulated-callback path will work — which is the intended demo insurance.
"""
import os
from sqlalchemy import inspect as sa_inspect, text

from app import create_app
from extensions import db

NEW_TXN_SQL = """
CREATE TABLE transactions (
    id INTEGER NOT NULL,
    loan_id INTEGER NOT NULL,
    repayment_schedule_id INTEGER,
    amount NUMERIC(14, 2) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    gateway_reference VARCHAR(255),
    transaction_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    allocation_breakdown JSON,
    checkout_request_id VARCHAR(80),
    merchant_request_id VARCHAR(80),
    failure_reason VARCHAR(255),
    raw_callback JSON,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_txn_channel_valid CHECK (channel IN ('mpesa', 'airtel_money', 'bank_transfer', 'cash')),
    CONSTRAINT ck_txn_type_valid CHECK (transaction_type IN ('disbursement', 'repayment', 'penalty', 'fee')),
    CONSTRAINT ck_txn_status_valid CHECK (status IN ('pending', 'completed', 'failed', 'reversed')),
    FOREIGN KEY(loan_id) REFERENCES loans (id),
    FOREIGN KEY(repayment_schedule_id) REFERENCES repayment_schedules (id),
    UNIQUE (gateway_reference),
    UNIQUE (checkout_request_id)
)
"""

OLD_TXN_COLS = ("id", "loan_id", "repayment_schedule_id", "amount", "channel",
                "gateway_reference", "transaction_type", "status",
                "allocation_breakdown", "created_at")

INSTITUTION_COLS = {
    "mpesa_consumer_key": "TEXT",
    "mpesa_consumer_secret": "TEXT",
    "mpesa_passkey": "TEXT",
    "mpesa_stk_shortcode": "VARCHAR(20)",
    "mpesa_environment": "VARCHAR(20)",
}

# Safaricom's public Sandbox values.
SANDBOX_SHORTCODE = "174379"
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"

app = create_app()
with app.app_context():
    insp = sa_inspect(db.engine)

    # 1. Rebuild transactions if the pending status isn't allowed yet.
    txn_sql = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'"
    )).scalar()
    if txn_sql and "'pending'" in txn_sql and "checkout_request_id" in txn_sql:
        print("transactions: already migrated")
    else:
        db.session.execute(text("PRAGMA foreign_keys=OFF"))
        db.session.execute(text("BEGIN"))
        try:
            db.session.execute(text("ALTER TABLE transactions RENAME TO transactions_old"))
            db.session.execute(text(NEW_TXN_SQL))
            cols = ", ".join(OLD_TXN_COLS)
            db.session.execute(text(
                f"INSERT INTO transactions ({cols}) SELECT {cols} FROM transactions_old"
            ))
            db.session.execute(text("DROP TABLE transactions_old"))
            db.session.execute(text("COMMIT"))
            print("transactions: rebuilt (status 'pending' + M-Pesa columns)")
        except Exception:
            db.session.execute(text("ROLLBACK"))
            raise
        finally:
            db.session.execute(text("PRAGMA foreign_keys=ON"))

    # 2. lending_institutions M-Pesa columns
    inst_cols = {c["name"] for c in sa_inspect(db.engine).get_columns("lending_institutions")}
    for name, ddl in INSTITUTION_COLS.items():
        if name not in inst_cols:
            db.session.execute(text(f"ALTER TABLE lending_institutions ADD COLUMN {name} {ddl}"))
            print(f"lending_institutions: added {name}")
    db.session.commit()

    # 3. savings_deposits + anything else new
    db.create_all()
    print("savings_deposits: ensured")

    # 4. Seed Faulu only
    from foundations.models import LendingInstitution
    from servicing.mpesa.config import encrypt_secret

    faulu = LendingInstitution.query.filter_by(code="FAULU").first()
    if faulu is None:
        print("FAULU institution not found — skipping credential seed.")
    else:
        ck = os.environ.get("FAULU_MPESA_CONSUMER_KEY", "REPLACE_WITH_DARAJA_SANDBOX_CONSUMER_KEY")
        cs = os.environ.get("FAULU_MPESA_CONSUMER_SECRET", "REPLACE_WITH_DARAJA_SANDBOX_CONSUMER_SECRET")
        # Passkey: default is Safaricom's public value for test shortcode 174379.
        # Override with FAULU_MPESA_PASSKEY only if your Daraja app shows a
        # different per-app passkey.
        pk = os.environ.get("FAULU_MPESA_PASSKEY", SANDBOX_PASSKEY)
        # Shortcode: 174379 is the sandbox test shortcode that delivers a real
        # STK prompt to a real phone. Override only if you know you need to.
        sc = os.environ.get("FAULU_MPESA_SHORTCODE", SANDBOX_SHORTCODE)

        faulu.mpesa_consumer_key = encrypt_secret(ck)
        faulu.mpesa_consumer_secret = encrypt_secret(cs)
        faulu.mpesa_passkey = encrypt_secret(pk)
        faulu.mpesa_stk_shortcode = sc
        faulu.mpesa_environment = "sandbox"
        db.session.commit()
        placeholder = ck.startswith("REPLACE_WITH")
        print(f"FAULU: seeded sandbox M-Pesa credentials  shortcode={sc}  "
              f"passkey={'custom' if pk != SANDBOX_PASSKEY else 'public-sandbox'}  "
              f"({'PLACEHOLDER consumer key/secret — set FAULU_MPESA_CONSUMER_KEY/SECRET env and re-run' if placeholder else 'real consumer key/secret from env'})")

    others = LendingInstitution.query.filter(
        LendingInstitution.code != "FAULU",
        LendingInstitution.mpesa_stk_shortcode.isnot(None),
    ).all()
    print("Non-Faulu institutions left unconfigured:",
          "OK" if not others else [i.code for i in others])
