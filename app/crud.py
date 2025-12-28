from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Trade, Position, GreeksSnapshot
async def get_trade_by_order(session: AsyncSession, order_id: str):
    q = select(Trade).where(Trade.dh_order_id == order_id)
    res = await session.execute(q)
    return res.scalar_one_or_none()
async def create_trade(session: AsyncSession, **kwargs):
    t = Trade(**kwargs)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t
async def upsert_position(session: AsyncSession, symbol: str, qty, avg_price):
    q = select(Position).where(Position.symbol==symbol)
    res = await session.execute(q)
    pos = res.scalar_one_or_none()
    if pos:
        pos.qty = qty
        pos.avg_price = avg_price
        await session.commit()
        await session.refresh(pos)
        return pos
    pos = Position(symbol=symbol, qty=qty, avg_price=avg_price)
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    return pos
async def create_greeks(session: AsyncSession, **kwargs):
    g = GreeksSnapshot(**kwargs)
    session.add(g)
    await session.commit()
    await session.refresh(g)
    return g
