// Bản đồ nhiệt thị trường: treemap / lưới / bảng. Diện tích ô = giá trị giao dịch trung bình 20 phiên (không có vốn hoá).
// Dùng làm trang (pages/Heatmaps.jsx) và widget (widgets/heatmap-market.jsx). Số liệu thống kê, không phải khuyến nghị.
import { useCallback, useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Chip, Seg, Sparkline, cn } from "../ui";
import HeatmapVN from "../vn/Heatmap";
import { useVnHeatmap } from "../../lib/vn";
import { ASSET_GROUPS, chartHref, fcompact, fpct, fprice, useHeatmap } from "../../lib/intel";
import { AsOf, HeatTreemap, Pct, QState, SymLink, useLocal } from "./bits";

export const HEAT_GROUPS = [...ASSET_GROUPS.filter((g) => g.value !== "vn"), { value: "vn", label: "Ngành VN" }];
const PERIODS = [
  { value: "1d", label: "1D" }, { value: "1w", label: "1W" }, { value: "1m", label: "1M" },
  { value: "3m", label: "3M" }, { value: "ytd", label: "YTD" }, { value: "1y", label: "1Y" },
];
const CAPS = { "1d": 3, "1w": 6, "1m": 12, "3m": 20, ytd: 30, "1y": 40 };
const VIEWS = [{ value: "map", label: "Treemap" }, { value: "grid", label: "Lưới" }, { value: "table", label: "Bảng" }];
const SIZE_NOTE = "Kích thước ô: giá trị giao dịch TB 20 phiên";
const openChart = (sym) => { window.location.hash = chartHref(sym); };

function Legend({ cap }) {
  const steps = ["hd-4", "hd-2", "h-0", "hu-2", "hu-4"];
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted" aria-label={`Thang màu: từ −${cap}% đến +${cap}%`}>
      <span className="num">−{cap}%</span>
      {steps.map((s) => <i key={s} className={cn("inline-block w-4 h-3 rounded-[2px]", s)} aria-hidden="true" />)}
      <span className="num">+{cap}%</span>
    </span>
  );
}

function SortTh({ k, label, sort, onSort, right }) {
  const on = sort.k === k;
  return (
    <th className={right ? "r" : undefined} aria-sort={on ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(k)}>
        {label}{on && (sort.dir > 0 ? <ArrowUp size={11} aria-hidden="true" /> : <ArrowDown size={11} aria-hidden="true" />)}
      </button>
    </th>
  );
}

function HeatTable({ items, limit, onMore }) {
  const [sort, setSort] = useState({ k: "turnover", dir: -1 });
  const onSort = (k) => setSort((s) => (s.k === k ? { k, dir: -s.dir } : { k, dir: k === "label" || k === "name" ? 1 : -1 }));
  const rows = useMemo(() => {
    const a = [...items];
    const k = sort.k;
    a.sort((x, y) => {
      const vx = x[k], vy = y[k];
      if (vx == null && vy == null) return 0;
      if (vx == null) return 1;
      if (vy == null) return -1;
      return typeof vx === "string" ? vx.localeCompare(vy) * sort.dir : (vx - vy) * sort.dir;
    });
    return a;
  }, [items, sort]);
  const shown = rows.slice(0, limit);
  return (
    <div className="overflow-x-auto">
      <table className="tbl" aria-label="Bảng bản đồ nhiệt">
        <thead>
          <tr>
            <SortTh k="label" label="Mã" sort={sort} onSort={onSort} />
            <SortTh k="name" label="Tên" sort={sort} onSort={onSort} />
            <SortTh k="change_pct" label="% thay đổi" sort={sort} onSort={onSort} right />
            <SortTh k="last" label="Giá" sort={sort} onSort={onSort} right />
            <SortTh k="turnover" label="GTGD TB 20 phiên" sort={sort} onSort={onSort} right />
            <th className="r">Xu hướng</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((it) => (
            <tr key={it.symbol} className="cursor-pointer" onClick={() => openChart(it.symbol)}>
              <td><SymLink symbol={it.symbol} label={it.label} /></td>
              <td className="text-muted max-w-[18rem] truncate" title={it.name}>{it.name}</td>
              <td className="r"><Pct v={it.change_pct} /></td>
              <td className="r num">{fprice(it.last)}</td>
              <td className="r num">{fcompact(it.turnover)}</td>
              <td className="r"><span className="inline-block align-middle"><Sparkline values={it.spark} width={72} height={22} /></span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > limit && <div className="p-2"><button className="btn" onClick={onMore}>Hiện thêm ({rows.length - limit})</button></div>}
    </div>
  );
}

function HeatGrid({ items, cap }) {
  const sorted = useMemo(() => [...items].sort((a, b) => (b.turnover || 0) - (a.turnover || 0)), [items]);
  return (
    <div className="grid gap-1.5 grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))]" role="list" aria-label="Lưới bản đồ nhiệt">
      {sorted.map((it) => {
        const t = Math.min(Math.abs(it.change_pct ?? 0) / cap, 1);
        const hc = it.change_pct == null ? "h-na" : t < 0.06 ? "h-0" : `${it.change_pct > 0 ? "hu" : "hd"}-${t < 0.25 ? 1 : t < 0.5 ? 2 : t < 0.78 ? 3 : 4}`;
        return (
          <div key={it.symbol} role="listitem" className={cn("rounded-md px-2 py-1.5 grid gap-0.5 min-w-0", hc)} title={`${it.name} · GTGD TB 20 phiên ${fcompact(it.turnover)}`}>
            <a href={chartHref(it.symbol)} style={{ color: "inherit" }} className="font-semibold no-underline truncate">{it.label}</a>
            <span className="num text-[13px] font-semibold">{fpct(it.change_pct)}</span>
            <span className="num text-[11px] opacity-80 truncate">{fprice(it.last)}</span>
          </div>
        );
      })}
    </div>
  );
}

function IntelPart({ group, period, view, compact, height, byGroup }) {
  const q = useHeatmap(group, period);
  const [limit, setLimit] = useState(100);
  const d = q.data;
  const cap = (CAPS[period] || 3) * (group === "crypto" ? 1.3 : 1);
  const items = useMemo(() => (d?.items || []).map((it) => ({
    ...it,
    key: it.symbol,
    value: it.turnover || 0,
    pct: it.change_pct,
    tip: `Giá ${fprice(it.last)}<br/>GTGD TB 20 phiên: ${fcompact(it.turnover)}`,
  })), [d]);
  const tmItems = useMemo(() => items.map((it) => ({ key: it.key, name: `${it.label} · ${it.name}`, label: it.label, value: it.value, pct: it.pct, tip: it.tip, group: it.group })), [items]);
  const onSelect = useCallback((k) => openChart(k), []);
  const st = QState({
    q, compact, rows: 6,
    isEmpty: (x) => !x?.items?.length,
    empty: group === "sector" ? "Chưa có dữ liệu nhóm Ngành Mỹ (ETF)." : "Chưa có dữ liệu cho nhóm này.",
    hint: group === "sector" ? "Dữ liệu nhóm này xuất hiện sau khi hệ thống nạp xong lịch sử giá; vui lòng quay lại sau ít phút." : "Thử chọn nhóm hoặc kỳ khác.",
  });
  if (st) return st;
  const sm = d.summary || {};
  return (
    <div className={cn("grid gap-2", q.isPlaceholderData && "opacity-70")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Chip tone="up" title="Số mã tăng">▲ {sm.up ?? "—"} tăng</Chip>
        <Chip tone="down" title="Số mã giảm">▼ {sm.down ?? "—"} giảm</Chip>
        <span className="text-[12px] text-muted">TB <Pct v={sm.avg} /></span>
        <span className="text-[12px] text-muted">Trung vị <Pct v={sm.median} /></span>
        <span className="text-[11.5px] text-faint num">{d.count ?? items.length} mã</span>
        <AsOf ts={d.as_of} label="Dữ liệu đến" className="ml-auto" />
      </div>
      {view === "map" && (
        <HeatTreemap items={tmItems} height={height} cap={cap} onSelect={onSelect} groupKey={byGroup ? "group" : undefined} ariaLabel={`Bản đồ nhiệt ${group}, kỳ ${period}`} />
      )}
      {view === "grid" && <HeatGrid items={items} cap={cap} />}
      {view === "table" && <HeatTable items={items} limit={limit} onMore={() => setLimit((n) => n + 100)} />}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-faint">
        <Legend cap={Math.round(cap)} />
        <span>{SIZE_NOTE} · màu = % thay đổi · số % luôn in trong ô · bấm ô để mở biểu đồ</span>
      </div>
    </div>
  );
}

function VnPart({ height, compact }) {
  const [uni, setUni] = useState("vn100");
  const [size, setSize] = useState("marketcap");
  const q = useVnHeatmap({ universe: uni, size, per_sector: uni === "vn30" ? 30 : 18 });
  const st = QState({ q, compact, rows: 6, isEmpty: (x) => !x?.sectors?.length, empty: "Chưa có dữ liệu ngành cho nhóm này.", hint: "Dữ liệu vốn hoá nạp sau phiên; thử lại sau ít phút." });
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Seg label="Rổ cổ phiếu" value={uni} onChange={setUni} options={[{ value: "vn30", label: "VN30" }, { value: "vn100", label: "VN100" }, { value: "hose", label: "HOSE" }, { value: "hnx", label: "HNX" }]} />
        <Seg label="Diện tích theo" value={size} onChange={setSize} options={[{ value: "marketcap", label: "Vốn hoá" }, { value: "value", label: "GTGD" }]} />
      </div>
      {st || (
        <>
          <HeatmapVN data={q.data} height={height} />
          <div className="text-[11.5px] text-faint">Màu = % thay đổi so với giá tham chiếu · ngành tô theo bình quân gia quyền · số % in trong ô · dữ liệu cuối ngày {q.data.as_of}.</div>
        </>
      )}
    </div>
  );
}

/** group/period chỉ dùng khi compact (widget); ở chế độ đầy đủ người dùng chọn và giá trị được nhớ. */
export function HeatmapView({ group: groupProp, period: periodProp, compact = false, height = 480 }) {
  const [gl, setGl] = useLocal("intel.hm.group", groupProp || "crypto");
  const [pl, setPl] = useLocal("intel.hm.period", periodProp || "1d");
  const [vl, setVl] = useLocal("intel.hm.view", "map");
  const [bl, setBl] = useLocal("intel.hm.bygroup", false);
  const [vs, setVs] = useState("map");
  const group = compact ? groupProp || "crypto" : gl;
  const period = compact ? periodProp || "1d" : pl;
  const view = compact ? vs : vl;
  const isVn = group === "vn";
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {!compact && <Seg label="Nhóm tài sản" value={group} onChange={setGl} options={HEAT_GROUPS} />}
        {!isVn && !compact && <Seg label="Kỳ" value={period} onChange={setPl} options={PERIODS} />}
        {!isVn && <Seg label="Kiểu hiển thị" value={view} onChange={compact ? setVs : setVl} options={VIEWS} />}
        {!isVn && !compact && view === "map" && (
          <label className="flex items-center gap-1.5 text-[12px] text-muted cursor-pointer">
            <input type="checkbox" checked={!!bl} onChange={(e) => setBl(e.target.checked)} style={{ accentColor: "var(--accent)" }} /> Nhóm theo phân loại
          </label>
        )}
      </div>
      {isVn ? <VnPart height={height} compact={compact} /> : <IntelPart group={group} period={period} view={view} compact={compact} height={height} byGroup={!compact && !!bl} />}
    </div>
  );
}

export default HeatmapView;
