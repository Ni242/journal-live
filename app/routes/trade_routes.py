from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from ..deps import get_db
from ..models import Trade

router = APIRouter(prefix="/trades", tags=["trades"])


# =========================
# SCHEMAS
# =========================
class StrategyPayload(BaseModel):
    strategy: Optional[str] = None
    notes: Optional[str] = None


# =========================
# GET ALL TRADES
# =========================
@router.get("/")
async def get_trades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Trade).order_by(Trade.trade_time.desc())
    )
    trades = result.scalars().all()
    return trades


# =========================
# UPDATE STRATEGY + NOTES
# =========================
@router.patch("/{trade_id}/strategy")
async def update_strategy(
    trade_id: int,
    payload: StrategyPayload,
    db: AsyncSession = Depends(get_db)
):
    trade = await db.get(Trade, trade_id)

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # ✅ Update only provided fields
    if payload.strategy is not None:
        trade.final_strategy = payload.strategy
        trade.strategy_source = "MANUAL"

    if payload.notes is not None:
        trade.notes = payload.notes

    await db.commit()
    await db.refresh(trade)

    return {
        "status": "updated",
        "id": trade.id,
        "final_strategy": trade.final_strategy,
        "notes": trade.notes,
    }
