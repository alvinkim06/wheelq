"""Add manual financial entries

Revision ID: 761e360ba712
Revises: d5f4576470e3
Create Date: 2026-11-12 09:42:30.430880

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '761e360ba712'
down_revision = 'd5f4576470e3'
branch_labels = None
depends_on = None



def upgrade():
    op.create_table(
        'manual_financial_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_type', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('transaction_date', sa.DateTime(), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "entry_type IN ('earning', 'expense')",
            name='check_manual_entry_type'
        ),
        sa.CheckConstraint(
            'amount > 0',
            name='check_manual_entry_amount'
        ),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['admin_user.id'],
            ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(
        'ix_manual_financial_entries_category',
        'manual_financial_entries',
        ['category']
    )

    op.create_index(
        'ix_manual_financial_entries_entry_type',
        'manual_financial_entries',
        ['entry_type']
    )

    op.create_index(
        'ix_manual_financial_entries_transaction_date',
        'manual_financial_entries',
        ['transaction_date']
    )


def downgrade():
    op.drop_index(
        'ix_manual_financial_entries_transaction_date',
        table_name='manual_financial_entries'
    )

    op.drop_index(
        'ix_manual_financial_entries_entry_type',
        table_name='manual_financial_entries'
    )

    op.drop_index(
        'ix_manual_financial_entries_category',
        table_name='manual_financial_entries'
    )

    op.drop_table('manual_financial_entries')
