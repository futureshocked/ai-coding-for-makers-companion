"""add resource management fields

Revision ID: ca048952536f
Revises: 82ffcbc93503
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'ca048952536f'
down_revision = '82ffcbc93503'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('resources', sa.Column('location', sa.Text(), nullable=True))
    op.add_column('resources', sa.Column('available_start', sa.Time(), nullable=True))
    op.add_column('resources', sa.Column('available_end', sa.Time(), nullable=True))
    op.add_column('resources', sa.Column(
        'is_archived', sa.Boolean(), server_default=sa.false(), nullable=False
    ))


def downgrade():
    op.drop_column('resources', 'is_archived')
    op.drop_column('resources', 'available_end')
    op.drop_column('resources', 'available_start')
    op.drop_column('resources', 'location')
