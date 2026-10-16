// Lưới xác nhận ví dụ (6-10 thẻ): ảnh nến + sóng đánh số, phím tắt Đ/S/G + mũi tên, lý do 1 dòng, thống kê tức thời,
// hộp "AI đã học được gì từ nhãn" (tính tất định phía client). Chỉ nghiên cứu/paper, không có thao tác đặt lệnh.
// Props: {lang, rid, examples, labels, onLabel, onSend, onClose}
//  examples: [{id, symbol, tf, ts, image_url, entry, sl, note, waves?:[{n, x, y}] (x,y chuẩn hoá 0..1 trên ảnh)}]
//  labels:   [{example_id, verdict:"dung"|"sai"|"gan_dung", reason?}]; onLabel(info) gọi sau khi lưu nhãn (để cha refetch).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Lightbulb, X } from "lucide-react";
import { cpost, mediaUrl } from "./classApi";
import SafeImg from "./SafeImg";
import "./ux-examples.css";

const V = [["dung", "ĐÚNG", "RIGHT", "Đ", "up"], ["sai", "SAI", "WRONG", "S", "down"], ["gan_dung", "GẦN ĐÚNG", "CLOSE", "G", "accent"]];
const KEY = { d: "dung", "đ": "dung", s: "sai", g: "gan_dung" };
const STOP = new Set("khong không nhung nhưng thi thì cua của cho voi với duoc được nay này khi nhieu nhiều qua quá rat rất the thế and the for not too with that this was are".split(" "));
const fmt = (v) => (Number.isFinite(+v) ? String(+(+v).toFixed(5)) : String(v));
const P = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export function computeStats(examples, labels) {
  const ids = new Set(examples.map((e) => e.id)), L = labels.filter((l) => ids.has(l.example_id));
  const d = L.filter((l) => l.verdict === "dung").length, g = L.filter((l) => l.verdict === "gan_dung").length, s = L.filter((l) => l.verdict === "sai").length, n = L.length;
  return { n, total: examples.length, d, g, s, precision: n ? (d + 0.5 * g) / n : null, strict: n ? d / n : null, coverage: examples.length ? n / examples.length : null };
}

/** Tóm tắt "AI học được gì" tất định từ nhãn + lý do (không gọi mô hình). */
export function learnSummary(examples, labels, en) {
  const L = (a, b) => (en ? b : a), by = Object.fromEntries(examples.map((e) => [e.id, e]));
  const st = computeStats(examples, labels), out = [];
  if (!st.n) return { st, lines: [] };
  out.push(L(`Đã có ${st.n}/${st.total} nhãn: ${st.d} đúng, ${st.g} gần đúng, ${st.s} sai. Độ chính xác ${P(st.precision)} (chặt ${P(st.strict)}).`, `${st.n}/${st.total} labelled: ${st.d} right, ${st.g} close, ${st.s} wrong. Precision ${P(st.precision)} (strict ${P(st.strict)}).`));
  const words = (arr) => { const m = {}; for (const l of arr) for (const w of String(l.reason || "").toLowerCase().match(/[\p{L}\p{N}%.]{4,}/gu) || []) if (!STOP.has(w)) m[w] = (m[w] || 0) + 1; return Object.entries(m).filter(([, c]) => c >= 2).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([w, c]) => `"${w}" (${c})`); };
  const wr = words(labels.filter((l) => l.verdict === "sai")), rt = words(labels.filter((l) => l.verdict === "dung"));
  if (rt.length) out.push(L(`Điểm chung ở ví dụ ĐÚNG: ${rt.join(", ")}.`, `Common in RIGHT examples: ${rt.join(", ")}.`));
  if (wr.length) out.push(L(`Lặp lại trong lý do SAI (thành phản ví dụ): ${wr.join(", ")}. Nên biến thành điều kiện loại trừ có số.`, `Recurring in WRONG reasons (counter-examples): ${wr.join(", ")}. Turn into a quantified exclusion rule.`));
  const grp = {}; for (const l of labels) { const e = by[l.example_id]; if (!e) continue; const k = `${e.symbol || "?"} ${e.tf || ""}`.trim(); (grp[k] ||= { d: 0, s: 0 })[l.verdict === "sai" ? "s" : l.verdict === "dung" ? "d" : "x"]++; }
  const bad = Object.entries(grp).filter(([, v]) => v.s >= 2 && v.s > v.d).map(([k]) => k);
  if (bad.length) out.push(L(`Hay sai ở: ${bad.join(", ")}. Có thể kịch bản chỉ hợp mã/khung khác.`, `Often wrong on: ${bad.join(", ")}. The setup may fit other symbols/timeframes.`));
  const noReason = labels.filter((l) => l.verdict !== "dung" && !String(l.reason || "").trim()).length;
  if (noReason) out.push(L(`${noReason} nhãn SAI/GẦN ĐÚNG chưa có lý do: AI chưa học được vì sao, hãy thêm 1 dòng.`, `${noReason} WRONG/CLOSE labels have no reason: add one line so the AI can learn why.`));
  if (st.n < 5) out.push(L("Còn ít nhãn (<5): kết luận chưa đáng tin, gắn thêm.", "Few labels (<5): conclusions are weak, label more."));
  else if (st.s === 0) out.push(L("Chưa có ví dụ SAI nào: nhờ AI tìm lại hoặc nêu ví dụ gần giống để AI phân biệt.", "No WRONG example yet: ask the AI to search again or give look-alikes so the AI can discriminate."));
  return { st, lines: out };
}

function Waves({ w }) {
  if (!Array.isArray(w) || !w.length) return null;
  const pts = w.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts.map((p) => `${p.x * 100},${p.y * 100}`).join(" ")} fill="none" stroke="var(--accent)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
      {pts.map((p, i) => <g key={i}><circle cx={p.x * 100} cy={p.y * 100} r="2.6" fill="var(--accent)" /><text x={p.x * 100} y={p.y * 100 - 4} fontSize="6" textAnchor="middle" fill="#fff" stroke="#000" strokeWidth="1.2" paintOrder="stroke" fontWeight="700">{p.n ?? i + 1}</text></g>)}
    </svg>
  );
}

export default function ExamplesGrid({ lang = "vi", rid, examples = [], labels = [], onLabel, onSend, onClose }) {
  const en = lang === "en", t = (a, b) => (en ? b : a);
  const [local, setLocal] = useState({}), [reason, setReason] = useState({}), [cur, setCur] = useState(0), [err, setErr] = useState(null), [busy, setBusy] = useState(null), [zoom, setZoom] = useState(null);
  const root = useRef(null);
  const merged = useMemo(() => { const m = {}; for (const l of labels) m[l.example_id] = l; for (const [k, v] of Object.entries(local)) m[k] = { ...(m[k] || {}), ...v, example_id: k }; return m; }, [labels, local]);
  const lab = useMemo(() => Object.values(merged), [merged]);
  const { st, lines } = useMemo(() => learnSummary(examples, lab, en), [examples, lab, en]);

  const save = useCallback(async (e, verdict, rs) => {
    const reasonTxt = (rs ?? reason[e.id] ?? merged[e.id]?.reason ?? "").trim().slice(0, 300);
    setErr(null); setBusy(e.id); setLocal((s) => ({ ...s, [e.id]: { verdict, reason: reasonTxt } }));
    try {
      const r = await cpost(`/rooms/${encodeURIComponent(rid)}/labels`, { example_id: e.id, verdict, ...(reasonTxt ? { reason: reasonTxt } : {}) });
      onLabel?.({ example_id: e.id, verdict, reason: reasonTxt, summary: r?.summary });
    } catch (x) { setErr(x.message || String(x)); setLocal((s) => { const c = { ...s }; delete c[e.id]; return c; }); } finally { setBusy(null); }
  }, [rid, reason, merged, onLabel]);

  const cols = () => { const li = root.current?.querySelectorAll(".xg-card"); if (!li?.length) return 1; const y = li[0].offsetTop; let c = 0; for (const x of li) { if (x.offsetTop === y) c++; else break; } return c || 1; };
  const focusCard = (i) => { setCur(i); requestAnimationFrame(() => root.current?.querySelector(`[data-i="${i}"]`)?.scrollIntoView({ block: "nearest" })); };
  const onKey = (ev) => {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const tag = ev.target.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const n = examples.length; if (!n) return;
    const k = ev.key.toLowerCase();
    if (KEY[k]) { ev.preventDefault(); save(examples[cur], KEY[k]); focusCard(Math.min(n - 1, cur + 1)); return; }
    const mv = { arrowright: 1, arrowleft: -1, arrowdown: cols(), arrowup: -cols() }[k];
    if (mv) { ev.preventDefault(); focusCard(Math.max(0, Math.min(n - 1, cur + mv))); }
    else if (k === "enter") { ev.preventDefault(); root.current?.querySelector(`[data-i="${cur}"] input`)?.focus(); }
    else if (k === "escape") onClose?.();
  };
  useEffect(() => { if (zoom) { const h = (e) => e.key === "Escape" && setZoom(null); addEventListener("keydown", h); return () => removeEventListener("keydown", h); } }, [zoom]);

  if (!examples.length) {
    return (
      <div className="xg-empty" role="status">
        <b>{t("Chưa có ví dụ để xác nhận", "No examples to confirm yet")}</b>
        <span className="text-[13px] text-muted">{t("Gõ lệnh dưới đây trong khung chat: AI sẽ quét lịch sử và đưa 6-10 ảnh nến để bạn gắn nhãn ĐÚNG / SAI / GẦN ĐÚNG.", "Type the command below in chat: the AI scans history and shows 6-10 candle images for you to label RIGHT / WRONG / CLOSE.")}</span>
        
        {onSend && <button type="button" className="btn" onClick={() => onSend("/quet")}>{t("Tìm ví dụ ngay", "Find examples now")}</button>}
      </div>
    );
  }
  return (
    <div className="xg" ref={root}>
      <div className="xg-stats" role="group" aria-label={t("Thống kê nhãn", "Label stats")} aria-live="polite">
        <div className="xg-stat"><b>{P(st.precision)}</b><span>{t("Độ chính xác", "Precision")}{st.strict != null && ` · ${t("chặt", "strict")} ${P(st.strict)}`}</span></div>
        <div className="xg-stat"><b>{P(st.coverage)}</b><span>{t("Độ phủ", "Coverage")} · {st.n}/{st.total}</span></div>
        <div className="xg-stat"><b className="text-up">{st.d}</b><span>{t("Đúng", "Right")}</span></div>
        <div className="xg-stat"><b className="text-down">{st.s}</b><span>{t("Sai", "Wrong")}</span></div>
        <div className="xg-stat"><b>{st.g}</b><span>{t("Gần đúng", "Close")}</span></div>
      </div>
      <div className="xg-keys" aria-hidden="true"><span><kbd>Đ</kbd> {t("đúng", "right")}</span><span><kbd>S</kbd> {t("sai", "wrong")}</span><span><kbd>G</kbd> {t("gần đúng", "close")}</span><span><kbd>←↑↓→</kbd> {t("di chuyển", "move")}</span><span><kbd>Enter</kbd> {t("nhập lý do", "reason")}</span></div>
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
      <ul className="xg-grid" tabIndex={0} aria-label={t("Các ví dụ cần xác nhận. Phím Đ, S, G để gắn nhãn, mũi tên để di chuyển.", "Examples to confirm. Keys D, S, G to label, arrows to move.")} onKeyDown={onKey} onFocus={(e) => { if (e.target === e.currentTarget) setCur((c) => Math.min(c, examples.length - 1)); }}>
        {examples.map((e, i) => {
          const l = merged[e.id], u = mediaUrl(e.image_url);
          return (
            <li key={e.id} id={`xg-${e.id}`} data-i={i} aria-current={i === cur ? "true" : undefined} className={`xg-card ${i === cur ? "cur" : ""} ${l?.verdict ? `v-${l.verdict}` : ""}`} onClick={() => setCur(i)}>
              <button type="button" className="xg-img" tabIndex={-1} onClick={() => u && setZoom(u)} aria-label={t("Phóng to ảnh", "Zoom image") + ` #${i + 1}`}>
                {u ? <SafeImg src={u} alt={`${e.symbol || ""} ${e.tf || ""}`} loading="lazy" lang={lang} /> : <span className="xg-no">{t("Chưa có ảnh", "No image")}</span>}
                <Waves w={e.waves} /><span className="xg-num">{i + 1}</span>
              </button>
              <div className="xg-meta"><b>{e.symbol} {e.tf}</b>{e.entry != null && <span>{t("Vào", "Entry")} {fmt(e.entry)}</span>}{e.sl != null && <span>SL {fmt(e.sl)}</span>}</div>
              {e.note && <p className="m-0 text-[12px] text-muted">{e.note}</p>}
              <div className="xg-vbtns" role="group" aria-label={t("Nhãn cho ví dụ", "Label for example") + ` ${i + 1}`}>
                {V.map(([v, vi, vn, k, tone]) => <button key={v} type="button" disabled={busy === e.id} aria-pressed={l?.verdict === v} className={`btn ${l?.verdict === v ? `cr-on-${tone}` : "ghost"}`} onClick={(ev) => { ev.stopPropagation(); setCur(i); save(e, v); }}>{en ? vn : vi} <kbd aria-hidden="true">{k}</kbd></button>)}
              </div>
              <input className="cr-inp xg-reason" maxLength={300} value={reason[e.id] ?? l?.reason ?? ""} onChange={(ev) => setReason((r) => ({ ...r, [e.id]: ev.target.value }))}
                onKeyDown={(ev) => { ev.stopPropagation(); if (ev.key === "Enter" && l?.verdict) { ev.preventDefault(); save(e, l.verdict, ev.currentTarget.value); ev.currentTarget.blur(); } else if (ev.key === "Escape") ev.currentTarget.blur(); }}
                onBlur={(ev) => { const v = ev.currentTarget.value.trim(); if (l?.verdict && v !== String(l.reason || "").trim()) save(e, l.verdict, v); }}
                placeholder={t("Lý do 1 dòng (đặc biệt khi SAI / GẦN ĐÚNG)", "One-line reason (esp. WRONG / CLOSE)")} aria-label={t("Lý do", "Reason") + ` ${i + 1}`} />
            </li>
          );
        })}
      </ul>
      <section className="xg-learn" aria-label={t("AI đã học được gì từ nhãn", "What the AI learned from labels")} aria-live="polite">
        <h3 className="flex items-center gap-1"><Lightbulb size={14} aria-hidden="true" />{t("AI đã học được gì từ nhãn", "What the AI learned from your labels")}</h3>
        {lines.length ? <ul>{lines.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="m-0 text-muted">{t("Gắn vài nhãn để thấy tóm tắt. Không có nhãn thì không ước lượng.", "Label a few examples to see a summary. No labels, no estimate.")}</p>}
        <p className="m-0 text-[11.5px] text-muted">{t("Tóm tắt tính tự động từ nhãn và lý do của bạn, không phải kết luận về lợi nhuận.", "Computed automatically from your labels and reasons; not a statement about profitability.")}</p>
        <div className="flex gap-2 flex-wrap">
          {onSend && <button type="button" className="btn ghost" style={{ minHeight: 40 }} onClick={() => onSend("/quet")}>{t("Quét vòng mới", "Scan a new round")}</button>}
          {onClose && <button type="button" className="btn ghost" style={{ minHeight: 40 }} onClick={onClose}>{t("Đóng", "Close")}</button>}
        </div>
      </section>
      {zoom && <div className="cr-zoom" role="dialog" aria-modal="true" aria-label="Zoom" onClick={() => setZoom(null)}><img src={zoom} alt="" /><button type="button" className="btn cr-zoom-x" onClick={() => setZoom(null)} aria-label={t("Đóng", "Close")}><X size={16} /></button></div>}
    </div>
  );
}
