-- 020: vai "expert" (Lop hoc AI: day AI + chay test paper; khong co du lieu tai khoan, khong cau hinh he thong). Idempotent.
ALTER TABLE portal_users DROP CONSTRAINT IF EXISTS portal_users_role_check;
ALTER TABLE portal_users ADD CONSTRAINT portal_users_role_check CHECK (role IN ('master','client','support','analyst','auditor','expert'));
