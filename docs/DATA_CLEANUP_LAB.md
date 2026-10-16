# DATA_CLEANUP_LAB — dữ liệu lab lẫn trong DB thật + migration đơn vị giá VN

Trạng thái: **ĐỀ XUẤT, chưa chạy gì**. Truy vấn nhận diện đã chạy (chỉ SELECT) trên `tradingsys-timescaledb-1` lúc 2026-10-11 ~11:40 UTC.
Chạy: `docker exec -i tradingsys-timescaledb-1 psql -U ts -d ts` (dán từng khối).

## 1. Cách nhận diện dữ liệu lab (kết quả thật)

| Bảng | Điều kiện nhận diện | Số dòng | Ghi chú |
|---|---|---|---|
| `bars` | `source LIKE 'mt4:%' OR source LIKE 'mt5:%'` | 350 | `mt4:demo-mt4-01` EURUSD H4 ×50 (2021-04-26→05-06); `mt5:demo-mt5-01` EURUSD ×300 (D1/H4/H1/M15/M5/M1 ×50, 2024-06-11→2024-08-21). Cả hai đều ts cũ (lab). Nguồn thật (`dukascopy`, `frankfurter`, `vnstock`) không bị dính |
| `quotes` | `source LIKE 'mt%:demo-%'` (hoặc `ts < '2025-01-01'`) | 2 | `mt4:demo-mt4-01` ts 2011-04-14, `mt5:demo-mt5-01` ts 2024-08-23. 3 dòng `frankfurter` là thật |
| `account_snapshots` | `account_id IN ('demo-mt4-01','demo-mt5-01')` | 32 + 1755 | ts đều là hôm nay (2026-10-11) — **đây là tài khoản DEMO đang chạy liên tục từ lab (MT agent), không phải dữ liệu 2024**; không có snapshot năm 2024. Chỉ xoá nếu bạn coi demo là lab (nên: tách bằng tiền tố `demo-` ở dashboard thay vì xoá) |
| `alerts` | `tags::text ILIKE '%demo-mt%' OR title ILIKE '%demo-mt%' OR body ILIKE '%demo-mt%'` | 20 | cảnh báo heartbeat/trade_allowed của 2 tài khoản demo (10:14→11:22 UTC) |

Nguyên nhân bars/quotes 2021/2024: EA/agent lab gửi bar/quote lịch sử (ts theo đồng hồ server demo) qua mt-bridge. mt-bridge nhãn `source = "<platform>:<account_id>"` nên **luôn lọc được bằng `source LIKE 'mt%:%'`**. Dữ liệu giá thật không dùng nguồn này.
Phòng tái diễn: đặt tiền tố `demo-` cho account demo (đã đúng) và lọc `source LIKE 'mt%:demo-%'` ở API/dashboard; hoặc không cho EA lab gửi bar/quote lịch sử vào mt-bridge production (dùng stack lab riêng).

## 2. Backup trước khi xoá (bắt buộc)

```sql
-- bảng lưu trữ trong schema `archive` (không ảnh hưởng hypertable); tạo 1 lần
CREATE SCHEMA IF NOT EXISTS archive;
CREATE TABLE archive.bars_lab_20261011 AS
  SELECT * FROM bars WHERE source LIKE 'mt4:%' OR source LIKE 'mt5:%';
CREATE TABLE archive.quotes_lab_20261011 AS
  SELECT * FROM quotes WHERE source LIKE 'mt%:demo-%';
CREATE TABLE archive.alerts_demo_20261011 AS
  SELECT * FROM alerts
  WHERE tags::text ILIKE '%demo-mt%' OR title ILIKE '%demo-mt%' OR body ILIKE '%demo-mt%';
-- (tuỳ chọn, chỉ khi quyết định xoá snapshot demo)
CREATE TABLE archive.account_snapshots_demo_20261011 AS
  SELECT * FROM account_snapshots WHERE account_id IN ('demo-mt4-01','demo-mt5-01');

SELECT 'bars' t, count(*) FROM archive.bars_lab_20261011
UNION ALL SELECT 'quotes', count(*) FROM archive.quotes_lab_20261011
UNION ALL SELECT 'alerts', count(*) FROM archive.alerts_demo_20261011;   -- kỳ vọng 350 / 2 / 20
```
Backup ra file ngoài DB (khuyến nghị): `docker exec tradingsys-timescaledb-1 pg_dump -U ts -d ts -n archive -Fc > /root/backup/archive_lab_20261011.dump`.

## 3. Xoá (chỉ chạy sau khi duyệt; đã gói trong transaction, kiểm đếm trước khi COMMIT)

```sql
BEGIN;
DELETE FROM bars   WHERE source LIKE 'mt4:%' OR source LIKE 'mt5:%';          -- kỳ vọng DELETE 350
DELETE FROM quotes WHERE source LIKE 'mt%:demo-%';                            -- kỳ vọng DELETE 2
DELETE FROM alerts WHERE tags::text ILIKE '%demo-mt%' OR title ILIKE '%demo-mt%' OR body ILIKE '%demo-mt%';  -- DELETE 20
-- chỉ khi coi snapshot demo là lab (xem mục 1): 
-- DELETE FROM account_snapshots WHERE account_id IN ('demo-mt4-01','demo-mt5-01');
SELECT count(*) FROM bars WHERE source LIKE 'mt%:%';   -- phải = 0
COMMIT;   -- hoặc ROLLBACK;
```
Không dùng `TRUNCATE` trên hypertable; không xoá theo `ts < '2025-01-01'` đơn thuần (có thể dính dữ liệu D1 thật nếu sau này backfill sâu).
Hoàn tác: `INSERT INTO bars SELECT * FROM archive.bars_lab_20261011;` (tương tự các bảng khác).

## 4. Migration đơn vị giá cổ phiếu VN (đi kèm bản market-collector mới)

Bản mới chuẩn hoá giá vnstock về **VND thật** (nguồn trả nghìn đồng, nhân 1000). Dữ liệu cũ trong DB vẫn là nghìn đồng (VNM 57,7) → phải nhân ×1000 **một lần**, cùng lúc deploy collector:

```sql
-- đếm trước (kỳ vọng ~ 15+ dòng D1 của VN:VNM/FPT/VCB; tất cả c < 1000)
SELECT symbol, count(*), min(c), max(c) FROM bars WHERE source='vnstock' AND symbol LIKE 'VN:%' GROUP BY symbol;

BEGIN;
UPDATE bars SET o=o*1000, h=h*1000, l=l*1000, c=c*1000
WHERE source='vnstock' AND symbol LIKE 'VN:%' AND h < 1000;   -- điều kiện an toàn: chạy lại không nhân đôi (giá VND thật ≥ 1000)
SELECT symbol, count(*), min(c), max(c) FROM bars WHERE source='vnstock' AND symbol LIKE 'VN:%' GROUP BY symbol;  -- VNM ~57.000-58.000
COMMIT;
```
Thứ tự: (1) backup `CREATE TABLE archive.bars_vn_20261011 AS SELECT * FROM bars WHERE source='vnstock';` (2) build+up market-collector mới (3) chạy UPDATE ngay sau khi collector mới lên (bar mới đã là VND nên điều kiện `h < 1000` bỏ qua chúng). Nếu bar phát giữa (2) và (3) đã là VND, UPDATE không đụng tới.
Kiểm giá thật: VNM đóng cửa ~57.200 (06/10), 58.000 (07/10) theo CafeF/Vietstock — khớp DB 57,7–57,9 nghìn đồng; số "68,490" thấy ở web-ui không khớp giá thị trường hiện nay (nên kiểm nguồn của web-ui: có thể dữ liệu cũ/mẫu hoặc lab).
