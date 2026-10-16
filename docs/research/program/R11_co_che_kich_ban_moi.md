# R11 - Cơ chế tiếp nhận kịch bản mới (YAML + ảnh) -> kiểm định trung thực tự động

Trạng thái: thiết kế + script chạy được (2026-10-15). Chỉ nghiên cứu / paper, không có đường đặt lệnh.

## 1. Sản phẩm
| Thứ | Đường dẫn |
|---|---|
| Mẫu trống có chú thích tiếng Việt | `docs/research/program/scenario_template/SCENARIO_TEMPLATE.yaml` |
| Mẫu 1 - Donchian BTCUSD H4 | `.../scenario_template/EXAMPLE_donchian.yaml` |
| Mẫu 2 - từ ảnh (2 đỉnh giảm dần, Sell XAUUSD H1) | `.../scenario_template/EXAMPLE_from_image.yaml` |
| Script | `data/research/program/R11/scenario_runner.py` |
| Đầu ra mỗi lần chạy | `data/research/program/R11/runs/<id>/{prereg.json,report.json,report.md,trades.csv,equity.svg}` |

Chạy: `python3 data/research/program/R11/scenario_runner.py <file.yaml> [--out DIR] [--max-sweep 60]` (cần pandas, numpy, scipy, PyYAML, jsonschema - đã có trên VPS; pydantic không có nên dùng jsonschema Draft7).

## 2. Quy trình tự động (thứ tự cố định)
1. **Validate** bằng JSON Schema (trường lạ bị từ chối, `transcribed_rules` của ảnh bắt buộc).
2. **Đăng ký giả thuyết trước**: ghi `prereg.json` (sha256 của YAML đã chuẩn hoá, thời điểm, tiêu chí chấp nhận). Chạy lại cùng `id` với YAML đã sửa -> TỪ CHỐI (phải đổi id; số lần thử tăng, nên thể hiện trong DSR của người dùng).
3. **Dữ liệu**: `data/research/patterns/bars/<MÃ>_<KHUNG>.parquet`; chỉ lấy dòng `split in (train,val)`. Dòng `test` và `embargo` bị loại ngay khi nạp, không có cờ nào để mở trong script. Mở test khoá là bước riêng (xem 5).
4. **Biên dịch DSL** thành chuỗi pandas vectorised qua `ast` với danh sách trắng (không `eval` tuỳ ý; thử `__import__('os').system(...)` bị chặn). Tín hiệu tại đóng nến t, vào ở mở nến t+1; `highest/lowest` gồm nến hiện tại nên "phá kênh" dùng `shift(...,1)`.
5. **Walk-forward neo-mở-rộng**: `folds` khối OOS liên tiếp sau phần train đầu (`min_train_frac`), embargo `embargo_bars`; mỗi fold chọn tổ hợp tham số theo kỳ vọng R trong mẫu (đủ `min_trades_is`), rồi chỉ báo cáo OOS. SL chạm trước TP trong cùng nến (bảo thủ).
6. **Chi phí**: spread + trượt + phí mỗi chiều + funding theo ngày, quy ra R bằng giá vào / khoảng SL.
7. **Baseline ngẫu nhiên**: cùng số lệnh, cùng hướng, cùng luật thoát/SL, vào ngẫu nhiên trong đúng khoảng OOS (300 lần) -> p = P(ngẫu nhiên >= thật).
8. **Bootstrap** CI95 kỳ vọng R OOS; **DSR** (Bailey - López de Prado, n_trials = số tổ hợp lưới, phương sai SR giữa các tổ hợp); **PBO** (CSCV trên các khối thời gian x tổ hợp; chỉ khi có sweep).
9. **Cổng chấp nhận** do chính YAML đăng ký trước. Kết luận chỉ có `REJECT` hoặc `CANDIDATE`; CANDIDATE = đủ điều kiện *xin* mở test khoá, không phải "đưa vào giao dịch".
10. **Sổ lệnh** `trades.csv` (tham số chọn, thời điểm vào/ra, R trước/sau chi phí), `equity.svg` (đường vốn OOS), `report.md/json`. (Hình ví dụ nến từng lệnh: dùng lại pattern-render ở lớp tích hợp, xem 4.)

Giới hạn bảo vệ chống tự lừa mình: lưới tối đa 60 tổ hợp (`--max-sweep`), mỗi tham số <=12 giá trị, `data_scope` chỉ nhận `dev`.

## 3. Kết quả chạy thật (dev = train+val, test khoá chưa mở)
| Mẫu | Lệnh OOS | R/lệnh net | R gross | CI95 | p vs ngẫu nhiên | DSR (6 thử) | PBO | Fold dương | Kết luận |
|---|---|---|---|---|---|---|---|---|---|
| Donchian BTCUSD H4 (11 862 nến dev, 0,8 s) | 120 | +0,469 | +0,542 | [-0,130 ; +1,231] | 0,176 | 0,85 | 0,00 | 2/5 | REJECT (CI chứa 0, không hơn ngẫu nhiên, fold dương 40% < 60%) |
| 2 đỉnh giảm dần Sell XAUUSD H1 | 39 | -0,162 | -0,117 | rộng, chứa 0 | 0,395 | 0,11 | 0,34 | 1/5 | REJECT (kỳ vọng âm, ít lệnh) |

Đọc đúng: Donchian có kỳ vọng dương nhưng chủ yếu là hệ quả BTC tăng mạnh trong giai đoạn (baseline ngẫu nhiên cùng luật thoát cũng +0,21 R), nên phần "edge" không tách được khỏi trôi giá - đúng loại ngộ nhận mà baseline ngẫu nhiên và CI phải bắt. Hai mẫu chỉ để kiểm thử đường ống, KHÔNG phải khuyến nghị giao dịch. Mẫu 2 là xấp xỉ DSL của KB-1, không thay detector sóng của pattern-engine.

Thử an toàn: YAML thiếu trường -> báo lỗi tiếng Việt; sửa YAML sau đăng ký -> từ chối; chèn `__import__` vào DSL -> chặn.

## 4. Nối vào tab AI Trading, phần B "Dạy kịch bản mới" (đặc tả, KHÔNG sửa mã ai-trading)
Phiên tích hợp thực hiện; giao diện đề xuất:

**Cách A - file drop (đơn giản, không đổi mã runner):**
- Gateway/ai-trading ghi YAML người dùng vào `data/research/program/R11/inbox/<id>.yaml` và ảnh vào `.../inbox/<id>/img/*` (ảnh chỉ lưu, runner không đọc).
- Worker nền (cron hoặc job runner đã có `jobs stub`) chạy `scenario_runner.py inbox/<id>.yaml --out runs/<id>` với `timeout 900` và quyền chỉ đọc dữ liệu; ghi `runs/<id>/status.json` {state: queued|running|done|error, started, finished}.
- Thẻ kịch bản đọc `runs/<id>/report.json` (`result.verdict`, `expectancy_r_net`, `ci95_expectancy_r`, `random_baseline.p_value`, `dsr`, `pbo`, `acceptance_checks`) và tải `trades.csv`, `equity.svg`.

**Cách B - API (đề xuất endpoint phía ai-trading, qua gateway, chỉ master):**
| Endpoint | Việc |
|---|---|
| `POST /v1/ai-trading/scenarios/validate` (body YAML) | chạy schema + biên dịch DSL thử trên 500 nến, trả lỗi theo dòng; không ghi đăng ký |
| `POST /v1/ai-trading/scenarios` (YAML + ảnh multipart) | đăng ký (ghi prereg) + xếp hàng job; trả `{id, job_id}`; 409 nếu id đã đăng ký với hash khác |
| `GET /v1/ai-trading/scenarios/{id}` | trạng thái + `report.json` |
| `GET /v1/ai-trading/scenarios/{id}/trades.csv`, `/equity.svg` | tải sổ lệnh/ hình |
| `POST /v1/ai-trading/scenarios/{id}/unlock-test` | CHƯA có ở bản đầu; chỉ bật sau khi người dùng duyệt (xem 5) |

Quy tắc cho lớp tích hợp: validate/giới hạn kích thước YAML (<=64 KB), ảnh <=5 MB mỗi ảnh (png/jpg/webp), `id` theo regex trong schema (chống path traversal), chạy runner như tiến trình tách biệt, không cho DSL gọi mạng/ file (đã bảo đảm bằng whitelist), UI không hiển thị tên nguồn dữ liệu (runner không in nguồn; `report.json` không chứa tên nguồn), thẻ luôn ghi "dev, test khoá chưa mở".

**Từ ảnh sang DSL** (bước người/ LLM, ngoài runner): LLM cục bộ (Qwen đã có) hoặc người đọc ảnh -> liệt kê điều kiện bằng lời -> ánh xạ sang DSL -> điền `transcribed_rules`; luôn kèm "golden check": vẽ tín hiệu runner lên đúng ảnh/ vùng mẫu bằng pattern-render để người xác nhận đúng ý trước khi chạy kiểm định. Đây là phần cần phiên tích hợp bổ sung (runner hiện chưa vẽ).

## 5. Test khoá
Mặc định không mở. Điều kiện xin mở: verdict `CANDIDATE` ở dev + người dùng đồng ý bằng văn bản trong phiên + ghi vào `data/research/patterns/test_access.log`. Mở = 1 lần duy nhất cho 1 YAML đã đăng ký (khoá file `runs/<id>/test_used`); không có chỉnh sửa sau đó. Phần này chưa cài trong runner (chủ ý), cần mở rộng riêng khi thật sự có CANDIDATE.

## 6. Hạn chế đã biết
- Vòng lặp vị thế bằng Python, đủ nhanh cho H4/H1 (dưới 1 s mỗi tổ hợp-fold); M1/M5 nhiều năm cần numba hoặc cắt dữ liệu.
- Khung và mã lấy từ `bars/`; kịch bản đa mã gộp lệnh các mã (chưa có phân bổ vốn/ tương quan); chưa mô hình spread biến thiên theo phiên/ tin.
- DSL chưa có: swing/pivot/ZigZag, đa khung (MTF), tin tức; thêm hàm vào whitelist khi cần (mỗi hàm phải không nhìn tương lai).
- Chưa có hình ví dụ nến từng lệnh; chưa có test unit trong repo (đã thử tay 4 ca ở mục 3).
