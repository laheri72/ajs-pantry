"""add global dish estimates

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-05-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('dish', schema=None) as batch_op:
        batch_op.add_column(sa.Column('normalized_name', sa.String(length=140), nullable=True))
        batch_op.add_column(sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False))
        batch_op.add_column(sa.Column('origin_tenant_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_dish_origin_tenant_id_tenants', 'tenants', ['origin_tenant_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_dish_normalized_name'), ['normalized_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_dish_is_archived'), ['is_archived'], unique=False)
        batch_op.create_index(batch_op.f('ix_dish_origin_tenant_id'), ['origin_tenant_id'], unique=False)

    op.execute("""
        UPDATE dish
        SET normalized_name = regexp_replace(lower(btrim(name)), '[[:space:]]+', ' ', 'g')
        WHERE normalized_name IS NULL
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'dish'
                  AND column_name = 'tenant_id'
            ) THEN
                UPDATE dish
                SET origin_tenant_id = tenant_id
                WHERE origin_tenant_id IS NULL
                  AND tenant_id IS NOT NULL;
            END IF;
        END $$;
    """)
    op.execute("UPDATE dish SET updated_at = created_at WHERE updated_at IS NULL")

    op.create_table(
        'dish_estimate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dish_id', sa.Integer(), nullable=False),
        sa.Column('serving_count', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('ingredients_json', sa.JSON(), nullable=True),
        sa.Column('tips_json', sa.JSON(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_tenant_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['dish_id'], ['dish.id']),
        sa.ForeignKeyConstraint(['updated_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['updated_by_tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dish_id', name='uq_dish_estimate_dish_id'),
    )
    op.create_index(op.f('ix_dish_estimate_updated_by_id'), 'dish_estimate', ['updated_by_id'], unique=False)
    op.create_index(op.f('ix_dish_estimate_updated_by_tenant_id'), 'dish_estimate', ['updated_by_tenant_id'], unique=False)

    op.create_table(
        'dish_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=60), nullable=False),
        sa.Column('dish_id', sa.Integer(), nullable=True),
        sa.Column('target_dish_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=True),
        sa.Column('performed_by_id', sa.Integer(), nullable=True),
        sa.Column('actor_tenant_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['actor_tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['dish_id'], ['dish.id']),
        sa.ForeignKeyConstraint(['performed_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['target_dish_id'], ['dish.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dish_audit_log_action'), 'dish_audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_dish_audit_log_actor_tenant_id'), 'dish_audit_log', ['actor_tenant_id'], unique=False)
    op.create_index(op.f('ix_dish_audit_log_created_at'), 'dish_audit_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_dish_audit_log_dish_id'), 'dish_audit_log', ['dish_id'], unique=False)
    op.create_index(op.f('ix_dish_audit_log_performed_by_id'), 'dish_audit_log', ['performed_by_id'], unique=False)
    op.create_index(op.f('ix_dish_audit_log_target_dish_id'), 'dish_audit_log', ['target_dish_id'], unique=False)

    with op.batch_alter_table('dish', schema=None) as batch_op:
        batch_op.alter_column('is_archived', server_default=None)


def downgrade():
    op.drop_index(op.f('ix_dish_audit_log_target_dish_id'), table_name='dish_audit_log')
    op.drop_index(op.f('ix_dish_audit_log_performed_by_id'), table_name='dish_audit_log')
    op.drop_index(op.f('ix_dish_audit_log_dish_id'), table_name='dish_audit_log')
    op.drop_index(op.f('ix_dish_audit_log_created_at'), table_name='dish_audit_log')
    op.drop_index(op.f('ix_dish_audit_log_actor_tenant_id'), table_name='dish_audit_log')
    op.drop_index(op.f('ix_dish_audit_log_action'), table_name='dish_audit_log')
    op.drop_table('dish_audit_log')

    op.drop_index(op.f('ix_dish_estimate_updated_by_tenant_id'), table_name='dish_estimate')
    op.drop_index(op.f('ix_dish_estimate_updated_by_id'), table_name='dish_estimate')
    op.drop_table('dish_estimate')

    with op.batch_alter_table('dish', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dish_origin_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_dish_is_archived'))
        batch_op.drop_index(batch_op.f('ix_dish_normalized_name'))
        batch_op.drop_constraint('fk_dish_origin_tenant_id_tenants', type_='foreignkey')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('origin_tenant_id')
        batch_op.drop_column('is_archived')
        batch_op.drop_column('normalized_name')
