"""Client llama.cpp server (OpenAI-compatible /v1/chat/completions). KHÔNG gửi `tools`; ép đầu ra JSON theo schema (grammar). Chỉ trả văn bản."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    prompt_tps: float | None = None
    gen_tps: float | None = None
    model: str = ""
    extra: dict = field(default_factory=dict)


class LLM(Protocol):
    async def complete(self, messages: list[dict], schema: dict, max_tokens: int) -> LLMResult: ...


class LlamaCppLLM:
    def __init__(self, base_url: str, timeout_s: float = 900, client: httpx.AsyncClient | None = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=10))

    async def complete(self, messages, schema, max_tokens):
        body: dict[str, Any] = {
            "model": "briefing", "messages": messages, "temperature": 0.2, "top_p": 0.9, "seed": 7, "max_tokens": max_tokens, "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "briefing", "strict": True, "schema": schema}},
            "chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True,
        }
        t0 = time.monotonic()
        r = await self.client.post(f"{self.base}/v1/chat/completions", json=body)
        r.raise_for_status()
        d = r.json()
        ms = int((time.monotonic() - t0) * 1000)
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        u, tm = d.get("usage") or {}, d.get("timings") or {}
        return LLMResult(content=msg.get("content") or "", prompt_tokens=int(u.get("prompt_tokens") or 0), completion_tokens=int(u.get("completion_tokens") or 0),
                         latency_ms=ms, prompt_tps=tm.get("prompt_per_second"), gen_tps=tm.get("predicted_per_second"), model=str(d.get("model") or ""))

    async def aclose(self):
        await self.client.aclose()


def parse_json(text: str) -> dict | None:
    """Đầu ra phải là JSON đúng 1 đối tượng; chịu được rác bao quanh nhưng KHÔNG chấp nhận ngoài đối tượng đầu tiên là dict."""
    text = (text or "").strip()
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    return None
