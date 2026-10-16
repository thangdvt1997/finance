// Thuật ngữ & công thức (tiếng Việt). Dùng cho <Term>, trang Trợ giúp và tìm kiếm trong Ctrl-K.
// Mỗi mục: id (khoá, không dấu), term (tên hiển thị), aka (tên khác/viết tắt dùng để tìm), short (1 câu, hiện trong tooltip), long (giải thích), formula (nếu có), cat.
export const GLOSSARY_CATS = { price: "Giá & lệnh", account: "Tài khoản & ký quỹ", risk: "Rủi ro & hiệu suất", tech: "Chỉ báo kỹ thuật", macro: "Kinh tế vĩ mô & tin", vn: "Chứng khoán Việt Nam", sys: "Hệ thống" };

export const GLOSSARY = [
  // ----- Giá & lệnh -----
  { id: "bid-ask", term: "Giá mua / giá bán (Bid/Ask)", aka: ["bid", "ask", "mua", "ban"], cat: "price",
    short: "Bid là giá cao nhất người mua sẵn sàng trả; Ask là giá thấp nhất người bán chấp nhận.",
    long: "Khi bạn BÁN ngay, bạn nhận giá Bid. Khi bạn MUA ngay, bạn trả giá Ask. Giá hiển thị lớn trên bảng thường là Bid (hoặc trung bình). Chênh lệch Ask − Bid chính là spread." },
  { id: "spread", term: "Spread (chênh lệch giá mua-bán)", aka: ["spread", "chenh lech"], cat: "price",
    short: "Chênh lệch giữa giá bán (Ask) và giá mua (Bid); là chi phí giao dịch ngầm.",
    formula: "Spread = Ask − Bid",
    long: "Spread nhỏ nghĩa là thanh khoản tốt và chi phí vào lệnh thấp. Spread thường nở rộng khi có tin lớn, lúc giao phiên hoặc thị trường mỏng. Với cặp 5 số lẻ, spread thường đọc bằng pip." },
  { id: "pip", term: "Pip / Point", aka: ["pip", "point", "pipette"], cat: "price",
    short: "Đơn vị biến động giá nhỏ nhất thường dùng: 0,0001 với đa số cặp tiền, 0,01 với cặp có JPY.",
    long: "Nhiều sàn báo giá thêm một chữ số thập phân (pipette = 1/10 pip). Giá trị 1 pip phụ thuộc cặp tiền và khối lượng lệnh." },
  { id: "lot", term: "Lot (khối lượng)", aka: ["lot", "khoi luong", "volume"], cat: "price",
    short: "Đơn vị khối lượng: 1 lot chuẩn = 100.000 đơn vị tiền cơ sở; 0,1 = mini; 0,01 = micro.",
    long: "Khối lượng càng lớn, mỗi pip biến động càng tạo lãi/lỗ lớn. Ở chứng khoán Việt Nam lô chẵn thường là 100 cổ phiếu." },
  { id: "slippage", term: "Trượt giá (Slippage)", aka: ["slippage", "truot gia"], cat: "price",
    short: "Chênh lệch giữa giá bạn muốn và giá lệnh thực sự khớp, thường khi thị trường biến động mạnh.",
    long: "Trượt giá có thể bất lợi hoặc có lợi. Lệnh giới hạn tránh được trượt giá nhưng có thể không khớp." },
  { id: "sl-tp", term: "Cắt lỗ / Chốt lời (SL/TP)", aka: ["stop loss", "take profit", "sl", "tp", "cat lo", "chot loi"], cat: "price",
    short: "Mức giá tự động đóng lệnh để giới hạn lỗ (SL) hoặc khoá lãi (TP).",
    long: "Hệ thống này chỉ ĐỌC dữ liệu tài khoản; mọi lệnh đặt/sửa/đóng đều làm trên nền tảng giao dịch của bạn." },
  { id: "swap", term: "Swap (phí qua đêm)", aka: ["swap", "phi qua dem", "rollover"], cat: "price",
    short: "Khoản phí hoặc lãi khi giữ lệnh qua 00:00 giờ máy chủ sàn, theo chênh lệch lãi suất hai đồng tiền.", long: "Thứ Tư thường tính swap gấp 3 lần để bù cuối tuần." },
  { id: "timeframe", term: "Khung thời gian (Timeframe)", aka: ["tf", "khung", "m1", "m5", "m15", "h1", "h4", "d1"], cat: "price",
    short: "Độ dài mỗi cây nến: M1 = 1 phút, H1 = 1 giờ, H4 = 4 giờ, D1 = 1 ngày.",
    long: "Khung lớn lọc nhiễu và cho xu hướng rõ hơn; khung nhỏ cho điểm vào chi tiết nhưng nhiều tín hiệu giả." },
  { id: "candle", term: "Nến (OHLC)", aka: ["nen", "candlestick", "ohlc", "bar"], cat: "price",
    short: "Mỗi nến cho 4 giá trong một khung: Mở (Open), Cao (High), Thấp (Low), Đóng (Close).",
    long: "Thân nến nối giá mở và đóng; bóng nến là phần giá chạy xa hơn rồi bị đẩy lại." },
  { id: "volume", term: "Khối lượng giao dịch (Volume)", aka: ["volume", "khoi luong giao dich", "tick volume"], cat: "price",
    short: "Lượng giao dịch trong một khung. Với forex thường là số lần cập nhật giá (tick volume), không phải khối lượng thật.", long: "Khối lượng tăng cùng giá giúp xác nhận xu hướng." },

  // ----- Tài khoản & ký quỹ -----
  { id: "balance", term: "Số dư (Balance)", aka: ["balance", "so du"], cat: "account", short: "Tiền trong tài khoản chưa tính lãi/lỗ của các lệnh đang mở.", long: "Số dư chỉ đổi khi lệnh được đóng hoặc có nạp/rút." },
  { id: "equity", term: "Vốn thực (Equity)", aka: ["equity", "von thuc"], cat: "account", formula: "Equity = Balance + Lãi/lỗ đang mở",
    short: "Giá trị tài khoản theo thời gian thực, gồm cả lãi/lỗ chưa chốt.", long: "Equity là số quyết định bạn còn bao nhiêu \"đệm\" trước khi bị gọi ký quỹ." },
  { id: "margin", term: "Ký quỹ (Margin)", aka: ["margin", "ky quy"], cat: "account", formula: "Margin = Giá trị lệnh ÷ Đòn bẩy",
    short: "Số tiền sàn giữ lại làm tài sản đảm bảo để duy trì các lệnh đang mở.", long: "Ký quỹ được giải phóng khi lệnh đóng." },
  { id: "free-margin", term: "Ký quỹ khả dụng (Free margin)", aka: ["free margin", "ky quy kha dung"], cat: "account", formula: "Free margin = Equity − Margin",
    short: "Phần vốn còn lại có thể dùng để mở thêm lệnh hoặc chịu thêm biến động bất lợi.", long: "Về 0 nghĩa là không mở thêm được lệnh mới." },
  { id: "margin-level", term: "Mức ký quỹ (Margin level)", aka: ["margin level", "muc ky quy"], cat: "account", formula: "Margin level = Equity ÷ Margin × 100%",
    short: "Chỉ số sức khoẻ tài khoản: càng cao càng an toàn; xuống ngưỡng của sàn (margin call/stop-out) có thể bị buộc đóng lệnh.",
    long: "Mỗi sàn đặt ngưỡng margin call (ví dụ 100%) và stop-out (ví dụ 20-50%) khác nhau. Hệ thống cho phép đặt cảnh báo khi margin level thấp để bạn xử lý sớm." },
  { id: "leverage", term: "Đòn bẩy (Leverage)", aka: ["leverage", "don bay"], cat: "account",
    short: "Tỷ lệ giữa giá trị lệnh và vốn ký quỹ (ví dụ 1:100). Đòn bẩy khuếch đại cả lãi lẫn lỗ.", long: "Đòn bẩy cao không làm lệnh có lợi hơn, chỉ làm tài khoản mỏng hơn trước biến động." },
  { id: "floating", term: "Lãi/lỗ đang mở (Floating P/L)", aka: ["floating", "lai lo", "unrealized"], cat: "account", short: "Lãi hoặc lỗ tạm tính của các lệnh chưa đóng; đổi theo từng tick giá.", long: "Chỉ thành lãi/lỗ thật khi lệnh đóng." },
  { id: "read-only", term: "Chỉ-đọc (Read-only)", aka: ["chi doc", "investor", "read only"], cat: "account",
    short: "Hệ thống chỉ xem số liệu tài khoản MT4/MT5, không thể đặt, sửa hay đóng lệnh.", long: "Mọi liên kết tài khoản dùng chế độ chỉ đọc; không lưu mật khẩu giao dịch." },

  // ----- Rủi ro & hiệu suất -----
  { id: "drawdown", term: "Sụt vốn (Drawdown)", aka: ["drawdown", "dd", "sut von", "max drawdown", "mdd"], cat: "risk", formula: "Drawdown = (Đỉnh vốn − Vốn hiện tại) ÷ Đỉnh vốn",
    short: "Mức giảm của vốn tính từ đỉnh gần nhất; Max Drawdown là mức sụt sâu nhất trong kỳ.", long: "Sụt 50% cần lãi 100% để hoà vốn, nên kiểm soát drawdown quan trọng hơn theo đuổi lợi nhuận." },
  { id: "var", term: "VaR (Giá trị chịu rủi ro)", aka: ["var", "value at risk"], cat: "risk",
    short: "Mức lỗ tối đa ước tính trong một khoảng thời gian với độ tin cậy cho trước (ví dụ VaR 95% 1 ngày).",
    long: "VaR 95% = 2% nghĩa là trong 95% số ngày lỗ không vượt 2%, nhưng 5% số ngày còn lại có thể lỗ nhiều hơn, và VaR không nói lỗ nhiều hơn bao nhiêu. Đọc cùng Expected Shortfall và sụt vốn lịch sử." },
  { id: "profit-factor", term: "Hệ số lợi nhuận (Profit factor)", aka: ["profit factor", "he so loi nhuan", "pf"], cat: "risk", formula: "Profit factor = Tổng lãi gộp ÷ Tổng lỗ gộp",
    short: "Trên 1 là có lãi; thường từ 1,5 trở lên mới đáng tin nếu đủ số lệnh.", long: "Cần cùng số lệnh đủ lớn; vài lệnh thắng lớn có thể làm chỉ số ảo." },
  { id: "win-rate", term: "Tỷ lệ thắng (Win rate)", aka: ["win rate", "ty le thang"], cat: "risk", formula: "Win rate = Số lệnh thắng ÷ Tổng số lệnh",
    short: "Phần trăm lệnh có lãi. Không đủ để đánh giá nếu không xét kích thước lãi so với lỗ.", long: "Tỷ lệ thắng 40% vẫn có lãi nếu mỗi lệnh thắng lớn gấp hơn 1,5 lần lệnh thua." },
  { id: "expectancy", term: "Kỳ vọng lợi nhuận (Expectancy)", aka: ["expectancy", "ky vong"], cat: "risk", formula: "E = Win% × Lãi TB − Thua% × Lỗ TB",
    short: "Lãi/lỗ trung bình mong đợi mỗi lệnh sau nhiều lệnh.", long: "Dương nghĩa là hệ thống có lợi thế thống kê, với điều kiện mẫu đủ lớn." },
  { id: "rr", term: "Tỷ lệ lời/lỗ (Risk:Reward, R)", aka: ["risk reward", "rr", "r multiple", "r"], cat: "risk",
    short: "So sánh mức lãi mục tiêu với mức lỗ chấp nhận. 1R = số tiền rủi ro ban đầu của lệnh.", long: "Kết quả theo bội số R giúp so sánh lệnh với kích thước khác nhau." },
  { id: "sharpe", term: "Sharpe ratio", aka: ["sharpe"], cat: "risk", formula: "Sharpe = (Lợi suất − Lãi suất phi rủi ro) ÷ Độ lệch chuẩn lợi suất",
    short: "Lợi nhuận trên mỗi đơn vị biến động; càng cao càng tốt (trên 1 là khá, trên 2 là rất tốt).", long: "Sortino chỉ phạt biến động xuống nên công bằng hơn với chiến lược lệch dương." },
  { id: "correlation", term: "Tương quan (Correlation)", aka: ["correlation", "tuong quan"], cat: "risk", short: "Mức hai tài sản đi cùng nhau, từ −1 (ngược hẳn) đến +1 (cùng hẳn).", long: "Giữ nhiều lệnh tương quan cao thực chất là một lệnh lớn." },
  { id: "volatility", term: "Biến động (Volatility)", aka: ["volatility", "bien dong"], cat: "risk", short: "Mức dao động của giá trong một thời kỳ, thường đo bằng độ lệch chuẩn hoặc ATR.", long: "Biến động cao: cơ hội lớn hơn nhưng rủi ro bị quét lệnh cũng lớn hơn." },
  { id: "backtest", term: "Backtest / Paper trading", aka: ["backtest", "paper", "mo phong"], cat: "risk",
    short: "Backtest: thử chiến lược trên dữ liệu quá khứ. Paper: chạy thời gian thực bằng tiền ảo.", long: "Kết quả quá khứ không bảo đảm tương lai; cần kiểm tra ngoài mẫu và trừ chi phí/trượt giá." },

  // ----- Chỉ báo kỹ thuật -----
  { id: "rsi", term: "RSI", aka: ["rsi", "relative strength"], cat: "tech", short: "Chỉ báo động lượng 0-100 (thường chu kỳ 14): trên 70 gọi là quá mua, dưới 30 là quá bán.", long: "Quá mua không có nghĩa phải giảm; trong xu hướng mạnh RSI có thể ở vùng cao rất lâu." },
  { id: "ema-sma", term: "Đường trung bình (SMA/EMA)", aka: ["ema", "sma", "ma", "trung binh"], cat: "tech", short: "SMA là trung bình đơn giản của n phiên; EMA đặt trọng số cao hơn cho giá gần đây nên nhạy hơn.", long: "Giá nằm trên đường trung bình dài thường được coi là xu hướng tăng." },
  { id: "macd", term: "MACD", aka: ["macd"], cat: "tech", formula: "MACD = EMA12 − EMA26; Tín hiệu = EMA9 của MACD",
    short: "Đo động lượng xu hướng qua chênh lệch hai EMA; cắt lên đường tín hiệu thường báo đà tăng.", long: "Histogram là phần chênh lệch MACD và đường tín hiệu." },
  { id: "bollinger", term: "Dải Bollinger", aka: ["bollinger", "bb"], cat: "tech", formula: "Dải = SMA20 ± 2 × độ lệch chuẩn", short: "Dải trên/dưới bao quanh giá; dải hẹp báo biến động thấp, dải mở rộng báo biến động tăng.", long: "Giá chạm dải không tự động là tín hiệu đảo chiều." },
  { id: "atr", term: "ATR", aka: ["atr", "average true range"], cat: "tech", short: "Biên độ dao động trung bình (thường 14 nến). Dùng để đặt cắt lỗ và cỡ lệnh theo biến động.", long: "ATR cao: nên đặt SL xa hơn và giảm khối lượng." },
  { id: "adx", term: "ADX", aka: ["adx"], cat: "tech", short: "Đo ĐỘ MẠNH xu hướng (không chỉ hướng): trên 25 là có xu hướng rõ, dưới 20 là đi ngang.", long: "Dùng cùng +DI/−DI để biết hướng." },
  { id: "stoch", term: "Stochastic", aka: ["stochastic", "stoch"], cat: "tech", short: "So giá đóng với biên giá trong n phiên (0-100); trên 80 quá mua, dưới 20 quá bán.", long: "Nhạy hơn RSI, nhiều tín hiệu giả hơn khi thị trường có xu hướng." },
  { id: "ichimoku", term: "Ichimoku", aka: ["ichimoku", "kumo"], cat: "tech", short: "Hệ chỉ báo gồm Tenkan, Kijun và mây (Kumo) cho xu hướng, hỗ trợ/kháng cự trong một biểu đồ.", long: "Giá trên mây: xu hướng tăng; trong mây: do dự; dưới mây: xu hướng giảm." },
  { id: "sr", term: "Hỗ trợ / Kháng cự", aka: ["support", "resistance", "ho tro", "khang cu"], cat: "tech", short: "Vùng giá mà trước đó giá thường dừng lại hoặc quay đầu.", long: "Hỗ trợ bị phá thường trở thành kháng cự và ngược lại." },
  { id: "fib", term: "Fibonacci thoái lui", aka: ["fibonacci", "fib"], cat: "tech", short: "Các mức 23,6%, 38,2%, 50%, 61,8%, 78,6% của một nhịp để ước vùng giá hồi.", long: "Là công cụ tham khảo, hiệu quả khi trùng với hỗ trợ/kháng cự khác." },

  // ----- Vĩ mô & tin -----
  { id: "impact", term: "Mức tác động của tin", aka: ["impact", "tac dong"], cat: "macro", short: "Cao/Vừa/Thấp: mức tin kinh tế thường làm giá biến động. Tin cao như NFP, CPI, quyết định lãi suất.", long: "Hệ thống có thể cảnh báo trước khi tin cao ra để bạn tránh vào lệnh sát giờ." },
  { id: "nfp", term: "NFP (bảng lương phi nông nghiệp Mỹ)", aka: ["nfp", "non farm", "bang luong"], cat: "macro", short: "Báo cáo việc làm Mỹ công bố thứ Sáu đầu tháng; thường gây biến động mạnh cho USD, vàng và chỉ số.", long: "Số liệu so với dự báo (forecast) quyết định hướng phản ứng." },
  { id: "cpi", term: "CPI (chỉ số giá tiêu dùng)", aka: ["cpi", "lam phat", "inflation"], cat: "macro", short: "Thước đo lạm phát phổ biến; lạm phát cao hơn dự báo thường làm kỳ vọng tăng lãi suất tăng.", long: "Core CPI loại thực phẩm và năng lượng." },
  { id: "fomc", term: "FOMC / lãi suất", aka: ["fomc", "fed", "lai suat"], cat: "macro", short: "Ủy ban điều hành lãi suất của Cục Dự trữ Liên bang Mỹ, họp khoảng 8 lần/năm; quyết định và họp báo ảnh hưởng toàn thị trường.", long: "Hawkish: nghiêng về thắt chặt (tăng lãi suất). Dovish: nghiêng về nới lỏng." },
  { id: "forecast", term: "Dự báo / Thực tế / Kỳ trước", aka: ["forecast", "actual", "previous", "du bao", "thuc te"], cat: "macro", short: "Lịch kinh tế so sánh số công bố (Thực tế) với kỳ vọng thị trường (Dự báo) và kỳ trước.", long: "Độ \"bất ngờ\" là chênh lệch giữa thực tế và dự báo, quyết định mức phản ứng của giá." },
  { id: "sentiment", term: "Tâm lý tin tức (Sentiment)", aka: ["sentiment", "tam ly"], cat: "macro", short: "Điểm tích cực/tiêu cực của tin tức liên quan một mã, do mô hình ngôn ngữ chạy cục bộ tính toán.", long: "Chỉ là tham khảo: tin tốt đã được giá phản ánh trước vẫn có thể làm giá giảm." },
  { id: "session", term: "Phiên giao dịch", aka: ["session", "phien", "tokyo", "london", "new york"], cat: "macro", short: "Các khung giờ thanh khoản chính: Tokyo, London, New York. Chồng phiên London-New York thường biến động mạnh nhất.", long: "Thanh khoản mỏng làm spread nở và giá giật." },

  // ----- Chứng khoán VN -----
  { id: "ref-ceil-floor", term: "Giá tham chiếu, trần, sàn", aka: ["tham chieu", "tran", "san", "ceiling", "floor"], cat: "vn", short: "Giá tham chiếu là mốc (thường giá đóng cửa phiên trước); trần/sàn là biên độ tối đa ±7% (HOSE), ±10% (HNX), ±15% (UPCoM).", long: "Màu thường dùng: tím = trần, xanh lơ = sàn, vàng = tham chiếu, xanh = tăng, đỏ = giảm." },
  { id: "foreign", term: "Khối ngoại / room ngoại", aka: ["khoi ngoai", "room", "foreign"], cat: "vn", short: "Giao dịch của nhà đầu tư nước ngoài; room ngoại là tỷ lệ sở hữu tối đa còn lại cho họ.", long: "Mua ròng hoặc bán ròng của khối ngoại thường được theo dõi như tín hiệu dòng tiền." },
  { id: "settlement", term: "Thanh toán T+2", aka: ["t+2", "t2", "thanh toan"], cat: "vn", short: "Cổ phiếu mua hôm nay về tài khoản sau 2 ngày làm việc; chỉ bán được khi đã về.", long: "Quy định có thể thay đổi; luôn kiểm tra công ty chứng khoán của bạn." },
  { id: "ato-atc", term: "ATO / ATC", aka: ["ato", "atc"], cat: "vn", short: "Lệnh xác định giá mở cửa (ATO) và đóng cửa (ATC); khớp một lần theo giá xác định của phiên.", long: "Chỉ có tác dụng trong phiên định kỳ tương ứng." },

  // ----- Hệ thống -----
  { id: "freshness", term: "Độ tươi dữ liệu", aka: ["do tuoi", "fresh", "stale", "cu"], cat: "sys", short: "Huy hiệu cho biết dữ liệu mới cập nhật cách đây bao lâu: xanh = mới, vàng = chậm, đỏ = cũ, xám = thị trường nghỉ.", long: "Thị trường đóng cửa nên dữ liệu giữ nguyên lần cuối sẽ có huy hiệu xám, không báo lỗi." },
  { id: "realtime", term: "Trực tiếp (thời gian thực)", aka: ["realtime", "live", "truc tiep", "websocket"], cat: "sys", short: "Kênh đẩy dữ liệu liên tục tới trình duyệt. \"Mất kết nối\" nghĩa là số liệu có thể đã cũ; giao diện tự nối lại.", long: "Khi mất kết nối, bảng vẫn hiển thị số liệu cuối nhưng huy hiệu độ tươi sẽ chuyển vàng/đỏ." },
  { id: "dedupe", term: "Gộp cảnh báo trùng", aka: ["dedupe", "cooldown", "trung"], cat: "sys", short: "Mỗi cảnh báo có thời gian chờ (cooldown) để không bị gửi lặp liên tục khi điều kiện còn đúng.", long: "Chế độ \"một lần\" tự tắt sau khi kích hoạt; \"lặp lại\" tôn trọng cooldown." },
];

const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
export const foldText = fold;
const index = new Map();
for (const g of GLOSSARY) { index.set(g.id, g); for (const a of g.aka || []) if (!index.has(fold(a))) index.set(fold(a), g); }
/** Tìm mục theo id hoặc tên khác (không dấu, không phân biệt hoa thường). */
export const termById = (k) => index.get(k) || index.get(fold(k)) || null;

export const FAQ = [
  { q: "Vì sao có huy hiệu “cũ”, “chậm” hoặc “nghỉ” cạnh số liệu?", a: "Đó là độ tươi dữ liệu. Xanh: mới cập nhật; vàng: chậm hơn bình thường; đỏ: cũ, nên kiểm tra trang Hệ thống; xám (trăng): thị trường đang đóng cửa nên giá giữ nguyên lần cuối, không phải lỗi." },
  { q: "“Mất kết nối” ở góc trên nghĩa là gì?", a: "Kênh dữ liệu thời gian thực tạm đứt (mạng yếu hoặc máy chủ khởi động lại). Giao diện tự nối lại với khoảng chờ tăng dần; bạn cũng có thể bấm “Nối lại ngay” trên banner. Trong lúc đó số liệu hiển thị có thể đã cũ." },
  { q: "Hệ thống có đặt lệnh giúp tôi không?", a: "Không. Mọi tài khoản MT4/MT5 ở chế độ chỉ-đọc và không có đường đặt, sửa hay đóng lệnh. Thông tin chỉ để tham khảo, không phải khuyến nghị đầu tư." },
  { q: "Làm sao tạo cảnh báo giá nhanh nhất?", a: "Nhấn Ctrl K rồi gõ, ví dụ “cảnh báo eurusd 1.0850”, Enter. Hoặc vào trang Cảnh báo, chọn mẫu “Giá vượt ngưỡng”. Cảnh báo kích hoạt sẽ hiện ở chuông thông báo và gửi tới kênh bạn chọn (ntfy, Telegram, nhật ký)." },
  { q: "Đổi màu tăng/giảm hoặc giao diện sáng/tối ở đâu?", a: "Trang Cài đặt (nhấn g rồi k). Có xanh tăng/đỏ giảm, đỏ tăng/xanh giảm kiểu châu Á và bảng màu xanh dương/cam thân thiện với người mù màu. Giao diện có thể là sáng, tối hoặc tự động theo thiết bị." },
  { q: "Giờ hiển thị là múi giờ nào?", a: "Mặc định giờ Việt Nam (UTC+7). Bạn đổi được ở Cài đặt, khi đó thanh trên sẽ hiện nhãn múi giờ để tránh nhầm. Một số mô tả cố định trong trang (ví dụ giờ bản tin 06:15) vẫn tính theo giờ Việt Nam." },
  { q: "Xuất dữ liệu ra Excel hoặc PDF thế nào?", a: "Bấm nút “Công cụ trang” (biểu tượng chia sẻ) ở thanh trên: xuất bảng CSV hoặc Excel, lưu biểu đồ/bảng thành ảnh PNG, in hoặc lưu PDF (bố cục in đã được chỉnh), sao chép bảng để dán vào Excel/Google Sheets, sao chép liên kết có trạng thái." },
  { q: "Chia sẻ đúng mã và khung thời gian cho người khác?", a: "Sao chép liên kết từ “Công cụ trang”. Ví dụ liên kết biểu đồ có dạng #/thi-truong/EURUSD?tf=H4; mở liên kết đó sẽ đúng mã và khung. Người nhận cần có tài khoản." },
  { q: "Cài giao diện như ứng dụng trên điện thoại?", a: "Dùng nút “Cài đặt ứng dụng” trên thanh trên (nếu trình duyệt hỗ trợ) hoặc “Thêm vào màn hình chính” của Safari/Chrome. Ứng dụng không bao giờ lưu đệm dữ liệu giá hay tài khoản." },
  { q: "Vì sao có mục báo 403 hoặc “không có quyền”?", a: "Tài khoản khách hàng chỉ thấy dữ liệu thị trường và tài khoản của chính mình. Các mục vận hành (hệ thống, cảnh báo, báo cáo, khách hàng) dành cho quản trị viên." },
  { q: "Tôi quên mật khẩu hoặc mất thiết bị xác thực?", a: "Liên hệ quản trị viên để đặt lại. Sau khi đặt lại, mọi phiên cũ bị thu hồi và bạn đăng nhập bằng mật khẩu mới." },
  { q: "Thông báo của tôi lưu ở đâu?", a: "Chuông thông báo lưu trong trình duyệt của thiết bị này (tối đa 200 mục, 14 ngày). Cài đặt giao diện lưu lên máy chủ theo tài khoản và đồng bộ giữa các thiết bị." },
  { q: "Âm báo và thông báo trình duyệt hoạt động thế nào?", a: "Bật ở Cài đặt > Thông báo. Âm báo cần một thao tác của bạn trên trang trước (quy định của trình duyệt). Thông báo trình duyệt chỉ hiện khi tab đang ẩn và bạn đã cấp quyền." },
  { q: "Dùng bàn phím thế nào cho nhanh?", a: "Nhấn ? để xem bảng phím tắt: Ctrl K tìm nhanh, / tìm kiếm, g rồi chữ để chuyển trang (g o Tổng quan, g m Thị trường), t đổi giao diện, [ thu gọn thanh bên." },
];
