# MT Lab: MT4 + MT5 tren Wine/Docker (VPS <VPS_IP>, /root/mtlab)

Muc dich: bien dich va chay thu `mt-agent` (EA doc-chi) tren terminal MT4/MT5 THAT, noi vao `mt-bridge` cua stack `tradingsys`. Ban sao cua file nay nam o `/root/mtlab/README.md`. Ma nguon lab: `mt-agent/lab/` (Dockerfile, compose, scripts).

## Ket qua (2026-10-11)
| Hang muc | Ket qua |
|---|---|
| MT5 (build 6253) + MT4 (build 1492) chay trong Wine 9.0 / Docker | OK (VNC 127.0.0.1:5901 = MT5, :5902 = MT4) |
| Bien dich `MTAgentReadOnly.mq4` (MetaEditor MT4) | **0 loi, 1 canh bao** -> sua canh bao (prototype `long AGT_LoginNum();` bi MQL4 coi la `#import`) -> **0 loi 0 canh bao** |
| Bien dich `MTAgentReadOnly.mq5` (MetaEditor64) | **0 loi, 0 canh bao** (ngay lan dau) |
| MT5: EA -> bridge -> Redis -> storage-writer -> Postgres | OK (account_snapshots, quotes, bars; `GET /accounts` connected=true) |
| MT4: -> bridge -> Redis -> Postgres | OK nhung bang **script `MTAgentSmoke`**, khong phai EA (xem muc "MT4 offline") |
| Tai khoan DEMO that (ket noi may chu broker, gia live) | **CHUA**: buoc mo demo can nhap ho ten/email/dien thoai vao form cua MetaQuotes -> dung lai, de nguoi dung lam tay |
| Python `MetaTrader5` (adapter mt5_direct) trong Wine | Python 3.11 + goi cai duoc, `import` OK (can numpy 1.26.4); `initialize()` -> IPC timeout (-10005): **chua kiem chung** |

### Cap nhat 2026-10-11 (toi): nhanh lich su `deals` + HMAC
| Hang muc | Ket qua |
|---|---|
| Bien dich `MTAgentReadOnly.mq4` + `MTAgentSmoke.mq4` (MT4 build 1492) voi nhanh lich su | **0 loi 0 canh bao** (lan dau 2 canh bao 60 `uint w[64]` chua khoi tao trong SHA-256 HMAC -> them `ArrayInitialize`) |
| Bien dich `MTAgentReadOnly.mq5` + `MTAgentDealFixture.mq5` (MT5 build 6253) | **0 loi 0 canh bao** |
| EA MT5 khoi dong lai voi Core moi, HistoryDays=365 (mac dinh, .set cu chua co khoa) | Chay on, bridge tra 200, khong 4xx/5xx. Terminal lab **khong co lich su that** (tai khoan login=0) => EA khong gui khoa `deals` (dung nhu thiet ke) |
| Duong deal THAT (`HistorySelect`/`OrderSelect MODE_HISTORY` voi du lieu that, cursor nhieu lo, gop deal IN) | **CHUA kiem chung**: chi bien dich; can tai khoan demo co lich su |
| Duong deal bang FIXTURE (`MTAgentDealFixture.mq5`: 5 deal gom 1 type 2, 1 comment co dau nhay kep; gui 2 lan) | OK: HTTP 200 ca 2 lan, 5 dong `account_deals` (gui lai khong nhan doi => idempotent), JSON EA sinh parse duoc bang `protocol.Batch` (dung ten khoa/kieu). Day chi kiem chung dinh dang/bridge/DB, KHONG kiem chung logic lich su cua terminal |
| `test_mql_static.py` (6 test, chay trong container tren VPS) | 6 passed (them DealIn, khoa deals day du, cursor chi tien trong CommitDeals, khong co ham giao dich o moi file MQL) |

Chay fixture: `touch /root/mtlab/out/fixture-mt5 && docker restart mtlab-mt5` (start-term.sh doc co mot lan, chay script `MTAgentDealFixture` thay EA; script tu thu lai WebRequest toi 3 phut cho den khi URL duoc them bang GUI) roi `docker restart mtlab-mt5` lan nua de tra EA. Don du lieu: `DELETE FROM account_deals WHERE comment LIKE 'FIXTURE-JRN%'`.

Du lieu da di qua he thong la du lieu **offline mac dinh cua terminal** (nen EURUSD trong lich su kem theo ban cai, tai khoan login=0, balance 0), du de kiem chung dinh dang/giao thuc/duong ong, KHONG phai gia thi truong that.

## Nguon tai (chinh hang MetaQuotes)
| File | URL | SHA-256 (tai 2026-10-11) |
|---|---|---|
| mt5setup.exe | https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe | `a879492dd9d7b168d0538edd1c0dc5604ca43dc0951825b3501818e8b18f4c93` |
| mt4setup.exe | https://download.mql5.com/cdn/web/metaquotes.software.corp/mt4/mt4setup.exe | `8088bafcbe17aa98c5c3ac7028533caeb97b37ede99a5e59907161edbe5a0eeb` |
| python-3.11.9-amd64.exe | https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe | `5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde` |
MetaQuotes khong cong bo hash; day la hash ghi nhan luc tai (installer la web-installer, doi theo thoi gian). Cai bang co chinh thuc `/auto` (cai im lang vao `C:\Program Files\MetaTrader 5` / `...(x86)\MetaTrader 4`). Cai dat terminal khong yeu cau chap nhan EULA bang tay tren duong `/auto`; nhung quyen su dung demo/broker van theo dieu khoan MetaQuotes: kiem tra truoc khi dung that.

## Cau truc & tai tao
```
/root/mtlab/
  docker-compose.yml      project `mtlab`, 2 service (mtlab-mt5, mtlab-mt4), cpus 2 / mem 3g moi cai, VNC chi 127.0.0.1
  image/Dockerfile        ubuntu 22.04 + WineHQ stable 9.0 + Xvfb + x11vnc + fluxbox + xdotool + imagemagick + python3
  scripts/                start-term.sh (entry), compile.sh, patch_ini.py, patch_chr.py, allow-url*.sh, run-script-mt4.sh, tcp-fwd.py, ...
  ea/                     ban sao ma nguon EA (Include/MTAgent, MQL4, MQL5) - dong bo bang mt-agent/lab/put-ea.sh
  secrets-mt4.env, secrets-mt5.env   token (chmod 600, KHONG commit)
  dl/                     installer
  out/                    log bien dich, screenshot
```
1. `docker build -t mtlab-wine:9 image` (~4 phut). **Phai dung Wine 9**: `mt5setup.exe` tren Wine 11 va 10 bao "A debugger has been found running" va dung (chong debug cua installer); tren Wine 9.0 chay duoc. (MT5 in log: "unstable and unsupported Wine 9.0 ... upgrade to Wine 10" - chi la canh bao.)
2. Tao `secrets-mt4.env` / `secrets-mt5.env` tu `/root/trading-system/infra/.env` (`MT_TOKEN_DEMO_MT4_01=...`, `MT_TOKEN_DEMO_MT5_01=...`).
3. Lan dau chay: cai terminal (`wine mt5setup.exe /auto`), chay `terminal /portable` 40s de tao thu muc du lieu (portable: data = thu muc cai), bien dich EA, sinh `MQL*/Presets/MTAgentReadOnly.set` (token lay tu env, khong ghi vao git), `startup.ini` (`[StartUp] Expert=MTAgentReadOnly`).
4. `cd /root/mtlab && docker compose -p mtlab up -d`. Container tu cai/bien dich/khoi dong; terminal tu khoi dong lai neu thoat.
5. **Buoc GUI (tu dong moi lan khoi dong)**: `scripts/post-start.sh` chay nen sau khi terminal len: dong wizard "Open account"/Login (Cancel), them URL `http://bridge.lab` vao Tools>Options>Expert Advisors>"Allow WebRequest" bang xdotool (`allow-url.sh` MT5, `allow-url-mt4.sh` MT4, MT4 con bat "Allow automated trading"), roi voi MT4 chay script `MTAgentSmoke` qua Navigator (`run-script-mt4.sh`). Trong moi truong nay danh sach URL **khong song qua restart** (da thu thoat sach bang alt+F4: van mat) nen phai them lai moi lan; danh sach luu ma hoa trong `Config/settings.ini`, khong sua tay bang ini duoc. Cac script phu thuoc toa do man hinh 1280x800: neu hong, xem anh `out/allow-url*.png`, `out/run-script.png`.
6. Xem man hinh: `ssh -L 5901:127.0.0.1:5901 root@<VPS_IP>` roi VNC toi localhost:5901 (khong dat mat khau VNC vi chi bind 127.0.0.1 -> bat buoc di qua tunnel SSH).
7. Kiem tra: `bash /root/mtlab/chk.sh` (bridge `/accounts`, Redis streams) va `chk2.sh` (Postgres).

## Cac phat hien/van de (quan trong khi trien khai that)
1. **MQL4 prototype**: `long AGT_LoginNum();` (khai bao truoc) -> `warning 46: no #import declaration` trong MQL4. Da chuyen dinh nghia ham len truoc noi dung dung (Core.mqh).
2. **Danh sach URL WebRequest bat buoc host co dau cham**: `http://mt-bridge:8000` bi tu choi khi nhap (hang khong duoc them). Lab dung ten `bridge.lab` -> `127.0.0.1`.
3. **MT4 chi cho WebRequest cong 80/443** (loi 5200 ERR_WEBREQUEST_INVALID_ADDRESS voi `:8000`). Lab chay forwarder `tcp-fwd.py` 127.0.0.1:80 -> `mt-bridge:8000` trong moi container. Khi trien khai that: dat bridge sau reverse proxy HTTPS 443 (dung khuyen nghi san co cua README).
4. **EA khong tu mo duoc `WebRequest` neu URL khong trong danh sach**: MT5 tra 4014, MT4 tra 4060/5200; EA ghi log + backoff toi 60s (hanh vi dung).
5. **MT4 offline khong chay EA**: neu terminal chua dang nhap (khong co ket noi may chu), EA duoc nap ("loaded successfully") nhung `OnInit`/`OnTimer` khong chay. MT5 thi EA chay du offline. Vi vay MT4 duoc kiem chung bang script `MQL4/Scripts/MTAgentSmoke.mq4` (cung `Core.mqh`, doc cau hinh tu `MQL4/Files/MTAgentSmoke.set`, gui ~8 batch roi thoat). Voi tai khoan demo/live that EA chay binh thuong (chua kiem chung do chua co tai khoan).
6. **Chong hoi quy**: lan dau chay MT4 EA phat hien **bug o bridge**: canh bao `trade_allowed` phat lai moi batch (8 hang trung `dedupe_key` trong Postgres) trai voi README ("bao theo chuyen trang thai"). Da sua `services/mt-bridge/src/mtbridge/service.py` (tap `_ta_warned`) + test `test_trade_allowed_alert_only_on_transition`; pytest 30 passed. Da deploy len VPS.
7. Terminal MT4/MT5 in **tham so input cua EA (ca token)** vao log Experts (`MQL*/Logs`). Log nam trong volume lab; `scripts/logs.sh` che token khi in. Token tung bi lo vao hoi thoai khi debug -> da **xoay** (MT_TOKEN_DEMO_MT4_01/MT5_01 trong infra/.env, tao lai mt-bridge).
8. `/tmp/.X1-lock` ton tai sau `docker restart` lam Xvfb khong len (MT bao "Initialization failed [10042]"): entrypoint xoa lock truoc khi chay Xvfb.
9. Wine can `WINEDLLOVERRIDES=mscoree,mshtml=d` (khong thi hop thoai Mono/Gecko chan khoi tao prefix).
10. `terminal.ini` cua MT4 la ASCII, `common.ini` MT5 la UTF-16: `patch_ini.py` giu nguyen ma hoa goc (ghi nham UTF-16 vao file ASCII lam MT4 khong khoi dong).
11. MT5 `startup.ini` them mot chart EA moi moi lan restart (EA nhan ban, nhieu EA cung gui; da thay 6-7 chart sau nhieu lan restart) - chua xu ly dut diem (bridge van chap nhan vi nonce khac nhau); can `docker compose down -v` hoac xoa chart trong volume de don. MT4 khong ap dung `[StartUp] Expert=` khi offline: chen khoi `<expert>` vao `profiles/default/chart01.CHR` (`patch_chr.py`).
12. Python `MetaTrader5` can `numpy==1.26.4` trong Wine 9 (numpy 2.x goi `ucrtbase.crealf` chua cai dat -> abort).

## Chua kiem chung / viec con lai
- **Tai khoan demo that + gia live**: mo demo qua wizard (File > Open an Account > MetaQuotes-Demo) can nhap ten/email/dien thoai: khong tu dong hoa. Sau khi co login/mat khau, dat `MT_LOGIN/MT_SERVER/MT_PASSWORD` (password INVESTOR neu co) trong `environment` cua service va `docker compose up -d`; `startup.ini` se dang nhap, MT4 EA se chay (dat `MT4_MODE=ea`).
- Vi the/lenh cho (positions/orders) chua duoc thu vi tai khoan trong; nhanh `AGT_PositionsJson/AGT_OrdersJson` da duoc bien dich nhung chua chay voi du lieu.
- `mt5_direct` (goi Python `MetaTrader5` trong Wine): `initialize()` IPC timeout, co the can terminal da dang nhap / khac biet pipe cua Wine. Khong ket luan.
- Nhieu symbol/khung thoi gian that, lech mui gio server, chay lau dai (reconnect, rotate log) chua thu.
- Wine 9 la ban "khong ho tro" theo MetaQuotes; nen thu Wine moi hon + installer dung cach khac (copy portable) neu can on dinh dai han.

## Tai khoan DEMO THAT MT5 (2026-10-14) - quy trinh KHONG ghi mat khau
Tai khoan: MetaQuotes-Demo, login 100000001 (hedging, EUR, 1:100), chi dung mat khau **INVESTOR** (trading disabled - log terminal "trading has been disabled - investor mode"). EA/script lab chi doc; KHONG co ma dat lenh. Khong dung tai khoan cu `mt5:99000001`.

| File (ngoai git, chmod 600) | Noi dung | Dung boi |
|---|---|---|
| `<SECRETS_DIR>/mt5_demo_100000001.txt` | mat khau investor (nguon goc) | nguoi van hanh |
| `/root/mtlab/secrets-mt5.env` | `MT_LOGIN`, `MT_SERVER`, `MT_PASSWORD` (investor) + token/HMAC lab | `env_file` cua mtlab-mt5 |
| `/root/mtlab/out/ea-mt5.set` | .set EA cho tai khoan that: BridgeUrl, **PairCode**, Symbols | start-term.sh (ghi de .set mac dinh) |
| `<SECRETS_DIR>/mt5_demo_100000001_provision.json` | passcode portal + pairing_code (ket qua `provision.py create`) | nguoi van hanh / client thu |

Luong:
1. **Dang nhap**: start-term.sh sinh `startup.ini` (`[Common] Login/Server/Password` tu env) moi lan container khoi dong. Mat khau chi ton tai trong env container + `startup.ini` trong volume `mtlab_mt5wine` (khong trong repo/out/log). Kiem tra: log terminal `authorized on MetaQuotes-Demo` + `investor mode`.
2. **Che do JOB** (xuat lich su): `/root/mtlab/out/job-mt5.cfg` 2 dong (`MTAgentExport` / `MTAgentExport.set`) -> startup chay SCRIPT thay EA. **Giu file = moi lan restart lai chay job**; xoa file de tra EA. `MTAgentExport.set`: `Mode=export`, `SymbolList=...`, `TfList=ALL` (21 khung), `MaxWaitSec`. Ket qua trong container: `.../MQL5/Files/export/<SYM>_<TF>.bin` + `status.csv`; log `MQL5/logs/YYYYMMDD.log` (UTF-16, "export ALL DONE"). common.ini duoc dat `Charts MaxBars=100000000` de lay toan bo lich su M1 **chi khi co job-mt5.cfg**; che do EA dung `MT5_MAXBARS_EA` (mac dinh 100000 ~ 70 ngay M1; RAM terminal 7 ma: ~4.4g -> ~1g, 2026-10-14). Can **mem_limit 10g** (terminal giu M1 cua moi ma da xuat: ~5.7g sau 4 ma; 3g -> swap nang).
3. **Che do EA**: `ea-mt5.set` (2026-10-14: `Symbols=EURUSD,XAUUSD,GBPUSD,USDJPY,US500,US30,USTEC`, `Timeframes=M1,M5,M15,H1` - H4/D1 cua EA theo gio server nen bo; khung cao lay tu feed canon cua mt-bridge) co `PairCode` -> EA goi register tren bridge, nhan credential luu `MQL5/Files/MTAgent_*.cred`, account_id = `mt5:100000001`, gui snapshot co HMAC. post-start.sh them URL WebRequest bang xdotool moi lan khoi dong (~25-60s).
4. **Tai khoan portal** `mt5:100000001` tao/kich hoat/xoa bang `docker exec -i tradingsys-auth python - create|activate <id>|delete <id> < /root/mtlab/out/provision.py` (ban sao `mt-agent/lab/provision.py`). `create` in passcode ra stdout -> chuyen thang vao file secrets 600, khong dan vao chat/log.
5. Nhap du lieu: `docker cp` cac `.bin` ra `data/research/patterns/mt5/raw/` roi `bash /root/mtlab/out/runimp.sh <SYM>` (ban sao `mt-agent/lab/runimp.sh`) - xem `docs/research/PATTERN_DATA.md` muc MT5 Gio server = EET (importer mac dinh `MT5_TZ_RULE=eu`). Sau khi parquet kiem xong: `zstd -T6 -15 --rm raw/*.bin` (giu `.bin.zst`).
6. **Tra EA sau job**: `rm /root/mtlab/out/job-mt5.cfg && docker restart mtlab-mt5` -> log `MTAgent: init ok account=mt5:100000001 ... (READ-ONLY)` + `ghep cap thanh cong, status=active`. Kiem: `mt_accounts.ea_status=online`, `account_snapshots` moi 3s, `bars/quotes source='mt5:mt5:100000001'` (M1 dong tre ~1 phut, quote <1s). Da thu cat mang 60s: EA tu noi lai ngay (2026-10-14).

Luu y bao mat: terminal in **input cua EA** (PairCode/Token) vao log Experts -> chi doc log qua `scripts/logs.sh` (che token); khong copy log tho ra ngoai VPS.


## Terminal FEED toan bo cap (mtlab-mt5-feed, 2026-10-14)
Terminal MT5 THU HAI (cung login investor demo 100000001, READ-ONLY) chay EA `MTAgentMarketFeed` (162 ma Forex/Metals/Indexes) -> mt-bridge account `mt5:100000001-feed`. Tach rieng khoi `mtlab-mt5` (EA 7 ma) va `mtlab-mt5-hist` (xuat lich su).
- Container: image `mtlab-wine:9`, `--cpus 1.5 --memory 3g --shm-size 512m`, volume `mtlab_feedwine`, mang `tradingsys_internal`, KHONG publish cong. Mount: `mt-agent/lab-feed/scripts:/mtlab:ro`, `mt-agent/lab-feed/ea:/ea:ro` (Core.mqh + `feed_symbols.txt` 162 ma), `mt-agent/MQL5:/feedsrc:ro` (nguon EA), `mt-agent/lab-feed/out:/out`, `/root/mtlab/dl:/dl:ro`. Env (env-file 600 NGOAI repo): MT_LOGIN/MT_SERVER/MT_PASSWORD (investor, lay tu env cua mtlab-mt5-hist), MT_KIND=mt5, WINEPREFIX, WINEDLLOVERRIDES, MT_PAIRCODE.
- Tao: `docker volume create mtlab_feedwine; docker run -d --name mtlab-mt5-feed --restart unless-stopped --cpus 1.5 --memory 3g --shm-size 512m --network tradingsys_internal --env-file <env600> -v mtlab_feedwine:/wine -v .../lab-feed/scripts:/mtlab:ro -v /root/mtlab/dl:/dl:ro -v .../lab-feed/ea:/ea:ro -v .../mt-agent/MQL5:/feedsrc:ro -v .../lab-feed/out:/out mtlab-wine:9`. Entry: `start-mt5.sh` -> `start-feed.sh` (cai dat lan dau ~3 phut, `compile-feed.sh` chi bien dich MTAgentMarketFeed.ex5, KHONG dung MTAgentReadOnly, xoa chart cu, startup.ini gan EA tren 1 chart EURUSD M1, patch MaxBars=5000, `post-start.sh` them URL `http://bridge.lab` vao Allow WebRequest bang GUI).
- Ghep cap: tao account `docker exec -i tradingsys-auth python - create-feed < mt-agent/lab/provision.py > <file600>`; ma ghep cap moi `... python - newcode mt5:100000001-feed < provision.py > <file600>` (ma dung 1 lan; neu EA timeout luc ghep cap thi credential mat -> cap ma moi). Credential luu trong volume (`MQL5/Files/MTAgentFeed_<login>.cred`).
- Tham so (env container, mac dinh): FEED_SCAN_MS=40, FEED_FLUSH_MS=250, FEED_MSG_PER_SEC=4, FEED_START_DELAY=90 (EA im lang 90 s de script GUI them URL WebRequest xong; mo hop thoai Options luc EA nap lich su lam treo terminal).
- Dung/restart sach: `docker stop -t 40 mtlab-mt5-feed` (trap alt+F4 de terminal ghi settings), `docker start mtlab-mt5-feed`. Sau khoi dong ~2.5 phut moi bat dau gui.
- Giam sat: log EA moi 30 s `MTFeed: stat ... / silent>5p=` (xem bang `iconv -f UTF-16LE -t UTF-8 .../MQL5/logs/<ngay>.log`), Prometheus `mtbridge_feed_*`, dashboard ts-feed-all, `mt_accounts.ea_status` account `-feed`.
- ROLLBACK: `docker stop mtlab-mt5-feed && docker rm mtlab-mt5-feed` (volume `mtlab_feedwine` giu de dung lai, hoac `docker volume rm mtlab_feedwine`); tat phia server `FEED_ALL_ENABLED=false` (mt-bridge) -> khong con chuoi canon thu 2; EA 7 ma + pipeline cu khong doi. Neu VPS qua tai: tang FEED_SCAN_MS/FEED_FLUSH_MS (tao lai container) hoac dung container.
- Bay da gap: GetTickCount() trong Wine = uptime may chu (>24.8 ngay -> so sanh `(int)(now-0)` am); ghep cap qua auth > TimeoutMs gui batch (register dung timeout 15 s); `docker restart` mac dinh 10 s khong du de terminal luu settings (dung `stop -t 40`).
