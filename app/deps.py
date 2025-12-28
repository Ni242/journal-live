import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# =========================
# DATABASE URL
# =========================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./trading_journal.db"
)

# =========================
# ASYNC ENGINE
# =========================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,   # avoids stale connections
)

# =========================
# SESSION FACTORY
# =========================
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# =========================
# DB DEPENDENCY
# =========================
async def get_db():
    async with AsyncSessionLocal() as session:
        # SQLite stability settings (safe for Postgres too)
        if DATABASE_URL.startswith("sqlite"):
            await session.execute(text("PRAGMA journal_mode=WAL;"))
            await session.execute(text("PRAGMA foreign_keys=ON;"))
        yield session
