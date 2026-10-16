-- Cot mo rong cho lich kinh te: nhom ban phat hanh, nguon forecast/actual, surprise (news-collector lam giau).
-- Idempotent. Ap xong moi bat STORAGE_CALENDAR_EXTRA=true (storage-writer). api-gateway tu phat hien cot (khong can cau hinh).
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS extra jsonb;
