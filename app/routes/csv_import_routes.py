# app/routes/csv_import_routes.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from ..deps import get_db
from ..crud import create_trade
from ..models import Trade

import pandas as pd
import io
import re
from datetime import datetime
from typing import Optional

# 🔥 AUTO STRATEGY ENGINE
from app.services.strategy_engine import detect_strategy


router = APIRouter(prefix="/import/csv", tags=["csv-import"])

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}


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


def extract_date_from_header(df: pd.DataFrame) -> Optional[str]:
    pattern = re.compile(r"Executed\s+Orders\s+on\s+(\d{1,2}-\d{1,2}-\d{4})", flags=re.I)
    for i in range(min(30, len(df))):
        row = df.iloc[i].astype(str).tolist()
        for cell in row:
            m = pattern.search(cell)
            if m:
                return m.group(1)
    return None


def find_header_row_index(df: pd.DataFrame) -> Optional[int]:
    for i in range(min(50, len(df))):
        row_vals = [str(x).strip().lower() for x in df.iloc[i].tolist()]
        if "time" in row_vals:
            return i
    return None


def parse_qty_lot(val) -> int:
    if pd.isna(val):
        return 0
    s = str(val).strip()
    if "/" in s:
        s = s.split("/")[0]
    try:
        return int(float(s))
    except Exception:
        return 0


def parse_side(val) -> Optional[str]:
    if pd.isna(val):
        return None
    v = str(val).strip().upper()
    if v in ("B", "BUY", "B/S (B)"):
        return "BUY"
    if v in ("S", "SELL", "B/S (S)"):
        return "SELL"
    if "BUY" in v:
        return "BUY"
    if "SELL" in v:
        return "SELL"
    return None


def parse_option_symbol(name: str, sheet_date: datetime):
    if not isinstance(name, str):
        return {"symbol_text": str(name)}

    parts = name.strip().split()
    underlying = parts[0] if parts else None

    option_type = None
    strike = None
    expiry = None

    for p in parts:
        if p.upper() in ("CALL", "PUT", "CE", "PE"):
            option_type = p.upper()
        if re.fullmatch(r"\d+", p):
            strike = int(p)

    if len(parts) >= 3:
        try:
            day = int(parts[1])
            mon = MONTHS.get(parts[2][:3].upper())
            if mon:
                expiry = datetime.strptime(
                    f"{day:02d}-{mon}-{sheet_date.year}", "%d-%m-%Y"
                ).date()
        except Exception:
            pass

    return {
        "symbol_text": name,
        "underlying": underlying,
        "expiry": expiry,
        "strike": strike,
        "option_type": option_type,
    }


# ==================================================
# CSV IMPORT ROUTE
# ==================================================

@router.post("/trades")
async def import_csv_trades(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await file.read()

        # -------- Read file --------
        try:
            df = pd.read_excel(io.BytesIO(data), header=None, engine="openpyxl")
        except Exception:
            df = pd.read_csv(io.BytesIO(data), header=None, low_memory=False)

        if df.empty:
            return {"inserted": 0, "fetched": 0, "preview": []}

        # -------- Sheet Date --------
        date_str = extract_date_from_header(df)
        sheet_date = (
            datetime.strptime(date_str, "%d-%m-%Y").date()
            if date_str else datetime.utcnow().date()
        )

        # -------- Header Row --------
        header_idx = find_header_row_index(df)
        if header_idx is None:
            raise HTTPException(400, "Header row with 'Time' not found")

        table = pd.read_excel(io.BytesIO(data), header=header_idx, engine="openpyxl")
        table.columns = [str(c).strip() for c in table.columns]

        preview = []
        inserted = 0
        fetched = 0

        for _, row in table.iterrows():
            fetched += 1

            name = row.get("Name")
            if pd.isna(name):
                continue

            # -------- Trade Time --------
            trade_time = datetime.combine(sheet_date, datetime.min.time())
            if "Time" in row and not pd.isna(row["Time"]):
                try:
                    t = pd.to_datetime(row["Time"])
                    trade_time = datetime.combine(sheet_date, t.time())
                except Exception:
                    pass

            quantity = parse_qty_lot(row.get("Qty/Lot"))
            price = safe_float(row.get("Avg Price"))
            side = parse_side(row.get("B/S"))

            parsed_symbol = parse_option_symbol(str(name), sheet_date)
            symbol_text = parsed_symbol["symbol_text"]

            # -------- Dedup --------
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

            # -------- AUTO STRATEGY --------
            temp_trade = Trade(
                symbol=symbol_text,
                side=side,
                quantity=quantity,
                price=price,
                trade_time=trade_time
            )

            strategy_result = detect_strategy(
                temp_trade,
                context={
                    "option_type": parsed_symbol.get("option_type"),
                    "expiry": parsed_symbol.get("expiry"),
                }
            )

            payload = {
                "dh_order_id": None,
                "symbol": symbol_text,
                "side": side,
                "quantity": quantity,
                "price": price,
                "trade_time": trade_time,
                "fees": 0,

                # STRATEGY
                "suggested_strategy": strategy_result["strategy"],
                "strategy_confidence": strategy_result["confidence"],
                "final_strategy": None,
                "strategy_source": "AI",
                "notes": None,

                "raw": row.dropna().to_dict(),
            }

            await create_trade(db, **payload)
            inserted += 1

            preview.append({
                "symbol": symbol_text,
                "side": side,
                "qty": quantity,
                "price": price,
                "strategy": strategy_result["strategy"],
                "confidence": strategy_result["confidence"],
            })

        return {
            "inserted": inserted,
            "fetched": fetched,
            "preview": preview[:50],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
