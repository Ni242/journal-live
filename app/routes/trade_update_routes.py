from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..deps import get_db
from ..models import Trade

router = APIRouter(tags=["trades"])

@router.patch("/trades/{trade_id}/strategy")
async def update_trade(
    trade_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db)
):
    trade = await db.get(Trade, trade_id)

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # ✅ UPDATE ONLY PROVIDED FIELDS
    if "strategy" in payload:
        trade.final_strategy = payload["strategy"]
        trade.strategy_source = "MANUAL"

    if "notes" in payload:
        trade.notes = payload["notes"]

    await db.commit()
    await db.refresh(trade)

    return {
        "id": trade.id,
        "final_strategy": trade.final_strategy,
        "notes": trade.notes,
        "strategy_source": trade.strategy_source,
    }
