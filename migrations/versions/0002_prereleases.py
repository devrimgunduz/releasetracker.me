"""pre-release support

Revision ID: 0002_prereleases
Revises: 0001_initial
Create Date: 2026-07-27 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_prereleases"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("include_prereleases", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "releases",
        sa.Column("prerelease", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("releases", "prerelease")
    op.drop_column("repositories", "include_prereleases")
