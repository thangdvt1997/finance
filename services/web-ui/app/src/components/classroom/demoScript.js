// Kịch bản "Buổi học mẫu" ghi sẵn (offline). TẤT CẢ số liệu là MINH HOẠ, không phải kết quả thật, không phải khuyến nghị.
// Kịch bản: 3 đỉnh giảm dần trong vùng đi ngang rồi nến nén -> Sell.
export const ROWS = [
  ["ctx", "Bối cảnh & xu hướng lớn", "Context & bigger trend"], ["sym", "Mã & khung", "Symbol & timeframe"], ["form", "Các bước hình thành", "Formation steps"],
  ["trig", "Điểm kích hoạt vào lệnh", "Entry trigger"], ["cancel", "Điều kiện HUỶ", "Cancel condition"], ["sl", "SL", "SL"], ["tp", "TP / quản lý lệnh", "TP / management"],
  ["risk", "Khối lượng & rủi ro", "Size & risk"], ["filt", "Bộ lọc", "Filters"], ["good", "Ví dụ ĐÚNG", "Right examples"], ["bad", "Ví dụ SAI / gần giống", "Wrong / look-alike examples"],
  ["fail", "Điều gì làm thất bại", "What makes it fail"], ["sym2", "Phiên bản đối xứng", "Mirror version"], ["why", "Lý do kinh tế / tâm lý", "Economic / psychological reason"],
  ["assume", "Giả định ngầm", "Hidden assumptions"], ["open", "Câu hỏi còn mở", "Open questions"],
];
const P = (vi, en) => ({ vi, en });

// Mỗi bước: chat (lượt chat mẫu), fill (hàng hồ sơ điền thêm: [vi,en,độ chắc]), clarity, view ('none'|'good'|'bad'|'scan'|'label'|'result'), note.
export const STEPS = [
  { id: "intro", clarity: 10,
    title: P("1. Mô tả bằng 3 câu", "1. Describe in 3 sentences"),
    chat: [
      ["u", P("Tôi muốn dạy kịch bản Sell: giá đi ngang, tạo 3 đỉnh thấp dần, rồi các nến bị nén lại.", "I want to teach a Sell scenario: price ranges, forms 3 falling peaks, then bars get compressed.")],
      ["a", P("Tôi hiểu sơ bộ: bias Sell sau chuỗi đỉnh giảm dần. Mã và khung nào? 'Thấp dần' là thấp hơn bao nhiêu?", "Rough understanding: Sell bias after a sequence of falling peaks. Which symbol and timeframe? How much lower is 'lower'?")],
    ],
    fill: { sym: [P("Chưa rõ (đang hỏi)", "Unclear (asking)"), P("Chưa rõ (đang hỏi)", "Unclear (asking)"), "low"], form: [P("3 đỉnh thấp dần, nến nén", "3 falling peaks, compressed bars"), P("3 falling peaks, compressed bars", "3 falling peaks, compressed bars"), "low"] }, view: "none" },
  { id: "numbers", clarity: 30,
    title: P("2. Nêu số cụ thể", "2. Give concrete numbers"),
    chat: [
      ["u", P("EURUSD khung H1. Mỗi đỉnh thấp hơn đỉnh trước ít nhất 0,2 ATR, cách nhau 5-12 nến, trong vùng đi ngang không quá 1,5 ATR.", "EURUSD on H1. Each peak at least 0.2 ATR below the previous, 5-12 bars apart, inside a range no wider than 1.5 ATR.")],
      ["a", P("Đã ghi 3 số định lượng. Bước nén: bao nhiêu nến và thân nhỏ cỡ nào?", "Recorded 3 numbers. For compression: how many bars and how small a body?")],
    ],
    fill: { sym: [P("EURUSD, H1", "EURUSD, H1"), null, "high"], form: [P("3 đỉnh, mỗi đỉnh thấp hơn >= 0,2 ATR, cách 5-12 nến, vùng <= 1,5 ATR", "3 peaks, each >= 0.2 ATR lower, 5-12 bars apart, range <= 1.5 ATR"), null, "mid"], ctx: [P("Vùng đi ngang (chưa nêu xu hướng lớn)", "Sideways range (bigger trend not stated)"), null, "low"] }, view: "none" },
  { id: "trigger", clarity: 45,
    title: P("3. Nói điều kiện huỷ", "3. State the cancel condition"),
    chat: [
      ["u", P("Nén là 4-8 nến thân nhỏ hơn 0,4 ATR. Vào Sell khi một nến đóng dưới đáy cụm nén. Huỷ nếu giá đóng trên đỉnh thứ nhất.", "Compression is 4-8 bars with body under 0.4 ATR. Sell when a bar closes below the compression low. Cancel if price closes above the first peak.")],
      ["a", P("Rõ. Điều kiện huỷ nằm ở đâu: đóng nến hay chỉ chạm bóng?", "Clear. Is the cancel on a close or just a wick touch?")],
    ],
    fill: { form: [P("... + 4-8 nến nén, thân < 0,4 ATR", "... + 4-8 compressed bars, body < 0.4 ATR"), null, "high"], trig: [P("Nến đóng dưới đáy cụm nén", "A bar closes below the compression low"), null, "high"], cancel: [P("Giá đóng trên đỉnh thứ nhất", "Price closes above the first peak"), null, "mid"] }, view: "none" },
  { id: "exit", clarity: 60,
    title: P("4. Lý do cung-cầu, SL/TP", "4. Supply-demand reason, SL/TP"),
    chat: [
      ["u", P("SL trên đỉnh thứ ba, TP về đáy vùng. Lý do: mỗi lần lên người mua yếu hơn, cầu cạn dần nên phá xuống.", "SL above the third peak, TP at the range floor. Reason: buyers get weaker each rally, demand dries up so it breaks down.")],
      ["a", P("Tôi coi 'cầu cạn dần' là giả định cần kiểm chứng, không phải sự thật. Ghi vào mục giả định ngầm nhé?", "I treat 'demand drying up' as an assumption to test, not a fact. Add it to hidden assumptions?")],
    ],
    fill: { sl: [P("Trên đỉnh thứ ba + 0,1 ATR", "Above third peak + 0.1 ATR"), null, "high"], tp: [P("Đáy vùng đi ngang", "Range floor"), null, "mid"], why: [P("Người mua yếu dần, cầu cạn trước khi phá xuống", "Buyers weaken, demand dries up before the break"), null, "mid"], assume: [P("Cầu thật sự cạn (cần test)", "Demand really dries up (to be tested)"), null, "low"], risk: [P("Chưa nêu", "Not stated"), null, "low"], filt: [P("Chưa nêu", "Not stated"), null, "low"] }, view: "none" },
  { id: "good", clarity: 70,
    title: P("5. Ví dụ ĐÚNG", "5. A RIGHT example"),
    chat: [
      ["u", P("Đây là ví dụ đúng: 3 đỉnh thấp dần, nén 5 nến, rồi đóng dưới đáy.", "Here is a right example: 3 falling peaks, 5-bar compression, then a close below the low.")],
      ["a", P("Đã đối chiếu: ví dụ này khớp 4/4 điều kiện. Còn ví dụ SAI, ví dụ gần giống?", "Checked: this example matches 4/4 conditions. What about a WRONG, look-alike example?")],
    ],
    fill: { good: [P("1 ví dụ (minh hoạ)", "1 example (illustration)"), null, "mid"] }, view: "good" },
  { id: "bad", clarity: 78,
    title: P("6. Ví dụ SAI", "6. A WRONG example"),
    chat: [
      ["u", P("Ví dụ SAI: 3 đỉnh nhưng đỉnh sau CAO hơn đỉnh trước. Nhìn giống nhưng là xu hướng tăng, không vào.", "WRONG example: 3 peaks but each is HIGHER than the last. Looks similar but it is an uptrend; do not enter.")],
      ["a", P("Cảm ơn, đây là ví dụ phân biệt rất tốt. Ghi 'đỉnh sau cao hơn' vào điều gì làm thất bại.", "Thanks, a very good discriminating example. Recording 'higher later peak' under what makes it fail.")],
    ],
    fill: { bad: [P("1 ví dụ: đỉnh sau cao hơn (minh hoạ)", "1 example: later peak higher (illustration)"), null, "high"], fail: [P("Đỉnh sau cao hơn đỉnh trước; vùng quá rộng", "Later peak higher; range too wide"), null, "mid"], sym2: [P("Buy: 3 đáy cao dần + nén (chưa test)", "Buy: 3 rising troughs + compression (untested)"), null, "low"] }, view: "bad" },
  { id: "scan", clarity: 84,
    title: P("7. Nhờ AI tìm ví dụ", "7. Ask the AI to find examples"),
    chat: [
      ["u", P("Tìm giúp tôi những lần nó xuất hiện", "Find the times it appeared")],
      ["a", P("Quét lịch sử mẫu (minh hoạ): 6 ứng viên. Hãy gắn nhãn Đúng / Sai / Gần đúng.", "Scanned sample history (illustration): 6 candidates. Please label Right / Wrong / Close.")],
    ],
    fill: { open: [P("Còn 1 câu: lọc phiên nào?", "1 left: which session filter?"), null, "low"] }, view: "scan" },
  { id: "label", clarity: 88,
    title: P("8. Gắn nhãn 6 ví dụ", "8. Label 6 examples"),
    chat: [
      ["u", P("Đ, Đ, S, Đ, G, S (đúng, đúng, sai, đúng, gần đúng, sai).", "R, R, W, R, C, W (right, right, wrong, right, close, wrong).")],
      ["a", P("AI đã học (minh hoạ): cả 3 ví dụ SAI đều có đỉnh sau cao hơn hoặc nén chưa đủ 4 nến. Lưu phiên bản v1?", "The AI learned (illustration): all wrong examples have a higher later peak or fewer than 4 compressed bars. Save version v1?")],
    ],
    fill: { good: [P("3 đúng + 1 gần đúng (minh hoạ)", "3 right + 1 close (illustration)"), null, "high"], bad: [P("2 sai + 1 ví dụ trước (minh hoạ)", "2 wrong + 1 earlier (illustration)"), null, "high"], filt: [P("Phiên London (giả định, cần kiểm chứng)", "London session (assumption, to verify)"), null, "mid"], risk: [P("Rủi ro 0,5% tài khoản giấy / lệnh", "0.5% paper account risk / trade"), null, "mid"] }, view: "label" },
  { id: "test", clarity: 90,
    title: P("9. Chạy thử trung thực", "9. Honest test"),
    chat: [
      ["u", P("Chạy thử xem có lời không", "Test it, is it profitable?")],
      ["a", P("Kết quả MINH HOẠ trên dữ liệu mẫu (không phải kết quả thật). Mẫu nhỏ, khoảng tin cậy chứa 0: không đủ bằng chứng có lợi thế. Test khoá chưa mở.", "ILLUSTRATIVE result on sample data (not a real result). Small sample, the interval contains 0: not enough evidence of an edge. The locked test stays closed.")],
    ],
    fill: { open: [P("Có thêm dữ liệu để kiểm chứng chưa?", "Is there more data to verify with?"), null, "mid"], assume: [P("Cầu cạn dần (đang test)", "Demand dries up (being tested)"), null, "mid"] }, view: "result" },
];

export const RESULT = { n: 38, exp: -0.04, lo: -0.31, hi: 0.23, rand: "~ 0,00R", pbo: "0,46", dsr: "0,31", verdictVi: "Chưa chứng minh", verdictEn: "Unproven" };
export const CANDS = [["Đ", "ok"], ["Đ", "ok"], ["S", "no"], ["Đ", "ok"], ["G", "mid"], ["S", "no"]];

// Nến tổng hợp (xác định, không ngẫu nhiên). wps: [chỉ số, giá, biên độ nhiễu]
function synth(wps, n) {
  const px = []; const amp = [];
  for (let i = 0; i < n; i++) {
    let k = 0; while (k < wps.length - 2 && wps[k + 1][0] < i) k++;
    const [i0, p0, a0] = wps[k], [i1, p1, a1] = wps[k + 1]; const f = Math.min(1, Math.max(0, (i - i0) / Math.max(1, i1 - i0)));
    px.push(p0 + (p1 - p0) * f); amp.push(a0 + (a1 - a0) * f);
  }
  let prev = px[0];
  return px.map((p, i) => { const w = Math.sin(i * 12.9898) * 0.5 + 0.5; const noise = (Math.sin(i * 2.3) + Math.cos(i * 1.1)) * amp[i] * 0.45; const c = p + noise; const o = prev; prev = c;
    const h = Math.max(o, c) + amp[i] * (0.35 + 0.5 * w), l = Math.min(o, c) - amp[i] * (0.35 + 0.5 * (1 - w)); return [o, h, l, c]; });
}
// Đúng: đỉnh ở 8, 19, 30 giảm dần; nén 31-37; rồi phá xuống. Sai: đỉnh tăng dần.
export const BARS_GOOD = synth([[0, 100, 1.2], [4, 103, 1.2], [8, 108, 1.2], [13, 100.5, 1.2], [19, 106, 1.2], [24, 100, 1.2], [30, 104, 1.2], [32, 102.4, .35], [37, 102, .3], [38, 101, .9], [44, 96, 1.2], [47, 95, 1.2]], 48);
export const BARS_BAD = synth([[0, 100, 1.2], [4, 103, 1.2], [8, 105, 1.2], [13, 101, 1.2], [19, 108, 1.2], [24, 103, 1.2], [30, 112, 1.2], [32, 110.4, .35], [37, 110, .3], [38, 109, .9], [44, 108, 1.2], [47, 109, 1.2]], 48);
export const PEAKS_GOOD = [8, 19, 30]; export const PEAKS_BAD = [8, 19, 30];
export const COMPRESS = [32, 37];
