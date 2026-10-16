# C2: regime, AI analyst, đồng thuận (2026-10-15)
Chỉ đọc/paper; không đặt lệnh. Mã: `services/ai-trading/research/regime_research.py` (chạy lại bằng hmmlearn+sklearn trên VPS), `services/ai-trading/src/ai_trading/c2.py`, `services/briefing/src/briefing/analyst.py`.

## Regime (HMM 3 trạng thái lọc nhân quả + k-means; D1; 9 mã: EURUSD GBPUSD USDJPY XAUUSD XAGUSD US500 US30 USTEC DE40)
- Huấn luyện 70% đầu của train; đánh giá ngoài mẫu: holdout (30% cuối train) và val. Test khoá KHÔNG dùng cho số đo (chỉ suy trạng thái hiện tại bằng mô hình đóng băng). Null: dịch vòng nhãn 2.000 lần.
- Kết quả: HMM bền (~26 ngày/trạng thái; k-means ~9). Dự báo biến động 5 ngày kế khác ngẫu nhiên ở 9/9 mã (holdout dài) nhưng 2/9 (val ngắn); HMM hơn đường cơ sở tercile-vol20 ở 3/9 (holdout), 6/9 (val). Theo-xu-hướng trong từng regime: 0/28 ô |t|>2. Kết luận: regime = công cụ rủi ro/bật-tắt kịch bản, KHÔNG dự báo hướng. Không có BTCUSD trong kho lịch sử.
- Hiện vật: `docs/research/regime/summary.json`. API: `/v1/ai-trading/regime[?symbol=]` (client: rút gọn, không chi tiết đánh giá).

## Đồng thuận
`/v1/ai-trading/consensus[?symbol=]`: đặc trưng [net, đồng thuận, số nguồn, tỉ lệ nguồn đủ mẫu] + độ tin cậy; hiện 10/122 nguồn đủ mẫu, 0 vượt ngẫu nhiên (FDR 10%) -> "chưa chứng minh". Chưa backtest làm bộ lọc (thiếu lịch sử). Nhãn có tên nguồn bị loại.

## AI analyst
`/v1/ai-trading/analyst?symbol=` (chỉ master -> service briefing). Ngữ cảnh đánh số (kỹ thuật D1, regime, đồng thuận, kịch bản đang hình thành với bước đạt/chưa đạt, lịch, tin); mục có tên nguồn bị loại. LLM llama.cpp dùng chung, không công cụ/URL, JSON theo grammar, chỉ viết các ý (tiêu đề do mã sinh). Hậu kiểm tất định: trích dẫn, số/mã khớp mục trích, chặn đảo dấu tăng/giảm, từ cấm (mua/bán ngay, chắc chắn, đảm bảo...), dự báo, URL, tên nguồn. Trả ngay bản mẫu tất định (llm_pending=true), sinh bản LLM nền (~150 giây, timeout 270 giây, bỏ qua nếu LLM đang bận bản tin), cache 10 phút. Nhãn "AI tạo, không phải lời khuyên".
