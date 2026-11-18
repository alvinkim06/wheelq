
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

    # Create the financial tables before adding references to them.
    op.create_table(
        "financial_charges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount_charged", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"], ["client.id"],
            name="fk_financial_charges_client_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["booking.id"],
            name="fk_financial_charges_booking_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["admin_user.id"],
            name="fk_financial_charges_created_by"
        ),
    )
    op.create_index("ix_financial_charges_client_id", "financial_charges", ["client_id"])
    op.create_index("ix_financial_charges_booking_id", "financial_charges", ["booking_id"])
    op.create_index("ix_financial_charges_category", "financial_charges", ["category"])

    op.create_table(
        "financial_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("charge_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["charge_id"], ["financial_charges.id"],
            name="fk_financial_payments_charge_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["admin_user.id"],
            name="fk_financial_payments_recorded_by"
        ),
        sa.UniqueConstraint("reference", name="uq_financial_payments_reference"),
    )
    op.create_index("ix_financial_payments_charge_id", "financial_payments", ["charge_id"])

    op.create_table(
        "financial_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("charge_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("adjustment_type", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["charge_id"], ["financial_charges.id"],
            name="fk_financial_adjustments_charge_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["admin_user.id"],
            name="fk_financial_adjustments_created_by"
        ),
    )
    op.create_index("ix_financial_adjustments_charge_id", "financial_adjustments", ["charge_id"])

    op.create_table(
        "penalty_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("grace_period_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["admin_user.id"],
            name="fk_penalty_settings_updated_by"
        ),
    )

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
