// Bảng danh sách đội tài khoản (desktop) + danh sách thẻ (mobile). Chọn nhiều dòng, sắp xếp phía máy chủ, bấm dòng mở hồ sơ.
import { useEffect, useState } from "react";
import { Activity, ArrowDown, ArrowUp, ChevronsUpDown, Hourglass, Pause, Siren, Wifi, WifiOff } from "lucide-react";
import { ACC_STATUS_VN, EA_VN } from "../../lib/fleetQueries";
import { CompStatus, GroupChip, Pill, TagChip, UsageBar, ago, fmtDTfull } from "./bits";

export function useNarrow(px = 760) {
  const q = `(max-width:${px}px)`;
  const [m, setM] = useState(() => typeof matchMedia !== "undefined" && matchMedia(q).matches);
  useEffect(() => { const mq = matchMedia(q); const h = () => setM(mq.matches); h(); mq.addEventListener("change", h); return () => mq.removeEventListener("change", h); }, [q]);
  return m;
}

const EA = { online: { tone: "ok", icon: Wifi }, degraded: { tone: "warn", icon: Activity }, offline: { tone: "bad", icon: WifiOff }, unknown: { tone: "mute", icon: Hourglass } };

export function StatePills({ r }) {
  if (r.status === "suspended") return <Pill tone="mute" icon={Pause}>{ACC_STATUS_VN.suspended}</Pill>;
  if (r.status === "pending") return <Pill tone="info" icon={Hourglass}>{ACC_STATUS_VN.pending}</Pill>;
  const e = EA[r.ea_status] || EA.unknown;
  return <Pill tone={e.tone} icon={e.icon} title={r.ea_latency_ms != null ? `Độ trễ EA ${r.ea_latency_ms} ms` : undefined}>{EA_VN[r.ea_status] || EA_VN.unknown}</Pill>;
}
const Chips = ({ r }) => (
  <span className="fl-cell-chips">
    {(r.groups || []).map((g) => <GroupChip key={g.id} g={g} />)}
    {(r.tags || []).map((t) => <TagChip key={t} t={t} />)}
    {!(r.groups?.length || r.tags?.length) && <span className="text-faint">—</span>}
  </span>
);
const Comp = ({ r }) => {
  const c = r.compliance || {};
  if (!c.status) return <span className="text-faint" title="Chưa có luật nào được áp cho tài khoản này">Chưa gán luật</span>;
  return (
    <div className="grid gap-1" style={{ minWidth: 130 }}>
      <CompStatus status={c.status} />
      {c.worst_usage_pct != null && <UsageBar compact pct={c.worst_usage_pct} status={c.status} label={c.worst_rule || "Mức dùng hạn mức"} />}
      {c.worst_usage_pct != null && <span className="text-[11px] text-muted num">{c.worst_usage_pct.toFixed(0)}%{c.worst_rule ? ` · ${c.worst_rule}` : ""}</span>}
    </div>
  );
};
const Inc = ({ n }) => (n > 0 ? <Pill tone="bad" icon={Siren}>{n}</Pill> : <span className="text-faint">—</span>);

const COLS = [
  { k: "label", label: "Tài khoản" }, { k: "account_id", label: "Mã" }, { k: "status", label: "Trạng thái" }, { k: null, label: "Nhóm & tag" },
  { k: "usage", label: "Tuân thủ luật" }, { k: null, label: "Sự cố" }, { k: "last_seen", label: "Lần cuối" },
];

export default function FleetTable({ rows, sort, dir, onSort, selected, onToggle, onTogglePage, onOpen, activeId }) {
  const narrow = useNarrow();
  const allOn = rows.length > 0 && rows.every((r) => selected.has(r.account_id));
  const someOn = rows.some((r) => selected.has(r.account_id));
  const open = (e, id) => { if (e.target.closest("input,button,a")) return; onOpen(id); };

  if (narrow) {
    return (
      <ul className="fl-list p-2" aria-label="Danh sách tài khoản">
        {rows.map((r) => (
          <li key={r.account_id} className={`fl-card ${r.compliance?.status === "red" ? "t-bad" : r.compliance?.status === "yellow" ? "t-warn" : r.ea_status === "offline" ? "t-bad" : "t-ok"}`} aria-current={activeId === r.account_id ? "true" : undefined}>
            <div className="flex items-start gap-2 min-w-0">
              <input type="checkbox" className="fl-chk mt-1" checked={selected.has(r.account_id)} onChange={() => onToggle(r.account_id)} aria-label={`Chọn ${r.label || r.account_id}`} />
              <button type="button" className="all-unset text-left min-w-0 flex-1" style={{ all: "unset", cursor: "pointer", display: "block", minWidth: 0, flex: 1 }} onClick={() => onOpen(r.account_id)}>
                <b className="block truncate">{r.label || r.login}</b>
                <span className="num text-[11.5px] text-muted">{r.account_id}{r.server ? ` · ${r.server}` : ""}</span>
              </button>
              <StatePills r={r} />
            </div>
            <div className="flex flex-wrap items-center gap-2"><Chips r={r} /></div>
            <div className="flex items-center justify-between gap-2"><Comp r={r} /><span className="grid justify-items-end gap-1"><Inc n={r.incidents_open} /><span className="text-[11px] text-muted">{ago(r.last_seen_at)}</span></span></div>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="fl-tablewrap">
      <table className="fl-tbl" style={{ minWidth: 900 }}>
        <caption className="fl-sr">Danh sách tài khoản trong đội. Bấm một dòng để mở hồ sơ.</caption>
        <thead>
          <tr>
            <th className="c-chk"><input type="checkbox" className="fl-chk" checked={allOn} ref={(el) => { if (el) el.indeterminate = !allOn && someOn; }} onChange={onTogglePage} aria-label="Chọn/bỏ chọn mọi dòng trên trang này" /></th>
            {COLS.map((c) => {
              const on = c.k && sort === c.k;
              return (
                <th key={c.label} aria-sort={on ? (dir === "desc" ? "descending" : "ascending") : c.k ? "none" : undefined}>
                  {c.k ? (
                    <button type="button" onClick={() => onSort(c.k, on && dir === "asc" ? "desc" : "asc")} title="Bấm để sắp xếp">
                      {c.label}{on ? (dir === "desc" ? <ArrowDown size={12} aria-hidden="true" /> : <ArrowUp size={12} aria-hidden="true" />) : <ChevronsUpDown size={12} className="opacity-40" aria-hidden="true" />}
                    </button>
                  ) : c.label}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.account_id} tabIndex={0} aria-selected={selected.has(r.account_id)} data-active={activeId === r.account_id ? "1" : undefined}
              onClick={(e) => open(e, r.account_id)} onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onOpen(r.account_id); }}>
              <td className="c-chk"><input type="checkbox" className="fl-chk" checked={selected.has(r.account_id)} onChange={() => onToggle(r.account_id)} aria-label={`Chọn ${r.label || r.account_id}`} /></td>
              <td><b className="font-semibold">{r.label || r.login}</b>{r.client_name && r.client_name !== r.label ? <span className="c-sub">{r.client_name}</span> : null}</td>
              <td className="c-id">{r.account_id}<span className="c-sub">{r.platform?.toUpperCase()}{r.server ? ` · ${r.server}` : ""}</span></td>
              <td><StatePills r={r} />{r.ea_version ? <span className="c-sub num">EA {r.ea_version}</span> : null}</td>
              <td><Chips r={r} /></td>
              <td><Comp r={r} /></td>
              <td><Inc n={r.incidents_open} /></td>
              <td title={fmtDTfull(r.last_seen_at)}>{r.last_seen_at ? ago(r.last_seen_at) : <span className="text-faint">chưa có</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
