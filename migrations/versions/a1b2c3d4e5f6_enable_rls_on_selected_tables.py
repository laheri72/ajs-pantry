"""enable rls on selected tables

Revision ID: a1b2c3d4e5f6
Revises: 9b7f2a6c4d11
Create Date: 2026-04-22 17:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9b7f2a6c4d11'
branch_labels = None
depends_on = None


def upgrade():
    # Enabling Row Level Security as requested by Supabase Linter
    op.execute("ALTER TABLE expense_print_report ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_budget_cycle ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE expense_print_report_bill ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_message ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_message_floor ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_report_submission ENABLE ROW LEVEL SECURITY;")


def downgrade():
    # Disabling Row Level Security
    op.execute("ALTER TABLE expense_print_report DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_budget_cycle DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE expense_print_report_bill DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_message DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_message_floor DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faculty_report_submission DISABLE ROW LEVEL SECURITY;")
