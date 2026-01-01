# app/routes/csv_import_routes.py

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

# ==================================================
# CONSTANTS
# ==================================================

REQUIRED_HEADERS = {
    "time",
    "b/s",
    "name",
    "qty/lot",
    "avg price",
}

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

# ==================================================
# HELPERS
# ==================================================

def safe_float(val, default=0.0):
    try:
        if pd.isna(val):
            return default
        return float(str(val).strip())
    except Exception:
        return default


def parse_qty_lot(val) -> int:
    try:
        if pd.isna(val):
            return 0
        return int(str(val).split("/")[0])
    except Exception:
        return 0


def parse_side(val) -> Optional[str]:
    if pd.isna(val):
        return None
    v = str(val).strip().upper()
    if v == "B":
        return "BUY"
    if v == "S":
        return "SELL"
    return None


def extract_date_from_sheet(df: pd.DataFrame) -> date:
    """
    Extracts date from:
    'Executed Orders on 24-12-2025'
    """
    pattern = re.compile(r"(\d{1,2}-\d{1,2}-\d{4})")
    for i in range(10):
        for cell in df.iloc[i].astype(str):
            m = pattern.search(cell)
            if m:
                return datetime.strptime(m.group(1), "%d-%m-%Y").date()
    return datetime.utcnow().date()


def find_dhan_header_row(df: pd.DataFrame) -> Optional[int]:
    """
    Finds row that contains ALL required Dhan headers
    """
    for i in range(30):
        row = [
            str(x).strip().lower()
            for x in df.iloc[i].tolist()
            if pd.notna(x)
        ]
        if REQUIRED_HEADERS.issubset(set(row)):
            return i
    return None


def parse_option_symbol(name: str, sheet_date: date):
    parts = name.split()
    underlying = parts[0]

    option_type = None
    strike = None
    expiry = None

    for p in parts:
        if p.upper() in ("CE", "PE"):
            option_type = p.upper()
        if p.isdigit():
            strike = int(p)

    if len(parts) >= 3:
        try:
            day = int(parts[1])
            mon = MONTHS.get(parts[2][:3].upper())
            if mon:
                expiry = datetime.strptime(
                    f"{day:02d}-{mon}-{sheet_date.year}",
                    "%d-%m-%Y"
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
# ROUTE
# ==================================================

@router.post("/trades")
async def import_csv_trades(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await file.read()

        # -------- Load raw file --------
        try:
            raw_df = pd.read_excel(io.BytesIO(data), header=None)
        except Exception:
            raw_df = pd.read_csv(io.BytesIO(data), header=None, encoding="latin1")

        if raw_df.empty:
            return {"inserted": 0, "fetched": 0, "preview": []}

        # -------- Sheet Date --------
        sheet_date = extract_date_from_sheet(raw_df)

        # -------- Header Row --------
        header_idx = find_dhan_header_row(raw_df)
        if header_idx is None:
            raise HTTPException(
                400,
                "Dhan header row not found. Ensure this is Executed Orders file."
            )

        # -------- Load table --------
        try:
            table = pd.read_excel(io.BytesIO(data), header=header_idx)
        except Exception:
            table = pd.read_csv(io.BytesIO(data), header=header_idx, encoding="latin1")

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
            if side is None:
                continue

            quantity = parse_qty_lot(row.get("Qty/Lot"))
            price = safe_float(row.get("Avg Price"))

            # Trade time
            trade_time = datetime.combine(sheet_date, datetime.min.time())
            if not pd.isna(row.get("Time")):
                try:
                    t = pd.to_datetime(row["Time"])
                    trade_time = datetime.combine(sheet_date, t.time())
                except Exception:
                    pass

            parsed = parse_option_symbol(str(name), sheet_date)
            symbol_text = parsed["symbol_text"]

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

            # -------- Strategy --------
            temp_trade = Trade(
                symbol=symbol_text,
                side=side,
                quantity=quantity,
                price=price,
                trade_time=trade_time,
            )

            strategy = detect_strategy(
                temp_trade,
                context={
                    "option_type": parsed.get("option_type"),
                    "expiry": parsed.get("expiry"),
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
                "suggested_strategy": strategy["strategy"],
                "strategy_confidence": strategy["confidence"],
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
                "strategy": strategy["strategy"],
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
