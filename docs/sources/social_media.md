# Nguon chuyen gia: nhom VIDEO / PODCAST / MANG XA HOI MO

Kiem tra that ngay 2026-10-12 tu VPS <VPS_IP> (curl + parse Python). Cau hinh: `services/expert-collector/config/sources.d/social_media.yaml`.
Nguyen tac: chi lay tieu de + link + mo ta ngan, KHONG tai media; UA `MarketMonitor/1.0`; khong vuot dang nhap/chong bot.

## Tong ket

| Loai | So nguon | Live + enabled | Ghi chu |
|---|---|---|---|
| Podcast RSS | 34 | 33 (1 tat) | tat ca feed tra ep moi trong 30 ngay (tru Sprott/CWT/IMF/Grant Williams: 2-4 tuan) |
| Bluesky (AT Protocol) | 38 | 34 (4 tat vi nhieu/chinh tri) | doc khong can xac thuc, da test getAuthorFeed |
| Reddit RSS | 2 | 0 (mac dinh TAT) | chat luong thap |
| YouTube RSS | 37 | 0 | **endpoint feed tra 404 voi moi kenh** (xem muc duoi) |
| Mastodon | 0 | 0 | khong tim duoc tai khoan kinh te hoat dong co RSS |
| **Tong live + enabled** | | **67** | dat muc tieu >= 40 |

## Tieu chi chon / prior_score
- 0.85-0.95: tai khoan chinh thuc NHTW/co quan thong ke (Fed, ECB, BLS) - nguon goc.
- 0.65-0.8: to chuc quoc te, hang tin lon, nghien cuu CTCK lon, nha kinh te hoc co lich su cong khai.
- 0.4-0.6: binh luan chuyen gia doc lap, podcast phong van macro.
- <=0.3: cong dong (Reddit), chinh kien manh, noi dung ngoai de tai -> mac dinh tat.
- Mo ta ngan, link ve goc; khong lay noi dung day du cua bao tra phi (tranh ban quyen).

## Bang nguon

### Podcast (type=podcast, RSS verified)
| id | Ten | Ep moi nhat | prior |
|---|---|---|---|
| pod_odd_lots | Odd Lots | 2026-10-08 | 0.72 |
| pod_bloomberg_surveillance | Bloomberg Surveillance | 2026-10-09 | 0.70 |
| pod_bloomberg_businessweek | Bloomberg Businessweek | 2026-10-09 | 0.60 |
| pod_bloomberg_big_take | The Big Take | 2026-10-09 | 0.58 |
| pod_bloomberg_daybreak | Bloomberg Daybreak US | 2026-10-09 | 0.62 |
| pod_money_stuff | Money Stuff | 2026-10-02 | 0.60 |
| pod_merryn_talks_money | Merryn Talks Money | 2026-10-07 | 0.55 |
| pod_planet_money | Planet Money | 2026-10-07 | 0.55 |
| pod_the_indicator | The Indicator | 2026-10-08 | 0.58 |
| pod_marketplace | Marketplace | 2026-10-08 | 0.58 |
| pod_freakonomics | Freakonomics Radio | 2026-10-09 | 0.35 |
| pod_econtalk | EconTalk | 2026-10-05 | 0.55 |
| pod_conversations_with_tyler | Conversations with Tyler | 2026-09-30 | 0.50 |
| pod_capitalisnt | Capitalisn't | 2026-10-08 | 0.45 |
| pod_macro_musings | Macro Musings | 2026-10-05 | 0.65 |
| pod_macrovoices | MacroVoices | 2026-10-08 | 0.65 |
| pod_forward_guidance | Forward Guidance | 2026-09-25 | 0.55 |
| pod_real_vision | Real Vision | 2026-09-21 | 0.55 |
| pod_goldman_exchanges | Exchanges at Goldman Sachs | 2026-09-29 | 0.70 |
| pod_morgan_stanley_otm | Thoughts on the Market | 2026-10-08 | 0.70 |
| pod_jpm_making_sense | Making Sense (JPM) | 2026-10-02 | 0.65 |
| pod_animal_spirits | Animal Spirits | 2026-10-05 | 0.40 |
| pod_hidden_forces | Hidden Forces | 2026-10-05 | 0.40 |
| pod_top_traders_unplugged | Top Traders Unplugged | 2026-10-07 | 0.50 |
| pod_chat_with_traders | Chat With Traders | 2026-09-16 | 0.30 (TAT) |
| pod_irf | The IRF Podcast | 2026-10-09 | 0.45 |
| pod_grant_williams | The Grant Williams Podcast | 2026-09-21 | 0.45 |
| pod_wealthion | Wealthion | 2026-10-07 | 0.35 |
| pod_kitco | Kitco News | 2026-10-07 | 0.55 |
| pod_sprott_radio | Sprott Radio | 2026-09-14 | 0.40 |
| pod_economist_money_talks | Money Talks (The Economist) | 2026-10-01 | 0.65 |
| pod_imf | IMF Podcasts | 2026-09-16 | 0.80 |
| pod_boe_money_matters | Money Matters (BoE) | 2026-09-25 | 0.75 |
| pod_world_bank_wh | What Have We Learned (World Bank) | 2026-09-21 | 0.65 |

Loai: Macro Hive Week Ahead (feed dung nhung ep cuoi 2023-10), Otis Report VN (ep cuoi 2022-05) - feed chet.
Chua tim duoc RSS podcast chinh thuc: ECB (ket qua iTunes la podcast khac), Fed, BIS.

### Bluesky (type=bluesky; can provider moi)
38 tai khoan, tat ca da kiem tra `getAuthorFeed` tra bai trong 60 ngay: Reuters, WSJ, FT, The Economist, Bloomberg Opinion, CNBC, MarketWatch, Nikkei Asia; ECB, Lagarde, Federal Reserve, Fed St. Louis, Fed Kansas City, BLS; Brookings, PIIE; Wolfers, Noah Smith, Claudia Sahm, Ritholtz, El-Erian, Furman, Dean Baker, Bernstein, Politano, Timiraos, Yglesias (tat), Chinn, DeLong (tat), Konczal, Casselman, Conor Sen, Matt Levine, Blyth (tat), Varoufakis (tat), Ed Conway, Robin Brooks, Pettis. Chi tiet prior/ly do trong YAML.
Ung vien da test nhung loai vi khong dang bai trong >60 ngay hoac khong co bai: Krugman nay chi dang thua (2026-08), Betsey Stevenson (2026-06), Larry Summers (2025-07), Heather Long (2025-04), Neil Irwin (2025-07), Martin Wolf (2025-05), Adam Tooze (2025-12), Skanda Amarnath/Employ America (2026-01/04), Isabel Schnabel (2025-05), BoE research (2026-07), Bank of England `bankofengland.bsky.social` (0 bai), OECD, Tracy Alloway, Torsten Slok, Tyler Cowen, Damodaran (0 bai), Weisenthal (2026-07), Jim Bianco (2026-03).

### Reddit (type=reddit, mac dinh TAT)
- `r/economics/.rss`: OK, 25 entry. Chat luong thap, prior 0.2.
- `r/SecurityAnalysis/.rss`: khong kiem duoc (HTTP 429 do rate limit). prior 0.25.
- Reddit gioi han ~1 req/phut/UA va chan nhieu IP datacenter; neu thuong mai hoa phai dung API chinh thuc/OAuth theo dieu khoan Reddit.

### YouTube (type=youtube, TAT toan bo)
Ngay 2026-10-12 `https://www.youtube.com/feeds/videos.xml?channel_id=<id>` tra **HTTP 404 voi moi kenh**, ke ca kenh Google (UC_x5XG1OV2P6uZZ5FSM9Ttw) va tu ca VPS lan may local; `?user=` va `playlist_id=` cung 404. Co the YouTube da go/loi tam thoi endpoint RSS. channel_id duoi day da xac minh tu trang kenh (`/@handle`, truong `externalId`) nhung CHUA kiem duoc feed. 37 kenh: Fed, ECB, BoE, Bundesbank, SNB, RBA, Fed St. Louis, IMF, World Bank, OECD, PIIE, CFA, Bridgewater, Reuters, CNBC (2), FT, Economist, WSJ, Real Vision, Forward Guidance, Macro Compass, Damodaran, Plain Bagel, Patrick Boyle, Wealthion, Kitco, George Gammon, cung VTV24, VTV Tai chinh, VnEconomy, VNDIRECT, Vietcap, KBSV, KIS VN, HOSE, HNX. Kenh VN can nguoi xac nhan danh tinh chinh thuc truoc khi bat (handle ngan de bi chiem).
Khong dua vao do handle khong ra kenh dung: Bloomberg TV (handle tro sai kenh), MacroVoices YT, CafeF, SSI, HSC, MBS, VDSC (khong tim duoc kenh chinh thuc xac minh). Khong dung Invidious/Piped (ben thu ba, khong chinh thuc).
Huong xu ly neu van 404: dung YouTube Data API v3 (khoa mien phi, 10k don vi/ngay; playlistItems 1 don vi) lam provider `youtube_api`, hoac chi dung podcast RSS cua cung to chuc.

### Mastodon (chua co nguon)
Tim tren mastodon.social/econtwitter.net: cac tai khoan kinh te hoc deu bo hoang tu 2023; con hoat dong chi la bot Flipboard (dieu khoan khong ro), Threads bridge, `ecb@respublicae.eu` (cuoi 2026-08-18, RSS chua kiem duoc). Khong them nguon Mastodon; neu sau nay can, RSS dang `https://<instance>/@user.rss` (404 voi hau het ung vien da thu).

### X/Twitter, TradingView
Khong dung: khong co API mien phi hop le (X); TradingView ideas bi ToS cam scrape.

## Dieu khoan
- Bluesky: AppView cong khai `public.api.bsky.app` doc khong can xac thuc, du lieu AT Protocol cong khai; gioi han ~3000 req/5 phut/IP. Dat UA ro rang, poll >=15 phut. Khong luu lai/ban lai noi dung day du; chi hien tieu de + link goc.
- Podcast RSS: feed cong khai do nha xuat ban cung cap de nghe/dong bo; chi doc metadata.
- YouTube: RSS la tinh nang cong khai nhung hien 404; khong tai video; neu dung API phai theo YouTube API ToS.
- Reddit: tuan thu rate limit/UA; chi lam tin hieu chu de.

## Dac ta provider Bluesky (cho agent dieu phoi cai dat)
- `GET https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=<handle>&filter=posts_no_replies&limit=20` (khong auth, header `User-Agent: MarketMonitor/1.0 (contact)`).
- Phan hoi: `{"feed":[{"post":{"uri","cid","author":{"handle","displayName"},"record":{"text","createdAt","embed":{"external":{"uri","title","description"}}},"embed"?:{"external":{...}}}, "reason"?:{repost}}], "cursor"}`.
- Chuan hoa: bo muc co `reason` (repost) hoac `post.author.handle != handle`; `title` = `embed.external.title` neu co, nguoc lai 140 ky tu dau `record.text`; `url` = `embed.external.uri` neu co, nguoc lai `https://bsky.app/profile/<handle>/post/<rkey cuoi cua uri>`; `published` = `record.createdAt`; `summary` = `embed.external.description` hoac text; dedupe theo `uri`.
- Loi/giam toc: 429 -> backoff theo `RateLimit-Reset`; 400 (handle sai) -> disable source. Chi can poll >=15 phut/handle.
- Provider `youtube` can dung `channel_id`; hien vo hieu hoa do 404 (xem tren).
