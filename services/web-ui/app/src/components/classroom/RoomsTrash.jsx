// Quản lý phòng: nút thùng rác, chọn nhiều + lọc nhanh, hộp thoại xác nhận (2 bước prepare/confirm), mục Thùng rác, toast Hoàn tác 10 giây.
// Hợp đồng: docs/handoff/ROOMS_TRASH_API.md. Xoá mềm (khôi phục được 30 ngày); xoá vĩnh viễn chỉ master.
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, RotateCcw, Trash2, X } from "lucide-react";
import { apiWrite } from "../../lib/api";
import { cget, cpost } from "./classApi";
import { cn } from "../ui";
import "./trash.css";

const DEMO_RE = /(demo|thử|thu nghiem|thử nghiệm|\btest\b|\bqa\b|e2e|probe|tmp|rác|phòng sell eurusd$)/i;
const DAY = 86400000;
const age = (r) => (Date.now() - new Date(r.updated_at || 0).getTime()) / DAY;
const isEmpty = (r) => (r.msg_count ?? 0) <= 1 && !r.profile_name;
const isDemo = (r) => DEMO_RE.test(r.title || "");
const heavy = (c) => (c?.messages ?? 0) >= 10 || (c?.examples ?? 0) > 0 || (c?.versions ?? 0) > 1 || (c?.labels ?? 0) > 0;
const del = (path) => apiWrite("DELETE", `/ai-trading/class${path}`, undefined);

export function useRoomManager({ t, rooms, rid, isMaster }) {
  const qc = useQueryClient();
  const [selecting, setSel] = useState(false), [sel, setSelSet] = useState(() => new Set()), [days, setDays] = useState(14);
  const [dlg, setDlg] = useState(null), [trashOpen, setTrashOpen] = useState(false), [toast, setToast] = useState(null);
  const tm = useRef(null);
  const trash = useQuery({ queryKey: ["cls", "trash"], queryFn: ({ signal }) => cget("/rooms/trash", {}, signal), refetchInterval: 30000, retry: false });
  const refresh = useCallback(() => { qc.invalidateQueries({ queryKey: ["cls", "rooms"] }); qc.invalidateQueries({ queryKey: ["cls", "trash"] }); }, [qc]);
  const say = useCallback((msg, undo) => { clearTimeout(tm.current); setToast({ msg, undo }); tm.current = setTimeout(() => setToast(null), 10000); }, []);
  useEffect(() => () => clearTimeout(tm.current), []);
  const toggle = (id) => setSelSet((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const pick = (fn) => setSelSet(new Set(rooms.filter(fn).slice(0, 50).map((r) => r.id)));
  const exit = () => { setSel(false); setSelSet(new Set()); };
  const ask = (list) => setDlg({ ids: list.map((r) => r.id), names: Object.fromEntries(list.map((r) => [r.id, r.title])) });

  const undo = async (ids) => {
    setToast(null);
    try { for (const id of ids) await cpost(`/rooms/${encodeURIComponent(id)}/restore`, {}); say(t("Đã khôi phục.", "Restored.")); } catch (e) { say(e.message); }
    refresh();
  };
  const done = (res) => {
    const ids = res.trashed || [];
    setDlg(null); exit(); refresh();
    if (ids.length) say(t(`Đã chuyển ${ids.length} phòng vào thùng rác.`, `Moved ${ids.length} room(s) to the trash.`), () => undo(ids));
    else say(t("Không có phòng nào được xoá.", "No room was deleted."));
  };

  const count = trash.data?.count ?? 0;
  const toolbar = (
    <div className="cr-mgr" role="toolbar" aria-label={t("Quản lý phòng", "Manage rooms")}>
      <button type="button" className={cn("btn ghost cr-sm", selecting && "on")} aria-pressed={selecting} onClick={() => (selecting ? exit() : setSel(true))}><CheckSquare size={13} aria-hidden="true" />{t("Chọn nhiều", "Select")}</button>
      <button type="button" className="btn ghost cr-sm" onClick={() => setTrashOpen(true)} aria-label={t(`Thùng rác (${count})`, `Trash (${count})`)} data-testid="trash-open"><Trash2 size={13} aria-hidden="true" />{t("Thùng rác", "Trash")}<span className="cr-badge" aria-hidden="true">{count}</span></button>
      {selecting && (
        <div className="cr-mgr-sel">
          <div className="flex gap-1 flex-wrap" role="group" aria-label={t("Lọc nhanh", "Quick filters")}>
            <button type="button" className="cr-chip" onClick={() => pick(isEmpty)}>{t("Phòng trống", "Empty rooms")}</button>
            <button type="button" className="cr-chip" onClick={() => pick(isDemo)}>{t("Phòng demo/thử", "Demo/test rooms")}</button>
            <span className="cr-agef"><button type="button" className="cr-chip" onClick={() => pick((r) => age(r) > days)}>{t("Cũ hơn", "Older than")}</button><input className="cr-inp" type="number" min={1} max={999} value={days} onChange={(e) => setDays(Math.max(1, Math.min(999, +e.target.value || 1)))} aria-label={t("Số ngày không hoạt động", "Inactive days")} /><span className="text-[11.5px] text-muted">{t("ngày", "days")}</span></span>
            <button type="button" className="cr-chip" onClick={() => setSelSet(new Set())}>{t("Bỏ chọn", "Clear")}</button>
          </div>
          <button type="button" className="btn cr-sm cr-danger" disabled={!sel.size} onClick={() => ask(rooms.filter((r) => sel.has(r.id)))} data-testid="bulk-delete"><Trash2 size={13} aria-hidden="true" />{t(`Xoá ${sel.size} phòng`, `Delete ${sel.size}`)}</button>
        </div>
      )}
    </div>
  );
  const rowCheck = (r) => selecting && <input type="checkbox" className="cr-chk" checked={sel.has(r.id)} onChange={() => toggle(r.id)} aria-label={t(`Chọn phòng ${r.title}`, `Select room ${r.title}`)} />;
  const rowTrash = (r) => !selecting && <button type="button" className="cr-iconbtn big cr-rowdel" onClick={() => ask([r])} aria-label={t(`Xoá phòng ${r.title}`, `Delete room ${r.title}`)} title={t("Xoá phòng (vào thùng rác)", "Delete room (to trash)")} data-testid="room-delete"><Trash2 size={14} aria-hidden="true" /></button>;
  const headerBtn = (r) => r && <button type="button" className="btn ghost cr-sm" onClick={() => ask([r])} aria-label={t("Xoá phòng", "Delete room")} data-testid="head-delete"><Trash2 size={14} aria-hidden="true" /><span className="hidden sm:inline">{t("Xoá", "Delete")}</span></button>;

  const overlay = (<>
    {dlg && <DeleteDialog t={t} dlg={dlg} onClose={() => setDlg(null)} onDone={done} />}
    {trashOpen && <TrashPanel t={t} data={trash.data} loading={trash.isPending} isMaster={isMaster} onClose={() => setTrashOpen(false)} onChanged={refresh} say={say} />}
    {toast && <div className="cr-toast" role="status" aria-live="polite"><span>{toast.msg}</span>{toast.undo && <button type="button" className="btn cr-sm" onClick={toast.undo}><RotateCcw size={12} aria-hidden="true" />{t("Hoàn tác", "Undo")}</button>}<button type="button" className="cr-iconbtn" onClick={() => setToast(null)} aria-label={t("Đóng", "Close")}><X size={13} /></button></div>}
  </>);
  return { toggle, toolbar, rowCheck, rowTrash, headerBtn, overlay, selecting, selected: sel };
}

function Modal({ t, title, onClose, children, wide }) {
  const ref = useRef(null);
  useEffect(() => {
    const prev = document.activeElement; ref.current?.focus();
    const h = (e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    addEventListener("keydown", h, true); return () => { removeEventListener("keydown", h, true); prev?.focus?.(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="cr-modal-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={cn("cr-modal", wide && "wide")} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <header className="cr-sheet-h"><b className="text-[14px]">{title}</b><button type="button" className="cr-iconbtn big ml-auto" onClick={onClose} aria-label={t("Đóng", "Close")}><X size={16} /></button></header>
        <div className="cr-modal-b">{children}</div>
      </div>
    </div>
  );
}

function DeleteDialog({ t, dlg, onClose, onDone }) {
  const [prep, setPrep] = useState(null), [err, setErr] = useState(null), [busy, setBusy] = useState(false), [typed, setTyped] = useState(""), [reason, setReason] = useState(""), [forget, setForget] = useState(false);
  useEffect(() => { let off = false; cpost("/rooms/bulk-delete", { step: "prepare", ids: dlg.ids }).then((p) => !off && setPrep(p)).catch((e) => !off && setErr(e.message)); return () => { off = true; }; }, [dlg]);
  const ok = prep?.eligible || [], rej = prep?.rejected || [];
  const sum = ok.reduce((a, r) => ({ m: a.m + r.counts.messages, e: a.e + r.counts.examples, v: a.v + r.counts.versions }), { m: 0, e: 0, v: 0 });
  const need = ok.some((r) => heavy(r.counts));
  const word = ok.length === 1 ? ok[0].title : String(ok.length);
  const can = ok.length > 0 && !busy && (!need || typed.trim() === word);
  const go = async () => {
    setBusy(true); setErr(null);
    try { onDone(await cpost("/rooms/bulk-delete", { step: "confirm", ids: dlg.ids, token: prep.token, reason: reason.trim().slice(0, 200), forget_learned: forget })); } catch (e) { setErr(e.message); setBusy(false); }
  };
  return (
    <Modal t={t} title={t("Chuyển phòng vào thùng rác?", "Move rooms to the trash?")} onClose={onClose}>
      {!prep && !err && <p className="m-0 text-[13px] text-muted" role="status">{t("Đang kiểm tra…", "Checking…")}</p>}
      {ok.length > 0 && (<>
        <ul className="cr-dl">{ok.map((r) => <li key={r.id}><b className="truncate">{r.title}</b><span>{t(`${r.counts.messages} tin · ${r.counts.examples} ví dụ · ${r.counts.versions} phiên bản`, `${r.counts.messages} msgs · ${r.counts.examples} examples · ${r.counts.versions} versions`)}</span></li>)}</ul>
        <p className="m-0 text-[12.5px]">{t(`Tổng: ${sum.m} tin, ${sum.e} ví dụ, ${sum.v} phiên bản. Phòng nằm trong thùng rác 30 ngày, khôi phục được; sau đó tự xoá hẳn kèm tệp đính kèm.`, `Total: ${sum.m} msgs, ${sum.e} examples, ${sum.v} versions. Rooms stay in the trash for 30 days (restorable), then are permanently removed with their attachments.`)}</p>
        <label className="cr-fld"><span>{t("Lý do (tuỳ chọn)", "Reason (optional)")}</span><input className="cr-inp" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} /></label>
        <label className="cr-chkrow"><input type="checkbox" checked={forget} onChange={(e) => setForget(e.target.checked)} />{t("Xoá cả những gì AI đã học từ phòng này (mặc định giữ, đánh dấu “nguồn phòng đã xoá”)", "Also forget what the AI learned from these rooms (default keeps it, marked “source room deleted”)")}</label>
        {need && <label className="cr-fld"><span>{ok.length === 1 ? t(`Phòng có nhiều dữ liệu. Gõ lại tên phòng để xác nhận: ${ok[0].title}`, `This room has a lot of data. Retype its name to confirm: ${ok[0].title}`) : t(`Có phòng nhiều dữ liệu. Gõ số phòng (${ok.length}) để xác nhận`, `Some rooms have a lot of data. Type the room count (${ok.length}) to confirm`)}</span><input className="cr-inp" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" data-testid="retype" /></label>}
      </>)}
      {rej.length > 0 && <div className="cr-rej" role="note"><b>{t("Không thể xoá:", "Cannot delete:")}</b><ul>{rej.map((r) => <li key={r.id}>{r.title || r.id.slice(0, 8)}: {r.reason}</li>)}</ul></div>}
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
      <div className="flex gap-2 justify-end"><button type="button" className="btn ghost" onClick={onClose}>{t("Huỷ", "Cancel")}</button><button type="button" className="btn cr-danger" disabled={!can} onClick={go} data-testid="confirm-delete"><Trash2 size={14} aria-hidden="true" />{t("Chuyển vào thùng rác", "Move to trash")}</button></div>
    </Modal>
  );
}

function TrashPanel({ t, data, loading, isMaster, onClose, onChanged, say }) {
  const [err, setErr] = useState(null), [busy, setBusy] = useState(null), [armed, setArmed] = useState(null);
  const items = data?.items || [];
  const run = async (id, fn, okMsg) => { setBusy(id); setErr(null); try { await fn(); say(okMsg); onChanged(); } catch (e) { setErr(e.message); } finally { setBusy(null); setArmed(null); } };
  return (
    <Modal t={t} wide title={t(`Thùng rác (${items.length})`, `Trash (${items.length})`)} onClose={onClose}>
      <p className="m-0 text-[12.5px] text-muted">{t(`Phòng ở đây tự xoá hẳn sau ${data?.days || 30} ngày. Xoá vĩnh viễn chỉ dành cho master.`, `Rooms here are permanently removed after ${data?.days || 30} days. Permanent deletion is master-only.`)}</p>
      {loading && <p className="m-0 text-[13px] text-muted" role="status">…</p>}
      {!loading && !items.length && <p className="m-0 text-[13px] text-muted">{t("Thùng rác trống.", "The trash is empty.")}</p>}
      <ul className="cr-dl">
        {items.map((r) => (
          <li key={r.id}>
            <div className="min-w-0"><b className="truncate block">{r.title}</b>
              <span className="text-[11.5px] text-muted block">{t(`${r.counts.messages} tin · ${r.counts.examples} ví dụ · ${r.counts.versions} phiên bản · còn ${r.days_left} ngày`, `${r.counts.messages} msgs · ${r.counts.examples} examples · ${r.counts.versions} versions · ${r.days_left} days left`)}{r.deleted_by_name ? ` · ${t("xoá bởi", "by")} ${r.deleted_by_name}` : ""}{r.reason ? ` · “${r.reason}”` : ""}</span></div>
            <div className="flex gap-1 shrink-0">
              <button type="button" className="btn cr-sm" disabled={busy === r.id} onClick={() => run(r.id, () => cpost(`/rooms/${encodeURIComponent(r.id)}/restore`, {}), t("Đã khôi phục phòng.", "Room restored."))}><RotateCcw size={12} aria-hidden="true" />{t("Khôi phục", "Restore")}</button>
              {isMaster && (armed === r.id
                ? <button type="button" className="btn cr-sm cr-danger" disabled={busy === r.id} onClick={() => run(r.id, () => del(`/rooms/${encodeURIComponent(r.id)}/purge`), t("Đã xoá vĩnh viễn.", "Permanently deleted."))}>{t("Chắc chắn xoá?", "Really delete?")}</button>
                : <button type="button" className="btn ghost cr-sm" onClick={() => setArmed(r.id)}><Trash2 size={12} aria-hidden="true" />{t("Xoá vĩnh viễn", "Delete forever")}</button>)}
            </div>
          </li>
        ))}
      </ul>
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
    </Modal>
  );
}
