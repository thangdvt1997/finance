// Bảng hướng dẫn: Cách dạy hiệu quả | Nhờ AI việc gì | Khái niệm. Nội dung tĩnh vi+en. Không hứa lợi nhuận.
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import "./guide.css";

// [việc nên làm, ví dụ câu nói, tác dụng, ví dụ SAI?]
const TEACH = [
  ["Nêu số cụ thể", "Nêu số cụ thể", "Specific numbers", "Hồi không quá 50% sóng 1, cách nhau 5-12 nến.", "Retrace no more than 50% of wave 1, 5-12 bars apart.", "Biến ý mơ hồ thành điều kiện kiểm tra được.", "Turns a vague idea into a testable condition."],
  ["Đưa ví dụ SAI giống ví dụ đúng", "Give a look-alike WRONG example", "", "Ví dụ SAI: đỉnh sau cao hơn đỉnh trước, nhìn giống nhưng không vào.", "WRONG example: the later peak is higher; it looks alike but we skip it.", "AI học ranh giới, giảm tín hiệu giả.", "The AI learns the boundary and fewer false signals."],
  ["Nói điều kiện HUỶ", "State the CANCEL condition", "", "Huỷ nếu giá đóng nến trên đỉnh thứ nhất.", "Cancel if price closes above the first peak.", "Kịch bản có điểm sai rõ ràng, đo được rủi ro.", "The scenario has a clear point of being wrong; risk is measurable."],
  ["Nêu lý do cung-cầu / tâm lý", "Give the supply-demand / psychology reason", "", "Mỗi lần lên người mua yếu hơn nên cầu cạn.", "Buyers get weaker each rally so demand dries up.", "AI phân biệt cơ chế với trùng hợp; ghi thành giả định cần test.", "The AI separates mechanism from coincidence; logged as an assumption to test."],
  ["Cho 3 ví dụ khác khung / mã", "Give 3 examples on other timeframes / symbols", "", "Đây là cùng mẫu trên GBPUSD H4 và XAUUSD M30.", "Same pattern on GBPUSD H4 and XAUUSD M30.", "Kiểm tra mẫu có tổng quát hay chỉ đúng một chỗ.", "Checks whether the pattern generalises or fits one place only."],
  ["Dùng đơn vị tương đối (ATR, %)", "Use relative units (ATR, %)", "", "Thân nến nhỏ hơn 0,4 ATR thay vì 'nến nhỏ'.", "Body under 0.4 ATR instead of 'small candle'.", "Cùng quy tắc chạy được trên mọi mã, mọi biến động.", "One rule works across symbols and volatility."],
  ["Nêu rõ đóng nến hay chạm bóng", "Say close vs wick touch", "", "Điều kiện tính theo giá ĐÓNG, bóng nến không tính.", "Conditions use the CLOSE; wicks do not count.", "Tránh hai cách hiểu khác nhau cho cùng một câu.", "Avoids two readings of the same sentence."],
  ["Nói bộ lọc: phiên, tin, spread", "Name filters: session, news, spread", "", "Bỏ qua 30 phút quanh tin mạnh và khi spread > 2 pip.", "Skip 30 minutes around major news and when spread > 2 pips.", "Loại các tình huống kịch bản không được thiết kế cho.", "Removes situations the scenario was not designed for."],
  ["Nói điều gì làm kịch bản THẤT BẠI", "Say what makes it FAIL", "", "Thất bại khi vùng rộng hơn 1,5 ATR hoặc có tin lớn.", "It fails when the range is wider than 1.5 ATR or major news hits.", "Đưa thêm điều kiện loại trừ, đúng chỗ.", "Adds exclusion conditions in the right place."],
  ["Dạy phiên bản đối xứng", "Teach the mirror version", "", "Phiên bản Buy: 3 đáy cao dần rồi nến nén.", "Buy version: 3 rising troughs then compression.", "Một ý tưởng, hai hướng; kiểm tra không phải may mắn một chiều.", "One idea, two directions; checks it is not one-sided luck."],
  ["Nói tự nhiên, AI tự hiểu ý", "Talk naturally, the AI picks up your intent", "", "Thử xem có lời không, rồi so với mua giữ nhé.", "Try it, is it profitable? Then compare with buy-and-hold.", "AI hiện 'AI hiểu ý bạn là…' (từ khoá được tô sáng) và hỏi xác nhận trước khi chạy việc nặng; sai ý thì bấm 'Không phải ý này'.", "The AI shows 'The AI understood…' (keywords highlighted) and asks before any heavy job; if wrong, tap 'Not what I meant'."],
  ["Sửa từng hàng, không viết lại cả đoạn", "Fix row by row, not whole paragraphs", "", "Sửa hàng 'SL': trên đỉnh thứ ba + 0,1 ATR.", "Edit row 'SL': above third peak + 0.1 ATR.", "AI cập nhật đúng chỗ, dễ so sánh phiên bản.", "The AI updates the right place; versions are easy to compare."],
  ["Chấp nhận 'chưa chắc'", "Accept 'not sure yet'", "", "Chỗ này tôi chưa chắc, hãy hỏi tôi 2 câu.", "I am not sure here, ask me two questions.", "Đánh dấu hàng thấp để AI hỏi tiếp thay vì đoán.", "Flags a low row so the AI asks instead of guessing."],
  ["Mức phương pháp: dạy từng kịch bản tới độ rõ >= 80 trước", "Method level: bring each scenario to clarity >= 80 first", "", "Làm rõ từng phòng kịch bản, rồi mới vào màn Phương pháp để khai báo quan hệ.", "Clarify each scenario room first, then open Methods to declare relations.", "Quan hệ giữa các kịch bản chỉ có nghĩa khi từng kịch bản đã rõ."],
  ["Mức phương pháp: nói rõ ai ưu tiên, ai loại trừ", "Method level: say who has priority and who excludes whom", "", "Khi bản 3 đỉnh và bản phá đáy cùng báo, bản 3 đỉnh đi trước; hai bản không chạy cùng lúc.", "When the 3-peaks and the low-break both fire, 3-peaks goes first; they never run together.", "AI ghi thành quy tắc kết hợp (ưu tiên, loại trừ) để bạn kiểm lại trong bảng."],
  ["Mức phương pháp: cho số ở quản trị vốn và quy tắc dừng", "Method level: give numbers for shared risk and stop rules", "", "Rủi ro 0,5% mỗi lệnh, tổng rủi ro nóng tối đa 2%, lỗ ngày 1,5%; dừng 30 phút quanh tin mạnh.", "Risk 0.5% per trade, max total open risk 2%, daily loss 1.5%; pause 30 minutes around major news.", "Hồ sơ phương pháp chỉ tính là rõ khi các hàng rủi ro có con số và được xác nhận (bước 6 của kế hoạch)."],];
const WRONG = { vi: "Tránh: 'Nến nhỏ rồi thì Sell thôi' (không số, không điều kiện huỷ, không ví dụ sai).", en: "Avoid: 'Small candles then just Sell' (no numbers, no cancel rule, no wrong example)." };
const CMDS = [
  ["“Chạy thử xem có lời không”|“Test it, is it profitable?”", "Chạy kiểm tra trung thực kịch bản trên dữ liệu lịch sử (walk-forward), ra thẻ kết quả.", "Runs an honest walk-forward test on history and shows a result card.", "Sau khi độ rõ đủ cao và đã lưu phiên bản.", "After clarity is high and a version is saved."],
  ["“Tìm những lần nó xuất hiện”|“Find where it appeared”", "Quét lịch sử tìm các ứng viên giống kịch bản để bạn gắn nhãn.", "Scans history for look-alike candidates for you to label.", "Khi cần thêm ví dụ đúng/sai, hoặc sau khi sửa quy tắc.", "When you need more right/wrong examples or after changing a rule."],
  ["“Thử khung/mã khác, biến thể”|“Try other timeframes, variants”", "Tạo vài biến thể (đổi ngưỡng, khung) để xem ý tưởng có bền không.", "Creates variants (thresholds, timeframe) to see if the idea is robust.", "Khi một số của bạn là ước lượng, chưa biết chọn bao nhiêu.", "When a number of yours is an estimate and you are unsure of the value."],
  ["“Làm phiên bản phía mua”|“Make the buy version”", "Dựng phiên bản đối xứng (Sell thành Buy hoặc ngược lại).", "Builds the mirror version (Sell to Buy or the reverse).", "Sau khi bản chính đã rõ, để kiểm tra không phải may mắn một chiều.", "Once the main version is clear, to check it is not one-sided luck."],
  ["“So với mua-giữ”|“Compare to buy-and-hold”", "So sánh hai phiên bản: khác điều kiện nào, kết quả khác ra sao.", "Compares two versions: which rules differ and how results differ.", "Sau khi sửa kịch bản và muốn biết có tốt hơn thật không.", "After editing and wanting to know if it is really better."],
  ["“Giải thích lại cho tôi”|“Explain it back to me”", "AI giải thích bằng lời của nó điều đã hiểu hoặc một kết quả.", "The AI explains in its own words what it understood or a result.", "Khi thấy kết quả lạ hoặc nghi AI hiểu sai.", "When a result looks odd or you suspect a misunderstanding."],
  ["“Tóm lại bạn hiểu thế nào?”|“Sum up what you understood”", "Tóm tắt hồ sơ kịch bản và các hàng còn mơ hồ.", "Summarises the profile and the vague rows.", "Đầu buổi học sau, hoặc trước khi lưu phiên bản.", "At the start of the next session or before saving a version."],
  ["“Lưu lại, chốt phiên bản”|“Save it, lock this version”", "Lưu phiên bản hiện tại của kịch bản (kèm ghi chú).", "Saves the current version of the scenario (with a note).", "Trước khi thay đổi lớn và trước khi chạy thử.", "Before a big change and before running a test."],
  ["“Còn gì chưa rõ, hỏi tôi tiếp”|“What is unclear, ask me”", "Yêu cầu AI hỏi tiếp vào hàng mơ hồ nhất.", "Asks the AI to question the vaguest row next.", "Khi bạn không biết nên nói thêm điều gì.", "When you do not know what else to say."],
  ["“Vẽ lên biểu đồ”|“Draw it on the chart”", "Mở biểu đồ để đánh dấu đỉnh, đáy, sóng, vùng, điểm vào.", "Opens the chart to mark peaks, troughs, waves, zones, entries.", "Khi lời nói khó diễn đạt hơn việc chỉ vào biểu đồ.", "When pointing at the chart beats describing it in words."],
];
const CONCEPTS = [
  ["Độ rõ ý tưởng", "Idea clarity", "Điểm 0-100: tỷ lệ các hàng hồ sơ đã xác nhận, có số định lượng và có ví dụ đúng/sai. Càng rõ ý tưởng thì giải pháp càng tốt; hàng thấp nhất được hỏi trước.", "A 0-100 score: the share of profile rows that are confirmed, quantified and backed by right/wrong examples. The clearer the idea, the better the result; the lowest row is asked first."],
  ["Nhãn ví dụ (Đúng / Sai / Gần đúng)", "Example labels (Right / Wrong / Close)", "Bạn gắn nhãn các ứng viên từ lần tìm ví dụ. Nhãn là dữ liệu dạy AI ranh giới của kịch bản. Phím tắt Đ / S / G, kèm lý do một dòng.", "You label candidates from the “Find examples” scan. Labels teach the AI the scenario boundary. Shortcuts R / W / C with a one-line reason."],
  ["Phiên bản", "Versions", "Mỗi lần lưu tạo một phiên bản có thể so sánh và quay lại. Test luôn gắn với một phiên bản cụ thể.", "Each save creates a comparable, restorable version. A test is always tied to one specific version."],
  ["Backtest trung thực", "Honest backtest", "Kiểm tra walk-forward trên dữ liệu chưa dùng để chỉnh quy tắc, tính cả chi phí, báo khoảng tin cậy, so với ngẫu nhiên và nêu rõ khi không có lợi thế. Không chọn lọc kết quả đẹp.", "Walk-forward on data not used to tune the rules, costs included, with a confidence interval and a random baseline, saying plainly when there is no edge. No cherry-picking."],
  ["Test khoá", "Locked test", "Một phần dữ liệu được giữ kín, chỉ mở MỘT lần khi ý tưởng đã chốt, và chỉ master cho phép (xác nhận 2 bước). Mở nhiều lần sẽ làm kết quả mất giá trị.", "A slice of data kept sealed, opened ONCE when the idea is final, and only with master approval (2-step confirmation). Opening it repeatedly destroys its value."],
  ["Vì sao không hứa lợi nhuận", "Why we never promise profit", "Hệ thống chỉ nghiên cứu và giao dịch giấy; kết quả quá khứ không bảo đảm tương lai, dữ liệu mẫu nhỏ dễ ngẫu nhiên, và thị trường đổi. Kết luận 'chưa chứng minh' là kết quả hợp lệ. Không có lệnh thật.", "The system is for research and paper trading only; past results never guarantee the future, small samples are mostly chance, and markets change. 'Unproven' is a valid outcome. No real orders."],
];

export default function GuidePanel({ lang = "vi", onClose }) {
  const en = lang === "en", L = (v, e) => (en ? e : v);
  const tabs = [["teach", L("Cách dạy hiệu quả", "Teaching well")], ["cmd", L("Nhờ AI việc gì", "What to ask the AI")], ["concept", L("Khái niệm", "Concepts")]];
  const [tab, setTab] = useState("teach");
  const root = useRef(null);
  useEffect(() => { root.current?.querySelector('[role="tab"][aria-selected="true"]')?.focus({ preventScroll: true }); }, []);
  const key = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose?.(); return; }
    const i = tabs.findIndex((x) => x[0] === tab);
    if (e.target.getAttribute?.("role") === "tab" && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
      const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length][0]; setTab(n); setTimeout(() => root.current?.querySelector(`#gd-tab-${n}`)?.focus(), 0); e.preventDefault();
    }
  };
  return (
    <div className="gd" ref={root} onKeyDown={key} role="region" aria-label={L("Hướng dẫn dạy AI", "Guide to teaching the AI")}>
      <div className="gd-head"><h2>{L("Hướng dẫn", "Guide")}</h2>{onClose && <button type="button" className="gd-btn" onClick={onClose} aria-label={L("Đóng hướng dẫn", "Close guide")}><X size={16} aria-hidden="true" />{L("Đóng", "Close")}</button>}</div>
      <div className="gd-tabs" role="tablist" aria-label={L("Mục hướng dẫn", "Guide sections")}>
        {tabs.map(([id, lb]) => <button key={id} id={`gd-tab-${id}`} type="button" role="tab" className="gd-tab" aria-selected={tab === id} aria-controls={`gd-pan-${id}`} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)}>{lb}</button>)}
      </div>
      <div className="gd-body" id={`gd-pan-${tab}`} role="tabpanel" aria-labelledby={`gd-tab-${tab}`} tabIndex={0}>
        {tab === "teach" && <>
          <div className="gd-tw" tabIndex={0}><table className="gd-table"><caption className="sr-only">{L("Cách dạy hiệu quả", "Teaching well")}</caption>
            <thead><tr><th scope="col">{L("Việc nên làm", "What to do")}</th><th scope="col">{L("Ví dụ câu nói", "Example sentence")}</th><th scope="col">{L("Tác dụng", "Effect")}</th></tr></thead>
            <tbody>{TEACH.map((r) => <tr key={r[0]}><td>{en ? r[2] || r[1] : r[0]}</td><td><q>{en ? r[4] : r[3]}</q></td><td>{en ? r[6] : r[5]}</td></tr>)}</tbody></table></div>
          <p className="gd-note"><span className="gd-bad">{L("Ví dụ SAI. ", "A BAD example. ")}</span>{en ? WRONG.en : WRONG.vi}</p>
        </>}
        {tab === "cmd" && <div className="gd-tw" tabIndex={0}><table className="gd-table"><caption className="sr-only">{L("Nhờ AI việc gì", "What to ask the AI")}</caption>
          <thead><tr><th scope="col">{L("Bạn có thể nói", "You can say")}</th><th scope="col">{L("Làm gì", "What it does")}</th><th scope="col">{L("Khi nào dùng", "When to use")}</th></tr></thead>
          <tbody>{CMDS.map((r) => <tr key={r[0]}><td><span className="gd-code">{r[0].split("|")[en ? 1 : 0]}</span></td><td>{en ? r[2] : r[1]}</td><td>{en ? r[4] : r[3]}</td></tr>)}</tbody></table></div>}
        {tab === "concept" && <dl className="gd-dl">{CONCEPTS.map((c) => <div key={c[0]}><dt>{en ? c[1] : c[0]}</dt><dd>{en ? c[3] : c[2]}</dd></div>)}</dl>}
      </div>
    </div>
  );
}
