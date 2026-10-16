# Hướng dẫn sử dụng — Trạm theo dõi thị trường (master + client)

Dành cho **người dùng cuối, không cần biết lập trình**. Gồm: **Phần A — dành cho MASTER** (người vận hành/quản trị), **Phần B — dành cho CLIENT** (chủ tài khoản MT4/MT5), **Phần C — cách đọc số liệu và giới hạn trung thực**, **Phần D — hỏi đáp và xử lý sự cố**. Thuật ngữ lạ: xem [GLOSSARY.md](GLOSSARY.md). Việc kỹ thuật (log, deploy, sao lưu, khoá API…) ở [VAN_HANH.md](VAN_HANH.md). Mục lục mọi tài liệu: [INDEX.md](INDEX.md).

> **Đọc một lần cho chắc**
> - Hệ thống **chỉ đọc và quan sát**. **Không đặt lệnh**, không có nút mua/bán, không đăng nhập vào tài khoản giao dịch của bạn.
> - Số liệu "Mô phỏng" (paper) dùng **tiền ảo**.
> - Chỉ báo, tín hiệu, tin tức, ý kiến chuyên gia, bản tin AI **chỉ để tham khảo, không phải khuyến nghị đầu tư**.
> - **Không bao giờ nhập mật khẩu giao dịch hay mật khẩu investor của MT** vào bất kỳ đâu (EA, trang web, tin nhắn cho master). Hệ thống không cần và không hỏi.
> - Trước khi dùng tiền thật cần xác nhận pháp lý (forex cho cá nhân tại Việt Nam chưa được cấp phép; chứng khoán: hỏi công ty chứng khoán về robot) — xem `PLAN.md`, mục "Cổng quyết định" (G1–G3).

## 0. Hệ thống làm gì

```
Nguồn dữ liệu → thu thập → lưu trữ → phân tích / cảnh báo / mô phỏng / rủi ro → website MASTER, ứng dụng CLIENT, báo cáo, thông báo
(giá, tin, lịch,                                                              ▲
 chuyên gia, EA của client MT4/MT5) ─────────── EA chỉ đọc đẩy dữ liệu ra ─────┘
```

| Vai trò | Là ai | Thấy gì | Vào ở đâu |
|---|---|---|---|
| **Master** | Người vận hành/quản trị | Mọi tài khoản của khách, thị trường, hệ thống, mô phỏng, báo cáo | `<link tunnel>/` (website chính) |
| **Master phụ** (support / analyst / auditor) | Nhân sự do master giao quyền | Chỉ phần được giao (xem mục 15) | cùng website |
| **Client** | Chủ một tài khoản MT4/MT5 | **Chỉ tài khoản của mình** + dữ liệu thị trường/tin/lịch dùng chung | `<link tunnel>/c/` (ứng dụng điện thoại PWA) |

Bạn thấy gì: giá và nến (ngoại hối, vàng, ETF/cổ phiếu Mỹ, cổ phiếu Việt Nam, crypto 29 mã 24/7), tin + lịch kinh tế (forecast/actual), vị thế đầu cơ lớn và ý kiến chuyên gia (kèm đánh giá độ tin cậy), tài khoản MT (số dư, equity, vị thế, lệnh chờ — chỉ đọc), rủi ro (VaR/stress/margin), nhật ký giao dịch, mô phỏng tiền ảo, cảnh báo do bạn đặt, báo cáo PDF/HTML tự sinh, bản tin AI hai lần một ngày.

---
# PHẦN A — DÀNH CHO MASTER

## 1. Truy cập và đăng nhập

Website chạy trên máy chủ và ra Internet qua **đường hầm Cloudflare (quick tunnel)**. **Địa chỉ đường hầm đổi mỗi khi dịch vụ đường hầm khởi động lại** (khởi động máy chủ, cập nhật…) nên link cũ sẽ hỏng. Địa chỉ nằm ở đâu:
```bash
ssh root@<VPS_IP>
cat /root/trading-system/data/tunnel_url.txt      # in ra https://xxxx-xxxx.trycloudflare.com
systemctl status tradingsys-tunnel                 # nếu file trống: xem dịch vụ có đang chạy không
```
Nếu file không có: xem `/root/trading-system/data/tunnel.log` (dòng `https://….trycloudflare.com`) hoặc `systemctl restart tradingsys-tunnel`, đợi ~1 phút. Mẹo: "Thêm vào màn hình chính" trên điện thoại và nhớ lấy link mới sau mỗi lần đổi.

**Đăng nhập master (phiên đăng nhập, từ 2026-10-12 — thay cho Basic Auth cũ):**
1. Mở link → trang đăng nhập. Chọn **master**, tên đăng nhập `admin`, mật khẩu.
2. Mật khẩu ban đầu do script tạo ngẫu nhiên và ghi ở **`<SECRETS_DIR>/auth_master_admin.txt` trên VPS** (quyền root, không in ra log). Đọc bằng `cat` trên VPS — **tài liệu này không chứa mật khẩu**.
3. **Lần đầu bắt buộc đổi mật khẩu** (trước đó chỉ trang đăng nhập dùng được). Sau khi đổi, xoá file mật khẩu ban đầu.
4. **Bật 2FA (TOTP)** ở trang **Phiên & thiết bị** (thẻ Bảo mật/TOTP; quét mã QR bằng Google Authenticator/Authy). Master chưa bật TOTP sẽ bị chặn các thao tác nhạy cảm: thao tác hàng loạt (bulk), nhập CSV, quản lý nhân sự/vai trò.
5. Phiên master hết hạn tuyệt đối sau 12 giờ và sau 2 giờ không hoạt động. Sai mật khẩu 5 lần → khoá tạm 15 phút.

Quên mật khẩu / mất thiết bị 2FA: người vận hành chạy `bash infra/ops/auth_bootstrap_master.sh --reset` trên VPS (mật khẩu mới ngẫu nhiên, tắt TOTP, thu hồi mọi phiên). Chi tiết: [AUTH.md](AUTH.md) mục 4.
Đường dự phòng khẩn cấp Basic Auth (mặc định **tắt**): [VAN_HANH.md](VAN_HANH.md).

![Trang Tổng quan](../services/web-ui/docs/01-tong-quan-desktop.png)

## 2. Làm quen giao diện master

- **Thanh bên trái** chia nhóm: **Terminal**, **Thị trường**, **Thông tin**, **Tài khoản**, **Vận hành**, **Quản trị đội** (khách hàng/đội tài khoản), **Tiện ích** (Cài đặt, Trợ giúp, Giới thiệu). Dòng chạy trên cùng là băng giá; chấm xanh "Trực tiếp" = kết nối realtime tốt, "Mất kết nối" = trình duyệt đang nối lại (banner vàng, có nút "Nối lại ngay").
- Điện thoại: thanh dưới 4 trang chính (Tổng quan, Thị trường, Chứng khoán, Cảnh báo) + nút "Thêm".
- **Giờ hiển thị mặc định là giờ Việt Nam (UTC+7)**; đổi ở Cài đặt (thanh trên hiện nhãn UTC± khi khác mặc định).
- **Phím tắt**: `Ctrl/Cmd+K` tìm nhanh (trang, mã, tin; `>` lệnh, `$` mã, `#` tin, `?` thuật ngữ; ví dụ `cảnh báo eurusd 1.0850` mở biểu mẫu đã điền, `eurusd h4` mở biểu đồ); `g` rồi chữ (vd `g` `j` = Nhật ký, `g` `t` = Terminal, `g` `k` = Cài đặt, `g` `h` = Trợ giúp); `?` danh sách phím; `Alt+N` chuông thông báo; `Alt+1…9` đổi workspace Terminal; `Shift+F` toàn màn hình biểu đồ.
- **Cài đặt** (`g` `k`): sáng/tối/tự động, 6 màu nhấn, mật độ gọn, cỡ chữ 90–125%, tương phản cao, giảm chuyển động, múi giờ, kiểu ngày/số/tiền, **màu tăng/giảm** (xanh-đỏ, đỏ-xanh kiểu châu Á, xanh dương-cam cho người mù màu), âm báo, thông báo trình duyệt. Lưu theo tài khoản, đồng bộ các thiết bị.
- **Chuông thông báo**: cảnh báo giá của bạn, tin quan trọng, tín hiệu chuyên gia, sự cố hệ thống; lọc theo loại/chưa đọc. Âm cần chạm trang một lần; thông báo trình duyệt cần cấp quyền, chỉ hiện khi tab ẩn.
- **Công cụ trang** (biểu tượng chia sẻ trên thanh trên): xuất CSV/Excel, lưu ảnh PNG, in/PDF, sao chép bảng (dán vào Excel), sao chép liên kết giữ mã/khung, đánh dấu trang.
- **Thuật ngữ**: rê chuột/Tab tới chữ gạch chấm hoặc biểu tượng ⓘ cạnh số liệu; tra đầy đủ ở Trợ giúp.
- **Huy hiệu tuổi dữ liệu** cạnh giá: cho biết giá cách đây bao lâu. Cuối tuần ngoại hối đóng cửa nên giá "cũ" là bình thường; crypto 24/7 nên phải luôn mới (vài giây–vài phút).

## 3. Terminal: workspace và widget (`#/terminal`)

Trang chính cho người dùng nhiều màn hình. **Workspace** = một bố cục gồm nhiều **widget** kéo-thả.
- Có sẵn workspace Tổng quan, Forex, Crypto, Chứng khoán VN, Tin & Lịch; bạn tạo thêm tuỳ ý.
- Lưới 24 cột: kéo để di chuyển, kéo góc để đổi cỡ; **khoá bố cục**, **nhân bản**, **nhập/xuất JSON**; **kênh màu** liên kết mã giữa các widget (đổi mã ở một widget thì các widget cùng màu đổi theo); **toàn màn hình/trình chiếu** xoay workspace (Esc thoát). Lưu theo người dùng ở máy chủ + dự phòng trong trình duyệt.
- Widget có sẵn (31): biểu đồ, thẻ giá, watchlist, băng giá, heat-strip, top movers/movers, sức mạnh tiền tệ, bản đồ nhiệt FX, tỷ giá chéo, bản đồ nhiệt thị trường, tương quan, phân phối lợi suất, xếp hạng biến động, phiên giao dịch/giờ thị trường/đồng hồ, tin mới nhất + terminal tin, lịch kinh tế sắp tới + lịch pro, cửa sổ rủi ro tin, vị thế COT, nguồn cấp chuyên gia + bản đồ đồng thuận, nhịp thị trường, tài khoản mini, vị thế đang mở, cảnh báo gần đây, trạng thái hệ thống, ghi chú.
- Xuất ảnh PNG một widget có ở công cụ của widget; tìm nhanh workspace/widget bằng Ctrl+K.

## 4. Thị trường và biểu đồ chuyên nghiệp

**Thị trường** (`#/thi-truong`): chọn mã ở danh sách (nhóm theo loại tài sản), chọn khung (M1…D1).
![Thị trường](../services/web-ui/docs/02-thi-truong-desktop.png)
- **Bố cục**: 1 / 2 dọc / 2 ngang / 2×2 / 1+3 / 3×2 ô; mỗi ô độc lập hoặc liên kết theo **nhóm màu**; đồng bộ **crosshair** và **vùng thời gian** giữa các ô.
- **Loại biểu đồ**: nến, nến rỗng, Heikin-Ashi, OHLC, đường, vùng, Baseline, cột; **Renko, Range, Line Break, Kagi, Point & Figure** (tính trong trình duyệt từ OHLC nên chỉ là **xấp xỉ**).
- **Chỉ báo**: SMA/EMA/WMA, Bollinger, RSI, MACD, Stochastic, ATR, ADX, CCI, OBV, PSAR, Ichimoku, Keltner, Donchian, Supertrend, VWAP ngày, Pivot… (tính trong Web Worker nên không giật).
- **Công cụ vẽ** (thanh trái, phím tắt Alt+chữ): đường xu hướng/tia/ngang/dọc/mũi tên, kênh, kênh hồi quy, Pitchfork Andrews, Fibonacci (thoái lui/mở rộng/cung/vùng thời gian/projection), Gann fan, chữ nhật/tam giác, vùng cung-cầu, sóng Elliott, nhãn ghi chú, thước đo, anchored VWAP, volume profile. Bản vẽ lưu theo (mã, khung) trên máy chủ (+ dự phòng cục bộ).
- **Lớp phủ**: vùng phiên Tokyo/London/New York/VN, đóng cửa hôm qua/mở cửa hôm nay, **sự kiện lịch tác động CAO** và **tin quan trọng** trên trục thời gian, **đường cảnh báo giá** (bấm/kéo để tạo/chỉnh cảnh báo — chỉ cảnh báo, **không đặt lệnh**).
- **So sánh nhiều mã** (chồng %), Spread A−B, Tỉ lệ A/B, tương quan Pearson lăn, **đa khung (MTF)**.
- **Replay**: chọn nến bắt đầu, bước từng nến hoặc phát 1–25 nến/giây, tua — để luyện đọc biểu đồ mà không bị lộ tương lai.
- **Mẫu (template)**: lưu chỉ báo + kiểu + giao diện (+ bố cục), nhập/xuất JSON. Tải thêm lịch sử khi kéo sang trái (tới 20.000 nến). Chụp ảnh PNG, toàn màn hình.
- Lưu ý: ngoại hối dùng **tick volume**, không phải khối lượng thật. Cổ phiếu Mỹ/VN là **giá thô** (chưa điều chỉnh cổ tức/thưởng): có thể có cú nhảy giả (ví dụ VCB 03/2025).

## 5. Thông tin thị trường (nhóm Thị trường / Thông tin)

Mọi con số là thống kê tính từ dữ liệu đã lưu; không phải khuyến nghị. ([MARKET_INTEL.md](MARKET_INTEL.md))
- **Sức mạnh tiền tệ**: điểm 8 tiền tệ so với rổ, tính từ 7 cặp quy USD; thiếu cặp thì chỉ tính các tiền tệ đủ dữ liệu (UI nói rõ).
- **Bản đồ nhiệt**: crypto, ETF, ngành, hàng hoá, forex, cổ phiếu Mỹ, trái phiếu, VN; ô = % đổi, kích thước = giá trị giao dịch trung bình 20 phiên (không có vốn hoá).
- **Movers & biến động**: tăng/giảm mạnh, biến động bất thường, khối lượng đột biến, gần đỉnh/đáy 52 tuần, gap.
- **Tương quan & rủi ro**: ma trận Pearson/Spearman, tương quan lăn, phân phối lợi suất, VaR/ES lịch sử, ATR%/beta.
- **Phiên giao dịch**: biên độ trung bình phiên Tokyo/London/New York (giờ UTC cố định) và theo giờ.
- **Nhịp thị trường (Pulse)**: khẩu vị rủi ro 0–100, chỉ số biến động kiểu VIX, độ rộng thị trường, tâm lý tin 24 giờ.
- **Vị thế lớn & đồng thuận**: COT hằng tuần (vị thế ròng đầu cơ, thay đổi tuần, phân vị lịch sử, cờ đảo chiều) và đồng thuận chuyên gia (mục 7).
- **Phân tích** (`#/phan-tich`): RSI, MACD, ATR, Bollinger, EMA 20/50/200, ADX, Stochastic, pivot theo H1/H4/D1; bản đồ nhiệt trạng thái (**heat** = mức đáng chú ý, **không có hướng**; màu = **bias** từ −100 đến +100), screener, tương quan 30 ngày, phiên. **Không có tín hiệu "mua/bán".**
![Phân tích](../services/web-ui/docs/13-phan-tich-desktop.png)

## 6. Tin tức, lịch kinh tế, cửa sổ rủi ro

- **Tin tức** (terminal tin): tìm toàn văn, lọc theo mã/chủ đề/mức quan trọng/cảm xúc/ngôn ngữ/giờ; tin liên quan; thống kê chủ đề. **Cảm xúc −1…+1** do thuật toán chấm từ tiêu đề (mô hình FinBERT cho tiếng Anh, ViSoBERT cho tiếng Việt) — **thô**, hay sai với tin mỉa mai/kỹ thuật. Nhãn mã (ví dụ `EURUSD`) nghĩa là bài được gắn với cặp đó, **không** nghĩa là nên mua/bán.
![Tin tức](../services/web-ui/docs/03-tin-tuc.png)
- **Lịch kinh tế** (lịch chuyên nghiệp): mỗi dòng là một số liệu; **tác động** cao/trung bình/thấp; *Dự báo (forecast)*, *Kỳ trước (previous)*, *Thực tế (actual)* và cột "thực tế − dự báo" tô màu theo quy ước từng chỉ số; xem **lịch sử** từng chỉ số và tỉ lệ vượt dự báo. Ví dụ: CPI Mỹ thực tế 3,4% so với dự báo 3,2% → "cao hơn dự báo", thường làm USD mạnh lên ngắn hạn. Giới hạn: không phải sự kiện nào cũng có forecast; số actual có thể trễ vài phút đến vài chục phút; giờ đã quy đổi sang giờ Việt Nam và theo giờ mùa hè/mùa đông (nếu lệch 1 giờ quanh ngày đổi giờ, đối chiếu nguồn chính thức).
![Lịch](../services/web-ui/docs/04-lich-kinh-te.png)
- **Cửa sổ rủi ro tin (risk window)**: khoảng quanh sự kiện tác động CAO (CPI, NFP, FOMC…) khi giá có thể giật mạnh. Mặc định **15 phút trước → 30 phút sau**; vàng/bạc quanh FOMC/NFP: 15 trước → 45 sau; ngày nghỉ lễ ("Bank Holiday") bị bỏ qua. Trạng thái: *sắp vào* (cảnh báo sớm 30 phút), *đang trong cửa sổ*, *đã hết*. Mục đích: **nhắc bạn đừng vào lệnh/đừng dựa vào tín hiệu** trong khoảng này; chiến lược mô phỏng cũng bị chặn *tăng vị thế*. Ví dụ: NFP 19:30 giờ VN → cửa sổ 19:15–20:00. Áp dụng cho forex, vàng/bạc, chỉ số và một số mã Mỹ/VN; **crypto mặc định không có** cửa sổ tin.

## 7. Chuyên gia và track record

Trang **Chuyên gia** (+ widget bản đồ đồng thuận, nguồn cấp):
![Chuyên gia](../services/web-ui/docs/05-chuyen-gia.png)
- Dữ liệu: vị thế công khai (COT/13F), tín hiệu/ý kiến chuyên gia từ nguồn công khai, hợp pháp — **không hiển thị tên nguồn** (nhãn trung lập như "Luồng tin #3", "Vị thế đầu cơ — EUR").
- **Bảng xếp hạng đọc `status` trước**: `insufficient` ("chưa đủ mẫu", n < 30 quan điểm độc lập) nghĩa là **chưa có bằng chứng**, đừng suy diễn từ hit-rate hay điểm. Chỉ khi `rated` mới có thứ hạng, p/q-value, khoảng tin cậy.
- Cách chấm (tóm tắt): quan điểm có hướng → vào ở giá mở nến D1 **sau** thời điểm ta thực sự biết quan điểm (chống nhìn trước) → thoát sau 1/5/21 nến; hit-rate + khoảng Wilson 95%; lợi suất trung bình + bootstrap; kiểm định hoán vị nhãn hướng; hiệu chỉnh đa kiểm định (BH-FDR, q=0,10); "vượt baseline" cần **cả ba**: q<0,10, cận dưới Wilson > 0,5, cận dưới lợi suất > 0. Chi tiết: [EXPERT_TRACKRECORD.md](EXPERT_TRACKRECORD.md).
- **Thật thà về kết quả hiện tại: chưa chuyên gia/nguồn nào vượt baseline ngẫu nhiên** (0/99 kiểm định). **Đồng thuận** hiện chủ yếu là **đếm phiếu** (thực thể chưa đủ mẫu có trọng số 1) — **không phải bằng chứng**. COT chỉ nên dùng làm bối cảnh "vị thế đông đúc", không làm tín hiệu vào lệnh. Đường "nếu theo ý kiến" kèm dải ngẫu nhiên: đường nằm trong dải = không phân biệt được với đoán bừa.

## 8. Chứng khoán Việt Nam (`#/chung-khoan-vn`)

Dữ liệu **cuối ngày** (cập nhật sau ~15:10 giờ VN); **không có giá thời gian thực trong phiên**, **không có tự doanh** (nguồn miễn phí hợp lệ không có; trang ghi rõ "chưa có"). ([VN_MARKET.md](VN_MARKET.md))
- Tổng quan: VNINDEX, VN30, HNX, UPCoM…; độ rộng (tăng/giảm/đứng/trần/sàn), thanh khoản so trung bình 20 phiên; khối ngoại (mua/bán ròng, room).
- Bản đồ nhiệt ngành (diện tích theo vốn hoá hoặc giá trị giao dịch; viền tím = trần, xanh lơ = sàn); top tăng/giảm; trần/sàn (biên ±7% HOSE, ±10% HNX, ±15% UPCoM); bộ lọc P/E, P/B, ROE*, vốn hoá, cổ tức, RSI; sự kiện doanh nghiệp; tin tiếng Việt gắn mã; chi tiết từng mã.
- `*` ROE và EPS là **ước tính** (từ P/B ÷ P/E). Phân ngành theo KBS (không phải ICB). Đơn vị giá: VND. Lịch phiên ATO/liên tục/ATC theo giờ VN, **không xét ngày lễ**.
- **T+2**: cổ phiếu về tài khoản sau 2 ngày làm việc; hệ thống giữ cấu hình T+2 (chưa thấy văn bản chuyển sang T+1). **Mô phỏng hiện chưa áp T+2, biên độ trần/sàn, margin call, thanh khoản** — nên kết quả mô phỏng cổ phiếu VN lạc quan hơn thực tế.
- Backtest trung thực momentum cổ phiếu VN: **không có alpha**, Sharpe 0,21, MaxDD −58,8% (xem Phần C).

## 9. Crypto

29 mã (BTC, ETH, SOL… quote USDT, ký hiệu `CRYPTO:BTCUSDT`), chạy **24/7** (có nến Thứ Bảy/Chủ nhật); nến gốc của sàn, chỉ nến **đã đóng**; D1 cắt tại 00:00 UTC (07:00 giờ VN). Một số mã ít thanh khoản (TON) có thể thiếu nến phút/giờ. Giá USDT không hoàn toàn bằng USD. Mặc định không có cửa sổ rủi ro tin.

## 10. Tài khoản, rủi ro, nhật ký

- **Tài khoản** (nhãn READ-ONLY): equity theo thời gian, vị thế đang mở, lệnh chờ. Số liệu từ **snapshot** do EA gửi (mỗi vài giây–phút). "Số lệnh" = số vị thế đang mở.
![Tài khoản](../services/web-ui/docs/06-tai-khoan.png)
- **Rủi ro**: **Margin level** = equity/margin (càng thấp càng gần bị đóng lệnh; mặc định cảnh báo ở 200%/100%). **VaR 95% 1 ngày** = mức lỗ mà 95% số ngày không bị vượt (ước tính lịch sử); **ES** = lỗ trung bình khi đã vượt VaR; **Stress** = lặp lại biến cố lớn (2008, CHF 2015, Brexit, COVID, 2022, yên 2024…). Đây là **ước tính**, không thay số liệu margin của sàn; VaR đánh giá thấp rủi ro gap cuối tuần. Cảnh báo "mất kết nối tài khoản" chỉ phát cho tài khoản đã gửi dữ liệu trong 24 giờ qua. **Nếu EA báo tài khoản cho phép giao dịch (không phải investor) → cảnh báo bảo mật.**
- **Nhật ký** (`g` `j`): phân tích lệnh đã đóng của tài khoản MT (và mô phỏng, có nhãn riêng; dữ liệu thử gắn FIXTURE). Tab: **Tổng quan** (tỷ lệ thắng, lợi nhuận ròng, profit factor, kỳ vọng/lệnh, đường vốn + drawdown, lịch nhiệt theo ngày, thống kê giờ/thứ/phiên/mã/hướng, đóng góp theo EA), **Lệnh** (lọc; bấm dòng để ghi **tag/ghi chú/đánh giá** — thao tác ghi duy nhất), **Kỷ luật** (điểm 0–100: vi phạm quy tắc của chính bạn, ví dụ giao dịch trong cửa sổ tin), **Review tuần**. Mẫu ít lệnh (<30) thì mọi thống kê rất nhiễu; MAE/MFE là ước tính từ nến.
![Nhật ký](../services/web-ui/docs/journal-01-overview.png)
![Kỷ luật](../services/web-ui/docs/journal-05-discipline.png)

## 11. Mô phỏng (paper trading)

Chạy một phương pháp bằng **vốn ảo trên dữ liệu thật** để xem có đáng tin không **trước khi** nghĩ tới tiền thật. Chỉ dùng nến đã đóng; khớp ở giá mở nến kế + chi phí giả định (spread, trượt giá, phí, thuế bán cổ phiếu VN 0,1%). Mọi kết quả mang nhãn **"MÔ PHỎNG — không phải tiền thật"**.
- **Đối chứng (benchmark)**: mua-giữ 60/40 (SPY/IEF), giữ đều FX+vàng, giữ đều cổ phiếu VN. Chiến lược không thắng nổi mua-giữ thì chưa đáng tin.
- **Chiến lược** (ví dụ `slow_trend_*_v2`: xu hướng chậm đa tài sản, cân bằng rủi ro, tái cân bằng hàng tháng). **Replay** và `smoke`: chỉ kiểm đường ống, không có ý nghĩa thống kê. Tài khoản cũ nhãn DEPRECATED bị đóng băng.
- Trang cho thấy: equity so với benchmark (chuẩn hoá 100); **CAGR, Vol, Sharpe, MaxDD, Sortino, Calmar** (+ khoảng tin cậy 95% khi ≥20 ngày); **kill-switch** (lỗ ngày/tuần vượt ngưỡng → tạm dừng; vượt drawdown → khoá cứng cần người reset); trang **Chất lượng & quản trị**: giai đoạn (sớm → theo dõi → đủ điều kiện xét duyệt), TCA, phát hiện suy giảm, **strategy card** (giả thuyết, tham số khoá, kết quả backtest kể cả mục không đạt), **hash-chain** (bản ghi nối bằng hàm băm; sửa/xoá/chèn làm chuỗi đứt, trang hiện đỏ + cảnh báo nghiêm trọng).
- Mẫu ngắn (< ~60 ngày): "n/a" hoặc "mẫu quá ngắn" — cố ý, đừng lấy số vài ngày làm kết luận.

### 11b. Tab "AI Trading" (master; client xem bản rút gọn)
Mở `#/ai-trading`: các thẻ chiến lược/mô hình với trạng thái (nghiên cứu / paper / tạm dừng / không có edge), kết quả backtest và forward-paper (kỳ vọng R, khoảng tin cậy, so với ngẫu nhiên, drawdown) và cảnh báo trung thực. Kịch bản Sell KB-1..KB-4 hiện hiển thị đúng kết quả thật: **không có edge sau chi phí** (walk-forward −0,10 R/lệnh; test khoá −0,26 R/lệnh) — chỉ dùng như công cụ mô tả cấu trúc, không dùng để vào lệnh. Mục Lab liệt kê thí nghiệm đã chạy (có thể tái lập) và backlog ý tưởng. Muốn thêm kịch bản mới: nạp YAML đặc tả + ảnh mẫu rồi chạy detector thử/backtest nền (giai đoạn B). Tab chỉ nghiên cứu/paper/thông báo, không đặt lệnh thật. Xem [AI_TRADING.md](AI_TRADING.md).

## 12. Cảnh báo và danh sách theo dõi

**Danh sách theo dõi**: nhiều nhóm (vd "Vàng và USD"), thêm mã bằng ô tìm kiếm, lưu **trên máy chủ**. Nút "Tạo cảnh báo" cạnh mã để đặt luật nhanh.

**Cảnh báo của tôi** (trang Cảnh báo → "Quy tắc của tôi"):
1. Tạo mới, chọn mã. 2. Chọn điều kiện: *giá* (vượt lên/xuống dưới/cắt qua), *% thay đổi* trong N phút, *chỉ báo* (RSI, ADX, khoảng cách EMA200), *cửa sổ tin*, *cảm xúc tin* đảo chiều, *tài khoản MT* (margin, drawdown 24 giờ). 3. Kết hợp AND/OR (≤ 8 điều kiện/luật, ≤ 50 luật). 4. **Một lần** (báo xong tự tắt) hoặc **lặp** (có thời gian nghỉ) và hạn dùng. 5. Dùng **Xem trước** để thấy luật đúng/sai tại thời điểm này. 6. Kênh nhận: ntfy/log; Telegram **chưa cấu hình**.
Ví dụ: "XAUUSD cắt lên 2700 **VÀ** RSI(H1) > 60, lặp, nghỉ 60 phút".
**An toàn:** dữ liệu cũ hoặc thiếu **không bao giờ** kích hoạt cảnh báo (trạng thái "không rõ"). Cảnh báo "im lặng" → kiểm tra độ mới dữ liệu ở trang Hệ thống.
**Lịch sử cảnh báo hệ thống** (tab còn lại): service lỗi, mất kết nối MT, sắp tới tin lớn… Mức *Nghiêm trọng/Cảnh báo/Thông tin*; cột "đã gửi" cho biết có tới kênh nhận chưa.

## 13. Báo cáo và bản tin AI

- **Báo cáo ngày** (06:30 VN): thị trường, lịch 24 giờ tới, tin nổi bật, đồng thuận chuyên gia, tài khoản MT + rủi ro, hiệu suất mô phỏng, chỉ báo nổi bật, sức khoẻ hệ thống. **Báo cáo tuần** (Chủ nhật 19:00 VN): 7 ngày + lịch tuần tới. Mỗi báo cáo có **HTML** (xem ngay) và **PDF A4**; mục thiếu dữ liệu ghi "Chưa có dữ liệu" (degraded). Giữ 60 báo cáo ngày + 26 tuần.
- **Báo cáo theo khách** (Quản trị đội → Báo cáo khách): báo cáo cho từng khách/nhóm/theo lịch.
- **Bản tin AI** (Briefing): hai bản mỗi ngày (**06:15** và **16:30** giờ VN) × hai phạm vi (Việt Nam, Quốc tế). Do mô hình ngôn ngữ **chạy cục bộ**, chỉ **tóm tắt** dữ liệu có đánh số, mọi ý bị **hậu kiểm tất định** (phải trích dẫn được số liệu). Không phải khuyến nghị; vẫn có thể thiếu sót.

### 13b. AI Training Class (vai chuyên gia)
Master tạo tài khoản vai "Chuyên gia" (mục 15); chuyên gia đăng nhập như nhân sự, mở AI Trading, tab "AI Training Class". Quy trình: tạo phòng -> giao kịch bản bằng 3 câu -> trả lời từng câu AI hỏi (số cụ thể thì AI "chắc" hơn; câu mơ hồ AI ghi độ chắc thấp) -> nói "tóm lại bạn hiểu thế nào" để sửa chỗ AI hiểu sai -> nói "tìm những lần nó xuất hiện" rồi gắn nhãn ĐÚNG/SAI/GẦN ĐÚNG + lý do -> nói "lưu lại" -> nói "chạy thử xem có lời không" (AI hiện thẻ hỏi xác nhận trước khi chạy việc nặng, không cần gõ lệnh; dưới ô nhập luôn có 2-4 gợi ý bấm được và dòng "AI hiểu ý bạn là…"; sai ý thì bấm "Không phải ý này"; kết quả là thẻ có số thật + cảnh báo; thường là "chưa chứng minh" hoặc "không có edge"). Chuyên gia KHÔNG mở được test khoá; master mở bằng nút riêng. Chi tiết: `docs/AI_CLASSROOM.md`.
Xoá phòng rác: bấm biểu tượng thùng rác cạnh phòng (hoặc nút Xoá trong phòng); "Chọn nhiều" có lọc nhanh phòng trống/demo/cũ. Phòng vào Thùng rác 30 ngày, bấm "Hoàn tác" (10 giây) hoặc "Khôi phục" trong mục Thùng rác; chỉ master được "Xoá vĩnh viễn".

## 14. Trạng thái hệ thống (trang Hệ thống) và công cụ vận hành
Bảng service (chấm xanh = ổn), độ mới của từng nguồn dữ liệu, luồng sự kiện, lỗi gần đây. Một nguồn có "tuổi" lớn bất thường trong giờ thị trường mở = có thể sự cố. Công cụ cho người vận hành (qua SSH tunnel, cổng chỉ `127.0.0.1`): Gatus `:8590`, Dozzle (log) `:8591`, ntfy `:8592`, Grafana `:3300`, Jaeger `:16686` — [VAN_HANH.md](VAN_HANH.md) mục 1.
![Hệ thống](../services/web-ui/docs/08-he-thong.png)

## 15. Quản trị khách hàng và đội tài khoản (master)

Nhóm **Quản trị đội** (riêng trang **Khách hàng** nằm ở nhóm Vận hành) (chỉ đọc/quản trị — không có đặt lệnh; mọi màn hình ghi rõ "Chỉ-đọc · không có đặt lệnh"). Chi tiết kỹ thuật: [FLEET_MGMT.md](FLEET_MGMT.md), [CLIENT_PLATFORM.md](CLIENT_PLATFORM.md).

**15.1 Thêm khách (Khách hàng `#/khach-hang`)** — chọn nền tảng (MT4/MT5) + số tài khoản (+ máy chủ broker) → hệ thống hiển thị **MỘT LẦN**: **passcode** (mật khẩu cổng ban đầu), **mã ghép cặp** (hết hạn 7 ngày, một lần), **EA token** và **HMAC secret**. Giao cho khách qua kênh an toàn, **không qua email thường**. Khách có thể tự đặt mật khẩu bằng mã ghép cặp.

**15.2 Đội tài khoản (`#/doi-tai-khoan`)**: danh sách với trạng thái EA (online/degraded/offline, độ trễ, phiên bản, lần cuối thấy), nhóm, tag, tuân thủ (xanh/vàng/đỏ), sự cố. Lọc/tìm/sắp xếp, **chế độ xem đã lưu**. **Nhóm** và **tag** (≤12/tài khoản). **Ghi chú CRM** từng tài khoản.
- **Thao tác hàng loạt (bulk)** — hai bước: *chuẩn bị* (xem tóm tắt, tài khoản bị bỏ qua) rồi *xác nhận* bằng cụm gõ lại (`XAC NHAN <n>`); tối đa 200 tài khoản; cần TOTP. Hành động: đình chỉ/kích hoạt, thêm/gỡ tag/nhóm, xoay EA token/HMAC (secret chỉ hiện một lần).
- **Nhập CSV** (cột `platform,login,server,label,group,tags,notes`, ≤200 dòng): xem trước từng dòng (lỗi/cảnh báo) rồi commit; có thể tải "thẻ onboarding" CSV/PDF (dựng trong trình duyệt, server không lưu).
- **Xem như khách (view-as)**: bắt buộc nhập **lý do** (≥8 ký tự), hiệu lực **30 phút** rồi tự thoát, banner đếm ngược, được ghi audit. Chỉ đọc.

**15.3 Luật & tuân thủ (`#/luat`)**: mẫu luật gồm lỗ trong ngày (`daily_loss`), drawdown tối đa (`max_drawdown`: static/trailing), margin level tối thiểu, ngày tốt nhất chiếm quá nhiều lãi (`best_day`), số lệnh/ngày. Gán theo **nhóm/tag/tài khoản/tất cả**. Bảng tuân thủ: **xanh/vàng/đỏ** theo mức dùng hạn mức (vàng từ 70% mặc định, đỏ từ 100%), hiển thị giá trị, hạn mức, còn bao nhiêu, mốc reset. **Quan trọng:** luật nhà cái/prop firm **khác nhau** và thay đổi; mẫu của hệ thống là gợi ý trung tính, **hãy đối chiếu điều khoản thật**. Đo bằng **equity** (gồm lệnh đang mở) nên có thể lệch cách tính của nhà cái.

**15.4 Sự cố (`#/su-co`)**: điều kiện bất thường tự mở (EA offline quá hạn, vi phạm luật, …) với trạng thái *open → ack → snoozed → resolved*; giao việc, tạm hoãn 5 phút–7 ngày, ghi chú, đóng hàng loạt, gom theo nguyên nhân; **tự đóng** khi điều kiện hết. Khách có thể tự bật thông báo đẩy khi sát/vi phạm luật.

**15.5 Vai trò & nhân sự (`#/vai-tro`)**: ngoài master còn **support** (xem + xử lý sự cố + ghi chú, trong nhóm được giao), **analyst** (xem + tuân thủ + báo cáo), **auditor** (chỉ xem nhật ký kiểm toán). Không được giao nhóm nào và không "toàn quyền phạm vi" → thấy 0 tài khoản (mặc định từ chối). Mật khẩu nhân sự mới sinh ngẫu nhiên, hiện một lần, phải đổi lần đầu.

**15.6 Nhật ký kiểm toán (`#/kiem-toan`) và Phiên & thiết bị (`#/phien-thiet-bi`)**: mọi thao tác quản trị được ghi, nối hash-chain; kiểm toàn vẹn bằng `GET /auth/admin/audit/verify`. Xem thiết bị đang đăng nhập, thu hồi phiên, đăng xuất mọi nơi.

**15.7 Thu hồi/đình chỉ**: đình chỉ tài khoản có hiệu lực ở request kế tiếp (bridge được báo xoá cache); khách bị từ chối dữ liệu, EA nhận 403.

---
## 15b. AI Training Class (master + chuyên gia)

Dạy AI một kịch bản giao dịch qua chat. Master: trang **AI Trading > AI Training Class**. Chuyên gia (vai `expert`): trang **AI Training Class** trong menu, chỉ thấy phòng được mời. Mọi thứ chỉ nghiên cứu/paper: không có nút hay lệnh đặt lệnh; chuyên gia không mở được test khoá.

1. **Phòng**: cột trái, mỗi kịch bản/chủ đề một phòng. "Phòng mới" đặt tên (3-80 ký tự). "Mời" thêm chuyên gia bằng mã đăng nhập + tên hiển thị (tin nhắn ghi rõ tên + vai trò người nói). Trên điện thoại/máy tính bảng dùng thanh 3 nút Phòng / Chat / Bảng bên.
2. **Giao kịch bản** bằng 3 câu: mã, khung, hình dạng, vào/ra thế nào. AI hỏi từng cụm nhỏ (thanh tiến độ = checklist 13 bước). Trả lời bằng SỐ (bao nhiêu nến, bao nhiêu ATR, SL/TP theo R). Chế độ **AI hỏi tôi** hiện nút nhanh "Đúng", "Bỏ qua" và các mục bắt buộc còn thiếu; **Tôi hỏi AI** ẩn chúng để bạn tự hỏi.
3. **Nhận định của AI** có 3 nút: **Chấp nhận**, **Sửa** (gõ lại cho đúng, ghi vào hồ sơ), **Phản bác** (thêm câu hỏi mở). Khối "AI hiểu như sau" kèm độ chắc chắn cao/vừa/thấp do mã tính, không phải AI tự chấm.
4. **Việc nhờ AI** (bấm chip dưới ô nhập, hoặc mở menu gợi ý bấm được; không cần gõ lệnh đặc biệt). Chip: Chạy thử (cần bấm Xác nhận; walk-forward dev + baseline ngẫu nhiên, không mở test khoá), Tìm ví dụ, Biến thể, Phía mua, So với mua-giữ, Giải thích, Tóm lại, Lưu phiên bản, AI hỏi thêm, Vẽ lên biểu đồ, Đặt lại (có bước xác nhận). Chip đổi theo ngữ cảnh. Tin do chip gửi hiện trong khung chat bằng câu tự nhiên.
5. **Thẻ kết quả test** hiện số thật (kỳ vọng R, p so với ngẫu nhiên, số lệnh) và cảnh báo trung thực; "không có edge" là kết quả bình thường, đừng chỉnh luật theo test. Nút "Mở test khoá (một lần)" chỉ master, phải gõ lại đúng id kịch bản.
6. **Gắn nhãn ví dụ** (tab Ví dụ): sau khi bấm chip "Tìm ví dụ" có 6-10 ảnh nến; bấm ĐÚNG / GẦN ĐÚNG / SAI + lý do. Độ chính xác = (ĐÚNG + ½ GẦN ĐÚNG) / số đã gắn; độ phủ = đã gắn / tổng; chưa gắn nhãn thì để trống. Nhãn SAI + lý do thành phản ví dụ trong hồ sơ.
7. **Biểu đồ** (tab Biểu đồ, hoặc nút biểu đồ cạnh ô nhập): chọn mã/khung, chọn công cụ (khoảng nến, sóng, đỉnh, đáy, vùng cung/cầu, điểm vào), bấm trên biểu đồ (công cụ 2 điểm: bấm đầu rồi cuối), viết ghi chú, "Xong" để đính vào phòng làm ví dụ. Khoảng nến gửi dưới dạng ghi chú; các công cụ còn lại gửi lệnh `/ve`.
8. **Đính kèm**: kẹp giấy, dán ảnh (Ctrl+V) hoặc kéo thả: ảnh png/jpg/webp ≤700 KB (phải có chú thích, AI chưa tự đọc được ảnh), YAML ≤64 KB, CSV ≤256 KB, PDF ≤1,5 MB, ghi chú .txt/.md. Nội dung đính kèm chỉ là dữ liệu tham khảo, mẫu chỉ thị bị loại.
9. **Sổ tay** (tab Sổ tay): hồ sơ kịch bản (luật, AI hiểu, giả định, câu hỏi mở, người đóng góp), phiên bản + so sánh A→B, "Xuất & kiểm tra" ra YAML (hợp lệ/lỗi/cảnh báo, tải về), "Đăng ký vào Dạy kịch bản" (chỉ khi hợp lệ), "Biên bản (.md)" và "In / PDF" (in từ trình duyệt).
10. **Tìm / ghim / nháp / phím tắt**: Ctrl+K tìm trong phòng; ghim bằng biểu tượng ghim, xem ở tab Ghim; ô nhập tự lưu nháp theo phòng. Enter gửi, Shift+Enter xuống dòng, Ctrl+/ về ô nhập, Alt+1..4 đổi tab bảng bên, Esc đóng gợi ý/dừng luồng. Sáng/tối theo giao diện; VI/EN ở góc phải trang.

11. **Giao diện 3 cột + Hồ sơ kịch bản + Độ rõ ý tưởng** (từ 2026-10-15): cột phải có bảng 16 hàng AI tự điền khi bạn chat; mỗi hàng Xác nhận / Sửa / Hỏi lại, có độ chắc chắn cao/vừa/thấp. "Độ rõ ý tưởng" 0-100 ở thanh trên tăng khi bạn nêu số cụ thể, xác nhận hàng và đưa ví dụ đúng/sai; bấm "Mơ hồ nhất" để biết hỏi tiếp chỗ nào.
12. **Người mới**: nút **Xem demo** (buổi học mẫu minh hoạ), **Cách dạy** (bảng việc nên làm), **Mẫu** (breakout, 3 đỉnh giảm dần, cung/cầu, pullback...), **Tham quan** (5 bước) và checklist "Buổi học đầu tiên" ở cột trái. Tab **Ví dụ**: phím Đ / S / G để gắn nhãn nhanh. Chi tiết: docs/AI_CLASSROOM.md mục "Giao diện và cách dạy".
13. **Bộ nhớ của AI**: tab **Bộ nhớ** (cột phải). AI nhớ điều bạn dạy để không hỏi lại. Khi bạn nêu luật vào lệnh/ SL/ TP/ điều kiện huỷ, AI hỏi "Mình ghi nhớ: ... đúng không?": bấm **Đúng** để chốt, **Sửa** nếu lệch, **Đừng nhớ** để bỏ. Trong tab bạn xem nguồn hội thoại, sửa, ghim, xoá, giải quyết mâu thuẫn giữa các chuyên gia, xem thống kê và xuất/ nhập JSON. Đây là bộ nhớ tham khảo bạn kiểm soát được, không phải huấn luyện lại model. Chi tiết: docs/AI_CLASSROOM.md mục "Bộ nhớ và học liên tục".
14. **Phương pháp** (nhiều kịch bản + quy tắc kết hợp + kế hoạch áp dụng): master vào tab **Phương pháp** trong AI Trading; chuyên gia bấm **Phương pháp** ở đầu trang AI Training Class. Bấm **Tạo mới**, đặt tên, rồi **Thêm kịch bản** (tạo mới hoặc gắn phòng có sẵn; phòng và lịch sử luôn được giữ). Tab **Tổng quan** có sơ đồ: bấm vào một kịch bản để mở phòng của nó. Tab **Quy tắc kết hợp**: loại trừ, bổ trợ, ưu tiên, chỉ chạy trong regime, đối xứng mua/bán, khung xác nhận; bấm **Lưu**. Tab **Phòng phương pháp**: nói với AI về bối cảnh dùng, thứ tự ưu tiên, quản trị vốn chung, quy tắc dừng (nên nêu số). Tab **Kế hoạch áp dụng**: 9 bước và tiêu chí đạt. Biển đỏ **CHƯA đủ điều kiện áp dụng** nghĩa là chưa qua backtest trung thực/ ổn định/ guardrail (bước 4-6); đọc phần Hướng sửa. Nút **Xuất tài liệu** tải Markdown hoặc PDF. Chỉ nghiên cứu/ paper; không có đường đặt lệnh thật.

Lưu ý: khi chưa có khoá đám mây AI dùng mô hình cục bộ + câu hỏi mẫu (hướng dẫn cấp khoá: docs/AI_CLASSROOM.md); tin của chuyên gia khác cập nhật mỗi 4 giây (không đẩy realtime). Chi phí token chưa hiển thị trên giao diện (backend chưa trả số liệu).

# PHẦN B — DÀNH CHO CLIENT (chủ tài khoản MT4/MT5)

Bạn **không cần mật khẩu gì của MT cho hệ thống**. Bạn chỉ cài một chương trình nhỏ (EA) trong terminal MT đã đăng nhập sẵn; EA **chỉ đọc** (không có mã giao dịch) và gửi số liệu ra ngoài.

## 16. Cài EA và ghép cặp
1. **Nhận từ master (kênh an toàn)**: thư mục `mt-agent` (EA MT4 `MTAgentReadOnly.mq4` hoặc MT5 `MTAgentReadOnly.mq5` + `Include/MTAgent`), địa chỉ `BridgeUrl`, và **mã ghép cặp (PairCode)** — hoặc Token + HmacSecret nếu master giao trực tiếp.
2. **Chép file**: trong MT chọn *File → Open Data Folder*; chép `Include/MTAgent/` vào `MQL4/Include/` (hoặc `MQL5/Include/`) và file EA vào `MQL4/Experts/` (hoặc `MQL5/Experts/`). Mở MetaEditor, nhấn F7 — phải **0 lỗi**.
3. **Cho phép WebRequest**: *Tools → Options → Expert Advisors* → tick "Allow WebRequest for listed URL" → thêm **URL gốc** của bridge master cung cấp (ví dụ `https://bridge.example.com`). Thiếu bước này log báo lỗi 4060 (MT5: 4014; MT4: 5200).
4. **Kéo EA vào MỘT biểu đồ**. Điền `BridgeUrl`, `PairCode` (hoặc `Token`+`HmacSecret`), `Symbols` (tên ký hiệu **của broker bạn**, ví dụ `EURUSD.m`), `Timeframes`. `AccountId` để trống (EA tự đặt `mt4:<số>`/`mt5:<số>`). Không cần bật quyền giao dịch.
5. **Xem trạng thái** ngay trên biểu đồ và tab *Experts*:

| Hiển thị | Ý nghĩa | Việc cần làm |
|---|---|---|
| `ghép cặp: pending` + mã `XXXXXX` | Đã gửi yêu cầu, chờ master duyệt (EA thử lại mỗi 30 giây) | Đưa mã cho master, hoặc nhập ở cổng `/c/` (Ghép cặp) |
| `ghép cặp: rejected` | Mã sai/hết hạn/không khớp số tài khoản | Xin mã mới |
| `ghép cặp thành công` → `ok` | Đã có credential, đang gửi dữ liệu | — |
| `chờ master duyệt (pending)` | Credential đúng nhưng tài khoản chưa kích hoạt | Chờ master |
| `401: token/HMAC sai hoặc đã bị thu hồi` | Không khớp, bị xoay, hoặc **đồng hồ máy lệch > 120 giây** | Xin mã mới; đồng bộ giờ (NTP) |
| `403: tài khoản bị ĐÌNH CHỈ` | Master đã đình chỉ | Liên hệ master |
| `429` | Gửi quá nhanh | Tăng `SendIntervalSec` |
| `WebRequest lỗi 4060/4014/5200` | URL chưa nằm trong danh sách cho phép (MT4 chỉ cổng 80/443) | Làm lại bước 3 |

**Bảo mật:** terminal MT in giá trị input của EA vào log *Experts* — **đừng gửi file log hay file `.set` cho ai**. Nghi ngờ lộ token (máy bị xâm nhập) → xin master xoay token/HMAC. Terminal tắt hoặc offline = hệ thống thấy "EA offline" (không phải lỗi hệ thống).

## 17. Ứng dụng client (`<link>/c/`)

Mở link do master cung cấp + `/c/`, "Thêm vào màn hình chính". **Đăng nhập** bằng *nền tảng* + *số tài khoản MT* + **passcode** do master cấp (lần đầu sẽ yêu cầu đổi), hoặc dùng **mã ghép cặp** để tự đặt mật khẩu. Phiên client hết hạn tuyệt đối sau 7 ngày, 48 giờ không hoạt động. Sai mật khẩu 5 lần → khoá tạm 15 phút (có thể do người khác cố đăng nhập vào ID của bạn; đợi hoặc báo master).
Bạn **chỉ thấy tài khoản của mình** (và thị trường/tin/lịch dùng chung). Các trang:

| Trang | Nội dung |
|---|---|
| **Tổng quan** | Đồng hồ margin, lãi/lỗ ngày/tuần/tháng, đường vốn (1D/1W/1M/YTD/ALL), tiếp xúc theo mã/tiền tệ, chia sẻ ảnh |
| **Vị thế & lệnh chờ** | Lọc/tìm; giá trị tính theo **tiền tệ của từng tài khoản** (không cộng gộp khác tiền tệ) |
| **Rủi ro** | Tóm tắt bằng lời: margin, drawdown, tiếp xúc |
| **Nhật ký** | Tổng quan, phân tích theo giờ/thứ/phiên/mã/EA, danh sách lệnh (xuất CSV), kỷ luật, ghi chú/tag |
| **Thị trường** | Biểu đồ chuyên nghiệp (chỉ báo, vẽ, Fibonacci, tín hiệu), watchlist nhiều nhóm, sức mạnh tiền tệ, heatmap |
| **Tin & Lịch** | Tin, lịch kinh tế, cửa sổ rủi ro tin |
| **Bản tin AI** | Bản tin sáng/chiều (mục 13) |
| **Phân tích** | Chỉ báo/bản đồ trạng thái |
| **Cảnh báo** | Cảnh báo giá/điều kiện của bạn |
| **Thông báo** | Chuông + trung tâm thông báo (giá, giới hạn, tin, sự cố EA) |
| **Danh mục** | Nhiều tài khoản (nếu bạn có) |
| **Hồ sơ & cài đặt** | Đổi mật khẩu, phiên/thiết bị, ngôn ngữ, giao diện, múi giờ |
| **Trợ giúp & thuật ngữ** | Giải thích số liệu; hướng dẫn lần đầu (onboarding) |

![Tổng quan client](../services/client-ui/docs/375x812-dark-tong-quan.jpg)

**Giới hạn tự đặt (mục tiêu/hạn mức của chính bạn):** bạn đặt hạn mức lỗ ngày, drawdown, … Hệ thống **nhắc ở các mốc 70/90/100%** (thông báo + đẩy), **chỉ nhắc, không chặn lệnh**. **Siết giới hạn có hiệu lực ngay; nới hoặc xoá phải chờ 24 giờ** (để tránh nới trong lúc nóng). Có lịch sử thay đổi. Nếu master cũng gán luật cho bạn, mức nghiêm hơn được ưu tiên hiển thị.

**Thông báo đẩy (Web Push):** bật ở trang Thông báo (thẻ chỉ hiện khi máy chủ đã cấu hình khoá). Cảnh báo cá nhân chạy trên máy chủ nên **vẫn báo khi app đóng** (khi đã bật Web Push); cảnh báo chạy riêng trên thiết bị chỉ hoạt động khi app mở.

**Ngôn ngữ vi/en:** Hồ sơ → "Ngôn ngữ" (hoặc nút ở màn hình đăng nhập). Nội dung do máy chủ sinh (bản tin, tin tức, lý do luật) **không dịch**. **Cài đặt** (giao diện, mật độ, múi giờ, định dạng số, watchlist) đồng bộ giữa thiết bị khi máy chủ hỗ trợ.

**Cache và riêng tư:** dữ liệu thị trường dùng chung được lưu tạm trong trình duyệt (6 giờ); dữ liệu **tài khoản của bạn không bao giờ lưu** ở máy và bị xoá khi đăng xuất.

**Thử nhanh không cần tài khoản (chế độ minh hoạ):** thêm `?mock=1` vào URL để xem dữ liệu mẫu (`?mock=0` để tắt).

---
# PHẦN C — CÁCH ĐỌC SỐ LIỆU VÀ GIỚI HẠN TRUNG THỰC

## 18. Mô phỏng: vì sao 12 tuần chưa đủ để kết luận
1. Chiến lược xu hướng chậm tái cân bằng hàng **tháng** → 12 tuần chỉ có ~3 lần đổi vị thế, quá ít để phân biệt kỹ năng với may rủi.
2. Với Sharpe thật khoảng 0,3–0,5, cần **hàng năm** dữ liệu; backtest dài hạn còn có giai đoạn nhiều năm gần như không sinh lời (2010–2019). Khoảng tin cậy 12 tuần rộng đến mức bao trùm cả "lời" lẫn "lỗ".
3. 12 tuần có thể rơi vào một chế độ thị trường thuận lợi hoặc bất lợi cho chiến lược xu hướng.
4. Chi phí/trượt giá là **giả định**; chưa mô phỏng T+2, biên độ trần/sàn VN, margin call, thanh khoản.
5. Tiêu chí tối thiểu tự đặt cho "đủ điều kiện xét duyệt": ≥12 tuần, ≥60 ngày dữ liệu, ≥30 lệnh khớp, ≥3 kỳ tái cân bằng, Sharpe ≥ 0, |MaxDD| ≤ 15%, chi phí ≤ 1,5× giả định, không cảnh báo suy giảm, chuỗi nguyên vẹn, cấu hình không đổi. **Đạt = "đáng xem xét tiếp", không phải "được dùng tiền thật".** Không có bước tự động nào chuyển sang tiền thật.

## 19. Kết quả nghiên cứu đã đo (đọc để chỉnh kỳ vọng)

| Chủ đề | Kết quả thật thà | Tài liệu |
|---|---|---|
| Xu hướng chậm đa tài sản (1990–2026) | Sharpe **0,55** (CI95 0,21–0,87), MaxDD −23,5%; **không thắng 60/40 một cách phân biệt được**; Deflated Sharpe 0,87 (<0,95 đặt trước); suy giảm theo thời gian. Dùng như **lớp đa dạng hoá/bảo hiểm đuôi**, không phải nguồn lợi nhuận độc lập. Kỳ vọng thực tế: Sharpe 0,3–0,5, ~30% số năm âm. | `research/MULTI_ASSET_BACKTEST.md` |
| Momentum cổ phiếu VN | Có lãi sau chi phí nhưng **không hơn thị trường**: Sharpe 0,21 (CI −0,40…+0,88), MaxDD **−58,8%**; không phát hiện alpha; **không qua** kiểm định (Deflated Sharpe 0,24). Mua-giữ E1VFVN30 đơn giản hơn và không tệ hơn. Dùng danh sách VN100 hiện tại áp ngược quá khứ làm Sharpe nhảy ảo lên 0,58 (thiên lệch sống sót). **Không triển khai** vào mô phỏng. | `research/VN_BACKTEST.md` |
| Ý kiến chuyên gia/COT | Không nguồn nào vượt baseline (0/99); COT liên quan giá cùng tuần nhưng không dự báo tuần sau. | `EXPERT_TRACKRECORD.md`, `research/INFO_SIGNALS_STUDY.md` |
| Giao dịch quanh tin | Không đo được spread/slippage thật → mặc định **tránh quanh tin** (cửa sổ rủi ro). | `research/INFO_SIGNALS_STUDY.md` |

## 20. Giới hạn của chỉ báo và dữ liệu
1. Chỉ báo mô tả **quá khứ**, không dự đoán; heat cao không có nghĩa sẽ tăng hay giảm.
2. D1 tính theo ngày **UTC** nên có thể thấy một nến D1 ngày Chủ nhật chỉ chứa vài giờ (khác nến sàn đóng 17:00 New York). H4/D1 đôi khi gộp từ H1.
3. Mã ít thanh khoản có thể thiếu nến ở khung nhỏ. Tương quan chỉ có ý nghĩa với cửa sổ đủ dài.
4. Spread/slippage/tick volume trong dữ liệu miễn phí là **xấp xỉ**; khớp lệnh thật sẽ khác.
5. Nguồn miễn phí có thể thay đổi/gián đoạn; có độ ưu tiên và dự phòng ([DATA_SOURCE_PRIORITY.md](DATA_SOURCE_PRIORITY.md)). Hệ thống **không hiển thị tên nguồn** ([UI_NO_SOURCES.md](UI_NO_SOURCES.md)); cần chẩn đoán thì dùng công cụ vận hành.
6. Dữ liệu cũ hoặc thiếu **không kích hoạt cảnh báo**; mẫu ngắn hiển thị "n/a".

---
# PHẦN D — HỎI ĐÁP VÀ XỬ LÝ SỰ CỐ

## 21. FAQ

**Hệ thống có đặt lệnh cho tôi không?** Không. Không có nút mua/bán và không có mã đặt lệnh. Đây là cố ý ([ADR-004](ADR/ADR-004-chi-doc-truoc-thuc-thi-sau-cong-phap-ly-g1-g3.md)).
**Master có thấy mật khẩu MT của tôi không?** Không. Hệ thống không bao giờ thu mật khẩu giao dịch/investor.
**Master thấy gì của tôi?** Số dư/equity/vị thế/lệnh chờ/lịch sử đã đóng của tài khoản bạn đã ghép EA; thao tác "xem như khách" của master có lý do, có hạn 30 phút và được ghi audit.
**Tôi có thấy tài khoản của khách khác không?** Không (kiểm bằng test chống IDOR).
**Vì sao cảnh báo của tôi không kêu?** Kiểm tra: dữ liệu mã đó có đang mới không (huy hiệu tuổi); luật còn hạn/chưa tắt sau "một lần"; điều kiện AND chưa đủ; dữ liệu cũ → "không rõ" nên không kích hoạt.
**Vì sao tôi thấy "chưa đủ mẫu"?** n < 30 quan điểm độc lập — cố ý, xem mục 7.
**Giá đứng yên?** Cuối tuần/ngoài giờ thị trường là bình thường (crypto thì không).
**Link không mở được?** Đường hầm đã đổi địa chỉ → nhờ người vận hành lấy link mới (mục 1).
**Con số của tôi khác số của sàn?** Hệ thống dùng snapshot của EA (cách vài giây–phút) và công thức riêng; **số của sàn là chuẩn**.
**Có chạy trên điện thoại không?** Có: client-ui là PWA; web master cũng thích ứng điện thoại.

## 22. Bảng xử lý sự cố (người dùng)

| Hiện tượng | Thử |
|---|---|
| Link không mở được | Địa chỉ tunnel đã đổi → lấy link mới (mục 1) |
| Quay về trang đăng nhập liên tục / "hết phiên" | Phiên hết hạn (master 12 giờ/2 giờ rảnh; client 7 ngày/48 giờ); đăng nhập lại. Cookie yêu cầu HTTPS: dùng đúng link `https://…trycloudflare.com`, không dùng IP thuần |
| "ID hoặc mật khẩu không đúng" | Thông báo chung cố ý. Kiểm tra nền tảng (mt4/mt5), số tài khoản, passcode. Sau 5 lần sai bị khoá 15 phút |
| Master: yêu cầu bật TOTP (403 `totp_required`) | Bật 2FA ở trang Phiên & thiết bị rồi thử lại |
| Chỉ thấy 0 tài khoản (master phụ) | Chưa được giao nhóm/phạm vi — nhờ master |
| "Mất kết nối" kéo dài | F5 tải lại; vẫn vậy báo người vận hành |
| Trang Phân tích trống | Chu kỳ đầu cần ~10 giây sau khi khởi động |
| Lỗi 502/503 | Một service đang khởi động lại; thử lại sau 1 phút |
| Tài khoản hiện "EA offline" | Terminal MT tắt/mất mạng; mở lại terminal, xem tab Experts (bảng trạng thái mục 16); kiểm tra đồng hồ máy (lệch > 120 s sẽ bị 401) |
| Ghép cặp bị `rejected` | Mã hết hạn (7 ngày) hoặc dùng rồi → xin mã mới |
| Thông báo đẩy không tới | Chưa bật Web Push/chưa cấp quyền/ứng dụng chưa "thêm vào màn hình chính" (iOS) |
| Số liệu mô phỏng "n/a" | Mẫu quá ngắn — cố ý |
| Giá cổ phiếu có cú nhảy giả | Giá thô chưa điều chỉnh thưởng/chia tách |

Hết. Việc kỹ thuật (log, deploy, sao lưu, thêm khoá API, thêm tài khoản MT cho master…) → [VAN_HANH.md](VAN_HANH.md). Kiến trúc → [KIEN_TRUC.md](KIEN_TRUC.md).
