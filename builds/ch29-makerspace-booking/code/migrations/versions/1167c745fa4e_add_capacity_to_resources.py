"""add capacity to resources

Revision ID: 1167c745fa4e
Revises: ca048952536f
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '1167c745fa4e'
down_revision = 'ca048952536f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('resources', sa.Column('capacity', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('resources', 'capacity')
