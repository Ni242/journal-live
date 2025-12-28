from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    JSON,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

# ==================================================
# Trades Table (CORE)
# ==================================================
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)

    dh_order_id = Column(
        String,
        unique=True,
        index=True,
        nullable=True
    )

    symbol = Column(
        String,
        index=True,
        nullable=False
    )

    side = Column(
        String,
        nullable=False
    )  # BUY / SELL

    quantity = Column(
        Integer,
        nullable=False
    )

    price = Column(
        Numeric(10, 2),
        nullable=False
    )

    trade_time = Column(
        DateTime,
        default=datetime.utcnow,
        index=True
    )

    # ===============================
    # 💰 PnL SYSTEM
    # ===============================
    realized_pnl = Column(
        Numeric(12, 2),
        nullable=True
    )

    fees = Column(
        Numeric(10, 2),
        default=0
    )

    # ===============================
    # 🧠 STRATEGY SYSTEM
    # ===============================
    suggested_strategy = Column(
        String,
        index=True,
        nullable=True
    )

    strategy_confidence = Column(
        Integer,
        nullable=True
    )

    final_strategy = Column(
        String,
        index=True,
        nullable=True
    )

    strategy_source = Column(
        String,
        default="AI",
        nullable=False
    )

    notes = Column(
        Text,
        nullable=True
    )

    raw = Column(
        JSON,
        nullable=True
    )

    # ===============================
    # HELPERS
    # ===============================
    @property
    def effective_strategy(self):
        return self.final_strategy or self.suggested_strategy

    @property
    def net_pnl(self):
        if self.realized_pnl is None:
            return None
        return float(self.realized_pnl) - float(self.fees or 0)

    def __repr__(self):
        return (
            f"<Trade {self.symbol} "
            f"{self.side} qty={self.quantity} "
            f"strategy={self.effective_strategy} "
            f"pnl={self.realized_pnl}>"
        )


# ==================================================
# Positions Table (OPTIONAL / SNAPSHOT)
# ==================================================
class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)

    symbol = Column(
        String,
        index=True,
        nullable=False
    )

    net_qty = Column(
        Integer,
        nullable=False
    )

    avg_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    realized_pnl = Column(
        Numeric(12, 2),
        default=0
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow
    )


# ==================================================
# Greeks Snapshot Table
# ==================================================
class GreeksSnapshot(Base):
    __tablename__ = "greeks_snapshot"

    id = Column(Integer, primary_key=True)

    symbol = Column(
        String,
        index=True,
        nullable=False
    )

    delta = Column(Numeric(10, 4))
    gamma = Column(Numeric(10, 6))
    theta = Column(Numeric(10, 4))
    vega = Column(Numeric(10, 4))
    iv = Column(Numeric(10, 4))

    timestamp = Column(
        DateTime,
        default=datetime.utcnow
    )


# ==================================================
# ✅ ACCOUNT SETTINGS (EDITABLE CAPITAL)
# ==================================================
class AccountSettings(Base):
    """
    Single-row table to store account-level settings
    (capital, later risk limits, etc.)
    """
    __tablename__ = "account_settings"

    id = Column(Integer, primary_key=True)

    capital = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


# ==================================================
# 🔥 PERFORMANCE INDEXES
# ==================================================
Index(
    "idx_trade_strategy_date",
    Trade.final_strategy,
    Trade.trade_time
)

# ==================================================
# ✅ ACCOUNT SETTINGS (Editable Capital – SINGLE ROW)
# ==================================================

