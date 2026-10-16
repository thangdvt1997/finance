// Bộ lọc đã lưu (saved views): chọn / lưu bộ lọc hiện tại / chia sẻ cho nhân sự khác / xoá. API: GET|POST views, DELETE views/{id}.
import { useEffect, useRef, useState } from "react";
import { Bookmark, BookmarkPlus, Share2, Trash2 } from "lucide-react";
import { Dialog } from "../dialog";
import { toast } from "../../ux/bus";
import { fdel, fpost } from "../../lib/fleetApi";
import { useAuthMe, useFleetMut, usePerm, useViews } from "../../lib/fleetQueries";
import { FILTER_KEYS } from "../../lib/fleetFilters";
import { ErrLine, Field, PRIMARY } from "./bits";

export default function SavedViews({ filters, onApply, activeCount }) {
  const q = useViews();
  const me = useAuthMe().data;
  const perm = usePerm();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const wrap = useRef(null);
  const items = q.data?.items || [];
  const mut = useFleetMut((v) => fpost("/views", v), ["views"]);
  const del = useFleetMut((id) => fdel(`/views/${id}`), ["views"]);

  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    const k = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", h); document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [open]);

  const save = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(FILTER_KEYS.filter((k) => filters[k]).map((k) => [k, filters[k]]));
    try { await mut.mutateAsync({ name: name.trim(), filters: f, shared }); toast({ tone: "ok", title: "Đã lưu bộ lọc", body: name.trim() }); setSaving(false); setName(""); setShared(false); }
    catch { /* hiển thị ở ErrLine */ }
  };
  const mine = (v) => perm.isMaster || (me?.user_id && (v.owner_id === me.user_id || v.user_id === me.user_id || v.owner === me.user_id));

  return (
    <div className="relative" ref={wrap}>
      <button type="button" className="btn" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Bookmark size={14} aria-hidden="true" />Bộ lọc đã lưu{items.length ? ` (${items.length})` : ""}
      </button>
      {open && (
        <div role="menu" aria-label="Bộ lọc đã lưu" className="absolute z-40 mt-1 w-[min(22rem,88vw)] rounded-lg border border-line2 bg-panel shadow-2xl p-1" style={{ right: 0 }}>
          {q.isPending && <p className="m-2 text-[12.5px] text-muted">Đang tải…</p>}
          {q.isError && <p className="m-2 text-[12.5px] text-muted">{q.error?.code === "unavailable" ? "Máy chủ chưa hỗ trợ bộ lọc đã lưu." : q.error?.message}</p>}
          {!q.isPending && !q.isError && !items.length && <p className="m-2 text-[12.5px] text-muted">Chưa có bộ lọc nào. Đặt bộ lọc rồi bấm “Lưu bộ lọc hiện tại”.</p>}
          <ul className="m-0 p-0 list-none max-h-64 overflow-auto">
            {items.map((v) => (
              <li key={v.id} className="flex items-center gap-1">
                <button type="button" role="menuitem" className="flex-1 min-w-0 text-left px-2 py-1.5 rounded-md hover:bg-panel2 bg-transparent border-0 text-fg cursor-pointer text-[12.5px]"
                  onClick={() => { const f = v.filters || {}; onApply({ ...Object.fromEntries(FILTER_KEYS.map((k) => [k, ""])), ...f }); setOpen(false); }}>
                  <span className="flex items-center gap-1.5 min-w-0"><b className="truncate">{v.name}</b>{v.shared && <Share2 size={11} className="text-info shrink-0" aria-label="Chia sẻ cho nhân sự" />}</span>
                  <span className="block text-[11px] text-muted truncate">{Object.entries(v.filters || {}).map(([k, x]) => `${k}=${x}`).join(" · ") || "không lọc"}</span>
                </button>
                {mine(v) && !perm.viewAs && <button type="button" className="btn !px-2 !h-7" onClick={() => del.mutate(v.id, { onSuccess: () => toast({ tone: "info", title: "Đã xoá bộ lọc", body: v.name }) })} aria-label={`Xoá bộ lọc ${v.name}`}><Trash2 size={13} aria-hidden="true" /></button>}
              </li>
            ))}
          </ul>
          <div className="border-t border-line mt-1 pt-1">
            <button type="button" role="menuitem" className="btn w-full justify-start" disabled={!activeCount || !!perm.viewAs} title={!activeCount ? "Đặt ít nhất một bộ lọc trước" : undefined} onClick={() => { setOpen(false); setSaving(true); }}>
              <BookmarkPlus size={14} aria-hidden="true" />Lưu bộ lọc hiện tại
            </button>
          </div>
        </div>
      )}
      <Dialog open={saving} onClose={() => setSaving(false)} title="Lưu bộ lọc hiện tại">
        <form onSubmit={save} className="p-3 grid gap-3">
          <Field label="Tên bộ lọc" htmlFor="sv-name"><input id="sv-name" className="field" value={name} maxLength={60} required data-autofocus onChange={(e) => setName(e.target.value)} placeholder="Ví dụ: Mất kết nối nhóm VIP" /></Field>
          <p className="m-0 text-[12px] text-muted num">{Object.entries(filters).map(([k, v]) => `${k}=${v}`).join(" · ")}</p>
          <label className="fl-check"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /><span>Chia sẻ cho nhân sự khác (họ xem được, chỉ bạn/master xoá được)</span></label>
          <ErrLine error={mut.error} />
          <div className="flex justify-end gap-2"><button type="button" className="btn" onClick={() => setSaving(false)}>Huỷ</button><button type="submit" className={`btn ${PRIMARY}`} disabled={!name.trim() || mut.isPending}>{mut.isPending ? "Đang lưu…" : "Lưu"}</button></div>
        </form>
      </Dialog>
    </div>
  );
}
