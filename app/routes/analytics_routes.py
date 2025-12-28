from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db
from ..models import Trade
from ..services.pnl_engine import aggregate_pnl

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ==================================================
# DAILY / WEEKLY / MONTHLY PnL
# ==================================================
@router.get("/daily-pnl")
async def daily_pnl(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Trade).order_by(Trade.trade_time)
    )
    trades = result.scalars().all()

    pnl = aggregate_pnl(trades)
    return pnl["daily"]


# ==================================================
# STRATEGY PERFORMANCE (SAFE VERSION)
# ==================================================
@router.get("/strategy")
async def strategy_analytics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Trade).where(Trade.final_strategy.isnot(None))
    )
    trades = result.scalars().all()

    stats = {}

    for t in trades:
        strategy = t.final_strategy
        pnl = float(t.price) * int(t.quantity)
        if t.side == "SELL":
            pnl = -pnl

        if strategy not in stats:
            stats[strategy] = {
                "trades": 0,
                "wins": 0,
                "total_pnl": 0.0
            }

        stats[strategy]["trades"] += 1
        stats[strategy]["total_pnl"] += pnl

        if pnl > 0:
            stats[strategy]["wins"] += 1

    output = []
    for s, v in stats.items():
        win_rate = (v["wins"] / v["trades"]) * 100 if v["trades"] else 0
        output.append({
            "strategy": s,
            "trades": v["trades"],
            "win_rate": round(win_rate, 2),
            "total_pnl": round(v["total_pnl"], 2),
        })

    return output
