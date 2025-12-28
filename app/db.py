import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Load .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print("🚀 CONNECTING TO DATABASE:", DATABASE_URL)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
