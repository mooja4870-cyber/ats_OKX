import asyncio
import json
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os

async def main():
    load_dotenv()
    exchange = ccxt.okx({
        'apiKey': os.getenv('OKX_API_KEY'),
        'secret': os.getenv('OKX_SECRET_KEY'),
        'password': os.getenv('OKX_PASSWORD'),
        'enableRateLimit': True,
    })
    try:
        balance = await exchange.fetch_balance()
        usdt_bal = balance.get('USDT', {})
        print("USDT Balance keys:", usdt_bal)
        print("Info data totalEq:", balance.get('info', {}).get('data', [{}])[0].get('totalEq'))
        print("Info data:", json.dumps(balance.get('info', {}).get('data', [{}])[0], indent=2))
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(main())
