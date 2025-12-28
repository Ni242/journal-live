from datetime import time
from decimal import Decimal


# ===============================
# STRATEGY RULE ENGINE
# ===============================

def detect_strategy(trade, context=None):
    """
    Rule-based strategy detection engine.

    Returns:
    {
        "strategy": str,
        "confidence": int,
        "reason": str
    }
    """

    # -------------------------
    # SAFETY CHECKS
    # -------------------------
    if not trade or not trade.symbol or not trade.side:
        return _result("Unclassified", 0, "Invalid trade data")

    symbol = trade.symbol.upper()
    side = trade.side.upper()
    qty = int(trade.quantity or 0)
    price = Decimal(trade.price or 0)

    t = trade.trade_time.time() if trade.trade_time else None
    context = context or {}

    # -------------------------
    # 1️⃣ SCALPING
    # Small size + early market
    # -------------------------
    if t and time(9, 15) <= t <= time(9, 45):
        if qty <= 2:
            return _result(
                "Scalp",
                80,
                "Early market entry with small quantity"
            )

    # -------------------------
    # 2️⃣ HEDGE
    # Options + larger size
    # -------------------------
    if ("PE" in symbol or "CE" in symbol) and qty >= 4:
        return _result(
            "Hedge",
            75,
            "Options position with hedge-sized quantity"
        )

    # -------------------------
    # 3️⃣ BREAKOUT
    # -------------------------
    if context.get("above_day_high"):
        return _result(
            "Breakout",
            85,
            "Price broke above day high"
        )

    # -------------------------
    # 4️⃣ SUPPORT / RESISTANCE
    # -------------------------
    if context.get("near_support"):
        return _result(
            "Support Bounce",
            70,
            "Entry near support zone"
        )

    if context.get("near_resistance"):
        return _result(
            "Resistance Rejection",
            70,
            "Entry near resistance zone"
        )

    # -------------------------
    # 5️⃣ TREND FOLLOWING
    # -------------------------
    if context.get("trend") == "UP":
        return _result(
            "Trend Following",
            65,
            "Higher-highs / higher-lows structure"
        )

    if context.get("trend") == "DOWN":
        return _result(
            "Trend Following",
            65,
            "Lower-highs / lower-lows structure"
        )

    # -------------------------
    # 6️⃣ FALLBACK
    # -------------------------
    return _result(
        "Unclassified",
        30,
        "No strong rule matched"
    )


# ===============================
# HELPER
# ===============================

def _result(strategy, confidence, reason):
    return {
        "strategy": strategy,
        "confidence": confidence,
        "reason": reason
    }
