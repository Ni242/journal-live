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

REQUIRED_HEADERS = {"time", "b/s", "name", "qty/lot", "avg price"}

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

# ==================================================
# SAFE CSV READER (FIXES TOKENIZING ERROR)
# ==================================================

def safe_read_csv(data: bytes, header=None):
    return pd.read_csv(
        io.BytesIO(data),
        header=header,
        sep=None,
        engine="python",
        encoding="latin1",
        on_bad_lines="skip",
    )

# ==================================================
# HELPERS
# ==================================================

def safe_float(val, default=0.0):
    try:
        return float(str(val).strip())
    except Exception:
        return default


def parse_qty_lot(val):
    try:
        return int(str(val).split("/")[0])
    except Exception:
        return 0


def parse_side(val):
    if not isinstance(val, str):
        return None
    v = val.strip().upper()
    return "BUY" if v == "B" else "SELL" if v == "S" else None


def extract_date(df):
    for i in range(10):
        for cell in df.iloc[i].astype(str):
            m = re.search(r"\d{1,2}-\d{1,2}-\d{4}", cell)
            if m:
                return datetime.strptime(m.group(), "%d-%m-%Y").date()
    return datetime.utcnow().date()


def find_header_row(df):
    for i in range(30):
        row = [str(x).lower().strip() for x in df.iloc[i] if pd.notna(x)]
        if REQUIRED_HEADERS.issubset(set(row)):
            return i
    return None


def parse_option_symbol(name, sheet_date):
    parts = name.split()
    underlying = parts[0]
    option_type = None
    strike = None
    expiry = None

    for p in parts:
        if p in ("CE", "PE"):
            option_type = p
        if p.isdigit():
            strike = int(p)

    if len(parts) >= 3:
        try:
            expiry = datetime.strptime(
                f"{parts[1]}-{MONTHS[parts[2][:3]]}-{sheet_date.year}",
                "%d-%m-%Y"
            ).date()
        except Exception:
            pass

    return {
        "symbol_text": name,
        "option_type": option_type,
        "expiry": expiry,
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

        # -------- RAW LOAD --------
        try:
            raw_df = pd.read_excel(io.BytesIO(data), header=None)
        except Exception:
            raw_df = safe_read_csv(data, header=None)

        sheet_date = extract_date(raw_df)

        header_idx = find_header_row(raw_df)
        if header_idx is None:
            raise HTTPException(400, "Dhan header row not found")

        try:
            table = pd.read_excel(io.BytesIO(data), header=header_idx)
        except Exception:
            table = safe_read_csv(data, header=header_idx)

        table.columns = [c.strip() for c in table.columns]

        inserted = 0
        preview = []

        for _, row in table.iterrows():
            name = row.get("Name")
            side = parse_side(row.get("B/S"))
            if not name or not side:
                continue

            qty = parse_qty_lot(row.get("Qty/Lot"))
            price = safe_float(row.get("Avg Price"))

            trade_time = datetime.combine(sheet_date, datetime.min.time())
            if row.get("Time"):
                try:
                    trade_time = datetime.combine(
                        sheet_date,
                        pd.to_datetime(row["Time"]).time()
                    )
                except Exception:
                    pass

            parsed = parse_option_symbol(name, sheet_date)

            exists = await db.execute(
                select(Trade).where(
                    and_(
                        Trade.symbol == name,
                        Trade.trade_time == trade_time,
                        Trade.side == side,
                        Trade.quantity == qty,
                        Trade.price == price,
                    )
                )
            )
            if exists.scalar_one_or_none():
                continue

            temp_trade = Trade(
                symbol=name,
                side=side,
                quantity=qty,
                price=price,
                trade_time=trade_time,
            )

            strategy = detect_strategy(
                temp_trade,
                context={
                    "option_type": parsed["option_type"],
                    "expiry": parsed["expiry"],
                }
            )

            await create_trade(
                db,
                symbol=name,
                side=side,
                quantity=qty,
                price=price,
                trade_time=trade_time,
                fees=0,
                suggested_strategy=strategy["strategy"],
                strategy_confidence=strategy["confidence"],
                strategy_source="AI",
                raw=row.dropna().to_dict(),
            )

            inserted += 1
            preview.append({
                "symbol": name,
                "side": side,
                "qty": qty,
                "price": price,
            })

        return {"inserted": inserted, "preview": preview[:20]}

    except Exception as e:
        raise HTTPException(500, f"CSV import failed: {str(e)}")
