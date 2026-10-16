import { useMemo, useState } from "react";
import { CalendarDays, Filter, Landmark, LineChart, Newspaper, Search } from "lucide-react";
import { Async, Chip, Disclaimer, Panel, Seg, Stat, cn } from "../ui";
import { DataTable } from "../table";
import { EChart, CandleChart, css } from "../charts";
import { Code, Note, Pct } from "./vnbits";
import { ETYPE, UNIVERSES, bil, n0, n1, n2, pc, tone, useVnEvents, useVnForeign, useVnNews, useVnScreener, useVnSymbol, useVnSymbols, vnd, vol } from "../../lib/vn";
import { date as fdate, clean } from "../../lib/format";

/* ---------- Khối ngoại ---------- */
function NetChart({ rows }) {
  const byDay = useMemo(() => {
    const m = new Map();
    for (const r of rows) m.set(r.d, (m.get(r.d) || 0) + (r.net_val || 0));
    return [...m.entries()].sort();
  }, [rows]);
  const build = () => ({
    animation: false, grid: { left: 48, right: 8, top: 10, bottom: 22 },
    tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (p) => `${p[0].axisValue}<br/>Ròng: <b>${bil(p[0].value, true)}</b>` },
    xAxis: { type: "category", data: byDay.map(([d]) => d.slice(5)), axisLabel: { color: css("--muted"), fontSize: 10 }, axisTick: { show: false }, axisLine: { lineStyle: { color: css("--line2") } } },
    yAxis: { type: "value", axisLabel: { color: css("--muted"), fontSize: 10, formatter: (v) => `${Math.round(v / 1e9)}` }, splitLine: { lineStyle: { color: css("--line") } }, name: "tỷ", nameTextStyle: { color: css("--muted"), fontSize: 10 } },
    series: [{ type: "bar", barMaxWidth: 14, data: byDay.map(([, v]) => ({ value: v, itemStyle: { color: v >= 0 ? css("--up") : css("--down"), borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] } })) }],
  });
  return <EChart build={build} deps={[byDay]} height={190} label="Khối ngoại mua/bán ròng theo ngày (tỷ đồng)" />;
}

const FTable = ({ rows, cum }) => (
  <DataTable data={rows || []} getRowId={(r) => r.code} minWidth={cum ? 260 : 420} empty="Chưa có dữ liệu."
    columns={[
      { id: "code", header: "Mã", accessorKey: "code", cell: (c) => <Code code={c.getValue()} name={c.row.original.name} /> },
      { id: "net", header: "Ròng", accessorKey: cum ? "net_val" : "f_net", meta: { align: "r" }, cell: (c) => <span className={cn("num", tone(c.getValue()))}>{bil(c.getValue(), true)}</span> },
      ...(cum ? [{ id: "days", header: "Phiên", accessorKey: "days", meta: { align: "r" }, cell: (c) => <span className="num text-muted">{c.getValue()}</span> }]
        : [{ id: "pct", header: "%", accessorKey: "pct", meta: { align: "r" }, cell: (c) => <Pct v={c.getValue()} /> },
          { id: "own", header: "NN sở hữu", accessorKey: "own_pct", meta: { align: "r" }, cell: (c) => <span className="num text-muted">{c.getValue() == null ? "—" : `${n1(c.getValue())}%`}</span> }]),
    ]} />
);

export function ForeignTab() {
  const [uni, setUni] = useState("all");
  const q = useVnForeign({ universe: uni, n: 15, cum_days: 5 });
  return (
    <div className="grid gap-3">
      <Disclaimer>Giao dịch <b>tự doanh</b> và giá <b>realtime trong phiên</b> chưa có. Khối ngoại dưới đây là số cuối ngày của sở.</Disclaimer>
      <Async q={q} rows={6}>
        {(d) => {
          const t = d.totals.ALL;
          return (
            <>
              <Panel title="Khối ngoại toàn thị trường" icon={Landmark} right={<select className="field" value={uni} onChange={(e) => setUni(e.target.value)} aria-label="Nhóm mã">{UNIVERSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  <Stat label="Mua" value={bil(t.buy)} /><Stat label="Bán" value={bil(t.sell)} />
                  <Stat label="Mua/bán ròng" value={bil(t.net, true)} tone={tone(t.net)} />
                  <Stat label="Theo sàn" value={Object.entries(d.totals).filter(([k]) => k !== "ALL").map(([k, v]) => `${k} ${bil(v.net, true)}`).join(" · ")} />
                </div>
                <NetChart rows={d.market_series || []} />
              </Panel>
              <div className="vn-2">
                <Panel title="Mua ròng nhiều nhất hôm nay" scroll bodyClass="max-h-[420px]"><FTable rows={d.top_buy} /></Panel>
                <Panel title="Bán ròng nhiều nhất hôm nay" scroll bodyClass="max-h-[420px]"><FTable rows={d.top_sell} /></Panel>
              </div>
              {d.cum && (
                <div className="vn-2">
                  <Panel title={`Mua ròng tích luỹ ${d.cum.days} phiên`} scroll bodyClass="max-h-[420px]"><FTable rows={d.cum.top_buy} cum /></Panel>
                  <Panel title={`Bán ròng tích luỹ ${d.cum.days} phiên`} scroll bodyClass="max-h-[420px]"><FTable rows={d.cum.top_sell} cum /></Panel>
                </div>
              )}
            </>
          );
        }}
      </Async>
    </div>
  );
}

/* ---------- Screener ---------- */
const FIELDS = [
  ["pe", "P/E", "tối đa", "max"], ["pb", "P/B", "tối đa", "max"], ["roe", "ROE ước tính (%)", "tối thiểu", "min"], ["div_yield", "Cổ tức/giá (%)", "tối thiểu", "min"],
  ["marketcap", "Vốn hoá (tỷ đ)", "tối thiểu", "min"], ["avg_value_20d", "GTGD TB 20 phiên (tỷ đ)", "tối thiểu", "min"], ["chg_1m", "Thay đổi 1 tháng (%)", "tối thiểu", "min"],
  ["rsi14", "RSI14", "tối thiểu", "min"],
];
const SCALE = { marketcap: 1e9, avg_value_20d: 1e9 };
const PRESETS = [
  { id: "value", label: "Giá trị", set: { pe_max: "12", pb_max: "2", roe_min: "12" } },
  { id: "div", label: "Cổ tức cao", set: { div_yield_min: "5", marketcap_min: "2000" } },
  { id: "mom", label: "Động lượng", set: { chg_1m_min: "5", rsi14_min: "55" } },
  { id: "liq", label: "Thanh khoản lớn", set: { avg_value_20d_min: "100" } },
  { id: "clear", label: "Xoá lọc", set: {} },
];
const SORTS = [["marketcap", "Vốn hoá"], ["pe", "P/E"], ["pb", "P/B"], ["roe", "ROE"], ["div_yield", "Cổ tức"], ["pct", "% hôm nay"], ["chg_1m", "% 1 tháng"], ["avg_value_20d", "GTGD TB"], ["rsi14", "RSI"]];

export function ScreenerTab() {
  const [f, setF] = useState({ universe: "vn100", sort: "marketcap", order: "desc", industry: "" });
  const [applied, setApplied] = useState(f);
  const params = useMemo(() => {
    const p = { universe: applied.universe, sort: applied.sort, order: applied.order, industry: applied.industry, limit: 100 };
    for (const [k] of FIELDS) {
      for (const side of ["min", "max"]) {
        const v = applied[`${k}_${side}`];
        if (v !== undefined && v !== "" && !Number.isNaN(Number(v))) p[`${k}_${side}`] = Number(v) * (SCALE[k] || 1);
      }
    }
    return p;
  }, [applied]);
  const q = useVnScreener(params);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const columns = [
    { id: "code", header: "Mã", accessorKey: "code", cell: (c) => <Code code={c.getValue()} name={c.row.original.name} /> },
    { id: "industry", header: "Ngành", accessorKey: "industry", cell: (c) => <span className="text-[12px] text-muted">{c.getValue()}</span> },
    { id: "price", header: "Giá", accessorKey: "price", meta: { align: "r" }, cell: (c) => <span className="num">{vnd(c.getValue())}</span> },
    { id: "pct", header: "%", accessorKey: "pct", meta: { align: "r" }, cell: (c) => <Pct v={c.getValue()} /> },
    { id: "marketcap", header: "Vốn hoá", accessorKey: "marketcap", meta: { align: "r" }, cell: (c) => <span className="num">{bil(c.getValue())}</span> },
    { id: "pe", header: "P/E", accessorKey: "pe", meta: { align: "r" }, cell: (c) => <span className="num">{n1(c.getValue())}</span> },
    { id: "pb", header: "P/B", accessorKey: "pb", meta: { align: "r" }, cell: (c) => <span className="num">{n2(c.getValue())}</span> },
    { id: "roe", header: "ROE*", accessorKey: "roe", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : `${n1(c.getValue())}%`}</span> },
    { id: "eps", header: "EPS*", accessorKey: "eps", meta: { align: "r" }, cell: (c) => <span className="num">{n0(c.getValue())}</span> },
    { id: "div", header: "Cổ tức", accessorKey: "div_yield", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : `${n1(c.getValue())}%`}</span> },
    { id: "chg_1m", header: "1T", accessorKey: "chg_1m", meta: { align: "r" }, cell: (c) => <Pct v={c.getValue()} dp={1} /> },
    { id: "rsi14", header: "RSI", accessorKey: "rsi14", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : n0(c.getValue())}</span> },
    { id: "avg", header: "GTGD TB20", accessorKey: "avg_value_20d", meta: { align: "r" }, cell: (c) => <span className="num">{bil(c.getValue())}</span> },
  ];
  return (
    <div className="grid gap-3">
      <Panel title="Bộ lọc cổ phiếu" icon={Filter} right={<div className="flex flex-wrap gap-1">{PRESETS.map((p) => <button key={p.id} className="btn !h-7" onClick={() => { const n = { universe: f.universe, sort: f.sort, order: f.order, industry: f.industry, ...p.set }; setF(n); setApplied(n); }}>{p.label}</button>)}</div>}>
        <form className="vn-filter" onSubmit={(e) => { e.preventDefault(); setApplied(f); }}>
          <label>Nhóm mã<select className="field" value={f.universe} onChange={(e) => set("universe", e.target.value)}>{UNIVERSES.filter(([k]) => k !== "etf").map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label>Ngành<select className="field" value={f.industry} onChange={(e) => set("industry", e.target.value)}><option value="">Tất cả ngành</option>{(q.data?.industries || []).map((i) => <option key={i} value={i}>{i}</option>)}</select></label>
          {FIELDS.map(([k, label, hint, side]) => (
            <label key={k}>{label} <span className="text-faint">({hint})</span>
              <input className="field num" inputMode="decimal" placeholder="—" value={f[`${k}_${side}`] ?? ""} onChange={(e) => set(`${k}_${side}`, e.target.value)} /></label>
          ))}
          <label>Xếp theo<select className="field" value={f.sort} onChange={(e) => set("sort", e.target.value)}>{SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label>Thứ tự<select className="field" value={f.order} onChange={(e) => set("order", e.target.value)}><option value="desc">Giảm dần</option><option value="asc">Tăng dần</option></select></label>
          <button className="btn !bg-[var(--accent)] !text-[var(--accent-fg)] !border-transparent justify-center" type="submit"><Search size={14} aria-hidden="true" />Lọc</button>
        </form>
      </Panel>
      <Panel title={q.data ? `Kết quả: ${q.data.total} mã${q.data.total > 100 ? " (hiện 100)" : ""}` : "Kết quả"} icon={LineChart} scroll bodyClass="max-h-[640px]">
        <Async q={q} rows={6} isEmpty={(d) => !d?.rows?.length} empty="Không có mã nào khớp bộ lọc." hint="Nới điều kiện, hoặc đổi nhóm mã. Mã thiếu dữ liệu của một tiêu chí sẽ bị loại.">
          {(d) => (
            <>
              <DataTable data={d.rows} columns={columns} getRowId={(r) => r.code} minWidth={980} />
              <ul className="m-0 mt-2 pl-4 text-[11.5px] text-muted">{d.caveats.map((c) => <li key={c}>{c}</li>)}<li>Dữ liệu cuối ngày {d.as_of} (không chính thức). Không phải khuyến nghị đầu tư.</li></ul>
            </>
          )}
        </Async>
      </Panel>
    </div>
  );
}

/* ---------- Sự kiện + tin ---------- */
export function EventsTab() {
  const [days, setDays] = useState(30);
  const [focus, setFocus] = useState(true);
  const ev = useVnEvents({ days, back: 3, focus: focus ? "true" : "false" });
  const nw = useVnNews({ days: 5, limit: 30 });
  return (
    <div className="vn-2">
      <Panel title="Lịch sự kiện doanh nghiệp" icon={CalendarDays} scroll bodyClass="max-h-[680px]"
        right={<><Seg label="Phạm vi" value={focus ? "vn" : "all"} onChange={(v) => setFocus(v === "vn")} options={[{ value: "vn", label: "VN100/HNX30" }, { value: "all", label: "Tất cả" }]} />
          <Seg label="Số ngày tới" value={days} onChange={setDays} options={[{ value: 14, label: "14 ngày" }, { value: 30, label: "30" }, { value: 90, label: "90" }]} /></>}>
        <Async q={ev} rows={5} isEmpty={(d) => !d?.rows?.length} empty="Không có sự kiện trong khoảng này.">
          {(d) => d.rows.map((e) => (
            <div key={e.event_id} className="vn-ev">
              <div className="num text-[12px]"><div className="font-semibold">{fdate(e.effective_date)}</div><div className="text-faint">{e.effective_date?.slice(0, 4)}</div></div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><Code code={e.code} name={e.name} /><Chip className={e.etype === "DIVIDEND" ? "up" : e.etype === "ISSUE" ? "accent" : ""}>{ETYPE[e.etype] || e.type_desc}</Chip>
                  {e.dividend ? <span className="num text-[12px]">{n0(e.dividend)} đ/cp</span> : null}</div>
                <div className="text-[12.5px] text-muted">{e.note}</div>
              </div>
            </div>
          ))}
        </Async>
        <Note>Ngày hiển thị là ngày giao dịch không hưởng quyền (hoặc ngày họp tuỳ loại sự kiện). Có thể thay đổi: đối chiếu thông báo của doanh nghiệp.</Note>
      </Panel>
      <Panel title="Tin doanh nghiệp theo mã" icon={Newspaper} scroll bodyClass="max-h-[680px]">
        <NewsList q={nw} />
      </Panel>
    </div>
  );
}

function NewsList({ q }) {
  return (
    <Async q={q} rows={5} isEmpty={(d) => !d?.rows?.length} empty="Chưa có tin nào nhắc tới mã cổ phiếu trong vài ngày gần đây.">
      {(d) => (
        <>
          <ul className="m-0 p-0 list-none grid gap-2">
            {d.rows.map((n) => (
              <li key={n.url} className="border-b border-line pb-2">
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="no-underline hover:underline text-[13px]">{clean(n.title)}</a>
                <div className="flex flex-wrap items-center gap-1 mt-1 text-[11.5px] text-muted">{n.codes.map((c) => <a key={c} href={`#/chung-khoan-vn/ma/${c}`}><Chip>{c}</Chip></a>)}</div>
              </li>
            ))}
          </ul>
          <Note>{d.caveat}</Note>
        </>
      )}
    </Async>
  );
}

/* ---------- Chi tiết mã ---------- */
export function SymbolTab({ code }) {
  const list = useVnSymbols({ focus: "true", limit: 300 });
  const q = useVnSymbol(code);
  const nw = useVnNews({ code, days: 14, limit: 15 });
  const [input, setInput] = useState(code || "");
  const go = (v) => { const c = v.trim().toUpperCase().replace(/^VN:/, ""); if (c) location.hash = `#/chung-khoan-vn/ma/${c}`; };
  const bars = useMemo(() => (q.data?.history || []).map((h) => ({ ts_open: `${h.d}T00:00:00Z`, o: h.open, h: h.high, l: h.low, c: h.close, v: h.volume })), [q.data]);
  const adj = useMemo(() => {
    const h = q.data?.history || [];
    if (!h.some((x) => x.ad_close && Math.abs(x.ad_close - x.close) > 1)) return undefined;
    return [{ id: "adj", color: css("--info"), width: 1, dashed: true, data: h.filter((x) => x.ad_close).map((x) => ({ time: Math.floor(Date.parse(`${x.d}T00:00:00Z`) / 1000), value: x.ad_close })) }];
  }, [q.data]);
  const info = q.data?.info, fu = q.data?.fundamentals, sn = q.data?.snapshot;
  return (
    <div className="grid gap-3">
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); go(input); }}>
        <input className="field num uppercase" list="vn-codes" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Nhập mã: VCB, HPG, E1VFVN30…" aria-label="Mã cổ phiếu" style={{ width: 260 }} />
        <datalist id="vn-codes">{(list.data?.rows || []).map((r) => <option key={r.code} value={r.code}>{r.short_name}</option>)}</datalist>
        <button className="btn" type="submit"><Search size={14} aria-hidden="true" />Xem mã</button>
      </form>
      {!code && <Panel><div className="text-muted">Chọn một mã để xem biểu đồ giá, định giá, khối ngoại, sự kiện và tin. Bấm vào mã ở bất kỳ bảng nào cũng mở nhanh trang này.</div></Panel>}
      {code && (
        <Async q={q} rows={8}>
          {() => (
            <>
              <Panel title={`${info.code} · ${info.short_name || info.name || ""}`} right={<><Chip>{info.floor}</Chip>{info.industry_name && <Chip>{info.industry_name}</Chip>}{info.in_vn30 && <Chip className="accent">VN30</Chip>}</>}>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
                  <Stat label="Giá đóng" value={vnd(sn?.close)} sub={pc(sn?.pct)} tone={tone(sn?.pct)} big />
                  <Stat label="Vốn hoá" value={bil(fu?.marketcap)} /><Stat label="P/E" value={n1(fu?.pe)} /><Stat label="P/B" value={n2(fu?.pb)} />
                  <Stat label="ROE ước tính" value={fu?.roe == null ? "—" : `${n1(fu.roe)}%`} sub="= P/B ÷ P/E" /><Stat label="EPS ước tính" value={n0(fu?.eps)} sub="= giá ÷ P/E" />
                  <Stat label="Cổ tức/giá" value={fu?.div_yield == null ? "—" : `${n1(fu.div_yield)}%`} /><Stat label="Beta" value={n2(fu?.beta)} />
                </div>
                <Note>Biên độ hôm nay: sàn {vnd(sn?.flr)} · tham chiếu {vnd(sn?.basic)} · trần {vnd(sn?.ceil)}. 52 tuần: {vnd(fu?.lo_52w)} – {vnd(fu?.hi_52w)}.</Note>
              </Panel>
              <Panel title="Biểu đồ ngày (giá thô)" icon={LineChart} pad={false} bodyClass="flex flex-col" right={adj && <Chip title="Nét đứt xanh: giá điều chỉnh cổ tức/thưởng/chia tách">có đường giá điều chỉnh</Chip>}>
                <div className="flex flex-col" style={{ height: 420 }}><CandleChart bars={bars} symbol={`VN:${code}`} tf="D1" decimals={0} overlays={adj} height={380} /></div>
              </Panel>
              <div className="vn-2">
                <Panel title="Khối ngoại 30 phiên" scroll bodyClass="max-h-[320px]">
                  <DataTable data={[...(q.data.foreign || [])].reverse()} getRowId={(r) => r.d} minWidth={360} empty="Chưa có dữ liệu khối ngoại."
                    columns={[{ id: "d", header: "Ngày", accessorKey: "d", cell: (c) => <span className="num">{fdate(c.getValue())}</span> },
                      { id: "b", header: "Mua", accessorKey: "buy_val", meta: { align: "r" }, cell: (c) => <span className="num">{bil(c.getValue())}</span> },
                      { id: "s", header: "Bán", accessorKey: "sell_val", meta: { align: "r" }, cell: (c) => <span className="num">{bil(c.getValue())}</span> },
                      { id: "n", header: "Ròng", accessorKey: "net_val", meta: { align: "r" }, cell: (c) => <span className={cn("num", tone(c.getValue()))}>{bil(c.getValue(), true)}</span> }]} />
                </Panel>
                <Panel title="Sự kiện sắp tới / vừa qua" scroll bodyClass="max-h-[320px]">
                  {(q.data.events || []).length === 0 ? <div className="text-muted">Không có sự kiện nào trong khoảng −30 / +180 ngày.</div>
                    : q.data.events.map((e) => <div key={e.event_id} className="vn-ev"><div className="num text-[12px] font-semibold">{fdate(e.effective_date)}</div><div><Chip>{ETYPE[e.etype] || e.type_desc}</Chip> <span className="text-[12.5px] text-muted">{e.note}</span></div></div>)}
                </Panel>
              </div>
              <Panel title={`Tin nhắc tới ${code}`} icon={Newspaper} scroll bodyClass="max-h-[320px]"><NewsList q={nw} /></Panel>
            </>
          )}
        </Async>
      )}
    </div>
  );
}
