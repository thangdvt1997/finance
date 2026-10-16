# mt-bridge (READ-ONLY)

Theo doi tai khoan MT4/MT5: so du, equity, margin, vi the, lenh cho, gia, nen. **Khong co code dat/sua/dong lenh o bat ky dau** (co test `test_no_trading_code_anywhere` + `test_gateway_is_read_only`). Phuong thuc ghi se them o phase sau trong gateway/service `execution` rieng.

## Kien truc
```
EA MQL4/MQL5 --HTTPS POST /ingest/v1 (outbound tu VPS)--> AgentGateway --+
terminal MT5 (Windows) <--package MetaTrader5 (investor)-- MT5Gateway ---+--> BridgeService
                                                                           -> account.snapshots, md.quotes, md.bars, alerts.out (Redis Streams)
```
- `BrokerGateway` (ABC): `get_account, get_positions, get_orders, get_rates, get_quotes, health` (+ `get_ticks` tuy chon).
- Mo hinh chuan hoa: `Account, Position, PendingOrder, Quote, Bar`; `net_exposure()` cho hedging (MT4/MT5 hedging) va netting (MT5).
- `accounts.yaml` theo tung tai khoan: hau to/tien to symbol, alias (`GOLD -> XAUUSD`), mui gio server (`server_tz` xu ly DST, hoac `server_utc_offset_hours`, hoac tu suy ra tu `server_time` EA gui), nguong canh bao. Xem `config/accounts.example.yaml`.
- Thoi gian MT la "gio server dong goi nhu epoch"; bridge quy ve UTC.

## Giao thuc ingest v1
`POST /ingest/v1`, header `Authorization: Bearer <token>`, `X-MT-Account: <id>`, body JSON (xem `protocol.py`; schema `extra=forbid`, gioi han kich thuoc/so phan tu, NaN bi tu choi).
Bao ve: token rieng moi tai khoan (so sanh hang so thoi gian; token doc tu bien moi truong, khong nam trong YAML); tuy chon HMAC-SHA256 (`X-MT-Sig = hex(HMAC(secret, "{ts}.{nonce}.{body}"))`, bat bang `hmac_secret_env`); chong replay: `ts` trong +-120s va `nonce` khong lap; loi xac thuc tra chung 401 (khong lo tai khoan co ton tai). Ma loi: 400 sai account/platform, 401, 409 replay, 413, 422 sai schema.
**Phai dat sau reverse proxy TLS** (token di trong header). EA mau chi gui Bearer token (chua ky HMAC).

## Canh bao (`alerts.out`)
Mat heartbeat (`heartbeat_timeout_s`, chi bao sau khi tung ket noi; co alert ket noi lai), drawdown equity so voi dinh trong phien >= `drawdown_pct`, margin level < warn/crit, vi the moi ngoai du kien (magic/ticket khong nam trong `expected_*`; vi the co san luc khoi dong la baseline). Bao theo chuyen trang thai, khong spam; `dedupe_key` on dinh. Neu EA bao tai khoan `trade_allowed=true` -> canh bao khuyen dung investor password.

## Chay
```
pip install -e libs/common -e "services/mt-bridge[test]"          # Windows them: ".[mt5]"
BRIDGE_CONFIG=config/accounts.yaml MT_TOKEN_DEMO_MT4_01=... uvicorn mtbridge.service:create_default_app --factory --port 8000
pytest services/mt-bridge
```
Endpoint: `/healthz`, `/metrics`, `GET /accounts` (BAT BUOC Bearer `BRIDGE_ADMIN_TOKEN`; chua cau hinh -> 503 fail-closed; chi dev local moi dat `BRIDGE_ADMIN_INSECURE_DEV=1`), `POST /ingest/v1`.
Docker (Linux, chi duong EA): `docker build -f services/mt-bridge/Dockerfile -t mt-bridge .` tu goc repo, mount `accounts.yaml` vao `/config`.

## MT5 truc tiep (chi Windows)
Dung **mat khau INVESTOR** (chi doc). Neu tai khoan cho phep giao dich (`trade_allowed`) va `require_investor: true` (mac dinh) -> adapter tu choi ket noi. Package `MetaTrader5` khong thread-safe -> adapter khoa lock. Moi process Python = toi da 1 terminal/tai khoan hieu qua; nhieu tai khoan = nhieu terminal (`terminal_path`) + nhieu process.

## Lich su deal da dong (nhat ky giao dich)
`Batch.deals` (toi da 500, `DealIn`, `extra=forbid`): EA gui lo deal DA DONG theo con tro; bridge chuan hoa (symbol, gio server -> UTC) va phat `account.deals` (1 event/lo). storage-writer upsert bang `account_deals` theo `(account_id, ticket)` (idempotent); chong replay nhu cac truong khac (nonce + ts + HMAC). Bridge KHONG giu trang thai deal va khong the dung de dat lenh. Xem `services/journal` va `docs/CONTRACTS.md`.

## Chua kiem chung
Xem bao cao cuoi cung: toan bo test dung `FakeMT5` va EA gia (HTTP); chua chay voi terminal MT4/MT5 that; ma MQL chua bien dich.

## Cap phat dong, ghep cap, suc khoe EA (2026-10-12)
- `AccountRegistry` (`registry.py`): `StaticRegistry` (accounts.yaml, tuong thich), `HttpRegistry` (goi API noi bo cua service `auth`, KHONG doc DB cheo; cache TTL `BRIDGE_AUTH_TTL_S`=15s, stale-if-error 10 phut roi fail-closed, thu hoi tuc thi qua `POST /internal/invalidate`), `InMemoryRegistry` (test/loadtest), `CompositeRegistry`. Bat bang `BRIDGE_AUTH_URL` + `BRIDGE_AUTH_TOKEN`; de trong = chi YAML. Hop dong: `docs/CLIENT_PLATFORM.md`.
- Token EA chi luu dang bam sha256, so sanh hang so thoi gian. `pending` -> 202 (khong nhan du lieu); `suspended` -> 403 + audit; token sai -> 401 dong nhat; auth chua san sang + tai khoan la -> 503.
- HMAC mac dinh BAT cho tai khoan dong; YAML: `require_hmac: true|false` theo tai khoan, `MT_REQUIRE_HMAC=1` toan cuc.
- `POST /ingest/v1/register`: ghep cap bang PairCode (auth tra credential 1 lan, bridge khong luu/log) hoac bao thong tin bang token.
- Suc khoe: `GET /accounts` co `ea_status/latency_ms/ea_version/build/broker/server/remote_addr/skew_s`; su kien `mt.account_status` (online|degraded|offline) chi khi doi trang thai; `last_seen`+suc khoe day len auth qua `/internal/mt-accounts/seen`.
- Gioi han: `BRIDGE_RATE_PER_S` (5) / `BRIDGE_RATE_BURST` (20) moi tai khoan; xac thuc sai khoa tam theo (IP, tai khoan), tai khoan la dung chung 1 xo theo IP; nonce RAM bi chan boi rate limit + cua so.
- Tai: `loadtest/run_loadtest.sh` (container tam `mtload-*`, khong mang/Redis/DB): 200 tai khoan x 1 req/s ~200 rps p99 ~9ms; 495 rps p99 ~17ms; RSS ~75MB; kich ban loi (sai chu ky/replay/schema/flood/dinh chi) khong anh huong tai khoan tot (0 loi).
