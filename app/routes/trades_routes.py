from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db
from ..models import Trade

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("")
async def get_trades(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Trade).order_by(Trade.trade_time.desc())
    )
    trades = result.scalars().all()

    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "quantity": t.quantity,
            "price": float(t.price),
            "trade_time": t.trade_time.isoformat(),
            "suggested_strategy": t.suggested_strategy,
            "final_strategy": t.final_strategy,
            "strategy_source": t.strategy_source,
            "notes": t.notes,
        }
        for t in trades
    ]
