from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from ..models import AccountSettings


async def get_capital(db: AsyncSession) -> Decimal:
    result = await db.execute(select(AccountSettings))
    row = result.scalars().first()
    return row.capital if row else Decimal("0")


async def update_capital(db: AsyncSession, capital: Decimal):
    result = await db.execute(select(AccountSettings))
    row = result.scalars().first()

    if row:
        row.capital = capital
    else:
        row = AccountSettings(capital=capital)
        db.add(row)

    await db.commit()
    await db.refresh(row)
    return row
