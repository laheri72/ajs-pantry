"""add user soft delete and tenant audit log

Revision ID: c6d7e8f9a0b1
Revises: fix_estimates_v2
Create Date: 2026-05-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a0b1'
down_revision = 'fix_estimates_v2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_active',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.create_table(
        'tenant_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('target_type', sa.String(length=80), nullable=True),
        sa.Column('target_id', sa.String(length=80), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['actor_user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tenant_audit_log_action'), 'tenant_audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_tenant_audit_log_actor_user_id'), 'tenant_audit_log', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_tenant_audit_log_created_at'), 'tenant_audit_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_tenant_audit_log_tenant_id'), 'tenant_audit_log', ['tenant_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_tenant_audit_log_tenant_id'), table_name='tenant_audit_log')
    op.drop_index(op.f('ix_tenant_audit_log_created_at'), table_name='tenant_audit_log')
    op.drop_index(op.f('ix_tenant_audit_log_actor_user_id'), table_name='tenant_audit_log')
    op.drop_index(op.f('ix_tenant_audit_log_action'), table_name='tenant_audit_log')
    op.drop_table('tenant_audit_log')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('is_active')
