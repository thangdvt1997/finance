// Thẻ kết quả test TRUNG THỰC trong chat AI Training Class. Mặc định kỳ vọng "không có edge": không tô xanh ăn mừng, luôn kèm cảnh báo.
// Chỉ nghiên cứu/paper, không khuyến nghị, không hứa lợi nhuận.
// Props: {lang, result, role, rid, onSend, onEdit}
//  result = data của tin result_card: {scenario_id, verdict, metrics:{expectancy_r, ci95:[lo,hi], p_vs_random, trades, baseline_expectancy_r?, pbo?, dsr?, max_dd_r?, win_rate?, equity?:[R luỹ kế]}, equity?, honesty:[..], disclaimer}
import { useState } from "react";
import { AlertTriangle, Download, Info, Lock, MessageCircleQuestion, Pencil } from "lucide-react";
import { cpost } from "./classApi";
import "./ux-examples.css";

const N = (v) => (v == null || v === "" || !Number.isFinite(+v) ? null : +v);
const f = (v, d = 2) => (N(v) == null ? "—" : (+v).toFixed(d).replace(".", ","));
const R = (v) => (N(v) == null ? "—" : `${+v > 0 ? "+" : ""}${f(v)}R`);

function Equity({ pts, label }) {
  if (!pts || pts.length < 2) return <p className="m-0 text-[12px] text-muted">{label.none}</p>;
  const W = 300, H = 90, pad = 6, lo = Math.min(0, ...pts), hi = Math.max(0, ...pts), span = hi - lo || 1;
  const X = (i) => pad + (i / (pts.length - 1)) * (W - 2 * pad), Y = (v) => H - pad - ((v - lo) / span) * (H - 2 * pad);
  const last = pts[pts.length - 1];
  return (
    <svg className="tr-eq" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${label.eq}: ${label.end} ${R(last)}, ${label.n} ${pts.length}`}>
      <line x1="0" x2={W} y1={Y(0)} y2={Y(0)} stroke="var(--line2)" strokeDasharray="4 3" />
      <polyline fill="none" stroke="var(--info)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" points={pts.map((v, i) => `${X(i)},${Y(v)}`).join(" ")} />
    </svg>
  );
}

export default function TestResultCard({ lang = "vi", result, role, rid, onSend, onEdit }) {
  const en = lang === "en", t = (a, b) => (en ? b : a);
  const d = result || {}, m = d.metrics || {}, id = d.scenario_id;
  const exp = N(m.expectancy_r), ci = Array.isArray(m.ci95 ?? m.expectancy_ci) ? (m.ci95 ?? m.expectancy_ci).map(N) : [N(m.ci_low), N(m.ci_high)];
  const p = N(m.p_vs_random), trades = N(m.trades ?? m.n), pbo = N(m.pbo), dsr = N(m.dsr), dd = N(m.max_dd_r ?? m.max_drawdown_r), wr = N(m.win_rate);
  const base = N(m.baseline_expectancy_r ?? m.random_expectancy_r ?? m.baseline_r);
  const raw = d.equity ?? m.equity ?? m.equity_curve ?? d.equity_curve;
  const eq = Array.isArray(raw) ? raw.map((x) => N(typeof x === "object" && x ? x.r ?? x.equity ?? x.v : x)).filter((x) => x != null) : null;
  const [lo, hi] = ci;
  const ciCross = lo != null && hi != null && lo <= 0 && hi >= 0;
  // Kết luận thận trọng: chỉ "có dấu hiệu" khi verdict=edge VÀ kỳ vọng>0 VÀ CI không chứa 0 VÀ p<0,05; ngược lại coi như chưa có edge.
  const signal = d.verdict === "edge" && exp > 0 && lo != null && lo > 0 && p != null && p < 0.05;
  const kind = d.verdict === "no_edge" || (exp != null && exp <= 0) ? "down" : signal ? "pos" : "neutral";
  const title = kind === "down" ? t("Không có edge trong dữ liệu đã test", "No edge found in the tested data")
    : kind === "pos" ? t("Có dấu hiệu, CHƯA phải bằng chứng: cần kiểm chứng ngoài mẫu", "A signal, NOT proof: needs out-of-sample confirmation")
    : t("Chưa chứng minh được edge", "Edge not proven");
  const body = kind === "down" ? t("Đây là kết quả bình thường và hữu ích: kịch bản này chưa thắng được ngẫu nhiên sau chi phí. Đừng chỉnh luật để 'cứu' kết quả trên cùng dữ liệu này.", "This is a normal, useful result: the scenario did not beat chance after costs. Do not tweak rules to rescue it on the same data.")
    : kind === "pos" ? t("Kết quả dev có thể do may mắn hoặc quá khớp. Không phải khuyến nghị, không đảm bảo lợi nhuận; chỉ nghiên cứu/paper.", "Dev results may be luck or overfitting. Not a recommendation and no guarantee of profit; research/paper only.")
    : t("Số liệu chưa đủ để kết luận (khoảng tin cậy rộng hoặc chưa hơn ngẫu nhiên). Cần thêm dữ liệu/ví dụ, không phải thêm tham số.", "Not enough to conclude (wide interval or not beating chance). Needs more data/examples, not more parameters.");
  const flags = [];
  if (trades != null && trades < 100) flags.push(t(`Chỉ ${trades} lệnh (<100): kết quả rất nhiễu.`, `Only ${trades} trades (<100): very noisy.`));
  if (ciCross) flags.push(t("Khoảng tin cậy chứa 0: không loại trừ được kỳ vọng bằng 0.", "The confidence interval contains 0: zero expectancy cannot be ruled out."));
  if (p != null && p >= 0.05) flags.push(t(`p so với ngẫu nhiên = ${f(p, 3)} (≥0,05): chưa hơn ngẫu nhiên.`, `p vs random = ${f(p, 3)} (≥0.05): not better than chance.`));
  if (pbo != null && pbo > 0.5) flags.push(t(`PBO ${f(pbo)} > 0,5: nguy cơ quá khớp cao.`, `PBO ${f(pbo)} > 0.5: high overfitting risk.`));
  if (dsr != null && dsr < 0.95) flags.push(t(`DSR ${f(dsr)} < 0,95: chưa vững sau hiệu chỉnh số lần thử.`, `DSR ${f(dsr)} < 0.95: not robust after multiple-testing adjustment.`));
  const honesty = Array.isArray(d.honesty) ? d.honesty.map((x) => (typeof x === "string" ? x : JSON.stringify(x))) : [];

  const [lock, setLock] = useState(false), [cf, setCf] = useState(""), [busy, setBusy] = useState(false), [res, setRes] = useState(null);
  const isMaster = role === "master";
  const openLocked = async () => {
    setBusy(true); setRes(null);
    try { await cpost(`/rooms/${encodeURIComponent(rid)}/final-test`, { scenario_id: id, confirm: cf }); setRes({ ok: true }); } catch (e) { setRes({ err: e.message }); } finally { setBusy(false); }
  };
  const Icon = kind === "pos" ? Info : AlertTriangle;
  const rows = [
    [t("Số lệnh", "Trades"), trades ?? "—", t("walk-forward dev, ngoài mẫu, đã trừ chi phí", "walk-forward dev, out-of-sample, net of costs")],
    [t("Kỳ vọng mỗi lệnh", "Expectancy per trade"), R(exp), wr != null ? `${t("Tỷ lệ thắng", "Win rate")} ${Math.round(wr * (wr <= 1 ? 100 : 1))}%` : null],
    [t("Khoảng tin cậy 95%", "95% confidence interval"), lo != null && hi != null ? `${R(lo)} … ${R(hi)}` : "—", ciCross ? t("chứa 0", "contains 0") : null],
    [t("So với ngẫu nhiên", "Versus random"), p == null ? "—" : `p = ${f(p, 3)}`, base != null ? `${t("ngẫu nhiên", "random")}: ${R(base)}` : (p != null && p >= 0.05 ? t("chưa hơn ngẫu nhiên", "not better than chance") : null)],
    ["PBO", pbo == null ? "—" : f(pbo), t("xác suất quá khớp, càng thấp càng tốt", "overfit probability, lower is better")],
    ["DSR", dsr == null ? "—" : f(dsr), t("hiệu chỉnh số lần thử, cần ≥0,95", "multiple-testing adjusted, want ≥0.95")],
    ...(dd != null ? [[t("Sụt vốn tối đa", "Max drawdown"), `${f(dd)}R`, null]] : []),
  ];
  const sendExplain = () => onSend?.(`/giai-thich ${id ? `${id} ` : ""}${t("Giải thích kết quả test này bằng lời đơn giản: vì sao ra như vậy và tôi nên làm rõ điều gì trong kịch bản?", "Explain this test result in plain words: why it came out like this and what should I clarify in the scenario?")}`.trim());

  return (
    <section className="tr" aria-label={t("Kết quả test", "Test result")}>
      <div className="tr-head"><b className="text-[13.5px]">{t("Kết quả test trung thực", "Honest test result")}</b>{id && <code className="text-[11.5px] text-muted">{id}</code>}</div>
      <div className={`tr-warn ${kind === "down" ? "" : kind}`} role="alert">
        <Icon size={18} aria-hidden="true" style={{ color: kind === "down" ? "var(--down)" : kind === "pos" ? "var(--info)" : "var(--accent)" }} />
        <div><b>{title}</b><p className="m-0 mt-1 text-[12.5px]">{body}</p></div>
      </div>
      <table className="tr-tbl"><caption className="sr-only">{t("Số liệu kết quả test", "Test result figures")}</caption>
        <tbody>{rows.map(([k, v, s]) => <tr key={k}><th scope="row">{k}</th><td>{v}{s && <small>{s}</small>}</td></tr>)}</tbody>
      </table>
      <div><div className="text-[12px] text-muted mb-1">{t("Đường vốn (R luỹ kế, dev)", "Equity curve (cumulative R, dev)")}</div>
        <Equity pts={eq} label={{ none: t("Chưa có dữ liệu đường vốn.", "No equity curve data."), eq: t("Đường vốn", "Equity curve"), end: t("cuối", "end"), n: t("điểm", "points") }} /></div>
      {(flags.length > 0 || honesty.length > 0) && (
        <ul className="m-0 pl-0 list-none grid gap-1 text-[12.5px]">
          {[...flags, ...honesty].map((x, i) => <li key={i} className="flex gap-1.5"><AlertTriangle size={13} className="shrink-0 mt-0.5 text-down" aria-hidden="true" /><span>{x}</span></li>)}
        </ul>
      )}
      <p className="m-0 text-[12px] text-muted">{d.disclaimer || t("Không phải khuyến nghị đầu tư; không hứa lợi nhuận. Chỉ nghiên cứu/paper.", "Not investment advice; no promise of profit. Research/paper only.")}</p>
      <div className="tr-actions">
        {onSend && <button type="button" className="btn" onClick={sendExplain}><MessageCircleQuestion size={14} aria-hidden="true" />{t("Hỏi AI giải thích", "Ask AI to explain")}</button>}
        {onEdit && <button type="button" className="btn ghost" onClick={() => onEdit(d)}><Pencil size={14} aria-hidden="true" />{t("Sửa kịch bản & chạy lại", "Edit scenario & re-run")}</button>}
        {id && <a className="btn ghost" href={`/api/v1/ai-trading/ledger.csv?strategy=${encodeURIComponent(id)}&source=backtest_dev`} download><Download size={14} aria-hidden="true" />{t("Tải sổ lệnh (CSV)", "Download trade ledger (CSV)")}</a>}
        {isMaster && id && <button type="button" className="btn ghost" aria-expanded={lock} onClick={() => setLock(!lock)}><Lock size={14} aria-hidden="true" />{t("Mở test khoá (một lần)", "Open locked test (once)")}</button>}
      </div>
      {isMaster && id && lock && (
        <div className="tr-lock">
          <p className="m-0"><b>{t("Bước 1/2 — hiểu rõ:", "Step 1/2 — understand:")}</b> {t("test khoá chỉ mở MỘT lần cho id này, có ghi nhật ký, và sau đó không được chỉnh luật theo kết quả. Kết quả không có edge là bình thường.", "the locked test opens ONLY ONCE for this id, is logged, and rules must not be tuned afterwards. A no-edge result is normal.")}</p>
          <label className="m-0"><b>{t("Bước 2/2 — gõ lại đúng id", "Step 2/2 — retype the exact id")}</b> <code>{id}</code></label>
          <div className="row">
            <input className="cr-inp" value={cf} onChange={(e) => setCf(e.target.value)} autoComplete="off" spellCheck={false} aria-label={t("Gõ lại id để xác nhận", "Retype id to confirm")} />
            <button type="button" className="btn" disabled={busy || cf !== id} onClick={openLocked} style={{ minHeight: 40 }}>{t("Mở test khoá", "Open locked test")}</button>
          </div>
          {res?.ok && <p role="status" className="m-0 text-up">{t("Đã yêu cầu mở test khoá. Kết quả sẽ hiện trong phòng.", "Locked test requested. The result will appear in the room.")}</p>}
          {res?.err && <p role="alert" className="m-0 text-down">{res.err}</p>}
        </div>
      )}
    </section>
  );
}
