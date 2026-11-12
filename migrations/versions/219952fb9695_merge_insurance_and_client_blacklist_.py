"""Merge insurance and client blacklist migrations

Revision ID: 219952fb9695
Revises: 033d0996d89e, 51d69824c1b8
Create Date: 2026-11-10 10:54:53.576762

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '219952fb9695'
down_revision = ('033d0996d89e', '51d69824c1b8')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
