# Nguồn chuyên gia / nhận định Việt Nam

Kiểm tra thật 2026-10-12 từ VPS <VPS_IP> (container tạm, UA `trading-system/0.1 (contact: <OWNER_EMAIL>)`, robots.txt đã tra bằng urllib.robotparser). Cấu hình: `services/expert-collector/config/sources.d/vietnam.yaml` (47 mục: 46 bật, 1 tắt).

Ghi chú chung: cột "mục" là số bài trong feed; ngày = bài mới nhất. Chỉ lấy tiêu đề + link + ngày + tóm tắt ngắn. IP VPS (nước ngoài) bị chặn/timeout ở một số trang VN: ghi nhận ở bảng "Không dùng".

## 1. Dùng được: RSS (đã parse bằng feedparser)

| Nguồn (id yaml) | URL | HTTP / định dạng / mục / mới nhất | robots | Dùng |
|---|---|---|---|---|
| vn_vs_expert_opinion | vietstock.vn/145/chung-khoan/y-kien-chuyen-gia.rss | 200 RSS 20 · 10-11 | ok | có |
| vn_vs_market_view | vietstock.vn/1636/.../nhan-dinh-thi-truong.rss | 200 RSS 20 · 10-11 | ok | có |
| vn_vs_fundamental | vietstock.vn/582/.../phan-tich-co-ban.rss | 200 RSS 20 · 10-01 | ok | có (ít bài) |
| vn_vs_technical | vietstock.vn/585/.../phan-tich-ky-thuat.rss | 200 RSS 20 · 10-12 | ok | có |
| vn_vs_hot_stocks | vietstock.vn/830/chung-khoan/co-phieu.rss | 200 RSS 20 · 10-12 | ok | có |
| vn_vs_macro | vietstock.vn/761/kinh-te/vi-mo.rss | 200 RSS 20 · 10-12 | ok | có |
| vn_vs_intl_finance | vietstock.vn/772/the-gioi/tai-chinh-quoc-te.rss | 200 RSS 20 · 10-10 | ok | có |
| vn_vs_bond | vietstock.vn/785/chung-khoan/thi-truong-trai-phieu.rss | 200 RSS 20 · 10-12 | ok | có |
| vn_vs_gold | vietstock.vn/759/hang-hoa/vang-va-kim-loai-quy.rss | 200 RSS 20 · 10-10 | ok | có |
| vn_vs_fuel | vietstock.vn/34/hang-hoa/nhien-lieu.rss | 200 RSS 20 · 10-12 | ok | có |
| vn_vs_world_stocks | vietstock.vn/773/the-gioi/chung-khoan-the-gioi.rss | 200 RSS 20 · 10-11 | ok | có |
| vn_cf_stock_market | cafef.vn/thi-truong-chung-khoan.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_cf_macro | cafef.vn/vi-mo-dau-tu.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_cf_banking | cafef.vn/tai-chinh-ngan-hang.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_cf_intl_finance | cafef.vn/tai-chinh-quoc-te.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_ve_stock | vneconomy.vn/chung-khoan.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_ve_finance | vneconomy.vn/tai-chinh.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_ve_banking | vneconomy.vn/tai-chinh-ngan-hang.rss | 200 RSS 50 · 10-08 | ok | có |
| vn_ve_world | vneconomy.vn/kinh-te-the-gioi.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_vne_business | vnexpress.net/rss/kinh-doanh.rss | 200 RSS 60 · 10-12 | ok | có (keywords_only) |
| vn_tt_business | tuoitre.vn/rss/kinh-doanh.rss | 200 RSS 50 · ngày dạng M/D/Y 12h | ok | có (keywords_only) |
| vn_tn_stock | thanhnien.vn/rss/kinh-te/chung-khoan.rss | 200 RSS 50 · 10-10 | ok | có |
| vn_tn_banking | thanhnien.vn/rss/kinh-te/ngan-hang.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_dt_business | dantri.com.vn/rss/kinh-doanh.rss | 200 RSS 100 · 10-12 | ok | có (keywords_only) |
| vn_vnp_economy | vietnamplus.vn/rss/kinhte-91.rss | 200 RSS 50 · 10-12 (gzip ngầm) | ok | có |
| vn_vnp_stock | vietnamplus.vn/rss/chungkhoan-110.rss | 200 RSS 50 · 10-12 (gzip ngầm) | ok | có |
| vn_nd_stock | nhandan.vn/rss/chungkhoan-1191.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_nd_economy | nhandan.vn/rss/kinhte-1185.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_tp_economy | tienphong.vn/rss/kinh-te-3.rss | 200 RSS 50 · 10-12 | ok | có (keywords_only) |
| vn_tp_stock | tienphong.vn/rss/kinh-te-tai-chinh-ngan-hang-chung-khoan-48.rss | 200 RSS 50 · 10-12 | ok | có |
| vn_vtv_economy | vtv.vn/rss/kinh-te.rss | 200 RSS 500 · ngày TZ "+07" | ok | có (keywords_only) |
| vn_vov_economy | vov.vn/rss/kinh-te.rss | 200 RSS 30 · 10-12 | ok | có |
| vn_ndh_finance | ndh.vn/feed | 200 RSS 10 · 10-02 | ok | có (ít bài) |
| vn_ct_finance / vn_ct_energy | congthuong.vn/rss/tai-chinh.rss, /rss/nang-luong.rss | 200 RSS 25 · build 10-09 | ok | có |
| vn_vnn_business | vietnamnet.vn/kinh-doanh.rss | 200 RSS 1000 · 10-12 | ok | có (keywords_only) |
| vn_vir_business | vir.com.vn/rss_feed/ | 200 RSS 25 · 10-12 (EN) | ok | có |
| vn_gov_stock / vn_gov_economy / vn_gov_policy | baochinhphu.vn/chung-khoan.rss, /kinh-te.rss, /chinh-sach-moi.rss | 200 RSS 50 · ngày M/D/Y 12h | ok | có |
| vn_nso_news / vn_nso_stats_news | nso.gov.vn/feed/, /tin-tuc-thong-ke/feed/ | 200 RSS 10 · 10-12 | ok | có |

Lưu ý parse (cho loader): (1) `tuoitre.vn`, `baochinhphu.vn` dùng `M/D/YYYY h:mm:ss AM/PM`; `vtv.vn`, `soha` dùng TZ `+07` -> feedparser trả null ngày, cần parse tay hoặc dùng thời điểm lấy. (2) `vietnamplus.vn` trả gzip không khai báo header -> nếu 2 byte đầu = 1f8b thì giải nén. (3) `thanhnien.vn` tiêu đề chứa entity (`&aacute;`) -> html.unescape. (4) VTV 500 mục / VietnamNet 1000 mục -> cắt 50 mới nhất.

## 2. Dùng được: trang danh sách HTML (`type: html_list`, cần provider mới)

Tất cả HTTP 200, robots ok, nội dung render server-side (không cần JS). Chỉ lấy tiêu đề + link + ngày.

| id | Trang list | Selector / parse | Ghi chú |
|---|---|---|---|
| vn_vcsc_research | vietcap.com.vn/trung-tam-phan-tich | `a[href^="/trung-tam-phan-tich/"]`, bỏ link có `?page=` và 8 link chuyên mục (`phan-tich-doanh-nghiep`, `bao-cao-nganh`, `nhan-dinh-thi-truong`, `bao-cao-trai-phieu-tien-te`, `bao-cao-vi-mo`, `bao-cao-chien-luoc-dau-tu`, `y-kien-chuyen-gia`, `phan-tich-ky-thuat`). Text = tiêu đề + chuyên mục + `dd/mm/yyyy` dính liền (regex `(\d{2}/\d{2}/\d{4})` cuối). Khuyến nghị trong tiêu đề (`PLX [MUA +25,1%]`). | Trung tâm phân tích Vietcap (VCSC): 1489 trang, 10 mục/trang -> chỉ lấy trang 1 |
| vn_vdsc_daily | vdsc.com.vn/trung-tam-phan-tich/nhan-dinh-hang-ngay | `a[href^="/data/api/app/file-storage/"]`; text `DD tháng M - YYYY <tiêu đề>` + số lượt xem dính cuối (bỏ `\d+$`). Link tuyệt đối = `https://www.vdsc.com.vn` + href. | Bản tin sáng PDF công khai. Trang `bao-cao-chien-luoc`/`doanh-nghiep`/`bao-cao-chuyen-de` link qua `/dang-nhap?returnUrl=` = cần đăng nhập -> không dùng |
| vn_phs_daily | phs.vn/trung-tam-phan-tich | `a[href^="/trung-tam-phan-tich/ban-tin-ngay-"]`; id cuối slug (`/4788`), ngày từ slug `ban-tin-ngay-DD-MM-YYYY`; text "Bản tin ngày DD.MM.YYYY - <nhận định>" | 1 bản tin/phiên |
| vn_shs_daily | shs.com.vn/trung-tam-phan-tich (redirect 1 lần) | `a[href^="/nhan-dinh-thi-truong/"]`; text `dd/mm/yyyy` + tiêu đề dính liền | bản tin ngày + tuần |

## 3. Tắt (giữ ghi nhận)

| Nguồn | URL | Kết quả | Lý do |
|---|---|---|---|
| VinaCapital insights (vn_vinacapital_insights, `enabled: false`) | vinacapital.com/insights/feed/ | 200 RSS 10 · mới nhất 2026-06-22 | >60 ngày; bật lại khi có bài mới |

## 4. Không dùng

| Nguồn | URL thử | Kết quả | Lý do |
|---|---|---|---|
| VNDirect | vndirect.com.vn (/, /feed/, /category/bao-cao-phan-tich/) | 403 | WAF chặn IP VPS |
| VPBankS | vpbanks.com.vn | 403 | WAF |
| Yuanta VN | yuanta.com.vn | 200 "Attention Required" (Cloudflare challenge) | bot-check, không vượt |
| BVSC | bvsc.com.vn | 200 "Attention Required" | bot-check |
| Manulife IM VN | manulifeim.com.vn | 403 | WAF |
| Ngân hàng Nhà nước | sbv.gov.vn trang chủ 200 nhưng `/vi/tin-ngan-hang`, `/vi/tin-tuc-su-kien`, `sitemap.xml` 403; không có RSS (/rss 404) | WAF chặn trang tin | dùng gián tiếp qua `vn_cf_banking`, `vn_vs_*` |
| HSC | hsc.com.vn/vi/bao-cao-phan-tich | 200 nhưng báo cáo dẫn tới `research-center/logon` | cần đăng nhập |
| SSI Research | ssi.com.vn | trang chủ 200; các URL research thử đều 404; trang SPA | không tìm được trang list công khai |
| MBS | mbs.com.vn/feed/ | 200 RSS 10 nhưng toàn thông báo giao dịch (tính quyền cổ phiếu), `category/phan-tich/feed/` 0 mục | không có nhận định |
| TCBS / ACBS | tcbs.com.vn/feed/, acbs.com.vn/feed | 200 RSS 10 nhưng là thông báo margin/cổ tức | không phải nhận định |
| BSC | bsc.com.vn/en/feed/ (0 mục), /feed/ (1 mục từ 2024-06) | 200 | feed chết; site chính đôi lúc reset kết nối |
| Agriseco | agriseco.com.vn/Report/ReportsInCategory/{id}/vi-VN | 200 (không www; www lỗi SSL EOF) nhưng HTML list trống ở bản server-render (65 link lẫn menu) | chưa xác định được selector ổn định; thử lại sau |
| KBSV | kbsec.com.vn/vi/bao-cao-*.htm | 200 nhưng danh sách báo cáo nạp bằng JS (không thấy mục) | cần JS |
| Mirae Asset VN | masvn.com | 200 SPA, không có trang list công khai | |
| FPTS | fpts.com.vn/ho-tro-khach-hang/tu-van-dau-tu/bao-cao-tu-van/ | 200 nhưng không có link báo cáo trong HTML | cần JS/đăng nhập |
| VCBS | vcbs.com.vn | 200 trang stub 11,9 KB (frame) | không có list |
| HNX, VSDC, VietinbankSC, Mekong Capital, VEPR, vnu.edu.vn | hnx.vn, vsd.vn, mekongcapital.com, vepr.org.vn | lỗi `CERTIFICATE_VERIFY_FAILED` | chuỗi chứng chỉ không hợp lệ, không bỏ qua verify |
| HOSE | hsx.vn | 200 trang stub 1,9 KB; `/vi` timeout | không có list công khai |
| UBCKNN | ssc.gov.vn | 302; đường dẫn tin 404 | không tìm được feed |
| Bộ Tài chính | mof.gov.vn | 200 trang stub 2 KB (portal JS) | |
| CIEM | ciem.org.vn/feed | 200 RSS nhưng nội dung spam (bán đất) | site bị lạm dụng |
| Dragon Capital | dragoncapital.com/feed/ 500; /insights/ chuyển sang dịch vụ ngoài; `/institutional/category/dc-insights` có list HTML (bài tháng, ~1 bài/tháng, bài mới nhất thấy là 11/2025) | | cũ/ít, bỏ |
| Eastspring VN, PYN Elite, VCCI (không RSS), FiinGroup (không RSS/insights), Thông tin Giá (qlg.mof.gov.vn bảo trì), Forbes VN | timeout / DNS fail / 404 / không feed | | không truy cập được từ VPS |
| Tạp chí Tài chính, TBKTSG (thesaigontimes.vn), Nhịp cầu đầu tư, Đầu tư chứng khoán | tapchitaichinh.vn RSS 410; thesaigontimes.vn chuyển sang tuoitre.vn; nhipcaudautu.vn /rss là trang HTML không link feed; baodautu.vn/*.rss hợp lệ nhưng 0 mục (channel rỗng) | | không có feed dùng được |
| F319 và diễn đàn NĐT | chưa kiểm tra | | chất lượng thấp, mặc định TẮT; không thêm |

## 5. Việc cho agent điều phối
1. Cài provider `html_list` với 4 mục ở mục 2 (cấu hình selector theo bảng; mỗi nguồn 1 hàm parse nhỏ hoặc thêm khóa `selector`/`date_regex` vào loader).
2. Provider RSS cần: giải nén gzip ngầm, parse ngày M/D/Y 12h và TZ `+07`, `html.unescape` tiêu đề, giới hạn 50 mục.
3. Các nguồn `keywords_only: true` là chuyên mục chung (báo tổng hợp) nên lọc từ khóa tài chính.
