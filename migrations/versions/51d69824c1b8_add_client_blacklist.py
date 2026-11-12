"""add client blacklist

Revision ID: 51d69824c1b8
Revises: c7426718dbea
Create Date: 2026-11-10 10:49:19.547410
"""

from alembic import op
import sqlalchemy as sa


revision = "51d69824c1b8"
down_revision = "c7426718dbea"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_blacklist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("blacklisted_by", sa.Integer(), nullable=False),
        sa.Column("blacklisted_at", sa.DateTime(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("removed_by", sa.Integer(), nullable=True),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.Column("removal_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["blacklisted_by"], ["admin_user.id"]
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["client.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["removed_by"], ["admin_user.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_client_blacklist_client_id",
        "client_blacklist",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_blacklist_is_active",
        "client_blacklist",
        ["is_active"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_client_blacklist_is_active",
        table_name="client_blacklist",
    )
    op.drop_index(
        "ix_client_blacklist_client_id",
        table_name="client_blacklist",
    )
    op.drop_table("client_blacklist")