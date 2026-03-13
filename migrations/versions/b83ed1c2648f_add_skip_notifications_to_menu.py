"""add skip_notifications to Menu

Revision ID: b83ed1c2648f
Revises: bdd4590fc68f
Create Date: 2026-03-13 07:52:34.519405

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b83ed1c2648f'
down_revision = 'bdd4590fc68f'
branch_labels = None
depends_on = None


def upgrade():
    # Only add the skip_notifications column to the menu table
    with op.batch_alter_table('menu', schema=None) as batch_op:
        batch_op.add_column(sa.Column('skip_notifications', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('menu', schema=None) as batch_op:
        batch_op.drop_column('skip_notifications')
