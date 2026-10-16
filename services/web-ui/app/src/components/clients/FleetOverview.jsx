import { useMemo, useState } from "react";
import { Activity, BellRing, Layers, ShieldAlert, Server, Wallet } from "lucide-react";
import { Chip, Panel, Seg, Stat, cn } from "../ui";
import { ageText } from "../../lib/freshness";
import { clean, money, rel } from "../../lib/format";
import { HEALTH_VN, LATEST_EA, summarize } from "../../lib/clientsQueries";
import { RiskChip, StatusChip, fmtDT } from "./bits";

const METRICS = [
  { value: "health", label: "Sức khoẻ EA" },
  { value: "lag", label: "Độ trễ dữ liệu" },
  { value: "margin", label: "Margin" },
  { value: "dd", label: "Drawdown" },
];
const grey = { tone: "idle", text: "—" };

/** Màu + chữ của một ô theo thước đo. Luôn kèm chữ để không chỉ dựa vào màu. */
export function cellOf(r, metric) {
  if (r.status === "suspended") return { tone: "idle", text: "Đình chỉ" };
  if (r.status === "pending") return { tone: "idle", text: "Chờ ghép" };
  if (metric === "health") return { tone: r.health === "online" ? "up" : r.health === "lag" ? "warn" : "down", text: HEALTH_VN[r.health] };
  if (metric === "lag") {
    if (r.age == null) return { tone: "down", text: "Chưa có" };
    return { tone: r.age <= 30 ? "up" : r.age <= 120 ? "up2" : r.age <= 900 ? "warn" : "down", text: ageText(r.age) };
  }
  if (metric === "margin") {
    if (r.marginLevel == null) return grey;
    return { tone: r.marginLevel >= 300 ? "up" : r.marginLevel >= 150 ? "warn" : "down", text: `${r.marginLevel.toFixed(0)}%` };
  }
  if (r.dd == null) return grey;
  return { tone: r.dd < 5 ? "up" : r.dd < 10 ? "warn" : "down", text: `${r.dd.toFixed(1)}%` };
}
const LEGEND = {
  health: [["up", "Trực tuyến ≤ 2 phút"], ["warn", "Chậm ≤ 15 phút"], ["down", "Mất kết nối"], ["idle", "Chờ ghép / đình chỉ"]],
  lag: [["up", "≤ 30 giây"], ["up2", "≤ 2 phút"], ["warn", "≤ 15 phút"], ["down", "> 15 phút"]],
  margin: [["up", "≥ 300%"], ["warn", "150–300%"], ["down", "< 150%"], ["idle", "Không có vị thế"]],
  dd: [["up", "< 5%"], ["warn", "5–10%"], ["down", "≥ 10%"], ["idle", "Không có dữ liệu"]],
};

export function Heatmap({ rows, metric, hrefBase = "#/khach-hang/danh-sach/" }) {
  return (
    <>
      <ul className="hm-grid" aria-label="Bản đồ nhiệt sức khoẻ EA theo tài khoản">
        {rows.map((r) => {
          const c = cellOf(r, metric);
          const tip = [`${r.account_id}${r.label ? ` · ${r.label}` : ""}`, `Khách: ${r.client_name || "—"}`, `Server: ${r.server || "—"}`, `EA ${r.ea_version || "—"} · build ${r.terminal_build || "—"}`,
            `Dữ liệu cuối: ${r.lastData ? fmtDT(r.lastData) : "chưa có"}`, r.latency_ms != null ? `Độ trễ mạng EA: ${r.latency_ms} ms` : null, r.riskReasons.length ? `Rủi ro: ${r.riskReasons.join("; ")}` : null].filter(Boolean).join("\n");
          return (
            <li key={r.account_id}>
              <a href={`${hrefBase}${r.account_id}`} className={cn("hm-cell", `t-${c.tone}`)} title={tip} aria-label={`${r.account_id}, ${r.label || ""}: ${c.text}`}>
                <span className="hm-top"><b className="truncate">{r.label || r.login}</b><span className="hm-plat">{r.platform.toUpperCase()}</span></span>
                <span className="hm-val num">{c.text}</span>
                <span className="hm-sub truncate">{r.login}{r.eaOutdated ? " · EA cũ" : ""}</span>
              </a>
            </li>
          );
        })}
      </ul>
      <ul className="hm-legend" aria-label="Chú giải màu">
        {LEGEND[metric].map(([t, l]) => <li key={t}><i className={`hm-sw t-${t}`} aria-hidden="true" />{l}</li>)}
      </ul>
    </>
  );
}

export default function FleetOverview({ rows, gwOk }) {
  const [metric, setMetric] = useState("health");
  const sum = useMemo(() => summarize(rows), [rows]);
  const risky = useMemo(() => rows.filter((r) => r.riskLevel === "crit" || r.riskLevel === "warn").sort((a, b) => (b.riskLevel === "crit") - (a.riskLevel === "crit") || (a.marginLevel ?? 9e9) - (b.marginLevel ?? 9e9)), [rows]);
  const withAlert = useMemo(() => rows.filter((r) => r.lastAlert).sort((a, b) => Date.parse(b.lastAlert.ts) - Date.parse(a.lastAlert.ts)).slice(0, 8), [rows]);
  const sorted = useMemo(() => [...rows].sort((a, b) => ({ offline: 0, never: 0, lag: 1, online: 2, pending: 3, suspended: 4 }[a.health] - { offline: 0, never: 0, lag: 1, online: 2, pending: 3, suspended: 4 }[b.health]) || String(a.label).localeCompare(String(b.label))), [rows]);
  const vers = Object.entries(sum.ver).sort((a, b) => b[0].localeCompare(a[0], undefined, { numeric: true }));
  const servers = Object.entries(sum.server).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid gap-3">
      <section aria-label="Tổng quan fleet" className="kpi-row">
        <Kpi label="Tổng tài khoản" value={sum.total} sub={`${rows.filter((r) => r.platform === "mt5").length} MT5 · ${rows.filter((r) => r.platform === "mt4").length} MT4`} />
        <Kpi label="Trực tuyến" value={sum.online} sub={sum.lag ? `+${sum.lag} chậm` : "EA đang gửi dữ liệu"} tone="up" />
        <Kpi label="Mất kết nối" value={sum.down} sub={sum.down ? "cần kiểm tra EA" : "không có"} tone={sum.down ? "down" : ""} />
        <Kpi label="Chờ ghép cặp" value={sum.pending} sub="chưa cài/ghép EA" />
        <Kpi label="Đình chỉ" value={sum.suspended} sub="không nhận dữ liệu" />
        <Kpi label="Tổng equity" value={gwOk?.snaps === false ? "—" : money(sum.equity)} sub="tài khoản không đình chỉ" icon={Wallet} />
        <Kpi label="Exposure ước tính" value={gwOk?.risks === false ? "—" : money(sum.exposure)} sub="equity × đòn bẩy hiệu dụng" icon={Layers} />
        <Kpi label="Vi phạm rủi ro" value={sum.crit + sum.warn} sub={`${sum.crit} vượt · ${sum.warn} gần ngưỡng`} tone={sum.crit ? "down" : sum.warn ? "accent" : ""} />
      </section>

      <Panel title="Bản đồ nhiệt sức khoẻ EA" icon={Activity} right={<Seg value={metric} onChange={setMetric} options={METRICS} label="Thước đo" />}>
        {rows.length ? <Heatmap rows={sorted} metric={metric} /> : <p className="m-0 text-muted">Chưa có tài khoản nào. Tạo tài khoản đầu tiên ở tab Danh sách.</p>}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Vi phạm ngưỡng rủi ro" icon={ShieldAlert} right={<Chip tone={risky.length ? "down" : "up"}>{risky.length}</Chip>} pad={false}>
          {risky.length ? (
            <ul className="m-0 p-0 list-none divide-y divide-line">
              {risky.map((r) => (
                <li key={r.account_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <a href={`#/khach-hang/danh-sach/${r.account_id}`} className="font-medium no-underline hover:underline min-w-0 truncate">{r.label || r.account_id}</a>
                  <span className="num text-[11.5px] text-faint">{r.account_id}</span>
                  <span className="ml-auto"><RiskChip level={r.riskLevel} reasons={r.riskReasons} /></span>
                  <span className="basis-full text-[12px] text-muted">{r.riskReasons.join(" · ") || "Vượt ngưỡng ngân sách."}</span>
                </li>
              ))}
            </ul>
          ) : <p className="m-0 p-3 text-muted">Không có tài khoản nào vượt hoặc gần ngưỡng rủi ro.</p>}
        </Panel>

        <Panel title="Cảnh báo gần nhất theo tài khoản" icon={BellRing} pad={false}>
          {withAlert.length ? (
            <ul className="m-0 p-0 list-none divide-y divide-line">
              {withAlert.map((r) => (
                <li key={r.account_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <Chip tone={r.lastAlert.level === "crit" ? "down" : r.lastAlert.level === "warn" ? "accent" : ""}>{r.lastAlert.level === "crit" ? "Nghiêm trọng" : r.lastAlert.level === "warn" ? "Cảnh báo" : "Thông tin"}</Chip>
                  <a href={`#/khach-hang/danh-sach/${r.account_id}`} className="num text-[12px] no-underline hover:underline">{r.account_id}</a>
                  <span className="ml-auto text-[11.5px] text-faint" title={fmtDT(r.lastAlert.ts)}>{rel(r.lastAlert.ts)}</span>
                  <span className="basis-full text-[12.5px]">{clean(r.lastAlert.title)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="m-0 p-3 text-muted">{gwOk?.alerts === false ? "Chưa tải được cảnh báo." : "Chưa có cảnh báo gắn với tài khoản nào."}</p>}
        </Panel>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Phiên bản EA" icon={Server}>
          {vers.length ? (
            <ul className="m-0 p-0 list-none grid gap-2">
              {vers.map(([v, n]) => (
                <li key={v} className="grid grid-cols-[5rem_minmax(0,1fr)_auto] items-center gap-2 text-[12.5px]">
                  <span className="num">{v}</span>
                  <span className="h-[6px] rounded bg-panel2 overflow-hidden" aria-hidden="true"><span className="block h-full rounded" style={{ width: `${(n / sum.total) * 100}%`, background: v === LATEST_EA ? "var(--up)" : "var(--accent)" }} /></span>
                  <span className="num text-muted">{n} · {v === LATEST_EA ? "mới nhất" : "cần cập nhật"}</span>
                </li>
              ))}
            </ul>
          ) : <p className="m-0 text-muted">Chưa có EA nào báo phiên bản.</p>}
        </Panel>
        <Panel title="Broker / server" icon={Server}>
          {servers.length ? (
            <ul className="m-0 p-0 list-none grid gap-2">
              {servers.map(([s, n]) => (
                <li key={s} className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] items-center gap-2 text-[12.5px]">
                  <span className="truncate" title={s}>{s}</span>
                  <span className="h-[6px] rounded bg-panel2 overflow-hidden" aria-hidden="true"><span className="block h-full rounded" style={{ width: `${(n / sum.total) * 100}%`, background: "var(--info)" }} /></span>
                  <span className="num text-muted">{n}</span>
                </li>
              ))}
            </ul>
          ) : <p className="m-0 text-muted">Chưa có dữ liệu server.</p>}
        </Panel>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, tone, icon: Icon }) {
  return (
    <div className="kpi">
      <Stat label={<span className="inline-flex items-center gap-1">{Icon && <Icon size={12} aria-hidden="true" />}{label}</span>} value={value} sub={sub} tone={tone} big />
    </div>
  );
}
export { StatusChip };
