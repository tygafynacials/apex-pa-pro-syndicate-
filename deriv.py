import asyncio
import json
from urllib.request import Request, urlopen

DERIV_WS_URL = "wss://ws.binaryws.com/websockets/v3"

class DerivProvider:
    """Small async wrapper around Deriv's public market-data WebSocket API."""

    async def _request(self, payload: dict) -> dict:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("Install the 'websockets' package (add it to requirements.txt) to use Deriv live data.") from exc
        async with websockets.connect(DERIV_WS_URL, open_timeout=10, close_timeout=5) as ws:
            await ws.send(json.dumps(payload))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if response.get("error"):
                raise RuntimeError(response["error"].get("message", "Deriv API error"))
            return response

    async def active_symbols(self) -> list[dict]:
        response = await self._request({"active_symbols": "full", "product_type": "basic"})
        symbols = response.get("active_symbols", [])
        return [
            {
                "symbol": item.get("symbol"),
                "display_name": item.get("display_name") or item.get("underlying_symbol") or item.get("symbol"),
                "market": item.get("market"),
                "market_display_name": item.get("market_display_name"),
                "submarket": item.get("submarket"),
                "submarket_display_name": item.get("submarket_display_name"),
                "exchange_is_open": item.get("exchange_is_open"),
                "feed": "Deriv"
            }
            for item in symbols if item.get("symbol")
        ]

    async def candles(self, symbol: str, granularity: int, count: int) -> list[dict]:
        response = await self._request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "granularity": granularity,
            "style": "candles"
        })
        return response.get("candles", [])
