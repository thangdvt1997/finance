# Chứng khoán Việt Nam (service `vn-market`, trang "Chứng khoán VN")

Chỉ đọc, dữ liệu CUỐI NGÀY (cập nhật sau ~15:10 giờ VN), gói 0 đồng, không đặt lệnh. Làm xong 2026-10-12.

## Nguồn dữ liệu: đã kiểm tra thật từ VPS <VPS_IP> (2026-10-12)
| Nguồn | Kết quả | Dùng? |
|---|---|---|
| **VNDirect finfo** `api-finfo.vndirect.com.vn/v4` (stock_prices, vnmarket_prices, foreigns, ratios, events, stocks) | 200, không key/đăng nhập, 1 request = cả sàn (HOSE 430, HNX 299, UPCoM 817 dòng); có giá tham chiếu/trần/sàn, giá điều chỉnh, GTGD khớp+thoả thuận, khối ngoại + room, vốn hoá/P/E/P/B/beta/cổ tức, sự kiện quyền, 42 chỉ số kèm số mã tăng/giảm/trần/sàn, lịch sử từ 2018 | **CÓ** (nguồn chính). API không chính thức: tự giới hạn ≥0,8 s/request, UA khai báo, chỉ dùng cá nhân. robots.txt không có |
| vnstock 4.0.9 (không key, đã có trong market-collector) | `Listing`: phân ngành 25 nhóm (KBS) cho 698 mã + thành phần VN30/VN100/HNX30 + 24 ETF | **CÓ, chỉ để tạo seed** (`services/vn-market/tools/refresh_vn_universe.py`, chạy mỗi quý). Không đưa vào image. Nến D1 vnstock vẫn TẮT (xem DATA_SOURCE_PRIORITY.md) |
| Yahoo `.VN` / `^VNINDEX.VN` | 200 (VNINDEX 1735,09; E1VFVN30 33.840) | Giữ làm nguồn D1 của md.bars (provider `yahoo_daily` đã có, giá thô, cảnh báo thưởng/chia tách không điều chỉnh) |
| SSI iBoard `iboard-query.ssi.com.vn` | **403 Blocked** (anti-bot) | KHÔNG (không vượt) |
| TCBS `apipubaws.tcbs.com.vn` | **403 Cloudflare challenge** | KHÔNG |
| Vietcap `trading.vietcap.com.vn` | 200 nhưng là API nội bộ của vnstock/VCI, không rõ ToS | Không dùng |

## Phạm vi
- **1.551 mã** trong `vn_symbols`: HOSE 406 cổ phiếu + 21 ETF, HNX 299, UPCoM 818 (giá cuối ngày + độ rộng toàn thị trường). Rổ theo dõi sâu (lịch sử D1 từ 2018 giá thô + giá điều chỉnh, ratios, RSI/MA): VN100 + HNX30 + ETF (~150 mã). VN30 = 30 mã. Chỉ số: VNINDEX, VN30, VN100, HNX, HNX30, UPCoM, VNALL, VNMID, VNSML + 30 chỉ số ngành/chiến lược (lưu theo ngày).
- Symbol chuẩn `VN:XXX`, đơn vị VND (nguồn trả nghìn đồng, service nhân 1000). assets.yaml: class `stock_vn` có VN30 + 5 ETF với tên/nhóm; phân ngành chi tiết ở `vn_symbols.industry_name` (**KBS/vnstock, không phải ICB chính thức**).

## Tính năng (API `/v1/vn/*`, UI `#/chung-khoan-vn`)
Tổng quan (6 chỉ số + sparkline, độ rộng từng sàn, thanh khoản so TB 20 phiên, khối ngoại, ngành) · Bản đồ nhiệt ngành (treemap ECharts theo vốn hoá/GTGD, viền tím = trần, xanh lơ = sàn) · Top tăng/giảm/KL/GTGD + danh sách chạm trần/sàn (±7% HOSE, ±10% HNX, ±15% UPCoM) · Khối ngoại (ngày + tích luỹ 5 phiên, room) · Bộ lọc cổ phiếu (P/E, P/B, ROE*, vốn hoá, cổ tức, RSI, GTGD TB20, %1T..., 4 mẫu) · Sự kiện doanh nghiệp (cổ tức, thưởng, phát hành, ĐHCĐ; 90 ngày) · Tin tiếng Việt gắn mã (từ `news_items`, khớp mã IN HOA, chỉ là gợi ý) · Chi tiết mã (nến D1, định giá, khối ngoại 30 phiên, sự kiện, tin) · Phiên ATO/liên tục/ATC theo sàn (giờ VN, **không xét ngày lễ**) tại `/v1/vn/session`, quy tắc bước giá/biên độ/thuế tại `/v1/vn/rules`.
`*` ROE = P/B ÷ P/E và EPS = giá ÷ P/E là **ước tính** (nguồn không cung cấp trực tiếp).

## Chưa làm được / cần tài khoản CTCK
- **Giá realtime trong phiên** (bảng giá, khớp lệnh): SSI iBoard/TCBS chặn truy cập tự động → cần tài khoản **SSI FastConnect** hoặc **DNSE (Lightspeed API)**.
- **Tự doanh**: không có nguồn miễn phí hợp lệ ổn định → cần SSI/DNSE hoặc nguồn trả phí (FiinQuant/WiChart). UI ghi rõ "chưa có", không làm giả.
- **BCTC chi tiết** (doanh thu, lợi nhuận, ROE công bố): chưa tích hợp.
- Khối ngoại ở đây là **cuối ngày** và gồm cả giao dịch thoả thuận (có ngày một vài giao dịch lớn làm số ròng rất lớn).

## Kiến trúc & vận hành
- Service riêng `vn-market` (FastAPI + asyncpg + httpx; `infra/docker-compose.tools.yml`), không publish cổng; api-gateway proxy GET-only whitelist (`vn_routes.py`); nginx không cần đổi. Bảng `vn_*` (migration `005_vn_market.sql`), role ghi `ts_vn` (`infra/db/create_vn_role.sh`; chỉ bảng vn_* + SELECT news_items).
- Nạp: lúc khởi động + mỗi 30 phút kiểm tra "có phiên đã đóng mà chưa có dữ liệu" (ngày lễ: 3 giờ/lần); idempotent; ~10-20 request/ngày sau lần nạp đầu (lần đầu: 30 phiên + lịch sử 150 mã, vài phút).
- Giám sát: `/healthz`, Gatus, Prometheus `vn_last_session_age_days`, `vn_ingest_runs_total`, cảnh báo `VnMarketStale` (>5 ngày).
- Tắt nạp khẩn cấp: `VN_INGEST=false` trong `.env` rồi `up -d vn-market`.
- **Lệnh compose trên VPS PHẢI kèm cả 3 file** `-f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.tools.yml` (ops ghim redis 8.10 và timescaledb có WAL archiving; thiếu ops thì compose tạo lại redis bằng 7-alpine và nó không đọc được AOF của 8.x). Sự cố này đã xảy ra và đã khắc phục ngày 2026-10-12 (redis + timescaledb tạo lại bằng đủ 3 file, dữ liệu nguyên vẹn). Ngoài ra `infra/ops/redis_acl_render.sh` từng sinh dòng chú thích `#` trong `users.acl` mà Redis từ chối khi nạp file (chỉ lộ ra khi redis tạo lại): đã xoá dòng chú thích ở file trên VPS và trong script.
- Làm mới seed ngành/rổ chỉ số mỗi quý: xem docstring `tools/refresh_vn_universe.py`.

## Chi phí/thuế trong paper-trader (đã kiểm tra nhất quán)
`paper-trader/config.py` lớp `equity_vn`: lô 100, VND, `sell_tax_bps=10` (0,1% giá trị bán, chỉ khi bán), `commission_bps=15`, không bán khống, swap 0. Khớp `vn_market.rules` (SELL_TAX 0,1%, phí tham chiếu 0,15%) và có test `test_tax_consistent_with_paper_trader`. Còn thiếu so với quy định thật: bước giá, biên độ trần/sàn và T+2 chưa được paper-trader áp (khớp mô phỏng có thể ra giá ngoài biên) — nên dùng `vn_market.rules.limit_prices/round_to_tick` khi làm phương án C.
