from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from datetime import date

from ..deps import get_db
from ..models import Trade, AccountSettings
from ..services.pnl_engine import aggregate_pnl

router = APIRouter(prefix="/risk-usage", tags=["risk"])


@router.get("/")
async def risk_usage(db: AsyncSession = Depends(get_db)):
    trades = (await db.execute(select(Trade))).scalars().all()

    account = (await db.execute(select(AccountSettings))).scalars().first()
    capital = Decimal(account.capital) if account else Decimal(0)

    pnl = aggregate_pnl(trades, capital)

    result = []
    for d in pnl["daily"]:
        if capital > 0:
            risk_pct = abs(Decimal(str(d["net_pnl"])) / capital) * 100
        else:
            risk_pct = Decimal(0)

        result.append({
            "date": d["date"],
            "risk_pct": float(round(risk_pct, 2))
        })

    return result
