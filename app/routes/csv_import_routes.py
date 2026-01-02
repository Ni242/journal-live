# app/routes/csv_import_routes.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.deps import get_db
from app.crud import create_trade
from app.models import Trade
from app.services.strategy_engine import detect_strategy

import pandas as pd
import io
import re
from datetime import datetime, date
from typing import Optional

router = APIRouter(prefix="/import/csv", tags=["csv-import"])

# ==================================================
# SAFE LOADERS
# ==================================================

def safe_read_csv(data: bytes) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(data),
        engine="python",
        sep=None,
        header=None,
        encoding_errors="ignore",
        on_bad_lines="skip",
        quoting=3,
    )


def safe_read_excel(data: bytes) -> pd.DataFrame:
    return pd.read_excel(
        io.BytesIO(data),
        header=None,
        engine="openpyxl"
    )

# ==================================================
# HEADER DETECTION (FIX)
# ==================================================

REQUIRED_COLS = {
    "time",
    "name",
    "qty",
    "quantity",
    "avg price",
    "price",
    "b/s",
    "side",
}

def find_header_row_index(df: pd.DataFrame) -> Optional[int]:
    """
    Find the row that looks like a trade table header
    """
    for i in range(min(80, len(df))):
        row = [str(x).strip().lower() for x in df.iloc[i].tolist()]
        hits = sum(any(req in cell for cell in row) for req in REQUIRED_COLS)
        if hits >= 3:
            return i
    return None

# ==================================================
# HELPERS
# ==================================================

def safe_float(val, default=0.0) -> float:
    try:
        if val is None:
            return default
        s = str(val).strip().lower()
        if s in ("", "market", "--", "nan"):
            return default
        return float(s)
    except Exception:
        return default


def parse_qty(val) -> int:
    try:
        if pd.isna(val):
            return 0
        s = str(val).split("/")[0]
        return int(float(s))
    except Exception:
        return 0


def parse_side(val) -> Optional[str]:
    if pd.isna(val):
        return None
    v = str(val).upper()
    if "BUY" in v or v == "B":
        return "BUY"
    if "SELL" in v or v == "S":
        return "SELL"
    return None


def parse_option_symbol(name: str, sheet_date: date):
    parts = str(name).split()
    underlying = parts[0] if parts else name

    option_type = None
    strike = None
    expiry = None

    for p in parts:
        if p.upper() in ("CE", "PE", "CALL", "PUT"):
            option_type = p.upper()
        if p.isdigit():
            strike = int(p)

    return {
        "symbol_text": name,
        "underlying": underlying,
        "expiry": expiry,
        "strike": strike,
        "option_type": option_type,
    }


def clean(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return str(val)

# ==================================================
# ROUTE
# ==================================================

@router.post("/trades")
async def import_csv_trades(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    data = await file.read()
    filename = file.filename.lower()

    try:
        # ---------- RAW LOAD ----------
        if filename.endswith(".xlsx"):
            raw_df = safe_read_excel(data)
        elif filename.endswith(".csv"):
            raw_df = safe_read_csv(data)
        else:
            raise HTTPException(400, "Upload CSV or Excel file")

        if raw_df.empty:
            raise HTTPException(400, "File is empty")

        # ---------- HEADER ----------
        header_idx = find_header_row_index(raw_df)
        if header_idx is None:
            raise HTTPException(400, "Dhan header row not found")

        # ---------- FINAL TABLE ----------
        if filename.endswith(".xlsx"):
            table = pd.read_excel(
                io.BytesIO(data),
                header=header_idx,
                engine="openpyxl"
            )
        else:
            table = pd.read_csv(
                io.BytesIO(data),
                header=header_idx,
                engine="python",
                sep=None,
                encoding_errors="ignore",
                on_bad_lines="skip",
            )

        table.columns = [str(c).strip().lower() for c in table.columns]

        inserted = 0
        fetched = 0
        preview = []

        for _, row in table.iterrows():
            fetched += 1

            name = row.get("name")
            if pd.isna(name):
                continue

            side = parse_side(row.get("b/s") or row.get("side"))
            if side is None:
                continue

            quantity = parse_qty(row.get("qty/lot") or row.get("qty") or row.get("quantity"))
            price = safe_float(row.get("avg price") or row.get("price"))

            trade_time = datetime.utcnow()
            if "time" in row and not pd.isna(row["time"]):
                try:
                    t = pd.to_datetime(row["time"])
                    trade_time = t.to_pydatetime()
                except Exception:
                    pass

            parsed = parse_option_symbol(str(name), trade_time.date())
            symbol_text = parsed["symbol_text"]

            # ---------- DEDUP ----------
            q = select(Trade).where(
                and_(
                    Trade.symbol == symbol_text,
                    Trade.trade_time == trade_time,
                    Trade.side == side,
                    Trade.quantity == quantity,
                    Trade.price == price,
                )
            )
            if (await db.execute(q)).scalar_one_or_none():
                continue

            strategy = detect_strategy(
                Trade(
                    symbol=symbol_text,
                    side=side,
                    quantity=quantity,
                    price=price,
                    trade_time=trade_time,
                ),
                context={"option_type": parsed.get("option_type")}
            )

            payload = {
                "symbol": symbol_text,
                "side": side,
                "quantity": quantity,
                "price": price,
                "trade_time": trade_time,
                "fees": 0,
                "suggested_strategy": strategy["strategy"],
                "strategy_confidence": strategy["confidence"],
                "strategy_source": "AI",
                "raw": {k: clean(v) for k, v in row.items() if pd.notna(v)},
            }

            await create_trade(db, **payload)
            inserted += 1

            preview.append({
                "symbol": symbol_text,
                "side": side,
                "qty": quantity,
                "price": price,
            })

        return {
            "inserted": inserted,
            "fetched": fetched,
            "preview": preview[:20],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"CSV import failed: {str(e)}")
