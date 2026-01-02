from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.deps import get_db
from app.crud import create_trade
from app.models import Trade

import pandas as pd
import io
import re
from datetime import datetime, date
from typing import Optional

from app.services.strategy_engine import detect_strategy

router = APIRouter(prefix="/import/csv", tags=["csv-import"])

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

# =====================================================
# HELPERS
# =====================================================

def is_excel_bytes(data: bytes) -> bool:
    # XLSX files always start with PK\x03\x04
    return data[:2] == b"PK"

def safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        s = str(val).strip().lower()
        if s in ("", "market", "--", "nan"):
            return default
        return float(s)
    except Exception:
        return default

def parse_qty(val):
    try:
        if pd.isna(val):
            return 0
        s = str(val).split("/")[0]
        return int(float(s))
    except Exception:
        return 0

def parse_side(val):
    if pd.isna(val):
        return None
    v = str(val).upper()
    if "BUY" in v or v == "B":
        return "BUY"
    if "SELL" in v or v == "S":
        return "SELL"
    return None

def normalize(col: str) -> str:
    return col.lower().replace(" ", "").replace("/", "")

def find_dhan_header(df: pd.DataFrame) -> int:
    REQUIRED = {
        "time",
        "bs",
        "name",
        "qtylot",
        "avgprice",
    }

    for i in range(min(50, len(df))):
        row = [normalize(str(x)) for x in df.iloc[i].tolist()]
        matches = sum(any(req in cell for cell in row) for req in REQUIRED)

        # 🔥 If at least 3 core columns found → header row
        if matches >= 3:
            return i

    raise HTTPException(400, "Dhan header row not found")


def extract_date(df: pd.DataFrame) -> date:
    pattern = re.compile(r"(\d{1,2}-\d{1,2}-\d{4})")
    for i in range(min(20, len(df))):
        for cell in df.iloc[i].astype(str):
            m = pattern.search(cell)
            if m:
                return datetime.strptime(m.group(1), "%d-%m-%Y").date()
    return datetime.utcnow().date()

# =====================================================
# ROUTE
# =====================================================

@router.post("/trades")
async def import_csv_trades(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()

    # 🔥 CRITICAL: detect real file type
    try:
        if is_excel_bytes(data):
            raw_df = pd.read_excel(io.BytesIO(data), header=None, engine="openpyxl")
            table_reader = lambda h: pd.read_excel(
                io.BytesIO(data), header=h, engine="openpyxl"
            )
        else:
            raw_df = pd.read_csv(
                io.BytesIO(data),
                header=None,
                engine="python",
                encoding_errors="ignore",
                on_bad_lines="skip",
            )
            table_reader = lambda h: pd.read_csv(
                io.BytesIO(data),
                header=h,
                engine="python",
                encoding_errors="ignore",
                on_bad_lines="skip",
            )
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}")

    if raw_df.empty:
        return {"inserted": 0, "fetched": 0, "preview": []}

    sheet_date = extract_date(raw_df)
    header_idx = find_dhan_header(raw_df)

    table = table_reader(header_idx)
    table.columns = [str(c).strip() for c in table.columns]

    inserted = 0
    fetched = 0
    preview = []

    for _, row in table.iterrows():
        fetched += 1

        name = row.get("Name")
        if pd.isna(name):
            continue

        side = parse_side(row.get("B/S"))
        if not side:
            continue

        qty = parse_qty(row.get("Qty/Lot"))
        price = safe_float(row.get("Avg Price"))

        trade_time = datetime.combine(sheet_date, datetime.min.time())
        if "Time" in row and not pd.isna(row["Time"]):
            try:
                t = pd.to_datetime(row["Time"])
                trade_time = datetime.combine(sheet_date, t.time())
            except Exception:
                pass

        # Dedup
        q = select(Trade).where(
            and_(
                Trade.symbol == name,
                Trade.trade_time == trade_time,
                Trade.side == side,
                Trade.quantity == qty,
                Trade.price == price,
            )
        )
        if (await db.execute(q)).scalar_one_or_none():
            continue

        temp_trade = Trade(
            symbol=name,
            side=side,
            quantity=qty,
            price=price,
            trade_time=trade_time,
        )

        strategy = detect_strategy(temp_trade)

        await create_trade(
            db,
            dh_order_id=None,
            symbol=name,
            side=side,
            quantity=qty,
            price=price,
            trade_time=trade_time,
            fees=0,
            suggested_strategy=strategy["strategy"],
            strategy_confidence=strategy["confidence"],
            final_strategy=None,
            strategy_source="AI",
            notes=None,
            raw=row.dropna().to_dict(),
        )

        inserted += 1
        preview.append({
            "symbol": name,
            "side": side,
            "qty": qty,
            "price": price,
            "strategy": strategy["strategy"],
        })

    return {
        "inserted": inserted,
        "fetched": fetched,
        "preview": preview[:50],
    }
