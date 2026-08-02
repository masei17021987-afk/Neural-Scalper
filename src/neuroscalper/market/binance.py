from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp

from ..domain import BookSnapshot
from .orderbook import LocalOrderBook, OrderBookGap

logger = logging.getLogger(__name__)


class BinanceFuturesPublicCollector:
    """Public USD-M Futures feed. No API key and no order submission."""

    REST_BASE = "https://fapi.binance.com"
    WS_BASE = "wss://fstream.binance.com/stream"

    def __init__(
        self,
        symbol: str,
        levels: int = 20,
        update_ms: int = 100,
        status_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.levels = levels
        self.update_ms = 100 if update_ms <= 100 else 250
        self.status_callback = status_callback
        self.stop_event = asyncio.Event()
        self.book = LocalOrderBook(self.symbol)
        self.reconnects = 0
        self.messages = 0
        self.last_message_ms = 0

    def stop(self) -> None:
        self.stop_event.set()

    def _status(self, state: str, **extra: Any) -> None:
        payload = {
            "state": state,
            "symbol": self.symbol,
            "messages": self.messages,
            "reconnects": self.reconnects,
            "last_message_ms": self.last_message_ms,
            **extra,
        }
        if self.status_callback:
            self.status_callback(payload)

    async def _fetch_snapshot(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        params = {"symbol": self.symbol, "limit": 1000}
        async with session.get(f"{self.REST_BASE}/fapi/v1/depth", params=params, timeout=10) as response:
            response.raise_for_status()
            return await response.json()

    @staticmethod
    def _unwrap(message: dict[str, Any]) -> dict[str, Any]:
        data = message.get("data")
        return data if isinstance(data, dict) else message

    async def _reader(self, ws: aiohttp.ClientWebSocketResponse, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    payload = msg.json()
                except Exception:
                    continue
                data = self._unwrap(payload)
                data["_local_ts_ms"] = int(time.time() * 1000)
                await queue.put(data)
            elif msg.type in {aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE}:
                break

    async def _run_connection(self, session: aiohttp.ClientSession) -> AsyncIterator[BookSnapshot]:
        lower = self.symbol.lower()
        streams = [
            f"{lower}@depth@{self.update_ms}ms",
            f"{lower}@aggTrade",
            f"{lower}@forceOrder",
        ]
        url = f"{self.WS_BASE}?streams={'/'.join(streams)}"
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=50_000)
        self._status("CONNECTING", url=url)
        async with session.ws_connect(url, heartbeat=20, receive_timeout=35, max_msg_size=4_000_000) as ws:
            reader = asyncio.create_task(self._reader(ws, queue))
            try:
                snapshot_payload = await self._fetch_snapshot(session)
                buffered: list[dict[str, Any]] = []
                await asyncio.sleep(0)
                while not queue.empty():
                    buffered.append(queue.get_nowait())
                self.book.set_snapshot(snapshot_payload)
                for event in buffered:
                    event_type = event.get("e")
                    if event_type == "depthUpdate":
                        try:
                            self.book.apply_diff(event)
                        except OrderBookGap:
                            if int(event.get("u", 0)) <= self.book.last_update_id:
                                continue
                            raise
                    elif event_type == "aggTrade":
                        self.book.update_trade(event)
                    elif event_type == "forceOrder":
                        self.book.update_liquidation(event)
                self._status("CONNECTED", last_update_id=self.book.last_update_id)

                while not self.stop_event.is_set():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError as exc:
                        raise ConnectionError("Binance feed timeout") from exc
                    self.messages += 1
                    self.last_message_ms = int(event.get("_local_ts_ms", time.time() * 1000))
                    event_type = event.get("e")
                    if event_type == "aggTrade":
                        self.book.update_trade(event)
                        continue
                    if event_type == "forceOrder":
                        self.book.update_liquidation(event)
                        continue
                    if event_type != "depthUpdate":
                        continue
                    if self.book.apply_diff(event):
                        yield self.book.snapshot(self.levels, local_ts_ms=self.last_message_ms)
            finally:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)

    async def stream(self) -> AsyncIterator[BookSnapshot]:
        backoff = 1.0
        timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15, sock_read=None)
        headers = {"User-Agent": "CryptoHunter-Neural-Scalper/0.1"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            while not self.stop_event.is_set():
                try:
                    async for snapshot in self._run_connection(session):
                        backoff = 1.0
                        yield snapshot
                    if self.stop_event.is_set():
                        break
                    raise ConnectionError("Binance WebSocket closed")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.reconnects += 1
                    self._status("RECONNECTING", error=str(exc), retry_seconds=backoff)
                    logger.warning("Binance collector reconnect: %s", exc)
                    await asyncio.sleep(backoff)
                    backoff = min(30.0, backoff * 1.8)
        self._status("STOPPED")
