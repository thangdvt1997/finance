# mt-agent: EA doc-chi cho MT4 va MT5

> **2026-10-12 (EA v1.1)**: cap phat dong + ghep cap (`PairCode`, `POST /ingest/v1/register`), thong tin suc khoe EA (`agent`: phien ban/build/broker/RTT), xu ly 202 pending / 403 suspended / 429, HMAC bat mac dinh. Da bien dich MetaEditor MT4 (build 1492) + MT5 (build 6253): **0 loi 0 canh bao**; lab: EA MT5 + script MT4 ky HMAC -> bridge chap nhan, chu ky sai/thieu -> 401 (`lab/scripts/hmac_check.py`). Chua co terminal ket noi may chu broker that.

> **TRANG THAI (2026-10-11): DA BIEN DICH SACH tren MetaEditor MT4 build 1492 va MT5 build 6253 (0 loi, 0 canh bao), DA CHAY tren terminal that trong Wine/Docker (xem `LAB.md`), du lieu di het duong ong toi Postgres. CHUA thu voi tai khoan demo/live co ket noi may chu broker (chi du lieu offline mac dinh cua terminal), chua thu vi the/lenh cho that.** MT4 offline khong khoi dong EA (can dang nhap) - xem `LAB.md`.

EA **chi doc**: khong co ham giao dich nao, khong nhan lenh, khong mo cong vao (khong dung Socket). Moi `SendIntervalSec` giay no day (outbound) mot batch JSON qua `WebRequest` HTTPS toi `mt-bridge`: account snapshot, vi the, lenh cho, quote, nen da dong. Giao thuc chung cho MQL4 va MQL5 (xem `services/mt-bridge/src/mtbridge/protocol.py`).

```
mt-agent/
  Include/MTAgent/Core.mqh            # dung chung (#ifdef __MQL5__ cho khac biet API)
  MQL4/Experts/MTAgentReadOnly.mq4
  MQL5/Experts/MTAgentReadOnly.mq5
```

## Cai dat cho CLIENT (EA v1.1) - KHONG nhap mat khau giao dich o bat ky dau
> **Tuyet doi KHONG nhap mat khau giao dich / investor cua tai khoan MT vao EA, vao cong web hay gui cho master.** EA chay trong terminal MT4/MT5 ma ban da dang nhap san; no chi DOC va gui du lieu ra. Du lieu EA gui: so du/equity/margin, vi the, lenh cho, gia, nen, lich su lenh da dong. EA khong the dat/sua/dong lenh (khong co ma giao dich).

1. **Tai EA**: lay thu muc `mt-agent` (Include/MTAgent, `MQL4/Experts/MTAgentReadOnly.mq4` hoac `MQL5/Experts/MTAgentReadOnly.mq5`) tu master. Copy `Include/MTAgent/` vao `<Data Folder>/MQL4/Include/` (hoac `MQL5/Include/`) va file EA vao `<Data Folder>/MQL4/Experts/` (hoac `MQL5/Experts/`) (MT: File > Open Data Folder). Mo MetaEditor, bam F7 (bien dich, phai 0 loi).
2. **Cho phep WebRequest**: Tools > Options > Expert Advisors > tick *Allow WebRequest for listed URL* > them **URL goc** cua bridge master cung cap (vd `https://bridge.example.com`). Thieu buoc nay log bao loi 4060 (MT5: 4014; MT4: 5200).
3. **Nhan tu master** (qua kenh an toan, khong qua email thuong): `BridgeUrl` (dang `https://.../ingest/v1`) va **mot trong hai**:
   - **PairCode (khuyen dung)**: ma ghep cap ngan (dung 1 lan). EA tu xin Token + HMAC secret tu bridge va luu o thu muc `MQL*/Files` cua terminal (`MTAgent_<mt4|mt5>_<so tai khoan>.cred`). Ban khong phai dan token dai.
   - **Token + HmacSecret**: master giao truc tiep (hien dung 1 lan khi tao/xoay).
4. Keo EA vao **1 chart** (bat *Allow Algo Trading* neu terminal doi; khong can cho phep giao dich). Inputs: `BridgeUrl`, `PairCode` *hoac* `Token`+`HmacSecret`, `Symbols` (ten symbol cua BROKER, vd `EURUSD.m`), `Timeframes`. `AccountId` de trong (EA tu dat `mt4:<login>`/`mt5:<login>`).
5. **Xem trang thai** ngay tren chart (`Comment`) va tab Experts. EA khong bao gio in Token/HMAC. Cac trang thai:

| Hien thi | Y nghia | Viec can lam |
|---|---|---|
| `ghep cap: pending` + `Ma ghep cap: XXXXXX` | Da gui yeu cau, cho master duyet (EA tu thu lai moi 30s) | Dua ma cho master hoac nhap o cong `/c/` (Ghep cap) |
| `ghep cap: rejected` | Ma sai/het han/khong khop so tai khoan | Xin ma moi |
| `ghep cap thanh cong` -> `ok` | Da co credential, dang gui du lieu | - |
| `cho master duyet (pending)` | Credential dung nhung tai khoan chua duoc kich hoat (bridge tra 202, KHONG nhan du lieu) | Cho master |
| `401: token/HMAC sai hoac da bi thu hoi` | Token/HMAC khong khop, bi xoay, hoac dong ho lech > 120s | Nhap lai/xin ma moi; dong bo gio (NTP) |
| `403: tai khoan bi DINH CHI` | Master dinh chi | Lien he master |
| `429` | Gui qua nhanh | Tang `SendIntervalSec` |
| `WebRequest loi 4060/4014/5200` | URL chua nam trong danh sach cho phep (MT4 chi cong 80/443) | Lam lai buoc 2 |

6. Tren master (`GET /accounts` cua bridge, trang *Khach hang*): thay `ea_status` (online/degraded/offline), do tre (RTT), phien ban EA, build terminal, ten broker, may chu broker, lan cuoi thay du lieu. Degraded = RTT cao, lech dong ho, hoac loi gui lien tiep.

### Cho master: cap phat tai khoan
`Khach hang > Them tai khoan` (service `auth`): chon nen tang + so tai khoan -> he thong sinh EA token, HMAC secret (HMAC **bat mac dinh**), ma ghep cap -> giao cho client (hien 1 lan). Xoay token/HMAC, dinh chi, kich hoat co hieu luc o request ke tiep (bridge duoc bao `invalidate`). Hop dong chi tiet: `docs/CLIENT_PLATFORM.md` (muc "Van hanh EA + cap phat tai khoan dong"). Voi tai khoan cau hinh tinh (`accounts.yaml`) van dung `token_env`/`hmac_secret_env`/`require_hmac`.

### Bao mat (tom tat)
- HMAC-SHA256 (`X-MT-Sig`) tren `"<ts>.<nonce>." + body`: chong gia mao/sua body/replay (ts +-120s, nonce khong lap, luu Redis neu co). Tai khoan dong mac dinh BAT; EA 1.1 ky bang SHA-256 thuan MQL (khong can DLL).
- Token chi luu dang bam o bridge; so sanh hang so thoi gian; thu hoi tuc thi. Token/HMAC nam trong inputs/`.cred` cua terminal: coi la bi lo neu may bi xam nhap -> xin xoay. **Terminal MT in gia tri input cua EA vao log Experts** (`MQL*/Logs`): khong gui file log cho nguoi khac; khong commit file `.set`.
- Luon HTTPS (EA tu choi `http://` tru khi `AllowInsecureHttp=true`, chi de thu nghiem).

## Quy tac van hanh
- **1 terminal = 1 tai khoan** (moi terminal mot thu muc cai rieng, portable mode `/portable`); N tai khoan = N terminal + N EA + N token.
- **MT4/MT5 chay duoc trong Docker/Wine 9** (lab o `mt-agent/lab`, huong dan `LAB.md`); luu y MetaQuotes xem Wine la "unsupported" - production nen dung Windows VPS. MT4 `WebRequest` chi cho cong 80/443; URL trong danh sach cho phep phai co dau cham.
- Dang nhap terminal bang **mat khau investor** neu duoc: EA van doc duoc; khong the bi dung de giao dich. EA khong chua code giao dich.
- Token nam trong inputs cua EA (hien o file `.set`/profile): coi la bi lo neu may bi xam nhap -> doi token tren bridge (thu hoi). Khong commit file `.set` co token.
- Token qua HTTP thuong la lo: luon dung HTTPS (EA tu choi `http://` tru khi bat `AllowInsecureHttp`).
- Gui lai khi loi: EA khong luu hang doi nhi phan. Snapshot/quote la trang thai moi nhat; nen dung **cursor** (chi tien khi bridge tra 200/409), nen khong mat nen khi mat mang; moi lan gui co `ts`+`nonce` moi (tranh bi chan boi chong replay); backoff luy thua toi da 60s.
- Cuoi tuan/thi truong dong: timer van chay nen heartbeat van duoc gui.

## Kiem tra EULA / ToS (bat buoc)
Moi broker co dieu khoan rieng ve EA, VPS, doc du lieu va chia se du lieu thi truong. Kiem tra truoc khi trien khai tren tai khoan that; MetaQuotes cung co dieu khoan cho terminal. Du an nay khong tu dong hoa giao dich o phase nay.

## Nguon tham khao
- darwinex/dwxconnect (EA <-> Python; BSD-3-Clause): hoc cach tach EA/connector; o day dao chieu thanh outbound-only HTTP. Khong sao chep ma; neu sau nay tai su dung doan ma thi giu nguyen thong bao ban quyen.

## Ghi chu ky thuat can xac minh khi bien dich
- Cac hang `ACCOUNT_TRADE_ALLOWED`, `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`, `StringGetCharacter`, chu ky 7 tham so cua `WebRequest` trong MQL4 build moi, `iVolume` (tick volume) tren MQL5.
- Thoi gian gui la `TimeGMT()`/`TimeCurrent()`; neu broker lech gio server hoac terminal khong dong bo dong ho he thong, `ts` co the lech >120s so voi bridge -> 401 (chinh dong ho/NTP hoac tang `BRIDGE_SKEW_S`).
- EA chay duoc khi nut AutoTrading tat? Can xac minh tren tung build (khong anh huong WebRequest/OnTimer theo tai lieu, chua thu).

## HMAC-SHA256 (X-MT-Sig) — EA mới (2026-10-11, ARCH_AUDIT S-6)
- Input mới `HmacSecret` (cả MQL4/MQL5). Khi để trống EA hoạt động như cũ (chỉ Bearer token). Khi có giá trị, EA gửi thêm header `X-MT-Sig = hex(HMAC_SHA256(secret, "<ts>.<nonce>." + body))`, khớp `mtbridge.protocol.sign()`.
- Bridge: tài khoản có `hmac_secret_env` trong `accounts.yaml` BẮT BUỘC chữ ký (sai/thiếu -> 401). Hiện **demo-mt4-01 đã bật HMAC**; **demo-mt5-01 chưa** (chờ EA MT5 mới được biên dịch + thử trong lab). Khi mọi EA đã cập nhật: đặt `MT_REQUIRE_HMAC=1` trong `infra/.env` (bridge từ chối tài khoản agent không có HMAC — fail-closed).
- Sinh secret: `sh infra/ops/gen_mt_hmac.sh` (ghi `MT_HMAC_*` vào `infra/.env`, không in). Đọc giá trị để dán vào EA: `grep MT_HMAC_DEMO_MT4_01 infra/.env` (coi như mật khẩu).
- Nonce: bridge lưu nonce trong Redis (`SET NX EX`, `BRIDGE_NONCE_TTL_S`=600) nên replay bị chặn xuyên restart; cache RAM giữ làm lớp phụ.
- Thuật toán SHA-256/HMAC trong `Core.mqh` là MQL thuần (không dùng CryptEncode, chạy cả MT4 lẫn MT5); hằng số được sinh bằng số nguyên và thuật toán mirror trong Python đã khớp `hashlib/hmac` với nhiều độ dài, và đoạn MQL **đã biên dịch sạch** (MetaEditor MT4/MT5, 0 lỗi 0 cảnh báo, 2026-10-11; lần đầu MT4 báo 2 cảnh báo `uint w[64]` chưa khởi tạo -> đã `ArrayInitialize`). Vẫn nên gửi 1 batch thử tới bridge (HMAC bật) trước khi dùng cho tài khoản mới.

## Lịch sử giao dịch đã đóng (`deals`) — Nhật ký giao dịch (2026-10-11)
- Input mới `HistoryDays` (mặc định 365; `0` = tắt) = cửa sổ backfill lần đầu. Lần đầu cursor = `TimeCurrent() - HistoryDays*86400`. Smoke script đọc cùng khóa `HistoryDays` từ `.set`.
- Batch có thêm khóa `"deals":[...]` **chỉ khi có deal mới** (không có -> bỏ khóa). Mỗi lô tối đa `AGT_MAX_DEALS_BATCH=200`; còn dư thì tick kế tiếp (<=3s) gửi tiếp, không chờ chu kỳ quét. Mỗi deal = khóa của `protocol.DealIn`: `ticket, position_id, symbol, type (0 buy/1 sell = HƯỚNG VỊ THẾ ĐÃ ĐÓNG; 2 = thao tác số dư), lots, open_price, close_price, sl, tp, open_time, close_time (epoch giờ server), profit, swap, commission, magic, comment (<=64), reason ("" | sl | tp | so | expert | client)`.
- **Cursor + idempotent**: EA giữ `g_deal_cursor_time` (close_time lớn nhất đã gửi) + `g_deal_sent_at_cursor[]` (ticket đã gửi có close_time == cursor). Ứng viên = `close_time > cursor` hoặc `== cursor` và ticket chưa gửi; sắp tăng dần theo close_time, lấy 200 đầu. Cursor chỉ tiến sau khi bridge trả 200/409 (`AGT_CommitDeals`); gửi lỗi -> lần sau gửi lại ĐÚNG lô đó (nonce+ts mới). Bridge/DB upsert theo `(account_id, ticket)` nên gửi lại vô hại. Nếu bridge trả 422 hai lần liên tiếp khi đang chờ lô deals, EA bỏ lô đó (log) để không chặn snapshot/vị thế.
- Quét lịch sử tối đa mỗi 15 giây (O(N)), trừ khi vừa gửi đủ 200 deal. Body < 1MB (comment cắt 64, `AGT_Esc` chỉ ASCII).
- **MT4**: `OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)`; 1 lệnh đóng = 1 deal (`position_id = ticket`); balance/credit (type 6/7) -> `type=2`; bỏ lệnh chờ đã xóa. `reason` suy từ comment (`[sl]`, `[tp]`, bắt đầu `so:`). **Hạn chế: MT4 chỉ trả phần lịch sử đang nạp ở tab Account History** (đặt "All History" trong terminal nếu muốn backfill đủ); deal nạp muộn có close_time < cursor sẽ không được gửi.
- **MT5**: `HistorySelect` + `HistoryDealGetTicket`. Deal OUT/OUT_BY/INOUT = 1 deal đóng; `type` ngược chiều deal; open_price = giá TB theo volume các deal IN cùng `DEAL_POSITION_ID`, open_time/sl/tp lấy deal IN đầu tiên, commission = commission(+fee) OUT + commission(+fee) IN theo tỷ lệ volume; `reason` theo `DEAL_REASON`. Deal loại khác (balance/credit/charge/...) -> `type=2`, `profit = profit+commission+swap`. Thuộc tính deal OUT được đọc hết vào mảng TRƯỚC khi gọi `HistorySelectByPosition` (đổi vùng chọn). Hedging và netting dùng chung cách này (theo position id); với netting, 1 position có nhiều deal OUT (đóng từng phần) -> mỗi deal là 1 dòng (commission IN chia theo volume).
- Lô tối đa 200 deal nhưng bước 2 (gộp deal IN) gọi `HistorySelectByPosition` mỗi position một lần: backfill 365 ngày nhiều deal sẽ trải trong nhiều tick.
- Biên dịch/kiểm chứng: xem `LAB.md`. Script fixture `MQL5/Scripts/MTAgentDealFixture.mq5` (không có hàm giao dịch) dựng 5 deal cố định (comment `FIXTURE-JRN`, magic 990001..3) qua cùng hàm `AGT_*` để kiểm chứng định dạng/bridge khi terminal lab chưa có lịch sử thật.
