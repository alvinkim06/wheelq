"""Add client documents

Revision ID: f84d680044a2
Revises: 219952fb9695
Create Date: 2026-11-10 12:37:11.720100

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f84d680044a2'
down_revision = '219952fb9695'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'client_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=30), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['client.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['admin_user.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(
        'ix_client_documents_client_id',
        'client_documents',
        ['client_id']
    )

    op.create_index(
        'ix_client_documents_document_type',
        'client_documents',
        ['document_type']
    )


def downgrade():
    op.drop_index(
        'ix_client_documents_document_type',
        table_name='client_documents'
    )

    op.drop_index(
        'ix_client_documents_client_id',
        table_name='client_documents'
    )

    op.drop_table('client_documents')