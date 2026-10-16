# data-keeper — giám sát phủ dữ liệu (K5: LLM + API + trang "Dữ liệu")

Service `services/data-keeper` (container `tradingsys-data-keeper`, nội bộ :8000). Phần K5 gồm `llm.py`, `api.py`, proxy gateway và trang UI. Vòng kiểm kê/tự chữa/lấp gap/nạp lịch sử do K1-K4 (xem `docs/handoff/TASK_data_keeper.md`).

## LLM cục bộ (`llm.py`)
- Dùng llama.cpp nội bộ (`DATA_KEEPER_LLM_URL`, mặc định `briefing-llm:8080`; `DATA_KEEPER_LLM_ENABLED=0` để tắt; `DATA_KEEPER_LLM_TIMEOUT_S`). CHỈ viết văn bản tiếng Việt (chẩn đoán, báo cáo); không công cụ, không hành động. Hành động hạ tầng chỉ qua allow-list ở `heal.py`.
- An toàn: prompt chỉ chứa "facts" đã lọc (`make_facts`: số đếm + mã hợp lệ; bỏ mọi khoá tài khoản/mật khẩu/token; chuỗi tự do không vào prompt). Đầu ra được kiểm (`validate_output`): đúng schema, mọi số/mã phải có trong facts, không URL/tên nguồn/mẫu chỉ thị; sai là dùng bản mẫu.
- Fallback tất định (`template_diagnosis`, `template_daily`): dùng khi LLM tắt, lỗi (nghỉ 2 phút), trả rác, hoặc khi mọi thứ khoẻ (không tốn CPU). Câu chốt báo cáo ngày luôn tất định: "Đủ N/162 mã, lấp X gap, Y mã im lặng vì thị trường đóng".

## API (service, qua gateway chỉ master)
| Đường dẫn | Mô tả |
|---|---|
| `GET /v1/data/health` | tổng quan + ma trận mã x khung + chẩn đoán (LLM chạy nền, cache 5 phút) |
| `POST /v1/data/recheck` | kiểm kê lại ngay (nhẹ; 1 lần/20 giây; gateway: master + Origin + CSRF; nginx whitelist đúng đường này) |
| `GET /v1/data/report/daily` | báo cáo ngày (cache 15 phút; `?fresh=1`) |
| `GET /v1/data/decisions?limit=` | nhật ký quyết định + lời giải thích tất định (khoá trắng: kind/symbol/tf/ok/count/ts) |

`build_router(ctx, llm)` được main.py gắn vào app. Đọc `ctx.matrix` (bộ nhớ) hoặc `dk.coverage` (symbol, tf, last_bar, last_tick, gaps, status, updated_at) và `dk.actions` (ts, kind, symbol, tf, ok, detail jsonb). `ctx.recheck()` và `ctx.queue_len()` tuỳ chọn. `DATA_KEEPER_MOCK=1` hoặc ctx=None: dữ liệu mẫu. Trạng thái mã = tồi nhất theo khung (BROKEN > SLOW > OK; CLOSED khi mọi khung đóng).
Gateway: `api_gateway/datakeeper_routes.py` (`DATA_KEEPER_URL`, mặc định `http://data-keeper:8000`), client/vai trò phụ nhận 403, đầu ra qua `scrub_obj`. `data-keeper` đã thêm vào `DEFAULT_HOSTS` của `tscommon.internal_auth` (gắn X-Internal-Token).

## UI
Trang `#/du-lieu` ("Vận hành" > Dữ liệu, chỉ master): tổng quan, chẩn đoán, báo cáo ngày, bảng phủ mã x khung (lọc nhóm/trạng thái/tìm mã; ký hiệu + màu), nút "Kiểm tra lại", nhật ký quyết định. KHÔNG hiện tên nguồn dữ liệu. QA 1440/1024/768/375, sáng/tối, không cuộn ngang.

## Việc lead cần làm khi deploy
Thêm service vào compose + `DATA_KEEPER_URL`; nginx web-ui đã có dòng cho `POST /api/v1/data/recheck`; build lại api-gateway + web-ui; main.py gọi `app.include_router(build_router(ctx))`.

## Cập nhật 2026-10-16 (cảnh báo không báo giả)
- `sessions.py`: TECHDE30 có cửa sổ báo giá hẹp 08-15 UTC (broker không báo giá ngoài khung này); mã giới hạn giờ thuộc nhóm chỉ số vẫn được xếp nhóm "index".
- `heal.py`: mã BROKEN nhưng còn tick tươi (<= 300 s) thì KHÔNG tính là "im lặng": không đưa vào resync/restart feed, báo riêng `bars_missing` ("còn giá nhưng thiếu nến M1 (nguồn nến)"). Cảnh báo `feed_partial` chỉ còn cho mã thật sự không có tick.
- Heal vẫn DRY-RUN (`DK_HEAL_DRY_RUN=true`): chưa có proxy docker cho phép POST (`DK_DOCKER_RESTART_URL`) và hiện không cần; tối đa 2 restart feed/giờ khi bật.
- mt-bridge `feed_fb` (FEED_FALLBACK_ENABLED, mặc định bật): 7 mã chuỗi cũ nhận nến M1 từ EA feed khi EA lab cũ im > 5 phút.
- Bảng 162 mã + nguyên nhân NO_SOURCE: `docs/handoff/FEED_ALL_status.md` (mục 2026-10-16).

## Chạy range an toàn / chống job-mt5.cfg bỏ quên (2026-10-16)
Sự cố 2026-10-15: `job-mt5.cfg` (MTAgentRange) còn sót -> terminal live `mtlab-mt5` chạy SCRIPT thay EA đọc live, canon M1 của 7 mã chính khuyết 15/10 10:12 -> 16/10 07:47 UTC.

**Quy tắc: KHÔNG chạy range/export trên terminal live `mtlab-mt5`.** Dùng terminal phụ `mtlab-mt5-hist` (volume Wine riêng, cùng tài khoản investor, không gửi dữ liệu lên bridge):
1. Chép `MTAgentRange.ex5` vào volume hist (một lần): `docker cp mtlab-mt5:"/wine/drive_c/Program Files/MetaTrader 5/MQL5/Scripts/MTAgentRange.ex5" <tmp> && docker cp <tmp> "mtlab-mt5-hist:/wine/drive_c/Program Files/MetaTrader 5/MQL5/Scripts/"`.
2. Trong `data/mtlab-hist/out/`: sao lưu `job-mt5.cfg`, đặt `job-mt5.cfg` = `MTAgentRange` / `MTAgentRange.set`; `MTAgentRange.set` = `Mode=range`, `XchgDir=xchg`, `PollMs=1000`, `MaxRangeBars=5000`. `docker start mtlab-mt5-hist`, đợi thư mục `MQL5/Files/xchg` xuất hiện (~1 phút).
3. `python3 infra/ops/fill_canon_gap.py --dry-run` rồi chạy thật (`--from 2026-10-15T00:00` căn đầu ngày UTC để gộp H4/D1 đúng). Ghi `source=canon:mt5:100000001`, tự dò lệch giờ máy chủ bằng cách đối chiếu H1 đã có, M1/M5/M15/H1 native, H4/D1 gộp từ H1 theo mốc UTC, idempotent (ON CONFLICT DO NOTHING; nến đang dở có volume thấp hơn bản native được cập nhật). ~1 phút cho 7 mã x 32 giờ; không đụng EA live.
4. Dọn NGAY: `docker stop mtlab-mt5-hist`, trả `job-mt5.cfg` cũ (MTAgentExport) trong `data/mtlab-hist/out/`, xoá `MTAgentRange.set`.
Lần 2026-10-16: 10.866 nến chèn mới + 18 nến dở cập nhật (M1 8.400, M5 1.697, M15 575, H1 147, H4 40, D1 7); p95 giá không đổi (0,242 s trước/sau).

**Nếu buộc phải dùng terminal live** (không khuyến nghị): cfg phải là SYMLINK. `/root/mtlab/out/job-mt5.cfg` -> `xchg/job-mt5.cfg` (đã tạo; data-keeper mount `/xchg` nên thấy file). Tạo job: ghi nội dung vào `/root/mtlab/out/job-mt5.cfg` rồi `docker restart mtlab-mt5`; xong việc `rm -f /root/mtlab/out/xchg/job-mt5.cfg` + restart để trả EA; đo lại `infra/ops/feed_latency.py` và thời gian EA mất kết nối (phút).

**Chống tái diễn (3 lớp)**
- `backfill.guard_job_cfg()` chạy mỗi chu kỳ data-keeper (5 phút, kể cả khi backfill tắt): thấy `/xchg/job-mt5.cfg` -> log WARNING + gauge `dk_range_job_cfg_age_seconds`; quá `DK_JOB_CFG_TTL_S` (mặc định 1800 s) -> XOÁ file + log ERROR + counter `dk_range_job_cfg_removed_total` (terminal chỉ đọc cfg lúc khởi động nên EA trở lại ở lần restart kế tiếp: cần `docker restart mtlab-mt5`, sau khi kiểm tra LiveUpdate).
- Cảnh báo Prometheus `MtRangeJobCfgStale` (`dk_range_job_cfg_age_seconds > 900`, 1 phút).
- `start-term.sh` (bản repo `mt-agent/lab/scripts/`, đã cài vào `/root/mtlab/scripts/`, bản cũ `.bak-20261016`): cfg dạng symlink cũ hơn `JOB_TTL_MIN` (mặc định 120) phút lúc khởi động bị bỏ qua (đổi tên `.stale-<ts>`) và chạy EA. cfg file thường (terminal phụ hist) không bị TTL.

**Không restart `mtlab-mt5-feed`** khi chưa cần, và hạn chế restart `mtlab-mt5`: khởi động kích LiveUpdate tải `terminal64.exe` mới gây lỗi "debugger found" (Wine 9) -> terminal không lên. Đã khắc phục 2026-10-16 bằng cách chép `terminal64.exe`/`MetaEditor64.exe` chuẩn (md5 `d2aac9ff...`) từ `mtlab-mt5-feed` sang `mtlab-mt5`; bản lỗi lưu ở `/out/bak/terminal64.new.exe`. Nếu lỗi lặp lại: dừng container, chép lại hai file này từ volume feed (`mtlab_feedwine`) rồi start; không để restart tự động hoá.
