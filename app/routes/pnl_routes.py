from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from ..deps import get_db
from ..models import Trade, AccountSettings
from ..services.pnl_engine import aggregate_pnl

router = APIRouter(prefix="/pnl", tags=["pnl"])


@router.get("/")
async def pnl_summary(db: AsyncSession = Depends(get_db)):
    # -------------------------------------------------
    # Fetch trades
    # -------------------------------------------------
    trades = (await db.execute(select(Trade))).scalars().all()

    # -------------------------------------------------
    # Fetch capital (READ ONLY)
    # -------------------------------------------------
    account = (
        await db.execute(
            select(AccountSettings).order_by(AccountSettings.id.desc())
        )
    ).scalars().first()

    capital = Decimal(account.capital) if account else Decimal("0")

    # -------------------------------------------------
    # Calculate PnL (single source of truth)
    # -------------------------------------------------
    pnl = aggregate_pnl(trades, capital=capital)

    # -------------------------------------------------
    # Return engine output AS-IS
    # -------------------------------------------------
    return pnl
