-- Cột mở rộng cho kết quả `nlp` (stream news.enriched). Idempotent. Áp xong mới bật STORAGE_ENRICH_EXTENDED=true.
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS sentiment_label text;
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS sentiment_conf double precision;
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS topics text[] DEFAULT '{}';
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS importance text;
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS nlp_model text;
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS enriched_at timestamptz;
