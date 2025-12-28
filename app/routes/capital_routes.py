from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from pydantic import BaseModel, Field

from ..deps import get_db
from ..services.capital_service import get_capital, update_capital

router = APIRouter(prefix="/capital", tags=["capital"])


# ===============================
# SCHEMA
# ===============================
class CapitalPayload(BaseModel):
    capital: Decimal = Field(..., gt=0, description="Trading capital must be > 0")


# ===============================
# GET CURRENT CAPITAL
# ===============================
@router.get("/")
async def read_capital(db: AsyncSession = Depends(get_db)):
    capital = await get_capital(db)
    return {
        "capital": float(capital)
    }


# ===============================
# UPDATE CAPITAL
# ===============================
@router.post("/")
async def save_capital(
    payload: CapitalPayload,
    db: AsyncSession = Depends(get_db)
):
    try:
        account = await update_capital(db, payload.capital)
        return {
            "capital": float(account.capital)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update capital: {str(e)}"
        )
