from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    # Required for Supabase pgbouncer (transaction mode).
    # Two separate caches must both be disabled:
    # 1. asyncpg's own statement cache (connect_args, driver level)
    # 2. SQLAlchemy's asyncpg PreparedStatement object cache (engine level)
    # Without both, pgbouncer can route the EXECUTE to a different server
    # connection than the one where the statement was PREPAREd.
    connect_args={"statement_cache_size": 0},
    prepared_statement_cache_size=0,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
