# reporter

Báo cáo tự động **ngày** và **tuần** (HTML tự chứa + PDF A4) cho trạm theo dõi thị trường. **Chỉ đọc / mô phỏng, không phải lời khuyên đầu tư**: service chỉ GET dữ liệu từ api-gateway, không có mã đặt lệnh.

```
api-gateway (GET, X-API-Key) ─> collect ─> build (mục độc lập) ─> Jinja2 HTML ─> WeasyPrint PDF ─> /data/reports/{daily|weekly}/{YYYY-MM-DD}.{html,pdf} + index.json
                                                                                          └─> Redis alerts.out (info, dedupe_key report:<kind>:<kỳ>) ─> alert-service ─> ntfy/Telegram
web-ui "Báo cáo" ─> /api/v1/reports ─> api-gateway reports_routes.py (proxy GET) ─> reporter /reports
```

## Nội dung
- **Ngày**: tóm tắt 5 dòng; thị trường (FX, vàng, ETF Mỹ, cổ phiếu VN: Δ phiên, Δ 7 ngày, sparkline 30 phiên, biểu đồ cột); lịch 24h (tác động cao/trung bình, giờ VN); tin 24h theo |sentiment| + sentiment trung bình theo mã; đồng thuận tín hiệu chuyên gia (nhãn *Tham khảo - không phải khuyến nghị*); tài khoản MT + rủi ro (`/v1/risk/accounts` kind=mt); hiệu suất paper (equity, DD, so benchmark); kỹ thuật nổi bật; sức khoẻ hệ thống/nguồn dữ liệu/cảnh báo.
- **Tuần**: như ngày với kỳ 7 ngày, lịch tuần tới, hiệu suất tuần của paper và thị trường, mục *Rủi ro & stress nổi bật* và tổng hợp cảnh báo tuần.
- Mỗi mục độc lập: nguồn lỗi/thiếu -> mục hiện "Chưa có dữ liệu", báo cáo vẫn ra (`status=degraded`, `sections_fail` trong index).
- Biểu đồ là SVG inline (không matplotlib), in trắng-đen vẫn đọc được (dương = nền đặc, âm = gạch chéo, kèm ▲/▼ và số).

## Cấu hình (biến môi trường)
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GATEWAY_URL` / `API_KEY` | `http://api-gateway:8000` / `${API_TOKEN}` | gateway nội bộ + khoá API |
| `REPORT_TZ` | `Asia/Ho_Chi_Minh` | múi giờ lịch chạy |
| `REPORT_DAILY_AT` | `06:30` | giờ chạy báo cáo ngày |
| `REPORT_WEEKLY_DOW` / `REPORT_WEEKLY_AT` | `6` (Chủ nhật) / `19:00` | báo cáo tuần |
| `REPORT_KEEP_DAILY` / `REPORT_KEEP_WEEKLY` | `60` / `26` | số báo cáo giữ lại |
| `REPORT_BASE_URL` | rỗng | gốc URL web-ui để gắn liên kết trong thông báo (rỗng -> chỉ nêu `#/bao-cao`) |
| `REDIS_URL` | từ compose (user `ts_app`) | phát sự kiện `alerts.out` |
| `DATA_DIR` | `/data` | volume `reports-data` |
| `ENABLED` | `true` | tắt scheduler (vẫn phục vụ file/API) |

Danh sách mã thị trường nằm ở `config.py` (`Settings.instruments`).

## Lịch chạy
Scheduler asyncio trong service (không cron ngoài), tick 60 giây. Kỳ báo cáo = ngày theo giờ VN của mốc lịch gần nhất. **Idempotent theo kỳ**: đã có file thì bỏ qua; khởi động muộn thì **chạy bù** kỳ gần nhất chưa có; thất bại thử lại tối thiểu mỗi 30 phút.

## API (chỉ nội bộ, cổng 8000, không publish ra host)
- `GET /reports` danh sách từ `index.json` (+ `next_runs`)
- `GET /reports/{daily|weekly}/{YYYY-MM-DD}.{html|pdf}` tải file (regex chặt, chống path traversal)
- `POST /generate?kind=daily|weekly[&force=1][&period=YYYY-MM-DD]` — **chỉ nội bộ, gateway KHÔNG chuyển tiếp**
- `/healthz`, `/metrics` (`reporter_reports_total{kind,result}`, `reporter_last_report_timestamp_seconds`, `reporter_sections_failed`)
- CLI: `docker compose exec reporter python -m reporter.cli daily --force`

Gateway expose `GET /v1/reports` và `GET /v1/reports/{kind}/{period}.{html|pdf}` (`reports_routes.py`). Nginx web-ui có `location /api/v1/reports/` với CSP riêng (cho phép `<style>` nội tuyến, vẫn không script/không tải ngoài) để HTML hiển thị đúng định dạng.

## Hạn chế
- Số liệu `/v1/risk/accounts` do service rủi ro cung cấp; chưa có -> mục MT/rủi ro ghi "Chưa có dữ liệu".
- Cảnh báo kỳ lấy 500 bản ghi gần nhất của `/v1/alerts` (không có tham số `since`).
- Tài khoản paper `replay`/ngừng dùng bị loại; mẫu < 60 ngày hiện Sharpe "n/a".
- Font PDF: DejaVu Sans (phủ đủ dấu tiếng Việt). Báo cáo ngày/tuần toàn hệ thống chưa có bản tháng (bản THEO TÀI KHOẢN có daily/weekly/monthly, xem dưới).

## Báo cáo THEO TÀI KHOẢN (docs/FLEET_MGMT.md §5, §5.1)
Mã: `account_report.py` (kỳ, thu thập, dựng), `account_store.py` (lưu + bảng lịch), `account_service.py` (sinh + scheduler), `account_reports.py` (router nội bộ), mẫu `templates/account_report.html.j2` (in được, tiếng Việt). Mỗi tài khoản có báo cáo `daily|weekly|monthly` gồm Hiệu suất · Rủi ro · Nhật ký · Tuân thủ luật (HTML + PDF), lưu `/data/reports/accounts/<thư-mục-mã-hoá>/{kind}/{YYYY-MM-DD}.{html,pdf}` + `index.json` (cờ `released`: client chỉ thấy bản đã phát hành; thủ công mặc định chưa phát hành).
- Nguồn: gateway nội bộ (`/v1/risk/accounts/{id}`, `/v1/equity-history`, `/v1/journal/{id}/summary`) + auth nội bộ (`/internal/fleet/account/{id}/compliance`, `/internal/fleet/scope-accounts`, Bearer `FLEET_INTERNAL_TOKEN`). Auth chưa chạy -> mục tuân thủ "Chưa có dữ liệu" (không lỗi); lịch theo phạm vi group/tag/all cần auth, phạm vi `account` thì không.
- Lịch: `account_schedules.json` `{schedule_id,scope{type,ref},kind,hour,enabled,auto_release}`; scheduler nền tick 60 s, tối đa 2 báo cáo đồng thời, không chạy trùng, bỏ qua tài khoản không có dữ liệu, thử lại sau 30 phút khi lỗi.
- Env mới: `FLEET_AUTH_URL` (`http://auth:8000`), `FLEET_INTERNAL_TOKEN` (compose chỉ tham chiếu `${FLEET_INTERNAL_TOKEN:-}`).
- API nội bộ: `GET /account-reports?account_id=`, `POST /account-reports/generate|release`, `GET /account-reports/{id}/{period}/{html|pdf}?kind=&released_only=`, `DELETE /account-reports/{id}`, `GET|PUT|POST /account-report-schedules`, `DELETE /account-report-schedules/{id}`.
- An toàn: account_id regex chặt + tên thư mục mã hoá (chống path traversal); mọi chuỗi qua `scrub_obj`/`scrub_sources` (test quét HTML + PDF); chỉ GET dữ liệu, không có đường đặt lệnh.
- Hạn chế: lãi/lỗ kỳ = equity cuối - đầu (gồm lệnh mở, có thể gồm nạp/rút); số liệu rủi ro là ảnh chụp lúc tạo; PDF phải sinh trong image reporter thật (test PDF bị skip ở container test trần).
