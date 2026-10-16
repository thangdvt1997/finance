-- Bản tin thị trường do LLM cục bộ tóm tắt (service briefing). Idempotent. Chỉ lưu VĂN BẢN bản tin + danh sách mục trích dẫn (tiêu đề + liên kết), KHÔNG tên nguồn.
CREATE TABLE IF NOT EXISTS briefings (
  id uuid PRIMARY KEY,
  edition text NOT NULL CHECK (edition IN ('morning','close')),
  scope text NOT NULL CHECK (scope IN ('vn','intl')),
  for_date date NOT NULL,                              -- ngày theo giờ VN
  generated_at timestamptz NOT NULL,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  status text NOT NULL CHECK (status IN ('llm','fallback')),   -- fallback = bản mẫu không LLM
  model text NOT NULL,
  runtime text NOT NULL,
  latency_ms integer,
  prompt_tokens integer,
  completion_tokens integer,
  title text NOT NULL,
  headline text NOT NULL,
  body jsonb NOT NULL,                                 -- headline, points[{text,cites}], watch[], mood, disclaimer
  context jsonb NOT NULL,                              -- items[{n,kind,title,href,ts,symbols}], stats
  quality jsonb NOT NULL DEFAULT '{}'::jsonb,          -- kết quả hậu kiểm: số ý thô/giữ/loại + lý do, tin bị chặn, tốc độ
  disclaimer text NOT NULL
);
CREATE INDEX IF NOT EXISTS briefings_gen_idx ON briefings (generated_at DESC);
CREATE INDEX IF NOT EXISTS briefings_key_idx ON briefings (scope, edition, generated_at DESC);
