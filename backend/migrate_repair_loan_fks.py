"""Repair child-table FK references left pointing at 'loans_old'.

The rename step in migrate_add_rejected_status.py caused SQLite to rewrite the
loan_id foreign keys on transactions / repayment_schedules / loan_approvals /
reschedule_requests to REFERENCES "loans_old". This rebuilds each of those
tables with the reference pointed back at 'loans'. Idempotent.

Usage:  .venv/bin/python migrate_repair_loan_fks.py
"""
from app import create_app
from extensions import db
from sqlalchemy import text

CHILD_TABLES = ("transactions", "repayment_schedules", "loan_approvals", "reschedule_requests")

app = create_app()
with app.app_context():
    conn = db.session
    conn.execute(text("PRAGMA foreign_keys=OFF"))

    for table in CHILD_TABLES:
        sql = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"
        ), {"n": table}).scalar()
        if sql is None or '"loans_old"' not in sql and "loans_old" not in sql:
            print(f"  {table}: already clean")
            continue

        fixed = sql.replace('"loans_old"', "loans").replace("loans_old", "loans")
        cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
        collist = ", ".join(cols)
        tmp = f"{table}__new"
        fixed_tmp = fixed.replace(f"CREATE TABLE {table}", f"CREATE TABLE {tmp}", 1)

        conn.execute(text("BEGIN"))
        try:
            conn.execute(text(fixed_tmp))
            conn.execute(text(f"INSERT INTO {tmp} ({collist}) SELECT {collist} FROM {table}"))
            conn.execute(text(f"DROP TABLE {table}"))
            conn.execute(text(f"ALTER TABLE {tmp} RENAME TO {table}"))
            conn.execute(text("COMMIT"))
            print(f"  {table}: FK repointed to loans")
        except Exception:
            conn.execute(text("ROLLBACK"))
            raise

    conn.execute(text("PRAGMA foreign_keys=ON"))
    issues = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
    loan_issues = [i for i in issues if "loans_old" in str(i)]
    print("\nremaining loans_old references:", loan_issues or "none")
    print("all foreign_key_check rows:", len(issues), "(pre-existing audit_logs noise is unrelated)")
