"""add faculty budget cycles and report submissions

Revision ID: e2a2b6f7d4c1
Revises: b83ed1c2648f
Create Date: 2026-04-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2a2b6f7d4c1'
down_revision = 'b83ed1c2648f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'faculty_budget_cycle',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('submission_deadline', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('faculty_budget_cycle', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faculty_budget_cycle_created_by_id'), ['created_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_budget_cycle_end_date'), ['end_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_budget_cycle_start_date'), ['start_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_budget_cycle_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_budget_cycle_submission_deadline'), ['submission_deadline'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_budget_cycle_tenant_id'), ['tenant_id'], unique=False)

    op.create_table(
        'faculty_report_submission',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cycle_id', sa.Integer(), nullable=False),
        sa.Column('floor', sa.Integer(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('report_title', sa.String(length=150), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('submission_notes', sa.Text(), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('revision_no', sa.Integer(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verified_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['cycle_id'], ['faculty_budget_cycle.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['verified_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cycle_id', 'floor', name='uq_faculty_report_submission_cycle_floor')
    )
    with op.batch_alter_table('faculty_report_submission', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_cycle_id'), ['cycle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_floor'), ['floor'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_uploaded_by_id'), ['uploaded_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_verified_by_id'), ['verified_by_id'], unique=False)

    with op.batch_alter_table('budget', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cycle_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('allocated_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('faculty_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('is_faculty_allocation', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f('ix_budget_allocated_by_id'), ['allocated_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_cycle_id'), ['cycle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_budget_is_faculty_allocation'), ['is_faculty_allocation'], unique=False)
        batch_op.create_foreign_key(None, 'faculty_budget_cycle', ['cycle_id'], ['id'])
        batch_op.create_foreign_key(None, 'user', ['allocated_by_id'], ['id'])

    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('report_submission_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_bill_report_submission_id'), ['report_submission_id'], unique=False)
        batch_op.create_foreign_key(None, 'faculty_report_submission', ['report_submission_id'], ['id'])

    with op.batch_alter_table('expense', schema=None) as batch_op:
        batch_op.add_column(sa.Column('report_submission_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_expense_report_submission_id'), ['report_submission_id'], unique=False)
        batch_op.create_foreign_key(None, 'faculty_report_submission', ['report_submission_id'], ['id'])


def downgrade():
    with op.batch_alter_table('expense', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_expense_report_submission_id'))
        batch_op.drop_column('report_submission_id')

    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_bill_report_submission_id'))
        batch_op.drop_column('report_submission_id')

    with op.batch_alter_table('budget', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_budget_is_faculty_allocation'))
        batch_op.drop_index(batch_op.f('ix_budget_cycle_id'))
        batch_op.drop_index(batch_op.f('ix_budget_allocated_by_id'))
        batch_op.drop_column('is_faculty_allocation')
        batch_op.drop_column('faculty_note')
        batch_op.drop_column('allocated_by_id')
        batch_op.drop_column('cycle_id')

    with op.batch_alter_table('faculty_report_submission', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_verified_by_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_uploaded_by_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_status'))
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_floor'))
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_cycle_id'))

    op.drop_table('faculty_report_submission')

    with op.batch_alter_table('faculty_budget_cycle', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faculty_budget_cycle_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_faculty_budget_cycle_submission_deadline'))
        batch_op.drop_index(batch_op.f('ix_faculty_budget_cycle_status'))
        batch_op.drop_index(batch_op.f('ix_faculty_budget_cycle_start_date'))
        batch_op.drop_index(batch_op.f('ix_faculty_budget_cycle_end_date'))
        batch_op.drop_index(batch_op.f('ix_faculty_budget_cycle_created_by_id'))

    op.drop_table('faculty_budget_cycle')
