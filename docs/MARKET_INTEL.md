# MARKET_INTEL — thông tin thị trường tổng hợp (Agent C)

Mọi con số là **thống kê** tính từ dữ liệu giá/tin/lịch đã lưu; không phải khuyến nghị đầu tư. Giao diện KHÔNG hiển thị tên nguồn dữ liệu (xem `UI_NO_SOURCES.md`).

## Endpoint mới (api-gateway, chỉ đọc, `GET /v1/intel/*`)
Mã: `services/api-gateway/src/api_gateway/intel_calc.py` (hàm thuần, không numpy), `intel_data.py` (SQL tham số hoá qua `ts_ro` + cache TTL), `intel_routes.py`; test `tests/test_intel_api.py`. Role `client` được đọc (`authz.CLIENT_ALLOW`).

| Endpoint | Nội dung |
|---|---|
| `strength?tf=H1\|H4\|D1&window` | Điểm sức mạnh 8 tiền tệ: `u_X = dấu·ln(P_t/P_0)·100` từ 7 cặp quy USD (USD=0); điểm = `(n·u_X − Σu)/(n−1)` = % vượt trội so với rổ; lịch sử từng nến, hạng, cặp chênh lệch lớn nhất, `coverage`/`missing` (thiếu cặp thì chỉ tính tập tiền tệ đủ dữ liệu, nói rõ trên UI) |
| `fx` | Bảng 28 cặp × (1h,4h,1d,1w,1m) (7 cặp USD + 21 cặp chéo suy ra), ma trận tỷ giá chéo 8×8 |
| `heatmap?group&period` | `crypto, etf, sector, commodity, forex, us_stock, bond, vn, all` × `1d..1y,ytd`; ô = % đổi, kích thước = giá trị giao dịch TB 20 phiên (không có vốn hoá) |
| `movers?group&period=1h..1m&limit` | tăng/giảm, biến động bất thường (z), biên độ, khối lượng đột biến, gần đỉnh/đáy 52 tuần, gap; `covered/universe` |
| `stats?group&benchmark&window` | ATR%, phân vị ATR 1 năm, độ biến động thực hiện 20 phiên (annualized) + phân vị, khoảng cách SMA20/50/200, beta/tương quan so với benchmark |
| `correlation?symbols&window&method` , `correlation/rolling` | Ma trận Pearson/Spearman trên lợi suất log nến ngày (quan sát chung từng cặp, `n_obs`), tương quan lăn |
| `distribution?symbol&window&bins` | Histogram lợi suất ngày + chuẩn tương ứng, skew, kurtosis, VaR/ES lịch sử 95% |
| `pulse` | Khẩu vị rủi ro 0–100 (độ rộng cổ phiếu/crypto, tâm lý tin, độ bình lặng, xu hướng S&P), chỉ số biến động kiểu VIX (phân vị vol thực hiện 1 năm), độ rộng & xu hướng theo lớp tài sản, tâm lý tin 24h |
| `news?q&symbol&topic&min_importance&sentiment&lang&hours&before&limit` | Tìm toàn văn (ILIKE mọi từ), lọc, phân trang theo thời gian (`next_before`); chủ đề/mức quan trọng/nhãn cảm xúc do service `nlp` gắn sẵn (thiếu thì dự phòng theo từ khoá) |
| `news/topics`, `news/related?url` | Thống kê chủ đề + mã nhắc nhiều; tin liên quan (mã chung, chủ đề chung, tiêu đề tương tự) |
| `calendar/indicators`, `calendar/history?title&country` | Chỉ số lặp lại; lịch sử thực tế/dự báo/kỳ trước + tỉ lệ vượt dự báo. “Kỳ trước” của lần công bố sau được dùng làm thực tế khi chưa có số thực tế |
| `cot` | Vị thế ròng đầu cơ lớn hàng tuần theo mã: chuỗi, thay đổi tuần, phân vị lịch sử (≥8 tuần), cờ đảo chiều (USDJPY/CAD/CHF) |

## Giao diện
Trang (tự đăng ký, `pages/*.jsx` có `meta`): Sức mạnh tiền tệ, Bản đồ nhiệt, Movers & biến động, Tương quan & rủi ro, Phiên giao dịch, Nhịp thị trường, Vị thế lớn & đồng thuận; hai trang cũ được thay thân (đường dẫn giữ nguyên): **Tin tức → terminal tin** (`#/tin-tuc`), **Lịch kinh tế → lịch chuyên nghiệp** (`#/lich`).
Widget (`widgets/*.jsx`): currency-strength, fx-heatmap, cross-rates, market-hours, session-ranges, heatmap-market, movers-list, market-pulse, correlation-matrix, volatility-rank, return-distribution (linkable), cot-positions, news-terminal (linkable), calendar-pro.

Terminal tin: danh sách ảo hoá (hàng cố định 76/36px), WebSocket (`news.items` + `news.enriched` qua `onStreamEvent` trong `lib/stream.js`), chèn tin mới giữ vị trí cuộn + nút “N tin mới”, âm báo/đọc to tin quan trọng (tuỳ chọn), đã đọc/đã lưu trong localStorage (theo thiết bị), phím j/k/s/u. Lịch: lưới tuần / ngày / bảng, cụm cửa sổ rủi ro (tin cao cách ≤60 phút), nhắc trước sự kiện (thông báo trong ứng dụng) và tạo quy tắc cảnh báo máy chủ `news_window` (áp dụng theo mức tác động + quốc gia, không riêng 1 sự kiện).

## Mở rộng dữ liệu đi kèm
- `assets.yaml`: thêm ETF ngành Mỹ (XL*), DIA, EFA, EEM, SMH, GDX, UUP, VIXY, LQD, HYG; `market-collector` (yahoo_daily) lấy thêm các mã này; dukascopy lấy đủ 7 cặp quy USD + XAG để H1/H4 có đủ 8 tiền tệ.
- `news-collector`: `cot_contracts.yaml: limit 1900` backfill ~3 năm vị thế hàng tuần; chỉ báo cáo mới nhất tạo tin.

## Giới hạn dữ liệu (nói thẳng trên UI)
- Heatmap không có vốn hoá → kích thước theo giá trị giao dịch TB 20 phiên. Cổ phiếu VN dùng service `vn-market` (cuối ngày).
- Sức mạnh tiền tệ H1/H4 chỉ đủ 8/8 khi collector backfill xong các cặp (API trả `coverage`).
- Movers 1h/4h chỉ có cho mã có nến H1/H4 (crypto + vài cặp FX); 52 tuần/gap/khối lượng từ nến ngày. Forex không có khối lượng thật.
- Lịch kinh tế: số liệu thực tế mới tích luỹ gần đây nên biểu đồ lịch sử chủ yếu có dự báo + kỳ trước; dòng thử nghiệm `QA ...` bị ẩn khỏi UI.
- Đồng thuận chuyên gia và vị thế lớn chỉ là thống kê dữ liệu công khai, nhãn “tham khảo”.
- Ngày lễ sàn: bảng tĩnh 2026–2027 (Nhật, Việt Nam, Hồng Kông là ước tính, cần đối chiếu lịch chính thức).

## QA
`sh /root/trading-system/services/web-ui/qa/run-c.sh [intel.mjs|intel-flow.mjs]` (VPS, container `qa-ui-c-*`, master thử `qa-ui-c` tự tạo/xoá; biến `VIEWPORT=WxH THEME=dark|light ONLY WAIT`).
