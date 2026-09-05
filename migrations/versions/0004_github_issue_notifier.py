"""github issue notifier

Revision ID: 0004_github_issue_notifier
Revises: 0003_etags
Create Date: 2026-09-05 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_github_issue_notifier"
down_revision = "0003_etags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "releases",
        sa.Column("issue_filed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Every release that already exists predates this channel — there was no
    # github_issue route to file it through, so (as with notified/summarized
    # when no route exists) treat it as already handled rather than letting
    # the next sweep's retry pass flood the tracker with the entire backlog.
    op.execute("UPDATE releases SET issue_filed = true")

    # Turn the channel on for every already-tracked repository, so existing
    # software keeps working the same way it always has notification-wise —
    # only *new* releases discovered from here on get an issue filed.
    op.execute(
        """
        INSERT INTO notification_routes (repository_id, channel_type, enabled)
        SELECT id, 'github_issue', true FROM repositories
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM notification_routes WHERE channel_type = 'github_issue'")
    op.drop_column("releases", "issue_filed")
