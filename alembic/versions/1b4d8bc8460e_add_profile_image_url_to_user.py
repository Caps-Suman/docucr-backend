"""add profile_image_url to user

Revision ID: 1b4d8bc8460e
Revises: 0bc66bb69507
Create Date: 2026-02-15 10:15:21.007811

"""
from alembic import op
import sqlalchemy as sa


revision = '1b4d8bc8460e'
down_revision = '0bc66bb69507'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user', sa.Column('profile_image_url', sa.String(), nullable=True), schema='docucr')


def downgrade() -> None:
    op.drop_column('user', 'profile_image_url', schema='docucr')
