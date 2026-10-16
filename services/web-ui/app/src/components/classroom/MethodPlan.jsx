// Kế hoạch áp dụng: pipeline 9 bước + biển cảnh báo trung thực. Không hiện "sẵn sàng" khi chưa qua bước 4-6 (normPlan cũng chặn ở client).
import { useState } from "react";
import { Download, RefreshCw, ShieldCheck } from "lucide-react";
import { Chip } from "../ui";
import { STEP_ST, VERDICT_TONE, mwrite, enc } from "./methodsApi";
import { hhmm } from "./ctx";

export function PlanBar({ plan, t }) {
  const pct = Math.round((plan.passed / plan.total) * 100);
  return (
    <div className="grid gap-1" aria-label={t("Tiến độ kế hoạch", "Plan progress")}>
      <div className="flex items-center gap-2 text-[12.5px]"><b>{t("Kế hoạch áp dụng", "Application plan")}</b><span className="num">{plan.passed}/{plan.total} {t("bước đạt", "steps passed")}</span></div>
      <div className="cm-bar" role="progressbar" aria-valuemin={0} aria-valuemax={plan.total} aria-valuenow={plan.passed} aria-label={`${plan.passed}/${plan.total}`}><i style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export function Verdict({ plan, t }) {
  const ready = plan.code === "ready", review = plan.code === "eligible_review";
  if (ready || review) {
    return (
      <div className={ready ? "cm-ok" : "cm-warn"} role="status" style={review ? { borderColor: "var(--accent)", background: "var(--accent-bg)" } : undefined}>
        <b className="text-[14px]">{ready ? t("Đủ điều kiện áp dụng (nghiên cứu/paper)", "Eligible to apply (research/paper)") : t("Đã qua bước 4-6; còn chờ paper, duyệt và tài liệu", "Steps 4-6 passed; paper, approval and document still pending")}</b>
        <p className="m-0 text-[12.5px]">{plan.note || t("Chỉ nghiên cứu/paper; vốn thật cần cổng pháp lý G1-G3.", "Research/paper only; real capital needs legal gates G1-G3.")}</p>
      </div>
    );
  }
  return (
    <div className="cm-warn" role="alert">
      <b className="t">⚠ {t("CHƯA đủ điều kiện áp dụng", "NOT yet eligible to apply")}</b>
      <p className="m-0 text-[12.5px]">{t("Phương pháp chưa qua các bước 4-6 (backtest trung thực, ổn định, guardrail). Điều này không hàm ý có lợi nhuận; số liệu thật được hiển thị nguyên trạng.", "The method has not passed steps 4-6 (honest backtest, stability, guardrails). This implies no profitability; real figures are shown as they are.")}</p>
      {plan.reasons.length > 0 && <ul className="m-0 pl-5 text-[12.5px]" aria-label={t("Lý do", "Reasons")}>{plan.reasons.slice(0, 6).map((r, i) => <li key={i}>{String(r)}</li>)}</ul>}
      <div className="text-[12.5px]"><b>{t("Hướng sửa", "How to fix")}:</b>
        <ul className="m-0 pl-5">{[t("Làm rõ ý tưởng (độ rõ >= 80, xác nhận các hàng bắt buộc)", "Clarify the idea (clarity >= 80, confirm required rows)"), t("Đổi khung/ mã hoặc thêm bộ lọc rồi test lại", "Change timeframe/symbol or add a filter, then retest"), t("Nếu vẫn không có edge sau chi phí: dừng, không ép áp dụng", "If there is still no edge after costs: stop, do not force it")].map((f, i) => <li key={i}>{f}</li>)}</ul></div>
    </div>
  );
}

function Evidence({ mid, t, onDone }) {
  const [kind, setKind] = useState("paper"), [trades, setTrades] = useState(""), [weeks, setWeeks] = useState(""), [exp, setExp] = useState(""), [hc, setHc] = useState(false), [passed, setPassed] = useState(false), [note, setNote] = useState(""), [err, setErr] = useState(null), [busy, setBusy] = useState(false);
  const go = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null);
    const data = kind === "paper" ? { trades: +trades, weeks: +weeks, expectancy_r: +exp, hash_chain_ok: hc } : { passed, scenarios: [] };
    try { await mwrite("POST", `/methods/${enc(mid)}/plan/evidence`, { kind, data, ...(note.trim() ? { note: note.trim().slice(0, 300) } : {}) }); onDone(); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  const num = (v, set, label) => <label>{label}<input className="cr-inp" style={{ minHeight: 40 }} type="number" step="any" value={v} onChange={(e) => set(e.target.value)} required /></label>;
  return (
    <form className="cr-card cm-form" onSubmit={go} aria-label={t("Ghi bằng chứng (master)", "Record evidence (master)")}>
      <b className="text-[12.5px]">{t("Ghi bằng chứng (chỉ master)", "Record evidence (master only)")}</b>
      <label>{t("Loại", "Type")}<select className="cr-inp" style={{ minHeight: 40 }} value={kind} onChange={(e) => setKind(e.target.value)}><option value="paper">Paper forward-test</option><option value="stress">{t("Kiểm tra stress", "Stress check")}</option></select></label>
      {kind === "paper" ? <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))" }}>{num(trades, setTrades, t("Số lệnh", "Trades"))}{num(weeks, setWeeks, t("Số tuần", "Weeks"))}{num(exp, setExp, t("Kỳ vọng (R)", "Expectancy (R)"))}<label className="row"><input type="checkbox" checked={hc} onChange={(e) => setHc(e.target.checked)} />{t("Sổ hash-chain hợp lệ", "Hash-chain valid")}</label></div>
        : <label className="row"><input type="checkbox" checked={passed} onChange={(e) => setPassed(e.target.checked)} />{t("Stress đạt", "Stress passed")}</label>}
      <label>{t("Ghi chú", "Note")}<input className="cr-inp" style={{ minHeight: 40 }} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <button type="submit" className="btn cm-btn justify-self-start" disabled={busy}>{t("Ghi bằng chứng", "Record")}</button>
      {err && <p role="alert" className="m-0 text-[12px] text-down">{err}</p>}
    </form>
  );
}

export default function MethodPlan({ mid, plan, t, lang, onOpenRoom, onGoTab, onChanged, canEdit, isMaster }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState(null), [ev, setEv] = useState(false);
  const recheck = async () => { setBusy(true); setErr(null); try { await mwrite("POST", `/methods/${enc(mid)}/plan/recheck`, {}); onChanged?.(); } catch (e) { setErr(e.message); } finally { setBusy(false); } };
  const approve = async () => { if (!window.confirm(t("Duyệt phương pháp ở phiên bản hiện tại? Việc này chỉ cho phép dùng trong nghiên cứu/paper.", "Approve the method at its current version? This only permits research/paper use."))) return; setBusy(true); setErr(null); try { await mwrite("POST", `/methods/${enc(mid)}/plan/approve`, { approve: true }); onChanged?.(); } catch (e) { setErr(e.message); } finally { setBusy(false); } };
  const exp = (fmt) => `/api/v1/ai-trading/class/methods/${enc(mid)}/plan/export?format=${fmt}`;
  const act = (s) => { const a = s.action; if (!a) return null; if (a.room_id && ["open_room", "run_test"].includes(a.kind)) return () => onOpenRoom?.(a.room_id); if (a.kind === "open_canvas") return () => onGoTab?.("room"); if (a.kind === "open_relations") return () => onGoTab?.("rules"); if (a.kind === "attach_evidence" && isMaster) return () => setEv(true); if (a.kind === "approve" && isMaster) return approve; return null; };
  return (
    <section className="grid gap-3" aria-label={t("Kế hoạch áp dụng", "Application plan")}>
      <PlanBar plan={plan} t={t} />
      <Verdict plan={plan} t={t} />
      <div className="flex gap-2 flex-wrap">
        {canEdit && <button type="button" className="btn ghost cm-btn" onClick={recheck} disabled={busy}><RefreshCw size={14} aria-hidden="true" />{t("Kiểm tra lại các bước", "Re-check steps")}</button>}
        {isMaster && <button type="button" className="btn ghost cm-btn" onClick={() => setEv(!ev)} aria-expanded={ev}><ShieldCheck size={14} aria-hidden="true" />{t("Ghi bằng chứng", "Record evidence")}</button>}
        <a className="btn ghost cm-btn" href={exp("md")} download><Download size={14} aria-hidden="true" />{t("Xuất tài liệu (Markdown)", "Export document (Markdown)")}</a>
        <a className="btn ghost cm-btn" href={exp("pdf")} download><Download size={14} aria-hidden="true" />{t("Xuất PDF", "Export PDF")}</a>
      </div>
      {plan.computed_at && <p className="m-0 text-[11.5px] text-faint">{t("Tính lúc", "Computed")}: {hhmm(plan.computed_at)}</p>}
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
      {ev && isMaster && <Evidence mid={mid} t={t} onDone={() => { setEv(false); onChanged?.(); }} />}
      <ol className="cm-steps">
        {plan.steps.map((s) => {
          const st = STEP_ST[s.status], go = act(s);
          return (
            <li key={s.key} className={`cm-step ${s.status === "passed" ? "done" : s.status}`}>
              <div className="flex items-center gap-2 flex-wrap"><span className="num text-[12px] text-muted" aria-hidden="true">{s.n}</span><b className="text-[13px]">{s.title}</b><Chip tone={st[2]}><span aria-hidden="true">{st[3]} </span>{lang === "en" ? st[1] : st[0]}</Chip></div>
              {s.criteria.length > 0 && (
                <div className="cm-scroll"><table className="cm-tbl"><caption className="cm-sr">{t("Tiêu chí đạt", "Pass criteria")}</caption><thead><tr><th scope="col">{t("Tiêu chí đạt", "Pass criterion")}</th><th scope="col">{t("Yêu cầu", "Required")}</th><th scope="col">{t("Thực tế", "Actual")}</th><th scope="col">{t("Kết quả", "Result")}</th></tr></thead>
                  <tbody>{s.criteria.map((c, i) => <tr key={i}><td>{c.label}</td><td className="num">{c.required ?? "—"}</td><td className="num">{c.actual ?? "—"}</td><td>{c.pass == null ? "—" : c.pass ? <span className="text-up">✓ {t("Đạt", "Pass")}</span> : <span className="text-down">✕ {t("Chưa", "No")}</span>}</td></tr>)}</tbody></table></div>
              )}
              <div className="flex gap-x-3 gap-y-1 flex-wrap text-[11.5px] text-muted">{s.owner && <span>{t("Người chịu trách nhiệm", "Owner")}: {s.owner}</span>}{s.since && <span>{t("Từ", "Since")}: {hhmm(s.since)}</span>}</div>
              {s.evidence.length > 0 ? <ul className="m-0 pl-5 text-[12px]" aria-label={t("Bằng chứng", "Evidence")}>{s.evidence.map((e, i) => <li key={i}>{e.room_id ? <button type="button" className="cr-link cm-linkbtn" onClick={() => onOpenRoom?.(e.room_id)}>{e.label}</button> : e.label}{e.value ? <span className="text-muted"> — {e.value}</span> : null}</li>)}</ul>
                : s.status !== "pending" || s.n > 3 ? <p className="m-0 text-[11.5px] text-muted">{t("Chưa có bằng chứng đính kèm.", "No evidence attached yet.")}</p> : null}
              {s.suggestions.length > 0 && s.status !== "passed" && <ul className="m-0 pl-5 text-[12px]" aria-label={t("Gợi ý", "Suggestions")}>{s.suggestions.map((x, i) => <li key={i}>{String(x)}</li>)}</ul>}
              {go && s.status !== "passed" && <button type="button" className="btn cm-btn justify-self-start" onClick={go}>{s.action.label || t("Làm bước này", "Do this step")}</button>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
