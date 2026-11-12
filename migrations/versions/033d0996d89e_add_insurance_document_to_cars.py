"""Add insurance document to cars

Revision ID: 033d0996d89e
Revises: 094281751754
"""

from alembic import op
import sqlalchemy as sa


revision = "033d0996d89e"
down_revision = "094281751754"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "car",
        sa.Column("insurance_document", sa.String(length=255), nullable=True)
    )


def downgrade():
    op.drop_column("car", "insurance_document")
