// "Bộ nhớ của AI": danh sách bản ghi AI đã học (lọc/ tìm), xem nguồn, sửa/ xác nhận/ bác/ ghim/ xoá, mâu thuẫn, thống kê, xuất/ nhập JSON.
// Bộ nhớ là NGỮ CẢNH THAM KHẢO do chuyên gia kiểm soát, không phải huấn luyện lại model. Hợp đồng: docs/handoff/MEMORY_API.md.
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Lock, Pencil, Pin, PinOff, Trash2, Upload, X } from "lucide-react";
import { Chip, cn } from "../ui";
import { cget } from "./classApi";
import { EVENTS, STATUS, TOPICS, TYPES, errText, lab, mget, mw, saveJson } from "./memoryApi";
import { hhmm } from "./ctx";
import "./memory.css";

const TABS = [["list", "Bản ghi", "Items"], ["conflicts", "Mâu thuẫn", "Conflicts"], ["stats", "Thống kê", "Stats"]];

function Conf({ v }) {
  const p = Math.round(Math.max(0, Math.min(1, +v || 0)) * 100);
  return <span title={`${p}%`}><span className="mem-conf" aria-hidden="true"><i style={{ width: `${p}%` }} /></span>{p}%</span>;
}

function Item({ it, en, t, open, onToggle, onChanged, setMsg }) {
  const [busy, setBusy] = useState(false), [edit, setEdit] = useState(false), [text, setText] = useState(""), [reason, setReason] = useState(""), [err, setErr] = useState(null);
  const det = useQuery({ queryKey: ["mem", "item", it.id, it.updated_at], enabled: open, queryFn: ({ signal }) => mget(`/memory/${encodeURIComponent(it.id)}`, {}, signal), retry: false });
  const act = async (method, path, body, ok) => {
    setBusy(true); setErr(null);
    try { const r = await mw(method, `/memory/${encodeURIComponent(it.id)}${path}`, body); if (ok) setMsg(ok); setEdit(false); onChanged(r); } catch (e) { setErr(errText(e, en)); } finally { setBusy(false); }
  };
  const dead = it.status === "rejected" || it.status === "revoked";
  const [stL, stE, stT] = STATUS[it.status] || [it.status, it.status, ""];
  const mine = it.can_edit && !it.locked;
  const txt = it.content?.text || "";
  return (
    <li className={cn("mem-item", it.pinned && "pinned", (!it.is_current || dead) && "old")} id={`mem-${it.id}`}>
      <div className="mem-head">
        <Chip>{lab(TYPES, it.type, en)}</Chip><Chip tone={stT}>{en ? stE : stL}</Chip>
        {it.importance === "critical" && <Chip tone="down">{t("Quan trọng", "Critical")}</Chip>}
        {it.topic && it.topic !== "general" && <span>{lab(TOPICS, it.topic, en)}</span>}
        {it.pinned && <Pin size={12} aria-label={t("Đã ghim", "Pinned")} />}{it.locked && <Lock size={12} aria-label={t("Master đã khoá", "Locked by master")} />}
        {!it.is_current && <span>{t("Bản cũ", "Old version")}</span>}{it.conflict_id && <Chip tone="down">{t("Mâu thuẫn", "Conflict")}</Chip>}
      </div>
      <p className="mem-text">{txt}</p>
      <div className="mem-meta">
        <span>{t("Độ tin cậy", "Confidence")}: <Conf v={it.confidence} /></span>
        <span>{t("Dùng", "Used")} {it.use_count ?? 0}×</span>
        {it.author?.name && <span>{it.author.name}</span>}
        <span>{it.room_title ? `${it.room_title}${it.room_deleted ? t(" (phòng đã xoá)", " (room deleted)") : ""}` : it.scope === "expert" ? t("Riêng chuyên gia", "Expert-only") : ""}</span>
        <span>v{it.version ?? 1} · {hhmm(it.updated_at)}</span>
      </div>
      <div className="mem-act" role="group" aria-label={t("Thao tác bản ghi", "Item actions")}>
        {it.status !== "confirmed" && it.is_current && <button type="button" className="mem-btn pri" disabled={busy || !mine && !it.can_moderate} onClick={() => act("POST", "/confirm", {}, t("Đã xác nhận.", "Confirmed."))}><Check size={14} aria-hidden="true" />{t("Xác nhận", "Confirm")}</button>}
        {!dead && <button type="button" className="mem-btn" disabled={busy || !mine} onClick={() => { setEdit(!edit); setText(txt); setOpenSafe(); }}><Pencil size={14} aria-hidden="true" />{t("Sửa", "Edit")}</button>}
        {!dead && <button type="button" className="mem-btn" disabled={busy || !mine && !it.can_moderate} onClick={() => act("POST", "/reject", {}, t("Đã bác, AI sẽ không dùng nữa.", "Rejected, the AI will not use it."))}><X size={14} aria-hidden="true" />{t("Bác", "Reject")}</button>}
        <button type="button" className="mem-btn" aria-pressed={!!it.pinned} disabled={busy} onClick={() => act("POST", "/pin", { pinned: !it.pinned }, it.pinned ? t("Đã bỏ ghim.", "Unpinned.") : t("Đã ghim.", "Pinned."))}>{it.pinned ? <PinOff size={14} aria-hidden="true" /> : <Pin size={14} aria-hidden="true" />}{it.pinned ? t("Bỏ ghim", "Unpin") : t("Ghim", "Pin")}</button>
        <button type="button" className="mem-btn dng" disabled={busy || !mine && !it.can_moderate} onClick={() => { if (window.confirm(t("Xoá bản ghi này? AI sẽ không dùng nữa (nhật ký vẫn giữ).", "Delete this item? The AI will stop using it (the log is kept)."))) act("DELETE", "", undefined, t("Đã xoá.", "Deleted.")); }}><Trash2 size={14} aria-hidden="true" />{t("Xoá", "Delete")}</button>
        <button type="button" className="mem-btn" aria-expanded={open} onClick={onToggle}>{open ? t("Thu gọn", "Collapse") : t("Nguồn & nhật ký", "Source & log")}</button>
      </div>
      {err && <p role="alert" className="mem-err">{err}</p>}
      {edit && (
        <form className="mem-detail" onSubmit={(e) => { e.preventDefault(); if (text.trim()) act("PATCH", "", { text: text.trim(), ...(reason.trim() ? { reason: reason.trim() } : {}) }, t("Đã lưu thành phiên bản mới.", "Saved as a new version.")); }}>
          <label className="mem-msg" htmlFor={`me-${it.id}`}>{t("Nội dung (lưu thành phiên bản mới, bản cũ vẫn giữ)", "Content (saved as a new version, the old one is kept)")}</label>
          <textarea id={`me-${it.id}`} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} />
          <input type="text" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder={t("Vì sao sửa (tuỳ chọn)", "Why (optional)")} aria-label={t("Lý do sửa", "Reason for edit")} />
          <div className="mem-act"><button type="submit" className="mem-btn pri" disabled={busy || !text.trim()}>{t("Lưu", "Save")}</button><button type="button" className="mem-btn" onClick={() => setEdit(false)}>{t("Huỷ", "Cancel")}</button></div>
        </form>
      )}
      {open && (
        <div className="mem-detail">
          {det.isPending && <p className="mem-msg" role="status">{t("Đang tải…", "Loading…")}</p>}
          {det.isError && <p className="mem-err">{det.error?.message}</p>}
          {det.data && (<>
            <div><b>{t("Nguồn hội thoại", "Conversation source")}</b>
              {det.data.source_message ? <blockquote className="mem-src">{det.data.source_message.text}<br /><small>{det.data.source_message.author?.name || det.data.source_message.author} · {hhmm(det.data.source_message.created_at)}</small></blockquote>
                : it.source?.excerpt ? <blockquote className="mem-src">{it.source.excerpt}</blockquote> : <p className="mem-msg">{t("Không có tin nhắn nguồn (nhập tay hoặc phòng đã xoá).", "No source message (manual entry or deleted room).")}</p>}
            </div>
            {det.data.versions?.length > 1 && <div><b>{t("Các phiên bản", "Versions")}</b><ul className="mem-log">{det.data.versions.map((v) => <li key={v.id}>v{v.version} · {v.content?.text}{v.is_current ? ` (${t("hiện tại", "current")})` : ""}</li>)}</ul></div>}
            <div><b>{t("Nhật ký thay đổi", "Change log")}</b>
              {det.data.history?.length ? <ul className="mem-log">{det.data.history.map((h) => <li key={h.id}><b>{lab(EVENTS, h.event, en)}</b> · {h.by?.name || h.by?.user_id || ""} · {hhmm(h.at)}{h.detail ? ` · ${h.detail}` : ""}{h.before || h.after ? <><br />{h.before ? <s>{h.before}</s> : null}{h.before && h.after ? " → " : ""}{h.after}</> : null}</li>)}</ul> : <p className="mem-msg">{t("Chưa có thay đổi.", "No changes yet.")}</p>}
            </div>
          </>)}
        </div>
      )}
    </li>
  );
  function setOpenSafe() { if (!open) onToggle(); }
}

function Conflicts({ en, t, refresh, setMsg }) {
  const q = useQuery({ queryKey: ["mem", "conflicts"], queryFn: ({ signal }) => mget("/memory/conflicts", { status: "open" }, signal), retry: false });
  const [sel, setSel] = useState({}), [err, setErr] = useState(null), [busy, setBusy] = useState(false);
  const items = q.data?.items || [];
  const resolve = async (c, choice) => {
    const s = sel[c.id] || {};
    if (choice === "merge" && !(s.text || "").trim()) { setErr(t("Nhập nội dung hợp nhất.", "Enter the merged text.")); return; }
    if (choice === "both_context" && !(s.note || "").trim()) { setErr(t("Ghi điều kiện áp dụng cho từng bản.", "Note when each version applies.")); return; }
    setBusy(true); setErr(null);
    try { await mw("POST", `/memory/conflicts/${encodeURIComponent(c.id)}/resolve`, { choice, ...(s.text ? { text: s.text.trim() } : {}), ...(s.note ? { note: s.note.trim() } : {}) }); setMsg(t("Đã giải quyết mâu thuẫn.", "Conflict resolved.")); refresh(); q.refetch(); } catch (e) { setErr(errText(e, en)); } finally { setBusy(false); }
  };
  if (q.isPending) return <p className="mem-msg" role="status">{t("Đang tải…", "Loading…")}</p>;
  if (q.isError) return <p className="mem-err">{q.error?.message}</p>;
  if (!items.length) return <p className="mem-msg">{t("Không có mâu thuẫn nào đang chờ. Khi hai điều AI nhớ trái nhau, chúng hiện ở đây để bạn chọn bản đúng.", "No open conflicts. When two remembered things disagree, they show up here for you to pick the right one.")}</p>;
  return (
    <ul className="mem-list">
      {items.map((c) => {
        const s = sel[c.id] || {};
        const set = (k, v) => setSel((o) => ({ ...o, [c.id]: { ...o[c.id], [k]: v } }));
        return (
          <li key={c.id} className="mem-item">
            <p className="mem-text"><b>{c.question || t("Hai điều AI nhớ đang trái nhau. Bản nào đúng?", "Two remembered things disagree. Which is right?")}</b></p>
            <div className="mem-vs">
              {[["a", c.a], ["b", c.b]].map(([k, m]) => m && (
                <div key={k} className="mem-card"><div className="mem-head"><Chip>{k.toUpperCase()}</Chip>{m.author?.name && <span>{m.author.name}</span>}<span>{hhmm(m.created_at)}</span></div><p className="mem-text">{m.content?.text}</p>
                  <button type="button" className="mem-btn pri" disabled={busy} onClick={() => resolve(c, k)}>{t(`Bản ${k.toUpperCase()} đúng`, `${k.toUpperCase()} is right`)}</button></div>
              ))}
            </div>
            <div className="mem-detail">
              <input type="text" value={s.note || ""} maxLength={300} onChange={(e) => set("note", e.target.value)} placeholder={t("Điều kiện áp dụng (cho 'cả hai tuỳ ngữ cảnh') hoặc ghi chú", "When each applies (for 'both, by context') or a note")} aria-label={t("Ghi chú", "Note")} />
              <textarea value={s.text || ""} maxLength={1000} onChange={(e) => set("text", e.target.value)} placeholder={t("Hoặc viết bản hợp nhất…", "Or write a merged version…")} aria-label={t("Bản hợp nhất", "Merged version")} />
              <div className="mem-act"><button type="button" className="mem-btn" disabled={busy} onClick={() => resolve(c, "both_context")}>{t("Cả hai, tuỳ ngữ cảnh", "Both, by context")}</button><button type="button" className="mem-btn" disabled={busy} onClick={() => resolve(c, "merge")}>{t("Dùng bản hợp nhất", "Use merged version")}</button></div>
            </div>
          </li>
        );
      })}
      {err && <li><p role="alert" className="mem-err">{err}</p></li>}
    </ul>
  );
}

function Stats({ t, en }) {
  const q = useQuery({ queryKey: ["mem", "stats"], queryFn: ({ signal }) => mget("/memory/stats", {}, signal), retry: false });
  const o = useQuery({ queryKey: ["mem", "opt-stats"], queryFn: ({ signal }) => cget("/options/stats", {}, signal), retry: false });
  if (q.isPending) return <p className="mem-msg" role="status">{t("Đang tải…", "Loading…")}</p>;
  if (q.isError) return <p className="mem-err">{q.error?.message}</p>;
  const s = q.data || {};
  const headline = en ? `The AI learned ${s.confirmed ?? 0} things from ${s.sessions ?? 0} sessions` : (s.learned_from_sessions || `AI đã học ${s.confirmed ?? 0} điều từ ${s.sessions ?? 0} buổi`);
  return (
    <div className="grid gap-2">
      <p className="m-0 text-[14px] font-semibold" role="status">{headline}</p>
      <div className="mem-stat">
        {[["confirmed", "Đã xác nhận", "Confirmed"], ["proposed", "Đề xuất", "Proposed"], ["rejected", "Bị bác", "Rejected"], ["conflicts_open", "Mâu thuẫn mở", "Open conflicts"], ["repeat_questions_avoided", "Câu hỏi lặp đã tránh", "Repeat questions avoided"]].map(([k, vi, e]) => <div key={k}><b>{s[k] ?? 0}</b>{t(vi, e)}</div>)}
        <div><b>{Math.round((s.avg_confidence || 0) * 100)}%</b>{t("Độ tin cậy TB", "Avg confidence")}</div>
      </div>
      {s.by_type && <div className="flex gap-1 flex-wrap">{Object.entries(s.by_type).map(([k, n]) => <Chip key={k}>{lab(TYPES, k, en)}: {n}</Chip>)}</div>}
      <div><b>{t("Độ phủ theo hàng hồ sơ", "Coverage by profile row")}</b>
        {(s.rooms_covered || []).length ? s.rooms_covered.map((r) => (
          <div key={r.room_id} className="mem-cov"><span className="truncate">{r.title}</span><span>{r.rows_known}/{r.rows_total}</span><div className="mem-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((r.coverage || 0) * 100)} aria-label={r.title}><i style={{ width: `${Math.round((r.coverage || 0) * 100)}%` }} /></div></div>
        )) : <p className="mem-msg">{t("Chưa có phòng nào được AI ghi nhớ.", "No room has been memorised yet.")}</p>}
      </div>
      <div><b>{t("Gợi ý của AI được chấp nhận", "AI suggestions accepted")}</b>
        {o.data?.mine?.kinds?.length || o.data?.class?.kinds?.length ? (o.data.class.kinds.length ? o.data.class.kinds : o.data.mine.kinds).map((k) => {
          const mine = o.data.mine.kinds.find((x) => x.kind === k.kind);
          return <div key={k.kind} className="mem-cov"><span>{k.label}</span><span>{Math.round((mine?.p_accept ?? k.p_accept) * 100)}%</span><div className="mem-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((mine?.p_accept ?? k.p_accept) * 100)} aria-label={k.label}><i style={{ width: `${Math.round((mine?.p_accept ?? k.p_accept) * 100)}%` }} /></div></div>;
        }) : <p className="mem-msg">{t("Chưa có dữ liệu bấm. Càng dùng, thứ tự gợi ý càng hợp với bạn (xếp hạng thống kê nhẹ, không phải huấn luyện lại model).", "No click data yet. The more you use it, the better suggestions fit you (light statistical ranking, not model retraining).")}</p>}
      </div>
    </div>
  );
}

export default function MemoryPanel({ lang = "vi", rid, focusId, onClose }) {
  const en = lang === "en";
  const t = (vi, e) => (en ? e : vi);
  const qc = useQueryClient();
  const [tab, setTab] = useState("list"), [f, setF] = useState({ type: "", status: "", room: "", author: "", q: "", pinned: "", history: "" }), [open, setOpen] = useState(null), [msg, setMsg] = useState(null), [err, setErr] = useState(null);
  const [qd, setQd] = useState(""), fileRef = useRef(null);
  useEffect(() => { const h = setTimeout(() => setQd(f.q.trim().slice(0, 80)), 250); return () => clearTimeout(h); }, [f.q]);
  useEffect(() => { if (focusId) { setTab("list"); setOpen(focusId); setF((x) => ({ ...x, type: "", status: "", q: "", room: "" })); setTimeout(() => document.getElementById(`mem-${focusId}`)?.scrollIntoView({ block: "center" }), 400); } }, [focusId]);
  useEffect(() => { if (!msg) return undefined; const h = setTimeout(() => setMsg(null), 5000); return () => clearTimeout(h); }, [msg]);

  const params = { type: f.type, status: f.status, room: f.room, author: f.author, q: qd, pinned: f.pinned, history: f.history, limit: 100 };
  const list = useQuery({ queryKey: ["mem", "list", params], queryFn: ({ signal }) => mget("/memory", params, signal), retry: false, refetchInterval: 15000 });
  const rooms = useQuery({ queryKey: ["cls", "rooms"], queryFn: ({ signal }) => cget("/rooms", {}, signal), staleTime: 30000 });
  const people = useMemo(() => { const m = new Map(); for (const r of rooms.data?.items || []) for (const p of r.members || []) m.set(p.user_id, p.name || p.user_id); return [...m]; }, [rooms.data]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["mem"] }); };
  const conf = useQuery({ queryKey: ["mem", "conflicts", "count"], queryFn: ({ signal }) => mget("/memory/conflicts", { status: "open" }, signal), retry: false, refetchInterval: 20000 });
  const nConf = conf.data?.total ?? conf.data?.items?.length ?? 0;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const items = list.data?.items || [];

  const doExport = async () => {
    setErr(null);
    try { const d = await mget("/memory/export"); saveJson(`bo-nho-ai-${new Date().toISOString().slice(0, 10)}.json`, d); setMsg(t("Đã xuất bộ nhớ (đã lọc khoá/ mật khẩu).", "Exported (secrets filtered).")); } catch (e) { setErr(e.message); }
  };
  const doImport = async (file) => {
    setErr(null);
    if (!file) return;
    if (file.size > 800_000) { setErr(t("Tệp quá lớn (tối đa ~800KB, 500 bản ghi).", "File too large (max ~800KB, 500 items).")); return; }
    try {
      const d = JSON.parse(await file.text());
      const arr = Array.isArray(d) ? d : d.items;
      if (!Array.isArray(arr) || !arr.length) throw new Error(t("Tệp không có mục 'items'.", "File has no 'items'."));
      const dry = await mw("POST", "/memory/import", { items: arr.slice(0, 500), dry_run: true });
      const sk = dry.skipped?.length || 0;
      if (!window.confirm(t(`Sẽ nhập ${dry.imported} bản ghi (gộp ${dry.merged || 0}, bỏ qua ${sk}). Tất cả vào trạng thái "đề xuất". Tiếp tục?`, `Will import ${dry.imported} items (merged ${dry.merged || 0}, skipped ${sk}). All become "proposed". Continue?`))) return;
      const r = await mw("POST", "/memory/import", { items: arr.slice(0, 500), dry_run: false });
      setMsg(t(`Đã nhập ${r.imported} bản ghi.`, `Imported ${r.imported} items.`)); refresh();
    } catch (e) { setErr(errText(e, en)); } finally { if (fileRef.current) fileRef.current.value = ""; }
  };

  return (
    <section className="mem" aria-label={t("Bộ nhớ của AI", "AI memory")}>
      <p className="mem-msg m-0">{t("AI nhớ điều bạn dạy để khỏi hỏi lại. Đây là ngữ cảnh tham khảo bạn kiểm soát được (sửa, bác, xoá bất cứ lúc nào), không phải huấn luyện lại model.", "The AI remembers what you teach so it does not ask twice. It is reference context you control (edit, reject, delete anytime), not model retraining.")}</p>
      <div className="mem-tabs" role="tablist" aria-label={t("Bộ nhớ của AI", "AI memory")}>
        {TABS.map(([k, vi, e]) => <button key={k} type="button" role="tab" id={`memtab-${k}`} aria-selected={tab === k} aria-controls="mem-body" className="mem-tab" onClick={() => setTab(k)}>{t(vi, e)}{k === "conflicts" && nConf > 0 ? ` (${nConf})` : ""}</button>)}
      </div>
      <div id="mem-body" role="tabpanel" aria-labelledby={`memtab-${tab}`} className="grid gap-2">
        <div aria-live="polite">{msg && <p role="status" className="mem-msg" style={{ color: "var(--up)" }}>{msg}</p>}{err && <p role="alert" className="mem-err">{err}</p>}</div>
        {tab === "list" && (<>
          <div className="mem-filters" role="search" aria-label={t("Lọc bộ nhớ", "Filter memory")}>
            <input type="search" className="mem-q" value={f.q} onChange={set("q")} maxLength={80} placeholder={t("Tìm trong bộ nhớ…", "Search memory…")} aria-label={t("Tìm trong bộ nhớ", "Search memory")} />
            <select value={f.type} onChange={set("type")} aria-label={t("Loại", "Type")}><option value="">{t("Mọi loại", "All types")}</option>{Object.keys(TYPES).map((k) => <option key={k} value={k}>{lab(TYPES, k, en)}{list.data?.facets?.type?.[k] != null ? ` (${list.data.facets.type[k]})` : ""}</option>)}</select>
            <select value={f.status} onChange={set("status")} aria-label={t("Trạng thái", "Status")}><option value="">{t("Mọi trạng thái", "All statuses")}</option>{Object.keys(STATUS).map((k) => <option key={k} value={k}>{lab(STATUS, k, en)}</option>)}</select>
            <select value={f.room} onChange={set("room")} aria-label={t("Kịch bản / phòng", "Scenario / room")}><option value="">{t("Mọi kịch bản", "All scenarios")}</option>{rid && <option value={rid}>{t("Phòng đang mở", "Current room")}</option>}{(rooms.data?.items || []).filter((r) => r.id !== rid).map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}</select>
            <select value={f.author} onChange={set("author")} aria-label={t("Chuyên gia", "Expert")}><option value="">{t("Mọi chuyên gia", "All experts")}</option>{people.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
            <label className="flex items-center gap-1 text-[12.5px] min-h-[40px]"><input type="checkbox" checked={!!f.pinned} onChange={(e) => setF((x) => ({ ...x, pinned: e.target.checked ? "1" : "" }))} />{t("Chỉ đã ghim", "Pinned only")}</label>
            <label className="flex items-center gap-1 text-[12.5px] min-h-[40px]"><input type="checkbox" checked={!!f.history} onChange={(e) => setF((x) => ({ ...x, history: e.target.checked ? "1" : "" }))} />{t("Kèm bản cũ", "Include old versions")}</label>
          </div>
          {list.isPending && <p className="mem-msg" role="status">{t("Đang tải…", "Loading…")}</p>}
          {list.isError && <p className="mem-err">{list.error?.status === 404 ? t("Dịch vụ bộ nhớ chưa sẵn sàng.", "Memory service is not ready.") : list.error?.message}</p>}
          {list.isSuccess && !items.length && <p className="mem-msg">{t("Chưa có gì khớp. Hãy dạy AI qua chat; khi bạn nêu luật vào lệnh, SL/TP, điều kiện huỷ, AI sẽ hỏi lại 'Mình ghi nhớ … đúng không?'.", "Nothing matches yet. Teach the AI in chat; when you state entry rules, SL/TP or invalidation, it asks 'I will remember … right?'.")}</p>}
          {list.isSuccess && <p className="mem-msg" role="status">{list.data.total ?? items.length} {t("bản ghi", "items")}</p>}
          <ul className="mem-list">{items.map((it) => <Item key={it.id} it={it} en={en} t={t} open={open === it.id} onToggle={() => setOpen(open === it.id ? null : it.id)} onChanged={refresh} setMsg={setMsg} />)}</ul>
          <div className="mem-act">
            <button type="button" className="mem-btn" onClick={doExport}><Download size={14} aria-hidden="true" />{t("Xuất JSON", "Export JSON")}</button>
            <button type="button" className="mem-btn" onClick={() => fileRef.current?.click()}><Upload size={14} aria-hidden="true" />{t("Nhập JSON", "Import JSON")}</button>
            <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => doImport(e.target.files?.[0])} aria-label={t("Chọn tệp JSON để nhập", "Choose a JSON file to import")} />
          </div>
        </>)}
        {tab === "conflicts" && <Conflicts en={en} t={t} refresh={refresh} setMsg={setMsg} />}
        {tab === "stats" && <Stats t={t} en={en} />}
      </div>
      {onClose && <div className="mem-act"><button type="button" className="mem-btn" onClick={onClose}>{t("Đóng", "Close")}</button></div>}
    </section>
  );
}
