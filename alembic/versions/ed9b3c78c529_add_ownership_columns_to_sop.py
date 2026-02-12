"""add ownership columns to sop

Revision ID: ed9b3c78c529
Revises: 7ffa90fe3bbe
Create Date: 2026-02-11 12:52:23.895931

"""
from alembic import op
import sqlalchemy as sa


revision = 'ed9b3c78c529'
down_revision = '7ffa90fe3bbe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sop', sa.Column('created_by', sa.String(), nullable=True), schema='docucr')
    op.add_column('sop', sa.Column('organisation_id', sa.String(), nullable=True), schema='docucr')
    op.create_foreign_key(None, 'sop', 'user', ['created_by'], ['id'], source_schema='docucr', referent_schema='docucr')
    op.create_foreign_key(None, 'sop', 'organisation', ['organisation_id'], ['id'], source_schema='docucr', referent_schema='docucr')


def downgrade() -> None:
    op.drop_constraint(None, 'sop', schema='docucr', type_='foreignkey')
    op.drop_constraint(None, 'sop', schema='docucr', type_='foreignkey')
    op.drop_column('sop', 'organisation_id', schema='docucr')
    op.drop_column('sop', 'created_by', schema='docucr')
