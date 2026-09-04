"""Add 'rejected' to the loans.status CHECK constraint.

SQLite can't ALTER a CHECK constraint in place, so this does the documented
table-rebuild: rename, recreate with the new constraint, copy, drop. Child
tables (loan_approvals, repayment_schedules, reschedule_requests, transactions)
reference `loans` by name and survive the swap.

Idempotent: re-running is a no-op once 'rejected' is already allowed.

Usage:  .venv/bin/python migrate_add_rejected_status.py
"""
from app import create_app
from extensions import db
from sqlalchemy import text

NEW_LOANS_SQL = """
CREATE TABLE loans (
    id INTEGER NOT NULL,
    lending_institution_id INTEGER NOT NULL,
    customer_profile_id INTEGER NOT NULL,
    principal NUMERIC(14, 2) NOT NULL,
    interest_rate NUMERIC(6, 4) NOT NULL,
    term_days INTEGER NOT NULL,
    repayment_frequency VARCHAR(20) NOT NULL,
    loan_purpose VARCHAR(255),
    status VARCHAR(20) NOT NULL,
    write_off_reason TEXT,
    disbursed_at DATETIME,
    maturity_date DATE,
    created_at DATETIME NOT NULL,
    available_credit_at_application NUMERIC(14,2),
    PRIMARY KEY (id),
    CONSTRAINT ck_loans_status_valid CHECK (status IN
        ('pending', 'active', 'rejected', 'restructured', 'fully_paid', 'defaulted', 'written_off')),
    CONSTRAINT ck_loans_repayment_frequency_valid CHECK (repayment_frequency IN ('daily', 'weekly', 'lump_sum')),
    FOREIGN KEY(lending_institution_id) REFERENCES lending_institutions (id),
    FOREIGN KEY(customer_profile_id) REFERENCES customer_profiles (id)
)
"""

app = create_app()
with app.app_context():
    current = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='loans'"
    )).scalar()

    if current and "'rejected'" in current:
        print("loans.status already allows 'rejected' — nothing to do.")
    else:
        db.session.execute(text("PRAGMA foreign_keys=OFF"))
        db.session.execute(text("BEGIN"))
        try:
            db.session.execute(text("ALTER TABLE loans RENAME TO loans_old"))
            db.session.execute(text(NEW_LOANS_SQL))
            db.session.execute(text(
                "INSERT INTO loans ("
                "id, lending_institution_id, customer_profile_id, principal, interest_rate, "
                "term_days, repayment_frequency, loan_purpose, status, write_off_reason, "
                "disbursed_at, maturity_date, created_at, available_credit_at_application) "
                "SELECT id, lending_institution_id, customer_profile_id, principal, interest_rate, "
                "term_days, repayment_frequency, loan_purpose, status, write_off_reason, "
                "disbursed_at, maturity_date, created_at, available_credit_at_application "
                "FROM loans_old"
            ))
            db.session.execute(text("DROP TABLE loans_old"))
            db.session.execute(text("COMMIT"))
            print("Rebuilt loans table with 'rejected' allowed in ck_loans_status_valid.")
        except Exception:
            db.session.execute(text("ROLLBACK"))
            raise
        finally:
            db.session.execute(text("PRAGMA foreign_keys=ON"))

    fk_issues = db.session.execute(text("PRAGMA foreign_key_check")).fetchall()
    print("foreign_key_check:", "clean" if not fk_issues else fk_issues)
    n = db.session.execute(text("SELECT count(*) FROM loans")).scalar()
    print(f"loans rows preserved: {n}")
