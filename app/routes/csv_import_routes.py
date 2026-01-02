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
# SAFE LOADERS (NO PARSER CRASH)
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
# HEADER DETECTION — DHAN SAFE
# ==================================================

HEADER_KEYWORDS = [
    "time",
    "name",
    "qty",
    "quantity",
    "price",
    "avg",
    "b/s",
    "side",
]

def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())

def find_header_row_index(df: pd.DataFrame) -> Optional[int]:
    for i in range(min(100, len(df))):
        cells = [normalize(str(c)) for c in df.iloc[i].tolist()]
        hits = 0
        for key in HEADER_KEYWORDS:
            if any(key.replace("/", "") in c for c in cells):
                hits += 1
        if hits >= 4:   # 🔥 THIS IS THE MAGIC
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

def parse_option_symbol(name: str, trade_date: date):
    parts = str(name).split()
    underlying = parts[0] if parts else name

    option_type = None
    strike = None

    for p in parts:
        if p.upper() in ("CE", "PE", "CALL", "PUT"):
            option_type = p.upper()
        if p.isdigit():
            strike = int(p)

    return {
        "symbol_text": name,
        "underlying": underlying,
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
    name = file.filename.lower()

    # ---------- RAW LOAD ----------
    if name.endswith(".xlsx"):
        raw_df = safe_read_excel(data)
    elif name.endswith(".csv"):
        raw_df = safe_read_csv(data)
    else:
        raise HTTPException(400, "Upload CSV or Excel file")

    if raw_df.empty:
        raise HTTPException(400, "File is empty")

    # ---------- FIND HEADER ----------
    header_idx = find_header_row_index(raw_df)
    if header_idx is None:
        raise HTTPException(400, "Dhan header row not found")

    # ---------- FINAL TABLE ----------
    if name.endswith(".xlsx"):
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

    table.columns = [normalize(c) for c in table.columns]

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

        qty = parse_qty(row.get("qty/lot") or row.get("qty") or row.get("quantity"))
        price = safe_float(row.get("avgprice") or row.get("price"))

        trade_time = datetime.utcnow()
        if "time" in row and not pd.isna(row["time"]):
            try:
                trade_time = pd.to_datetime(row["time"]).to_pydatetime()
            except Exception:
                pass

        parsed = parse_option_symbol(str(name), trade_time.date())

        # ---------- DEDUP ----------
        q = select(Trade).where(
            and_(
                Trade.symbol == parsed["symbol_text"],
                Trade.trade_time == trade_time,
                Trade.side == side,
                Trade.quantity == qty,
                Trade.price == price,
            )
        )
        if (await db.execute(q)).scalar_one_or_none():
            continue

        strategy = detect_strategy(
            Trade(
                symbol=parsed["symbol_text"],
                side=side,
                quantity=qty,
                price=price,
                trade_time=trade_time,
            ),
            context={"option_type": parsed.get("option_type")}
        )

        await create_trade(
            db,
            symbol=parsed["symbol_text"],
            side=side,
            quantity=qty,
            price=price,
            trade_time=trade_time,
            fees=0,
            suggested_strategy=strategy["strategy"],
            strategy_confidence=strategy["confidence"],
            strategy_source="AI",
            raw={k: clean(v) for k, v in row.items() if pd.notna(v)},
        )

        inserted += 1
        preview.append({
            "symbol": parsed["symbol_text"],
            "side": side,
            "qty": qty,
            "price": price,
        })

    return {
        "inserted": inserted,
        "fetched": fetched,
        "preview": preview[:20],
    }
