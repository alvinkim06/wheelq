
"""Add unified financial charges payments and adjustments

Revision ID: b58505c43f7c
Revises: f84d680044a2
"""

from alembic import op
import sqlalchemy as sa

revision = "b58505c43f7c"
down_revision = "f84d680044a2"
branch_labels = None
depends_on = None


def upgrade():

    # The four financial tables and their indexes were already
    # created by the previous partially completed upgrade.
    # Do not create them again.

    # Extend existing damage charges.
    with op.batch_alter_table("damage_charge") as batch_op:
        batch_op.add_column(
            sa.Column("financial_charge_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("description", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("payment_method", sa.String(50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("payment_reference", sa.String(100), nullable=True)
        )
        batch_op.add_column(
            sa.Column("paid_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="unpaid"
            )
        )

        batch_op.create_unique_constraint(
            "uq_damage_charge_financial_charge_id",
            ["financial_charge_id"]
        )

        batch_op.create_foreign_key(
            "fk_damage_charge_financial_charge",
            "financial_charges",
            ["financial_charge_id"],
            ["id"],
            ondelete="RESTRICT"
        )

    # Extend existing late penalties.
    with op.batch_alter_table("late_penalties") as batch_op:
        batch_op.add_column(
            sa.Column("financial_charge_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("expected_return_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("actual_return_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "minutes_late",
                sa.Integer(),
                nullable=False,
                server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "chargeable_minutes",
                sa.Integer(),
                nullable=False,
                server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column("rate", sa.Numeric(12, 2), nullable=True)
        )
        batch_op.add_column(
            sa.Column("interval_minutes", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "grace_period_minutes",
                sa.Integer(),
                nullable=False,
                server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "intervals_charged",
                sa.Integer(),
                nullable=False,
                server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column("discarded_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("discard_reason", sa.Text(), nullable=True)
        )

        batch_op.create_unique_constraint(
            "uq_late_penalties_financial_charge_id",
            ["financial_charge_id"]
        )

        batch_op.create_foreign_key(
            "fk_late_penalties_financial_charge",
            "financial_charges",
            ["financial_charge_id"],
            ["id"],
            ondelete="RESTRICT"
        )


def downgrade():

    # Remove late penalty additions.
    with op.batch_alter_table("late_penalties") as batch_op:
        batch_op.drop_constraint(
            "fk_late_penalties_financial_charge",
            type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_late_penalties_financial_charge_id",
            type_="unique"
        )

        batch_op.drop_column("discard_reason")
        batch_op.drop_column("discarded_at")
        batch_op.drop_column("intervals_charged")
        batch_op.drop_column("grace_period_minutes")
        batch_op.drop_column("interval_minutes")
        batch_op.drop_column("rate")
        batch_op.drop_column("chargeable_minutes")
        batch_op.drop_column("minutes_late")
        batch_op.drop_column("actual_return_at")
        batch_op.drop_column("expected_return_at")
        batch_op.drop_column("financial_charge_id")

    # Remove damage charge additions.
    with op.batch_alter_table("damage_charge") as batch_op:
        batch_op.drop_constraint(
            "fk_damage_charge_financial_charge",
            type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_damage_charge_financial_charge_id",
            type_="unique"
        )

        batch_op.drop_column("status")
        batch_op.drop_column("paid_at")
        batch_op.drop_column("payment_reference")
        batch_op.drop_column("payment_method")
        batch_op.drop_column("description")
        batch_op.drop_column("financial_charge_id")

    # Remove the financial tables created by this revision.
    op.drop_table("financial_payments")
    op.drop_table("financial_adjustments")
    op.drop_table("financial_charges")
    op.drop_table("penalty_settings")
