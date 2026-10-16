// Mẫu khởi tạo kịch bản (tĩnh). Mỗi mẫu cho 3 câu mô tả để gửi vào chat; chuyên gia sửa số liệu theo ý mình. Không phải khuyến nghị giao dịch.
export const TEMPLATES = [
  { id: "breakout", vi: "Phá vỡ vùng đi ngang", en: "Range breakout",
    sd: { vi: "Giá nén trong vùng đi ngang rồi phá ra một phía.", en: "Price compresses in a range, then breaks out one side." },
    brief: {
      vi: ["Mã EURUSD khung H1: giá đi ngang ít nhất 20 nến, biên độ không quá 1,5 ATR.", "Vào khi một nến đóng cửa ngoài biên vùng ít nhất 0,3 ATR; huỷ nếu 3 nến sau đó đóng lại trong vùng.", "SL ở phía bên kia vùng, TP tối thiểu 1,5R; lý do: tích luỹ lệnh chờ bị quét rồi dòng lệnh một chiều xuất hiện."],
      en: ["EURUSD on H1: price moves sideways for at least 20 bars, range no wider than 1.5 ATR.", "Enter when a bar closes beyond the range edge by at least 0.3 ATR; cancel if 3 later bars close back inside.", "SL on the far side of the range, TP at least 1.5R; rationale: resting orders get swept, then one-sided flow appears."] } },
  { id: "lh3", vi: "3 đỉnh giảm dần", en: "3 lower highs",
    sd: { vi: "Ba đỉnh thấp dần trong vùng đi ngang rồi nến nén, hướng Sell.", en: "Three falling peaks in a range, then compressed bars; Sell bias." },
    brief: {
      vi: ["Mã EURUSD khung H1, trong vùng đi ngang: có 3 đỉnh, mỗi đỉnh thấp hơn đỉnh trước ít nhất 0,2 ATR, cách nhau 5-12 nến.", "Sau đỉnh thứ ba có 4-8 nến nén (thân nhỏ hơn 0,4 ATR); vào Sell khi một nến đóng dưới đáy cụm nén; huỷ nếu giá đóng trên đỉnh thứ nhất.", "SL trên đỉnh thứ ba, TP về đáy vùng; lý do: người mua yếu dần, lực cầu cạn trước khi phá xuống."],
      en: ["EURUSD on H1, inside a range: 3 peaks, each at least 0.2 ATR below the previous, 5-12 bars apart.", "After the third peak 4-8 compressed bars (body under 0.4 ATR); Sell when a bar closes below the compression low; cancel if price closes above the first peak.", "SL above the third peak, TP at the range floor; rationale: buyers weaken, demand dries up before the break down."] } },
  { id: "supply", vi: "Vùng cung / cầu", en: "Supply / demand zone",
    sd: { vi: "Giá quay lại vùng xuất phát của một nhịp mạnh.", en: "Price returns to the origin of a strong impulse." },
    brief: {
      vi: ["Mã GBPUSD khung H4: tìm nhịp đi mạnh (thân nến lớn hơn 1,5 ATR) rời khỏi một cụm 1-3 nến nhỏ; cụm đó là vùng.", "Vào khi giá quay lại chạm vùng lần đầu và xuất hiện nến từ chối (bóng dài hơn 2 lần thân); huỷ nếu giá đóng xuyên hẳn qua vùng.", "SL ngoài vùng 0,2 ATR, TP tại đỉnh/đáy gần nhất; lý do: lệnh lớn chưa khớp hết còn nằm lại ở vùng đó."],
      en: ["GBPUSD on H4: find a strong move (body larger than 1.5 ATR) leaving a cluster of 1-3 small bars; that cluster is the zone.", "Enter on the first return to the zone with a rejection bar (wick over 2x body); cancel if price closes fully through the zone.", "SL 0.2 ATR beyond the zone, TP at the nearest swing; rationale: large unfilled orders remain in that zone."] } },
  { id: "pullback", vi: "Pullback theo xu hướng", en: "Trend pullback",
    sd: { vi: "Xu hướng rõ, hồi nông rồi đi tiếp.", en: "Clear trend, shallow retrace, then continuation." },
    brief: {
      vi: ["Mã XAUUSD khung H1: xu hướng giảm khi giá dưới EMA 50 và EMA 50 dốc xuống trên 10 nến gần nhất.", "Vào Sell khi giá hồi lên chạm EMA 50 nhưng không quá 50% sóng giảm trước, rồi có nến đóng cửa quay xuống; huỷ nếu hồi quá 61,8%.", "SL trên đỉnh hồi, TP ở đáy trước đó; lý do: người bán cũ chốt, người bán mới vào ở vùng giá rẻ hơn."],
      en: ["XAUUSD on H1: downtrend when price is below EMA 50 and EMA 50 slopes down over the last 10 bars.", "Sell when price retraces up to EMA 50 without exceeding 50% of the prior leg, then a bar closes back down; cancel beyond 61.8%.", "SL above the retrace high, TP at the prior low; rationale: earlier sellers take profit, new sellers join at a better price."] } },
  { id: "blank", vi: "Trống", en: "Blank",
    sd: { vi: "Tự mô tả từ đầu, AI sẽ hỏi từng hàng.", en: "Describe from scratch; the AI asks row by row." },
    brief: {
      vi: ["Tôi muốn dạy một kịch bản mới, chưa có tên.", "Mã và khung thời gian: [điền].", "Hãy hỏi tôi từng câu một để làm rõ ý tưởng."],
      en: ["I want to teach a new scenario, no name yet.", "Symbol and timeframe: [fill in].", "Please ask me one question at a time to clarify the idea."] } },
  { id: "import", vi: "Nhập từ ảnh / YAML", en: "Import from image / YAML", import: true,
    sd: { vi: "Đính ảnh biểu đồ hoặc tệp YAML mô tả kịch bản có sẵn.", en: "Attach a chart image or a YAML file describing an existing scenario." },
    brief: {
      vi: ["Tôi đính kèm ảnh/tệp YAML của một kịch bản đã có.", "Hãy đọc và điền vào Hồ sơ kịch bản những gì bạn hiểu được.", "Đánh dấu hàng nào còn mơ hồ rồi hỏi tôi."],
      en: ["I am attaching an image/YAML file of an existing scenario.", "Please read it and fill the scenario profile with what you understand.", "Mark which rows are still vague, then ask me."] } },
];
export const briefText = (t, lang) => (t.brief[lang === "en" ? "en" : "vi"]).join("\n");
