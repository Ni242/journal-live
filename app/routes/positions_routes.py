from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from collections import defaultdict
from decimal import Decimal

from app.deps import get_db
from app.models import Trade
from app.services.pnl_engine import get_lot_size

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/")
async def get_realized_positions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Trade))
    trades = result.scalars().all()

    pos = defaultdict(lambda: {
        "buy_qty": Decimal(0),
        "sell_qty": Decimal(0),
        "buy_value": Decimal(0),
        "sell_value": Decimal(0),
        "lot_size": Decimal(1),
    })

    for t in trades:
        if not t.symbol or not t.side:
            continue

        qty = Decimal(t.quantity or 0)
        price = Decimal(t.price or 0)

        p = pos[t.symbol]
        p["lot_size"] = Decimal(get_lot_size(t.symbol) or 1)

        if t.side.upper() == "BUY":
            p["buy_qty"] += qty
            p["buy_value"] += qty * price
        elif t.side.upper() == "SELL":
            p["sell_qty"] += qty
            p["sell_value"] += qty * price

    output = []

    for symbol, p in pos.items():
        if p["buy_qty"] == 0 or p["sell_qty"] == 0:
            continue

        net_qty = p["buy_qty"] - p["sell_qty"]
        if net_qty != 0:
            continue

        avg_buy = p["buy_value"] / p["buy_qty"]
        avg_sell = p["sell_value"] / p["sell_qty"]

        pnl_points = avg_sell - avg_buy
        pnl_amount = pnl_points * p["lot_size"] * p["buy_qty"]

        output.append({
            "symbol": symbol,
            "net_qty": 0,
            "avg_price": float(avg_buy),
            "realized_pnl_points": float(pnl_points),
            "realized_pnl_amount": float(pnl_amount),
        })

    return output
