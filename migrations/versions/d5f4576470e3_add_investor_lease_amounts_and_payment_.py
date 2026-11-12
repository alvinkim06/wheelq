
"""Add investor lease amounts and payment links

Revision ID: d5f4576470e3
Revises: a2f1765ef7e9
"""

from alembic import op
import sqlalchemy as sa

revision = 'd5f4576470e3'
down_revision = 'a2f1765ef7e9'
branch_labels = None
depends_on = None


def upgrade():
    # Add agreed amount to existing leases.
    with op.batch_alter_table('lease') as batch_op:
        batch_op.add_column(
            sa.Column(
                'agreed_amount',
                sa.Numeric(12, 2),
                nullable=False,
                server_default=sa.text('0')
            )
        )

    # Link investor payments to their lease.
    with op.batch_alter_table('lease_payment') as batch_op:
        batch_op.add_column(
            sa.Column('lease_id', sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('payment_method', sa.String(50), nullable=True)
        )
        batch_op.add_column(
            sa.Column('reference', sa.String(100), nullable=True)
        )
        batch_op.add_column(
            sa.Column('notes', sa.Text(), nullable=True)
        )

        batch_op.create_index(
            'ix_lease_payment_lease_id',
            ['lease_id'],
            unique=False
        )

        batch_op.create_foreign_key(
            'fk_lease_payment_lease_id_lease',
            'lease',
            ['lease_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('lease_payment') as batch_op:
        batch_op.drop_constraint(
            'fk_lease_payment_lease_id_lease',
            type_='foreignkey'
        )
        batch_op.drop_index('ix_lease_payment_lease_id')
        batch_op.drop_column('notes')
        batch_op.drop_column('reference')
        batch_op.drop_column('payment_method')
        batch_op.drop_column('lease_id')

    with op.batch_alter_table('lease') as batch_op:
        batch_op.drop_column('agreed_amount')
