// Chuông thông báo + ngăn kéo "Trung tâm thông báo": lọc theo loại/chưa đọc, đánh dấu đã đọc, xoá, mở trang liên quan.
import { useMemo, useState } from "react";
import { Bell, BellRing, Check, CheckCheck, Newspaper, Server, Settings, Trash2, Users } from "lucide-react";
import { Dialog } from "../dialog";
import { cn } from "../ui";
import { CATS, clearNotifs, markAllRead, markRead, removeNotif, useNotifications } from "../../ux/bus";
import { rel, dateTime } from "../../lib/format";
import { useNow } from "../../lib/queries";

const ICON = { alert: BellRing, news: Newspaper, expert: Users, system: Server };
const SEV = { crit: ["Nghiêm trọng", "text-down"], warn: ["Cảnh báo", "text-accent"], info: ["Thông tin", "text-info"] };

export function NotificationCenter({ open, onClose }) {
  const { items, unread } = useNotifications();
  const [cat, setCat] = useState("");
  const [onlyUnread, setOnlyUnread] = useState(false);
  useNow(30_000);
  const list = useMemo(() => items.filter((x) => (!cat || x.cat === cat) && (!onlyUnread || !x.read)), [items, cat, onlyUnread]);
  const counts = useMemo(() => { const c = {}; for (const x of items) c[x.cat] = (c[x.cat] || 0) + 1; return c; }, [items]);
  const go = (n) => { markRead(n.id); if (n.href) { onClose(); location.hash = n.href.replace(/^#?/, "#"); } };

  return (
    <Dialog open={open} onClose={onClose} variant="drawer" title={`Thông báo${unread ? ` (${unread} chưa đọc)` : ""}`}
      footer={<>
        <a href="#/cai-dat" className="btn no-underline mr-auto" onClick={onClose}><Settings size={13} aria-hidden="true" /> Cài đặt thông báo</a>
        <button type="button" className="btn" onClick={markAllRead} disabled={!unread}><CheckCheck size={13} aria-hidden="true" /> Đánh dấu đã đọc</button>
        <button type="button" className="btn" onClick={() => { if (confirm("Xoá toàn bộ thông báo trong thiết bị này?")) clearNotifs(); }} disabled={!items.length}><Trash2 size={13} aria-hidden="true" /> Xoá hết</button>
      </>}>
      <div className="px-3 pt-3 pb-2 flex flex-wrap gap-2 items-center border-b border-line">
        <div className="seg" role="group" aria-label="Lọc theo loại">
          <button type="button" aria-pressed={cat === ""} onClick={() => setCat("")}>Tất cả{items.length ? ` ${items.length}` : ""}</button>
          {Object.entries(CATS).map(([k, l]) => <button type="button" key={k} aria-pressed={cat === k} onClick={() => setCat(k)}>{l}{counts[k] ? ` ${counts[k]}` : ""}</button>)}
        </div>
        <label className="flex items-center gap-2 text-[12.5px] ml-auto cursor-pointer"><input type="checkbox" checked={onlyUnread} onChange={(e) => setOnlyUnread(e.target.checked)} /> Chỉ chưa đọc</label>
      </div>
      {list.length === 0 ? (
        <div className="p-6 text-center text-muted grid gap-2 justify-items-center">
          <Bell size={28} className="text-faint" aria-hidden="true" />
          <b className="text-fg">{items.length ? "Không có thông báo khớp bộ lọc" : "Chưa có thông báo"}</b>
          <p className="m-0 max-w-[36ch] text-[12.5px]">Cảnh báo giá của bạn, tin quan trọng, tín hiệu chuyên gia và trạng thái hệ thống sẽ hiện ở đây. Tạo cảnh báo ở trang <a className="ux-a" href="#/canh-bao" onClick={onClose}>Cảnh báo</a>.</p>
        </div>
      ) : (
        <ul className="m-0 p-0 list-none">
          {list.map((n) => {
            const Ic = ICON[n.cat] || Bell;
            const [sevLabel, sevCls] = SEV[n.sev] || SEV.info;
            return (
              <li key={n.id} className={cn("ux-nitem", !n.read && "unread")}>
                <Ic size={16} className={cn("shrink-0 mt-[3px]", sevCls)} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <button type="button" className="ux-nmain" onClick={() => go(n)}>
                    <span className="block font-semibold text-[13px] break-words">{!n.read && <span className="sr-only">Chưa đọc. </span>}{n.title}</span>
                    {n.body && <span className="block text-[12.5px] text-muted break-words line-clamp-3">{n.body}</span>}
                  </button>
                  <div className="text-[11.5px] text-faint mt-[2px]" title={dateTime(n.ts)}>{CATS[n.cat]} · <span className={sevCls}>{sevLabel}</span> · {rel(n.ts)}</div>
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  {!n.read && <button type="button" className="ux-x" aria-label="Đánh dấu đã đọc" title="Đánh dấu đã đọc" onClick={() => markRead(n.id)}><Check size={14} aria-hidden="true" /></button>}
                  <button type="button" className="ux-x" aria-label="Xoá thông báo" title="Xoá" onClick={() => removeNotif(n.id)}><Trash2 size={14} aria-hidden="true" /></button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Dialog>
  );
}
