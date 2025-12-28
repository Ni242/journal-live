from decimal import Decimal

# ===============================
# CHARGE CONSTANTS (INDIA F&O)
# ===============================
BROKERAGE_PER_ORDER = Decimal("20")
EXCHANGE_CHARGE_RATE = Decimal("0.00053")  # NSE F&O approx
SEBI_CHARGE_RATE = Decimal("0.000001")
GST_RATE = Decimal("0.18")
STAMP_RATE = Decimal("0.00003")


def calculate_charges(buy_turnover: Decimal, sell_turnover: Decimal):
    """
    Calculate full brokerage & statutory charges
    """
    turnover = buy_turnover + sell_turnover

    # Brokerage (₹20 per side if executed)
    brokerage = Decimal(0)
    if buy_turnover > 0:
        brokerage += BROKERAGE_PER_ORDER
    if sell_turnover > 0:
        brokerage += BROKERAGE_PER_ORDER

    exchange_charges = turnover * EXCHANGE_CHARGE_RATE
    sebi_charges = turnover * SEBI_CHARGE_RATE
    stamp_duty = buy_turnover * STAMP_RATE  # buy side only

    gst = (brokerage + exchange_charges) * GST_RATE

    total_charges = (
        brokerage +
        exchange_charges +
        sebi_charges +
        stamp_duty +
        gst
    )

    return {
        "brokerage": round(brokerage, 2),
        "exchange": round(exchange_charges, 2),
        "sebi": round(sebi_charges, 2),
        "stamp": round(stamp_duty, 2),
        "gst": round(gst, 2),
        "total": round(total_charges, 2)
    }
