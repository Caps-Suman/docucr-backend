"""create_sop_table

Revision ID: b91b03b94f3d
Revises: 
Create Date: 2026-01-23 09:33:06.756508

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b91b03b94f3d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the docucr.sop table
    op.create_table(
        'sop',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('provider_type', sa.String(), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('provider_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('workflow_process', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('billing_guidelines', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('coding_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['docucr.client.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='docucr'
    )
    op.create_index(op.f('ix_docucr_sop_id'), 'sop', ['id'], unique=False, schema='docucr')


def downgrade() -> None:
    op.drop_index(op.f('ix_docucr_sop_id'), table_name='sop', schema='docucr')
    op.drop_table('sop', schema='docucr')
