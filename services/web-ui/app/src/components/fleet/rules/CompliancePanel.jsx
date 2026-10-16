import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, CheckCircle2, AlertTriangle, XOctagon, Minus, Clock, RefreshCw, X } from "lucide-react";
import { Panel } from "../../ui";
import { EmptyState, ErrorState, TableSkeleton } from "../../ux/States";
import { useHashQuery } from "../../../ux/urlstate";
import { useCompliance, useGroups, useTags, useRuleAssignments, KIND_VN, COMP_VN } from "../../../lib/fleetQueries";
import { isUnavailable } from "../../../lib/fleetApi";
import { CompStatus, GroupChip, UsageBar, Unavailable, ago, fmtDTfull, fmtNum } from "../bits";

const KPI = [
  { k: "red", icon: XOctagon, tone: "bad" },
  { k: "yellow", icon: AlertTriangle, tone: "warn" },
  { k: "green", icon: CheckCircle2, tone: "ok" },
  { k: "na", icon: Minus, tone: "mute" },
];

function useNow(ms = 30_000) {
  const [n, setN] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setN(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return n;
}

/** "reset sau 3 giờ 12 phút" / "đã qua mốc reset". */
export function resetIn(t, now) {
  const x = t ? Date.parse(t) : NaN;
  if (!Number.isFinite(x)) return "";
  const s = Math.round((x - now) / 1000);
  if (s <= 0) return "đã qua mốc reset";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h >= 24) return `reset sau ${Math.floor(h / 24)} ngày ${h % 24} giờ`;
  if (h > 0) return `reset sau ${h} giờ ${m} phút`;
  return `reset sau ${Math.max(1, m)} phút`;
}

const cmp = {
  usage: (a, b) => (a.usage_pct ?? -1) - (b.usage_pct ?? -1),
  acc: (a, b) => String(a.label || a.account_id).localeCompare(String(b.label || b.account_id), "vi"),
  reset: (a, b) => (Date.parse(a.reset_at) || Infinity) - (Date.parse(b.reset_at) || Infinity),
};
const goAccount = (id) => { location.hash = `#/doi-tai-khoan?q=${encodeURIComponent(id)}`; };

/** Bảng "Tuân thủ luật toàn đội". */
export default function CompliancePanel() {
  const [status, setStatus] = useHashQuery("tt", "");
  const [group, setGroup] = useHashQuery("nhom", "");
  const [tag, setTag] = useHashQuery("tag", "");
  const [asgId, setAsgId] = useHashQuery("luat", "");
  const [sort, setSort] = useState({ key: "usage", dir: -1 });
  const params = { group, tag, status, assignment: asgId, limit: 1000 };
  const q = useCompliance(params);
  const all = useCompliance({ limit: 1 }, { refetchInterval: 30_000 }); // tổng tóm tắt không phụ thuộc bộ lọc
  const gq = useGroups(); const tq = useTags(); const aq = useRuleAssignments();
  const now = useNow();
  const groups = gq.data?.items || [];
  const tags = tq.data?.items || [];
  const asgs = aq.data?.items || [];
  const sum = (all.data || q.data)?.summary || {};
  const items = useMemo(() => {
    const rows = [...(q.data?.items || [])];
    const f = cmp[sort.key];
    rows.sort((a, b) => sort.dir * f(a, b) || cmp.acc(a, b));
    return rows;
  }, [q.data, sort]);
  const filtered = !!(status || group || tag || asgId);
  const clear = () => { setStatus(""); setGroup(""); setTag(""); setAsgId(""); };
  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === "usage" ? -1 : 1 }));
  const sortTh = (k, children, className) => (
    <th key={k} scope="col" className={className} aria-sort={sort.key === k ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => toggleSort(k)}>{children}{sort.key === k && (sort.dir > 0 ? <ArrowUp size={12} aria-hidden="true" /> : <ArrowDown size={12} aria-hidden="true" />)}</button>
    </th>);
  const gName = groups.find((g) => g.id === group)?.name;
  const aName = asgs.find((a) => a.id === asgId)?.template_name;

  return (
    <Panel title="Tuân thủ luật toàn đội" pad={false} right={<span className="fl-count" aria-live="polite">{q.isFetching ? <RefreshCw size={12} className="inline ux-spin" aria-hidden="true" /> : null} {q.data ? `${items.length} dòng` : ""}</span>}>
      <div className="p-3 grid gap-3">
        <ul className="fl-kpis" aria-label="Tóm tắt tuân thủ (bấm để lọc)">
          {KPI.map(({ k, icon: Icon, tone }) => {
            const n = sum[k] ?? 0;
            return (
              <li key={k}>
                <button type="button" className={`fl-kpi t-${tone} w-full`} data-zero={n === 0 ? "1" : undefined} aria-pressed={status === k} onClick={() => setStatus(status === k ? "" : k)}>
                  <span className="fl-kpi-l"><Icon size={13} aria-hidden="true" />{COMP_VN[k]}</span>
                  <span className="fl-kpi-n">{n}</span>
                </button>
              </li>);
          })}
          <li>
            <div className="fl-kpi t-info !cursor-default" role="group" aria-label="Dữ liệu cũ">
              <span className="fl-kpi-l"><Clock size={13} aria-hidden="true" />Dữ liệu cũ</span>
              <span className="fl-kpi-n" data-zero={(sum.stale ?? 0) === 0 ? "1" : undefined}>{sum.stale ?? 0}</span>
            </div>
          </li>
        </ul>

        <div className="fl-bar-tools" role="group" aria-label="Bộ lọc tuân thủ">
          <label className="inline-flex items-center gap-1 text-[12px] text-muted min-w-0 max-w-full">Nhóm
            <select className="field min-w-0 max-w-full" value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Lọc theo nhóm">
              <option value="">Tất cả nhóm</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select></label>
          <label className="inline-flex items-center gap-1 text-[12px] text-muted min-w-0 max-w-full">Tag
            <select className="field min-w-0 max-w-full" value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Lọc theo tag">
              <option value="">Tất cả tag</option>{tags.map((t) => { const n = typeof t === "string" ? t : t.tag; return <option key={n} value={n}>#{n}</option>; })}
            </select></label>
          <label className="inline-flex items-center gap-1 text-[12px] text-muted min-w-0 max-w-full">Luật
            <select className="field min-w-0 max-w-full" value={asgId} onChange={(e) => setAsgId(e.target.value)} aria-label="Lọc theo luật">
              <option value="">Tất cả luật</option>{asgs.map((a) => <option key={a.id} value={a.id}>{a.template_name}{a.scope_label ? ` · ${a.scope_label}` : ""}</option>)}
            </select></label>
          <label className="inline-flex items-center gap-1 text-[12px] text-muted min-w-0 max-w-full">Trạng thái
            <select className="field min-w-0 max-w-full" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Lọc theo trạng thái">
              <option value="">Tất cả</option>{Object.entries(COMP_VN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></label>
          {filtered && <button type="button" className="btn" onClick={clear}><X size={13} aria-hidden="true" />Xoá lọc</button>}
        </div>
        {filtered && (
          <div className="fl-active-filters" aria-label="Bộ lọc đang bật">
            {status && <span className="fl-fchip">{COMP_VN[status]}<button type="button" onClick={() => setStatus("")} aria-label="Bỏ lọc trạng thái"><X size={11} aria-hidden="true" /></button></span>}
            {group && <span className="fl-fchip">Nhóm: {gName || "…"}<button type="button" onClick={() => setGroup("")} aria-label="Bỏ lọc nhóm"><X size={11} aria-hidden="true" /></button></span>}
            {tag && <span className="fl-fchip">Tag: #{tag}<button type="button" onClick={() => setTag("")} aria-label="Bỏ lọc tag"><X size={11} aria-hidden="true" /></button></span>}
            {asgId && <span className="fl-fchip">Luật: {aName || "…"}<button type="button" onClick={() => setAsgId("")} aria-label="Bỏ lọc luật"><X size={11} aria-hidden="true" /></button></span>}
          </div>)}
      </div>

      {q.isPending ? <div className="p-3 pt-0"><TableSkeleton rows={5} cols={6} /></div>
        : q.isError ? <div className="p-3 pt-0">{isUnavailable(q.error) ? <Unavailable what="Bảng tuân thủ" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /> : <ErrorState compact error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} what="tuân thủ luật" />}</div>
        : !items.length ? <div className="p-3 pt-0"><EmptyState compact title={filtered ? "Không có dòng nào khớp bộ lọc" : "Chưa có kết quả tuân thủ"}
            hint={filtered ? "Thử bỏ bớt bộ lọc." : "Cần gán luật cho nhóm/tag/tài khoản (mục “Gán luật”) và có tài khoản đang hoạt động; kết quả xuất hiện sau vài phút."}
            actions={filtered ? [{ label: "Xoá bộ lọc", onClick: clear }] : undefined} /></div>
        : (
          <div className="fl-tablewrap relative">
            <table className="fl-tbl">
              <caption className="fl-sr">Tuân thủ luật theo tài khoản, sắp xếp theo {sort.key === "usage" ? "mức dùng hạn mức" : sort.key === "acc" ? "tài khoản" : "mốc reset"}</caption>
              <thead><tr>
                {sortTh("acc", "Tài khoản")}
                <th scope="col">Luật</th>
                <th scope="col">Trạng thái</th>
                {sortTh("usage", "Mức dùng hạn mức")}
                <th scope="col" className="r">Giá trị / Hạn mức</th>
                {sortTh("reset", "Mốc reset (giờ VN)")}
                <th scope="col">Đánh giá</th>
              </tr></thead>
              <tbody>
                {items.map((r) => (
                  <tr key={`${r.assignment_id}-${r.account_id}`} onClick={() => goAccount(r.account_id)}>
                    <td>
                      <a className="c-id no-underline text-fg hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" href={`#/doi-tai-khoan?q=${encodeURIComponent(r.account_id)}`} onClick={(e) => e.stopPropagation()} aria-label={`Mở tài khoản ${r.account_id} trong Đội tài khoản`}>{r.account_id}</a>
                      {r.label && r.label !== r.account_id && <span className="c-sub">{r.label}</span>}
                      {r.groups?.length > 0 && <span className="fl-cell-chips">{r.groups.slice(0, 3).map((g) => <GroupChip key={g} g={{ name: g }} />)}{r.groups.length > 3 && <span className="text-muted text-[11px]">+{r.groups.length - 3}</span>}</span>}
                    </td>
                    <td>{r.rule_name}<span className="c-sub">{KIND_VN[r.kind] || r.kind}</span></td>
                    <td><CompStatus status={r.status} stale={r.stale} /></td>
                    <td style={{ minWidth: "11rem" }}><UsageBar pct={r.usage_pct} status={r.status} headroom={r.headroom} unit={r.unit} label={r.rule_name} /></td>
                    <td className="r num" style={{ whiteSpace: "nowrap" }}>{r.value == null ? "—" : fmtNum(r.value)} <span className="text-muted">/ {r.limit == null ? "—" : fmtNum(r.limit)}{r.unit ? ` ${r.unit}` : ""}</span></td>
                    <td style={{ whiteSpace: "nowrap" }}>{r.reset_at ? <><span className="num">{fmtDTfull(r.reset_at)}</span><span className="c-sub">{resetIn(r.reset_at, now)}</span></> : <span className="text-muted">—</span>}</td>
                    <td style={{ whiteSpace: "nowrap" }}><span title={fmtDTfull(r.evaluated_at)}>{ago(r.evaluated_at, now)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>)}
    </Panel>
  );
}
