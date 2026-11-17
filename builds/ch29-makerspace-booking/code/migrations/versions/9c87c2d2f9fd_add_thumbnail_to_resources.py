"""add_thumbnail_to_resources

Revision ID: 9c87c2d2f9fd
Revises: 40900e5960ff
Create Date: 2026-05-23 14:44:35.334246

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c87c2d2f9fd'
down_revision = '40900e5960ff'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thumbnail', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.drop_column('thumbnail')
