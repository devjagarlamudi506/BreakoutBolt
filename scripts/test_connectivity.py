"""Connectivity test for all APIs and WebSockets."""
import asyncio
import json

import httpx
import websockets


async def test():
    env = {}
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v

    fh_key = env.get("FINNHUB_API_KEY", "")
    pg_key = env.get("POLYGON_API_KEY", "")
    alp_key = env.get("ALPACA_API_KEY", "")
    alp_sec = env.get("ALPACA_API_SECRET", "")
    webhook = env.get("DISCORD_WEBHOOK_URL", "")

    print("=== 1. Finnhub REST (Quote) ===")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={fh_key}")
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            print(f"  AAPL: current={d.get('c')}, high={d.get('h')}, low={d.get('l')}")
        else:
            print(f"  Error: {r.text[:200]}")

    print("\n=== 2. Polygon REST (Grouped Daily) ===")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2026-04-16?adjusted=true&apiKey={pg_key}"
        )
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            print(f"  Results count: {d.get('resultsCount', 0)}")
        else:
            print(f"  Error: {r.text[:200]}")

    print("\n=== 3. Finnhub WebSocket ===")
    try:
        async with websockets.connect(f"wss://ws.finnhub.io?token={fh_key}", close_timeout=5) as ws:
            await ws.send(json.dumps({"type": "subscribe", "symbol": "AAPL"}))
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print(f"  Connected OK, msg type: {data.get('type')}")
            except asyncio.TimeoutError:
                print("  Connected OK (no trades in 5s - market closed, expected)")
            await ws.send(json.dumps({"type": "unsubscribe", "symbol": "AAPL"}))
    except Exception as e:
        print(f"  FAILED: {e}")

    print("\n=== 4. Alpaca REST (Account) ===")
    async with httpx.AsyncClient(timeout=10) as client:
        headers = {"APCA-API-KEY-ID": alp_key, "APCA-API-SECRET-KEY": alp_sec}
        r = await client.get("https://paper-api.alpaca.markets/v2/account", headers=headers)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            acct = r.json()
            print(f"  Account: {acct.get('account_number')}, Equity: ${acct.get('equity')}")
        else:
            print(f"  Error: {r.text[:200]}")

    print("\n=== 5. Alpaca WebSocket (IEX) ===")
    try:
        async with websockets.connect("wss://stream.data.alpaca.markets/v2/iex") as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"  Connected, welcome: {data}")
            auth = {"action": "auth", "key": alp_key, "secret": alp_sec}
            await ws.send(json.dumps(auth))
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            status = data[0].get("msg") if isinstance(data, list) else data
            print(f"  Auth: {status}")
    except Exception as e:
        print(f"  FAILED: {e}")

    print("\n=== 6. Discord Webhook ===")
    if webhook:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(webhook)
            print(f"  Status: {r.status_code} (GET to verify URL exists)")
    else:
        print("  No webhook URL configured")

    print("\n=== DONE ===")


asyncio.run(test())
