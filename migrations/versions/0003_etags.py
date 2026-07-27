"""conditional-request etags

Revision ID: 0003_etags
Revises: 0002_prereleases
Create Date: 2026-07-27 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_etags"
down_revision = "0002_prereleases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("etag_releases", sa.String(255), nullable=True))
    op.add_column("repositories", sa.Column("etag_tags", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("repositories", "etag_tags")
    op.drop_column("repositories", "etag_releases")
