from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from collections import defaultdict
from ..deps import get_db
from ..models import Trade

router = APIRouter(prefix="/analytics/strategy", tags=["strategy-analytics"])

@router.get("")
async def strategy_analytics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Trade))
    trades = result.scalars().all()

    stats = defaultdict(lambda: {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "win_pnl": [],
        "loss_pnl": []
    })

    for t in trades:
        strategy = t.final_strategy or t.suggested_strategy or "Unclassified"
        pnl = float(t.price * t.quantity * (-1 if t.side == "SELL" else 1))

        s = stats[strategy]
        s["trades"] += 1
        s["total_pnl"] += pnl

        if pnl > 0:
            s["wins"] += 1
            s["win_pnl"].append(pnl)
        elif pnl < 0:
            s["losses"] += 1
            s["loss_pnl"].append(abs(pnl))

    response = []

    for strategy, s in stats.items():
        win_rate = (s["wins"] / s["trades"]) * 100 if s["trades"] else 0
        avg_rr = (
            (sum(s["win_pnl"]) / len(s["win_pnl"])) /
            (sum(s["loss_pnl"]) / len(s["loss_pnl"]))
            if s["win_pnl"] and s["loss_pnl"] else 0
        )

        response.append({
            "strategy": strategy,
            "trades": s["trades"],
            "total_pnl": round(s["total_pnl"], 2),
            "win_rate": round(win_rate, 2),
            "avg_rr": round(avg_rr, 2)
        })

    return response
