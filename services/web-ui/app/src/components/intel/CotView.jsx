// Vị thế đầu cơ lớn (báo cáo hàng tuần) + đồng thuận chuyên gia. Thống kê dữ liệu công khai, tham khảo, không phải khuyến nghị.
// Không hiển thị tên nguồn dữ liệu trong chữ giao diện.
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Info, Minus } from "lucide-react";
import { EChart, css } from "../charts";
import { Async, Chip, Seg, Sparkline, cn } from "../ui";
import { fcompact, useCot } from "../../lib/intel";
import { CLASS_LABEL, classOf } from "../../lib/assetClass";
import { consensus, useExperts, usePositions, useSignals } from "../../lib/queries";
import { symbolLabel } from "../../lib/format";
import { QState, SymLink } from "./bits";

const sgn = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fcompact(v)}`);
const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const isQa = (s) => /^qa/i.test(String(s || "")) || /(^|[:_-])qa[-_]/i.test(String(s || ""));

function Delta({ v }) {
  if (v == null) return <span className="text-faint">—</span>;
  const Ic = v > 0 ? ArrowUp : v < 0 ? ArrowDown : Minus;
  return <span className={cn("inline-flex items-center gap-0.5 num", tone(v))}><Ic size={12} aria-hidden="true" />{sgn(v)}</span>;
}

function Pctl({ it, compact }) {
  if (it.percentile == null)
    return <div className="text-[11px] text-faint">Đủ ≥8 tuần mới có phân vị (hiện {it.n ?? 0} tuần)</div>;
  const p = it.percentile;
  return (
    <div className="grid gap-0.5" title={`Vị thế ròng hiện tại cao hơn ${Math.round(p)}% các tuần trong lịch sử (${it.n} tuần)`}>
      <div className="in-bar" aria-hidden="true">
        <i style={{ left: 0, width: `${Math.max(2, p)}%`, background: p >= 80 ? "var(--up)" : p <= 20 ? "var(--down)" : "var(--accent)", opacity: 0.8 }} />
      </div>
      <div className="flex justify-between text-[11px] text-muted"><span>Phân vị lịch sử{compact ? "" : ` (${it.n} tuần)`}</span><span className="num text-fg">{Math.round(p)}</span></div>
    </div>
  );
}

function DetailChart({ it, height = 240 }) {
  const pts = useMemo(() => (it.series || []).map((s) => [s.d, s.net]), [it]);
  const build = () => {
    const fg = css("--fg"), muted = css("--muted"), line = css("--line2"), panel = css("--panel"), acc = css("--accent") || "#f0b84f";
    return {
      animation: false,
      grid: { left: 8, right: 14, top: 14, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", confine: true, backgroundColor: panel, borderColor: line, textStyle: { color: fg, fontSize: 12 }, valueFormatter: (v) => sgn(v) },
      xAxis: { type: "time", axisLabel: { color: muted, fontSize: 11 }, axisLine: { lineStyle: { color: line } }, splitLine: { show: false } },
      yAxis: { type: "value", scale: true, axisLabel: { color: muted, fontSize: 11, formatter: (v) => fcompact(v) }, splitLine: { lineStyle: { color: line, opacity: 0.5 } } },
      series: [{
        type: "line", data: pts, showSymbol: false, step: false, lineStyle: { width: 1.8, color: acc }, areaStyle: { color: acc, opacity: 0.07 },
        markLine: {
          silent: true, symbol: "none", animation: false,
          data: [
            { yAxis: 0, lineStyle: { color: fg, width: 1, type: "solid", opacity: 0.6 }, label: { show: false } },
            { yAxis: it.max, lineStyle: { color: muted, type: "dashed", width: 1 }, label: { formatter: "Cao nhất " + sgn(it.max), color: muted, fontSize: 10, position: "insideStartTop" } },
            { yAxis: it.min, lineStyle: { color: muted, type: "dashed", width: 1 }, label: { formatter: "Thấp nhất " + sgn(it.min), color: muted, fontSize: 10, position: "insideStartBottom" } },
          ],
        },
      }],
    };
  };
  return (
    <div className="flex flex-col" style={{ minHeight: height }}>
      <EChart build={build} deps={[pts, it.min, it.max]} height={height} label={`Biểu đồ vị thế ròng theo tuần của ${it.label || it.symbol}`} />
    </div>
  );
}

function Detail({ it }) {
  return (
    <div className="rounded-md border border-line bg-panel2 p-3 grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 text-[13px] font-semibold">{it.label || it.symbol} · Hợp đồng tương lai {it.contract}</h3>
        <span className="text-[11.5px] text-faint num">{it.n} tuần · tới {it.as_of}</span>
        <span className="ml-auto text-[12px]"><SymLink symbol={it.symbol} label="Mở biểu đồ giá" /></span>
      </div>
      <DetailChart it={it} />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px]">
        <div><div className="text-muted text-[11px]">Hiện tại</div><div className={cn("num text-[15px]", tone(it.net))}>{sgn(it.net)}</div></div>
        <div><div className="text-muted text-[11px]">Thay đổi tuần</div><div className="text-[15px]"><Delta v={it.change} /></div></div>
        <div><div className="text-muted text-[11px]">Thấp nhất lịch sử</div><div className="num text-[15px]">{sgn(it.min)}</div></div>
        <div><div className="text-muted text-[11px]">Cao nhất lịch sử</div><div className="num text-[15px]">{sgn(it.max)}</div></div>
      </div>
      {it.inverted && (
        <p className="m-0 flex gap-1.5 text-[12px] text-muted"><Info size={14} className="shrink-0 mt-[2px] text-accent" aria-hidden="true" />
          Cặp {it.label} có chiều ngược với hợp đồng {it.contract} (đồng đối ứng với USD). Số hiển thị là vị thế của hợp đồng {it.contract}: vị thế ròng mua {it.contract} tương ứng nghiêng bán {it.label}, và ngược lại.</p>
      )}
    </div>
  );
}

function Card({ it, active, onPick }) {
  const vals = useMemo(() => (it.series || []).slice(-104).map((s) => s.net), [it]);
  return (
    <button type="button" aria-pressed={active} onClick={() => onPick(it.symbol)}
      className={cn("text-left rounded-md border bg-panel2 p-2.5 grid gap-1.5 cursor-pointer text-fg font-[inherit] hover:border-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent", active ? "border-accent" : "border-line")}
      aria-label={`${it.label}, hợp đồng ${it.contract}, vị thế ròng ${sgn(it.net)}, thay đổi tuần ${sgn(it.change)}${it.percentile != null ? `, phân vị ${Math.round(it.percentile)}` : ""}`}>
      <div className="flex items-start gap-1.5 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">{it.label || it.symbol}</div>
          <div className="text-[11px] text-faint truncate" title={`Hợp đồng tương lai ${it.contract}`}>Hợp đồng tương lai {it.contract}</div>
        </div>
        {it.inverted && <Chip tone="accent" title="Cặp có chiều ngược với hợp đồng">Đảo chiều</Chip>}
      </div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className={cn("num text-[19px] leading-none", tone(it.net))}>{sgn(it.net)}</div>
          <div className="text-[11.5px] mt-1 flex items-center gap-1 text-muted">Tuần <Delta v={it.change} /></div>
        </div>
        <Sparkline values={vals} width={84} height={30} up={it.net >= 0} />
      </div>
      <Pctl it={it} compact />
    </button>
  );
}

const TCOLS = [
  ["symbol", "Mã", (r) => r.label || r.symbol, true],
  ["contract", "Hợp đồng", (r) => r.contract, true],
  ["net", "Vị thế ròng", (r) => r.net],
  ["change", "Δ tuần", (r) => r.change],
  ["percentile", "Phân vị", (r) => r.percentile],
  ["n", "Số tuần", (r) => r.n],
  ["as_of", "Tính đến", (r) => r.as_of, true],
];

function CotTable({ items, active, onPick, compact }) {
  const [sort, setSort] = useState({ id: "percentile", desc: true });
  const list = useMemo(() => {
    const c = TCOLS.find((x) => x[0] === sort.id) || TCOLS[0];
    return [...items].sort((a, b) => {
      const x = c[2](a), y = c[2](b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const d = c[3] ? String(x).localeCompare(String(y)) : x - y;
      return sort.desc ? -d : d;
    });
  }, [items, sort]);
  const cols = compact ? TCOLS.filter((c) => ["symbol", "net", "change", "percentile"].includes(c[0])) : TCOLS;
  return (
    <div className="scroll-x">
      <table className="tbl" style={{ minWidth: compact ? 320 : 640 }} aria-label="Tóm tắt vị thế đầu cơ lớn">
        <thead>
          <tr>
            {cols.map(([id, l, , text]) => (
              <th key={id} className={cn(!text && "r")} aria-sort={sort.id === id ? (sort.desc ? "descending" : "ascending") : "none"}>
                <button type="button" onClick={() => setSort((s) => (s.id === id ? { id, desc: !s.desc } : { id, desc: !text }))}>
                  {l}{sort.id === id ? (sort.desc ? <ArrowDown size={11} aria-hidden="true" /> : <ArrowUp size={11} aria-hidden="true" />) : <ArrowUpDown size={10} className="opacity-40" aria-hidden="true" />}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((r) => (
            <tr key={r.symbol} onClick={() => onPick(r.symbol)} tabIndex={0} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onPick(r.symbol); } }} className={cn("cursor-pointer", active === r.symbol && "bg-accent-bg")} aria-selected={active === r.symbol}>
              {cols.map(([id]) => {
                switch (id) {
                  case "symbol": return <td key={id}><b>{r.label || r.symbol}</b>{r.inverted && <span className="ml-1 text-[10.5px] text-accent" title="Cặp có chiều ngược với hợp đồng">⇄</span>}</td>;
                  case "contract": return <td key={id} className="text-muted">{r.contract}</td>;
                  case "net": return <td key={id} className={cn("r num", tone(r.net))}>{sgn(r.net)}</td>;
                  case "change": return <td key={id} className="r"><Delta v={r.change} /></td>;
                  case "percentile": return <td key={id} className="r num">{r.percentile == null ? <span className="text-faint" title="Cần ≥8 tuần dữ liệu">—</span> : Math.round(r.percentile)}</td>;
                  case "n": return <td key={id} className="r num text-muted">{r.n}</td>;
                  default: return <td key={id} className="num text-muted whitespace-nowrap">{r.as_of}</td>;
                }
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Consensus({ compact, symbols }) {
  const ex = useExperts();
  const s = useSignals({ status: "open" });
  const p = usePositions({});
  const [grp, setGrp] = useState("all");
  const experts = useMemo(() => (ex.data?.items || []).filter((e) => !isQa(e.expert_id)), [ex.data]);
  const rows = useMemo(() => {
    const sig = (s.data?.items || []).filter((x) => !isQa(x.expert_id) && !isQa(x.symbol));
    const pos = (p.data?.items || []).filter((x) => !isQa(x.expert_id) && !isQa(x.symbol));
    return consensus(sig, pos, experts).filter((r) => !isQa(r.symbol));
  }, [s.data, p.data, experts]);
  const q = { isPending: s.isPending || p.isPending, isError: s.isError || p.isError, error: s.error || p.error, refetch: () => { s.refetch(); p.refetch(); }, data: rows };
  const present = useMemo(() => [...new Set(rows.map((r) => classOf({ symbol: r.symbol })))], [rows]);
  const base = symbols?.length ? rows.filter((r) => symbols.includes(r.symbol)) : rows;
  const shown = (grp === "all" ? base : base.filter((r) => classOf({ symbol: r.symbol }) === grp)).slice(0, compact ? 12 : 60);
  return (
    <section className="grid gap-2" aria-label="Đồng thuận chuyên gia">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 text-[13px] font-semibold">Đồng thuận chuyên gia <Chip>tham khảo</Chip></h3>
        {!compact && present.length > 1 && (
          <Seg value={grp} onChange={setGrp} label="Lọc theo nhóm tài sản" options={[{ value: "all", label: "Tất cả" }, ...present.map((c) => ({ value: c, label: CLASS_LABEL[c] || c }))]} />
        )}
      </div>
      <Async q={q} empty="Chưa đủ dữ liệu để tính đồng thuận." hint="Cần ít nhất một tín hiệu đang mở hoặc vị thế công khai." rows={3}>
        {() => (
          <div className="scroll-x">
            <table className="tbl" style={{ minWidth: compact ? 360 : 560 }} aria-label="Đồng thuận chuyên gia theo mã">
              <thead><tr><th>Mã</th><th className="r">Mua</th><th className="r">Bán</th><th>Nghiêng (−1…+1)</th>{!compact && <th className="r" title="Số vị thế ròng dương − âm trong các chuyên gia/tổ chức công khai">Vị thế ròng</th>}</tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.symbol}>
                    <td><b>{symbolLabel(r.symbol)}</b></td>
                    <td className="r num up">{r.buy}</td>
                    <td className="r num down">{r.sell}</td>
                    <td style={{ minWidth: 150 }}>
                      <div className="flex items-center gap-2">
                        <div className="relative h-[8px] rounded bg-line flex-1" role="img" aria-label={`Điểm nghiêng ${(r.score * 100).toFixed(0)} phần trăm, ${r.score > 0 ? "nghiêng mua" : r.score < 0 ? "nghiêng bán" : "trung tính"}`}>
                          <div className="absolute inset-y-0 left-1/2 w-px bg-line2" />
                          <div className="absolute inset-y-0 rounded" style={{ background: r.score >= 0 ? "var(--up)" : "var(--down)", left: r.score >= 0 ? "50%" : `${50 + r.score * 50}%`, width: `${Math.abs(r.score) * 50}%` }} />
                        </div>
                        <span className={cn("num w-[40px] text-right text-[12px]", tone(r.score))}>{r.score > 0 ? "+" : r.score < 0 ? "−" : ""}{Math.abs(r.score).toFixed(2)}</span>
                      </div>
                    </td>
                    {!compact && <td className={cn("r num", r.posNet > 0 ? "up" : r.posNet < 0 ? "down" : "text-muted")}>{r.posN ? (r.posNet > 0 ? "+" : "") + r.posNet : "—"}</td>}
                  </tr>
                ))}
                {shown.length === 0 && <tr><td colSpan={5} className="text-muted">Không có mã nào trong nhóm này.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </Async>
      {!compact && <p className="m-0 text-[11.5px] text-faint max-w-[90ch]">Điểm nghiêng = (tổng trọng số mua − bán) / tổng, trọng số là điểm uy tín của từng chuyên gia. Chỉ là thống kê dữ liệu công khai của chuyên gia, không phải khuyến nghị đầu tư.</p>}
    </section>
  );
}

/** view: "cards" | "table" (nếu truyền vào thì không hiện nút chuyển). symbols: lọc theo mã. showConsensus: mặc định = !compact. */
export function PositioningView({ compact = false, view: viewProp, symbols, showConsensus }) {
  const q = useCot();
  const [viewLocal, setViewLocal] = useState("cards");
  const [grp, setGrp] = useState("all");
  const [sel, setSel] = useState(null);
  const view = viewProp || viewLocal;
  const items = useMemo(() => {
    let l = (q.data?.items || []).filter((i) => !isQa(i.symbol));
    if (symbols?.length) l = l.filter((i) => symbols.includes(i.symbol));
    return l;
  }, [q.data, symbols]);
  const present = useMemo(() => [...new Set(items.map((i) => classOf(i)))], [items]);
  const filtered = grp === "all" ? items : items.filter((i) => classOf(i) === grp);
  const active = filtered.find((i) => i.symbol === sel) || null;
  const pick = (s) => setSel((c) => (c === s ? null : s));
  const withConsensus = showConsensus ?? !compact;

  return (
    <div className={cn("grid gap-4", compact && "tm-pad")}>
      <section className="grid gap-3" aria-label="Vị thế đầu cơ lớn">
        <div className="flex flex-wrap items-center gap-2">
          {!compact && <h3 className="m-0 text-[13px] font-semibold">Vị thế đầu cơ lớn (báo cáo hàng tuần)</h3>}
          {!viewProp && <Seg value={view} onChange={setViewLocal} label="Kiểu hiển thị" options={[{ value: "cards", label: "Thẻ" }, { value: "table", label: "Bảng" }]} />}
          {!compact && present.length > 1 && (
            <Seg value={grp} onChange={setGrp} label="Lọc theo nhóm tài sản" options={[{ value: "all", label: "Tất cả" }, ...present.map((c) => ({ value: c, label: CLASS_LABEL[c] || c }))]} />
          )}
          {q.data?.items?.length > 0 && <span className="ml-auto text-[11.5px] text-faint num">{filtered.length} mã{q.data.weeks_max ? ` · tối đa ${q.data.weeks_max} tuần` : ""}</span>}
        </div>
        <QState q={q} empty="Chưa có dữ liệu vị thế hàng tuần." hint="Dữ liệu được cập nhật mỗi tuần, đợi lần thu thập kế tiếp." rows={5} compact={compact} isEmpty={() => items.length === 0} />
        {q.data && items.length > 0 && (
          view === "table" ? (
            <CotTable items={filtered} active={sel} onPick={pick} compact={compact} />
          ) : (
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${compact ? 180 : 220}px, 1fr))` }}>
              {filtered.map((it) => <Card key={it.symbol} it={it} active={sel === it.symbol} onPick={pick} />)}
            </div>
          )
        )}
        {active && <Detail it={active} />}
        <p className="m-0 text-[11.5px] text-faint max-w-[90ch]">
          {q.data?.note || "Vị thế ròng nhóm đầu cơ lớn theo báo cáo hàng tuần; công bố trễ vài ngày."} Tham khảo, không phải tín hiệu giao dịch.
          {!compact && " Phân vị cho biết vị thế ròng hiện tại cao/thấp so với toàn bộ lịch sử đang có; bấm thẻ hoặc hàng để xem biểu đồ."}
        </p>
      </section>
      {withConsensus && <Consensus compact={compact} symbols={symbols} />}
    </div>
  );
}

export default PositioningView;
