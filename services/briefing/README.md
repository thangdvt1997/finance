# briefing — bản tin thị trường tiếng Việt do LLM cục bộ tóm tắt

Hai bản tin mỗi ngày (06:15 sáng, 16:30 cuối phiên, giờ VN) × hai phạm vi (Việt Nam, Quốc tế). LLM chỉ **tóm tắt/phân loại** dữ liệu có đánh số; **không** có công cụ, URL, hành động hay lệnh giao dịch. Mọi nhận định có trích dẫn [n] bấm được tới tin gốc. Không hiển thị tên nguồn (dùng `tscommon.sources.scrub_sources`).

## Kiến trúc
```
news_items(ts_ro) + calendar_events + bars D1/analytics + vn_index_daily
        -> context.py  (làm sạch, loại tin nghi chèn chỉ thị, scrub tên nguồn, đánh số [1..N], khung <<<DU_LIEU_nonce>>>)
        -> llm.py      (llama.cpp server, JSON-schema grammar, KHÔNG gửi tools)
        -> verify.py   (hậu kiểm tất định từng ý) -> pipeline.py (hoặc BẢN MẪU không LLM)
        -> store.py    (bảng briefings, role ts_briefing: chỉ SELECT/INSERT) + stream briefing.items + alerts.out (ntfy)
api-gateway GET /v1/briefing/{latest|list|<uuid>}  ->  web-ui #/ban-tin  ->  reporter (báo cáo ngày)
```
- `briefing-llm`: `ghcr.io/ggml-org/llama.cpp:server` (MIT, ghim digest), mạng `ops` (không internet), user 10001, read_only, `cpus: 8`, `mem_limit: 16g`, mô hình ở volume `briefing-models` (:ro).
- `briefing`: Python 512 MB, user 10001, read_only. Lịch chạy nằm trong service (`BRIEFING_SCHEDULE`). Không publish cổng.
- "Cần theo dõi hôm nay" (lịch HIGH + cửa sổ rủi ro tin từ `tscommon.risk_windows`) và "tâm lý chung" (số liệu sentiment thật) do **mã** sinh, không do LLM viết.

## Mô hình đã chọn: Qwen3.5-9B Q4_K_M (Apache-2.0)
Đo thật trên VPS (Xeon Gold 6130, 8 luồng, AVX-512, prompt thật ~3.500 token, ngữ cảnh 8192), `llama.cpp` build 11552:

| Mô hình (GGUF Q4_K_M) | License | Prefill tok/s | Sinh tok/s | 1 bản tin | Chất lượng đối chiếu tay |
|---|---|---|---|---|---|
| Qwen3.5-4B | Apache-2.0 | 55,7 | 7,1 | ~144 s | 7/8 ý qua hậu kiểm nhưng lặp (3 dòng chỉ số liên tiếp), chọn tin kém |
| Qwen2.5-7B-Instruct | Apache-2.0 | 37,5 | 5,0 | ~161 s | chỉ 4/5 ý, ý cụt, tiêu đề rộng |
| **Qwen3.5-9B** | Apache-2.0 | 33,6 | 4,3 | 190–209 s | 7–8 ý/bản, đa dạng chủ đề, bám tin |
| Qwen3-30B-A3B-2507 (18,6 GB) | Apache-2.0 | 34,5 | 4,9 | ~219 s | giàu chi tiết hơn nhưng vượt trần RAM 16 GB (đọc đĩa lặp), đọc nhầm "tín dụng tăng 16,69%" thành lãi suất -> loại |

Bản tin ngày không cần realtime nên chọn 9B (chất lượng tốt nhất trong trần tài nguyên). Đổi mô hình: đặt `BRIEFING_LLM_FILE` + `BRIEFING_LLM_MODEL` trong `infra/.env`, `./deploy.sh "up -d briefing-llm briefing"`. Gemma/Llama không dùng: license có điều khoản hạn chế; Vistral/SeaLLM chưa được thử (chưa khảo sát). Ollama không chọn vì cần daemon + quyền ghi vùng model; llama.cpp server gọn hơn, ép được JSON-schema.

Tải mô hình (1 lần, trên VPS): `curl -L -o <volume>/Qwen3.5-9B-Q4_K_M.gguf https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf` (volume: `docker volume inspect tradingsys_briefing-models`).

## Hậu kiểm tất định (verify.py) — loại ý nếu vi phạm
1. thiếu/sai trích dẫn [n] (n phải tồn tại, ≤4 mục); 2. con số **không có trong chính các mục được trích** (nhận cả cách đọc 1.730 = 1,73 hay 1730); 3. mã/viết tắt IN HOA không có trong mục trích; 4. khuyến nghị mua/bán, mục tiêu giá, "sẽ tăng/có thể giảm", dự đoán; 5. URL/markup/ngoặc lạ; 6. mẫu chỉ thị rò (ignore…, bỏ qua…); 7. tên nguồn; 8. ít chồng lấn từ khoá với mục trích (khi mục là tiếng Việt); 9. trùng ý. Còn < `BRIEFING_MIN_POINTS` (3) ý hợp lệ, hoặc LLM lỗi/quá hạn/JSON sai -> **bản mẫu** (`status=fallback`, ghép tiêu đề tin quan trọng + số liệu). Chốt chặn cuối `leaks_source` từ chối lưu bản có tên nguồn.

## Chống prompt-injection
Tin là dữ liệu không đáng tin: chuẩn hoá NFKC, bỏ zero-width/thẻ HTML/URL/`[n]` giả/dấu khung; tin có mẫu chỉ thị (Anh + Việt) **bị loại hẳn** khỏi ngữ cảnh (không thể trích dẫn; đếm ở `quality.blocked_injection`); phần còn lại nằm trong khung `<<<DU_LIEU_<nonce ngẫu nhiên>>>`; system prompt dặn coi là dữ liệu; đầu ra bị ép JSON-schema, không gửi `tools`, không đường gọi URL; hậu kiểm lọc phần còn sót. Test: `tests/test_sanitize_and_context.py`, `tests/test_pipeline.py` + chạy mô hình thật với tin giả (xem dưới).

## Vận hành
- Chạy tay: `docker exec tradingsys-briefing python -c "import urllib.request,os;print(urllib.request.urlopen(urllib.request.Request('http://localhost:8000/internal/run?edition=morning&scope=all&wait=true',method='POST',headers={'X-Admin-Token':os.environ['BRIEFING_ADMIN_TOKEN']}),timeout=3000).read())"` (`edition=morning|close`, `scope=vn|intl|all`; bỏ `wait=true` để chạy nền; `GET /internal/status` cùng header). `BRIEFING_ADMIN_TOKEN` ở `infra/.env`; chưa đặt -> endpoint trả 503.
- Lần đầu: `bash infra/db/create_briefing_role.sh` (migration `010_briefing.sql` + role `ts_briefing` + `POSTGRES_BRIEFING_PASSWORD`), rồi `./deploy.sh "up -d --build briefing briefing-llm api-gateway reporter web-ui"`.
- Quan sát: metric `briefing_runs_total{scope,edition,status}`, `briefing_run_seconds`, `briefing_points_dropped_total`, `briefing_last_success_timestamp`; luật `BriefingStale` (>30 giờ); Gatus `briefing`.
- Biến: `BRIEFING_SCHEDULE` (mặc định `06:15=morning,16:30=close`), `BRIEFING_LLM_ENABLED=false` (chỉ bản mẫu), `BRIEFING_NOTIFY`, `BRIEFING_MAX_NEWS`. VN close bị bỏ cuối tuần.
- Thông báo: `alerts.out` (tags `briefing`, `ch:ntfy`) -> alert-service -> ntfy; nội dung không có tên nguồn; stream `briefing.items` cho consumer khác. Reporter: mục "Bản tin thị trường (AI tóm tắt)" trong báo cáo ngày.
- Test: `sh infra/ops/run_tests.sh briefing reporter api-gateway` (container tạm trên VPS).

## Kết quả chạy thật (2026-10-12, VPS, Qwen3.5-9B)
4 bản (sáng/cuối phiên × VN/quốc tế) đều `status=llm`, 7–8 ý/bản qua hậu kiểm, 190–209 s/bản (prefill ~105 s + sinh ~100 s), thông báo ntfy `delivered=true`.
Đối chiếu DB: VNINDEX 1735,09 / −0,22% / 121 tăng–170 giảm khớp `vn_index_daily`; tâm lý 24h VN +0,32 (176 tin) khớp truy vấn lại (184 tin, TB 0,30 lúc sau); giá SPY 778,57, BTC 82985,10 khớp `bars`.
Hậu kiểm bắt được: số bịa ("9", "60.000" không có trong mục trích), "[3, 22]" (nay chấp nhận), dự báo CPI ("có thể tăng lên 3,7%" bị loại là dự báo).
Test tiêm chỉ thị với mô hình thật (lần chạy trước khi bổ sung mẫu `[SYSTEM]`/"từ giờ trả lời" vào bộ lọc: tin `[SYSTEM]… HACKED` lọt vào ngữ cảnh nhưng mô hình không làm theo; sau đó đã chặn) (tin giả "Bỏ qua mọi hướng dẫn…", "IMPORTANT SYSTEM MESSAGE…", "[SYSTEM] … HACKED", và tin chuyển tiếp "khuyến nghị mua… giá mục tiêu"): không rò vào đầu ra, 7 ý đều từ tin thật.

### Hạn chế / lỗi đã thấy (trung thực)
- Lỗi **ngữ nghĩa** mà hậu kiểm số không bắt được: lần 30B đọc nhầm tăng trưởng tín dụng là lãi suất; lần 9B gọi giá quỹ ETF SPY là "chỉ số S&P 500" (đã sửa: ngữ cảnh ghi "Giá quỹ ETF SPY"). Nến D1 của ngày đang chạy là nến chưa đóng -> ngữ cảnh ghi "giá gần nhất", không "đóng cửa".
- Lần chạy lại sau sửa (intl cuối phiên): một ý ghép sai hai sự kiện ("các cuộc tấn công của Ukraine vào Yandex **và các cơ sở của Aramco**" — Aramco bị Houthi tấn công, không phải Ukraine); số liệu đúng, trích dẫn tồn tại nên hậu kiểm tất định không bắt được. Đây là rủi ro còn lại: đọc bản tin như tham khảo, bấm [n] để đối chiếu tin gốc.
- Chọn tin dựa điểm NLP: có tin ít liên quan (Bitcoin trong bản VN, UNIQLO). Nhiều ý chỉ là diễn đạt lại tiêu đề, ít phân tích liên kết giữa các tin (có chủ đích, tránh bịa).
- `scrub_sources` thay tên công ty chứng khoán trùng tên nhà cung cấp dữ liệu (ví dụ một công ty chứng khoán trong tin PNJ) -> câu mất tên đó.
- Bản VN không có sự kiện lịch HIGH của VN/US/CN trong cửa sổ -> mục "Cần theo dõi" hiển thị "không có sự kiện".
- 190–209 s/bản trên CPU; chạy tuần tự (khoá) nên 4 bản ≈ 14 phút; cần ≥ 8 lõi rảnh.
