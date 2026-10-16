-- Tín hiệu kịch bản Sell do service `pattern-engine` phát (KB-1..KB-4). Idempotent. CHỈ thông tin/paper, không có lệnh thật.
-- Mỗi (setup_id, symbol, tf, state) tối đa 1 hàng: vòng đời forming -> armed -> triggered | invalid, replay/restart không tạo trùng.
CREATE TABLE IF NOT EXISTS pattern_signals (
  id bigserial PRIMARY KEY,
  setup_id text NOT NULL,                       -- 'KB-2:<ts đáy neo>:<ts đỉnh hồi>' ...
  pattern text NOT NULL,                        -- KB-1 | KB-2 | KB-3 | KB-4
  symbol text NOT NULL,
  tf text NOT NULL,
  state text NOT NULL CHECK (state IN ('forming','armed','triggered','invalid')),
  side text NOT NULL DEFAULT 'sell',
  score real NOT NULL,                          -- 0..100 chất lượng setup (chỉ để xếp hạng)
  bar_ts timestamptz NOT NULL,                  -- ts_open của nến ĐÃ ĐÓNG làm đổi trạng thái
  ts timestamptz NOT NULL,                      -- lúc nến đóng (tín hiệu được biết)
  levels jsonb NOT NULL DEFAULT '{}'::jsonb,    -- entry/sl/tp_1r.. neckline/support... (chỉ gợi ý)
  steps jsonb NOT NULL DEFAULT '[]'::jsonb,     -- checklist [{id,label,ok,detail}]
  reason text,                                  -- lý do khi invalid
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (setup_id, symbol, tf, state)
);
CREATE INDEX IF NOT EXISTS pattern_signals_sym_tf_idx ON pattern_signals (symbol, tf, bar_ts DESC);
CREATE INDEX IF NOT EXISTS pattern_signals_pat_state_idx ON pattern_signals (pattern, state, bar_ts DESC);
CREATE INDEX IF NOT EXISTS pattern_signals_bar_ts_idx ON pattern_signals (bar_ts DESC);
-- Gateway/dịch vụ đọc bằng role chỉ-đọc ts_ro (nếu đã tạo).
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ts_ro') THEN
    GRANT SELECT ON pattern_signals TO ts_ro;
  END IF;
END $$;
