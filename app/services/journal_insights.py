def generate_insights(trades):
    insights = []

    by_strategy = {}
    for t in trades:
        pnl = float(t.price * t.quantity)
        if t.side == "SELL":
            pnl = -pnl
        by_strategy.setdefault(t.final_strategy, 0)
        by_strategy[t.final_strategy] += pnl

    worst = min(by_strategy, key=by_strategy.get)
    insights.append(f"⚠️ {worst} strategy loses the most money")

    return insights
