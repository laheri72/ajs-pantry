"""add expense print reports

Revision ID: a7b91f5c2d44
Revises: e2a2b6f7d4c1
Create Date: 2026-04-05 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b91f5c2d44'
down_revision = 'e2a2b6f7d4c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'expense_print_report',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cycle_id', sa.Integer(), nullable=True),
        sa.Column('floor', sa.Integer(), nullable=False),
        sa.Column('report_title', sa.String(length=150), nullable=False),
        sa.Column('report_budget', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_spent', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('remaining_balance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['cycle_id'], ['faculty_budget_cycle.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('expense_print_report', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expense_print_report_created_by_id'), ['created_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_print_report_cycle_id'), ['cycle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_print_report_floor'), ['floor'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_print_report_tenant_id'), ['tenant_id'], unique=False)

    op.create_table(
        'expense_print_report_bill',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('print_report_id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('include_in_summary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('include_as_voucher', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['bill_id'], ['bill.id'], ),
        sa.ForeignKeyConstraint(['print_report_id'], ['expense_print_report.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('print_report_id', 'bill_id', name='uq_expense_print_report_bill')
    )
    with op.batch_alter_table('expense_print_report_bill', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expense_print_report_bill_bill_id'), ['bill_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_print_report_bill_print_report_id'), ['print_report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_expense_print_report_bill_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('faculty_report_submission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('print_report_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_faculty_report_submission_print_report_id'), ['print_report_id'], unique=False)
        batch_op.create_foreign_key(None, 'expense_print_report', ['print_report_id'], ['id'])


def downgrade():
    with op.batch_alter_table('faculty_report_submission', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_faculty_report_submission_print_report_id'))
        batch_op.drop_column('print_report_id')

    with op.batch_alter_table('expense_print_report_bill', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_expense_print_report_bill_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_expense_print_report_bill_print_report_id'))
        batch_op.drop_index(batch_op.f('ix_expense_print_report_bill_bill_id'))

    op.drop_table('expense_print_report_bill')

    with op.batch_alter_table('expense_print_report', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_expense_print_report_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_expense_print_report_floor'))
        batch_op.drop_index(batch_op.f('ix_expense_print_report_cycle_id'))
        batch_op.drop_index(batch_op.f('ix_expense_print_report_created_by_id'))

    op.drop_table('expense_print_report')
