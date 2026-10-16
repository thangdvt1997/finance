// Movers & biến động: tăng/giảm mạnh, biến động bất thường, biên độ, khối lượng đột biến, gần đỉnh/đáy 52 tuần, gap.
// Số liệu thống kê từ nến ngày (1h/4h chỉ cho mã có nến giờ), không phải khuyến nghị.
import { useMemo, useState } from "react";
import { Chip, Seg, Sparkline, cn } from "../ui";
import { ASSET_GROUPS, chartHref, fpct, fprice, useMovers } from "../../lib/intel";
import { AsOf, Pct, QState, SymLink, useLocal } from "./bits";

export const MOVER_KINDS = [
  { k: "gainers", label: "Tăng mạnh", head: null, bar: "sign" },
  { k: "losers", label: "Giảm mạnh", head: null, bar: "sign" },
  { k: "volatile", label: "Biến động bất thường", head: "Z-score", get: (r) => r.z, fmt: (v) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}σ`), bar: "sign" },
  { k: "range", label: "Biên độ trong ngày", head: "Biên độ", get: (r) => r.range_pct, fmt: (v) => (v == null ? "—" : `${v.toFixed(2)}%`), bar: "accent" },
  { k: "volume", label: "Khối lượng đột biến", head: "KL / TB20", get: (r) => r.vol_ratio, fmt: (v) => (v == null ? "—" : `${v.toFixed(2)}×`), bar: "accent" },
  { k: "near_high", label: "Gần đỉnh 52 tuần", head: "Cách đỉnh", get: (r) => r.from_high, fmt: fpct, bar: "accent" },
  { k: "near_low", label: "Gần đáy 52 tuần", head: "Trên đáy", get: (r) => r.from_low, fmt: fpct, bar: "accent" },
  { k: "gaps", label: "Gap mở cửa", head: "Gap", get: (r) => r.gap, fmt: fpct, bar: "sign" },
];
const KIND_BY = Object.fromEntries(MOVER_KINDS.map((x) => [x.k, x]));
const OVERVIEW = ["gainers", "losers", "volatile", "volume"];
const PERIODS = [{ value: "1h", label: "1H" }, { value: "4h", label: "4H" }, { value: "1d", label: "1D" }, { value: "1w", label: "1W" }, { value: "1m", label: "1M" }];
const GROUPS = [{ value: "all", label: "Tất cả nhóm" }, ...ASSET_GROUPS];
const openChart = (sym) => { window.location.hash = chartHref(sym); };

function Bar({ v, max, mode }) {
  if (v == null || !max) return <div className="in-bar" aria-hidden="true" />;
  const w = Math.min(100, (Math.abs(v) / max) * 100);
  const col = mode === "accent" ? "var(--accent)" : v >= 0 ? "var(--up)" : "var(--down)";
  return (
    <div className="in-bar" aria-hidden="true" style={{ minWidth: 56 }}>
      <i style={{ left: 0, width: `${w}%`, background: col, opacity: 0.75 }} />
    </div>
  );
}

export function MoverTable({ rows, kind, compact, showSpark, showName }) {
  const def = KIND_BY[kind] || KIND_BY.gainers;
  const metric = (r) => (def.get ? def.get(r) : r.change_pct);
  const max = useMemo(() => Math.max(0, ...rows.map((r) => Math.abs(metric(r) ?? 0))), [rows, kind]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="overflow-x-auto">
      <table className="tbl" aria-label={def.label}>
        <thead>
          <tr>
            <th className="r" style={{ width: 28 }}>#</th>
            <th>Mã</th>
            {showName && <th>Tên</th>}
            <th className="r">%</th>
            {!compact && <th className="r">Giá</th>}
            {def.head && <th className="r">{def.head}</th>}
            <th style={{ width: compact ? 64 : 110 }}><span className="sr-only">Độ lớn</span></th>
            {showSpark && <th className="r">Xu hướng</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.symbol} className="cursor-pointer" tabIndex={0} onClick={() => openChart(r.symbol)} onKeyDown={(e) => { if (e.key === "Enter") openChart(r.symbol); }}>
              <td className="r num text-faint">{i + 1}</td>
              <td><SymLink symbol={r.symbol} label={r.label} /></td>
              {showName && <td className="text-muted max-w-[16rem] truncate" title={r.name}>{r.name}</td>}
              <td className="r"><Pct v={r.change_pct} /></td>
              {!compact && <td className="r num">{fprice(r.last)}</td>}
              {def.head && <td className="r num">{def.fmt(metric(r))}</td>}
              <td><Bar v={metric(r)} max={max} mode={def.bar} /></td>
              {showSpark && <td className="r"><span className="inline-block align-middle"><Sparkline values={r.spark} width={72} height={22} /></span></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Coverage({ d }) {
  const part = d.covered != null && d.universe != null && d.covered < d.universe;
  return (
    <>
      {d.covered != null && <Chip tone={part ? "accent" : undefined} title="Số mã có đủ dữ liệu cho kỳ này trên tổng số mã theo dõi">phủ {d.covered}/{d.universe} mã</Chip>}
      <Chip tone="up" title="Số mã đang ở đỉnh 52 tuần">Mới đỉnh 52T: {d.new_high ?? 0}</Chip>
      <Chip tone="down" title="Số mã đang ở đáy 52 tuần">Mới đáy 52T: {d.new_low ?? 0}</Chip>
    </>
  );
}

/** group/period/kind/rows: dùng cho widget (compact). Ở chế độ đầy đủ người dùng tự chọn, giá trị được nhớ. */
export function MoversView({ group: groupProp, period: periodProp, kind: kindProp, rows = 15, compact = false, pollMs }) {
  const [gl, setGl] = useLocal("intel.mv.group", "all");
  const [pl, setPl] = useLocal("intel.mv.period", "1d");
  const [kl, setKl] = useLocal("intel.mv.kind", "gainers");
  const [ml, setMl] = useLocal("intel.mv.mode", "tab");
  const [ks, setKs] = useState(kindProp || "gainers");
  const group = compact ? groupProp || "all" : gl;
  const period = compact ? periodProp || "1d" : pl;
  const kind = compact ? (KIND_BY[kindProp] ? kindProp : ks) : (KIND_BY[kl] ? kl : "gainers");
  const mode = compact ? "tab" : ml;
  const n = Math.max(3, Math.min(30, Number(rows) || 15));
  const q = useMovers(group, period, mode === "overview" ? 8 : n, pollMs);
  const st = QState({ q, compact, rows: 6, isEmpty: (x) => !x || !x.count, empty: "Chưa có dữ liệu cho bộ lọc này.", hint: period === "1h" || period === "4h" ? "Kỳ 1h/4h chỉ có cho mã có nến giờ; thử kỳ 1D hoặc nhóm khác." : "Thử nhóm khác." });
  const d = q.data;
  const setKind = compact ? setKs : setKl;
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {!compact && (
          <select className="field" aria-label="Nhóm tài sản" value={group} onChange={(e) => setGl(e.target.value)} style={{ width: "auto" }}>
            {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        )}
        {!compact && <Seg label="Kỳ" value={period} onChange={setPl} options={PERIODS} />}
        {!compact && <Seg label="Chế độ" value={mode} onChange={setMl} options={[{ value: "tab", label: "Chi tiết" }, { value: "overview", label: "Tổng quan 4 cột" }]} />}
        {compact && !kindProp && (
          <select className="field" aria-label="Loại" value={kind} onChange={(e) => setKs(e.target.value)} style={{ width: "auto" }}>
            {MOVER_KINDS.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
          </select>
        )}
      </div>
      {mode === "tab" && !compact && <Seg label="Loại biến động" value={kind} onChange={setKind} options={MOVER_KINDS.map((x) => ({ value: x.k, label: x.label }))} />}
      {st || (
        <div className={cn("grid gap-2", q.isPlaceholderData && "opacity-70")}>
          <div className="flex flex-wrap items-center gap-2">
            <Coverage d={d} />
            <AsOf ts={d.as_of} label="Dữ liệu đến" className="ml-auto" />
          </div>
          {mode === "overview" && !compact ? (
            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 xl:grid-cols-4">
              {OVERVIEW.map((k) => (
                <section key={k} className="min-w-0" aria-label={KIND_BY[k].label}>
                  <h3 className="m-0 mb-1 text-[12.5px] font-semibold">{KIND_BY[k].label}</h3>
                  <MoverTable rows={(d[k] || []).slice(0, 8)} kind={k} compact />
                </section>
              ))}
            </div>
          ) : (
            <>
              {(d[kind] || []).length === 0
                ? <div className="text-muted text-[12.5px] p-2">Không có mã nào thoả điều kiện “{KIND_BY[kind].label}”.</div>
                : <MoverTable rows={(d[kind] || []).slice(0, n)} kind={kind} compact={compact} showName={!compact} showSpark={!compact} />}
            </>
          )}
          {d.note && <div className="text-[11.5px] text-faint">{d.note}</div>}
        </div>
      )}
    </div>
  );
}

export default MoversView;
