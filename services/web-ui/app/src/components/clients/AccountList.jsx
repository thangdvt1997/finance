import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Panel, Seg } from "../ui";
import { DataTable } from "../table";
import { money } from "../../lib/format";
import { ageText } from "../../lib/freshness";
import { HealthChip, RiskChip, StatusChip } from "./bits";

const FILTERS = [
  { value: "all", label: "Tất cả" }, { value: "online", label: "Trực tuyến" }, { value: "down", label: "Mất kết nối" },
  { value: "pending", label: "Chờ ghép" }, { value: "suspended", label: "Đình chỉ" }, { value: "risk", label: "Vi phạm rủi ro" },
];
const match = (r, f) => f === "all" || (f === "online" && (r.health === "online" || r.health === "lag")) || (f === "down" && (r.health === "offline" || r.health === "never")) ||
  (f === "pending" && r.status === "pending") || (f === "suspended" && r.status === "suspended") || (f === "risk" && (r.riskLevel === "crit" || r.riskLevel === "warn"));

export default function AccountList({ rows }) {
  const [q, setQ] = useState("");
  const [f, setF] = useState("all");
  const [plat, setPlat] = useState("");
  const data = useMemo(() => {
    const t = q.trim().toLowerCase();
    return rows.filter((r) => match(r, f) && (!plat || r.platform === plat) &&
      (!t || `${r.account_id} ${r.label} ${r.client_name} ${r.server} ${r.login}`.toLowerCase().includes(t)));
  }, [rows, q, f, plat]);

  const columns = useMemo(() => [
    { id: "acc", header: "Tài khoản", accessorFn: (r) => r.account_id, cell: ({ row: { original: r } }) => (
      <a href={`#/khach-hang/danh-sach/${r.account_id}`} className="no-underline hover:underline block min-w-[8rem]"><b className="block">{r.label || r.login}</b><span className="num text-[11.5px] text-muted">{r.account_id}</span></a>) },
    { id: "client", header: "Khách hàng", accessorFn: (r) => r.client_name || "", cell: (c) => c.getValue() || <span className="text-faint">—</span> },
    { id: "status", header: "Trạng thái", accessorFn: (r) => r.status, cell: ({ row: { original: r } }) => <StatusChip status={r.status} /> },
    { id: "health", header: "Kết nối EA", accessorFn: (r) => r.age ?? 9e9, cell: ({ row: { original: r } }) => <HealthChip row={r} /> },
    { id: "ea", header: "EA · build", accessorFn: (r) => r.ea_version || "", cell: ({ row: { original: r } }) => r.ea_version ? <span className="num">{r.ea_version}{r.eaOutdated && <span className="text-accent" title="Có bản mới hơn"> ↑</span>} <span className="text-faint">· {r.terminal_build || "—"}</span></span> : <span className="text-faint">—</span> },
    { id: "server", header: "Server", accessorFn: (r) => r.server || "", cell: (c) => <span className="block max-w-[11rem] truncate" title={c.getValue()}>{c.getValue() || "—"}</span> },
    { id: "equity", header: "Equity", accessorFn: (r) => r.equity ?? -1, meta: { align: "r" }, cell: ({ row: { original: r } }) => <span className="num">{r.equity == null ? "—" : money(r.equity)}</span> },
    { id: "margin", header: "Margin", accessorFn: (r) => r.marginLevel ?? 9e9, meta: { align: "r" }, cell: ({ row: { original: r } }) => <span className={`num ${r.marginLevel != null && r.marginLevel < 150 ? "down" : ""}`}>{r.marginLevel == null ? "—" : `${r.marginLevel.toFixed(0)}%`}</span> },
    { id: "dd", header: "DD", accessorFn: (r) => r.dd ?? -1, meta: { align: "r" }, cell: ({ row: { original: r } }) => <span className={`num ${r.dd != null && r.dd >= 10 ? "down" : ""}`}>{r.dd == null ? "—" : `${r.dd.toFixed(1)}%`}</span> },
    { id: "risk", header: "Rủi ro", accessorFn: (r) => ({ crit: 0, warn: 1, ok: 2, na: 3 }[r.riskLevel]), cell: ({ row: { original: r } }) => <RiskChip level={r.riskLevel} reasons={r.riskReasons} /> },
    { id: "seen", header: "Dữ liệu cuối", accessorFn: (r) => r.age ?? 9e9, meta: { align: "r" }, cell: ({ row: { original: r } }) => <span className="num text-muted">{r.age == null ? "—" : ageText(r.age)}</span> },
  ], []);

  return (
    <Panel title={`Khách hàng & tài khoản (${data.length}/${rows.length})`} pad={false}
      right={<Seg value={plat} onChange={(v) => setPlat(plat === v ? "" : v)} options={[{ value: "mt4", label: "MT4" }, { value: "mt5", label: "MT5" }]} label="Lọc nền tảng (bấm lại để bỏ)" />}>
      <div className="flex flex-wrap items-center gap-2 p-3 border-b border-line">
        <label className="relative flex-1 min-w-[12rem] max-w-[22rem]">
          <span className="sr-only">Tìm theo số tài khoản, nhãn, tên khách, server</span>
          <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-faint pointer-events-none" aria-hidden="true" />
          <input className="field w-full !pl-7" type="search" placeholder="Tìm số TK, nhãn, khách, server…" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <div className="scroll-x max-w-full"><Seg value={f} onChange={setF} options={FILTERS} label="Lọc trạng thái" /></div>
      </div>
      <DataTable data={data} columns={columns} minWidth={980} getRowId={(r) => r.account_id} initialSort={[{ id: "risk", desc: false }]} empty="Không có tài khoản khớp bộ lọc." />
    </Panel>
  );
}
