"""add faculty messages

Revision ID: f3c4e8a1b2d9
Revises: a7b91f5c2d44
Create Date: 2026-04-06 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3c4e8a1b2d9'
down_revision = 'a7b91f5c2d44'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'faculty_message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('target_scope', sa.String(length=30), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('faculty_message', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faculty_message_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_message_created_by_id'), ['created_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_message_is_archived'), ['is_archived'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_message_target_scope'), ['target_scope'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_message_tenant_id'), ['tenant_id'], unique=False)

    op.create_table(
        'faculty_message_floor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('faculty_message_id', sa.Integer(), nullable=False),
        sa.Column('floor', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['faculty_message_id'], ['faculty_message.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('faculty_message_floor', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faculty_message_floor_faculty_message_id'), ['faculty_message_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_message_floor_floor'), ['floor'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_message_floor_tenant_id'), ['tenant_id'], unique=False)


def downgrade():
    with op.batch_alter_table('faculty_message_floor', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faculty_message_floor_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_message_floor_floor'))
        batch_op.drop_index(batch_op.f('ix_faculty_message_floor_faculty_message_id'))

    op.drop_table('faculty_message_floor')

    with op.batch_alter_table('faculty_message', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faculty_message_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_message_target_scope'))
        batch_op.drop_index(batch_op.f('ix_faculty_message_is_archived'))
        batch_op.drop_index(batch_op.f('ix_faculty_message_created_by_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_message_created_at'))

    op.drop_table('faculty_message')
