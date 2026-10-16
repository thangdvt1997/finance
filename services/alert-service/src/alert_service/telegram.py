from __future__ import annotations

import asyncio
import logging

import httpx
from tscommon.sources import scrub_sources

log = logging.getLogger("alert.telegram")


class TelegramClient:
    """Client Bot API tối giản bằng httpx. Chỉ dùng sendMessage + getUpdates."""

    def __init__(self, token: str, chat_id: str, api_base: str = "https://api.telegram.org",
                 client: httpx.AsyncClient | None = None):
        self.token = token
        self.chat_id = str(chat_id)
        self.base = f"{api_base.rstrip('/')}/bot{token}"
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send(self, text: str, chat_id: str | None = None) -> bool:
        payload = {"chat_id": chat_id or self.chat_id, "text": scrub_sources(text)[:4000], "disable_web_page_preview": True}
        for attempt in range(2):
            try:
                r = await self._client.post(f"{self.base}/sendMessage", json=payload)
            except httpx.HTTPError as e:
                log.warning("telegram send error: %s", type(e).__name__)  # không log URL (chứa token)
                return False
            if r.status_code == 429 and attempt == 0:
                try:
                    wait = float(r.json().get("parameters", {}).get("retry_after", 1))
                except Exception:
                    wait = 1.0
                await asyncio.sleep(min(wait, 5))
                continue
            return r.status_code == 200
        return False

    async def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        params: dict = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        try:
            r = await self._client.post(f"{self.base}/getUpdates", json=params)
            if r.status_code != 200:
                return []
            return r.json().get("result", [])
        except (httpx.HTTPError, ValueError):
            return []
