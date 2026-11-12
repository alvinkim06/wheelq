"""Add account activation status

Revision ID: c7426718dbea
Revises: 094281751754
"""

from alembic import op
import sqlalchemy as sa

revision = 'c7426718dbea'
down_revision = '094281751754'
branch_labels = None
depends_on = None


def upgrade():
    # Add account activation status
    with op.batch_alter_table('admin_user') as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_active',
                sa.Boolean(),
                server_default=sa.text('1'),
                nullable=False
            )
        )

    # Add admin reply to contact messages
    with op.batch_alter_table('contact_messages') as batch_op:
        batch_op.add_column(
            sa.Column('admin_reply', sa.Text(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('contact_messages') as batch_op:
        batch_op.drop_column('admin_reply')

    with op.batch_alter_table('admin_user') as batch_op:
        batch_op.drop_column('is_active')