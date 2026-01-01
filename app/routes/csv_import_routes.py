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
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/import/csv", tags=["csv-import"])

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
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
    """
    Extract date from:
    Executed Orders on 24-12-2025
    """
    pattern = re.compile(r"Executed\s+Orders\s+on\s+(\d{1,2}-\d{1,2}-\d{4})", re.I)

    for i in range(min(40, len(df))):
        for cell in df.iloc[i].astype(str):
            match = pattern.search(cell)
            if match:
                return match.group(1)

    return None


def find_header_row_index(df: pd.DataFrame) -> Optional[int]:
    """
    Strict Dhan header detection
    """
    REQUIRED = {"time", "b/s", "name", "qty/lot", "avg price"}

    for i in range(min(60, len(df))):
        row = {str(x).strip().lower() for x in df.iloc[i].tolist()}
        if REQUIRED.issubset(row):
            return i

    return None


def parse_qty_lot(val) -> int:
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

    v = str(val).strip().upper()
    if v in ("B", "BUY", "B/S (B)") or "BUY" in v:
        return "BUY"
    if v in ("S", "SELL", "B/S (S)") or "SELL" in v:
        return "SELL"

    return None


def parse_option_symbol(name: str, sheet_date: datetime):
    parts = name.strip().split()
    underlying = parts[0] if parts else name

    option_type = None
    strike = None
    expiry = None

    for p in parts:
        if p.upper() in ("CE", "PE", "CALL", "PUT"):
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
# CSV / EXCEL IMPORT ROUTE
# ==================================================

@router.post("/trades")
async def import_csv_trades(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            400,
            "Please upload the Dhan Executed Orders Excel (.xlsx) file"
        )

    try:
        data = await file.read()

        # ---------- READ RAW EXCEL (NO CSV EVER) ----------
        df = pd.read_excel(
            io.BytesIO(data),
            header=None,
            engine="openpyxl"
        )

        if df.empty:
            return {"inserted": 0, "fetched": 0, "preview": []}

        # ---------- DATE ----------
        date_str = extract_date_from_header(df)
        sheet_date = (
            datetime.strptime(date_str, "%d-%m-%Y").date()
            if date_str else datetime.utcnow().date()
        )

        # ---------- HEADER ----------
        header_idx = find_header_row_index(df)
        if header_idx is None:
            raise HTTPException(400, "Dhan header row not found")

        table = pd.read_excel(
            io.BytesIO(data),
            header=header_idx,
            engine="openpyxl"
        )

        table.columns = [str(c).strip() for c in table.columns]

        inserted = 0
        fetched = 0
        preview = []

        # ---------- PROCESS ROWS ----------
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

            trade_time = datetime.combine(sheet_date, datetime.min.time())
            if "Time" in row and not pd.isna(row["Time"]):
                try:
                    t = pd.to_datetime(row["Time"])
                    trade_time = datetime.combine(sheet_date, t.time())
                except Exception:
                    pass

            parsed = parse_option_symbol(str(name), sheet_date)
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

            # ---------- STRATEGY ----------
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
                "raw": row.dropna().astype(str).to_dict(),
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
            "preview": preview[:50],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            500,
            f"CSV import failed: {str(e)}"
        )
