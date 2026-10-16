# AI Training Class (lõi P2a)

Chuyên gia ngồi DẠY AI một kịch bản giao dịch; AI đóng vai học trò hoài nghi, chủ động hỏi sâu rồi "học 1 hiểu 10". Mọi thứ CHỈ nghiên cứu/paper: không có đường đặt lệnh, không mở được test khoá từ chat.

Mã: `services/ai-trading/src/ai_trading/classroom/` (module thuần trong ai-trading, không I/O, không DB; chọn module thay vì service riêng vì dùng chung `scenario_schema`, registry, worker backtest và quyền master/expert; P2b nối API/DB/SSE). Test: `services/ai-trading/tests/test_classroom.py` (37 test, LLM giả).

## Kiến trúc
| Tệp | Vai trò |
|---|---|
| `llm.py` | `LLMClient` (stream iterator). `LlamaCppClient` (mặc định, server OpenAI-compatible của briefing, KHÔNG gửi tools), `ClaudeClient` (chỉ khi `CLASSROOM_CLAUDE_ENABLED=true` + `CLASSROOM_CLAUDE_KEY`, mặc định tắt), `NullClient`, `FakeLLM`. `GuardedLLM` giới hạn độ dài prompt/đầu ra/token, tốc độ (mặc định 12 lần/phút), hạn thời gian; `generate()` luôn hậu kiểm và rơi về câu mẫu khi lỗi. `build_client(env)`. |
| `checklist.py` | 13 bước có thứ tự, mỗi cụm ≤3 câu hỏi mẫu cố định (fallback) + câu hỏi làm rõ. |
| `machine.py` | `Classroom` (state machine do CODE điều khiển): intake (giao kịch bản bằng ~3 câu) -> interview -> review. `respond()` trả `Turn`; `respond_stream()` phát văn bản đã hậu kiểm theo luồng; `attach()` cho nội dung từ ảnh/file/tin. |
| `profile.py` | `Profile` (hồ sơ kịch bản có cấu trúc, JSON/YAML), `ProfileHistory` (phiên bản bất biến + `diff`). |
| `extract.py` | Trích số/luật/mức SL-TP/mã/khung từ câu trả lời bằng regex tất định; chấm độ chắc chắn cao/vừa/thấp BẰNG MÃ (câu mơ hồ như "khoảng", "cảm giác" không bao giờ "cao"). |
| `one_to_ten.py` | "Học 1 hiểu 10" tất định: dải biến thể tham số, đối xứng, khung/mã khác, kịch bản liên quan/đối lập, phản ví dụ, điều kiện biên, giả định ngầm. LLM chỉ gợi ý thêm (đã hậu kiểm, đánh dấu chưa kiểm chứng). |
| `commands.py` | Parser lệnh `/` theo allow-list, trả `Intent` (không thực thi), `chips_for()`. |
| `safety.py` | Chống injection (`looks_injected`, `ingest_untrusted`, `data_block`), hậu kiểm đầu ra (`check_output`). |
| `export.py` | Hồ sơ -> YAML schema "Dạy kịch bản" (đã qua `scenario_schema.validate`). |
| `prompts.py` | Prompt hệ thống (vai trader/analyst hoài nghi, nhắc nến cổ điển không có edge sau chi phí). |

## Cách dạy hiệu quả
1. Giao kịch bản bằng 3 câu: mã, khung, hình dạng, vào/ra thế nào. Hệ thống điền tạm vài mục từ mô tả và xin xác nhận ("đúng" là đủ).
2. Trả lời từng cụm câu hỏi bằng SỐ: bao nhiêu nến, bao nhiêu ATR, bao nhiêu %, SL/TP theo R. Câu trả lời mơ hồ bị chấm "thấp" và hỏi lại đúng một lần.
3. Không biết thì gõ "bỏ qua": ghi vào danh sách câu hỏi còn mở, không bị ép.
4. Nhiều chuyên gia: sửa/bổ sung bước bất kỳ bằng `số bước: nội dung`. Hai người nêu số khác nhau ở cùng bước -> AI hỏi thống nhất (xung đột ghi trong hồ sơ cho tới khi có câu thống nhất).
5. Cho ví dụ ĐÚNG và ví dụ GẦN GIỐNG nhưng KHÔNG vào: đây là phần quý nhất.
6. Muốn AI NHỚ: nói rõ và có số ("SL 1 ATR trên đỉnh nhịp"); khi AI hỏi "Mình ghi nhớ: ... đúng không?" bấm **Đúng** để chốt, **Sửa** nếu lệch, **Đừng nhớ** nếu không muốn lưu. Điều phụ (phong cách, thuật ngữ) tự lên "đã xác nhận" sau 3 lần nhắc lại. Mở tab **Bộ nhớ** để xem/ sửa/ ghim/ xoá bất cứ lúc nào.

| Bạn muốn | Cách làm | Kết quả |
|---|---|---|
| AI nhớ một luật (vào lệnh, SL/TP, huỷ) | Nói bằng số, bấm [Đúng] ở thẻ xác nhận | Bản ghi "đã xác nhận", AI không hỏi lại |
| AI sửa điều hiểu sai | Bấm [Sửa] hoặc sửa trong tab Bộ nhớ, ghi "vì sao" | Phiên bản mới, bản cũ vẫn giữ (nhật ký) |
| AI quên một điều | [Đừng nhớ] hoặc Xoá trong tab Bộ nhớ | Không dùng nữa (nhật ký vẫn giữ) |
| Điều quan trọng không bị phai | Ghim | Không giảm trọng số theo thời gian |
| Hai người dạy khác nhau | Vào tab Mâu thuẫn, chọn bản đúng/ giữ cả hai kèm điều kiện/ hợp nhất | Một nguồn thống nhất |
| Gợi ý hợp gu hơn | Cứ bấm gợi ý hữu ích, bấm "không phải ý này" khi lệch | Thứ tự gợi ý thích nghi theo bạn và theo lớp |
| Cho AI biết các kịch bản phối hợp thế nào | Màn Phương pháp > Quy tắc kết hợp: ưu tiên, loại trừ, bổ trợ, regime, đối xứng, khung xác nhận | Bảng quy tắc lưu bằng PUT; sơ đồ cập nhật; AI dùng khi nhiều tín hiệu cùng lúc |
| Chốt quản trị vốn chung và quy tắc dừng | Phòng phương pháp: nêu số (rủi ro/ lệnh, rủi ro nóng, lỗ ngày/ tuần, dừng quanh tin) rồi xác nhận | Hồ sơ phương pháp rõ hơn; bước 6 của kế hoạch cần các hàng này có số và đã xác nhận |
| Biết vì sao chưa áp dụng được | Tab Kế hoạch áp dụng: đọc tiêu chí yêu cầu/ thực tế và Hướng sửa | Biển "CHƯA đủ điều kiện" nêu đúng bước vướng; không có nhãn "sẵn sàng" khi bước 4-6 chưa đạt |

## Checklist (thứ tự cố định)
1 Bối cảnh; 2 Mã + khung (bắt buộc); 3 Điều kiện hình thành định lượng (bắt buộc); 4 Điểm kích hoạt (bắt buộc); 5 Điều kiện huỷ; 6 SL/TP/quản lý (bắt buộc); 7 Khối lượng/rủi ro; 8 Bộ lọc phiên/tin/vol/spread; 9 Ví dụ đúng/sai; 10 Điều gì làm thất bại; 11 Đối xứng buy/sell; 12 Khung/mã khác; 13 Lý do kinh tế/tâm lý. "Bắt buộc" = cần để xuất YAML và chạy /test.

## Hành động (mã nội bộ `/`)
Giao diện KHÔNG bắt gõ lệnh: người dùng bấm chip/ nút/ menu gợi ý và thấy câu tự nhiên; mã `/...` dưới đây chỉ là hợp đồng nội bộ UI <-> backend (và tương thích API).
| Lệnh | Action (ý định) | Ghi chú |
|---|---|---|
| `/test [version=N] [mode=dev\|walkforward]` | `backtest` | cần xác nhận; đăng ký giả thuyết trước, walk-forward, baseline ngẫu nhiên. `lock=` khác `no` bị từ chối (test khoá chỉ master mở bằng nút riêng). Kèm `scenario_yaml`. |
| `/quet [limit=6..10] [symbol=] [tf=]` | `scan_history` | quét lần xuất hiện + ảnh nến để gắn nhãn ĐÚNG/SAI/GẦN ĐÚNG |
| `/bien-the` | `variants` (local) | biến thể, liên quan/đối lập, phản ví dụ, biên, giả định |
| `/doi-xung` | `mirror` (local) | bản buy đối xứng + điểm bất đối xứng (DSL hiện chỉ chạy sell) |
| `/so-sanh [vs=buy_hold\|random\|<id>]` | `compare` | |
| `/giai-thich <phần>` | `explain` (local) | |
| `/tom-tat` | `summary` (local) | "AI hiểu như sau" + độ chắc chắn |
| `/luu [ghi chú]` | `save_version` | chụp phiên bản hồ sơ; intent mang `profile` đầy đủ để backend lưu |
| `/hoi-them` | `ask_more` (local) | giả định ngầm, phản ví dụ, điều kiện biên (3 câu/lượt) |
| `/ve kind=dinh\|day\|vung\|diem-vao\|song [ghi chú]` | `draw_annotation` | |
| `/dat-lai xacnhan=co` | `reset` (local) | |

Alias không dấu/tiếng Anh được chấp nhận (`/bien-the`, `/biến-thể`, `/backtest`...). Lệnh lạ hoặc tham số lạ -> `CommandError` kèm danh sách lệnh. `/test /quet /so-sanh` bị chặn nếu hồ sơ thiếu bước bắt buộc hoặc không xuất được YAML. Intent luôn `paper_only=True`; lớp backend phải kiểm quyền (master/expert), CSRF, rate limit, audit rồi mới thực thi.

## An toàn
- Nội dung từ ảnh/OCR/file/tin chuyên gia: `attach()` làm sạch (thẻ, URL, ký tự ẩn); có mẫu chỉ thị ("ignore previous...", "bỏ qua mọi hướng dẫn...", chữ rời, leetspeak, base64 dài) thì LOẠI HẲN; phần còn lại chỉ vào prompt trong khối "DỮ LIỆU THAM KHẢO" delimiter ngẫu nhiên ở vai user, không bao giờ vai system. Tin nhắn chat có mẫu chỉ thị bị bỏ qua, không lưu vào hồ sơ, ghi vào `Classroom.flags` (cho audit).
- Hậu kiểm đầu ra LLM (`check_output`): URL/markup, tên nguồn dữ liệu, hứa hẹn/"chắc chắn", khuyến nghị mua/bán/đặt lệnh, mẫu chỉ thị, quá dài; câu hỏi do LLM diễn đạt không được thêm số mới và phải có 1-3 dấu hỏi; tóm tắt không được có số ngoài hồ sơ. Sai -> câu mẫu cố định.
- LLM không có công cụ, không thực thi gì; mã quét tĩnh (test) không có `order_send`/`subprocess`/`eval`.
- Streaming chỉ phát văn bản ĐÃ hậu kiểm (không phát nháp thô).

## Giới hạn của model 9B cục bộ (Qwen3.5-9B Q4 qua llama.cpp)
Chậm trên CPU (hàng chục giây/câu), hay lạc đề, dễ bịa số, tiếng Việt chuyên ngành chưa sâu. Vì vậy: trạng thái hội thoại và checklist do mã giữ (model không nhớ gì), độ chắc chắn và trích xuất số do mã tính, LLM chỉ làm văn phong và gợi ý, mọi thứ có phương án rơi về câu mẫu. Chưa có đa phương thức: đọc ảnh = chuyên gia chú thích rồi dùng pattern-render vẽ lại. Claude API (nếu người dùng cấp key) chỉ thay `LLMClient`, các hàng rào giữ nguyên.

## Quy trình dạy -> test -> paper
Dạy (checklist) -> “Tóm lại” sửa chỗ AI hiểu sai -> “Biến thể”, “Phía mua”, “AI hỏi thêm” xác nhận giả định -> “Tìm ví dụ” gắn nhãn (P2b) -> “Lưu phiên bản” -> “Chạy thử” (walk-forward, so baseline; kết quả trung thực, mặc định kỳ vọng `no_edge`) -> chỉ khi qua tiêu chí và master mở test khoá một lần -> mới xét paper-trade trong arena (guardrail rủi ro). Không bước nào đặt lệnh thật.

## Cấu hình (env)
`CLASSROOM_LLM_BACKEND` (llamacpp|claude|none, mặc định llamacpp), `CLASSROOM_LLM_URL` (mặc định `BRIEFING_LLM_URL` hoặc `http://briefing-llm:8080`), `CLASSROOM_LLM_TIMEOUT_S`, `CLASSROOM_LLM_MAX_TOKENS` (400), `CLASSROOM_LLM_MAX_CALLS_PER_MIN` (12), `CLASSROOM_LLM_DEADLINE_S` (90), `CLASSROOM_CLAUDE_ENABLED` (false), `CLASSROOM_CLAUDE_KEY`, `CLASSROOM_CLAUDE_MODEL`.

## P2b: backend (đã triển khai 2026-10-15)
Hợp đồng API cho UI: `docs/handoff/AI_CLASSROOM_API.md` (đường dẫn, JSON, SSE, mã lỗi). Mã: `classroom/api.py` (route `/class/*` trong ai-trading), `classroom/store.py` (lưu trữ), `classroom/persist.py` (lưu/khôi phục state machine), `api-gateway/class_routes.py` (proxy), worker `scan_examples` + `candle_png.py`.

### Lưu trữ: SQLite (WAL) trên volume riêng, KHÔNG phải Postgres/Redis (lý do)
- Bảng: `class_rooms, class_members, class_messages, class_labels, class_profiles` (trạng thái máy + hồ sơ hiện hành), `class_profile_versions` (bất biến), thêm `class_examples, class_actions, class_attachments, class_audit`. Schema ở `classroom/store.py`.
- Vì sao không Postgres: ai-trading không có DB/đường tới Postgres (read_only, mạng backend, Redis ACL là cache không bền); thêm Postgres cần role + migration + lock-file (hash) + mật khẩu mới cho dữ liệu nhỏ, 1 tiến trình ghi. Vì sao không Redis: không AOF/không truy vấn quan hệ/tìm kiếm. SQLite cho giao dịch + tìm kiếm + bền qua restart; volume `data/ai-classroom` -> `/classroom` CHỈ gắn vào ai-trading (worker không gắn) = cô lập quyền ghi tương đương "role hẹp"; không thêm bí mật. Đánh đổi: 1 instance, sao lưu = sao chép thư mục (đã nằm trong `data/`, gộp vào backup hiện có; kiểm tra khi làm backup off-site), không truy vấn từ dịch vụ khác. Muốn chuyển Postgres sau này: `ClassStore` là lớp duy nhất đụng SQL.
- Phiên dạy bền: state machine (phase, idx, hồ sơ, phiên bản, cờ injection) lưu mỗi lượt vào `class_profiles`; dựng lại sau restart (test `test_sse_and_persistence`). Mọi lượt tuần tự hoá theo phòng (khoá).

### Vai `expert`
- auth: vai phụ mới (đăng nhập `platform:"master"` + tên, như support/analyst); perm duy nhất `class.use`; migration `020_expert_role.sql` (CHECK role). Master tạo qua màn quản trị nhân sự (`role: "expert"`).
- gateway: coi expert là `client` bị thu hẹp, không có tài khoản MT; được `GET /v1/me`, `/v1/user/csrf`, dữ liệu thị trường (GET như analyst) và `/v1/ai-trading/class/*` (GET/POST). 403 cho mọi thứ khác (cấu hình, tài khoản, jobs, ledger, guardrail, kịch bản trực tiếp). master có tất cả; client/analyst/support/auditor 403; anon 401.
- Phòng: chỉ thành viên + master; phòng lạ/không tồn tại cùng trả 404 (không oracle IDOR). Test khoá (`/final-test`) chỉ master, `confirm` = id kịch bản, dev xong trước, mở 1 lần.

### Luồng action
`/quet` -> đăng ký kịch bản `CL-...` từ hồ sơ (YAML Dạy kịch bản) -> job worker `scan_examples` (chỉ dữ liệu dev, 6-10 ví dụ rải đều, ảnh nến PNG vẽ bằng numpy/zlib: nến tín hiệu tô sáng, vạch vào lệnh vàng, vạch SL đỏ, không có chữ/tên nguồn) -> thẻ `scan` trong phòng -> `POST labels` (ĐÚNG/SAI/GẦN ĐÚNG + lý do) -> độ chính xác `(đúng + 0,5*gần đúng)/đã gắn nhãn`, độ phủ `đã gắn/ví dụ`, theo vòng; nhãn SAI + lý do thành "phản ví dụ" (câu hỏi mở) trong hồ sơ. `/test` luôn cần xác nhận -> ghi tin "ĐĂNG KÝ giả thuyết" (băm YAML) TRƯỚC khi chạy job `backtest` (walk-forward + baseline ngẫu nhiên + DSR/PBO, KHÔNG mở test khoá) -> thẻ kết quả `result_card` lấy số thật từ `result.json` kèm cảnh báo trung thực (n<30, chưa mở test khoá, số lần thử, chi phí). Thẻ được thêm vào phòng khi UI poll `GET room`/`actions` (idempotent). Nhận định AI có Chấp nhận/Sửa/Phản bác (`.../review`): sửa/phản bác thành câu hỏi mở trong hồ sơ.
- Xuất: `profile/export` (YAML Dạy kịch bản, `register=true` để nạp vào tab AI Trading), `minutes.md` (biên bản). PDF: chưa làm (in từ trình duyệt).
- Đính kèm: ảnh (png/jpg/webp, kiểm magic bytes, <=700 KB), YAML (safe_load, cấm anchor/alias, <=64 KB), CSV (20 dòng đầu, ô cắt 40 ký tự), PDF (chỉ kiểm `%PDF-`, chưa trích chữ), ghi chú. Tên tệp chặt regex, lưu bằng uuid (không path traversal), phục vụ kèm `nosniff` + CSP sandbox. Nội dung làm sạch/loại nếu có mẫu chỉ thị, thành DỮ LIỆU tham khảo; tên nguồn dữ liệu bị che trong biên bản. Giới hạn: AI chưa đọc được ảnh (cần khoá Claude vision); chuyên gia phải chú thích.
- Giới hạn tốc độ: gateway 60 ghi/phút + 12 tin/phút/người; ai-trading `AI_CLASS_MSG_RATE`(12)/`AI_CLASS_WRITE_RATE`(90); LLM tối đa 12 lần/phút. Audit: bảng `class_audit` (không lưu nội dung) + log gateway.
- Cấu hình: `AI_CLASS_DIR=/classroom`, `CLASSROOM_LLM_BACKEND` (mặc định llamacpp; briefing-llm nằm mạng ops nên từ ai-trading thường KHÔNG tới được -> hệ thống tự dùng câu hỏi mẫu, đây là hành vi thiết kế). Claude chỉ khi master bật và cấp khoá (P2c), mặc định tắt.

### Còn lại
UI (agent web-ui); Claude API + vision + ngân sách (P2c); PDF biên bản; đọc ảnh bằng máy; vẽ chú thích thành PNG (hiện lưu JSON để UI vẽ trên lightweight-charts); thông báo realtime nhiều chuyên gia (hiện poll 3-5 s); trích chữ PDF.

## Giao diện và cách dạy (TASK_classroom_ux, 2026-10-15)
Mã: `services/web-ui/app/src/components/classroom/`. Chỉ nghiên cứu/paper, không có nút hay đường đặt lệnh; UI không hiển thị tên nguồn dữ liệu. Ảnh QA: `services/web-ui/docs/classroom/`.

### Bố cục
- Desktop (>=1180px): 3 cột. Trái: danh sách phòng + checklist "Buổi học đầu tiên"; giữa: chat (streaming, nhận định AI, chip hành động, ô nhập); phải: tab Hồ sơ | Ví dụ | Test | Biểu đồ | Sổ tay | Ghim. Alt+L / Alt+R thu gọn cột trái/phải; Alt+1..6 đổi tab phải; Ctrl+K tìm trong phòng; Ctrl+/ về ô nhập.
- Mobile/tablet: thanh tab dưới Chat | Hồ sơ | Ví dụ | Test; danh sách phòng mở bằng nút ở thanh trên.
- Thanh trên: tên kịch bản, phiên bản, "Độ rõ ý tưởng" (0-100, thanh tiến độ, gợi ý hàng mơ hồ nhất), nhóm nút Lưu phiên bản / Chạy test / Xuất, rồi Xem demo / Cách dạy / Mẫu / Tham quan; trạng thái model (cục bộ hay đám mây, tốc độ).
- Không còn lệnh gõ `/...` trên giao diện: chip hành động có nhãn tự nhiên (Chạy thử, Tìm ví dụ, Biến thể, Phía mua, So với mua-giữ, Tóm lại, Vẽ lên biểu đồ). Bên dưới vẫn gọi các lệnh allow-list của backend. Bộ nhận ý định bằng ngôn ngữ tự nhiên (từ khoá/LLM) CHƯA có ở backend tại thời điểm này.

### Hồ sơ kịch bản (canvas, 16 hàng)
Thứ tự và khoá hàng cố định: context, symbol_tf, formation, trigger, invalidation, sl, tp, sizing, filters, ex_ok, ex_bad, failure, symmetry, rationale, assumptions, open_questions. Mỗi hàng: nội dung AI đang hiểu (sửa trực tiếp), độ chắc chắn (cao/vừa/thấp/trống, kèm biểu tượng, không chỉ dựa màu), nguồn (người nói + số lượt), nút Xác nhận / Sửa / Hỏi lại; sửa có diff từ-theo-từ so với bản AI hiểu và nút Hoàn tác; lịch sử phiên bản + so sánh A→B.
- Nguồn dữ liệu: `GET /class/rooms/{rid}/canvas` (xem `docs/handoff/UX_API.md`). Nếu gateway chưa cho đường này (404) UI tự tính hồ sơ phía client từ `/profile`, xác nhận lưu trong trình duyệt, "Sửa" còn gửi vào chat để AI cập nhật.
- Ánh xạ API: `rows[].text`, `confidence`, `source.{author,turn}`, `confirmed`, `quantified`, `ai_understanding`, `editable`; `clarity.{score, weakest_row, next_question}`.

### Độ rõ ý tưởng (cách tính)
`score = 100 * (0.2*filled + 0.3*confirmed + 0.3*quantified + 0.2*examples)` trên 14 hàng lõi (backend, tất định; `assumptions` và `open_questions` không tính). `filled` = tỷ lệ hàng có nội dung; `confirmed` = đã xác nhận (mất hiệu lực nếu nội dung đổi sau đó); `quantified` = có con số; `examples` = có ví dụ đúng/sai. Hàng thấp nhất (`weakest_row`) hiện ở thanh trên kèm `next_question`. Khi chưa có API, client dùng công thức xấp xỉ: có nội dung 40 + có số/độ chắc >= vừa 30 + đã xác nhận 30, lấy trung bình.

### Demo, hướng dẫn, tour, mẫu
- **Xem demo**: buổi học mẫu offline (3 đỉnh giảm dần -> Sell), tự chạy hoặc bấm Tiếp; hồ sơ điền dần, độ rõ 10 -> 90, ví dụ đúng/sai, kết quả test. Mọi số gắn nhãn MINH HOẠ, không gọi API/model.
- **Cách dạy** (bảng): việc nên làm / ví dụ câu nói / tác dụng; bảng "Nhờ AI việc gì" (câu nói tự nhiên -> hành động); Khái niệm (độ rõ, nhãn, phiên bản, backtest trung thực, test khoá, vì sao không hứa lợi nhuận).
- **Tham quan** (5 bước, khoá `cr-tour-done`; neo `data-tour`: rooms, chat, profile, clarity, actions) và checklist "Buổi học đầu tiên" (tạo phòng, trả lời 5 câu, gắn nhãn 6 ví dụ, lưu phiên bản, chạy test) tự tick theo tiến độ thật.
- **Mẫu**: breakout, 3 đỉnh giảm dần, vùng cung/cầu, pullback, trống, nhập từ ảnh/YAML. Chọn mẫu thì brief 3 câu được điền vào ô nhập để sửa rồi gửi (không tự gửi).

### Ví dụ và thẻ kết quả test
- Tab Ví dụ: lưới 6-10 thẻ ảnh nến của lần tìm gần nhất; phím tắt Đ / S / G (đúng / sai / gần đúng), mũi tên chuyển thẻ, lý do 1 dòng; độ chính xác/độ phủ cập nhật ngay; hộp "AI đã học được gì từ nhãn" tính tất định phía client.
- Thẻ kết quả test (trong chat và tab Test): số lệnh, kỳ vọng R, khoảng tin cậy 95%, so với ngẫu nhiên, PBO/DSR, đường vốn mini, cảnh báo trung thực (mặc định kỳ vọng "không có edge"), nút Hỏi AI giải thích / Sửa kịch bản & chạy lại / tải sổ lệnh CSV; test khoá chỉ master, xác nhận 2 bước (gõ lại id).

### API mới
`GET /class/rooms/{rid}/canvas`, `POST /class/rooms/{rid}/canvas/{key}/confirm|edit`, `GET /class/templates`, `GET /class/demo/script` (backend `classroom/ux_api.py`, hợp đồng `docs/handoff/UX_API.md`). Gateway cần whitelist (phiên ts): xem `docs/handoff/UX_API_NOTES.md`. UI hiện KHÔNG phụ thuộc templates/demo API (mẫu và demo nằm sẵn ở client).

### Ảnh QA
`services/web-ui/docs/classroom/ux-<màn>-<rộng>-<sáng|tối>-<vi|en>.png` (màn: empty, chat, profile, examples, test, demo, guide, templates, tour). Kịch bản: `services/web-ui/qa/ai_classroom_ux.mjs` (chạy `sh services/web-ui/qa/run_ai_classroom_ux.sh master mock`; dùng fixture, kiểm tràn ngang, cỡ chạm, axe WCAG A/AA).

## Xoá phòng + Thùng rác (2026-10-16)
- Xoá MỀM: bảng `class_room_trash` (deleted_at/deleted_by/reason/forget_learned/purge_after); `store.room()`/`rooms_for()` lọc phòng đã vào thùng nên mọi route cũ trả 404 (IDOR đồng nhất). Module `classroom/rooms_trash.py`, hợp đồng `docs/handoff/ROOMS_TRASH_API.md`.
- Quyền: master xoá mọi phòng, khôi phục, xoá vĩnh viễn; chuyên gia chỉ xoá phòng mình tạo khi chưa có người khác đóng góp; từ chối khi còn action/job đang chạy (409). Xoá hàng loạt 2 bước prepare/confirm (token 5 phút, tối đa 50). Thùng rác 30 ngày, vòng nền mỗi giờ tự xoá hẳn (tin, ví dụ, nhãn, phiên bản, action, tệp đính kèm). Audit: room.trash/restore/purge/bulk_trash.
- Bộ nhớ AI: mặc định giữ điều đã xác nhận (đánh dấu nguồn phòng đã xoá); tuỳ chọn "xoá cả những gì AI đã học" đi qua hook `ON_TRASH/ON_PURGE` (module bộ nhớ đăng ký).
- Giao diện (`RoomsTrash.jsx`): nút thùng rác ở mỗi phòng + menu phòng, "Chọn nhiều" với lọc nhanh (trống/demo/cũ hơn N ngày), hộp thoại xác nhận nêu số tin/ví dụ/phiên bản (gõ lại tên khi nhiều dữ liệu), mục Thùng rác (đếm, Khôi phục, Xoá vĩnh viễn cho master), toast Hoàn tác 10 giây. E2E: `services/web-ui/qa/ai_classroom_trash.mjs` (SPEC=ai_classroom_trash.mjs, MOCK=0).

## Bộ nhớ và học liên tục (2026-10-16)
Hợp đồng route: `docs/handoff/MEMORY_API.md`. Mã: `services/ai-trading/src/ai_trading/classroom/memory.py` (lõi) + `memory_api.py` (route `/class/memory...`).

**Sự thật cần nói thẳng:** "AI học" ở đây là BỘ NHỚ + TRUY XUẤT + (sau này) XẾP HẠNG GỢI Ý học từ hành vi chuyên gia. KHÔNG phải huấn luyện/ fine-tune lại trọng số model: không cần GPU, không mất khi đổi model, xem/ sửa/ thu hồi được từng điều. Tuỳ chọn sau khi có GPU: gom các hội thoại tốt (đã xác nhận) thành bộ dữ liệu để tinh chỉnh LoRA; hiện CHỈ ghi vào tài liệu, chưa làm.

- **Loại bản ghi:** tri thức phương pháp, bài học/ sửa sai, nhãn ví dụ (nối từ `/labels`), kết quả test (hook `on_test_result`), sở thích chuyên gia, thuật ngữ cá nhân. Mỗi bản ghi có nguồn (chuyên gia + tin nhắn), độ tin cậy, trạng thái (đề xuất/ đã xác nhận/ bị bác/ thu hồi), số lần dùng, phiên bản (sửa = bản mới, không xoá lịch sử), ghim, khoá, phạm vi (chung theo kịch bản/ riêng chuyên gia). Bảng SQLite `class_memory*` (CREATE IF NOT EXISTS, volume `/classroom`, nằm trong backup hiện có).
- **Ghi (memory writer):** sau mỗi tin nhắn của chuyên gia, trích đề xuất bằng luật tất định (SL/TP/huỷ/vào lệnh/khối lượng/bộ lọc, sửa sai "không phải X mà là Y", thuật ngữ "gọi X là Y", sở thích). Khi LLM bật: thêm bước trích JSON ràng buộc, code kiểm (loại/ chủ đề hợp lệ, KHÔNG có số mới ngoài lời chuyên gia); LLM tắt/ lỗi -> chỉ luật. Thông tin QUAN TRỌNG (vào lệnh, SL/TP, huỷ, khối lượng, sửa sai) tạo thẻ xác nhận [Đúng] [Sửa] [Đừng nhớ]; thông tin phụ lưu "đề xuất" và tự nâng lên "đã xác nhận" sau 3 lần được nhắc lại/ xác nhận. Khử trùng lặp (n-gram cosine >= 0,8 -> hợp nhất, cộng số lần xác nhận); điều đã bị bác không bị đề xuất lại.
- **Mâu thuẫn:** cùng chủ đề + cùng đơn vị (ATR/pip/R/%...) nhưng giá trị khác nhau (không phải tập con) -> mở một "mâu thuẫn", giữ cả hai bản kèm nhãn và thẻ hỏi làm rõ; giải quyết bằng chọn A/ B, giữ cả hai kèm điều kiện, hoặc hợp nhất thành bản mới.
- **Truy xuất:** top-k theo BM25 + cosine n-gram ký tự (thuần Python; VPS hiện chưa có numpy/onnxruntime/sentence-transformers và gói 0 đồng, nên chưa dùng embedding; giao diện truy xuất tách riêng để thay bằng embedding ONNX đa ngôn ngữ nếu cài được sau). Lọc theo phòng/ chuyên gia, ưu tiên bản đã xác nhận và ghim, giảm trọng số bản cũ không dùng (bán rã 90-180 ngày), thuật ngữ cá nhân hoá mở rộng truy vấn. Kết quả nằm trong NGÂN SÁCH TOKEN cố định (600) và được nhét vào prompt như khối DỮ LIỆU THAM KHẢO có nhãn + mã khung ngẫu nhiên, không bao giờ vai system/ chỉ thị; mỗi dòng được lọc lại trước khi nhét.
- **Dùng lại:** AI nói rõ khi dựa vào bộ nhớ ("Mình nhớ bạn từng dạy: ..."; `turn.memory_used` cho UI), và không hỏi lại điều đã xác nhận: ở bước checklist đã có tri thức xác nhận, AI chỉ hỏi "áp dụng cho kịch bản này không?" (trả lời "đúng" là ghi nhận luôn). Số lần tránh hỏi lặp có ở `GET /class/memory/stats`.
- **Quyền & an toàn:** chỉ vai expert/ master ghi; chuyên gia sửa/ xoá bản của mình (xoá mềm), master xem/ khoá/ thu hồi/ xoá hẳn tất cả; IDOR theo phòng; mọi ghi đi qua `looks_injected`/ `clean_text` + chặn secret/ mật khẩu/ khoá, thông tin tài khoản MT, email/ điện thoại/ URL, lời hứa lợi nhuận; tin nhắn chứa chỉ thị thì không trích gì. Khi xoá phòng, điều đã xác nhận được giữ (đánh dấu nguồn phòng đã xoá) trừ khi người xoá chọn xoá cả những gì AI đã học (`Memory.on_room_trashed(rid, forget=True)`).
- **Cách dạy hiệu quả:** nói tự nhiên và nêu số cụ thể ("SL 1 ATR trên đỉnh nhịp"); bấm [Đúng] ở thẻ "Mình ghi nhớ" để chốt; muốn AI quên thì bấm [Đừng nhớ]; hai lần dạy khác số sẽ bị hỏi làm rõ.
- **Chưa làm (giai đoạn sau):** gợi ý biến thể/ cảnh báo kịch bản giống kịch bản thất bại. (Xếp hạng option và UI: xem hai mục dưới.)
- Test: `services/ai-trading/tests/test_memory.py` (hội thoại mẫu -> bản ghi, truy xuất, quyền/ IDOR, phiên bản, mâu thuẫn, bộ lọc injection/ secret/ PII/ lời hứa, không hỏi lại, LLM giả, thống kê/ xuất).

### Xếp hạng option học được (M3) — `classroom/option_rank.py`
Mỗi lượt có 5-8 option ứng viên (câu hỏi tiếp theo, làm rõ, biến thể, đối xứng, so sánh, hành động, test, quét, phản ví dụ); `rank(options, context, stats)` sắp xếp rồi hiển thị top 2-4.
- **Điểm** = 0,40 x giá trị thông tin (hàng hồ sơ trống 1,0 / mơ hồ 0,7 / vừa 0,35 / cao 0,05; hàng đã xác nhận giảm còn 30%) + 0,20 x độ phù hợp ngữ cảnh (trùng từ với câu vừa nói/ ý định) + 0,30 x xác suất được chấp nhận theo LOẠI option (bandit) - 0,10 x chi phí (việc nặng xếp sau).
- **Bandit:** hậu nghiệm Beta(2,3) theo loại option. Bấm = thành công; bỏ qua = thất bại; "không phải ý này" = thất bại nặng gấp 1,5; hiển thị mà không bấm gì = thất bại yếu (0,25). Lịch sử của chính chuyên gia tính đầy đủ, của cả lớp tính 0,35. Chế độ `thompson` (mặc định, có khám phá), `ucb`, `mean` (xác định, dùng cho giải thích/ test).
- **Lưu kết quả:** bảng `class_option_feedback` (CREATE IF NOT EXISTS) qua `record_feedback`; route `POST rooms/{rid}/options/feedback` do mô-đun nhận ý định cung cấp (`docs/handoff/INTENT_API.md`). `GET /class/options/stats` (mới, cần whitelist gateway) trả tỉ lệ chấp nhận theo loại cho UI.
- **Giải thích "vì sao gợi ý này":** mỗi option có `why`/`why_en` (hàng hồ sơ còn trống/ mơ hồ, khớp câu vừa nói, lịch sử bấm của bạn và lớp, việc nặng xếp sau) cùng `parts` (info/ctx/bandit/cost).
- **Giới hạn thật:** xếp hạng thống kê nhẹ trên một nhóm loại option, không phải huấn luyện model, không cá nhân hoá sâu theo từng câu. Tỉ lệ chấp nhận chỉ tăng khi người dùng có sở thích ổn định theo loại. Test mô phỏng (`tests/test_option_rank.py`, chuyên gia giả thích variant 0,8, ít khi bấm scan 0,05): tỉ lệ bấm top-2 ~0,56 ở vòng 1 (đã học dần trong vòng) lên ~0,70 sau 6 vòng x 60 lượt, so với ~0,375 nếu xếp ngẫu nhiên; mức tối ưu lý thuyết của mô phỏng này là 0,65, các vòng sau dao động quanh đó do lấy mẫu).

### Giao diện "Bộ nhớ của AI" (M4)
Tab **Bộ nhớ** ở cột phải (Alt+7); mã: `MemoryPanel.jsx` (panel), `MemoryCards.jsx` (thẻ trong chat), `memoryApi.js`, `memory.css`.
- **Bản ghi:** lọc theo loại/ trạng thái/ kịch bản/ chuyên gia/ đã ghim/ kèm bản cũ, tìm kiếm; mỗi bản ghi có xác nhận, sửa (lưu thành phiên bản mới kèm lý do), bác, ghim, xoá, và "Nguồn & nhật ký" (tin nhắn nguồn, các phiên bản, nhật ký thay đổi từng bước). Xuất/ nhập JSON (nhập có bước xem trước, mọi bản nhập vào là "đề xuất"; mục bị bộ lọc chặn hiện lý do).
- **Mâu thuẫn:** tab riêng (có số đếm); chọn bản A/ B, giữ cả hai tuỳ ngữ cảnh (bắt buộc ghi điều kiện) hoặc viết bản hợp nhất.
- **Thống kê:** "AI đã học N điều từ M buổi", đếm theo trạng thái/ loại, độ phủ theo hàng hồ sơ từng phòng, số câu hỏi lặp đã tránh, tỉ lệ gợi ý được chấp nhận theo loại.
- **Trong chat:** sự kiện SSE `memory` -> toast "Đã ghi nhớ 2 điều" + thẻ "Mình ghi nhớ: ... đúng không?" [Đúng] [Sửa] [Đừng nhớ] (thẻ mâu thuẫn mở thẳng tab Bộ nhớ); khi AI dựa vào bộ nhớ (`turn.memory_used` hoặc `data.memory_used` của tin) hiện chip "Mình nhớ lần trước bạn nói: ..." mở danh sách kèm nút "Xem / sửa nguồn".
- **Giao diện:** vi/en, nhãn ARIA, vùng trạng thái `aria-live`, cỡ chạm >= 40px, đúng cả sáng/tối, không tràn 375-1920. Không hiện tên nguồn dữ liệu.
- Test/ QA: `tests/test_option_rank.py`, `tests/test_memory_ui_flow.py` (chat -> thẻ -> Đúng/Sửa -> danh sách/ IDOR/ xuất-nhập/ thống kê gợi ý); `services/web-ui/qa/ai_memory.mjs` (MOCK, 375/768/1366/1920 x sáng/tối, axe AA); ảnh `services/web-ui/docs/classroom/mem-*.jpg`.

## Nhận ý định tự nhiên + option gợi ý (2026-10-16)
Người dùng KHÔNG gõ lệnh `/`: chỉ nói bình thường ("Chạy thử xem có lời không", "tim lai nhung lan no xuat hien", "so với mua giữ", "thử khung H4"...). Hợp đồng và interface xếp hạng: `docs/handoff/INTENT_API.md`. Mã: `classroom/intent.py` (thuần) + `intent_api.py`; UI: `Composer.jsx` + `IntentPanel.jsx` + `intentApi.js`.
- Bộ nhận ý định chạy trên mỗi tin của chuyên gia: chuẩn hoá (có dấu/không dấu/viết tắt/lỗi gõ, khớp mờ) + luật từ khoá/ cụm từ có trọng số -> ý định thuộc ALLOW-LIST (chạy thử, quét ví dụ, thử mã/khung khác, biến thể, đối xứng, so sánh, giải thích, tóm tắt, lưu phiên bản, hỏi thêm, vẽ/ chọn nến, đặt lại, xem phiên bản cũ, xuất biên bản, chuyển kịch bản) + trích tham số (mã, khung, khoảng thời gian, đối tượng so sánh). Mọi `command_text` đều qua `parse_command`.
- Việc NẶNG (chạy thử, quét, so sánh, thử mã/khung khác, đặt lại) KHÔNG tự chạy: hiện thẻ xác nhận dạng câu hỏi ("Bạn muốn mình chạy thử kịch bản này trên EURUSD H1 chứ?" [Chạy thử] [Đổi mã/khung] [Không]); chạy thử còn qua bước xác nhận đăng ký giả thuyết sẵn có. Việc NHẸ (tóm tắt, giải thích, biến thể, đối xứng, hỏi thêm, vẽ) tự chạy khi ý chắc + tin ngắn.
- Dòng "AI hiểu ý bạn là: ..." tô sáng từ khoá nhận ra; nút "Không phải ý này" chọn lại ý định hoặc gửi như tin thường. Sau mỗi lượt có 2-4 option bấm được (câu hỏi tiếp theo theo hàng hồ sơ mơ hồ nhất, hành động đoán từ ý định, làm rõ khoảng trống/ mâu thuẫn, biến thể/ đối xứng/ phản ví dụ), xếp hạng bằng `option_rank.rank` (bandit học từ lượt bấm), có "Vì sao gợi ý này".
- LLM (mặc định TẮT, `CLASSROOM_INTENT_LLM=1`): chỉ khi luật không chắc, hạn 3 s, JSON ràng buộc do code kiểm, trần độ tin 0,85, không bao giờ tự chạy. Không phụ thuộc LLM. Tin có mẫu chỉ thị (injection) -> không nhận ý định, coi là dữ liệu.
- Lỗi/ quá hạn của `understand` KHÔNG chặn gửi chat thường. Giới hạn thật: luật từ khoá không phải hiểu ngôn ngữ đầy đủ; câu dài/ giống câu trả lời dạy bị hạ điểm để tránh hiểu nhầm; độ chính xác đo trên bộ 170 câu tự dựng (`tests/test_intent.py`), không phải trên dữ liệu người dùng thật.

## Phương pháp và Kế hoạch áp dụng (2026-10-16)
Tầng trên phòng kịch bản: **Phương pháp** (playbook) gồm nhiều kịch bản liên kết, quy tắc kết hợp và một kế hoạch áp dụng 9 bước. Hợp đồng route/JSON: `docs/handoff/METHOD_API.md`; mã: `classroom/methods.py` (dữ liệu, quan hệ, hồ sơ, chat), `methods_api.py` (route), `methods_plan.py` (kế hoạch + xuất tài liệu). Bảng riêng `class_method_*` trong SQLite lớp học (CREATE IF NOT EXISTS); không sửa logic canvas/độ rõ/nhãn/test khoá, chỉ ĐỌC dữ liệu của chúng.
- **Mô hình**: Phương pháp 1-n Kịch bản (mỗi kịch bản là một phòng sẵn có, giữ nguyên lịch sử; một phòng thuộc tối đa một phương pháp). Gắn phòng sẵn có, tạo kịch bản/phòng mới ngay trong phương pháp, chuyển giữa phương pháp (`move`) hoặc tách ra mà không mất phòng. Vai trò: lõi, bổ trợ, bộ lọc, thử nghiệm (thử nghiệm không tính vào điều kiện áp dụng).
- **Quan hệ**: loại trừ, bổ trợ, ưu tiên (có hướng, cấm vòng), chỉ chạy trong regime (trend/range/high_vol/low_vol), bản đối xứng buy/sell (mỗi kịch bản tối đa một), khung chính/xác nhận. Kiểm hợp lệ phía máy chủ (mâu thuẫn, trùng, vòng); trả kèm đồ thị và thứ tự ưu tiên tính ra.
- **Phòng phương pháp**: chat SSE mức phương pháp, hỏi lần lượt 9 hàng (bối cảnh dùng, thứ tự ưu tiên khi nhiều tín hiệu, rủi ro mỗi lệnh, tổng rủi ro nóng, giới hạn lỗ ngày/tuần, tương quan, quy tắc dừng, danh sách mã/khung, vai trò từng kịch bản). Khung hỏi do CODE quyết, LLM (qua GuardedLLM, hậu kiểm số) chỉ diễn đạt; mất LLM thì dùng câu mẫu. Chống injection như phòng thường. Hồ sơ phương pháp (canvas 9 hàng, độ rõ 0-100, xác nhận/ sửa) dùng chung với chat. Ghi vào bộ nhớ của AI là hook mềm: đề xuất bản ghi `knowledge` trạng thái "đề xuất" (cần người xác nhận); thiếu module/lỗi thì bỏ qua.
- **Kế hoạch áp dụng, 9 bước, tiêu chí tất định** (hằng số ở `methods_plan.THRESHOLDS`, trả kèm trong API): (1) độ rõ >= 80 + 7 hàng bắt buộc đã xác nhận; (2) luật máy đã đăng ký + golden test đạt toàn bộ (>= 3 ví dụ); (3) >= 12 nhãn, độ chính xác >= 0,70, độ phủ >= 0,80; (4) backtest walk-forward: >= 100 lệnh ngoài mẫu, kỳ vọng ròng > 0, CI95 dưới > 0, p so với ngẫu nhiên < 0,05, DSR >= 0,95, PBO < 0,5, đã tính chi phí, VÀ test khoá do master mở một lần có verdict `edge`; (5) ổn định theo mã/khung và theo năm (>= 60% nhóm đủ mẫu dương; nếu có quan hệ regime thì phải có số liệu theo regime); (6) hồ sơ rủi ro đã xác nhận + có số, rủi ro mỗi lệnh <= 2%, rủi ro nóng >= rủi ro mỗi lệnh, SL/huỷ từng kịch bản đã xác nhận, thứ tự ưu tiên khi >= 2 kịch bản, bằng chứng stress (master ghi); (7) paper >= 30 lệnh, >= 12 tuần, sổ hash-chain hợp lệ, kỳ vọng không thấp hơn cận dưới backtest (master ghi bằng chứng); (8) master phê duyệt (chỉ khi 1-7 đạt; hết hiệu lực khi phương pháp đổi phiên bản); (9) tài liệu áp dụng đã xuất ở đúng phiên bản (chỉ tính khi 1-8 đạt). Mỗi bước có trạng thái (đạt/ trượt/ chưa có dữ liệu/ bị chặn), người chịu trách nhiệm, mốc ngày, bằng chứng liên kết, hành động "làm bước này".
- **Trung thực**: thiếu số liệu = "chưa có dữ liệu" (không bịa, không coi là đạt); bước 4-6 trượt -> "CHƯA đủ điều kiện áp dụng" kèm gợi ý hướng sửa (làm rõ ý tưởng, đổi khung/mã, thêm bộ lọc, hoặc dừng; không chỉnh rồi chạy lại test khoá); chưa đạt hẳn 4-6 cũng ghi "CHƯA đủ điều kiện"; "đủ điều kiện áp dụng (nghiên cứu/paper)" chỉ khi đủ cả 9 bước. Không có đường đặt lệnh; vốn thật cần cổng pháp lý G1-G3.
- **Xuất tài liệu**: `GET .../plan/export?format=md|pdf`. Markdown "Kế hoạch áp dụng phương pháp X": kịch bản, quy tắc kết hợp, hồ sơ phương pháp, pipeline, số test thật (nói thẳng nếu không có edge), rủi ro, việc còn thiếu, quyết định cần người dùng. PDF tự dựng trong máy chủ (không có công cụ ngoài trong image), chữ không dấu.
- **Quyền**: master thấy/sửa mọi phương pháp; chuyên gia chỉ phương pháp của mình; ghi bằng chứng và phê duyệt chỉ master; 404 đồng nhất chống IDOR; gắn phòng cần quyền ở cả phòng lẫn phương pháp. Test: `tests/test_methods.py`, `tests/test_methods_plan.py`.
- **Cách dạy hiệu quả ở mức phương pháp**: trước hết dạy từng kịch bản đến độ rõ >= 80, rồi mới khai báo quan hệ; điền số cụ thể ở hồ sơ rủi ro (rủi ro/lệnh, rủi ro nóng, giới hạn lỗ); đừng đợi backtest đẹp mới ghi giới hạn; nếu kết quả trượt, quay lại làm rõ ý tưởng thay vì chỉnh tham số.

### Giao diện màn "Phương pháp" (L4, 2026-10-16)
- Vị trí: master = tab **Phương pháp** trong AI Trading; chuyên gia = nút chuyển **Phòng kịch bản / Phương pháp** ở đầu trang AI Training Class. Mã: `services/web-ui/app/src/components/classroom/` (`MethodsPage.jsx` danh sách + tạo/sửa/xoá mềm, `MethodView.jsx` 4 tab, `MethodDiagram.jsx` sơ đồ SVG, `MethodRelations.jsx` bảng quy tắc, `MethodRoom.jsx` phòng + hồ sơ, `MethodPlan.jsx` kế hoạch, `methodsApi.js` chuẩn hoá + SSE, `methods.css`). Tái dùng `Bubble`, `Composer`, `ProfileCanvas` (thêm prop `title`).
- Tab **Tổng quan**: thanh tiến độ x/9, biển trạng thái, sơ đồ (nút = kịch bản, bấm hoặc Enter mở phòng của nó; nét: loại trừ đứt, bổ trợ liền xanh, ưu tiên có mũi tên, regime chấm + nhãn trên nút, đối xứng gạch-chấm, khung xác nhận có mũi tên; mỗi quan hệ có nhãn chữ), bảng kịch bản (vai sửa được, độ rõ, kết quả test thật, paper, mở phòng, tách khỏi phương pháp) + thêm kịch bản mới hoặc gắn phòng có sẵn (409 -> hỏi chuyển).
- Tab **Quy tắc kết hợp**: thêm/ sửa/ xoá quy tắc, lưu bằng PUT cả danh sách; lỗi 422 của máy chủ hiện nguyên văn; cảnh báo máy chủ hiện dưới bảng.
- Tab **Phòng phương pháp**: chat SSE `methods/{mid}/messages`, nút gợi ý (chip của lượt AI cuối) + 4 câu mở đầu, hồ sơ phương pháp 9 hàng (xác nhận/ sửa qua `canvas/{key}/confirm|edit`).
- Tab **Kế hoạch áp dụng**: 9 bước (trạng thái có ký hiệu + chữ, bảng tiêu chí yêu cầu/ thực tế/ đạt, bằng chứng, nút làm bước này mở đúng phòng/ tab), "Kiểm tra lại", xuất Markdown/PDF, master ghi bằng chứng + duyệt. Biển đỏ "CHƯA đủ điều kiện áp dụng" + hướng sửa hiện cho mọi trạng thái trừ `eligible_review`/`ready`; client còn tự hạ `ready` về `incomplete` nếu bước 4-6 chưa `passed`. Không bao giờ hiện chữ "sẵn sàng giao dịch"; vốn thật vẫn cần G1-G3.
- QA: `services/web-ui/qa/ai_methods.mjs` (+ `run_ai_methods.sh`, fixture mock cùng schema METHOD_API), ảnh `services/web-ui/docs/classroom/ux-m*.png`.
