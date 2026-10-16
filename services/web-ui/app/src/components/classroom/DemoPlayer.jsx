// "Buổi học mẫu": kịch bản ghi sẵn, chạy offline. Mọi thứ là MINH HOẠ — không phải dữ liệu/kết quả thật.
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play, X } from "lucide-react";
import { BARS_BAD, BARS_GOOD, CANDS, COMPRESS, PEAKS_GOOD, RESULT, ROWS, STEPS } from "./demoScript";
import "./guide.css";

const CONF = { high: ["Cao", "High"], mid: ["Vừa", "Medium"], low: ["Thấp", "Low"] };

function Candles({ bars, peaks, bad, en, entry }) {
  const W = 480, H = 220, pad = 8, n = bars.length, bw = (W - pad * 2) / n;
  const lo = Math.min(...bars.map((b) => b[2])), hi = Math.max(...bars.map((b) => b[1]));
  const y = (v) => pad + 14 + (hi - v) / (hi - lo) * (H - pad * 2 - 20), x = (i) => pad + i * bw + bw / 2;
  return (
    <svg className="dm-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={en ? "Synthetic illustrative candles (not market data)" : "Nến tổng hợp minh hoạ (không phải dữ liệu thị trường)"}>
      <rect x={x(COMPRESS[0]) - bw / 2} y={pad + 14} width={(COMPRESS[1] - COMPRESS[0] + 1) * bw} height={H - pad * 2 - 14} fill="var(--accent)" fillOpacity=".12" stroke="var(--accent)" strokeDasharray="4 3" />
      {bars.map((b, i) => { const up = b[3] >= b[0], c = up ? "var(--up)" : "var(--down)"; return (
        <g key={i}><line x1={x(i)} x2={x(i)} y1={y(b[1])} y2={y(b[2])} stroke={c} /><rect x={x(i) - bw * .32} width={bw * .64} y={y(Math.max(b[0], b[3]))} height={Math.max(1.5, Math.abs(y(b[0]) - y(b[3])))} fill={c} /></g>); })}
      {peaks.map((p, k) => <g key={p}><circle cx={x(p)} cy={y(bars[p][1]) - 9} r="8" fill="var(--panel)" stroke="var(--info)" /><text className="lbl" x={x(p)} y={y(bars[p][1]) - 6} textAnchor="middle">{k + 1}</text></g>)}
      <polyline fill="none" stroke="var(--info)" strokeDasharray="3 3" points={peaks.map((p) => `${x(p)},${y(bars[p][1])}`).join(" ")} />
      <text x={x(COMPRESS[0])} y={H - 4}>{en ? "compression" : "nén"}</text>
      {!bad && entry && <g><path d={`M${x(38)} ${y(bars[38][2]) + 4} l-5 9 h10 z`} fill="var(--down)" /><text className="lbl" x={x(38) + 8} y={y(bars[38][2]) + 16}>Sell (paper)</text></g>}
      {bad && <text className="lbl" x={x(peaks[2]) - 70} y={y(bars[peaks[2]][1]) - 20} fill="var(--down)" style={{ fill: "var(--down)" }}>{en ? "peaks RISING: wrong" : "đỉnh TĂNG dần: sai"}</text>}
      <text x={W - 8} y={pad + 8} textAnchor="end" style={{ fill: "var(--accent)", fontWeight: 700 }}>{en ? "ILLUSTRATION" : "MINH HOẠ"}</text>
    </svg>
  );
}

export default function DemoPlayer({ lang = "vi", onClose }) {
  const en = lang === "en", L = (v, e) => (en ? e : v), tx = (p) => (en ? p.en : p.vi);
  const [i, setI] = useState(0);
  const reduce = useMemo(() => { try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; } }, []);
  const [play, setPlay] = useState(!reduce);
  const root = useRef(null), chatEnd = useRef(null);
  const last = STEPS.length - 1;

  useEffect(() => { root.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => { if (!play) return undefined; if (i >= last) { setPlay(false); return undefined; } const t = setTimeout(() => setI((x) => Math.min(last, x + 1)), 5500); return () => clearTimeout(t); }, [play, i, last]);
  useEffect(() => { const el = chatEnd.current; if (el) el.scrollTop = el.scrollHeight; }, [i]);

  const prof = useMemo(() => { const o = {}; STEPS.slice(0, i + 1).forEach((s, k) => Object.entries(s.fill || {}).forEach(([key, v]) => { o[key] = { vi: v[0].vi, en: v[0].en, c: v[2], fresh: k === i }; })); return o; }, [i]);
  const chat = useMemo(() => STEPS.slice(0, i + 1).flatMap((s) => s.chat), [i]);
  const st = STEPS[i], clarity = st.clarity;

  const key = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose?.(); }
    else if (e.key === "ArrowRight") { setPlay(false); setI((x) => Math.min(last, x + 1)); }
    else if (e.key === "ArrowLeft") { setPlay(false); setI((x) => Math.max(0, x - 1)); }
  };

  return (
    <div className="gd" ref={root} tabIndex={-1} role="region" aria-label={L("Buổi học mẫu (minh hoạ)", "Sample lesson (illustration)")} onKeyDown={key}>
      <div className="gd-head">
        <h2>{L("Buổi học mẫu", "Sample lesson")} <span className="dm-badge">{L("Minh hoạ", "Illustration")}</span></h2>
        <button type="button" className="gd-btn" onClick={onClose} aria-label={L("Đóng buổi học mẫu", "Close sample lesson")}><X size={16} aria-hidden="true" />{L("Đóng", "Close")}</button>
      </div>
      <div className="dm-banner" role="note"><span className="dm-badge">{L("Minh hoạ", "Illustration")}</span>{L("Dữ liệu, nến, số liệu bên dưới là GIẢ LẬP để học cách dạy. Không phải kết quả thật, không phải khuyến nghị, không đặt lệnh.", "All data, candles and numbers below are SIMULATED to teach the method. Not real results, not a recommendation, no orders are placed.")}</div>
      <div className="gd-body" tabIndex={0}>
        <p className="m-0 mb-2 text-[13px]"><b>{tx(st.title)}</b> <span className="text-muted text-[12px]">({i + 1}/{STEPS.length})</span></p>
        <div className="dm-grid">
          <div className="grid gap-3 content-start min-w-0">
            <section className="dm-box" aria-label={L("Hội thoại mẫu", "Sample chat")}>
              <h3>{L("Hội thoại", "Chat")} <span className="dm-badge">{L("Minh hoạ", "Illustration")}</span></h3>
              <div className="dm-chat" ref={chatEnd} role="log" tabIndex={0} aria-label={L("Hội thoại mẫu", "Sample conversation")} aria-live="polite">
                {chat.map(([r, p], k) => <div key={k} className={`dm-msg ${r}`}><b className="who">{r === "u" ? L("Chuyên gia", "Expert") : "AI"}</b>{tx(p)}</div>)}
              </div>
            </section>
            {st.view === "good" || st.view === "bad" ? (
              <section className="dm-box" aria-label={L("Ví dụ", "Example")}>
                <h3>{st.view === "good" ? L("Ví dụ ĐÚNG", "RIGHT example") : L("Ví dụ SAI (gần giống)", "WRONG look-alike example")} <span className="dm-badge">{L("Minh hoạ", "Illustration")}</span></h3>
                <Candles bars={st.view === "good" ? BARS_GOOD : BARS_BAD} peaks={PEAKS_GOOD} bad={st.view === "bad"} en={en} entry />
              </section>
            ) : null}
            {st.view === "scan" || st.view === "label" ? (
              <section className="dm-box" aria-label={L("Ứng viên tìm được", "Found candidates")}>
                <h3>{st.view === "scan" ? L("6 ứng viên tìm được", "6 candidates found") : L("Đã gắn nhãn 6 ví dụ", "6 examples labelled")} <span className="dm-badge">{L("Minh hoạ", "Illustration")}</span></h3>
                <div className="dm-cands">
                  {CANDS.map(([tg, cl], k) => <div className="dm-cand" key={k}><Candles bars={k % 2 ? BARS_BAD : BARS_GOOD} peaks={PEAKS_GOOD} bad={k % 2 === 1} en={en} />
                    {st.view === "label" ? <span className={`tag ${cl}`}>{en ? { "Đ": "R", "S": "W", "G": "C" }[tg] : tg} {cl === "ok" ? L("đúng", "right") : cl === "no" ? L("sai", "wrong") : L("gần đúng", "close")}</span> : <span className="text-muted">#{k + 1} {L("chưa nhãn", "unlabelled")}</span>}</div>)}
                </div>
                {st.view === "label" && <p className="gd-note px-2 pb-2">{L("Độ chính xác minh hoạ: 3 đúng / 1 gần đúng / 2 sai. Phím tắt thật: Đ / S / G.", "Illustrative tally: 3 right / 1 close / 2 wrong. Real shortcuts: R / W / C.")}</p>}
              </section>
            ) : null}
            {st.view === "result" && (
              <section className="dm-box" aria-label={L("Thẻ kết quả test (minh hoạ)", "Test result card (illustration)")}>
                <h3>{L("Kết quả test", "Test result")} <span className="dm-badge">{L("Số minh hoạ", "Illustrative numbers")}</span></h3>
                <div className="dm-res">
                  {[[L("Số lệnh", "Trades"), RESULT.n], [L("Kỳ vọng", "Expectancy"), `${RESULT.exp.toString().replace(".", ",")}R`], [L("Khoảng tin cậy", "Interval"), `${RESULT.lo.toString().replace(".", ",")} .. +${RESULT.hi.toString().replace(".", ",")}`], [L("So với ngẫu nhiên", "vs random"), RESULT.rand], ["PBO", RESULT.pbo], ["DSR", RESULT.dsr]].map(([k, v]) => <div key={k} className="dm-stat"><span>{k}</span><b>{v}</b></div>)}
                </div>
                <p className="dm-warn" role="note"><b>{L("Kết luận trung thực: ", "Honest verdict: ")}{en ? RESULT.verdictEn : RESULT.verdictVi}.</b> {L("Khoảng tin cậy chứa 0, mẫu nhỏ. Không có bằng chứng về lợi thế; kết quả quá khứ không bảo đảm tương lai. Test khoá chưa mở (chỉ master mở, xác nhận 2 bước).", "The interval contains 0 and the sample is small. No evidence of an edge; past results never guarantee the future. The locked test is closed (master only, 2-step confirmation).")}</p>
              </section>
            )}
          </div>
          <div className="grid gap-3 content-start min-w-0">
            <section className="dm-box dm-clarity" aria-label={L("Độ rõ ý tưởng", "Idea clarity")}>
              <div className="flex justify-between text-[12.5px] mb-1"><b>{L("Độ rõ ý tưởng", "Idea clarity")}</b><span className="num"><b>{clarity}</b>/100 <span className="dm-badge">{L("Minh hoạ", "Illustration")}</span></span></div>
              <div className="dm-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={clarity} aria-label={L("Độ rõ ý tưởng", "Idea clarity")}><i style={{ width: `${clarity}%` }} /></div>
            </section>
            <section className="dm-box" aria-label={L("Hồ sơ kịch bản", "Scenario profile")}>
              <h3>{L("Hồ sơ kịch bản (điền dần)", "Scenario profile (fills in)")} <span className="dm-badge">{L("Minh hoạ", "Illustration")}</span></h3>
              <ul className="dm-rows">
                {ROWS.map(([id, vi, e]) => { const v = prof[id]; return (
                  <li key={id} className={`dm-row${v ? "" : " empty"}${v?.fresh ? " new" : ""}`}>
                    <span className="k">{en ? e : vi}</span><span className="v">{v ? (en ? v.en : v.vi) : L("chưa có", "empty")}</span>
                    {v ? <span className={`dm-conf ${v.c}`}>{en ? CONF[v.c][1] : CONF[v.c][0]}</span> : <span />}
                  </li>); })}
              </ul>
            </section>
          </div>
        </div>
      </div>
      <div className="dm-ctl">
        <button type="button" className="gd-btn" onClick={() => { setPlay(false); setI((x) => Math.max(0, x - 1)); }} disabled={i === 0}><ChevronLeft size={16} aria-hidden="true" />{L("Lùi", "Back")}</button>
        <button type="button" className="gd-btn" onClick={() => { if (i >= last) setI(0); setPlay((p) => !p); }} aria-pressed={play}>{play ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}{play ? L("Tạm dừng", "Pause") : i >= last ? L("Chạy lại", "Replay") : L("Tự chạy", "Auto-play")}</button>
        <button type="button" className="gd-btn pri" onClick={() => { setPlay(false); setI((x) => Math.min(last, x + 1)); }} disabled={i === last}>{L("Tiếp", "Next")}<ChevronRight size={16} aria-hidden="true" /></button>
        <div className="dm-dots" role="group" aria-label={L("Chọn bước", "Pick a step")}>
          {STEPS.map((s, k) => <button key={s.id} type="button" className={`dm-dot${k < i ? " past" : ""}`} aria-current={k === i ? "step" : undefined} aria-label={`${L("Bước", "Step")} ${k + 1}: ${tx(s.title)}`} onClick={() => { setPlay(false); setI(k); }} />)}
        </div>
      </div>
    </div>
  );
}
