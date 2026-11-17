"""split availability into weekday and weekend windows

Revision ID: d4e9f0a12b3c
Revises: 1167c745fa4e
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e9f0a12b3c'
down_revision = '1167c745fa4e'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns (nullable initially to allow data migration)
    op.add_column('resources', sa.Column('weekday_start', sa.Time(), nullable=True))
    op.add_column('resources', sa.Column('weekday_end',   sa.Time(), nullable=True))
    op.add_column('resources', sa.Column('weekend_start', sa.Time(), nullable=True))
    op.add_column('resources', sa.Column('weekend_end',   sa.Time(), nullable=True))

    # Migrate existing data: copy old values to weekday columns; fall back to 09:00/18:00 when NULL
    op.execute("""
        UPDATE resources
        SET weekday_start = COALESCE(available_start, '09:00'),
            weekday_end   = COALESCE(available_end,   '18:00')
    """)

    # Enforce NOT NULL on weekday columns now that all rows are populated
    op.alter_column('resources', 'weekday_start', nullable=False)
    op.alter_column('resources', 'weekday_end',   nullable=False)

    # Drop old columns
    op.drop_column('resources', 'available_start')
    op.drop_column('resources', 'available_end')


def downgrade():
    op.add_column('resources', sa.Column('available_start', sa.Time(), nullable=True))
    op.add_column('resources', sa.Column('available_end',   sa.Time(), nullable=True))

    op.execute("""
        UPDATE resources
        SET available_start = weekday_start,
            available_end   = weekday_end
    """)

    op.drop_column('resources', 'weekend_end')
    op.drop_column('resources', 'weekend_start')
    op.drop_column('resources', 'weekday_end')
    op.drop_column('resources', 'weekday_start')
