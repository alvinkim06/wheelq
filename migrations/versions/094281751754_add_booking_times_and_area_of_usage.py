
"""Add booking times and area of usage

Revision ID: 094281751754
Revises: 7bf64f01cce4
Create Date: 2026-11-09 07:09:41.997243
"""

from alembic import op
import sqlalchemy as sa

revision = '094281751754'
down_revision = '7bf64f01cce4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'booking',
        sa.Column('pickup_time', sa.Time(), nullable=True)
    )
    op.add_column(
        'booking',
        sa.Column('dropoff_time', sa.Time(), nullable=True)
    )
    op.add_column(
        'booking',
        sa.Column('area_of_usage', sa.String(length=150), nullable=True)
    )


def downgrade():
    op.drop_column('booking', 'area_of_usage')
    op.drop_column('booking', 'dropoff_time')
    op.drop_column('booking', 'pickup_time')

