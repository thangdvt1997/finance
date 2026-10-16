# nlp — làm giàu tin (sentiment, symbols, chủ đề, mức quan trọng, tóm tắt trích xuất)

READ-ONLY: chỉ đọc `news.items`, chỉ phát `news.enriched` (+ `alerts.out` khi sentiment đảo chiều). Không LLM sinh văn bản, không tool, không lệnh giao dịch.
Nội dung tin là DỮ LIỆU không tin cậy: chỉ đi qua tokenizer -> bộ phân loại -> nhãn; tóm tắt chỉ trích câu có sẵn.

## Luồng
`news.items` --(group `nlp`, hàng đợi có giới hạn, lô <= 32)--> ONNX Runtime CPU --> `news.enriched`
- (1) sentiment -1..1 + nhãn + confidence, theo ngôn ngữ (`lang`; thiếu thì đoán theo dấu tiếng Việt);
- (2) symbols: hợp của symbols collector đã gắn + từ điển `config/entities.yaml` (tiền tệ, vàng/bạc/dầu/khí/đồng, chỉ số, NHTW, BTC/ETH, ~90 mã VN viết hoa, cashtag `$XYZ`);
- (3) chủ đề (`config/topics.yaml`: lãi suất, lạm phát, việc làm, địa chính trị, thuế quan, năng lượng, doanh nghiệp, xếp hạng tín nhiệm...) + `importance` low|med|high (+ `importance_score`);
- (4) `extract`: 1-2 câu trích xuất bằng TextRank (chỉ khi `summary` dài >= 400 ký tự); mặc định bật, tắt bằng `NLP_SUMMARY=false`;
- (5) tổng hợp theo symbol cửa sổ 1h/24h -> gauge `nlp_symbol_sentiment{symbol,window}`; alert `alerts.out` khi trung bình 1h đổi dấu so với nền (24h trừ 1h) với chênh >= 0,5, đủ mẫu (>=3 tin/1h, >=6 tin nền), tin còn mới (<2h, bỏ qua khi backfill), cooldown 6h/symbol, `dedupe_key = nlp:flip:<symbol>:<up|down>:<yyyymmddhh>`.
- Idempotent theo `url + model_version` (khoá Redis `nlp:done:*`, TTL 30 ngày); đổi model/phiên bản -> xử lý lại và ghi đè.
- Backpressure: hàng đợi nội bộ `NLP_QUEUE_MAX`=256; reader dừng đọc khi processor chưa kịp. At-least-once (ack sau khi publish), khởi động đọc lại pending của chính mình, định kỳ `Bus.reclaim` message mồ côi; payload hỏng -> `dlq`.
- Bỏ qua nguồn dữ liệu có cấu trúc (`NLP_SKIP_SOURCES=cot,sec13f`).

## Mô hình đã chọn (kiểm chứng 2026-10-11)
| Ngôn ngữ | Model | Kích thước đĩa | License | Ghi chú |
|---|---|---|---|---|
| en | **FinBERT** `ProsusAI/finbert` qua bản ONNX int8 `Xenova/finbert` (`onnx/model_quantized.onnx`, 110MB, tải thẳng không cần torch) | 111MB | Apache-2.0 (repo GitHub ProsusAI/finBERT; thẻ HF không khai báo license) | BERT-base tinh chỉnh trên Financial PhraseBank |
| vi | **ViSoBERT** `5CD-AI/Vietnamese-Sentiment-visobert` (XLM-R tokenizer, không cần tách từ) tự xuất ONNX int8 bằng `scripts/export_onnx.py` | 99MB | Thẻ HF KHÔNG khai báo license (base `uitnlp/visobert` cũng không) — kiểm tra trước khi dùng thương mại | huấn luyện trên review/mạng xã hội, không phải tin tài chính |
| fallback | VADER (MIT) + từ vựng tài chính en/vi tự biên (`models.FIN_EN/FIN_VI`) | 0 | MIT / tự viết | KHÔNG dùng Loughran-McDonald vì giấy phép thương mại hạn chế. `model_version=lexicon-vader-fin@1` |

Đã thử và loại: `lxyuan/distilbert-base-multilingual-cased-sentiments-student` (Apache-2.0, ONNX có sẵn, 135M): trên mẫu thật cho "negative" gần như mọi câu (acc3 en 0,4 / vi 0,5) -> bỏ. PhoBERT-sentiment (`wonrax/...`, MIT) cần tách từ VnCoreNLP (Java) -> quá nặng. `Kenpache/multilingual-financial-sentiment-v2` XLM-R large 560M, không có tiếng Việt -> quá nặng. Không có model sentiment tài chính tiếng Việt công khai nào tìm được trên HF (2026-10-11).
`NLP_MODEL_OTHER=multi-distilbert` có trong REGISTRY nhưng KHÔNG khuyến nghị; ngôn ngữ khác `en`/`vi` mặc định đi bằng từ điển.
Hybrid tiếng Việt (ViSoBERT trộn từ vựng tài chính, `NLP_VI_HYBRID=true`) đã đo: không tốt hơn model đơn trên tập giữ riêng -> mặc định TẮT.

## Hiệu chỉnh sentiment tiếng Việt (NLP-VI, 2026-10-16)
Vấn đề: ViSoBERT (huấn luyện trên review) gán positive tin cậy cao cho câu VI trung tính ("Hôm nay là thứ ba" +0,999). Logit đo thực tế cho thấy model sai TỰ TIN (logit positive 5,7 vs neutral -1,7) nên temperature scaling/ngưỡng margin KHÔNG sửa được; chỉ có luật từ khoá hiệu quả.
`models.ViCalibrator` (chỉ bọc model VI, EN không đổi): (1) câu không chứa từ khoá cảm xúc/hướng giá nào trong `config/vi_cues.yaml` (khớp không dấu, theo ranh giới từ, sửa được không cần đổi mã) -> neutral; (2) có từ khoá -> giữ nguyên kết quả model, tuỳ chọn temperature `NLP_VI_CAL_TEMP` (mặc định 1.0) và `NLP_VI_CAL_MARGIN` (mặc định 0 = tắt). Tắt toàn bộ: `NLP_VI_CAL=false`. `model_version` có hậu tố `+vical@1`.
Bộ kiểm: `tests/data/vi_sentiment_cases.json` (40 câu viết tay: 14 neutral / 13 positive / 13 negative; 30 dev dùng để chọn tham số, 10 giữ lại không dùng). Test `tests/test_vi_calibration.py` chạy model thật nếu có trong `NLP_MODEL_DIR`, không thì dùng logits đã đo (`vi_logits_fixture.json`).

| Tập | Cấu hình | acc | macro-F1 | P/R/F1 negative | P/R/F1 neutral | P/R/F1 positive |
|---|---|---|---|---|---|---|
| dev (30) | trước | 0,60 | 0,60 | 0,73/0,80/0,76 | 0,71/0,50/0,59 | 0,42/0,50/0,45 |
| dev (30) | sau | 0,70 | 0,70 | 0,73/0,80/0,76 | 0,80/0,80/0,80 | 0,56/0,50/0,53 |
| giữ lại (10) | trước | 0,70 | 0,71 | 1,0/1,0/1,0 | 0,67/0,50/0,57 | 0,50/0,67/0,57 |
| giữ lại (10) | sau | 0,90 | 0,90 | 1,0/1,0/1,0 | 0,80/1,0/0,89 | 1,0/0,67/0,80 |

Giới hạn (trung thực): n rất nhỏ (30 + 10), sai số lớn (±15 điểm %); cải thiện đến từ lớp neutral, positive vẫn yếu (model nhầm positive/negative với vài tin tài chính, vd "nợ xấu giảm mạnh" bị gán negative; "Bộ Tài chính tổ chức hội nghị..." vẫn positive vì có từ khoá). Câu trung tính CÓ chứa từ khoá (vd "lãi suất tăng/giảm" kiểu tin số liệu) vẫn do model quyết. Luật từ khoá là thủ công: câu cảm xúc không dùng từ trong danh sách sẽ bị hạ về neutral. Thử margin/T trên dev chỉ lệch ±1 câu (nhiễu) nên giữ mặc định tối thiểu.

## Benchmark thật (VPS <VPS_IP>, container `python:3.12-slim`, `--cpus 4 --memory 6g`, `NLP_THREADS=3`, max_len=96)
Tập mẫu: 10 tiêu đề en (`scripts/sample_headlines.json`) + 10 vi + 11 vi giữ riêng (`sample_vi_heldout.json`, không dùng để chỉnh từ điển), đều lấy từ DB tin thật của hệ thống, nhãn do người đánh giá thủ công (cực tính theo giọng văn thị trường). **n rất nhỏ -> sai số ±15 điểm %, chỉ mang tính định hướng, không phải đánh giá thống kê.**

| Model / tập | acc 3 lớp | acc cực tính (bỏ neutral) | trễ 1 tin p50 / p95 | thông lượng lô 32 | RSS đỉnh |
|---|---|---|---|---|---|
| FinBERT int8 / en (10) | 0,70 | 0,71 | 10,1 / 14,4 ms | 94 tin/s | 270MB |
| ViSoBERT int8 / vi (10) | 0,50 | 0,50 | 10,6 / 16,4 ms | 83 tin/s | 465MB |
| ViSoBERT int8 / vi giữ riêng (11) | 0,64 | 0,78 | 12,5 / 14,7 ms | 92 tin/s | |
| ViSoBERT fp32 / vi (10) | 0,50 | 0,50 | 17,2 / 24,4 ms | 60 tin/s | 722MB (390MB đĩa) |
| ViSoBERT int8 + từ vựng tài chính / vi giữ riêng | 0,55 | 0,67 | ~12,6 ms | 95 tin/s | |
| Từ điển (VADER+FIN) / en (10) | 0,80* | 0,71* | 0,1ms | 16000 tin/s | |
| Từ điển / vi (10) / vi giữ riêng (11) | 0,90* / 0,73 | 0,88* / 0,67 | 0,1ms | | |
| FinBERT trên tiếng Việt (để so) | 0,20 | 0,00 | | | -> FinBERT chỉ dùng cho en |
(* từ điển được viết sau khi xem các mẫu en/vi (10) nên số đó lạc quan; số "giữ riêng" 0,73 là trung thực hơn.)
Parity: ONNX fp32 vs PyTorch lệch logit 3e-6 (khớp). int8 động lệch logit tới 0,77 và KHÔNG khớp argmax ở 1/3 câu thử, nhưng acc trên 10 câu vi bằng fp32 (0,50 = 0,50; fp32 chưa đo trên tập giữ riêng) -> giữ int8 vì nhanh hơn ~1,7 lần, nhẹ hơn 4 lần; nếu cần chắc chắn hơn dùng `NLP_MODEL_VI=visobert-fp32` (xuất bằng `export_onnx.py --no-quant --out /models/visobert-fp32`).

Nhận xét thẳng: FinBERT tốt với tiêu đề en kiểu thị trường (sai chủ yếu ở câu trung tính-có-số-liệu và câu "ẩn ý"); ViSoBERT yếu hơn (thường đoán "positive" cho từ "giảm"/"tăng" ngữ cảnh khác nhau) — sentiment tiếng Việt nên coi là gợi ý, cần dữ liệu gán nhãn tin tài chính VN để tinh chỉnh sau (PLAN tiếp theo).

**Đo toàn dịch vụ** (image thật build từ Dockerfile, Redis tạm, 1000 tin mới nhất trong DB gồm tiêu đề + summary, 525 en/475 vi): 1000/1000 làm giàu trong **47,1s = 21 tin/s** (CPU-bound, ~1,3s/lô 30 tin vì văn bản dài hơn tiêu đề), pending còn 0, RAM container 773MB, image **291MB** (không torch). Tải lần đầu: model nạp 0,3-0,6s khi đã có trong volume.

## Chạy thật / kiểm chứng
```bash
# trên VPS, trong container tạm (xoá sau khi xong), KHÔNG đụng Redis/DB:
docker run --rm --name nlp-smoke-1 --cpus 4 --memory 6g -v nlp-smoke-models:/models -v $PWD:/src:ro python:3.12-slim \
  sh -c "cp -r /src /w && pip install -q /w/libs/common /w/services/nlp && python /w/services/nlp/scripts/smoke_real.py --models finbert,visobert"
docker volume rm nlp-smoke-models
```
ViSoBERT phải xuất ONNX trước (1 lần, cần torch tạm ~200MB, không nằm trong image chạy): `scripts/export_onnx.py` hoặc `docker compose ... --profile export run --rm nlp-export` (xem dưới).
`NLP_TEST_MODEL_DIR=/đường/dẫn/models pytest` chạy thêm test model thật (mặc định bỏ qua).

## Triển khai (chưa deploy — theo yêu cầu)
Khối `nlp` + `nlp-export` nằm trong `infra/docker-compose.tools.yml` (`cpus: 4`, `mem_limit: 6g`, `read_only`, `cap_drop: ALL`, volume `nlp-models`).
```bash
cd infra
C="docker compose -p tradingsys --env-file .env -f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.tools.yml"
$C --profile export run --rm nlp-export        # 1 lần: xuất ViSoBERT -> volume nlp-models (cần mạng tới HF + download.pytorch.org)
$C up -d --build nlp                            # lần đầu tự tải FinBERT ONNX (110MB) vào volume
# (tuỳ chọn) lưu kết quả vào DB: áp infra/db/migrations/002_news_enrichment.sql, rồi đặt STORAGE_ENRICH_EXTENDED=true cho storage-writer và up lại nó.
```
Không có cột mở rộng: storage-writer vẫn cập nhật `sentiment` + hợp nhất `symbols` của `news_items` theo `url` (an toàn, không cần migration).
Nên thêm scrape Prometheus `nlp:8000` (infra/prometheus/prometheus.yml) và kiểm tra Gatus `/healthz`.
Rollback: `NLP_ENABLED=false` hoặc dừng container; `news.items` không bị ảnh hưởng (group `nlp` giữ vị trí đọc).

## Cấu hình chính (env)
`NLP_MODEL_EN=finbert`, `NLP_MODEL_VI=visobert` (đặt `lexicon` để chỉ dùng từ điển), `NLP_THREADS=3`, `NLP_BATCH=32`, `NLP_QUEUE_MAX=256`, `NLP_MAX_LEN=96`, `NLP_AUTO_DOWNLOAD=true`, `NLP_ALERT_ENABLED`, `NLP_ALERT_MIN_DELTA=0.5`, `NLP_ALERT_COOLDOWN_S=21600`, `NLP_SKIP_SOURCES`, `NLP_SUMMARY`, `NLP_VI_HYBRID`, `NLP_VI_CAL` (mặc định bật), `NLP_VI_CAL_TEMP`, `NLP_VI_CAL_MARGIN`. Xem `settings.py`.

## Endpoint
`/healthz`, `/metrics` (`nlp_items_total`, `nlp_infer_seconds`, `nlp_batch_size`, `nlp_queue_depth`, `nlp_stream_lag_messages`, `nlp_model_loaded`, `nlp_symbol_sentiment`, `nlp_symbol_news_count`, `nlp_reversal_alerts_total`, `nlp_errors_total`), `/status`, `GET /v1/sentiment[?symbol=]` (cửa sổ 1h/24h trong RAM), `POST /v1/analyze` (thử 1 tiêu đề, không ghi stream).

## Giới hạn đã biết
- Sentiment đo giọng văn bản tin, KHÔNG phải hướng giá; alert chỉ là chỉ báo tham khảo.
- Cửa sổ theo symbol nằm trong RAM: restart làm mất lịch sử 24h (nền alert đầy lại sau ~24h; gauge hồi lại khi backfill).
- Nhận diện thực thể bằng từ điển (không NER): bỏ sót tên công ty ngoài danh sách; mã VN ngoài ~90 mã trong `entities.yaml` cần thêm tay.
- Gauge `nlp_symbol_sentiment` có cardinality theo số symbol (hàng chục-trăm), chấp nhận được.
