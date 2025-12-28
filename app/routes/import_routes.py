from fastapi import APIRouter, Depends, HTTPException
from ..dhan_client import fetch_tradebook, fetch_positions
from ..deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from ..crud import get_trade_by_order, create_trade, upsert_position
import datetime
router = APIRouter(prefix='/import')
@router.get('/dhan/trades')
async def import_trades(limit:int=100, db:AsyncSession=Depends(get_db)):
    try:
        trades = await fetch_tradebook(limit=limit)
        inserted=0
        for t in trades:
            # keep raw payload for mapping later
            order_id = t.get('order_id') or t.get('id') or t.get('trade_id')
            if not order_id:
                continue
            existing = await get_trade_by_order(db, order_id)
            if existing:
                continue
            payload = {
                'dh_order_id': order_id,
                'symbol': t.get('tradingsymbol') or t.get('symbol') or t.get('instrument'),
                'side': t.get('transaction_type') or t.get('side') or t.get('order_type'),
                'quantity': t.get('filled_quantity') or t.get('quantity') or t.get('qty') or 0,
                'price': t.get('avg_price') or t.get('price') or t.get('fill_price') or 0,
                'trade_time': None,
                'raw': t
            }
            ts = t.get('filled_at') or t.get('trade_time') or t.get('created_at')
            if ts:
                try:
                    payload['trade_time'] = datetime.datetime.fromisoformat(ts.replace('Z','+00:00'))
                except Exception:
                    pass
            await create_trade(db, **payload)
            inserted += 1
        return {'inserted':inserted, 'fetched':len(trades)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get('/dhan/positions')
async def import_positions(db:AsyncSession=Depends(get_db)):
    try:
        positions = await fetch_positions()
        upserted = 0
        for p in positions:
            sym = p.get('tradingsymbol') or p.get('symbol') or p.get('instrument')
            qty = p.get('quantity') or p.get('qty') or p.get('net_qty') or p.get('position_qty') or 0
            avg = p.get('avg_price') or p.get('average_price') or p.get('cost_price') or 0
            await upsert_position(db, symbol=sym, qty=qty, avg_price=avg)
            upserted += 1
        return {'upserted': upserted, 'fetched': len(positions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
