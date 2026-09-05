"""fix stale check constraints on user role, loans status, loan approvals decision

Revision ID: 1f7121f7fc9a
Revises: 28cf0752fd5c
Create Date: 2026-09-05 21:32:06.628456

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f7121f7fc9a'
down_revision = '28cf0752fd5c'
branch_labels = None
depends_on = None


def upgrade():
    # These three CHECK constraints were part of the original (stale) initial
    # migration and never got updated as the models evolved - Alembic's
    # autogenerate does not detect CHECK constraint changes by default, so
    # the earlier sync migration (28cf0752fd5c) missed them.
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_users_role_valid',
            "role IN ('loan_officer', 'branch_manager', 'customer')"
        )

    with op.batch_alter_table('loans', schema=None) as batch_op:
        batch_op.drop_constraint('ck_loans_status_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_loans_status_valid',
            "status IN ('pending', 'active', 'rejected', 'restructured', 'fully_paid', 'defaulted', 'written_off')"
        )

    with op.batch_alter_table('loan_approvals', schema=None) as batch_op:
        batch_op.drop_constraint('ck_loan_approvals_decision_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_loan_approvals_decision_valid',
            "decision IN ('pending', 'approved', 'rejected', 'countered')"
        )


def downgrade():
    with op.batch_alter_table('loan_approvals', schema=None) as batch_op:
        batch_op.drop_constraint('ck_loan_approvals_decision_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_loan_approvals_decision_valid',
            "decision IN ('pending', 'approved', 'rejected')"
        )

    with op.batch_alter_table('loans', schema=None) as batch_op:
        batch_op.drop_constraint('ck_loans_status_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_loans_status_valid',
            "status IN ('pending', 'active', 'restructured', 'fully_paid', 'defaulted')"
        )

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_users_role_valid',
            "role IN ('loan_officer', 'manager', 'admin', 'super_admin')"
        )
