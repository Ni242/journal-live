import os, httpx, logging
from dotenv import load_dotenv
load_dotenv()
API_BASE = os.getenv('DHAN_API_BASE','https://api.dhan.co/v2')
API_TOKEN = os.getenv('DHAN_API_TOKEN')
HEADERS = {}
if API_TOKEN:
    HEADERS = {'Authorization':f'Bearer {API_TOKEN}','access-token':API_TOKEN}
async def http_get(path: str, params: dict=None):
    url = API_BASE.rstrip('/') + path
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()
async def fetch_tradebook(limit:int=100):
    # try common endpoints; return raw response list and raw first item for mapping
    candidates = ['/tradebook','/orders/tradebook','/orders/trades','/orders']
    for p in candidates:
        try:
            data = await http_get(p, params={'limit':limit})
            if isinstance(data, dict) and 'data' in data:
                return data['data']
            return data
        except Exception as e:
            logging.debug('path %s failed: %s', p, e)
    return []
async def fetch_positions():
    candidates = ['/positions','/orders/positions','/portfolio']
    for p in candidates:
        try:
            data = await http_get(p)
            if isinstance(data, dict) and 'data' in data:
                return data['data']
            return data
        except Exception:
            continue
    return []
async def fetch_option_chain(underlying: str):
    # attempt POST /optionchain; fallback to GET variations
    url = API_BASE.rstrip('/') + '/optionchain'
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(url, headers=HEADERS, json={'underlying':underlying})
        r.raise_for_status()
        obj = r.json()
        return obj.get('data', obj)
