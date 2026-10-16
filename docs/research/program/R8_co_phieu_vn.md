# R8 — Cổ phiếu & thị trường Việt Nam (long-only, chỉ tư vấn hướng)

Ngày: 2026-10-15. Mã + số thật: `data/research/program/R8/` (`r8_backtest.py`, `r8_results.json`, `r8_monthly.csv`; gitignore, chạy lại: `python3 -I r8_backtest.py`, ~vài phút). Dữ liệu: VNDirect finfo giá điều chỉnh, 876 mã HOSE gồm cả mã đã hủy niêm yết (nạp ở `/root/research/vn/data/raw`, chi tiết `docs/research/VN_BACKTEST.md`). READ-ONLY/PAPER, không giao dịch thật.

## 0. Kết luận thẳng
1. **Momentum cắt ngang (6 hoặc 12 tháng) KHÔNG có edge** sau chi phí: Sharpe 0,22 (12-1) / 0,27 (6-1) vs top-100 đều 0,24; ΔSharpe −0,02 (CI −0,31…+0,25). Khớp kết quả VN_BACKTEST (tái lập độc lập, engine khác, ra cùng số).
2. **Mọi thứ đều dưới E1VFVN30 mua-giữ** trừ các biến thể low-vol: E1VFVN30 Sharpe 0,40, CAGR 10,9% (từ 2014-12). Momentum thua ETF −3,7%/năm.
3. **Low-vol (và low-vol+momentum) là ứng viên duy nhất đáng ghi nhận, nhưng CHƯA kết luận có edge**: low-vol top-15 Sharpe 0,42, MaxDD −29% (vs −47% rổ đều); low-vol+mom 0,61 (CI 0,02…1,23), hơn rổ đều +0,36 Sharpe (CI +0,04…+0,74). Nhưng đó là cấu hình tốt nhất trong ~6 tín hiệu thử (không hiệu chỉnh đa kiểm định), và so với E1VFVN30 cùng kỳ chỉ +0,21 (CI −0,13…+0,58) — không phân biệt được. Walk-forward trung thực (chọn cấu hình theo Sharpe 36 tháng trước) cho 0,34 vs rổ đều 0,32, ΔSharpe +0,01 → **không thấy lợi thế ngoài mẫu khi phải chọn trước**.
4. **Khuyến nghị hướng**: nếu muốn có cổ phiếu VN thì E1VFVN30/FUEVFVND mua-giữ (rẻ, đơn giản, chi phí ~0). Low-vol là hướng *đáng theo dõi/paper* (giảm MaxDD thật, cơ chế giải thích được) chứ không phải nguồn lợi nhuận đã chứng minh. Không đủ cơ sở để nói "đánh bại thị trường".

## 1. Thực tế thị trường/pháp lý (chỉ tư vấn, đối chiếu văn bản gốc trước khi dùng)
| Hạng mục | Thực tế |
|---|---|
| Thanh toán | T+2 (mua xong chỉ bán được từ chiều T+2, "T+2,5" thực tế; engine VN_BACKTEST mô hình hóa). Rút ngắn T+1 và đối tác bù trừ trung tâm (CCP) đang trong lộ trình nâng hạng; chưa xác nhận được ngày áp dụng từ nguồn tìm được. |
| Biên độ | HOSE ±7%, HNX ±10%, UPCoM ±15% (kiến thức nền, tìm kiếm không xác nhận lại). Khóa trần/sàn làm không mua/bán được — engine đã mô hình. Bước giá HOSE 10/50/100đ; lô 100cp. |
| Bán khống | **Không có** trên thị trường cơ sở; chỉ phái sinh (VN30F). Bán khống/T+0 có kiểm soát nằm trong lộ trình nghiên cứu 2026–2028 (UBCKNN). Hệ quả: chỉ long-only; hiệu ứng "phía thua" của momentum (Q1−Q5) không khai thác được. |
| Thuế/phí | Thuế TNCN chuyển nhượng 0,1% giá bán mỗi lần (Luật TNCN 2025, hiệu lực 1/7/2026 giữ 0,1%; đề xuất 20% trên lãi đã rút). Phí CTCK ~0,1–0,15%/chiều. Cổ tức tiền thuế 5%. |
| Margin | CTCK cho vay ký quỹ trên danh mục được phép, lãi suất cao (~10–13%/năm, kiến thức nền, không xác nhận 2026) → không phù hợp cho chiến lược Sharpe 0,2–0,6. Pre-funding (phải có đủ tiền trước khi mua) là rào cản với nhà đầu tư tổ chức nước ngoài, đã nới từ 11/2024; cá nhân trong nước đã là tài khoản có tiền. |
| Nâng hạng | FTSE Russell xác nhận nâng Vietnam lên Emerging, hiệu lực 21/9/2026, vào chỉ số theo 4 đợt đến 9/2027 (10% → 20% → 35% → 35%). Đây là dòng vốn kỳ vọng 3–5 tỷ USD; **không phải tín hiệu giao dịch** (đã được định giá, và sau 12,7 năm dữ liệu không đo được tác động). |
| ETF | E1VFVN30 (VN30), FUEVFVND (VNDiamond), FUESSVFL: thanh khoản tốt, bước giá 10đ; phí quản lý ~0,65–0,85%/năm (kiến thức nền). E1VFVN30 giá điều chỉnh có trong dữ liệu. |

## 2. Dữ liệu realtime hợp lệ
- **SSI FastConnect Data** (guide.ssi.com.vn): cần có tài khoản giao dịch SSI; đăng ký tại quầy/qua môi giới; sau duyệt tạo ConsumerID/ConsumerSecret/PrivateKey trên iBoard. Có EOD hoặc realtime. **Không tìm được thông tin phí/miễn phí** — hỏi môi giới. Điều kiện này vi phạm "0 đồng" nếu cần nạp tiền/mở tài khoản có phí; mở tài khoản chứng khoán thường miễn phí nhưng cần giấy tờ cá nhân (việc của người dùng).
- **DNSE (Entrade X OpenAPI, openapi.dnse.com.vn)**: có API key/secret, market data + account + order; phạm vi realtime/rate limit phụ thuộc gói tài khoản; cổng trả ECONNREFUSED từ VPS nên chưa xác minh điều kiện miễn phí. Tài liệu chính thức cần đọc: trang developer DNSE. Cảnh báo: cùng key có thể đặt lệnh → chỉ dùng key quyền đọc nếu có, không nạp vào hệ thống paper.
- Hiện đã có: VNDirect finfo (không chính thức, trễ/EOD, tự giới hạn tốc độ) đủ cho nghiên cứu tháng. Intraday realtime hợp lệ cần broker API ở trên → việc của người dùng (mở tài khoản + đăng ký).
- Tuân thủ: dữ liệu realtime của sở là dữ liệu có bản quyền; chỉ dùng cho cá nhân qua kênh broker cấp phép, không phân phối lại, UI không hiển thị tên nguồn (quy tắc STANDING).

## 3. Backtest (2014-02 → 2026-10, 153 tháng, tái lập)
Thiết lập: universe tại thời điểm = top-100 GTGD TB60 phiên, tối thiểu 3 tỷ đ/ngày và ≥200 phiên dữ liệu; **gồm cả mã đã hủy niêm yết** (đóng băng giá cuối); tỷ trọng đều, top-15; rebalance cuối tháng, giao dịch phiên kế tiếp; chi phí = phí 0,15% + trượt giá 0,25%/chiều + thuế 0,1% bán (~0,95% khứ hồi); rf 4,5%. Chỉ số lấy từ lợi suất hàng tháng, bootstrap khối 3 tháng 2.000 lần. Khác VN_BACKTEST: thực thi tháng đơn giản (không mô phỏng T+2 từng lệnh/trần-sàn từng ngày), nên số hơi khác.

| Chiến lược | Sharpe | CI95 | CAGR | Vol | MaxDD | vòng quay/năm (1 chiều) |
|---|---|---|---|---|---|---|
| Momentum 12-1 | 0,22 | −0,38…0,77 | 7,0% | 27,2% | −56% | 3,8 |
| Momentum 6-1 | 0,27 | −0,29…0,79 | 8,4% | 29,9% | −58% | 4,9 |
| Low-vol (vol 252 ngày thấp nhất) | 0,42 | −0,19…1,02 | 10,6% | 16,7% | −29% | 1,9 |
| Low-vol + momentum (xếp hạng gộp) | **0,61** | 0,02…1,23 | 15,4% | 19,4% | −33% | 3,2 |
| Momentum trong nửa vol thấp | 0,53 | −0,07…1,15 | 14,1% | 20,7% | −38% | 3,5 |
| Top-100 đều (benchmark cùng universe) | 0,24 | −0,32…0,77 | 7,7% | 24,4% | −47% | 1,1 |
| Top-30 đều (xấp xỉ VN30, giá tính từ GTGD) | 0,09 | −0,50…0,62 | 3,3% | 26,3% | −56% | 1,4 |
| **E1VFVN30 mua-giữ** (từ 2014-12) | 0,40 | −0,17…1,05 | 10,9% | 19,6% | −43% | — |

(VN30 mua-giữ thật được xấp xỉ bằng E1VFVN30; "top-30 đều" theo GTGD là proxy kém, chứa cổ phiếu đầu cơ.)

**So sánh cặp (bootstrap, ΔSharpe)**
- vs top-100 đều: mom12 −0,02 (−0,31…+0,25); mom6 +0,02; lowvol +0,17 (−0,15…+0,56); lowvol+mom +0,36 (**+0,04…+0,74**); mom-trong-vol-thấp +0,28 (−0,02…+0,61).
- vs E1VFVN30 (cùng kỳ): mom12 −0,25 (−0,68…+0,17), −3,7%/năm; mom6 −0,21; lowvol +0,09 (−0,25…+0,41); lowvol+mom +0,21 (−0,13…+0,58), +4,0%/năm; top-100 đều −0,19.
- Chỉ một CI (lowvol+mom vs rổ đều) loại trừ 0 và đã chọn sau khi thử ~6 tín hiệu → với 5 phép so sánh, ngưỡng Bonferroni không đạt; coi là gợi ý, không phải bằng chứng.

**Nhạy chi phí / thanh khoản / số mã**
- Chi phí ×0/×1/×2: mom12 Sharpe 0,35/0,22/0,09 (CAGR 10,7%/7,0%/3,4%); lowvol 0,52/0,42/0,32. Low-vol chịu chi phí tốt hơn nhờ vòng quay thấp.
- Thanh khoản tối thiểu (GTGD TB60): mom12 Sharpe 0,24 (1 tỷ) / 0,22 (3 tỷ) / 0,18 (10 tỷ) / 0,11 (30 tỷ); lowvol 0,42 (1 tỷ) / 0,42 (3 tỷ) / 0,42 (10 tỷ) — siết thanh khoản không cứu momentum (hiệu ứng dồn ở mã nhỏ, khó giao dịch).
- N=10/15/30 mom12: 0,21/0,22/0,26 (đa dạng hóa hơn = tốt hơn).

**Theo giai đoạn (lợi suất kỳ)**: 2014-17: mom +59%, lowvol +74%, rổ đều +34%, E1 +70%; 2018-19: −14%, +5%, −15%, −12%; 2020-21: +100%, +67%, +159%, +75%; 2022: −51%, −29%, −46%, −33%; 2023-26: +77%, +66%, +61%, +95%. Low-vol thắng ở các giai đoạn giảm (2018-19, 2022) và thua khi thị trường bùng nổ (2020-21, bong bóng) — đúng bản chất phòng thủ, không phải alpha thuần. Momentum sập −51% năm 2022.

**Walk-forward / ngoài mẫu**
- Mỗi tháng chọn (trong 10 cấu hình: 5 tín hiệu × N{15,30}) cái có Sharpe 36 tháng trước cao nhất, 2017-02 → 2026-10 (117 tháng): Sharpe 0,34 (CI −0,33…1,11), CAGR 9,7%, MaxDD −42% vs top-100 đều 0,32 / 10,0% / −47%; ΔSharpe +0,01 (−0,34…+0,41). Cấu hình được chọn đổi liên tục (momlv 43, lowvol+mom 36, lowvol 27…). **Không có lợi thế ngoài mẫu khi chọn tự động.**
- Chọn tốt nhất 2014-19 (lowvol N30, Sharpe 0,76) → 2020-26: 0,39 vs rổ đều 0,40: giữ được, nhưng không hơn.

## 4. Giới hạn trung thực
- 12,7 năm, một chu kỳ bong bóng/sập; sai số Sharpe ±0,6. Mọi CI chứa 0 trừ một phép so sánh đã chọn lọc.
- Mã hủy niêm yết bị đóng băng giá cuối (thực tế thanh lý có thể tệ hơn); low-vol tự tránh được phần lớn rủi ro này nên có thể được lợi hơn thực tế.
- Không mô hình: thuế cổ tức, trần-sàn/T+2 từng lệnh, halt/cảnh báo, margin. Slippage 0,25% là giả định.
- Yếu tố value/quality: không có lịch sử point-in-time hợp lệ (xem VN_BACKTEST §5) → không backtest; không tuyên bố gì.
- ETF: E1VFVN30 chỉ có từ 2014-11/12; FUEVFVND ngắn hơn (không dùng riêng).
- Thị trường VN thay đổi cấu trúc 2026 (nâng hạng FTSE, KRX/CCP, T+1/bán khống tương lai) → quá khứ ít đại diện; low-vol có thể yếu đi khi dòng vốn ngoại thiên về vốn hóa lớn.

## 5. Đề xuất việc tiếp
1. Không đưa momentum VN vào paper. Giữ benchmark thụ động E1VFVN30 làm đối chứng.
2. Nếu muốn thử: paper "low-vol + momentum top-15, hàng tháng" chỉ như ứng viên giảm rủi ro; kiểm lại trên dữ liệu mới theo thời gian (out-of-sample thật), kèm đăng ký trước tiêu chí dừng. Cần nạp ~100 mã vào `md.bars` và luật T+2/trần-sàn vào paper-trader (công lớn).
3. Việc người dùng: mở/đăng ký API broker (SSI/DNSE) nếu cần realtime; xác nhận phí.

Nguồn tra cứu: FTSE nâng hạng (Vietstock 2026-04, World Bank 2026-04-22), thuế 0,1% (thuvienphapluat/luatvietnam), bán khống/T+0 (24hmoney, nhadautu), SSI FastConnect (guide.ssi.com.vn), DNSE (không truy cập được openapi.dnse.com.vn).
