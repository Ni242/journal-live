from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from collections import defaultdict
from decimal import Decimal

from ..deps import get_db
from ..models import Trade
from ..services.pnl_engine import get_lot_size
from ..services.charges_engine import calculate_charges

router = APIRouter(prefix="/analytics/strategy-pnl", tags=["analytics"])


@router.get("/")
async def strategy_pnl(db: AsyncSession = Depends(get_db)):
    trades = (await db.execute(select(Trade))).scalars().all()

    stats = defaultdict(lambda: {
        "gross": Decimal(0),
        "charges": Decimal(0),
        "pnl": Decimal(0),
        "trades": 0
    })

    daily_buy = defaultdict(Decimal)
    daily_sell = defaultdict(Decimal)

    # ---------- First pass: turnover ----------
    for t in trades:
        if not t.trade_time or not t.symbol:
            continue

        d = t.trade_time.date()
        qty = Decimal(t.quantity or 0)
        price = Decimal(t.price or 0)
        lot = get_lot_size(t.symbol)
        value = qty * price * lot

        if t.side == "BUY":
            daily_buy[d] += value
        elif t.side == "SELL":
            daily_sell[d] += value

    daily_charges = {
        d: Decimal(str(calculate_charges(daily_buy[d], daily_sell[d])["total"]))
        for d in daily_buy.keys() | daily_sell.keys()
    }

    # ---------- Second pass: strategy pnl ----------
    for t in trades:
        strategy = t.final_strategy or t.suggested_strategy or "Unclassified"
        d = t.trade_time.date()

        qty = Decimal(t.quantity or 0)
        price = Decimal(t.price or 0)
        lot = get_lot_size(t.symbol)
        value = qty * price * lot

        if t.side == "BUY":
            stats[strategy]["gross"] -= value
        elif t.side == "SELL":
            stats[strategy]["gross"] += value

        stats[strategy]["trades"] += 1

        # distribute daily charges proportionally
        day_total = daily_buy[d] + daily_sell[d]
        if day_total > 0:
            portion = value / day_total
            stats[strategy]["charges"] += daily_charges[d] * portion

    # ---------- Final result ----------
    output = []
    for s, v in stats.items():
        net = v["gross"] - v["charges"]
        output.append({
            "strategy": s,
            "pnl": float(round(net, 2)),
            "trades": v["trades"]
        })

    return sorted(output, key=lambda x: x["pnl"], reverse=True)
