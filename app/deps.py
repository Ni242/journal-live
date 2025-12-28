import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# =========================
# DATABASE URL (REQUIRED)
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# =========================
# ASYNC ENGINE
# =========================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
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
        # SQLite-only pragmas (safe guard)
        if DATABASE_URL.startswith("sqlite"):
            await session.execute(text("PRAGMA journal_mode=WAL;"))
            await session.execute(text("PRAGMA foreign_keys=ON;"))

        yield session
