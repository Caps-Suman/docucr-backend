"""add_status_id_to_sop

Revision ID: c92c04b95f4e
Revises: b91b03b94f3d
Create Date: 2026-01-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c92c04b95f4e'
down_revision = 'b91b03b94f3d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sop', sa.Column('status_id', sa.Integer(), nullable=True), schema='docucr')
    op.create_foreign_key('fk_sop_status', 'sop', 'status', ['status_id'], ['id'], source_schema='docucr', referent_schema='docucr')


def downgrade() -> None:
    op.drop_constraint('fk_sop_status', 'sop', schema='docucr', type_='foreignkey')
    op.drop_column('sop', 'status_id', schema='docucr')
