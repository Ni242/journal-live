from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db
from ..models import AccountSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/capital")
async def get_capital(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AccountSettings).order_by(AccountSettings.id.desc())
    )
    account = result.scalars().first()

    return {
        "capital": float(account.capital) if account else 0.0
    }
