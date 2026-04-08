"""add faculty_report_submission constraint and all

Revision ID: e8be6e260d2f
Revises: f3c4e8a1b2d9
Create Date: 2026-04-08 19:54:34.604113

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8be6e260d2f'
down_revision = 'f3c4e8a1b2d9'
branch_labels = None
depends_on = None


def upgrade():
    # Only adding the new Faculty features. NO DROPS or DELETES.
    with op.batch_alter_table('faculty_report_submission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allocated_amount', sa.Numeric(precision=12, scale=2), nullable=True))
        # We replace the old constraint name with the new one
        try:
            batch_op.drop_constraint('uq_faculty_report_submission_cycle_floor', type_='unique')
        except:
            pass
        batch_op.create_unique_constraint('uq_cycle_floor_submission', ['cycle_id', 'floor'])


def downgrade():
    with op.batch_alter_table('faculty_report_submission', schema=None) as batch_op:
        batch_op.drop_constraint('uq_cycle_floor_submission', type_='unique')
        batch_op.drop_column('allocated_amount')
