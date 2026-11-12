"""Link airport transfers to financial charges

Revision ID: a2f1765ef7e9
Revises: b58505c43f7c
Create Date: 2026-11-11 14:17:30.858680
"""

from alembic import op
import sqlalchemy as sa


revision = "a2f1765ef7e9"
down_revision = "b58505c43f7c"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("financial_charges", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("airport_transfer_id", sa.Integer(), nullable=True)
        )

        batch_op.create_index(
            "ix_financial_charges_airport_transfer_id",
            ["airport_transfer_id"],
            unique=True
        )

        batch_op.create_foreign_key(
            "fk_financial_charges_airport_transfer_id_airport_transfers",
            "airport_transfers",
            ["airport_transfer_id"],
            ["id"],
            ondelete="SET NULL"
        )


def downgrade():
    with op.batch_alter_table("financial_charges", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_financial_charges_airport_transfer_id_airport_transfers",
            type_="foreignkey"
        )

        batch_op.drop_index(
            "ix_financial_charges_airport_transfer_id"
        )

        batch_op.drop_column("airport_transfer_id")