from __future__ import annotations

from .templates import LEVEL_VI

# CHỈ ĐỌC. Không có lệnh nào thay đổi hệ thống hoặc giao dịch; thêm lệnh mới phải giữ nguyên tính chất này.
READ_ONLY_COMMANDS = ("/status", "/last_alerts", "/help")


async def handle_command(text: str, engine, telegram_enabled: bool = True) -> str:
    parts = text.strip().split()
    if not parts:
        return ""
    cmd = parts[0].split("@")[0].lower()
    if cmd == "/status":
        st = await engine.stats()
        total = sum(st.values())
        rows = ", ".join(f"{k}={v}" for k, v in sorted(st.items())) or "chưa có"
        return f"Alert-service đang chạy.\nTổng xử lý: {total}\nChi tiết: {rows}"
    if cmd == "/last_alerts":
        n = 5
        if len(parts) > 1 and parts[1].isdigit():
            n = max(1, min(20, int(parts[1])))
        items = await engine.recent(n)
        if not items:
            return "Chưa có cảnh báo nào."
        return "\n".join(
            f"{i['ts'][11:16]} [{LEVEL_VI.get(i.get('level'), i.get('level'))}] {i.get('title')} ({i.get('outcome')})"
            for i in items)
    if cmd in ("/help", "/start"):
        return "Lệnh chỉ đọc: /status, /last_alerts [n], /help. Bot không thực hiện thao tác hệ thống hay giao dịch."
    return "Lệnh không được hỗ trợ (bot chỉ có lệnh chỉ đọc). Gõ /help."


async def poll_once(tg, engine, offset: int | None) -> int | None:
    """Xử lý 1 lượt getUpdates; chỉ trả lời chat_id đã cấu hình. Trả về offset mới."""
    updates = await tg.get_updates(offset, timeout=25)
    for u in updates:
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        text = msg.get("text") or ""
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != tg.chat_id or not text.startswith("/"):
            continue
        reply = await handle_command(text, engine)
        if reply:
            await tg.send(reply, chat_id=chat)
    return offset
