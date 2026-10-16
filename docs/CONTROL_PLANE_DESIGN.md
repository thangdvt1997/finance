# CONTROL_PLANE_DESIGN — mặt phẳng điều khiển an toàn cho giai đoạn sau (2026-10-12)

> TRẠNG THÁI: THIẾT KẾ. KHÔNG có mã thực thi lệnh nào được thêm theo tài liệu này. Hệ thống hiện vẫn READ-ONLY (mt-bridge, mt-agent, paper-trader chỉ mô phỏng). Mọi nội dung từ bậc L2 trở lên chỉ được bắt đầu sau cổng pháp lý G1-G3 (PLAN.md mục 0) và có văn bản của luật sư. Đây không phải tư vấn pháp lý hay đầu tư. Chỗ nào ghi "chưa xác minh" nghĩa là chưa kiểm chứng bằng nguồn gốc.
> Tài liệu liên quan: PLAN.md, docs/CLIENT_PLATFORM.md, docs/AUTH.md, docs/STRATEGY_OPTIONS.md, docs/HARDENING.md, docs/research/ARCH_AUDIT.md (X-1..X-4, S-6, S-8), mt-agent/README.md, services/mt-bridge/README.md.

## 1. Mục tiêu, phi mục tiêu, bậc thang năng lực

### 1.1 Mục tiêu
1. Khi người dùng sẵn sàng (qua G1-G3, có phương thức giao dịch đã kiểm chứng), việc thêm điều khiển KHÔNG phá các bảo đảm an toàn hiện có (không mở cổng vào, không lưu mật khẩu giao dịch, audit bất biến, least-privilege).
2. Mặc định an toàn: mọi thành phần lỗi/mất kết nối/bị chiếm thì lệnh KHÔNG được thực thi (fail-closed).
3. Quyền của CLIENT là cao nhất đối với tài khoản của chính họ: client bật/tắt, đặt giới hạn, và master không thể vượt.
4. Tiến lên từng bậc có tiêu chí đo được, không nhảy bậc.

### 1.2 Phi mục tiêu
- Không tối ưu lợi nhuận, không hứa hẹn lợi nhuận (docs/STRATEGY_OPTIONS.md: chưa có phương pháp chắc chắn có lãi).
- Không lưu/chuyển mật khẩu giao dịch hay investor của client. Không "quản lý tài khoản hộ" bằng cách giữ credential.
- Không cho LLM ra lệnh, duyệt lệnh, hay sửa tham số rủi ro (xem 5).
- Không HFT/market making; độ trễ mục tiêu cấp giây, không phải micro-giây.
- Không thay thế cơ chế dừng lỗ/margin của broker.

### 1.3 Thang bậc L0-L4
```
L0 Theo dõi        (HIỆN TẠI)  EA chỉ đọc -> bridge -> dữ liệu/báo cáo/cảnh báo
L1 Cảnh báo/khuyến nghị        hệ thống nói "nên cân nhắc X", người dùng tự làm tay; KHÔNG có kênh lệnh
L2 Đề xuất + duyệt từng lệnh   master/strategy đề xuất lệnh -> client DUYỆT TỪNG LỆNH trên EA -> EA thực thi
L3 Tự động trong hộp cát       EA thực thi lệnh đã qua risk engine MÀ KHÔNG hỏi từng lệnh, trong giới hạn client đặt
L4 Phân phối tín hiệu/copy     1 master (nguồn tín hiệu) -> nhiều client, mỗi client có giới hạn riêng
```
| Bậc | Điều kiện tiên quyết (phải đạt TẤT CẢ trước khi bật cho tiền thật) |
|---|---|
| L1 | Không cần cổng pháp lý cho phần dữ liệu (STRATEGY_OPTIONS A) nhưng nội dung KHÔNG được trình bày như tư vấn đầu tư cá nhân hoá nếu chưa hỏi luật sư; ghi rõ disclaimer; không có kênh lệnh trong mã (giữ test `test_no_trading_code_anywhere`). |
| L2 | G1-G3 có văn bản; ToS broker cho phép EA/algo; chọn nền tảng/broker; phương thức giao dịch đã backtest trung thực + paper-shadow >= 8 tuần (STRATEGY_OPTIONS lộ trình 3); command bus + risk engine + kill-switch 4 tầng + audit hash-chain đã có test; thử kill-switch < 2 giây trên demo; client opt-in + điều khoản; chạy trên DEMO >= 4 tuần không lệch đối soát. |
| L3 | Đã vận hành L2 >= 3 tháng trên vốn nhỏ không sự cố P0/P1; giới hạn cứng tầng EA đã chứng minh chặn được lệnh vượt cả khi master bị giả lập (red-team); luật sư xác nhận mô hình (tự động hoá cho chính chủ tài khoản vs. cho người khác); 4-eyes cho kích hoạt; báo cáo drift sạch >= 30 ngày. |
| L4 | Luật sư xác nhận bằng văn bản (copy-trading/quản lý tài khoản hộ/phân phối tín hiệu có thể cần giấy phép — CẦN LUẬT SƯ, chưa xác minh); từng client ký điều khoản + cảnh báo rủi ro riêng; L3 ổn định >= 6 tháng; mô hình trượt giá/chia lô đã kiểm; tiêu chí công bằng phân phối (không ưu tiên master/nội bộ vào trước client). |
Mọi tiêu chí "chuyển bậc xuống" (hạ bậc) là tự động và tức thì (xem 4.6); chuyển bậc LÊN là thủ công, 4-eyes, có độ trễ (cooldown).

## 2. Kiến trúc kênh lệnh

### 2.1 Nguyên tắc
- EA CHỦ ĐỘNG kéo (outbound HTTPS), không mở cổng vào, không Socket server (kế thừa mt-agent: không dùng Socket, WebRequest HTTPS).
- Bridge KHÔNG tin master: lệnh phải mang chữ ký của dịch vụ `command-signer` (khoá riêng không nằm ở bridge/web) VÀ qua risk engine. Bridge chỉ là đường vận chuyển, không có khoá ký lệnh.
- EA tự kiểm tra: chữ ký, hạn dùng, nonce, giới hạn tầng EA, quyền client (xem 3.2). Một mình EA là chốt cuối cùng.
- Tách vùng theo ARCH_AUDIT X-1: (A) Data hiện tại, (B) Strategy chỉ đề xuất, (C) Execution/command bus + signer + risk engine ở vùng mạng và Redis/Postgres RIÊNG. A/B không nối trực tiếp C; giao tiếp một chiều qua hàng đợi "order proposals" có chữ ký.

### 2.2 Sơ đồ
```
 Strategy / Master console / Copy-source          (vùng B: chỉ ĐỀ XUẤT, không có khoá ký)
            |  proposal (JSON schema nghiêm, ký bởi danh tính dịch vụ)
            v
 +-------------------- vùng C (mạng riêng, DB/Redis riêng) --------------------+
 |  proposal-intake --> RISK ENGINE (tất định, 3.1) --> approval-gate (L2: chờ  |
 |                         |   ^                          client duyệt)          |
 |                  halt / lease                              |                 |
 |                  KILL-SWITCH (tiến trình riêng, 3.3)       v                 |
 |                                         command-signer (Ed25519 per-account)|
 |                                                |                             |
 |                      command_outbox (Postgres, write-ahead, append-only)    |
 +------------------------------------------------|----------------------------+
                                                   v
                         mt-bridge (đường vận chuyển, KHÔNG ký, KHÔNG sửa lệnh)
                                                   ^   |
                    EA kéo (long-poll, outbound)   |   | trả ack/nack/fill
                                                   |   v
                 EA (client terminal) = giới hạn cục bộ + opt-in + thực thi + báo kết quả
                                                   |
                                                   v
                                          broker (tài khoản của client)
 Đối soát: EA đẩy vị thế/deals (đã có account.snapshots, account.deals) -> reconciler so với trạng thái lệnh
```

### 2.3 Giao thức EA kéo lệnh (đề xuất, thêm vào bridge ở giai đoạn sau)
- `POST /cmd/v1/poll` (long-poll 20-25 giây, EA gửi `last_acked_seq`, `ea_state_digest`): trả danh sách lệnh chưa ack hoặc rỗng. Lý do chọn HTTPS long-poll thay WebSocket cho MQL: `WebRequest` đồng bộ, MT4 chỉ cổng 80/443, WebSocket gốc không có trong MQL (cần DLL/thư viện — tránh; chưa xác minh phương án thay thế ổn định). WebSocket outbound chỉ xét khi có client không phải MT.
- Lưu ý: WebRequest chặn luồng EA khi chờ; timeout của long-poll phải < timeout WebRequest và EA phải xử lý `OnTimer` không để treo vòng giám sát. Có thể cần 2 EA/2 chart (một cho dữ liệu, một cho lệnh) — CHƯA XÁC MINH, cần spike. Tách EA lệnh khỏi EA đọc để EA đọc hiện tại giữ nguyên "không có hàm giao dịch" (kiểm bằng test tĩnh).
- Hai EA tách biệt: `MTAgentReadOnly` (hiện tại, không bao giờ có mã giao dịch) và `MTAgentExec` (mới, build riêng, mã nguồn/ký riêng, client chủ động cài thêm). Client không opt-in thì không có file thực thi nào trên máy.

### 2.4 Mô hình thông điệp lệnh (envelope ký)
```
Command {
  v: 1,
  cmd_id: UUIDv7                  # do command-signer sinh, duy nhất toàn cục
  client_order_id: str            # idempotency key; = "<strategy>-<seq>-<hash8>"; ghi vào comment + magic của lệnh MT
  account_id: "mt5:12345678"      # đích (một lệnh = một tài khoản)
  seq: int                        # tăng đơn điệu theo từng account_id (phát hiện lỗ hổng/đảo thứ tự)
  issued_at, expires_at: UTC      # TTL ngắn (mặc định 15 giây cho market, tối đa 5 phút cho pending)
  nonce: 128-bit                  # chống replay, EA nhớ cửa sổ gần nhất
  action: open|modify|close|cancel|halt|reduce_only
  params: {symbol (chuẩn hoá), side, volume_lots, order_type, price?, sl, tp, max_slippage_points, position_ref?}
  policy_snapshot_hash            # băm bộ giới hạn đã áp lúc risk engine duyệt (EA đối chiếu phiên bản chính sách)
  risk_attest {engine_ver, decision_id, checks[]}   # bằng chứng đã qua risk engine
  approval {mode: none|client_per_trade, approval_id?}   # L2: cần chữ ký/xác nhận của client
}
sig = Ed25519(sk_signer_for_account, canonical_json(Command))   # JCS/RFC 8785
```
- Khoá: Ed25519 theo từng tài khoản (khoá công khai nằm ở EA và `mt_accounts.cmd_pubkey`; khoá riêng ở `command-signer`, tốt nhất HSM/ file 0400 + sops, không nằm trong `.env` chung — ARCH_AUDIT X-1). Xoay khoá có `key_id`. HMAC hiện tại (X-MT-Sig) giữ cho kênh ingest; KHÔNG dùng lại cho lệnh vì HMAC secret bridge đọc được (bridge bị chiếm thì giả được lệnh); chữ ký bất đối xứng khiến bridge không thể giả lệnh.
- Hạn chế MQL: Ed25519 chưa có sẵn trong MQL; phải tự cài thuần MQL hoặc dùng DLL (không khuyến khích) — CHƯA XÁC MINH khả thi/hiệu năng; phương án dự phòng: ECDSA/HMAC bằng khoá riêng của từng EA được "bọc" thêm — cần spike 1 tuần. Quyết định thiết kế chặn: lệnh KHÔNG được chấp nhận nếu EA không kiểm được chữ ký bất đối xứng.
- Kết quả EA -> bridge (`POST /cmd/v1/result`) ký HMAC như ingest hiện tại + chứa `cmd_id`, `status`, `ticket`, `fill_price`, `fill_volume`, `broker_retcode`, `ea_ts`.

### 2.5 Vòng đời lệnh (state machine)
```
 PROPOSED -> RISK_REJECTED (cuối)
   |
   v
 RISK_APPROVED -> AWAITING_CLIENT_APPROVAL (L2) -> CLIENT_REJECTED | EXPIRED (cuối)
   |                          |
   +-------- (L3/L4: bỏ qua)-+
   v
 SIGNED -> QUEUED (command_outbox) -> DELIVERED (EA đã kéo) -> ACKED (EA nhận, qua kiểm EA)
                                                         |-> NACKED (EA từ chối: lý do mã hoá) (cuối)
 ACKED -> SENT_TO_BROKER -> FILLED | PARTIAL | REJECTED_BY_BROKER | UNKNOWN
 UNKNOWN (mất kết nối/timeout sau khi gửi) -> RECONCILING -> FILLED | NOT_FOUND(an toàn gửi lại hoặc huỷ) | MANUAL_REVIEW
 CANCEL_REQUESTED -> CANCELLED | TOO_LATE
```
- Chuyển trạng thái hợp lệ cố định, bảng `command_events` append-only (xem 4.5); không UPDATE trạng thái tại chỗ.
- Write-ahead: `client_order_id` + bản ghi `QUEUED` được commit TRƯỚC khi lệnh có thể được EA kéo.
- Không bao giờ tự động gửi lại lệnh `open` ở trạng thái UNKNOWN; chỉ sau khi đối soát (tra vị thế/lệnh theo magic + comment + client_order_id) xác nhận NOT_FOUND và lệnh chưa hết hạn, và phải qua lại risk engine (lệnh mới = cmd_id mới).

### 2.6 Idempotency, replay, mất kết nối
| Tình huống | Xử lý |
|---|---|
| Lệnh gửi 2 lần (retry/kéo lại) | EA giữ bảng `executed[cmd_id, client_order_id]` bền (file trong MQL*/Files) + kiểm tra lệnh/deal hiện có theo magic/comment trước khi gửi; trùng -> ack "duplicate", không thực thi lần hai |
| Replay lệnh cũ | `expires_at`, `nonce` cửa sổ, `seq` đơn điệu (seq nhỏ hơn đã thấy -> nack `stale_seq`), chữ ký gắn account_id |
| EA mất mạng khi đang cầm lệnh | Lệnh `open`/`modify` hết hạn -> EA bỏ; lệnh đã gửi broker nhưng chưa báo kết quả -> UNKNOWN -> reconciler |
| Mất kết nối kéo dài | EA có "lease" (giấy phép sống): không có poll thành công trong N giây thì EA TỰ chuyển `reduce_only` (chỉ cho đóng/giảm), không mở mới; cấu hình bởi client (mặc định N=60) |
| Đồng hồ lệch | EA từ chối lệnh nếu lệch UTC > 5 giây so với phản hồi bridge (đã có đo `skew_s`); tự về `reduce_only` |
| Bridge trả lệnh cũ sau restart | `seq` + `expires_at` + kiểm `policy_snapshot_hash` ở EA |
| Terminal restart giữa chừng | EA nạp `executed` từ file, đối soát vị thế đang mở với lệnh gần nhất trước khi nhận lệnh mới |

### 2.7 Đa tài khoản, MT4 hedging / MT5 netting
- Mỗi lệnh = 1 tài khoản đích; không có "lệnh chung" đa tài khoản ở tầng EA. L4 phân phối bằng cách sinh N lệnh độc lập, mỗi lệnh qua risk engine RIÊNG của tài khoản đó.
- Chuẩn hoá "position" theo `net_exposure()` hiện có (mt-bridge). Risk engine tính exposure theo từng chế độ:
  - MT4 / MT5 hedging: nhiều vị thế cùng symbol; `open` mới LUÔN tạo ticket mới; `close` phải chỉ rõ `position_ref` (ticket) — không dùng "đóng theo symbol".
  - MT5 netting: một vị thế/symbol; `open` có thể tăng/giảm/đảo chiều vị thế sẵn có -> risk engine mô phỏng vị thế SAU lệnh (post-trade), cấm lệnh làm đảo chiều ngoài ý muốn (cần cờ `allow_flip` tường minh); `close` = lệnh đối ứng khối lượng bằng vị thế.
  - Nhận dạng chế độ từ EA (`ACCOUNT_MARGIN_MODE`), lưu trong `mt_accounts` (cột mới `margin_mode`) và kiểm lại mỗi snapshot; đổi chế độ -> halt tài khoản chờ rà.
- Mapping symbol/hậu tố/contract size theo tài khoản (đã có trong accounts config) bắt buộc dùng; symbol không có mapping -> từ chối.
- Mỗi terminal 1 tài khoản (không đổi): N tài khoản = N EA, khoá ký riêng.

## 3. Kiểm soát an toàn nhiều lớp

### 3.1 Risk engine tất định (chạy TRƯỚC khi lệnh tới EA)
Dịch vụ riêng, thuần hàm của (lệnh, trạng thái tài khoản mới nhất, chính sách đã duyệt), KHÔNG có LLM/ngẫu nhiên, mọi quyết định ghi lại cùng `decision_id` và đầu vào (tái lập được).
| Kiểm tra | Chi tiết |
|---|---|
| Lô | max lot/lệnh, max tổng lot, theo symbol và theo tài khoản |
| Đòn bẩy / margin | margin level sau lệnh >= ngưỡng, tổng exposure danh nghĩa / equity <= trần |
| Rủi ro/lệnh | (khoảng cách SL x lot x giá trị điểm) / equity <= r%; lệnh KHÔNG có SL bị từ chối |
| Lỗ ngày/tuần | tính từ equity do EA/broker báo (KHÔNG từ DB nội bộ — ARCH_AUDIT X-2); chạm ngưỡng -> chỉ `reduce_only` đến hết kỳ |
| Whitelist symbol | danh sách riêng từng tài khoản/chiến lược |
| Cửa sổ tin | dùng `tscommon.risk_windows` hiện có: cấm mở mới T-15..T+30 (T+45 FOMC/vàng); cho phép đóng/giảm |
| Spread tối đa | so với spread hiện tại EA báo (và trung vị lịch sử) |
| Tần suất | tối đa N lệnh/phút/tài khoản, M lệnh/giờ; chống bão lệnh |
| Giờ giao dịch | phiên thị trường mở, không quanh rollover |
| Phiên bản chính sách | lệnh mang `policy_snapshot_hash`; chính sách đổi -> lệnh cũ trong hàng đợi vô hiệu |
| Kích thước chốt chặn dữ liệu | dữ liệu tài khoản quá cũ (> vài giây) -> từ chối (fail-closed) |
Risk engine fail-closed: không trả lời kịp -> từ chối. Lease "dead-man" (Redis `SET key EX 15` do risk engine gia hạn): hết lease thì `command-signer` KHÔNG ký thêm lệnh (ARCH_AUDIT X-2).

### 3.2 Giới hạn tầng EA (tự chặn kể cả khi master bị chiếm)
Cấu hình do CLIENT đặt trong input EA (hoặc file bền cục bộ, KHÔNG nhận từ mạng): `MaxLotPerOrder, MaxTotalLots, MaxOpenPositions, MaxDailyLossPct/Amount (so với equity đầu ngày theo terminal), AllowedSymbols, MaxSpreadPoints, MaxSlippagePoints, MaxOrdersPerMinute, AllowedHours, RequireSL, ReduceOnlyOnDisconnect, MasterPubKey (ghim khoá), AllowOpen (bật/tắt từng loại hành động)`.
- Chính sách đến từ mạng chỉ có thể THU HẸP giới hạn (siêu tập hợp chặt hơn); mở rộng chỉ làm được ở input cục bộ do client tự sửa. EA lấy MIN(client_local, policy_from_master).
- EA kiểm độc lập: chữ ký, hạn, nonce, seq, symbol, lô, số lệnh, lỗ ngày, spread; nack kèm mã lý do.
- Nút "AllowTrading" của chính terminal (AutoTrading) do client điều khiển — tôn trọng; EA không cố vượt.
- Kill-switch cục bộ EA: input `Paused`, nút trên chart, file cờ `MTAgent_KILL` (EA kiểm mỗi tick), và lệnh `halt` từ master chỉ được phép làm GIẢM năng lực (không có lệnh "unhalt" từ xa — chỉ client bật lại).

### 3.3 Kill-switch 4 tầng
| Tầng | Phạm vi | Cơ chế | Ai kích hoạt | Ai gỡ |
|---|---|---|---|---|
| T1 Master toàn cục | mọi tài khoản | cờ trong command-signer (ngừng ký) + Redis lease risk engine + file cờ trên host + Telegram có MFA | master (1 người đủ để DỪNG) | 4-eyes + cooldown |
| T2 Theo client | 1 tài khoản | `mt_accounts.cmd_state=halted` + lệnh `halt` ký tới EA | master hoặc CLIENT | chỉ client (hoặc master + client đồng ý) |
| T3 Theo chiến lược | 1 chiến lược/mọi tài khoản dùng nó | `strategies.state=halted` | master/analyst-lead | 4-eyes |
| T4 Tại EA | 1 terminal | `Paused`, file cờ, AutoTrading tắt, lease hết hạn | CLIENT, hoặc tự động khi mất kết nối | chỉ client tại máy |
- Tính chất: DỪNG luôn dễ hơn BẬT (bất đối xứng): một người, một thao tác, không cần duyệt; bật lại cần quy trình.
- Kill-switch là tiến trình độc lập với chiến lược/risk engine, đọc trạng thái độc lập (equity từ EA), huỷ lệnh chờ + (tuỳ chính sách) đóng vị thế qua kênh `reduce_only`. Mục tiêu hiệu lực < 2 giây ở T1-T3 (đo hằng tuần trên demo); T4 tức thì.
- Đường dừng khi hệ thống hỏng: T4 hoạt động cả khi bridge/master chết (dead-man lease).

### 3.4 4-eyes (hai người)
- Cần 2 danh tính khác nhau (`proposed_by != approved_by`, MFA WebAuthn/TOTP) cho: kích hoạt chiến lược, thay đổi tham số rủi ro theo hướng NỚI, thêm tài khoản vào chiến lược/nhóm copy, nâng bậc L, xoay khoá ký lệnh, gỡ kill-switch T1/T3.
- Thay đổi theo hướng THU HẸP (giảm rủi ro) hiệu lực ngay, 1 người.
- Hiệu lực sau cooldown (mặc định 24 giờ) trừ thay đổi giảm rủi ro (ARCH_AUDIT X-4). Hiện chỉ có 1 master -> cần thêm ít nhất 1 người duyệt độc lập TRƯỚC L2; nếu dự án chỉ có 1 người vận hành thì 4-eyes = người + CI/kiểm thử tự động + cooldown (ghi rõ đây là giảm nhẹ, không tương đương).

### 3.5 Paper-shadow bắt buộc trước live
- Mọi chiến lược/phiên bản chạy "shadow": sinh đúng lệnh qua cùng risk engine, ghi `shadow_commands` (KHÔNG ký, KHÔNG vào outbox), mô phỏng fill bằng giá EA báo + chi phí. Có thể chạy song song khi đã live (so sánh live vs shadow để phát hiện trượt giá/lệch).
- Cổng chuyển: shadow >= 8 tuần (STRATEGY_OPTIONS nói 8-12), Sharpe/DD trong dải backtest đã khai báo, deflated Sharpe/khoảng tin cậy được ghi, 0 lần vi phạm risk engine bất thường; mỗi lần đổi mã/tham số chiến lược reset đồng hồ shadow.
- Cấu trúc mã bảo đảm: một cờ `mode in {shadow, live}` nằm trong chính sách đã ký; `shadow` thì không có đường tới `command_outbox` (ràng buộc DB + test).

### 3.6 Ngưỡng chuyển bậc và hạ bậc tự động
| Sự kiện | Hành động tự động |
|---|---|
| Drift đối soát > ngưỡng (vị thế EA != kỳ vọng) | halt tài khoản (T2), cảnh báo master+client |
| Lỗ ngày chạm trần | `reduce_only` đến hết ngày, hạ L3->L2 |
| >= 3 nack/timeout bất thường liên tiếp | hạ về L2 (cần duyệt tay) cho tài khoản đó |
| Heartbeat EA mất > N giây | EA tự `reduce_only`; hệ thống ngừng ký lệnh mới |
| Phát hiện chữ ký/seq lạ ở EA | EA tự halt + báo (có thể là bị chiếm) |
| Khoá hết hạn/xoay chưa xong | không ký |
Nâng bậc luôn thủ công (4.4).

### 3.7 Nhật ký bất biến (hash-chain)
- `command_log` (append-only) mở rộng mẫu `audit_log` hash-chain của dịch vụ auth hiện có: mỗi dòng `{id, ts, actor (người/dịch vụ), kind (proposal|risk_decision|approval|sign|deliver|ack|fill|reconcile|policy_change|kill|optin), cmd_id, account_id, payload_hash, prev_hash, row_hash}`; role ghi chỉ INSERT, REVOKE UPDATE/DELETE/TRUNCATE; xác minh định kỳ (`verify`) + neo băm đầu chuỗi mỗi giờ ra nơi ngoài host (WORM/R2 Object Lock hoặc OpenTimestamps; nơi lưu chưa chọn).
- Ghi nhật ký TRƯỚC khi hành động có hiệu lực (write-ahead). Nhật ký không chứa bí mật.
- EA cũng giữ nhật ký cục bộ (file) mọi lệnh nhận/thực thi/nack để client tự kiểm chứng và đối chiếu.

### 3.8 Đối soát (reconciliation) và phát hiện lệch
- Nguồn chân lý = broker, qua snapshot/vị thế/deals EA đẩy (đã có `account.snapshots`, `account.deals`; thêm `orders` đã có).
- Reconciler chạy mỗi N giây: so (a) lệnh `FILLED/SENT` kỳ vọng vs vị thế/deals thực, (b) vị thế THỰC không có lệnh gốc (lệnh tay của client là hợp lệ -> gắn nhãn `manual`, không tính drift nhưng tính vào risk exposure), (c) lệnh mồ côi do hệ thống (magic của hệ thống mà không có cmd_id).
- Drift > ngưỡng hoặc 2 chu kỳ liên tiếp -> halt tài khoản + cảnh báo + `MANUAL_REVIEW`.
- Kiểm tra số dư/equity hợp lý (P&L tính lại từ deals vs equity báo).

## 4. Mô hình quyền và đồng ý

### 4.1 Nguyên tắc đồng ý (consent)
- Opt-in bắt buộc, chủ động, nhiều bước: (1) client đọc và chấp nhận điều khoản + cảnh báo rủi ro (có phiên bản, lưu `consent_records` kèm băm văn bản, thời điểm, IP/UA); (2) client TỰ cài `MTAgentExec` và TỰ bật cho phép (input `EnableExecution=true` + AutoTrading của terminal); (3) EA báo trạng thái `exec_enabled` ngược về hệ thống; hệ thống KHÔNG ký lệnh cho tài khoản chưa có consent hiệu lực + `exec_enabled` hiện tại.
- Rút bất cứ lúc nào: client tắt EA/`Paused`/AutoTrading/gỡ EA -> hiệu lực tức thì tại EA; cổng web có nút "Ngừng nhận lệnh" -> T2 halt. Rút KHÔNG cần master đồng ý. Lệnh đang chờ bị huỷ, vị thế mở giữ nguyên trừ khi client chọn đóng.
- Hiển thị rõ: chip trạng thái "ĐANG CHO PHÉP NHẬN LỆNH TỪ MASTER" ở client-ui và trong `Comment()` chart của EA; mỗi lệnh nhận/thực thi gửi thông báo cho client (push/Web Push đã có).
- Giới hạn do CLIENT đặt có hiệu lực cao nhất (quy tắc ưu tiên): `hiệu lực = MIN(client_limits, master_policy, strategy_limits, risk_engine_defaults)` cho mọi giới hạn "trần"; client có quyền chặn (veto) mọi lệnh, mọi symbol, mọi chiến lược; master không có đường nới giới hạn của client.
- Không lưu mật khẩu giao dịch/investor trên server (giữ nguyên; kiểm bằng review + test chống trường `password` trong schema lệnh). Thực thi LUÔN diễn ra trong terminal của client, dùng phiên đăng nhập sẵn có của client. Không dùng MetaApi/ dịch vụ lưu credential (cũng vì 0 đồng + nguyên tắc này).

### 4.2 Vai trò
| Vai trò | Xem | Đề xuất | Duyệt (risk/policy) | Duyệt lệnh trên tài khoản | Kill |
|---|---|---|---|---|---|
| client | tài khoản mình | không (hoặc "yêu cầu" cho chính mình) | giới hạn của mình | CÓ (L2: duyệt từng lệnh của mình) | T2/T4 của mình |
| support | cấu hình/trạng thái (không số dư chi tiết trừ khi client đồng ý) | không | không | không | chỉ DỪNG tài khoản theo yêu cầu client |
| analyst | dữ liệu thị trường, shadow | CÓ (đề xuất chiến lược/lệnh) | không | không | không |
| master (operator) | tất cả | gián tiếp | CÓ (thu hẹp 1 người; nới = 4-eyes) | KHÔNG thay mặt client duyệt lệnh | T1, T2, T3 (dừng) |
| master-approver (người thứ 2) | tất cả | không | CÓ (người duyệt thứ hai cho 4-eyes) | không | gỡ T1/T3 |
| service | theo tối thiểu | strategy -> proposals | không | không | không |
- Tách quyền: người ĐỀ XUẤT không được DUYỆT chính đề xuất của mình; người DUYỆT chính sách không được là người ký/triển khai khoá. Quyền `execute` tách khỏi `view`: bảng quyền (cột mới `permissions` ở `mt_accounts`/`user_accounts`) lưu từng quyền độc lập: `view`, `propose`, `approve_policy`, `approve_trade`, `kill_stop`, `kill_release`.
- Mọi thao tác quyền ghi `command_log`.

### 4.3 Duyệt từng lệnh trên EA (L2)
- Lệnh `AWAITING_CLIENT_APPROVAL` hiển thị cho client trên client-ui (push) VÀ/HOẶC trên EA (hộp thoại/Alert + bấm xác nhận). Xác nhận phải đến từ KÊNH ĐỘC LẬP với master: chữ ký của client (khoá của thiết bị/Passkey WebAuthn của client gắn với `portal_users`) hoặc xác nhận cục bộ tại terminal. Phương án tại EA (bấm tại terminal) an toàn hơn cho giai đoạn đầu: tránh phụ thuộc web.
- Nội dung duyệt hiển thị đầy đủ: symbol, hướng, lô, SL/TP, rủi ro % equity, lý do (do hệ thống tất định sinh — không do LLM), hết hạn sau X giây.

### 4.4 Quy trình nâng bậc
Đề xuất -> checklist tự động (shadow, drift, kiểm thử) -> 4-eyes -> consent client cho bậc mới -> cooldown -> bật vốn nhỏ -> theo dõi 2 tuần. Hạ bậc: tự động hoặc 1 người.

## 5. Mô hình đe doạ (STRIDE)
| Mối đe doạ | Loại | Kịch bản | Biện pháp |
|---|---|---|---|
| Master/portal bị chiếm (phiên, XSS, lộ mật khẩu) | S/E/T | Kẻ tấn công đặt lệnh hoặc nới giới hạn | MFA bắt buộc cho master; master KHÔNG có khoá ký (chỉ đề xuất); mọi lệnh qua risk engine + chữ ký signer riêng; giới hạn tầng EA do client giữ nên chiếm master không nới được; 4-eyes cho nới; hạn mức rủi ro tuyệt đối trong EA; alert real-time cho mọi thay đổi chính sách |
| Bridge bị chiếm | T/E/I | Chèn/sửa/replay lệnh; đọc HMAC secret mọi tài khoản (rủi ro đã ghi ở AUTH 6) | Bridge không có khoá ký lệnh; chữ ký Ed25519 + `account_id` + `seq` + hạn + nonce kiểm ở EA; sửa body -> chữ ký sai; bridge chỉ có thể DROP/delay (an toàn: EA hết lease -> reduce_only); tách service `cmd-bridge` khỏi bridge ingest đọc-ghi để thu hẹp bề mặt; không dùng cùng secret cho ingest và lệnh |
| EA giả mạo (kẻ khác nhận lệnh/đẩy dữ liệu giả) | S/T | Dùng token bị lộ để kéo lệnh; đẩy snapshot giả để qua risk engine | Kéo lệnh cần token + HMAC + khoá EA gắn account; lệnh nội dung không bí mật cao nhưng ghi `cmd_id` không lộ sau hạn; trạng thái tài khoản xác thực chéo (so với deals/equity hợp lý, phát hiện bất thường) — CHƯA XÁC MINH mức bảo đảm vì EA là bên không tin cậy về dữ liệu; risk engine dùng thêm chỉ số độc lập (giá thị trường từ nguồn riêng); lộ token -> xoay (đã có) |
| Replay / trùng lệnh | R/T | Phát lại lệnh cũ | seq đơn điệu, nonce, hạn ngắn, executed-table bền ở EA, client_order_id (2.6) |
| Thao túng tin/tín hiệu (poisoning) | T | Tin giả/RSS độc để chiến lược ra lệnh sai | Tin chỉ là bộ lọc rủi ro/ngữ cảnh; chiến lược dùng dữ liệu đã làm sạch; giới hạn tầng risk/EA chặn mọi thiệt hại tối đa; paper-shadow phát hiện hành vi lạ |
| Prompt injection (nếu có LLM) | T/E | Văn bản tin chèn lệnh | LLM KHÔNG ra lệnh, KHÔNG duyệt, KHÔNG sửa chính sách, KHÔNG có credential/quyền ghi vào bus lệnh (kiến trúc: LLM ở vùng B chỉ đọc, đầu ra là văn bản hiển thị); đầu ra qua schema nghiêm nếu dùng làm gợi ý; test tĩnh cấm import SDK LLM ở vùng C; nội dung không tin cậy tách khỏi ngữ cảnh chỉ thị (ARCH_AUDIT S-8) |
| Insider (người vận hành) | E/R | Master đặt lệnh trên tài khoản client, xoá dấu vết | 4-eyes, hash-chain + neo ngoài host, role DB không UPDATE/DELETE, thông báo cho client mọi lệnh trên tài khoản, client veto, tách quyền đề xuất/duyệt/khoá |
| Từ chối dịch vụ (DoS) | D | Làm sập bridge để vô hiệu hoá dừng lỗ | Dừng lỗ nằm ở broker/EA (SL gắn khi mở), reduce_only khi mất lease, giới hạn tốc độ (đã có) |
| Lộ thông tin | I | Lộ vị thế/khoá | scope theo tài khoản (đã có), khoá ký tách vùng, log không chứa bí mật |
| Chuỗi cung ứng EA | T | EA bị sửa trên đường phân phối | Ký/băm file EA, phát hành có checksum, client tự biên dịch từ mã nguồn mở của dự án (chưa có ký image/cosign — HARDENING 5) |
| Redis bus: ai cũng XADD (đã ghi ở HARDENING 5) | T | Service bị chiếm giả sự kiện | Vùng C dùng Redis/DB riêng + ACL theo stream; vùng A/B không có quyền ghi vào vùng C |
Rủi ro còn lại: mã MQL chưa chạy trên broker thật; tính an toàn của việc cài chữ ký Ed25519 trong MQL chưa kiểm chứng.

## 6. Pháp lý / tuân thủ (CẦN LUẬT SƯ cho mọi mục)
| Cổng | Nội dung (kế thừa PLAN.md mục 0) | Tác động tới control plane |
|---|---|---|
| G1 | Forex bán lẻ tại VN: NHNN chưa cấp phép sàn forex; Nghị định 340/2025 (hiệu lực 9/2/2026) phạt đến 250 triệu cho phái sinh ngoại hối không phép; chế tài với cá nhân chưa rõ (chưa xác minh nguyên văn) | Chặn L2+ cho client cư trú tại VN trên tài khoản forex/CFD; có thể giới hạn theo quốc gia client; hỏi luật sư trước khi mời khách hàng nào |
| G2 | Chứng khoán VN: UBCKNN 2023 yêu cầu dừng đặt lệnh bằng robot; SSI/DNSE vẫn bán API (chưa xác minh hiện hành) | Không đặt lệnh chứng khoán qua control plane cho tới khi có văn bản của công ty chứng khoán/UBCKNN |
| G3 | Broker/ToS: API/EA/VPS; nhiều broker và prop firm cấm hoặc hạn chế copy trade, EA ngoài, khai thác độ trễ | Danh sách broker "đã duyệt" theo từng tài khoản; client cam kết ToS của broker mình; hệ thống không hỗ trợ prop firm cấm copy/EA |
| G4 (mới) | Dịch vụ tín hiệu/copy/quản lý tài khoản hộ/tư vấn đầu tư: ở nhiều nước cần giấy phép (tư vấn, quản lý danh mục); tại VN chưa xác minh | L4 và cả L2-L3 khi master giao dịch cho NGƯỜI KHÁC: cần ý kiến luật sư trước; nếu chỉ phục vụ tài khoản của chính chủ và chính chủ tự quyết thì rủi ro khác nhau — vẫn cần xác nhận |
| G5 (mới) | Dữ liệu cá nhân: nhật ký, hồ sơ rủi ro, consent của khách (Nghị định về bảo vệ dữ liệu cá nhân của VN — chưa xác minh chi tiết); thuế, lưu chứng từ | Thời hạn lưu `command_log`/`consent_records`, quyền xoá, chuyển dữ liệu qua biên giới (VPS ở nước ngoài) |
| G6 (mới) | Điều khoản dịch vụ, cảnh báo rủi ro, miễn trừ; phân định trách nhiệm khi lệnh lỗi | Văn bản consent có phiên bản; không hứa lợi nhuận; không bao giờ quảng bá hiệu suất |
Checklist go-live (kế thừa PLAN.md mục 6 + bổ sung): pháp lý bằng văn bản (G1-G6); backtest có chi phí + walk-forward; paper-shadow >= 8 tuần (không phải 4); kill-switch 4 tầng thử thật, đo thời gian; giới hạn lỗ/vị thế/lệnh ở risk engine VÀ EA; idempotency + đối soát chạy 30 ngày sạch; khoá ký ở vùng riêng + xoay thử; không có mật khẩu giao dịch trên server (rà soát); heartbeat + Telegram; sao lưu `command_log` ngoài host + runbook; dừng từ điện thoại; vốn nhỏ; LLM không có quyền thực thi (test tĩnh); red-team: master/bridge giả lập bị chiếm không vượt được giới hạn EA; client consent + veto hoạt động; 4-eyes có người thứ hai thật; DR: restore thử (ARCH_AUDIT R-2).

## 7. ADR ngắn
- ADR-C1 EA kéo (pull), không đẩy: giữ nguyên "không mở cổng vào". Hệ quả: độ trễ cấp giây; long-poll HTTPS. Thay thế bị loại: Socket/ZeroMQ server trong EA (mở cổng; dwxconnect ZeroMQ đã bị loại ở PLAN).
- ADR-C2 Chữ ký bất đối xứng cho lệnh, HMAC cho ingest: bridge không thể giả lệnh. Rủi ro: cần cài trong MQL (chưa xác minh).
- ADR-C3 Giới hạn EA do client giữ, mạng chỉ thu hẹp: chiếm master không nới được. Đánh đổi: master không thể tự chỉnh trần cho client; chấp nhận.
- ADR-C4 Hai EA tách (đọc / thực thi): bề mặt tấn công và tuân thủ tách biệt; client không opt-in thì không có mã thực thi.
- ADR-C5 Risk engine tất định, không LLM, fail-closed, quyết định tái lập được.
- ADR-C6 Dừng dễ hơn bật: bất đối xứng quyền.
- ADR-C7 Vùng C tách mạng/Redis/DB: tránh dùng chung VPS/Redis phẳng hiện tại (ARCH_AUDIT X-1, S-1).
- ADR-C8 Tái dùng khái niệm OMS có sẵn thay vì tự phát minh state machine (xem 8.2), nhưng KHÔNG nhúng cả framework vào đường lệnh MT cho đến khi spike chứng minh phù hợp.

## 8. Lộ trình, ước lượng, OSS

### 8.1 Pha (ước lượng thô, 1 kỹ sư; chưa tính chờ pháp lý)
| Pha | Nội dung | Ước lượng | Cổng vào |
|---|---|---|---|
| CP-0 | Chuẩn bị nhỏ trong kiến trúc hiện tại (mục 9) + đặc tả giao thức lệnh + threat model chi tiết + spike chữ ký Ed25519/ECDSA trong MQL, long-poll WebRequest, hai EA | 2-3 tuần | không cần pháp lý (không có mã đặt lệnh) |
| CP-1 | L1: cảnh báo/khuyến nghị (cửa sổ tin, chế độ biến động) trên client-ui, có disclaimer | 1-2 tuần | luật sư xem nội dung |
| CP-2 | Vùng C: command-signer, command_outbox, risk engine, command_log hash-chain, kill-switch T1-T3, reconciler — CHỈ chạy với EA giả/simulator + paper-shadow | 6-8 tuần | thiết kế được duyệt; vẫn không lệnh thật |
| CP-3 | `MTAgentExec` (MQL4+MQL5) + kéo lệnh + giới hạn tầng EA + consent flow + test hợp đồng MT4/MT5 trên DEMO | 5-7 tuần | G3 (broker demo), consent |
| CP-4 | L2 trên demo (duyệt từng lệnh) + red-team + kill-switch thử hằng tuần; paper-shadow >= 8 tuần | 8-10 tuần | — |
| CP-5 | L2 live vốn nhỏ | 4+ tuần quan sát | G1-G3(+G4,G5,G6) bằng văn bản |
| CP-6 | L3 hộp cát | 6-8 tuần | tiêu chí 1.3 |
| CP-7 | L4 phân phối | 8-12 tuần | luật sư G4 |
Tổng đến L2 trên demo: khoảng 5-6 tháng (ước lượng thô, chưa xác minh).

### 8.2 OSS tham khảo (kiểm chứng ngày 2026-10-12 qua GitHub API)
| Ứng viên | License | Trạng thái | Dùng để làm gì |
|---|---|---|---|
| NautilusTrader (nautechsystems) | LGPL-3.0 | ~29,9k sao, push 2026-10-12, không archived | Học mô hình OMS/lệnh: vòng đời lệnh (initialized/submitted/accepted/filled/...), risk engine tách, cache/đối soát khi khởi động. Liên kết động qua LGPL được; KHÔNG sao chép; chưa xác minh có adapter MT4/MT5 (không nên giả định) |
| QuantConnect LEAN | Apache-2.0 | ~22k sao, push 2026-10-09, không archived | Học mô hình lệnh/brokerage model/transaction handler, mô hình chi phí/slippage; không có MT4/MT5 gốc (chưa xác minh) |
| darwinex/dwxconnect | BSD-3-Clause (theo mt-agent/README) | PLAN ghi "MT4; MT5 chưa xác minh"; DWX ZeroMQ đã archived | Học tách EA/connector và bảng lệnh; dự án này đã đảo thành outbound |
| Trade copier mã nguồn mở (MT4/MT5) | — | Tìm kiếm web 2026-10-12 chỉ thấy sản phẩm thương mại/job trên MQL5; KHÔNG xác minh được bản OSS còn sống | Học kiến trúc qua mô tả (master/slave, symbol mapping, hệ số lô, đồng bộ SL/TP/đóng, ngưỡng drawdown); cần tìm tiếp trên GitHub bằng "mql copier ZeroMQ/named pipe" rồi kiểm license/ngày commit. GHI: chưa xác minh |
| Freqtrade (nếu crypto) | GPL-3.0 (chưa xác minh) | — | Tham khảo kill-switch/protections; chỉ nếu mở sang crypto |
| immudb / OpenTimestamps / pgAudit | Apache-2.0 / LGPL / PostgreSQL (chưa xác minh) | — | Nhật ký bất biến/neo thời gian (tuỳ chọn) |
| Authentik/Authelia (WebAuthn), Vault/sops | — | — | MFA + quản lý khoá (kiểm license từng cái khi chọn) |
Nguyên tắc (OSS-first, 0 đồng): không tự sáng chế OMS từ đầu — viết bảng chuyển trạng thái dựa theo mô hình của Nautilus/LEAN; riêng "EA thực thi + chữ ký + giới hạn tầng EA" phải tự viết nhỏ vì đặc thù MT, mô-đun chữ ký dùng thuật toán chuẩn (không tự chế mật mã).

## 9. Thay đổi NHỎ nên làm ngay (liệt kê, KHÔNG cài đặt trong tài liệu này)
Mục tiêu: chuẩn bị chỗ cho control plane mà không thêm khả năng đặt lệnh. Tất cả đều "inert" (không có hiệu lực thực thi).
1. `mt_accounts` thêm cột (migration mới, vd `014_control_ready.sql`): `permissions jsonb default '{}'` (view/propose/approve_trade...), `exec_optin boolean default false`, `exec_optin_at`, `exec_optin_consent_version`, `cmd_pubkey text null` (Ed25519 công khai), `cmd_key_id`, `margin_mode text null` (hedging|netting), `cmd_state text default 'disabled'` (disabled|halted|shadow|live), `autonomy_level smallint default 0` (0..4). Mặc định mọi thứ TẮT; có ràng buộc CHECK `autonomy_level <= 0` cho tới khi được gỡ bằng migration có chủ đích.
2. Bảng chỗ giữ: `consent_records(user_id, account_id, doc_version, doc_hash, accepted_at, revoked_at, ip, ua)`; `policy_versions(...)` chưa có hiệu lực.
3. Event type dự phòng trong `docs/CONTRACTS.md` (chỉ đặc tả, chưa phát): `cmd.proposals`, `cmd.decisions`, `cmd.outbox`, `cmd.results`, `ctl.kill`; namespace tách để tránh lẫn `account.*`.
4. Trường `exec_enabled`, `margin_mode`, `trade_allowed` đã có trong snapshot/ EA -> đảm bảo EA ĐỌC báo `margin_mode` và `exec_enabled=false` (EA đọc hiện tại luôn false). Thêm vào schema `extra=forbid` của ingest như trường tuỳ chọn.
5. Mở rộng audit action: đăng ký các tên hành động trong `audit_log` (consent.accept/revoke, policy.change, kill.*, level.change) và hash-chain đã có sẵn tái dùng cho `command_log`.
6. Test tĩnh: giữ `test_no_trading_code_anywhere`; thêm danh sách trắng đường dẫn duy nhất được phép chứa ký hiệu giao dịch (thư mục `services/exec/` và `mt-agent/MQL*/Experts/MTAgentExec*`, hiện chưa tồn tại); thêm test cấm import SDK LLM trong vùng C; test cấm trường `password|investor` trong mọi schema.
7. Tạo sẵn cơ chế khoá: script sinh cặp khoá Ed25519 (không dùng hiện tại) và tài liệu nơi giữ khoá riêng ở vùng C; tách `AUTH_SECRET_KEY` khỏi khoá ký tương lai.
8. Mở rộng `docs/CLIENT_PLATFORM.md`: mục "Control plane (tương lai)" trỏ tới tài liệu này (đã làm).
9. Quản trị: thêm vai trò `analyst`, `support` vào `portal_users.role` (hiện master|client) — chỉ định nghĩa, quyền mặc định 0; MFA TOTP bắt buộc cho master (đã có tuỳ chọn -> chuyển thành bắt buộc trước L1).
10. Hạ tầng: dựng Redis/Postgres riêng + mạng riêng cho vùng C trước khi viết dịch vụ (ARCH_AUDIT X-1); ký/ghim image (cosign) và lockfile cho auth; off-site backup (R-2).
11. Chính sách nội dung: không có thuật ngữ "tín hiệu mua/bán" cá nhân hoá trên client-ui cho tới khi luật sư xem (L1).

## 10. Chưa xác minh / rủi ro mở
- Khả thi Ed25519 (hoặc chữ ký bất đối xứng khác) thuần MQL, và hiệu năng trên terminal thật: cần spike.
- WebRequest long-poll chặn EA; mô hình 2 EA/2 chart; hành vi khi AutoTrading tắt: cần thử trên terminal kết nối broker thật (hiện mọi thứ mới chạy offline/lab Wine).
- Chữ ký của client trên duyệt lệnh L2 (WebAuthn vs xác nhận tại terminal): chọn sau spike UX.
- Mức đủ của đối soát khi EA là nguồn dữ liệu duy nhất (EA bị chiếm có thể nói dối): giảm nhẹ bằng giới hạn tại broker (SL trên lệnh), cảnh báo bất thường; tin cậy hoàn toàn vào terminal client là giả định.
- Toàn bộ nội dung pháp lý chưa được luật sư xác nhận.
- Số liệu OSS lấy ngày 2026-10-12; kiểm lại trước khi dùng.
