
"""Add email outbox

Revision ID: 06d27b94eba9
Revises: 761e360ba712
Create Date: 2026-11-12 11:24:41.757290
"""

from alembic import op
import sqlalchemy as sa


revision = '06d27b94eba9'
down_revision = '761e360ba712'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_outbox',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_key', sa.String(length=180), nullable=False),
        sa.Column('event_type', sa.String(length=60), nullable=False),
        sa.Column('related_model', sa.String(length=60), nullable=True),
        sa.Column('related_id', sa.Integer(), nullable=True),
        sa.Column('recipients', sa.JSON(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('html_body', sa.Text(), nullable=True),
        sa.Column('text_body', sa.Text(), nullable=True),
        sa.Column('attachment_name', sa.String(length=255), nullable=True),
        sa.Column('attachment_data', sa.LargeBinary(), nullable=True),
        sa.Column('attachment_mimetype', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index(
        'ix_email_outbox_event_key',
        'email_outbox',
        ['event_key'],
        unique=True,
    )

    op.create_index(
        'ix_email_outbox_event_type',
        'email_outbox',
        ['event_type'],
        unique=False,
    )

    op.create_index(
        'ix_email_outbox_status',
        'email_outbox',
        ['status'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_email_outbox_status', table_name='email_outbox')
    op.drop_index('ix_email_outbox_event_type', table_name='email_outbox')
    op.drop_index('ix_email_outbox_event_key', table_name='email_outbox')
    op.drop_table('email_outbox')
