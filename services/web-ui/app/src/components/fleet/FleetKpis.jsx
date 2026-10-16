// Thanh KPI của Fleet command center: 6 ô, bấm = lọc danh sách (bấm lần nữa = bỏ lọc).
import { Activity, AlertTriangle, Siren, Users, WifiOff, XOctagon } from "lucide-react";

const TILES = [
  { id: "total", label: "Tài khoản", icon: Users, tone: "info", get: (c) => c.total, filter: {}, isOn: (f) => !Object.keys(f).length },
  { id: "online", label: "Trực tuyến", icon: Activity, tone: "ok", get: (c) => c.online, filter: { ea: "online" }, isOn: (f) => f.ea === "online" },
  { id: "offline", label: "Mất kết nối", icon: WifiOff, tone: "bad", get: (c) => c.offline, filter: { ea: "offline" }, isOn: (f) => f.ea === "offline" },
  { id: "red", label: "Vi phạm luật", icon: XOctagon, tone: "bad", get: (c) => c.red, filter: { compliance: "red" }, isOn: (f) => f.compliance === "red" },
  { id: "yellow", label: "Sát ngưỡng", icon: AlertTriangle, tone: "warn", get: (c) => c.yellow, filter: { compliance: "yellow" }, isOn: (f) => f.compliance === "yellow" },
  { id: "inc", label: "Sự cố chưa xử lý", icon: Siren, tone: "bad", get: (c) => c.incidents_open ?? c.accounts_with_incidents, filter: { incident: "1" }, isOn: (f) => f.incident === "1" },
];
const CLEAR_ALL = { group: "", tag: "", status: "", ea: "", compliance: "", incident: "", q: "" };
const CLEAR_KPI = { ea: "", compliance: "", incident: "" }; // KPI chỉ đổi chiều của nó, giữ nhóm/tag/tìm kiếm

export default function FleetKpis({ counts, filters, onFilter, loading }) {
  const c = counts || {};
  return (
    <ul className="fl-kpis" aria-label="Chỉ số tổng quan đội tài khoản (bấm để lọc)">
      {TILES.map((t) => {
        const n = loading && !counts ? null : t.get(c);
        const on = t.isOn(filters);
        return (
          <li key={t.id} className="contents">
            <button type="button" className={`fl-kpi t-${t.tone}`} data-zero={n === 0 ? "1" : undefined} aria-pressed={on}
              onClick={() => onFilter(t.id === "total" ? CLEAR_ALL : on ? CLEAR_KPI : { ...CLEAR_KPI, ...t.filter })}
              title={t.id === "total" ? "Bỏ mọi bộ lọc" : `Lọc: ${t.label}`}>
              <span className="fl-kpi-l"><t.icon size={13} aria-hidden="true" />{t.label}</span>
              <span className="fl-kpi-n">{n == null ? "…" : n}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
