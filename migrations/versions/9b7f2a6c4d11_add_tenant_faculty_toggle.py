"""add tenant faculty toggle

Revision ID: 9b7f2a6c4d11
Revises: 8ee30d5a76d9
Create Date: 2026-04-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b7f2a6c4d11'
down_revision = '8ee30d5a76d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'faculty_workflow_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade():
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('faculty_workflow_enabled')
