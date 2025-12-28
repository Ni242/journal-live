from collections import defaultdict
from decimal import Decimal

LOT_SIZES = {
    "NIFTY": Decimal(75),
    "BANKNIFTY": Decimal(15),
    "FINNIFTY": Decimal(40),
    "SENSEX": Decimal(20),
}

def get_lot_size(symbol: str) -> Decimal:
    if not symbol:
        return Decimal(1)

    symbol = symbol.upper()
    for key, size in LOT_SIZES.items():
        if key in symbol:
            return size

    return Decimal(1)


def calculate_positions(trades):
    """
    Calculates REALIZED positions from executed trades.
    Returns BOTH points and ₹ amount.
    """

    positions = defaultdict(lambda: {
        "buy_qty": Decimal(0),
        "sell_qty": Decimal(0),
        "buy_value": Decimal(0),
        "sell_value": Decimal(0),
    })

    # ===============================
    # BUILD POSITION LEDGER
    # ===============================
    for t in trades:
        qty = Decimal(t.quantity or 0)
        price = Decimal(t.price or 0)

        if t.side == "BUY":
            positions[t.symbol]["buy_qty"] += qty
            positions[t.symbol]["buy_value"] += qty * price
        elif t.side == "SELL":
            positions[t.symbol]["sell_qty"] += qty
            positions[t.symbol]["sell_value"] += qty * price

    result = []

    # ===============================
    # CALCULATE P&L
    # ===============================
    for symbol, p in positions.items():
        traded_qty = min(p["buy_qty"], p["sell_qty"])
        if traded_qty == 0:
            continue

        avg_buy = p["buy_value"] / p["buy_qty"] if p["buy_qty"] else Decimal(0)
        avg_sell = p["sell_value"] / p["sell_qty"] if p["sell_qty"] else Decimal(0)

        pnl_points = avg_sell - avg_buy
        lot_size = get_lot_size(symbol)

        pnl_amount = pnl_points * lot_size * traded_qty

        net_qty = p["buy_qty"] - p["sell_qty"]

        result.append({
            "symbol": symbol,
            "net_qty": int(net_qty),
            "lots": int(traded_qty),
            "lot_size": int(lot_size),
            "avg_price": float(round(avg_buy, 2)),
            "realized_pnl_points": float(round(pnl_points, 2)),
            "realized_pnl_amount": float(round(pnl_amount, 2)),
        })

    return result
