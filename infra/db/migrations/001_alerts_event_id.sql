-- Idempotency cho alerts theo Event.id (storage-writer dùng ON CONFLICT (event_id)).
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS event_id text;
CREATE UNIQUE INDEX IF NOT EXISTS alerts_event_id_uq ON alerts (event_id);
