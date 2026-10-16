import { useState } from "react";
import { Search, Users } from "lucide-react";
import { Panel, Skeleton, cn } from "../../ui";
import { useFleetList, useGroups } from "../../../lib/fleetQueries";
import { ErrLine, GroupChip, Unavailable, useDebounced } from "../bits";
import { isUnavailable } from "../../../lib/fleetApi";

/** Chọn tài khoản (tìm theo nhãn/ID/khách) và lọc theo nhóm. onGroup(gid) để trang biết nhóm đang lọc (tạo hàng loạt). */
export default function AccountPicker({ value, onPick, group, onGroup }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 300);
  const groups = useGroups();
  const fl = useFleetList({ q: dq || undefined, group: group || undefined, limit: 60, sort: "label" });
  const items = fl.data?.items || [];
  const total = fl.data?.total ?? items.length;
  return (
    <Panel title="Tài khoản" icon={Users} right={<span className="fl-count num">{fl.data ? `${total}` : ""}</span>} pad={false}>
      <div className="grid gap-2 p-3 pb-2">
        <label className="fl-search" style={{ maxWidth: "none" }}>
          <Search size={14} aria-hidden="true" />
          <input className="field" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm nhãn, ID, tên khách…" aria-label="Tìm tài khoản" autoComplete="off" />
        </label>
        <select className="field" value={group || ""} onChange={(e) => onGroup(e.target.value)} aria-label="Lọc theo nhóm" disabled={groups.isError}>
          <option value="">Tất cả nhóm</option>
          {(Array.isArray(groups.data) ? groups.data : groups.data?.items || []).map((g) => <option key={g.id} value={g.id}>{g.name}{g.members != null ? ` (${g.members})` : ""}</option>)}
        </select>
      </div>
      <div className="max-h-[56vh] overflow-auto border-t border-line" role="region" aria-label="Danh sách tài khoản" tabIndex={0}>
        {fl.isPending ? <div className="p-3"><Skeleton rows={6} h={16} /></div>
          : fl.isError ? (isUnavailable(fl.error) ? <div className="p-3"><Unavailable what="Danh sách tài khoản" error={fl.error} onRetry={fl.refetch} retrying={fl.isFetching} /></div> : <div className="p-3"><ErrLine error={fl.error} /></div>)
          : items.length === 0 ? <p className="m-0 p-3 text-[12.5px] text-muted">{dq || group ? "Không có tài khoản khớp bộ lọc." : "Chưa có tài khoản nào được quản lý."}</p>
          : (
            <ul className="m-0 p-0 list-none">
              {items.map((a) => {
                const on = a.account_id === value;
                return (
                  <li key={a.account_id}>
                    <button type="button" onClick={() => onPick(a.account_id)} aria-current={on ? "true" : undefined}
                      className={cn("w-full text-left grid gap-0.5 px-3 py-2 border-0 border-b border-line bg-transparent cursor-pointer text-fg hover:bg-panel2 focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2", on && "!bg-[color-mix(in_srgb,var(--accent)_10%,var(--panel))] shadow-[inset_3px_0_0_var(--accent)]")}>
                      <span className="text-[12.5px] font-semibold truncate">{a.label || a.client_name || a.account_id}{on && <span className="fl-sr"> (đang chọn)</span>}</span>
                      <span className="num text-[11.5px] text-muted truncate">{a.account_id}</span>
                      {a.groups?.length > 0 && <span className="fl-cell-chips">{a.groups.slice(0, 3).map((g) => <GroupChip key={g.id} g={g} />)}{a.groups.length > 3 && <span className="text-[11px] text-faint">+{a.groups.length - 3}</span>}</span>}
                    </button>
                  </li>
                );
              })}
            </ul>)}
        {total > items.length && <p className="m-0 p-2 text-[11.5px] text-faint border-t border-line">Hiển thị {items.length}/{total} — gõ để thu hẹp.</p>}
      </div>
    </Panel>
  );
}
