from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # "admin" | "user"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("forge_type", "base_url", "owner", "name", name="uq_repo_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    forge_type: Mapped[str] = mapped_column(String(20))  # github|gitlab|gitea|bitbucket
    # Instance base URL. Empty means "use the provider's public default".
    base_url: Mapped[str] = mapped_column(String(255), default="")
    owner: Mapped[str] = mapped_column(String(200))       # owner / group / workspace
    name: Mapped[str] = mapped_column(String(200))        # repo / project slug

    watch_releases: Mapped[bool] = mapped_column(Boolean, default=True)
    watch_tags: Mapped[bool] = mapped_column(Boolean, default=False)
    include_prereleases: Mapped[bool] = mapped_column(Boolean, default=True)

    token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted access token
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)        # baseline captured?

    etag_releases: Mapped[str | None] = mapped_column(String(255), nullable=True)
    etag_tags: Mapped[str | None] = mapped_column(String(255), nullable=True)

    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    routes: Mapped[list["NotificationRoute"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    releases: Mapped[list["Release"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def web_url(self) -> str:
        """Browser URL for the repo, derived from forge + base_url + slug.
        Public hosts use their canonical domain; self-hosted uses base_url."""
        if self.forge_type == "sourceforge":
            root = self.base_url or "https://sourceforge.net"
            return f"{root.rstrip('/')}/projects/{self.name}/"  # owner is a pseudo-value
        if self.forge_type == "pypi":
            root = self.base_url or "https://pypi.org"
            return f"{root.rstrip('/')}/project/{self.name}/"
        if self.forge_type == "github":
            root = self.base_url or "https://github.com"
        elif self.forge_type == "gitlab":
            root = self.base_url or "https://gitlab.com"
        elif self.forge_type == "bitbucket":
            root = self.base_url or "https://bitbucket.org"
        else:  # gitea / forgejo are self-hosted; base_url is the site root
            root = self.base_url or ""
        return f"{root.rstrip('/')}/{self.owner}/{self.name}" if root else ""


class TelegramBot(Base):
    __tablename__ = "telegram_bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token_enc: Mapped[str] = mapped_column(Text)                 # encrypted bot token
    default_chat_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    routes: Mapped[list["NotificationRoute"]] = relationship(back_populates="bot")


class NotificationRoute(Base):
    __tablename__ = "notification_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    channel_type: Mapped[str] = mapped_column(String(16))  # "telegram" | "email"

    # Telegram-only fields:
    bot_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_bots.id", ondelete="SET NULL"), nullable=True
    )
    chat_id: Mapped[str | None] = mapped_column(String(120), nullable=True)  # overrides bot default

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    repository: Mapped["Repository"] = relationship(back_populates="routes")
    bot: Mapped["TelegramBot | None"] = relationship(back_populates="routes")


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("repository_id", "kind", "external_key", name="uq_release_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))          # "release" | "tag"
    external_key: Mapped[str] = mapped_column(String(255))  # release id or tag name
    name: Mapped[str] = mapped_column(String(255), default="")
    tag_name: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(500), default="")

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    prerelease: Mapped[bool] = mapped_column(Boolean, default=False)

    notified: Mapped[bool] = mapped_column(Boolean, default=False)   # Telegram sent?
    summarized: Mapped[bool] = mapped_column(Boolean, default=False)  # included in a digest?

    repository: Mapped["Repository"] = relationship(back_populates="releases")
