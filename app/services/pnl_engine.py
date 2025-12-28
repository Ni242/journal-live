from collections import defaultdict
from decimal import Decimal
from datetime import date
from .charges_engine import calculate_charges

# ===============================
# LOT SIZE CONFIG (INDIA F&O)
# ===============================
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
    for k, v in LOT_SIZES.items():
        if k in symbol:
            return v

    return Decimal(1)


# ===============================
# MAIN PnL ENGINE
# ===============================
def aggregate_pnl(trades, capital: Decimal):
    ledger = defaultdict(lambda: defaultdict(lambda: {
        "buy": Decimal(0),
        "sell": Decimal(0),
    }))

    daily_buy = defaultdict(Decimal)
    daily_sell = defaultdict(Decimal)

    # ===============================
    # TRADE LOOP
    # ===============================
    for t in trades:
        if not t.trade_time or not t.symbol:
            continue

        d = t.trade_time.date()
        qty = Decimal(t.quantity or 0)
        price = Decimal(t.price or 0)
        lot = get_lot_size(t.symbol)

        value = qty * price * lot

        if t.side == "BUY":
            ledger[d][t.symbol]["buy"] += value
            daily_buy[d] += value

        elif t.side == "SELL":
            ledger[d][t.symbol]["sell"] += value
            daily_sell[d] += value

    # ===============================
    # DAILY AGGREGATION
    # ===============================
    daily = []

    running_pnl = Decimal(0)
    equity = capital
    peak_equity = capital
    max_drawdown = Decimal(0)

    gross_total = Decimal(0)
    net_total = Decimal(0)
    charges_total = Decimal(0)

    for d in sorted(ledger):
        gross = sum(v["sell"] - v["buy"] for v in ledger[d].values())

        charges = calculate_charges(
            daily_buy[d],
            daily_sell[d]
        )
        charge_val = Decimal(str(charges["total"]))

        net = gross - charge_val

        # Totals
        gross_total += gross
        net_total += net
        charges_total += charge_val

        # Equity tracking
        running_pnl += net
        equity = capital + running_pnl
        peak_equity = max(peak_equity, equity)
        drawdown = equity - peak_equity
        max_drawdown = min(max_drawdown, drawdown)

        # ===============================
        # ✅ RISK % USED (NEW)
        # ===============================
        risk_pct = (
            abs(net) / capital * 100
            if capital > 0 else Decimal(0)
        )

        daily.append({
            "date": str(d),
            "gross_pnl": float(round(gross, 2)),
            "net_pnl": float(round(net, 2)),
            "equity": float(round(equity, 2)),
            "drawdown": float(round(drawdown, 2)),
            "charges": charges,

            # 🔥 NEW METRIC
            "risk_pct": float(round(risk_pct, 2)),
        })

    # ===============================
    # TIME FILTERS
    # ===============================
    if daily:
        last_date = date.fromisoformat(daily[-1]["date"])
    else:
        last_date = date.today()

    iso_year, iso_week, _ = last_date.isocalendar()
    month_key = last_date.strftime("%Y-%m")

    today_pnl = sum(
        Decimal(str(r["net_pnl"]))
        for r in daily
        if r["date"] == str(last_date)
    )

    week_pnl = sum(
        Decimal(str(r["net_pnl"]))
        for r in daily
        if date.fromisoformat(r["date"]).isocalendar()[:2] == (iso_year, iso_week)
    )

    month_pnl = sum(
        Decimal(str(r["net_pnl"]))
        for r in daily
        if r["date"].startswith(month_key)
    )

    remaining_capital = capital + net_total

    # ===============================
    # FINAL RESPONSE
    # ===============================
    return {
        "daily": daily,
        "summary": {
            "today": float(round(today_pnl, 2)),
            "this_week": float(round(week_pnl, 2)),
            "this_month": float(round(month_pnl, 2)),
            "gross_total": float(round(gross_total, 2)),
            "charges_total": float(round(charges_total, 2)),
            "net_total": float(round(net_total, 2)),
            "capital": float(round(capital, 2)),
            "remaining_capital": float(round(remaining_capital, 2)),
            "max_drawdown": float(round(max_drawdown, 2)),
        }
    }
