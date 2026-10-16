# LLM cục bộ (local-llm) — giảm token Claude cho việc cơ học

> Trạng thái: đã điền số đo thật từ L1/L2/L3 (2026-10-15).

## 1. Kiến trúc
- Mục tiêu: mọi công cụ gọi MỘT địa chỉ `http://local-llm:8080` (API OpenAI-compatible; /v1/messages kiểu Anthropic nếu bản llama.cpp hỗ trợ). Chạy CPU (Xeon Gold 6130, AVX512, không GPU), mạng nội bộ, KHÔNG publish cổng.
- Router/LB (L1): llama-swap hoặc nginx upstream + metrics Prometheus + Gatus. Theo infra/local-llm/config.yaml (L1): llama-swap, mỗi lúc nạp 1 model 30B (ttl 600 s), `--threads 24 --parallel 3 --ctx-size 49152 --flash-attn on --cache-reuse 256`, bọc `guard.sh` (từ chối khi load host > 60, nice 19). Container `local-llm` (llama-swap, mạng ops+backend). Cấu hình triển khai thực tế: 12 luồng ghim cpuset 20-31,52-63, parallel 3, ctx 49152, mem_limit 30g (24 luồng không ghim làm p95 feed vọt 2,43 s nên đã bỏ).
- Image llama.cpp pin sha (infra/docker-compose.tools.yml, dịch vụ briefing-llm). Model GGUF tải miễn phí từ HuggingFace, kiểm sha256.
- Model: Qwen3-30B-A3B-Instruct-2507 Q4_K_M (tổng quát, đo ~11,5 tok/s sinh, ~24 GB RAM), alias `code` = Qwen3-Coder-30B-A3B Q4_K_M (sha256 khớp), alias `general` = Qwen3-30B-A3B-Instruct-2507. Đo thật (host tải 40-60): general ~30 tok/s đọc, ~6,5 tok/s sinh; code ~32 / ~5,2.
- Giới hạn tài nguyên: nice thấp hơn đường giá, cpus <= 28; tạm dừng khi load VPS > 60/64.

## 2. Địa chỉ và alias model
| alias | model | ctx | slot |
|---|---|---|---|
| `code` | Qwen3-Coder-30B-A3B-Instruct Q4_K_M | 49152 | 3 |
| `general` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M | 49152 | 3 |

(đã triển khai; xem số đo ở mục model và LLM_L1_status.md)

## 3. Dùng `la` (infra/ops/la, L2)
Lệnh: `la fix-lint`, `la add-test <file>`, `la docs <topic>`, `la triage-log <service>`, `la summarize <file>`, `la commit-msg`, `la explain-error`, `la run-tests <service>`, `la issue-fix <mã lỗi>`; cờ `--dry-run` và `--review` (in diff, chưa áp dụng). Biến: LA_LLM_URL, LA_MODEL (code|general), LA_PARALLEL (<=2), LA_TIMEOUT; `la stats` in bảng tỉ lệ thành công theo loại task (từ data/la/decisions.jsonl).

## 4. Chính sách router Dễ / Vừa / Khó
- Dễ (cấu hình, lint, test cũ, docs, lỗi 1 file rõ ràng): chạy local.
- Vừa: thử local trước; nếu test không xanh sau N lần thì leo thang lên Claude (ghi lý do).
- Khó (thiết kế, debug phức tạp, nhiều file, không có test tái hiện): Claude ngay.
- Bảng quyết định + kết quả được ghi để học tỉ lệ thành công theo loại task. Luật thật (infra/ops/la_lib/router.py): Dễ = fix-lint, summarize, commit-msg, explain-error, triage-log, run-tests, docs với 1 file (local 1 lần); Vừa = add-test/issue-fix có test tái tạo, hoặc task Dễ nhưng 2-3 file (local tối đa N=2 lần rồi leo thang Claude); Khó = > 3 file, từ khoá race/deadlock/schema/migration/security/auth/concurren/thiết kế/design, issue-fix không có test tái tạo, loại task lạ (cần Claude, không chạy local). Quyết định ghi vào data/la/decisions.jsonl.

## 5. Mở rộng dung lượng: node phụ
Script `infra/ops/llm_node.sh` (đã viết, CHƯA chạy trên máy nào; chỉ chạy khi cần, bởi phiên có SSH).
```
infra/ops/llm_node.sh [--dry-run] add|remove|status <host>   # host thuộc Tier A: sv-51, sv-45, sv-02, sv-56
infra/ops/llm_node.sh [--dry-run] list | render | tunnels | reload   # chạy trên máy LB (VPS trading)
```
- Trên node chỉ có: container `tsllm-node` + volume `tsllm-node-models`, giới hạn cpus=8, mem 24 GB (swap = mem), cpu-shares=64, `nice -n 19`, cap-drop ALL, read-only, no-new-privileges. Cần node còn >= 40 GB đĩa và >= 26 GB RAM khả dụng (script kiểm trước).
- Model tải từ HuggingFace (miễn phí), kiểm sha256: ưu tiên `infra/local-llm/models.sha256` (ghim, định dạng `<sha256>  <tên-tệp>`), nếu chưa ghim thì lấy oid LFS từ HF API; sai sha thì xoá tệp và dừng.
- Mạng: cổng KHÔNG ra internet. Chế độ mặc định `ssh`: node chỉ bind 127.0.0.1:8080; máy LB mở tunnel `ssh -L 172.17.0.1:<18100+n>:127.0.0.1:8080` (ControlMaster, ServerAlive) — chỉ container trên docker0 của VPS tới được. Chế độ `wg` (`NODE_MODE=wg NODE_WG_IP=<ip wg>`): bind vào IP WireGuard riêng, LB trỏ thẳng `<ip wg>:8080`.
- Đăng ký vào LB: file `infra/local-llm/nodes.list` (`name|ssh|mode|endpoint|weight`) -> `render` sinh `infra/local-llm/upstream.nodes.conf` (các dòng `server ... max_fails=2 fail_timeout=30s;`) -> nginx của local-llm `include` tệp này trong khối `upstream` -> `reload` chạy `nginx -t && nginx -s reload` (không downtime; node chết tự bị loại sau 2 lỗi). L1 dùng llama-swap nên `render` sinh thêm `infra/local-llm/upstream.nodes.llama-swap.yaml` (mỗi node = model `general-<node>` với `proxy:` tới node) để dán vào `models:`; CHƯA kiểm với llama-swap thật (cơ chế `peers` nếu bản có hỗ trợ thì phù hợp hơn). Bản nginx upstream dùng được nếu L1 đặt nginx phía trước; `LLM_LB_CONTAINER` chỉ định container để reload.
- `remove <host>`: dừng + xoá container, volume model, bỏ khỏi danh sách, đóng tunnel, render + reload lại. Đặt `LLM_ALLOW_ANY=1` mới cho máy ngoài Tier A.
- Kiểm nhanh không SSH thật: `infra/ops/llm_node.sh --dry-run add sv-51` (in lệnh sẽ chạy).
- Biến chỉnh: LLM_HF_REPO, LLM_MODEL_FILE, LLM_CTX, LLM_THREADS, LLM_PARALLEL, LLM_NODE_PORT, LLM_TUNNEL_BIND, LLM_LB_CONTAINER.

## 6. Giới hạn (trung thực)
- CPU chậm: ~10-12 tok/s sinh, đọc prompt chậm (~31 t/s đo ở 16 luồng) nên prompt dài tốn phút; song song hạn chế.
- Yếu hơn Claude ở: suy luận nhiều bước, thay đổi nhiều file, thiết kế/kiến trúc, debug khó, tuân thủ định dạng dài. Tạm ổn: tóm tắt, phân loại lỗi, lint, commit message, docs ngắn.
- Benchmark 20 task: alias `code`: 20/20, 108 s, ~3,1k token; model 9B briefing: 15/20 (lỗi: không xoá import thừa, gán nhãn lỗi sai). Benchmark dễ (1 file, đầu vào ngắn) nên 100% chưa đại diện việc thật; local yếu ở lập luận nhiều file, debug nguyên nhân gốc, JSON dài. Chi tiết LLM_L2_status.md.

## 7. An toàn
- Không đưa secret vào prompt/log/repo; container agent không có secret, không mạng ngoài ngoài local-llm.
- Local KHÔNG tự merge: mọi thay đổi qua nhánh git + test liên quan xanh + người/phiên Claude duyệt.
- Allow-list công cụ (đọc/ghi file trong repo, grep, test/lint cho phép, git diff/commit), giới hạn số bước và timeout.
- Node phụ: không publish cổng, dọn sạch bằng `remove`.

## 8. Ảnh hưởng đường giá (p95)
p95 feed (fx): 0,356 s trước khi bật; 0,245 s khi LLM chạy đầy tải (12 luồng + cpuset); 0,315-0,335 s lúc swap sang `code` — đạt <= 0,5 s. Chưa đo lại ở mức tải host khác.

## 9. Token và tiết kiệm
Theo dõi ở docs/handoff/TOKENS.md (L3): token Claude theo phiên/ngày và token local theo loại task; mục tiêu >= 50% khối lượng token việc cơ học chuyển sang local. Đo thật 2026-10-15 (tokens_report.py, từ ~/.claude): Claude ~516k output, 7k input, 330M cache_read; token local chưa có (data/la/tokens.jsonl chưa tồn tại lúc viết). Digest định kỳ: docs/handoff/DIGEST.md (cron */30, nice 19, bỏ qua khi load > 60); metric token chưa vào Prometheus (cần root cho phép ghi textfile dir).

## 10. Pool node từ xa (nối 2026-10-16)
- Nguồn: `data/ai-pool/nodes.json` (5 node llama.cpp, Qwen3-30B-A3B-Instruct-2507 Q4_K_M, 4 nhân/24 GB mỗi node; khoá Bearer ở `data/ai-pool/pool_key`, chỉ đọc lúc chạy, không in/ghi vào log hay repo).
- Router: `infra/ops/la_lib/pool.py` + `llm.py`. Nạp lại nodes.json khi mtime đổi; bỏ node `status != up`, quá `expires_at` (TTL 48 h, gia hạn bằng `/opt/ai-pool/KEEP_UNTIL` trên pool) hoặc vừa lỗi (loại tạm 60 s); cân bằng theo slot rảnh (mỗi node 1 slot, flock giữa các tiến trình, ưu tiên node nhanh nhất). Pool rỗng/lỗi -> rơi về `local-llm` (≤2 song song). `LA_USE_POOL=0` để tắt; đặt `LA_LLM_URL` thì bỏ qua pool.
- Giới hạn node: ctx 4096 (1 slot) -> prompt + đầu ra phải vừa ~4k token; vượt thì lỗi 400 và tự rơi về local-llm (không coi là node chết). Đã thử `la summarize` (1037+304 token) qua pool OK.
- Số đo thật (10 yêu cầu song song, 200 token đầu ra, rải đều 5 node): tổng 1934 token sinh / 43,9 s = ~44 token/s thực tế (đã gồm đọc prompt và chờ slot); số danh nghĩa theo nodes.json là ~69 token/s (cộng tok_s_gen của 5 node: 14,2+9,6+13,7+15,7+15,9).
- Benchmark 20 task mẫu qua pool (tuần tự): 20/20, 102 s, 1973+1104 token (xem la_bench). Lưu ý benchmark dễ.
- Dữ liệu (mã/prompt) gửi tới máy ngoài VPS: chỉ dùng cho việc không nhạy cảm; không đưa secret vào prompt.

### 10b. Router `ai-pool-lb` (container, http://ai-pool-lb:8080)
- Dịch vụ `ai-pool-lb` (`infra/local-llm/pool_lb.py`, stdlib, python:3.12-slim, user cc để đọc `pool_key`, mạng ops + internal để ra các node, không publish cổng). Cùng API OpenAI-compatible; nạp lại nodes.json khi đổi; health check node mỗi 15 s; 1 slot/node, chọn node rảnh nhanh nhất, hàng đợi tối đa 90 s; header Bearer từ pool_key; prompt ước > 3000 token hoặc pool rỗng/lỗi -> dự phòng `local-llm:8080`.
- Metrics Prometheus (`/metrics`: yêu cầu, lỗi, fallback, token, node up/busy), job `ai-pool-lb` + check Gatus `ai-pool-lb`.
- Test thật qua router: 10 yêu cầu song song (200 token đầu ra mỗi yêu cầu): 1940 token / 41,3 s = ~46,9 token/s, 0 lỗi, 0 fallback, mỗi node nhận 2 yêu cầu (nodes_up=5).
- Giới hạn: phản hồi stream bị gom (không chảy từng token); đường dự phòng local-llm khi pool rỗng/prompt dài chưa kiểm bằng đo.

### 10c. Kiểm `la` (2026-10-16, qua pool)
- `la summarize` OK (1037+304 token, 51 s); `la triage-log api-gateway` OK sau khi sửa tìm container có hậu tố `-1`; `la run-tests risk-monitor`: 61 passed, XANH (44 s). Benchmark 20 task: 20/20 (102 s).

## 11. Teardown pool
- Script: `infra/ops/ai-pool-teardown.sh` — gỡ pool llama.cpp theo `data/ai-pool/nodes.json` khi người dùng báo xong hoặc trước TTL (`expires_at`, sớm nhất 2026-10-17 11:00Z).
- Mặc định CHỈ in kế hoạch (không kết nối). `--yes` mới gỡ thật; `--verify` kiểm chỉ-đọc (không còn container `ai-pool-llm*`, rule iptables comment `ai-pool`, `/opt/ai-pool`, socket cổng 18080; thêm thử cổng từ ngoài); `--only <node>` giới hạn node.
- Truy cập: SSH BatchMode. Đích: `AI_POOL_SSH_<TÊN>` > `data/ai-pool/ssh_targets` (`name user@host`) > `root@<ip>`; khoá qua ssh-agent hoặc `AI_POOL_SSH_KEY`. VPS trading không có khoá tới node (pool do laptop điều phối triển khai) -> chạy từ máy có truy cập.
- Chỉ dọn tài nguyên pool; rule cổng 18080 không có comment `ai-pool` chỉ bị cảnh báo, không xoá. `ai-pool-lb` trên VPS này không bị đụng.
- Sau gỡ script KHÔNG sửa nodes.json; tự đặt `"status":"removed"` (hoặc xoá node) để router/LB loại node.
