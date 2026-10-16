from prometheus_client import Counter, Gauge, Histogram

ITEMS = Counter("nlp_items_total", "Tin đã làm giàu", ["lang", "model", "label"])
SKIPPED = Counter("nlp_skipped_total", "Tin bỏ qua", ["reason"])        # duplicate | invalid
ERRORS = Counter("nlp_errors_total", "Lỗi xử lý", ["stage"])
INFER_SECONDS = Histogram("nlp_infer_seconds", "Thời gian suy luận một lô", ["model"],
                          buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30))
BATCH_SIZE = Histogram("nlp_batch_size", "Kích thước lô", buckets=(1, 2, 4, 8, 16, 32, 64, 128))
QUEUE_DEPTH = Gauge("nlp_queue_depth", "Số tin đang chờ trong hàng đợi nội bộ")
LAG = Gauge("nlp_stream_lag_messages", "Tin chưa đọc + đang xử lý của group nlp (xấp xỉ)")
MODEL_LOADED = Gauge("nlp_model_loaded", "1 nếu model ONNX đang dùng cho ngôn ngữ", ["lang", "model_version"])
SYMBOL_SENT = Gauge("nlp_symbol_sentiment", "Sentiment trung bình có trọng số theo symbol", ["symbol", "window"])
SYMBOL_N = Gauge("nlp_symbol_news_count", "Số tin trong cửa sổ", ["symbol", "window"])
ALERTS = Counter("nlp_reversal_alerts_total", "Cảnh báo đảo chiều sentiment đã phát", ["direction"])
LAST_ITEM_TS = Gauge("nlp_last_item_timestamp_seconds", "Unix time tin cuối cùng được làm giàu")
