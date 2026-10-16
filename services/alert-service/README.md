# alert-service

Consume `alerts.out` (group `alert-service`) + tự đánh giá luật từ `md.bars` -> Telegram (hoặc log).

- **Dedupe**: Redis `SET NX EX` theo `dedupe_key` (`DEDUPE_WINDOW_S`).
- **Rate limit**: `RATE_LIMIT_PER_MIN`/phút (mức `crit` không bị giới hạn). Phần vượt được gom vào buffer và gửi thành 1 tin "GOM NHÓM" mỗi `DIGEST_INTERVAL_S`.
- **Cửa sổ rủi ro tin** (tag `risk-window`, từ news-collector: T-30 sắp vào / đang trong / hết cửa sổ): luật mặc định gửi qua `apprise` (ntfy) + `log`, không làm ồn Telegram.
- **Định tuyến**: `routes.yaml` (min_level, tags_any -> channels). Thiếu token Telegram => kênh `log`.
- **Luật** (`rules.yaml`): `stream_silence` (không có bar mới), `heartbeat` (hằng ngày, UTC).
- **Apprise (kênh đa dịch vụ)**: `APPRISE_URLS` (phân tách bằng dấu phẩy) -> kênh `apprise` gửi tới Telegram/ntfy/Slack/Discord/email... (xem wiki Apprise). Có thể đặt cạnh `telegram` trong `routes.yaml` (vd `[telegram, apprise]`): Telegram lỗi thì ntfy vẫn nhận. Kênh chưa cấu hình bị bỏ qua; không còn kênh nào thì ghi log. Kênh Telegram native giữ lại vì cần long-poll cho lệnh `/status`; mọi đích gửi khác nên đi qua Apprise.
- **Telegram chỉ đọc**: `/status`, `/last_alerts [n]`, `/help`. Chỉ trả lời đúng `TELEGRAM_CHAT_ID`. Không có lệnh nào đổi hệ thống/giao dịch.
- **Trạng thái gửi**: sau mỗi alert có `Event.id` (từ `alerts.out`), alert-service phát `alert_delivered` vào stream `alerts.delivery`; storage-writer upsert `alerts.delivered` (alert-service KHÔNG đọc/ghi DB). Alert bị gom nhóm phát khi digest được gửi (`outcome=digest`).
- **Alertmanager**: `POST /webhook/alertmanager` nhận payload webhook v4, quy đổi (`severity` critical/warning/info -> crit/warn/info, `resolved` -> info "ĐÃ HẾT"), đẩy vào `alerts.out` để đi qua dedupe/rate-limit/Telegram như mọi alert. Tuỳ chọn bảo vệ bằng `ALERT_WEBHOOK_TOKEN` (header `Authorization: Bearer ...`); mặc định chỉ dùng trong mạng nội bộ compose.
- HTTP: `/healthz`, `/metrics`, `/status`, `/webhook/alertmanager`.

Token bot lấy từ @BotFather (miễn phí). Không commit token; đặt trong env/secret.

Test: `pytest` (không cần Docker/mạng). Build: `docker build -f services/alert-service/Dockerfile .` từ gốc repo.
