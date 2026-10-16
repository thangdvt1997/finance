// Màn "Phương pháp" của AI Training Class: danh sách phương pháp (tạo/ sửa/ xoá mềm) + chi tiết. Chỉ nghiên cứu/paper.
// Props: lang, onOpenRoom(rid) (mặc định: ghi phòng đã chọn rồi gọi onGoRooms()), onGoRooms().
import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Workflow } from "lucide-react";
import { cn, Chip } from "../ui";
import { EmptyState } from "../ux/States";
import { fetchMe } from "../../lib/clientsApi";
import { mget, mwrite, enc, normMethod } from "./methodsApi";
import { hhmm } from "./ctx";
import MethodView from "./MethodView";
import "./classroom.css";
import "./methods.css";

function MethodForm({ init, t, onDone, onCancel }) {
  const [name, setName] = useState(init?.name || ""), [desc, setDesc] = useState(init?.description || ""), [busy, setBusy] = useState(false), [err, setErr] = useState(null);
  const submit = async (e) => {
    e.preventDefault(); if (name.trim().length < 3) return; setBusy(true); setErr(null);
    try { const body = { name: name.trim().slice(0, 80), description: desc.trim().slice(0, 600) }; const r = init ? await mwrite("PATCH", `/methods/${enc(init.id)}`, body) : await mwrite("POST", "/methods", body); onDone(r); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <form className="cr-card cm-form" onSubmit={submit} aria-label={init ? t("Sửa phương pháp", "Edit method") : t("Tạo phương pháp", "Create method")}>
      <label>{t("Tên phương pháp (3-80 ký tự)", "Method name (3-80 chars)")}<input className="cr-inp" style={{ minHeight: 40 }} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      <label>{t("Mô tả: khi nào dùng, ý chính", "Description: when to use, key idea")}<textarea className="cr-inp" rows={3} value={desc} maxLength={600} onChange={(e) => setDesc(e.target.value)} /></label>
      <div className="flex gap-2"><button type="submit" className="btn cm-btn" disabled={busy || name.trim().length < 3}>{init ? t("Lưu", "Save") : t("Tạo", "Create")}</button><button type="button" className="btn ghost cm-btn" onClick={onCancel}>{t("Huỷ", "Cancel")}</button></div>
      {err && <p role="alert" className="m-0 text-[12px] text-down">{err}</p>}
    </form>
  );
}

export default function MethodsPage({ lang = "vi", onOpenRoom, onGoRooms }) {
  const t = useCallback((vi, en) => (lang === "en" ? en : vi), [lang]);
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 300_000, retry: false }).data || {};
  const isMaster = me.role === "master";
  const [sel, setSel] = useState(() => { try { return localStorage.getItem("cm-sel") || ""; } catch { return ""; } });
  const [form, setForm] = useState(null), [msg, setMsg] = useState(null), [mobileDetail, setMobileDetail] = useState(false);
  const lq = useQuery({ queryKey: ["cls", "methods"], queryFn: ({ signal }) => mget("/methods", {}, signal), refetchInterval: 15000, retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500) });
  const items = (lq.data?.items || (Array.isArray(lq.data) ? lq.data : [])).map(normMethod).filter((m) => m.id);
  const pick = (id) => { setSel(id); setMobileDetail(true); try { localStorage.setItem("cm-sel", id); } catch { /* bỏ */ } };
  const cur = items.find((m) => m.id === sel);
  const openRoom = (rid) => { if (onOpenRoom) return onOpenRoom(rid); try { localStorage.setItem("cr-room", rid); } catch { /* bỏ */ } onGoRooms?.(); return undefined; };
  const reload = () => qc.invalidateQueries({ queryKey: ["cls", "methods"] });
  const del = async (m) => { if (!window.confirm(t(`Xoá phương pháp «${m.name}»? Các phòng kịch bản và lịch sử được giữ nguyên, chỉ tách khỏi phương pháp.`, `Delete method “${m.name}”? Scenario rooms and history are kept, only detached.`))) return; try { await mwrite("DELETE", `/methods/${enc(m.id)}`); setMsg(t("Đã xoá phương pháp (phòng được giữ lại).", "Method deleted (rooms kept).")); if (sel === m.id) setSel(""); reload(); } catch (e) { setMsg(e.message); } };

  return (
    <div className="cm" aria-label={t("Phương pháp giao dịch", "Trading methods")}>
      <aside className={cn("cm-list", mobileDetail && sel && "hide-m")}>
        <div className="flex items-center gap-2 p-2 border-b border-line">
          <b className="text-[13px] flex items-center gap-1"><Workflow size={14} aria-hidden="true" />{t("Phương pháp", "Methods")}</b>
          <button type="button" className="btn cm-btn ml-auto" onClick={() => setForm({})} aria-expanded={!!form}><Plus size={14} aria-hidden="true" />{t("Tạo mới", "New")}</button>
        </div>
        {form && !form.id && <div className="p-2"><MethodForm t={t} onCancel={() => setForm(null)} onDone={(r) => { setForm(null); reload(); const id = String(r?.id ?? ""); if (id) pick(id); }} /></div>}
        {msg && <p role="status" className="m-0 px-3 py-1 text-[12px] text-muted">{msg}</p>}
        {lq.isError && <p role="alert" className="m-0 p-3 text-[12.5px] text-muted">{lq.error?.status === 404 || lq.error?.status >= 502 ? t("Dịch vụ Phương pháp chưa sẵn sàng. Trang sẽ tự tải lại.", "The Methods service is not ready. The page reloads automatically.") : lq.error?.message}</p>}
        {lq.isPending && <p className="m-0 p-3 text-[12.5px] text-muted" role="status">{t("Đang tải…", "Loading…")}</p>}
        {lq.isSuccess && !items.length && <p className="m-0 p-3 text-[12.5px] text-muted" role="note">{t("Chưa có phương pháp nào. Phương pháp gom nhiều kịch bản, quy tắc kết hợp và kế hoạch áp dụng. Bấm Tạo mới.", "No methods yet. A method groups scenarios, combination rules and an application plan. Click New.")}</p>}
        <ul>{items.map((m) => (
          <li key={m.id}>
            <button type="button" className={cn("cm-item", m.id === sel && "on")} aria-current={m.id === sel} onClick={() => pick(m.id)}>
              <span className="flex items-center gap-1 min-w-0"><b className="truncate text-[13px]">{m.name}</b>{m.version != null && <Chip>v{m.version}</Chip>}</span>
              <span className="text-[11.5px] text-muted">{m.scenarios != null ? `${m.scenarios} ${t("kịch bản", "scenarios")}` : ""}{m.plan.passed != null ? ` · ${t("kế hoạch", "plan")} ${m.plan.passed}/${m.plan.total}` : ""}{m.updated_at ? ` · ${hhmm(m.updated_at)}` : ""}</span>
            </button>
            {m.id === sel && (isMaster || m.owner === me.user_id) && <div className="px-2 pb-2"><button type="button" className="btn ghost cm-btn" onClick={() => del(m)}><Trash2 size={14} aria-hidden="true" />{t("Xoá (phòng được giữ lại)", "Delete (rooms are kept)")}</button></div>}
          </li>
        ))}</ul>
      </aside>
      <section className={cn("cm-main", !(mobileDetail && sel) && "hide-m")} aria-label={t("Chi tiết phương pháp", "Method details")}>
        {mobileDetail && sel && <button type="button" className="btn ghost cm-btn cm-back m-2" onClick={() => setMobileDetail(false)}>← {t("Danh sách", "List")}</button>}
        {form?.id && <div className="p-2"><MethodForm init={form} t={t} onCancel={() => setForm(null)} onDone={() => { setForm(null); reload(); qc.invalidateQueries({ queryKey: ["cls", "m", form.id] }); }} /></div>}
        {sel && cur ? <MethodView key={sel} mid={sel} t={t} lang={lang} me={me} isMaster={isMaster} onOpenRoom={openRoom} onEdit={(m) => setForm(m)} />
          : <div className="p-4"><EmptyState compact title={t("Chọn hoặc tạo một phương pháp", "Pick or create a method")} hint={t("Phương pháp = nhiều kịch bản liên kết + quy tắc kết hợp + kế hoạch áp dụng. Kế hoạch ghi trung thực khi chưa đủ điều kiện.", "A method = linked scenarios + combination rules + an application plan. The plan states honestly when it is not yet eligible.")} /></div>}
      </section>
    </div>
  );
}
