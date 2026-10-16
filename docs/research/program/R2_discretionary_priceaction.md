# R2 - Discretionary / price action / cung-cau / SMC / Wyckoff / Elliott / ICT

Ngay 2026-10-15. Pham vi: nghien cuu READ-ONLY/paper, khong lenh that. Ma + ket qua tho: `data/research/program/R2/` (r2_lib.py, r2_run.py, r2_analyze.py, r2_sens.py, cells.csv, cells_adj.csv, pooled_adj.csv, trades_train.parquet). Chi dung doan TRAIN (< 2025-07-27); KHONG mo VAL/TEST.

## 0. Ket luan (30 giay)
1. **Khong co edge dang tin cay sau chi phi** trong 4 y tuong duoc hinh thuc hoa (FVG fill, liquidity sweep, BOS pullback, Wyckoff spring/upthrust). 3/4 **lo co y nghia thong ke** (Sweep -0,11..-0,14 R/lenh, Wyckoff -0,14..-0,16 R, BOS -0,05..-0,06 R); truoc chi phi gan 0 (quanh 0 +-0,03 R) = tuong duong vao lenh ngau nhien.
2. **Ung vien duy nhat: FVG fill khung H4 (TP 2R), +0,093 R/lenh sau chi phi, z=4,7, sau Holm (m=20 pooled) van <0,001.** NHUNG edge **phu thuoc hoan toan gia dinh khop lenh limit "cham la khop"**: chi can doi gia xuyen qua muc vao 0,05 ATR thi giam con +0,045 R (H4) va am o H1; 0,15 ATR -> am (-0,055 R). Day la nhom thien lech tuong tac lenh cho (khong co hang doi, khong tu chon bat loi). Ket luan: **chua phai edge, khong dua vao paper-trade nhu chien luoc**; chi du tinh de dua vao danh sach "can kiem tra tick/L2 hoac bang lenh cho thuc" (khong lam duoc voi du lieu 0 dong).
3. Moi y tuong SMC/ICT khac (order block, CHoCH, premium/discount, killzone...) la bien the cua cung cac khoi tren (swing + gap + sweep + retest); ket qua tren la can tren hop ly cua nhom nay khi hinh thuc hoa khach quan. Elliott: khong hinh thuc hoa duoc mot cach duy nhat (dem song chu quan) -> khong kiem dinh duoc, loai.

## 1. Cac phuong phap co kiem dinh duoc khong?
| Nhom | Kiem dinh duoc? | Ghi chu |
|---|---|---|
| Support/resistance, breakout, sweep, range | Co - de hinh thuc hoa bang rolling max/min, fractal swing | da thu |
| FVG/imbalance, order block, BOS/CHoCH (SMC/ICT) | Co, sau khi chot dinh nghia (nen lien tiep, swing k, nguong ATR); moi dinh nghia la 1 gia thuyet -> dem vao da so sanh | FVG, BOS da thu |
| Wyckoff (spring, upthrust, accumulation) | Mot phan: spring/UT = range + quet + dong lai trong range; "pha" Wyckoff chu quan | spring/UT da thu |
| Elliott, Gann, "cam nhan" discretionary, doc order flow bang mat | Khong (dem song/ngu canh chu quan, nhieu cach goi); kiem dinh cung la kiem dinh nguoi dat nhan | loai |
Nguyen tac: chi "tin" khi luat duoc khoa truoc, chay tren du lieu chua nhin, tinh chi phi that, so voi baseline ngau nhien cung co che va hieu chinh da so sanh.

## 2. Tai lieu hoc thuat (muc tin cay)
- **Bajgrowicz & Scaillet (2012), JFE 106(3):473-491**, "Technical trading revisited: false discoveries, persistence tests, and transaction costs" - DJIA 1897-2011, kiem soat FDR; **khong the chon truoc luat tot ngoai mau; loi nhuan trong mau bi chi phi giao dich thap xoa het** [nguon: ideas.repec.org/a/eee/jfinec/v106y2012i3p473-491.html, CFA Digest]. Tin cay: CAO (da doc tom tat).
- **Park & Irwin (2007), J. Economic Surveys 21(4):786-826** - tong quan 92 nghien cuu hien dai: 58 duong, 24 am, nhung phan lon vuong data snooping, chon luat sau khi biet ket qua, uoc luong chi phi/rui ro yeu; loi nhuan giam ro tu sau ~1990 [ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html]. Tin cay: CAO (so lieu tu ban 2004).
- **Lo, Mamaysky & Wang (2000), J. Finance 55(4)** "Foundations of Technical Analysis" - hoi quy kernel nhan 10 mau hinh (head-and-shoulders, double top...) tren co phieu My 1962-96: mot so mau hinh co **thong tin gia tang nho** ve phan phoi loi nhuan, khong chung minh loi nhuan sau chi phi. Tin cay: TRUNG BINH (tu tri nho, chua mo lai ban goc; web search khong tra ve).
- Brock, Lakonishok & LeBaron (1992), Osler (2003, ho tro/khang cu FX), Neely-Weller-Ulrich (2009, loi nhuan FX giam dan): bang chung som co loi nhuan, sau do bien mat/giam. Tin cay: TRUNG BINH (nho, khong mo lai).
- Ban trong du an: PATTERN_SELL_BACKTEST (KB-1..4: -0,100 R/lenh dev, -0,263 R test khoa; DSR=0, PBO 0,86), METHODS_SURVEY.

## 3. Hinh thuc hoa thanh luat may
Du lieu: MT5 native (`data/research/patterns/mt5/bars`), 5 ma (EURUSD, GBPUSD, USDJPY, XAUUSD, US500) x H1, H4; TRAIN tu 2010-01 (US500 tu 2012-09) toi 2025-07-27; bo nen n_m1 < 50%. ATR14 chi dung nen da dong. Tin hieu biet khi nen i DONG, vao tu nen i+1.
- **FVG fill:** FVG tang khi low[i] > high[i-2], nen giua tang, gap >= 0,3 ATR (giam mirror). Lenh LIMIT tai mep gap (low[i]) hieu luc 20 nen; SL = low nen giua (i-1).
- **Liquidity sweep reversal:** nen quet qua dinh/day N nen truoc (N=20, 50) nhung dong cua lai ben trong va nen nguoc huong -> vao nguoc o open ke tiep; SL = cuc tri nen quet +-0,1 ATR.
- **BOS pullback:** swing fractal k=3 (xac nhan sau 3 nen); dong cua pha swing gan nhat lan dau = BOS; LIMIT tai muc swing bi pha (retest), SL = swing doi dien gan nhat, hieu luc 20 nen.
- **Wyckoff spring/upthrust:** range 40 nen co rong <= 4 ATR; nen quet xuong (len) day (dinh) <= 1 ATR roi dong cua lai trong range -> vao o open ke tiep; SL = cuc tri +-0,1 ATR.
Chung: hai chieu, TP = 1R hoac 2R (2 bien the), thoi gian giu toi da 50 nen (het gio dong o close), loc rui ro SL trong [0,25; 3] ATR, **moi lan mot lenh** (khong chong lan). Bien the = 5 (FVG, Sweep20, Sweep50, BOS, Wyckoff) x 2 RR x 5 ma x 2 khung = **100 o**.
Khop lenh bi quan: SL truoc neu cung nen SL va TP; gap qua SL khop o gia mo; nen khop lenh limit khong xet TP; chi phi khu hoi COST (EURUSD 1,4 pip, GBPUSD 1,8 pip, USDJPY 1,6 pip, XAUUSD 0,30 USD, US500 1,1 diem) tru vao R. (Loi da sua giua chung: ban dau huy lenh limit khi nen dong duoi SL = lookahead, tao edge ao FVG +0,15 R; da bo - nen la bai hoc ro cho ca cac backtest SMC.)

## 4. Ket qua (TRAIN, R/lenh sau chi phi)
Trung binh gia quyen theo so lenh toan 10 o ma x khung (sau khi sua loi):
| Y tuong | RR | n | Net R | Gross R | Baseline ngau nhien (net) |
|---|---|---|---|---|---|
| BOS pullback | 1 / 2 | 14,5k / 12,4k | -0,064 / -0,052 | -0,007 / +0,004 | -0,060 / -0,048 |
| FVG fill | 1 / 2 | 27,3k / 23,0k | -0,018 / +0,019 | +0,074 / +0,111 | -0,127 / -0,108 |
| Sweep N20 | 1 / 2 | 22,2k / 20,5k | -0,126 / -0,114 | -0,019 / -0,007 | -0,156 / -0,128 |
| Sweep N50 | 1 / 2 | 13,4k / 13,0k | -0,116 / -0,110 | -0,010 / -0,004 | -0,160 / -0,134 |
| Wyckoff spring | 1 / 2 | 733 / 709 | -0,164 / -0,140 | -0,029 / -0,008 | -0,223 / -0,199 |
Baseline: cung so lenh/ma/khung, cung huong, cung phan bo SL (va khoang cach tu close toi muc limit) theo ATR, thoi diem ngau nhien, 200 seed. Sweep/Wyckoff/BOS: ket qua ~ baseline hoac te hon (p_rand khong y nghia; vi du BOS EURUSD p_rand 0,5-0,75). Sweep va Wyckoff **lo hon baseline mot chut do chi phi chi tren R nho** (SL sat), khong co dau hieu "dao chieu theo thanh khoan".
Kiem dinh: SE cluster theo thang (chong chong lan/tuong quan cheo), z 2 phia; hieu chinh da so sanh Holm/BH.
- 100 o: net>0 va p<0,05 tho: 4; **sau Holm: 1 o duong (USDJPY H4 FVG RR2, +0,16 R, Holm 0,011)**; 24 o con lai sau Holm co y nghia nhung deu AM (BOS/Sweep/Wyckoff).
- Gop theo (y tuong x RR x khung, m=20): chi **FVG RR2 H4 duong co y nghia** (+0,093 R, n=5070, z 4,68, Holm<0,001) va FVG RR1 H4 (+0,035, Holm 0,069, khong dat). FVG H1: ~0 (RR2: -0,001) / am (RR1: -0,034).
- Theo huong (FVG RR2): long +0,036 (z 2,2), short +0,002 -> khong doi xung (xu huong tang dai han cua mau 2010-2025 vang/US500?).
- Theo ma (FVG RR2 H4): EUR +0,07, GBP +0,08, JPY +0,16, XAU +0,07, US500 +0,06; **theo nam** H4: 11/16 nam duong, nhung 2021, 2023, 2025 ~0/am; khong suy giam ro ret theo thoi gian (nua dau/sau nhu nhau).
- **Do nhay khop lenh (FVG RR2)**, pooled 5 ma: pen = so ATR gia phai xuyen qua muc limit moi tinh la khop:
| pen (ATR) | H1 net R | H4 net R |
|---|---|---|
| 0 (gia dinh mac dinh) | -0,001 | +0,093 |
| 0,05 | -0,050 | +0,045 |
| 0,15 | -0,141 | -0,055 |
| 0,30 | -0,289 | -0,209 |
Khong don dieu thuan loi: lenh chi khop khi gia xuyen sau thuong la lenh di tiep qua SL (thien lech chon loc). Tuc **neu thuc te lenh limit khong luon khop o cham dau tien, edge bien mat**; neu khop luon thi cung moi la +0,09 R truoc rui ro mo hinh. Tang nguong kich thuoc gap (0,6 / 1,0 ATR) lam H4 giam (+0,038 / +0,053, z ~1,5): khong co dau hieu "gap lon hon tot hon" -> phu hop gia thuyet la nhieu/gia tao chu khong phai co che.

## 5. Bai hoc tu KB-1..4 va ap dung
- Cung ket luan: **mau hinh hinh hoc, truoc chi phi ~0 R** (KB: +0,012 R; Sweep/BOS/Wyckoff: -0,02..0,00 R); chi phi (0,05-0,15 R/lenh) quyet dinh dau. Khung lon (H4) re hon trong R nen "song" hon, dung voi R7.
- Tham so/ngua da so sanh: KB co DSR=0, PBO 0,86; o day 100 o + 20 gop da la nhieu; chua tinh cac lua chon dinh nghia (k=3, N=20/50, gap 0,3 ATR) -> con uoc luong do thuong qua co the.
- **Nguy co lookahead trong SMC rat cao** (xac nhan swing tre k nen, quyet dinh huy lenh theo nen dong, thu tu high/low trong nen) - da ghi nhan 1 loi tai chinh minh; moi backtest SMC cua nguoi khac can nghi ngo.
- Mau hinh "tin tuong" (chart cong dong ma chi nhin ket qua tot) la survivorship cua anh minh hoa - khong kiem dinh duoc bang vai vi du.

## 6. Khuyen nghi dung / khong dung
| Muc | Khuyen nghi |
|---|---|
| Sweep reversal, Wyckoff spring/UT, BOS pullback (ban hinh thuc hoa) | KHONG dung de vao lenh; chi tuy chon lam "canh bao cau truc" hien thi |
| FVG fill H4 (RR2) | **KHONG dua vao paper-trade nhu chien luoc**; ghi vao backlog nhu gia thuyet "can du lieu khop lenh limit that"; neu muon thu: paper voi khop **nghiem ngat** (pen>=0,15 ATR) - ky vong am |
| Elliott/Gann/ICT "killzone" chu quan | Loai (khong kiem dinh duoc) hoac chi tinh nhu bo loc thoi gian (gia thuyet, can gop vao R7) |
Buoc tiep neu muon: khoa 1 dinh nghia FVG-H4 truoc (khong tinh chinh them), chay 1 lan tren VAL (chua mo) voi khop pen=0,05 ATR; chi mo TEST khi VAL dat. Hien chua lam vi nhiem vu R2 chi tren train.

## 7. Han che
- Du lieu feed demo MetaQuotes (spread/gio nghi khac broker that); chi phi dat co dinh theo gia (bi quan cho giai doan nay, co the lac quan cho truoc 2012). Khong co du lieu tick/L2 de kiem dinh khop limit. Mo phong khong co swap (giu <=50 nen). XAUUSD/US500 mau co xu huong tang dai han; khong tach.
- Chi 2 khung (H1/H4), 5 ma; khong thu M15 (chi phi/R lon hon, ket qua nhieu kha nang xau hon). Khong chay Order Block, CHoCH rieng.
- Kiem soat da so sanh tinh theo luoi da chay, khong tinh cac lan sua dinh nghia/khop lenh.
