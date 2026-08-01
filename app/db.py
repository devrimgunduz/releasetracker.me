from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

# pool_pre_ping discards cleanly-dead connections; command_timeout bounds every
# query so a black-hole connection (silently dropped TCP, no RST) can't hang the
# worker forever; pool_recycle drops connections older than 30 min to avoid them.
engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"command_timeout": 30},
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with SessionFactory() as session:
        yield session
