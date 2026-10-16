// Bảng quy tắc kết hợp giữa các kịch bản (sửa được, lưu bằng PUT cả danh sách). Chỉ master/ chuyên gia sở hữu sửa; lỗi máy chủ hiện nguyên văn.
import { useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { mwrite, enc, REL_KINDS, REL_BY, REGIMES, relToApi } from "./methodsApi";

export default function MethodRelations({ mid, scenarios, relations, t, lang, onSaved, readOnly }) {
  const [rows, setRows] = useState(relations), [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [err, setErr] = useState(null), [ok, setOk] = useState(false), [warn, setWarn] = useState([]);
  useEffect(() => { if (!dirty) setRows(relations); }, [relations, dirty]);
  const set = (i, p) => { setRows((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x))); setDirty(true); setOk(false); };
  const add = () => { setRows((r) => [...r, { id: `new${Date.now()}`, kind: "complementary", a: scenarios[0]?.rid || "", b: scenarios[1]?.rid || "", regime: "", note: "" }]); setDirty(true); };
  const del = (i) => { setRows((r) => r.filter((_, j) => j !== i)); setDirty(true); };
  const needB = (r) => REL_BY[r.kind]?.[6] !== false;
  const bad = rows.some((r) => !r.a || (needB(r) && (!r.b || r.a === r.b)) || (r.kind === "regime" && !r.regime));
  const save = async () => {
    setBusy(true); setErr(null);
    try { const x = await mwrite("PUT", `/methods/${enc(mid)}/relations`, { relations: rows.map(relToApi) }); setWarn(x?.warnings || []); setDirty(false); setOk(true); onSaved?.(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const opts = scenarios.map((s) => <option key={s.rid} value={s.rid}>{s.title || s.rid}</option>);
  return (
    <section className="grid gap-2" aria-label={t("Quy tắc kết hợp", "Combination rules")}>
      <div className="flex items-center gap-2 flex-wrap">
        <h3 className="m-0 text-[13.5px] font-semibold">{t("Quy tắc kết hợp giữa các kịch bản", "Rules for combining scenarios")}</h3>
        {!readOnly && <span className="ml-auto flex gap-1"><button type="button" className="btn ghost cm-btn" onClick={add} disabled={scenarios.length < 2}><Plus size={14} aria-hidden="true" />{t("Thêm quy tắc", "Add rule")}</button><button type="button" className="btn cm-btn" onClick={save} disabled={busy || !dirty || bad}><Save size={14} aria-hidden="true" />{t("Lưu", "Save")}</button></span>}
      </div>
      <p className="m-0 text-[12px] text-muted">{t("Loại trừ, bổ trợ, ưu tiên, regime, đối xứng mua/bán, khung xác nhận. AI dùng các quy tắc này khi nhiều tín hiệu cùng xuất hiện.", "Exclusive, complementary, priority, regime, buy/sell mirror, confirmation timeframe. The AI applies them when several signals fire together.")}</p>
      {scenarios.length < 2 && <p className="m-0 text-[12.5px] text-muted" role="note">{t("Cần ít nhất 2 kịch bản để đặt quy tắc.", "You need at least 2 scenarios to set a rule.")}</p>}
      {rows.length === 0 && scenarios.length >= 2 && <p className="m-0 text-[12.5px] text-muted" role="note">{t("Chưa có quy tắc nào. Bấm Thêm quy tắc, hoặc nói với AI trong Phòng phương pháp.", "No rules yet. Click Add rule, or tell the AI in the Method room.")}</p>}
      <ul className="m-0 p-0 list-none grid gap-2">
        {rows.map((r, i) => (
          <li key={r.id} className="cr-card m-0 cm-form" aria-label={`${t("Quy tắc", "Rule")} ${i + 1}`}>
            <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))" }}>
              <label>{t("Loại", "Type")}<select className="cr-inp" style={{ minHeight: 40 }} disabled={readOnly} value={r.kind} onChange={(e) => set(i, { kind: e.target.value })}>{REL_KINDS.map((k) => <option key={k[0]} value={k[0]}>{lang === "en" ? k[2] : k[1]}</option>)}</select></label>
              <label>{r.kind === "priority" ? t("A (ưu tiên hơn)", "A (higher priority)") : r.kind === "timeframe" ? t("A (khung chính)", "A (main timeframe)") : t("Kịch bản A", "Scenario A")}<select className="cr-inp" style={{ minHeight: 40 }} disabled={readOnly} value={r.a} onChange={(e) => set(i, { a: e.target.value })}>{opts}</select></label>
              {needB(r) && <label>{r.kind === "timeframe" ? t("B (khung xác nhận)", "B (confirming)") : t("Kịch bản B", "Scenario B")}<select className="cr-inp" style={{ minHeight: 40 }} disabled={readOnly} value={r.b} onChange={(e) => set(i, { b: e.target.value })}>{opts}</select></label>}
              {r.kind === "regime" && <label>{t("Regime", "Regime")}<select className="cr-inp" style={{ minHeight: 40 }} disabled={readOnly} value={r.regime} onChange={(e) => set(i, { regime: e.target.value })}><option value="">{t("— chọn —", "— pick —")}</option>{REGIMES.map((g) => <option key={g[0]} value={g[0]}>{lang === "en" ? g[2] : g[1]}</option>)}</select></label>}
            </div>
            <label>{t("Ghi chú / điều kiện", "Note / condition")}<input className="cr-inp" style={{ minHeight: 40 }} disabled={readOnly} maxLength={200} value={r.note} onChange={(e) => set(i, { note: e.target.value })} /></label>
            <div className="flex items-center gap-2"><span className="text-[11.5px] text-muted flex-1">{REL_BY[r.kind] ? t(REL_BY[r.kind][3], REL_BY[r.kind][4]) : ""}</span>{!readOnly && <button type="button" className="btn ghost cm-btn" onClick={() => del(i)} aria-label={`${t("Xoá quy tắc", "Delete rule")} ${i + 1}`}><Trash2 size={14} aria-hidden="true" />{t("Xoá", "Delete")}</button>}</div>
            {needB(r) && r.a && r.a === r.b && <p role="alert" className="m-0 text-[12px] text-down">{t("A và B phải khác nhau.", "A and B must differ.")}</p>}
          </li>
        ))}
      </ul>
      {warn.length > 0 && <ul className="m-0 pl-5 text-[12px] text-muted" role="status">{warn.map((w, i) => <li key={i}>{String(w)}</li>)}</ul>}
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
      {ok && <p role="status" className="m-0 text-[12.5px] text-up">{t("Đã lưu quy tắc.", "Rules saved.")}</p>}
    </section>
  );
}
