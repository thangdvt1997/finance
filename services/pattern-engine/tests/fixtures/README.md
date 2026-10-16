# Fixture golden test

`xauusd_m15_gcf.csv` — nến M15 (UTC, `ts_open_utc,o,h,l,c,v`) từ 2026-09-18 đến 2026-10-08, ~1290 nến, phủ 3 đoạn ảnh mẫu `plan1/Lệnh Sell.docx`
(21-28/09, 30/09-02/10, 01-06/10 năm 2026).

## Nguồn và LƯU Ý QUAN TRỌNG
- Bảng `bars` trên VPS chỉ có XAUUSD M15 từ 2026-10-04 22:00 UTC (nguồn tick công khai bị chặn 429/timeout từ IP VPS lúc xuất) nên **KHÔNG đủ** cho 3 đoạn ảnh.
- Fixture được xuất từ nguồn công khai có sẵn (Yahoo, chuỗi **GC=F vàng kỳ hạn COMEX**, interval 15m) bằng `tools/yahoo_to_csv.py`, chạy trên VPS.
  GC=F là hợp đồng tương lai nên **giá cao hơn giao ngay ~ +30 điểm** và hình dạng nến có thể lệch chút so với ảnh (giao ngay của sàn). Detector chuẩn hoá theo ATR nên không phụ thuộc mức giá tuyệt đối.
- Khi nguồn tick (Dukascopy) hoạt động lại, chạy `tools/export_fixture.py XAUUSD 2026-09-18 2026-10-08 out.csv` trên VPS để thay fixture bằng nến giao ngay chính xác và chạy lại golden test.

## Ánh xạ giờ ảnh -> UTC
Giờ trên ảnh = giờ sàn = **UTC+3** (đối chiếu: đỉnh 4217 ảnh 1 ↔ GC=F 4251 lúc 12:30 UTC = 15:30 giờ sàn; chênh giá ≈ +30 ổn định ở mọi đỉnh/đáy).

## Nến kích hoạt kỳ vọng (ts_open UTC)
| Ảnh | Kịch bản | Nến kỳ vọng | Căn cứ |
|---|---|---|---|
| 1 | KB-2 (nêm) | 2026-10-02 00:00 | nến đỏ thân 1.9 ATR nhấn chìm, đóng dưới cạnh dưới nêm (mũi tên (4)) |
| 2 | KB-1 | 2026-10-05 11:30 | nến đỏ thân 2.0 ATR nhấn chìm nến xanh trước ngay đỉnh (5) thấp hơn đỉnh (4) (mũi tên (6)) |
| 3 | KB-3 (vai-đầu-vai) | 2026-09-27 23:45 | cụm 3 nến thân nhỏ ở đường cổ ~4290 sau cuối tuần (ô vuông (8)) |
Dung sai ±2 nến.
