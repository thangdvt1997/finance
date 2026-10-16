# Nghiên cứu: loại thông tin nào thực sự có giá trị cho quyết định giao dịch

Ngày: 2026-10-11. Phạm vi: hệ thống READ-ONLY đang thu thập tin, lịch kinh tế, COT, 13F, tín hiệu chuyên gia. Tài liệu này KHÔNG phải khuyến nghị đầu tư. Mã và dữ liệu kiểm chứng nằm ở `research/info/` (tái lập được, xem mục 7).

Quy ước mức chắc chắn: **Cao** = nhiều nguồn độc lập nhất quán hoặc tôi tự đo được; **Trung bình** = có bằng chứng học thuật nhưng mẫu/thời kỳ hạn chế hoặc tôi chỉ đọc tóm tắt; **Thấp** = chủ yếu giai thoại/quảng cáo/luận văn nhỏ; **Chưa biết** = không tìm được bằng chứng độc lập.

---

## 1. Tóm tắt điều hành (đọc phần này nếu chỉ có 2 phút)

1. **Có giá trị thật nhất: thông tin dùng để QUẢN LÝ RỦI RO, không phải để dự đoán hướng giá.** Tôi đo trực tiếp trên nến M1 (EURUSD, GBPUSD, USDJPY, vàng; 6 NFP + 4 FOMC năm 2026): biên độ 5 phút đầu sau tin gấp trung bình **7 lần (NFP)** và **10 lần (FOMC)** so với cùng giờ ở các ngày thường; cần trung vị ~**22-25 phút** để biên độ từng phút trở lại ≤ 2 lần bình thường. Một "bộ lọc rủi ro tin" (không mở lệnh, thu hẹp/dời stop) dựa trên lịch kinh tế đã thu thập là tính năng có lợi ích rõ nhất và rẻ nhất.
2. **COT (vị thế đầu cơ) KHÔNG cho thấy tín hiệu đảo chiều/theo xu hướng dùng được**: 52 kiểm định (7 tài sản × 2 nhóm trader × 2 ngưỡng × 2 kỳ hạn, 2006-2026, đúng thời điểm công bố), **không kiểm định nào sống sót sau hiệu chỉnh đa kiểm định** (q nhỏ nhất = 0,43; Holm nhỏ nhất = 0,44). Dấu của hiệu ứng đổi chiều giữa các tài sản và giữa 2006-15 với 2016-26. Dùng COT làm **bối cảnh** (mức đông đúc), không làm tín hiệu vào lệnh.
3. **Không thể kiểm chứng sentiment/"surprise" với dữ liệu hiện có** — và đây là phát hiện về hệ thống: bảng `calendar_events` có **0/372 dòng có `actual` hoặc `forecast`** (chỉ 1 dòng có `previous`), bảng `news_items` có **0/1070 dòng có `sentiment`**, và 59% số tin dồn vào 11 ngày gần nhất. Không có "surprise = actual − consensus" để dùng.
4. **Kém giá trị nhất khi dùng làm tín hiệu vào lệnh**: tín hiệu chuyên gia/copy-trading công khai (thiên lệch sống sót, rủi ro martingale/grid, không có bằng chứng độc lập về lợi nhuận của người theo sau), retail sentiment (chưa có kiểm chứng độc lập; nguồn thu thập chính thức thì bị chặn/cần tài khoản) và tin tức thô (nhiễu cao, alpha giảm khi nhiều người dùng).
5. Cổ phiếu Mỹ: **mua của insider (Form 4, nhất là giao dịch "cơ hội")** có bằng chứng học thuật mạnh nhất trong nhóm "theo dấu người trong cuộc"; 13F có độ trễ tới 45 ngày nên chỉ hợp làm danh sách theo dõi/ý tưởng dài hạn.
6. Việt Nam: tôi **không tìm được nghiên cứu độc lập chứng minh dòng tiền khối ngoại/tự doanh có sức dự báo**; có bằng chứng sự kiện (event study) ở nhóm ngân hàng. Giữ ở mức "dữ liệu bối cảnh" cho đến khi tự kiểm chứng.

---

## 2. Bảng tổng hợp: loại thông tin → bằng chứng → cách dùng đúng → mức chắc chắn

| Loại thông tin | Bằng chứng (tóm tắt) | Cách dùng đúng | Mức chắc chắn |
|---|---|---|---|
| **Lịch kinh tế (thời điểm sự kiện)** — NFP, CPI, FOMC, ECB… | Tin vĩ mô làm giá nhảy và biến động tăng vọt quanh giờ công bố (Andersen et al. 2003; tự đo: 5 phút đầu ×7-×10 so với ngày thường). Hiệu ứng sau tin kéo dài vài chục phút. | **Bộ lọc rủi ro**: chặn mở lệnh mới quanh tin, nới/dời stop, giảm cỡ lệnh. Không dùng để "đoán hướng". | **Cao** (đo trực tiếp + văn liệu); lưu ý mẫu 10 sự kiện |
| **"Surprise" (actual − consensus)** | Học thuật: surprise làm dịch chuyển giá trung bình, phản ứng với tin xấu mạnh hơn tin tốt (Andersen et al. 2003). Phần lớn tác động đi qua order flow (Evans–Lyons). Nhưng khoảng thời gian có thể khai thác là vài giây–phút, cần dữ liệu consensus + tốc độ. | Chỉ có ý nghĩa nếu có consensus đáng tin và độ trễ thấp. Với hệ thống hiện tại (không có consensus, thu thập theo phút–giờ) **không khai thác được**. | Cao về hiện tượng; **Thấp** về khả năng khai thác bán lẻ |
| **Giao dịch tin trực tiếp (straddle/scalp)** | Không tìm thấy nghiên cứu độc lập chứng minh có lãi sau chi phí; nguồn chỉ là môi giới/diễn đàn. Spread giãn và trượt giá là cơ chế đã biết, nhưng tôi **không đo được spread** (xem 5.2). | Mặc định **tránh** và dùng như bộ lọc. Chỉ xem xét khai thác nếu đo được spread/trượt giá thật trên broker của bạn. | **Thấp** (thiếu dữ liệu chi phí) |
| **COT / TFF vị thế đầu cơ** | NY Fed (Klitgaard–Weir 2004): vị thế liên quan đồng thời tới giá trong tuần nhưng không dự báo tuần sau. Tự kiểm: 52 kiểm định, không cái nào sống sót hiệu chỉnh; dấu không ổn định. | Chỉ làm **ngữ cảnh/cảnh báo đông đúc** (percentile 3 năm), không làm lệnh. Nhớ độ trễ: dữ liệu thứ Ba, công bố thứ Sáu 15:30 ET. | **Trung bình-Cao** (cho kết luận "không có edge") |
| **Sentiment tin tức/NLP** | Tetlock 2007, Ke–Kelly–Xiu 2019: có dự báo trên cổ phiếu Mỹ, mạnh ở cổ phiếu nhỏ và tin xấu; Lopez-Lira & Tang: lợi suất giảm khi nhiều người dùng LLM; lo ngại rò rỉ bộ nhớ/look-ahead trong mô hình LLM. Không có bằng chứng tương tự độc lập cho cặp FX bán lẻ. | Dùng làm **bộ lọc ngữ cảnh/đếm sự kiện** (ví dụ cờ "nhiều tin tiêu cực về cặp này"), không tin điểm số đơn lẻ. Muốn dùng làm tín hiệu phải tự backtest ngoài mẫu, trừ phí. | **Trung bình** (cổ phiếu), **Thấp** (FX) |
| **Retail sentiment / contrarian** (OANDA, IG, Myfxbook) | Không có nghiên cứu đồng nghiệp xét duyệt kiểm tra dự báo của tỷ lệ vị thế do broker công bố. Có bằng chứng gián tiếp: dòng lệnh bán lẻ FX ngược chiều giá gần đây và thông tin kém. 74-89% tài khoản CFD lẻ lỗ (ESMA 2018, tổng CFD). | Chỉ **ngữ cảnh** khi tỷ lệ cực đoan; không phải tín hiệu độc lập. Nguồn công khai ổn định gần như không có (OANDA cần token, Myfxbook bị Cloudflare chặn). | **Thấp** |
| **Tín hiệu chuyên gia công khai** (RSS nhận định, ý tưởng) | Không có bằng chứng độc lập về độ chính xác; điểm "uy tín" của feed chỉ phản ánh nhà xuất bản. | Làm **bảng đồng thuận có trọng số** để thấy quan điểm đa số và mức bất đồng; không đặt lệnh theo. | **Thấp** |
| **Copy-trading (MQL5, ZuluTrade, eToro)** | Không tìm thấy nghiên cứu độc lập đo lợi nhuận của người theo sau sau phí. Thí nghiệm (Apesteguia et al. 2020): sao chép làm người ta chấp nhận rủi ro cao hơn. Thiên lệch sống sót và martingale/grid được nêu ở nguồn thực hành. | Chỉ dùng như **dữ liệu quan sát có cảnh báo** (heuristic martingale/grid, drawdown vốn, nạp tiền khi lỗ). Không coi thứ hạng là bằng chứng kỹ năng. | **Thấp** |
| **Insider (Form 4) — cổ phiếu Mỹ** | Lakonishok–Lee 2001: thông tin nằm ở lệnh mua (nhất là công ty nhỏ). Cohen–Malloy–Pomorski 2012: chỉ nhóm "opportunistic" có alpha (~82 điểm cơ bản/tháng giá trị-trọng số, mẫu 1986-2007), nhóm "routine" ≈ 0. | Nếu có mở rộng sang cổ phiếu Mỹ: lọc **mua mở thị trường, không theo lịch (opportunistic)**, công ty vốn hóa nhỏ; độ trễ 2 ngày làm việc. | **Trung bình** (mẫu lịch sử; chưa kiểm lại gần đây) |
| **13F (độ trễ ≤ 45 ngày)** | "Best ideas" (Cohen–Polk–Silli): cổ phiếu tin tưởng nhất của quỹ vượt thị trường. Copycat quỹ tương hỗ cho hiệu suất tương đương gốc sau chi phí (Verbeek–Wang 2013). 13F không có vị thế bán, độ trễ làm mất phần lớn lợi thế với quỹ quay vòng nhanh. | Danh sách theo dõi dài hạn/ý tưởng, ưu tiên quỹ tập trung–ít quay vòng. Không dùng cho vào lệnh ngắn hạn. | **Trung bình-Thấp** |
| **Việt Nam: khối ngoại, tự doanh, tin doanh nghiệp** | Chỉ tìm thấy event study ngân hàng 2006-2023 (mua/bán bất thường của khối ngoại đi kèm lợi suất bất thường cùng chiều) và VAR tuần (khối ngoại hầu như không lan sang tự doanh). Không có kiểm tra dự báo độc lập. | Hiển thị làm **bối cảnh**; muốn dùng làm tín hiệu thì tự kiểm chứng bằng dữ liệu HOSE hằng ngày (lag ≥ 1 ngày). | **Thấp-Chưa biết** |

---

## 3. PHẦN A — Văn liệu (2015-2026 là chính; một số bài nền tảng cũ hơn)

**Giới hạn trung thực**: tôi dùng tìm kiếm web và đọc **tóm tắt/trang kết quả**, không đọc toàn văn từng bài. Mỗi nhận định dưới đây gắn URL để bạn kiểm tra. Các con số mà nguồn không thể xác minh được đánh dấu rõ.

### 3.1 Phản ứng giá với tin kinh tế và hiệu quả giao dịch tin

- **Nền tảng**: Andersen, Bollerslev, Diebold, Vega (2003, AER) — dùng 6 năm báo giá FX thời gian thực cùng kỳ vọng và thực tế: surprise tạo bước nhảy trong giá trung bình; **tin xấu tác động mạnh hơn tin tốt** (bất đối xứng); hiệu ứng phụ thuộc thời điểm. https://www.nber.org/system/files/working_papers/w8959/w8959.pdf · https://papers.ssrn.com/abstract=313660
- **Cơ chế**: Evans & Lyons — khoảng một nửa đến hai phần ba tác động của tin vĩ mô lên tỷ giá đi qua order flow; mô hình order flow giải thích >50-60% biến thiên tỷ giá hằng ngày DEM/USD (mẫu cũ). https://www.nber.org/papers/w7317.pdf · https://www.nber.org/papers/w9433.pdf. Phản biện (Reitz–Schmidt–Taylor): order flow khách hàng không phải nguồn dự báo ngắn hạn dễ khai thác.
- **Thanh khoản**: FED IFDP 903 (EBS, FX liên ngân hàng): giá nhảy ngay lập tức khi tin ra mà gần như chưa có khối lượng; khối lượng và biến động vọt lên sau ~15 giây. https://www.federalreserve.gov/pubs/ifdp/2007/903/ifdp903.htm. **Tôi không tìm được nghiên cứu 2018-2024 nào đo trực tiếp spread FX quanh NFP**; chỉ có bình luận môi giới/diễn đàn (spread giãn, trượt 15-20 pip là giai thoại, không phải số đo): https://investinglive.com/Education/!/non-farm-payrolls-is-a-good-time-to-evaluate-a-broker-20160331/
- **Hiệu ứng NFP có suy giảm?** Luận văn MBA (Jandejsek 2021, **không xét duyệt**), 237 sự kiện NFP 2000-2020 trên EURUSD M1: mức tác động giảm liên tục 2017-2020 nhưng vẫn có ý nghĩa thống kê. https://web-typo3.modul.ac.at/uploads/files/Theses/Master/Grad_2021/MBA_2021/Master_Thesis_Jandejsek.pdf
- **Ví dụ "alpha biến mất sau công bố"**: pre-FOMC drift (Lucca–Moench) — Kurov–Wolfe–Gilbert (2021) mở rộng đến 2019: **hầu như biến mất sau 2015**; Boguth et al. 2019: chỉ ở cuộc họp có họp báo. https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf · https://fedinprint.org/item/fednls/87294. Không có bài nào chứng minh nhân quả do công bố nghiên cứu.
- **Hiệu quả giao dịch tin**: không tìm thấy nghiên cứu độc lập chứng minh chiến lược straddle/scalp tin có lãi sau chi phí; tài liệu môi giới thừa nhận biến động và trượt giá tăng quanh tin (https://pepperstone.com/en/learn-to-trade/trading-guides/what-is-slippage/). Một backtest EUR/USD ngày (không phải tin) cho thấy chỉ 1 điểm cơ bản trượt giá cũng xóa lợi nhuận: https://www.quantrocket.com/codeload/fx-bizday/fx_bizday/Part5-Parameter-Scans.ipynb — chỉ minh họa mức nhạy với chi phí.
- **Kết luận thực tế**: *tránh quanh tin* là mặc định hợp lý cho hệ thống này (không có consensus, không có tốc độ, không đo được chi phí). "Khai thác" chỉ nên đặt lại sau khi đo được spread/trượt giá thực trên tài khoản thật.

### 3.2 COT (vị thế đầu cơ)

- Dữ liệu: vị thế tính tại **thứ Ba**, công bố **thứ Sáu 15:30 ET** (độ trễ 3 ngày; chậm hơn khi nghỉ lễ). https://www.babypips.com/forexpedia/cot
- **NY Fed (Klitgaard & Weir, 2004)**: tuần có vị thế đầu cơ tăng thì tiền tệ mạnh lên cùng tuần (biết vị thế → đoán đúng hướng ~75% cho **cùng tuần**), nhưng **không giúp dự báo tuần sau**. https://www.newyorkfed.org/research/epr/04v10n1/0405klit/0405klit.html
- Luận văn Aalto: chiến lược đi ngược vị thế cực đoan có alpha ý nghĩa ở chỉ số chứng khoán (S&P E-mini, Nikkei) nhưng **chỉ lãi biên, không có ý nghĩa ở tiền tệ/năng lượng**. https://aaltodoc.aalto.fi/items/b84b07d6-3bd2-4040-bbcf-052b938b1f74 (luận văn, không xét duyệt)
- Lời khẳng định "cực đoan = đảo chiều" của các môi giới không kèm mẫu, kỳ hạn hay kiểm định. Kết quả tự kiểm ở mục 4.1 ủng hộ sự hoài nghi.

### 3.3 Sentiment tin tức / NLP / mạng xã hội

- Tetlock (2007, J. Finance): tần suất từ tiêu cực trong cột WSJ dự báo áp lực giảm giá rồi hồi về. https://www.columbia.edu/~pt2238/papers/Tetlock_Media_Sentiment_JF.pdf
- Ke–Kelly–Xiu (NBER 26186): điểm sentiment học có giám sát từ Dow Jones Newswires dự báo lợi suất, thông tin hấp thụ chậm, khai thác được sau chi phí trong mô phỏng. https://www.nber.org/papers/w26186
- Lopez-Lira & Tang (arXiv 2304.07619, bản mới nhất 2025): điểm ChatGPT tiêu đề dự báo lợi suất; mạnh ở cổ phiếu nhỏ và tin xấu; **lợi suất giảm khi LLM được dùng nhiều** (alpha decay do chính tác giả báo cáo). https://arxiv.org/abs/2304.07619v5 · Phản biện về rò rỉ tương lai/ghi nhớ trong LLM: https://arxiv.org/pdf/2512.23847 · Tổng quan 2026 về tính mong manh ngoài mẫu: https://arxiv.org/pdf/2605.05211 (preprint)
- Các bằng chứng này chủ yếu trên **cổ phiếu Mỹ**, không phải cặp FX; tôi không tìm được bằng chứng độc lập cho FX bán lẻ.

### 3.4 Retail sentiment / contrarian

- Không có nghiên cứu xét duyệt kiểm tra dự báo của tỷ lệ long/short công bố bởi IG/OANDA/Myfxbook. Công cụ của OANDA tự mô tả là để đi theo hoặc ngược đám đông (marketing): https://www.oanda.com/bvi-en/skills-and-insights/oanda-labs/sentiment/
- Gián tiếp: dòng lệnh FX bán lẻ giao dịch ngược chiều lợi suất gần đây (không do tin) và là thông tin kém: https://clok.uclan.ac.uk/55052 · bài về khách hàng OANDA FXTrade (kết quả chưa đọc): https://kops.uni-konstanz.de/server/api/core/bitstreams/f0e46283-5d68-402a-8fdd-93082a41cdcb/content · retail futures cũng vào lệnh ngược chiều giá: https://www.cftc.gov/node/249641
- ESMA 2018: 74-89% tài khoản CFD lẻ lỗ (tổng CFD, không riêng FX; Babypips tổng hợp 28 nhà cung cấp 2019: 54-83%, trung bình ~76%). https://www.babypips.com/news/almost-80-percent-of-retail-traders-are-unprofitable · số 74-89% (ESMA) qua https://rpclegal.com/thinking/financial-services-regulatory-and-risk/esma-cracks-down-on-the-sale-of-binary-options-and-cfds-to-retail-investors. Đây là bằng chứng "đa số lẻ lỗ", **không** chứng minh "làm ngược đa số thì có lãi".

### 3.5 Copy-trading, tín hiệu chuyên gia, 13F/insider

- **Copy-trading**: Apesteguia–Oechssler–Weidenholzer (2020, Management Science) — **thí nghiệm** cho thấy có thông tin thành tích người khác và tùy chọn sao chép làm tăng chấp nhận rủi ro, giảm phúc lợi kỳ vọng. https://focus.bse.eu/copy-trading-risk-taking/ . **Không có** ước tính độc lập lợi nhuận của người theo sau sau phí cho eToro/ZuluTrade/MQL5; nghiên cứu MIT–eToro 2012 (+6-10%) do nền tảng tài trợ, đo lợi nhuận gộp: https://www.financemagnates.com/forex/brokers/a-research-into-etoros-social-trading-shows-higher-returns/ . Cảnh báo ở nguồn thực hành: thống kê từ lệnh đã đóng che rủi ro martingale/grid (đường cong tăng đều rồi sụp), nạp tiền che drawdown, hồ sơ ngắn. https://www.mql5.com/en/articles/23673 · https://www.mql5.com/en/forum/192942 (nguồn thực hành, không xét duyệt). Các con số cụ thể kiểu "người theo −12%, 78% theo kịp" ở blog không kiểm chứng được — **bỏ qua**.
- **Insider/13F**: Lakonishok–Lee (2001, RFS): thông tin chủ yếu ở lệnh mua, công ty nhỏ; bán không dự báo. https://ideas.repec.org/a/oup/rfinst/v14y2001i1p79-111.html · Cohen–Malloy–Pomorski (NBER 16454): lệnh "opportunistic" cho alpha ~82 điểm cơ bản/tháng (trọng số giá trị; ~180 trọng số đều), "routine" ≈ 0. https://www.nber.org/papers/w16454.pdf · Với FTSE-350, hiệu ứng yếu hơn nhiều sau chi phí: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8886886/ .
- **13F**: độ trễ trung bình 37 ngày, ~30% nộp đủ/quá 45 ngày; lý do trì hoãn chủ yếu để tránh front-run và che quyền biểu quyết, **không phải** tránh bị sao chép (Christoffersen–Danesh–Musto). https://www.bwl.uni-mannheim.de/media/Lehrstuehle/bwl/Area_Finance/Finance_Area_Seminar/HWS2018/Christoffersen_Paper.pdf · "Best ideas": https://personal.lse.ac.uk/polk/research/BestIdeas.pdf · Copycat quỹ tương hỗ: https://ideas.repec.org/a/eee/jbfina/v37y2013i9p3454-3471.html (quỹ tương hỗ, không phải 13F hedge fund). Con số "vượt S&P ~4% (Barclays/Novus 2004-2015)" chỉ từ bài thứ cấp, **không xác minh được**.

### 3.6 Thông tin đặc thù Việt Nam

- Event study ngân hàng 2006-2023: mua bất thường của khối ngoại đi cùng lợi suất bất thường dương, bán bất thường làm giá giảm ngắn hạn rồi hồi: https://publisher.unimas.my/ojs/index.php/IJBS/article/view/9543 (đây là phản ứng cùng cửa sổ, **không phải** dự báo).
- VAR tuần (khối ngoại, nội, tự doanh, VN-Index): tác động của khối ngoại lên tự doanh rất nhỏ: https://vjol.info.vn/TC/article/view/111393 . VN30 2012-2022: giao dịch ròng của khối ngoại làm tăng thanh khoản, giảm biến động ngắn hạn: https://jeb.ueb.edu.vn/index.php/jeb/article/view/156
- Không bài nào kiểm tra "dòng tiền khối ngoại hôm nay dự báo lợi suất mai" với kiểm soát tự doanh. Phải tự kiểm chứng bằng dữ liệu HOSE hằng ngày nếu muốn dùng.

---

## 4. PHẦN B — Kiểm chứng định lượng (công khai, tái lập)

### 4.1 COT: "cực đoan positioning" có dự báo lợi suất sau không?

**Dữ liệu**: CFTC file lịch sử (https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm): TFF (Traders in Financial Futures, futures-only) cho EUR, GBP, JPY, AUD, CAD, CHF (CME) — nhóm *Leveraged Funds* và *Asset Managers*; Disaggregated cho vàng COMEX — nhóm *Managed Money*; 2006-06 → 2026-10-06. Giá ngày: Yahoo Finance (EURUSD, GBPUSD, AUDUSD, USDJPY, USDCAD, USDCHF, vàng GC=F).

**Phương pháp**
- Vị thế ròng chuẩn hóa = (long − short)/open interest. Percentile = vị trí của tuần này trong **156 tuần trước đó** (chỉ dùng quá khứ, tối thiểu 104 tuần).
- Tín hiệu "đi ngược cực đoan": percentile ≥ 90% (hoặc 80%) → bán; ≤ 10% (hoặc 20%) → mua (futures CAD/CHF/JPY quy về cùng chiều "đồng ngoại tệ so với USD").
- **Không look-ahead**: vị thế đo thứ Ba, công bố thứ Sáu 15:30 ET → vào lệnh ở **giá đóng cửa thứ Hai kế tiếp** (thận trọng; dữ liệu giá ngày của Yahoo không cho phép khớp chính xác giờ công bố), giữ 1 tuần hoặc 4 tuần. Biến thể "naive" (vào đóng cửa thứ Ba, look-ahead) chỉ để so sánh.
- Thống kê: trung bình lợi suất log trên các tuần có tín hiệu; khoảng tin cậy 95% bằng **stationary bootstrap** (khối trung bình 8 tuần, xử lý chồng lấn và tự tương quan); p tính trên phân phối đã căn tâm; **hiệu chỉnh đa kiểm định (Benjamini–Hochberg và Holm) trên cả họ 52 kiểm định**; tách mẫu 2006-15 và 2016-26. Bỏ qua lãi qua đêm (carry) và chi phí.

**Kết quả (2006-2026, vào thứ Hai, ngưỡng đã nêu)**

| Thống kê | Giá trị |
|---|---|
| Số kiểm định trong họ | 52 |
| Số p thô < 0,05 | 4 (kỳ vọng ngẫu nhiên ≈ 2,6) |
| p thô nhỏ nhất | 0,0085 (CAD, Leveraged Funds, 1 tuần, ngưỡng 20%: +0,11%/tuần, n=381) |
| q (BH) nhỏ nhất | **0,426** |
| p Holm nhỏ nhất | **0,442** |
| Số tài sản có trung bình "đi ngược" < 0 (ngưỡng 10%, 4 tuần) | 4/6 (Leveraged), 3/6 (Asset Managers) — tức vị thế cực đoan **hay tiếp diễn** hơn đảo chiều ở một nửa số cặp, và ngược lại ở nửa kia |

Một số hàng tiêu biểu (ngưỡng 10%, trung bình trên tuần có tín hiệu, KTC 95% bootstrap; âm = vị thế cực đoan tiếp diễn thay vì đảo chiều):

| Tài sản / nhóm | Kỳ hạn | n | Trung bình | KTC 95% | p thô | q (BH) |
|---|---|---|---|---|---|---|
| EUR / Leveraged | 4 tuần | 210 | −0,66% | [−1,32%; +0,04%] | 0,061 | 0,43 |
| AUD / Asset Mgr | 4 tuần | 300 | −0,86% | [−1,67%; −0,11%] | 0,030 | 0,43 |
| CAD / Asset Mgr | 4 tuần | 318 | +0,38% | [+0,02%; +0,77%] | 0,051 | 0,43 |
| Vàng / Managed Money | 4 tuần | 279 | −0,36% | [−1,22%; +0,63%] | 0,447 | 0,85 |
| GBP / Leveraged | 4 tuần | 173 | −0,01% | [−0,82%; +0,71%] | 0,971 | 0,98 |

(Bảng đầy đủ 52 hàng: `research/info/out/cot_family_adjusted.csv`; toàn bộ biến thể: `cot_contrarian_raw.csv`.)

**Diễn giải**
- Không có bằng chứng nào cho "COT cực đoan → đảo chiều" **hay** "→ tiếp diễn" đủ mạnh để sống sót sau hiệu chỉnh. AUD nghiêng về tiếp diễn, CAD nghiêng về đảo chiều — dấu không nhất quán, giống nhiễu.
- Tách mẫu: ở nhiều hàng dấu **đổi** giữa 2006-15 và 2016-26 (ví dụ AUD Asset Mgr 4 tuần: −1,96% rồi −0,20%; CHF Asset Mgr 4 tuần: −0,29% rồi +0,39%); hiệu ứng lớn ở mẫu đầu suy giảm gần như về 0 ở mẫu sau — đúng dạng "alpha biến mất".
- Look-ahead (vào thứ Ba) so với đúng thời điểm (thứ Hai) chênh dưới ~0,2 điểm phần trăm: khoảng trễ 3 ngày không phải nguồn chênh lệch lớn, nhưng đó là vì không có tín hiệu để mất.
- Kích cỡ mẫu hiệu dụng nhỏ hơn n rất nhiều (tín hiệu tự tương quan, chồng lấn 4 tuần). Bootstrap khối đã tính đến phần lớn điều này.

**Kết luận**: không dùng COT làm tín hiệu vào lệnh. Có thể dùng như bối cảnh "vị thế đông đúc" (rủi ro thanh lý/biến động) — nhưng bước đó **chưa được kiểm chứng** ở đây.

### 4.2 Lịch kinh tế: biên độ quanh tin và bộ lọc rủi ro

**Dữ liệu**: Dukascopy (`datafeed.dukascopy.com`) **không truy cập được** từ máy dev lẫn VPS <VPS_IP> và bastion trong lúc làm (máy dev: DNS trỏ về 127.0.0.1; VPS/bastion: timeout kết nối). Tôi thay bằng **nến M1 giá bid của HistData.com** (tải miễn phí ASCII M1, tháng 4-9/2026; tháng 10 chưa phát hành nên bỏ NFP 2026-10-02). Dấu thời gian của HistData khớp **giờ ET có DST** (đỉnh NFP ở 08:30), không phải EST cố định → UTC = +4 giờ vào mùa hè; đã kiểm bằng đỉnh biến động tại giờ tin. Kiểm tra từng ngày NFP: biên độ 5 phút đầu ≥ 4 lần ngày thường ở cả 6 ngày với EURUSD (nên các ngày NFP tháng 4-6 mà tôi không đối chiếu được với lịch BLS chính thức là đúng ngày).

**Sự kiện**: NFP 2026-04-03, 05-08, 06-05, 07-02, 08-07, 09-04 (12:30 UTC); FOMC 04-29, 06-17, 07-29, 09-16 (18:00 UTC; lịch Fed: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm). **Ngày đối chứng**: cùng thứ, cùng giờ, ±1/2/3 tuần, loại ngày sự kiện (n≈92-126 cửa sổ/loại). Bốn mã: EURUSD, GBPUSD, USDJPY, XAUUSD. "Biên độ" = cao nhất − thấp nhất của mid-bid M1 trong cửa sổ; đơn vị pip (0,0001; JPY 0,01; vàng 0,1 USD).

**Kết quả (trung vị; tỷ lệ = sự kiện/đối chứng, gộp 4 mã bằng trung bình nhân)**

| Cửa sổ | NFP | FOMC |
|---|---|---|
| 30 phút TRƯỚC tin | ×0,95 (≈ bình thường) | ×1,26 |
| Phút đầu tiên | ×13 | ×17 |
| 5 phút đầu | **×7,1** | **×10,2** |
| 30 phút đầu | ×4,2 | ×5,5 |
| 60 phút đầu | ×3,5 | ×6,0 |
| Cả ngày | ×1,33 | ×1,61 |

| Ví dụ trung vị (pip) | Sự kiện 5 phút | Đối chứng 5 phút | Sự kiện 30 phút | Đối chứng 30 phút |
|---|---|---|---|---|
| EURUSD NFP | 33,0 | 5,3 | 45,2 | 11,2 |
| EURUSD FOMC | 39,9 | 3,1 | 45,6 | 6,4 |
| GBPUSD NFP | 39,1 | 6,7 | 54,8 | 15,7 |
| USDJPY NFP | 52,3 | 5,3 | 62,3 | 11,5 |
| XAUUSD NFP (USD) | 55,6 | 7,8 | 63,2 | 15,9 |

(KTC 95% bootstrap theo sự kiện trong `out/event_ratios.csv`; mọi KTC của tỷ lệ 5 phút nằm hẳn trên 1: ví dụ EURUSD NFP [4,3; 10,1], EURUSD FOMC [4,8; 17,5].)

- **Thời gian lắng**: số phút trung vị để biên độ từng phút ≤ 2× mức bình thường 30 phút trước (giữ 3 phút liên tiếp): NFP ~22,5; FOMC ~25 (theo mã dao động ~12-35).
- **Hướng đi**: dấu dịch chuyển giá sau 5 phút trùng dấu sau 30 phút ở 22/23 sự kiện NFP-mã và 16/16 FOMC-mã — tức hướng ban đầu (so với giá ngay trước tin) thường **giữ** qua 30 phút; nhưng phần giá bị hoàn lại từ cực trị (trung vị 25-30% biên độ cực đại trong 30 phút) cho thấy vẫn có quét hai chiều. Với 10 sự kiện và 4 mã (không độc lập) đây chỉ là mô tả.
- **Biên độ cả ngày chỉ tăng ×1,3-×1,6**: phần lớn lượng tăng đến từ chính cửa sổ tin; tôi chưa tách biên độ của phần ngày sau tin (không đủ mẫu để tuyên bố).

**Đề xuất tham số bộ lọc rủi ro tin** (dựa số đo trên; chưa tối ưu hóa; xem mục 6 về hạn chế):
- Sự kiện mức `high` (NFP, FOMC, CPI, quyết định lãi suất ECB/BoE/BoJ): **không mở lệnh mới từ T−15 phút đến T+30 phút (T+45 phút cho FOMC và vàng)**; lệnh đang mở: kiểm tra stop có nằm ngoài biên độ 5 phút điển hình (≈ 30-55 pip FX, ~$55 vàng) hay không, nếu không thì giảm cỡ trước tin, không dời stop sát đúng lúc tin ra.
- Trước tin 30 phút giá không biến động hơn bình thường (×0,95) nên thị trường "yên lặng trước bão" không phải tín hiệu cảnh báo — dùng **giờ trong lịch**, không dùng biến động để phát hiện.
- Spread/trượt giá: **chưa đo**. Giá trị bộ lọc nằm ở biên độ; chi phí thực còn lớn hơn đối với lệnh thị trường.

### 4.3 Dữ liệu trong chính hệ thống (mô tả, KHÔNG kết luận thống kê)

Truy vấn `tradingsys-timescaledb-1` (VPS, 2026-10-11):

| Bảng | Nội dung | Ý nghĩa |
|---|---|---|
| `news_items` | 1.070 tin, 39 nguồn, 137 ngày khác nhau; 157 tin trước 2026-09 (cũ nhất 2014-08); 627 tin (59%) trong 11 ngày gần nhất; 545 tiếng Việt / 525 tiếng Anh; 639 tin có gắn mã (USDJPY 205, GBPUSD 203, VNINDEX 208, XAUUSD 133, EURUSD 127…); **sentiment: 0/1.070** | Mẫu quá nhỏ, chưa có nhãn → **không kiểm định được** mối liên hệ tin–giá. Nguồn lớn nhất: `boj_whatsnew` (98), `vnexpress_kinhdoanh` (60) |
| `calendar_events` | 372 sự kiện (nguồn: bls 313, ecb 19, boe 16, boj 16, fed 8), ngày đến 2028; mức: high 218, med 58, low 96; **actual 0, forecast 0, previous 1** | **Không tính được surprise**; `bls` chiếm 84% nên "lịch" gần như là lịch BLS |
| `experts` / `expert_signals` | 12 chuyên gia, 26 tín hiệu | Chưa đủ để lập bảng đồng thuận (cần ≥ 3 chuyên gia/mã) |

Tôi nói thẳng: với 11 ngày tin dày đặc và không có nhãn sentiment, mọi tương quan tin–giá tính bây giờ đều là nhiễu. Cần ít nhất vài tháng liên tục, có nhãn, và có giá M1 đi kèm trước khi thử lại; khi đó nên dùng thiết kế sự kiện (cửa sổ ±30 phút) và trừ chi phí.

---

## 5. Tính năng đề xuất bổ sung cho hệ thống (theo thứ tự giá trị/chi phí)

1. **Bộ lọc rủi ro tin (news risk filter)** — ưu tiên số 1. Đầu vào: `calendar.events` mức `high` (và `med` cho tài sản liên quan). Đầu ra: cờ `news_risk: blackout|caution|clear` theo mã, thời điểm T−15…T+30/45, kèm "biên độ 5 phút điển hình" theo mã làm gợi ý khoảng cách stop. Không cần consensus; chỉ cần giờ chính xác (múi giờ ET→UTC có DST).
2. **Hoàn thiện lịch**: thêm `actual` từ nguồn công khai (BLS API/FRED) để ghi lại kết quả sau khi tin ra; consensus (`forecast`) phần lớn là dữ liệu có bản quyền — chỉ thêm nếu nguồn được phép; nếu không, dùng `actual − previous` như đại lượng thô và gắn nhãn rõ "không phải surprise". Thêm CPI/PCE/GDP/PMI/ECB/BoE (hiện bls chiếm 84% và nhóm ECB/BoE/BoJ/Fed chỉ 59 sự kiện).
3. **Nhật ký phản ứng tin tự đo** (microstructure log): với mỗi sự kiện high, lưu biên độ 1/5/30 phút và spread từ báo giá (market-collector có `quote` bid/ask) — để dần có số đo spread thật mà tôi chưa có.
4. **Cảnh báo COT cực đoan (chỉ thông tin)**: percentile 3 năm của vị thế ròng (Leveraged/Asset Mgr/Managed Money), thông báo Chủ nhật/thứ Hai với nhãn "ngữ cảnh — không phải tín hiệu; không có edge được kiểm chứng". Hiển thị cả độ trễ (as-of thứ Ba).
5. **Bảng đồng thuận có trọng số (chỉ hiển thị)**: trọng số theo **thành tích đã kiểm chứng** và độ dài lịch sử, **không** theo uy tín nhà xuất bản; tối thiểu 3 nguồn độc lập, hiện mức bất đồng; tự giảm trọng số khi nguồn có dấu hiệu martingale/grid hoặc xóa lịch sử. Gắn nhãn "độ tin cậy thấp".
6. **Sentiment tin: chỉ đếm/tóm tắt, chưa chấm điểm giao dịch**: số tin theo mã/giờ, nguồn, và có/không tin rủi ro (từ khóa: "chiến tranh", "thuế quan"…). Khi có ≥ 3-6 tháng dữ liệu và giá M1 đi kèm, mới chạy thử nghiệm sentiment → lợi suất tiếp theo, có bootstrap, hiệu chỉnh đa kiểm định, và mẫu ngoài.
7. **Ngăn lỗi dữ liệu**: cảnh báo khi bảng calendar thiếu `actual` sau khi sự kiện qua; khi `news_items.sentiment` rỗng 100% nhưng giao diện hiển thị cột sentiment.
8. **Cổ phiếu Mỹ (nếu mở rộng)**: Form 4 — chỉ lệnh mua mở thị trường, không theo lịch, lọc công ty nhỏ. 13F — danh sách theo dõi, quỹ tập trung/ít quay vòng.
9. **Việt Nam**: lưu chuỗi dòng tiền khối ngoại/tự doanh hằng ngày kèm VN-Index để tự kiểm chứng (dự báo với độ trễ ≥ 1 ngày) trước khi dùng.

---

## 6. Cảnh báo trung thực và hạn chế

1. **Mẫu sự kiện nhỏ**: bộ đo biên độ chỉ có **10 sự kiện × 4 mã** (một giai đoạn 6 tháng trong năm 2026); các mã tương quan mạnh với nhau nên hiệu quả mẫu ≈ 10, không phải 40. Tỷ lệ ×7-×10 đủ lớn để chắc chắn về **hiện tượng**, nhưng **số cụ thể** (22-25 phút, 30-55 pip) có sai số lớn và chưa kiểm cho CPI/ECB/BoE.
2. **Không đo được spread/trượt giá**: nến M1 bid không có giá ask; Dukascopy tick (có spread) không tải được. Mọi kết luận "tránh/khai thác tin" về chi phí dựa trên văn liệu thực hành, không phải số đo của tôi.
3. **Dấu thời gian HistData** tôi suy ra bằng thực nghiệm (ET có DST) từ đỉnh NFP/FOMC; ba ngày NFP đầu (4-6) chưa đối chiếu với lịch BLS chính thức nhưng đỉnh biên độ ở đúng 08:30 ET.
4. **COT**: giá là đóng cửa ngày của Yahoo (FX: khung giờ không chuẩn; vàng = hợp đồng liên tục GC=F, có thể có bước nhảy khi gối hợp đồng); không tính carry/chi phí. Vào thứ Hai sau công bố là lựa chọn thận trọng nhưng bỏ qua phần giá thứ Sáu–thứ Hai. Không kiểm các hướng khác (vị thế thay đổi, tỷ lệ so với open interest, kết hợp xu hướng). Kết quả âm tính "không phát hiện" ≠ "chứng minh không có".
5. **Văn liệu**: đọc qua tìm kiếm và tóm tắt, không đọc toàn văn; một số nguồn là luận văn/preprint/blog (đã đánh dấu). Số liệu ESMA 74-89% là tổng CFD 2018. Con số "Barclays/Novus +4%" và "−12% / 78%" copy-trading **không xác minh được** và đã loại.
6. **Hệ thống**: dữ liệu tin/lịch/chuyên gia quá mới để kiểm thống kê; kết luận ở 4.3 chỉ là mô tả. TradingView ideas và Myfxbook vẫn bị loại vì ToS/chặn bot (xem `services/expert-collector/SOURCES.md`), nên "retail sentiment" hiện chưa có nguồn thu thập hợp lệ.
7. Không có nội dung nào ở đây là khuyến nghị đầu tư. Mọi quy tắc đề xuất chỉ nhằm giảm rủi ro vận hành và cần được kiểm thử giấy (paper trading) trước.

---

## 7. Tái lập

```
cd research/info
..\..\.venv\Scripts\python.exe fetch_data.py       # CFTC COT (TFF+Disaggregated) + giá ngày Yahoo
..\..\.venv\Scripts\python.exe cot_study.py        # ~6 phút; ghi out/cot_*.csv và in tóm tắt
..\..\.venv\Scripts\python.exe fetch_histdata.py   # M1 HistData 4 mã x 6 tháng (3 giây/yêu cầu)
..\..\.venv\Scripts\python.exe event_study.py      # ghi out/event_windows.csv, event_ratios.csv
```
Đầu ra đã chạy nằm ở `research/info/out/`. Dữ liệu tải về ở `research/info/data/` (có thể xóa, chạy lại sẽ tải lại). Truy vấn DB (mục 4.3) chỉ đọc, chạy qua `docker exec tradingsys-timescaledb-1 psql`.
