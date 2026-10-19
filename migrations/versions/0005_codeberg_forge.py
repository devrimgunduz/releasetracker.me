"""codeberg forge type

Revision ID: 0005_codeberg_forge
Revises: 0004_github_issue_notifier
Create Date: 2026-10-20 00:00:00
"""
from alembic import op

revision = "0005_codeberg_forge"
down_revision = "0004_github_issue_notifier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Codeberg repos used to be stored as gitea + base_url. Move them to the
    # dedicated forge so a re-add of the same URL hits uq_repo_identity instead
    # of creating a duplicate. Skip any that would collide with an existing row.
    op.execute(
        """
        UPDATE repositories r
        SET forge_type = 'codeberg', base_url = ''
        WHERE r.forge_type = 'gitea'
          AND rtrim(lower(r.base_url), '/') IN ('https://codeberg.org', 'https://www.codeberg.org')
          AND NOT EXISTS (
              SELECT 1 FROM repositories o
              WHERE o.forge_type = 'codeberg' AND o.base_url = ''
                AND o.owner = r.owner AND o.name = r.name
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE repositories
        SET forge_type = 'gitea', base_url = 'https://codeberg.org'
        WHERE forge_type = 'codeberg' AND base_url = ''
        """
    )
