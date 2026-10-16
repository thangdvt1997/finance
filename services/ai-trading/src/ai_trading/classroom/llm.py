"""LLMClient trừu tượng. Mặc định llama.cpp cục bộ (cùng server OpenAI-compatible với briefing, KHÔNG gửi `tools`).
Claude API chỉ khi bật cờ + có key (mặc định tắt, 0 đồng). Mọi lỗi -> LLMError -> nơi gọi rơi về câu hỏi mẫu."""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Callable, Iterator, Protocol

from .safety import check_output


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str

    def stream(self, messages: list[dict], max_tokens: int = 400) -> Iterator[str]: ...


def _b(v: str | None, d: bool = False) -> bool:
    return d if v is None else v.strip().lower() in ("1", "true", "yes", "on")


class LlamaCppClient:
    name = "llamacpp"

    def __init__(self, base_url: str, timeout_s: float = 120, model: str = "classroom"):
        if not base_url.startswith(("http://", "https://")):
            raise LLMError("base_url không hợp lệ")
        self.base, self.timeout_s, self.model = base_url.rstrip("/"), timeout_s, model

    def stream(self, messages, max_tokens=400):
        body = {"model": self.model, "messages": messages, "temperature": 0.3, "top_p": 0.9, "max_tokens": int(max_tokens), "stream": True,
                "chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True}
        req = urllib.request.Request(f"{self.base}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:  # nosec - URL nội bộ do cấu hình, không từ người dùng
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    p = line[5:].strip()
                    if p == "[DONE]":
                        return
                    try:
                        d = json.loads(p)
                    except ValueError:
                        continue
                    delta = ((d.get("choices") or [{}])[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
        except LLMError:
            raise
        except Exception as e:  # noqa: BLE001 - mọi lỗi mạng/HTTP -> LLMError
            raise LLMError(f"llm: {type(e).__name__}") from None


class ClaudeClient:
    """Chỉ dùng khi CLASSROOM_CLAUDE_ENABLED=true VÀ có key. Không có key -> build_client không tạo lớp này."""
    name = "claude"

    def __init__(self, api_key: str, model: str, timeout_s: float = 60):
        if not api_key:
            raise LLMError("thiếu key")
        self._key, self.model, self.timeout_s = api_key, model, timeout_s

    def stream(self, messages, max_tokens=400):
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        body = {"model": self.model, "max_tokens": int(max_tokens), "stream": True, "system": system, "messages": [m for m in messages if m["role"] != "system"]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-api-key": self._key, "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:  # nosec
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("data:"):
                        try:
                            d = json.loads(line[5:])
                        except ValueError:
                            continue
                        t = (d.get("delta") or {}).get("text")
                        if t:
                            yield t
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"llm: {type(e).__name__}") from None


class NullClient:
    """LLM tắt: luôn lỗi -> state machine dùng câu hỏi mẫu cố định."""
    name = "none"

    def stream(self, messages, max_tokens=400):
        raise LLMError("llm tắt")
        yield ""  # pragma: no cover


class FakeLLM:
    """LLM giả cho test: replies là danh sách chuỗi (hoặc hàm messages->str); hết thì lỗi."""
    name = "fake"

    def __init__(self, replies=None, chunk: int = 12, fail: bool = False):
        self.replies, self.chunk, self.fail, self.calls = list(replies or []), chunk, fail, []

    def stream(self, messages, max_tokens=400):
        self.calls.append(messages)
        if self.fail or not self.replies:
            raise LLMError("fake: lỗi")
        r = self.replies.pop(0)
        text = r(messages) if callable(r) else r
        for i in range(0, len(text), self.chunk):
            yield text[i:i + self.chunk]


class GuardedLLM:
    """Bọc LLMClient: giới hạn độ dài prompt/đầu ra/token, tốc độ (cửa sổ trượt), hạn tổng thời gian; luôn qua check_output; rơi về fallback khi lỗi."""

    def __init__(self, inner: LLMClient, *, max_prompt_chars: int = 6000, max_out_chars: int = 1200, max_tokens: int = 400,
                 max_calls: int = 12, per_seconds: float = 60.0, deadline_s: float = 90.0, clock: Callable[[], float] = time.monotonic):
        self.inner, self.max_prompt_chars, self.max_out_chars, self.max_tokens = inner, max_prompt_chars, max_out_chars, max_tokens
        self.max_calls, self.per_seconds, self.deadline_s, self.clock = max_calls, per_seconds, deadline_s, clock
        self._stamps: list[float] = []
        self._lock = threading.Lock()
        self.stats = {"ok": 0, "fallback": 0, "rejected": 0}

    def _allow(self) -> bool:
        now = self.clock()
        with self._lock:
            self._stamps = [t for t in self._stamps if now - t < self.per_seconds]
            if len(self._stamps) >= self.max_calls:
                return False
            self._stamps.append(now)
            return True

    def stream(self, messages, max_tokens: int | None = None) -> Iterator[str]:
        if sum(len(m.get("content", "")) for m in messages) > self.max_prompt_chars:
            raise LLMError("prompt quá dài")
        if not self._allow():
            raise LLMError("vượt giới hạn tốc độ")
        t0, n = self.clock(), 0
        for piece in self.inner.stream(messages, min(int(max_tokens or self.max_tokens), self.max_tokens)):
            if self.clock() - t0 > self.deadline_s:
                raise LLMError("quá thời gian")
            n += len(piece)
            if n > self.max_out_chars:
                return
            yield piece

    def generate(self, messages: list[dict], fallback: str, validate: Callable[[str], str | None] | None = None, max_tokens: int | None = None) -> tuple[str, bool]:
        """Trả (văn bản, used_llm). Đầu ra phải qua check_output + validate (trả lý do hoặc None); sai/lỗi -> fallback."""
        try:
            text = "".join(self.stream(messages, max_tokens)).strip()
        except LLMError:
            self.stats["fallback"] += 1
            return fallback, False
        why = check_output(text, self.max_out_chars) or ([validate(text)] if validate and validate(text) else [])
        if why:
            self.stats["rejected"] += 1
            return fallback, False
        self.stats["ok"] += 1
        return text, True


def build_client(env: dict | None = None) -> GuardedLLM:
    """Cấu hình qua env: CLASSROOM_LLM_BACKEND=llamacpp|claude|none (mặc định llamacpp), CLASSROOM_LLM_URL (mặc định BRIEFING_LLM_URL hoặc http://briefing-llm:8080),
    CLASSROOM_LLM_TIMEOUT_S (mặc định 10 s: chờ token đầu/ khoảng lặng tối đa; quá -> fallback tất định), CLASSROOM_LLM_DEADLINE_S (mặc định 30 s tổng; RS-7),
    CLASSROOM_CLAUDE_ENABLED (mặc định false) + CLASSROOM_CLAUDE_KEY + CLASSROOM_CLAUDE_MODEL. Claude không key/không bật -> quay về llamacpp."""
    e = os.environ if env is None else env
    backend = (e.get("CLASSROOM_LLM_BACKEND") or "llamacpp").lower()
    inner: LLMClient
    if backend == "none":
        inner = NullClient()
    elif backend == "claude" and _b(e.get("CLASSROOM_CLAUDE_ENABLED")) and e.get("CLASSROOM_CLAUDE_KEY"):
        inner = ClaudeClient(e["CLASSROOM_CLAUDE_KEY"], e.get("CLASSROOM_CLAUDE_MODEL", "claude-sonnet-5-5"))
    else:
        inner = LlamaCppClient(e.get("CLASSROOM_LLM_URL") or e.get("BRIEFING_LLM_URL") or "http://briefing-llm:8080", float(e.get("CLASSROOM_LLM_TIMEOUT_S", "10")))
    return GuardedLLM(inner, max_tokens=int(e.get("CLASSROOM_LLM_MAX_TOKENS", "400")), max_calls=int(e.get("CLASSROOM_LLM_MAX_CALLS_PER_MIN", "12")),
                      deadline_s=float(e.get("CLASSROOM_LLM_DEADLINE_S", "30")))
