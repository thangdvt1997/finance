// Xếp hạng biến động & rủi ro theo mã: ATR%, phân vị, độ biến động thực hiện, khoảng cách SMA, beta so với chỉ số tham chiếu.
// Thống kê lịch sử từ nến ngày, không phải khuyến nghị.
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ExternalLink } from "lucide-react";
import { Seg, cn } from "../ui";
import { ASSET_GROUPS, chartHref, fnum, useIntelStats } from "../../lib/intel";
import { HeatCell, QState, VirtualList, useLocal } from "./bits";

const BENCH = [
  { value: "US:SPY", label: "SPY" },
  { value: "US:QQQ", label: "QQQ" },
  { value: "CRYPTO:BTCUSDT", label: "BTC" },
  { value: "EURUSD", label: "EURUSD" },
  { value: "XAUUSD", label: "Vàng" },
];
const GROUP_OPTS = [{ value: "all", label: "Tất cả" }, ...ASSET_GROUPS];

const COLS = [
  { id: "symbol", label: "Mã", w: "minmax(120px,1.6fr)", get: (r) => r.label || r.symbol, text: true },
  { id: "atr_pct", label: "ATR% (14)", w: "78px", get: (r) => r.atr_pct, tip: "Biên độ dao động thực trung bình 14 phiên, tính theo % giá" },
  { id: "atr_rank", label: "Phân vị ATR 1 năm", w: "130px", get: (r) => r.atr_rank, tip: "ATR hiện tại nằm ở phân vị nào trong 1 năm gần nhất (0 = thấp nhất, 100 = cao nhất)" },
  { id: "vol20", label: "Biến động 20p", w: "86px", get: (r) => r.vol20, tip: "Độ lệch chuẩn lợi suất 20 phiên, quy đổi năm (%)" },
  { id: "vol_rank", label: "Phân vị vol", w: "120px", get: (r) => r.vol_rank, tip: "Biến động thực hiện hiện tại so với lịch sử 1 năm" },
  { id: "sma20_dist", label: "SMA20", w: "70px", get: (r) => r.sma20_dist, tip: "Khoảng cách giá so với trung bình động 20 phiên" },
  { id: "sma50_dist", label: "SMA50", w: "70px", get: (r) => r.sma50_dist },
  { id: "sma200_dist", label: "SMA200", w: "74px", get: (r) => r.sma200_dist },
  { id: "beta", label: "Beta", w: "62px", get: (r) => r.beta, tip: "Độ nhạy so với chỉ số tham chiếu: 1 = đi cùng biên độ, >1 = dao động mạnh hơn" },
  { id: "corr_bench", label: "Tương quan", w: "78px", get: (r) => r.corr_bench, tip: "Tương quan với chỉ số tham chiếu (−1…+1)" },
];
const COMPACT_IDS = new Set(["symbol", "atr_pct", "vol20", "sma50_dist", "beta"]);

function Rank({ v }) {
  if (v == null) return <span className="text-faint">—</span>;
  const hot = v >= 80, cold = v <= 20;
  return (
    <div className="flex items-center gap-2" title={`Phân vị ${Math.round(v)}/100`}>
      <div className="in-bar flex-1" aria-hidden="true"><i style={{ left: 0, width: `${Math.max(2, Math.min(100, v))}%`, background: hot ? "var(--down)" : cold ? "var(--info, #5aa9ff)" : "var(--accent)", opacity: 0.8 }} /></div>
      <span className="num w-[26px] text-right text-[12px]">{Math.round(v)}</span>
    </div>
  );
}

export function VolatilityRankView({ group: groupProp, benchmark: benchProp, compact = false, onSelect, selected, height }) {
  const [savedGroup, setSavedGroup] = useLocal("intel.vol.group", "all");
  const [savedBench, setSavedBench] = useLocal("intel.vol.bench", "US:SPY");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ id: "atr_rank", desc: true });
  const group = groupProp ?? savedGroup;
  const bench = benchProp ?? savedBench;
  const q = useIntelStats(group, bench, 60);
  const cols = useMemo(() => (compact ? COLS.filter((c) => COMPACT_IDS.has(c.id)) : COLS), [compact]);

  const rows = useMemo(() => {
    const t = search.trim().toLowerCase();
    let list = (q.data?.items || []).filter((r) => !t || r.symbol.toLowerCase().includes(t) || (r.name || "").toLowerCase().includes(t) || (r.label || "").toLowerCase().includes(t));
    const col = COLS.find((c) => c.id === sort.id) || COLS[2];
    list = [...list].sort((a, b) => {
      const x = col.get(a), y = col.get(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1; // thiếu dữ liệu luôn xuống cuối
      if (y == null) return -1;
      const c = col.text ? String(x).localeCompare(String(y)) : x - y;
      return sort.desc ? -c : c;
    });
    return list;
  }, [q.data, search, sort]);

  const template = cols.map((c) => c.w).join(" ");
  const minW = compact ? 460 : 960;
  const go = (r) => { if (onSelect) onSelect(r.symbol); else window.location.hash = chartHref(r.symbol).slice(1); };
  const toggle = (id) => setSort((s) => (s.id === id ? { id, desc: !s.desc } : { id, desc: id !== "symbol" }));
  const benchLabel = BENCH.find((b) => b.value === bench)?.label || bench.replace(/^[A-Za-z]+:/, "");

  const rowCells = (r) => cols.map((c) => {
    switch (c.id) {
      case "symbol":
        return (
          <div key={c.id} className="min-w-0 flex items-center gap-1">
            <div className="min-w-0">
              <div className="font-semibold truncate">{r.label || r.symbol}</div>
              {!compact && <div className="text-[10.5px] text-faint truncate">{r.name}</div>}
            </div>
            <a href={chartHref(r.symbol)} onClick={(e) => e.stopPropagation()} className="text-faint hover:text-accent shrink-0" aria-label={`Mở biểu đồ ${r.label || r.symbol}`}><ExternalLink size={12} aria-hidden="true" /></a>
          </div>
        );
      case "atr_pct": return <span key={c.id} className="num text-right">{r.atr_pct == null ? "—" : `${fnum(r.atr_pct, 2)}%`}</span>;
      case "atr_rank": return <Rank key={c.id} v={r.atr_rank} />;
      case "vol20": return <span key={c.id} className="num text-right">{r.vol20 == null ? "—" : `${fnum(r.vol20, 1)}%`}</span>;
      case "vol_rank": return <Rank key={c.id} v={r.vol_rank} />;
      case "sma20_dist": case "sma50_dist": case "sma200_dist":
        return <HeatCell key={c.id} v={r[c.id]} cap={c.id === "sma200_dist" ? 12 : c.id === "sma50_dist" ? 8 : 4} dp={1} />;
      case "beta": return <span key={c.id} className={cn("num text-right", r.beta != null && r.beta < 0 && "down")} title={r.beta_n ? `${r.beta_n} quan sát` : undefined}>{r.beta == null ? "—" : fnum(r.beta, 2)}</span>;
      case "corr_bench": return <span key={c.id} className="num text-right">{r.corr_bench == null ? "—" : (r.corr_bench < 0 ? "−" : "") + Math.abs(r.corr_bench).toFixed(2)}</span>;
      default: return null;
    }
  });

  const renderRow = (r) => (
    <div role="row" tabIndex={0} aria-selected={selected === r.symbol}
      className={cn("grid items-center gap-2 px-2 h-full border-b border-line text-[12.5px] cursor-pointer hover:bg-panel2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent", selected === r.symbol && "bg-accent-bg")}
      style={{ gridTemplateColumns: template }} onClick={() => go(r)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(r); } }}>
      {rowCells(r).map((el, i) => <div key={i} role="cell" className="contents">{el}</div>)}
    </div>
  );

  const virtual = rows.length > 150;
  const bodyH = height ?? (compact ? 320 : 520);

  return (
    <div className={cn("grid gap-3", compact && "tm-pad")}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="vol-search">Tìm mã</label>
        <input id="vol-search" type="search" className="field w-[150px]" placeholder="Tìm mã…" value={search} onChange={(e) => setSearch(e.target.value)} />
        {!groupProp && (
          <>
            <label className="sr-only" htmlFor="vol-group">Nhóm tài sản</label>
            <select id="vol-group" className="field" value={group} onChange={(e) => setSavedGroup(e.target.value)}>
              {GROUP_OPTS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
            </select>
          </>
        )}
        {!benchProp && !compact && (
          <div className="flex items-center gap-1.5">
            <span className="text-[11.5px] text-muted">Beta so với</span>
            <Seg value={bench} onChange={setSavedBench} options={BENCH} label="Chỉ số tham chiếu cho beta" />
          </div>
        )}
        <span className="ml-auto text-[11.5px] text-faint num">{rows.length} mã</span>
      </div>
      <QState q={q} empty="Chưa có thống kê biến động cho nhóm này." rows={6} compact={compact} isEmpty={(d) => !d?.items?.length} />
      {q.data?.items?.length > 0 && (
        <div className="scroll-x">
          <div role="table" aria-label={`Xếp hạng biến động, beta so với ${benchLabel}`} style={{ minWidth: minW }} className="flex flex-col">
            <div role="row" className="grid items-end gap-2 px-2 py-1.5 border-b border-line text-[11px] text-muted font-semibold" style={{ gridTemplateColumns: template }}>
              {cols.map((c) => {
                const on = sort.id === c.id;
                return (
                  <div key={c.id} role="columnheader" aria-sort={on ? (sort.desc ? "descending" : "ascending") : "none"} className={cn(!c.text && c.id !== "atr_rank" && c.id !== "vol_rank" && "text-right")} title={c.tip}>
                    <button type="button" onClick={() => toggle(c.id)} className="bg-transparent border-0 p-0 cursor-pointer text-inherit font-[inherit] inline-flex items-center gap-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                      {c.id === "beta" ? `Beta (${benchLabel})` : c.id === "corr_bench" ? `Tương quan (${benchLabel})` : c.label}
                      {on && (sort.desc ? <ArrowDown size={11} aria-hidden="true" /> : <ArrowUp size={11} aria-hidden="true" />)}
                    </button>
                  </div>
                );
              })}
            </div>
            {virtual ? (
              <div className="flex flex-col" style={{ height: bodyH }}>
                <VirtualList count={rows.length} rowHeight={34} role="rowgroup" itemRole="row" ariaLabel="Danh sách mã" render={(i) => renderRow(rows[i])} />
              </div>
            ) : (
              <div role="rowgroup" className="overflow-y-auto" style={{ maxHeight: bodyH }}>
                {rows.map((r) => <div key={r.symbol} style={{ height: compact ? 34 : 40 }}>{renderRow(r)}</div>)}
                {rows.length === 0 && <div className="p-3 text-[12.5px] text-muted">Không có mã khớp “{search}”.</div>}
              </div>
            )}
          </div>
        </div>
      )}
      {!compact && (
        <p className="m-0 text-[11.5px] text-faint max-w-[90ch]">
          ATR% và độ biến động thực hiện đo mức dao động quá khứ; phân vị cho biết hiện cao hay thấp so với 1 năm gần nhất. Beta/tương quan tính trên 60 phiên so với {benchLabel}. Ô SMA: dương = giá trên trung bình động.
          Thống kê lịch sử, tham khảo, không phải khuyến nghị. Bấm tiêu đề cột để sắp xếp{onSelect ? ", bấm hàng để xem phân phối lợi suất" : ", bấm hàng để mở biểu đồ"}.
        </p>
      )}
    </div>
  );
}

export default VolatilityRankView;
