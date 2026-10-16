// Chi tiết một phương pháp: Tổng quan (tiến độ, sơ đồ, kịch bản + quản lý), Quy tắc kết hợp, Phòng phương pháp, Kế hoạch áp dụng.
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Unlink } from "lucide-react";
import { Chip } from "../ui";
import { mget, mwrite, enc, ROLES, roleLabel, normMethod, normScenario, normRelation, normPlan } from "./methodsApi";
import MethodDiagram from "./MethodDiagram";
import MethodRelations from "./MethodRelations";
import MethodRoom from "./MethodRoom";
import MethodPlan, { PlanBar, Verdict } from "./MethodPlan";
import { hhmm } from "./ctx";

const VERD = { edge: ["Có edge (cần kiểm chứng thêm)", "Edge found (needs more checks)", "up"], no_edge: ["Không có edge", "No edge", "down"], unproven: ["Chưa chứng minh", "Unproven", "accent"] };

function ScenarioTable({ scenarios, t, lang, onOpen, canEdit, onRole, onRemove }) {
  if (!scenarios.length) return <p className="m-0 text-[12.5px] text-muted" role="note">{t("Chưa có kịch bản. Tạo kịch bản mới hoặc gắn phòng có sẵn vào phương pháp này.", "No scenarios yet. Create one or attach an existing room to this method.")}</p>;
  const en = lang === "en";
  return (
    <div className="cm-scroll"><table className="cm-tbl"><caption className="cm-sr">{t("Danh sách kịch bản", "Scenario list")}</caption>
      <thead><tr><th scope="col">{t("Kịch bản", "Scenario")}</th><th scope="col">{t("Vai", "Role")}</th><th scope="col">{t("Độ rõ", "Clarity")}</th><th scope="col">{t("Kết quả test", "Test result")}</th><th scope="col">Paper</th><th scope="col"><span className="cm-sr">{t("Thao tác", "Actions")}</span></th></tr></thead>
      <tbody>{scenarios.map((s) => {
        const v = VERD[s.test.verdict];
        return (<tr key={s.rid}>
          <td><b>{s.title || s.rid}</b>{s.labels.of != null && <div className="text-muted text-[11.5px]">{t("Nhãn", "Labels")} {s.labels.n ?? 0}/{s.labels.of}{s.labels.precision != null ? ` · ${t("chính xác", "precision")} ${(s.labels.precision * 100).toFixed(0)}%` : ""}</div>}</td>
          <td>{canEdit ? <select className="cr-inp" style={{ minHeight: 40, minWidth: 110 }} aria-label={`${t("Vai", "Role")}: ${s.title}`} value={s.role} onChange={(e) => onRole(s, e.target.value)}>{ROLES.map((r) => <option key={r[0]} value={r[0]}>{en ? r[2] : r[1]}</option>)}</select> : roleLabel(s.role, en)}</td>
          <td className="num">{s.clarity != null ? `${s.clarity}/100` : "—"}</td>
          <td>{v ? <Chip tone={v[2]}>{en ? v[1] : v[0]}</Chip> : <span className="text-muted">{t("Chưa có", "None yet")}</span>}{s.test.trades != null && <div className="text-muted text-[11.5px] num">{s.test.trades} {t("lệnh", "trades")}{s.test.expectancy != null ? ` · ${s.test.expectancy.toFixed(2)}R` : ""}</div>}</td>
          <td className="num">{s.paper.trades ? `${s.paper.trades} ${t("lệnh", "trades")}, ${s.paper.weeks ?? 0} ${t("tuần", "wk")}` : <span className="text-muted">{t("Chưa chạy", "Not started")}</span>}</td>
          <td><div className="flex gap-1 flex-wrap"><button type="button" className="btn ghost cm-btn" onClick={() => onOpen(s.rid)}>{t("Mở phòng", "Open room")}</button>{canEdit && <button type="button" className="btn ghost cm-btn" onClick={() => onRemove(s)} aria-label={`${t("Tách khỏi phương pháp", "Detach")}: ${s.title}`}><Unlink size={14} aria-hidden="true" /></button>}</div></td>
        </tr>);
      })}</tbody></table></div>
  );
}

function AddScenario({ mid, t, lang, attached, onDone }) {
  const [mode, setMode] = useState("new"), [title, setTitle] = useState(""), [room, setRoom] = useState(""), [role, setRole] = useState("core"), [err, setErr] = useState(null), [busy, setBusy] = useState(false), [open, setOpen] = useState(false);
  const rq = useQuery({ queryKey: ["cls", "rooms"], enabled: open && mode === "old", queryFn: ({ signal }) => mget("/rooms", {}, signal), retry: false });
  const rooms = (rq.data?.items || []).filter((r) => !attached.includes(r.id));
  const go = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null);
    const body = mode === "new" ? { new: { title: title.trim().slice(0, 120) }, role } : { room_id: room, role };
    try { await mwrite("POST", `/methods/${enc(mid)}/scenarios`, body); setTitle(""); setRoom(""); setOpen(false); onDone(); }
    catch (x) { if (x.status === 409 && window.confirm(t("Phòng này đang thuộc phương pháp khác. Chuyển sang phương pháp này? (phòng và lịch sử được giữ nguyên)", "This room belongs to another method. Move it here? (room and history are kept)"))) { try { await mwrite("POST", `/methods/${enc(mid)}/scenarios`, { ...body, move: true }); setOpen(false); onDone(); } catch (y) { setErr(y.message); } } else setErr(x.message); }
    finally { setBusy(false); }
  };
  if (!open) return <button type="button" className="btn cm-btn justify-self-start" onClick={() => setOpen(true)}><Plus size={14} aria-hidden="true" />{t("Thêm kịch bản", "Add scenario")}</button>;
  const en = lang === "en";
  return (
    <form className="cr-card cm-form" onSubmit={go} aria-label={t("Thêm kịch bản", "Add scenario")}>
      <div className="flex gap-1" role="group" aria-label={t("Cách thêm", "How to add")}>{[["new", t("Tạo kịch bản mới", "Create new")], ["old", t("Gắn phòng có sẵn", "Attach existing room")]].map(([k, l]) => <button key={k} type="button" className={`cm-tab ${mode === k ? "on" : ""}`} aria-pressed={mode === k} onClick={() => setMode(k)}>{l}</button>)}</div>
      {mode === "new" ? <label>{t("Tên kịch bản (3-120 ký tự)", "Scenario name (3-120 chars)")}<input className="cr-inp" style={{ minHeight: 40 }} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} required /></label>
        : <label>{t("Phòng", "Room")}<select className="cr-inp" style={{ minHeight: 40 }} value={room} onChange={(e) => setRoom(e.target.value)} required><option value="">{t("— chọn phòng —", "— pick a room —")}</option>{rooms.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label>}
      <label>{t("Vai trong phương pháp", "Role in the method")}<select className="cr-inp" style={{ minHeight: 40 }} value={role} onChange={(e) => setRole(e.target.value)}>{ROLES.map((r) => <option key={r[0]} value={r[0]}>{en ? r[2] : r[1]}</option>)}</select></label>
      <div className="flex gap-2"><button type="submit" className="btn cm-btn" disabled={busy || (mode === "new" ? title.trim().length < 3 : !room)}>{t("Thêm", "Add")}</button><button type="button" className="btn ghost cm-btn" onClick={() => setOpen(false)}>{t("Huỷ", "Cancel")}</button></div>
      {err && <p role="alert" className="m-0 text-[12px] text-down">{err}</p>}
    </form>
  );
}

export default function MethodView({ mid, t, lang, me, isMaster, onOpenRoom, onEdit }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState("overview"), [err, setErr] = useState(null);
  const mq = useQuery({ queryKey: ["cls", "m", mid, "detail"], queryFn: ({ signal }) => mget(`/methods/${enc(mid)}`, {}, signal), refetchInterval: 15000, retry: false });
  const rq = useQuery({ queryKey: ["cls", "m", mid, "rel"], queryFn: ({ signal }) => mget(`/methods/${enc(mid)}/relations`, {}, signal), retry: false });
  const pq = useQuery({ queryKey: ["cls", "m", mid, "plan"], queryFn: ({ signal }) => mget(`/methods/${enc(mid)}/plan`, {}, signal), refetchInterval: 20000, retry: false });
  const method = useMemo(() => normMethod(mq.data || {}), [mq.data]);
  const scenarios = useMemo(() => (mq.data?.scenarios || []).map(normScenario).filter((s) => s.rid), [mq.data]);
  const relations = useMemo(() => (rq.data?.relations || mq.data?.relations || []).map(normRelation), [rq.data, mq.data]);
  const plan = useMemo(() => normPlan(pq.data || {}, lang), [pq.data, lang]);
  const canEdit = isMaster || (!!method.owner && method.owner === me.user_id);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["cls", "m", mid] }); qc.invalidateQueries({ queryKey: ["cls", "methods"] }); };
  const setRole = async (s, role) => { setErr(null); try { await mwrite("PATCH", `/methods/${enc(mid)}/scenarios/${enc(s.rid)}`, { role }); refresh(); } catch (e) { setErr(e.message); } };
  const remove = async (s) => { if (!window.confirm(t(`Tách «${s.title}» khỏi phương pháp? Phòng và lịch sử được giữ nguyên; các quy tắc liên quan bị xoá.`, `Detach “${s.title}” from the method? The room and history are kept; related rules are removed.`))) return; setErr(null); try { await mwrite("DELETE", `/methods/${enc(mid)}/scenarios/${enc(s.rid)}`); refresh(); } catch (e) { setErr(e.message); } };
  const TABS = [["overview", t("Tổng quan", "Overview")], ["rules", t("Quy tắc kết hợp", "Rules")], ["room", t("Phòng phương pháp", "Method room")], ["plan", `${t("Kế hoạch áp dụng", "Application plan")} ${plan.passed}/${plan.total}`]];
  if (mq.isError) return <p className="m-3 text-[13px] text-muted" role="alert">{mq.error?.status === 404 ? t("Không tìm thấy phương pháp (hoặc bạn không có quyền).", "Method not found (or you lack access).") : mq.error?.message}</p>;
  return (
    <div>
      <header className="p-3 grid gap-1 border-b border-line">
        <div className="flex items-center gap-2 flex-wrap"><h2 className="m-0 text-[16px] font-semibold min-w-0 break-words">{method.name || "…"}</h2>{method.version != null && <Chip>v{method.version}</Chip>}{canEdit && <button type="button" className="btn ghost cm-btn ml-auto" onClick={() => onEdit?.(method)}>{t("Sửa thông tin", "Edit details")}</button>}</div>
        {method.description && <p className="m-0 text-[12.5px] text-muted">{method.description}</p>}
        <p className="m-0 text-[11.5px] text-faint">{method.ownerName && `${t("Chủ sở hữu", "Owner")}: ${method.ownerName}`}{method.updated_at ? ` · ${hhmm(method.updated_at)}` : ""}{method.clarityAvg != null ? ` · ${t("độ rõ TB", "avg clarity")} ${method.clarityAvg}` : ""}</p>
      </header>
      <div className="cm-tabs" role="tablist" aria-label={t("Phương pháp", "Method")}>
        {TABS.map(([k, l]) => <button key={k} type="button" role="tab" id={`cm-t-${k}`} aria-selected={tab === k} aria-controls={`cm-p-${k}`} className={`cm-tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      <div className="cm-pad" role="tabpanel" id={`cm-p-${tab}`} aria-labelledby={`cm-t-${tab}`}>
        {tab === "overview" && (<>
          <PlanBar plan={plan} t={t} />
          <Verdict plan={plan} t={t} />
          <section aria-label={t("Sơ đồ", "Diagram")} className="grid gap-2"><h3 className="m-0 text-[13.5px] font-semibold">{t("Sơ đồ kịch bản và quan hệ", "Scenarios and relations")}</h3><MethodDiagram scenarios={scenarios} relations={relations} t={t} lang={lang} onOpen={onOpenRoom} /></section>
          <section aria-label={t("Kịch bản", "Scenarios")} className="grid gap-2"><h3 className="m-0 text-[13.5px] font-semibold">{t("Kịch bản trong phương pháp", "Scenarios in this method")}</h3>
            <ScenarioTable scenarios={scenarios} t={t} lang={lang} onOpen={onOpenRoom} canEdit={canEdit} onRole={setRole} onRemove={remove} />
            {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
            {canEdit && <AddScenario mid={mid} t={t} lang={lang} attached={scenarios.map((s) => s.rid)} onDone={refresh} />}
          </section>
        </>)}
        {tab === "rules" && <MethodRelations mid={mid} scenarios={scenarios} relations={relations} t={t} lang={lang} onSaved={refresh} readOnly={!canEdit} />}
        {tab === "room" && <MethodRoom mid={mid} lang={lang} t={t} me={me} isMaster={isMaster} />}
        {tab === "plan" && <MethodPlan mid={mid} plan={plan} t={t} lang={lang} onOpenRoom={onOpenRoom} onGoTab={setTab} onChanged={refresh} canEdit={canEdit} isMaster={isMaster} />}
      </div>
    </div>
  );
}
