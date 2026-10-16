// Trang "Kịch bản" (master): tín hiệu kịch bản Sell KB-1..KB-4 đang chạy, chi tiết setup (ảnh, checklist, sự kiện, nến + mức gợi ý),
// lịch sử + kết quả PAPER (sổ cái hash-chain), thư viện ví dụ, mô tả kịch bản. CHỈ ĐỌC — không có thao tác đặt lệnh.
// API (gateway, GET): /v1/patterns/live, /setup, /trades, /stats, /examples, /spec — hợp đồng: docs/handoff/SCAN_status.md.
import { useEffect, useMemo, useRef, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { createSeriesMarkers, LineStyle } from "lightweight-charts";
import { Activity, BookOpenText, Download, FlaskConical, Crosshair, History, ImageIcon, Images, ListChecks, ShieldCheck, ShieldAlert, ZoomIn } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg, Stat, cn } from "../components/ui";
import { CandleChart, EChart, css } from "../components/charts";
import { DataTable } from "../components/table";
import { Dialog } from "../components/dialog";
import { EmptyState } from "../components/ux/States";
import { api } from "../lib/api";
import { useBars } from "../lib/queries";
import { clean, date, dateTime, decimals, price, rel, symbolLabel } from "../lib/format";
import "./scenarios.css";

export const meta = {
  path: "kich-ban", label: "Kịch bản", group: "Thị trường", icon: Crosshair, order: 62, roles: ["master"],
  keywords: "kich ban sell pattern setup KB-1 KB-2 KB-3 KB-4 nhan chim vai dau vai nem paper trade tin hieu",
};

const NOTE = "Chỉ thông tin/mô phỏng (paper), không phải khuyến nghị đầu tư; hệ thống không đặt lệnh.";
const STATE = {
  triggered: { label: "Đã kích hoạt", tone: "down" },
  armed: { label: "Sẵn sàng", tone: "accent" },
  forming: { label: "Đang hình thành", tone: "" },
  invalid: { label: "Đã huỷ", tone: "" },
};
const GROUPS = ["triggered", "armed", "forming"];
const LEG = { open: "Đang mở", tp: "Chốt lời", sl: "Cắt lỗ", timeout: "Hết hạn" };
// Mô tả ngắn từ docs/PATTERNS_SELL.md §3 (cấu trúc / nến kích hoạt / huỷ).
const KB_DOC = {
  "KB-1": { struct: "Sóng dẫn → hồi 15–60% → giảm nhẹ ≈ sóng (2) ±25% → hồi vượt đỉnh (2) ≤ 25% sóng (3) → đi ngang, 2 đỉnh giảm dần.", trigger: "Nhấn chìm giảm thân ≥ 1.5 ATR trong ≤ 8 nến sau đỉnh (5), đỉnh (5) < đỉnh (4).", cancel: "Đóng cửa > đỉnh (4) + 0.25 ATR; quá hạn; thủng đáy giữa > 0.75 ATR mà không có nhấn chìm." },
  "KB-2": { struct: "Sóng dẫn → hồi 25–75% → nêm: ≥ 3 đỉnh thấp dần, ≥ 2 đáy cao dần, co hẹp ≤ 85%.", trigger: "Nhấn chìm giảm thân ≥ 1.5 ATR, đóng dưới cạnh dưới của nêm.", cancel: "Đóng cửa > đỉnh hồi (2) + 0.25 ATR; quá 220 nến; đóng dưới cạnh dưới > 0.75 ATR mà không có nhấn chìm." },
  "KB-3": { struct: "Sóng dẫn ≥ 8 ATR → đi ngang ≥ 40 nến → vai-đầu-vai → giá về sát đường cổ.", trigger: "Cụm 3 nến thân ≤ 0.5 ATR ngay sát đường cổ.", cancel: "Chạm quá đỉnh đầu / đóng > vai phải + 0.25 ATR; thủng cổ > 1 ATR trước cụm nén; quá 90 nến sau vai phải." },
  "KB-4": { struct: "Đi ngang (hộp ≤ 8 ATR) → nến thân ≥ 2 ATR đóng dưới hộp → ≥ 3 nến đỏ + sóng dẫn → đi ngang mới → 3 đỉnh giảm dần.", trigger: "Cụm 3 nến nén dưới đỉnh thứ 3.", cancel: "Đóng cửa > đỉnh đầu của vùng mới; thủng đáy sóng dẫn > 0.75 ATR; quá 30 nến sau đỉnh 3." },
};

// ---------- dữ liệu ----------
const pq = (key, path, params, opts = {}) => ({
  queryKey: ["patterns", key, params], queryFn: ({ signal }) => api(path, params, signal),
  staleTime: 15_000, placeholderData: keepPreviousData, retry: 1, ...opts,
});
const useLive = (view) => useQuery(pq("live", "/patterns/live", { view, limit: 200, days: view === "history" ? 90 : undefined }, { refetchInterval: 30_000 }));
const useSetup = (s) => useQuery(pq("setup", "/patterns/setup", s ? { setup_id: s.setup_id, symbol: s.symbol, tf: s.tf } : {}, { enabled: !!s, placeholderData: undefined, refetchInterval: 30_000 }));
const useTrades = () => useQuery(pq("trades", "/patterns/trades", { status: "all", limit: 500 }, { refetchInterval: 60_000 }));
const useStats = () => useQuery(pq("stats", "/patterns/stats", {}, { refetchInterval: 60_000 }));
const useExamples = () => useQuery(pq("examples", "/patterns/examples", {}, { staleTime: 300_000 }));
const useBacktest = () => useQuery(pq("backtest", "/patterns/backtest/summary", {}, { staleTime: 600_000 }));
const useSpec = () => useQuery(pq("spec", "/patterns/spec", {}, { staleTime: 300_000 }));

const items = (d) => (Array.isArray(d) ? d : d?.items || []);
const img = (u) => (u ? (/^https?:/.test(u) ? u : `/api${u.startsWith("/") ? "" : "/"}${u}`) : null);
const dec = (s) => decimals(symbolLabel(s));
const px = (s, v) => price(symbolLabel(s), v);
const num = (v, dp = 2) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(dp));
const rr = (v, dp = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(dp)}R`);
const rTone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const pctv = (v) => (v == null ? "—" : `${(v <= 1 ? v * 100 : v).toFixed(1)}%`);
const tsOf = (s) => s.bar_ts || s.last_ts || s.first_ts;
const kbOf = (p) => (p || "").toUpperCase().replace(/^KB-?(\d+)$/, "KB-$1");

function StateChip({ state }) {
  const s = STATE[state] || { label: state, tone: "" };
  return <Chip tone={s.tone}>{s.label}</Chip>;
}

function Thumb({ src, alt, className, onClick, eager }) {
  const [bad, setBad] = useState(false);
  useEffect(() => setBad(false), [src]);
  const body = !src || bad
    ? <div className="sc-noimg" role="img" aria-label="Chưa có ảnh"><ImageIcon size={20} aria-hidden="true" /><span>Chưa có ảnh</span></div>
    : <img src={src} alt={alt} loading={eager ? "eager" : "lazy"} decoding="async" onError={() => setBad(true)} />;
  if (!onClick || !src || bad) return <div className={cn("sc-thumb", className)}>{body}</div>;
  return (
    <button type="button" className={cn("sc-thumb sc-zoomable", className)} onClick={onClick} aria-label={`Phóng to: ${alt}`}>
      {body}<span className="sc-zoom" aria-hidden="true"><ZoomIn size={14} /></span>
    </button>
  );
}

function Lightbox({ src, alt, onClose }) {
  return (
    <Dialog open={!!src} onClose={onClose} title={alt || "Ảnh kịch bản"} className="sc-lightbox">
      {src && <div className="sc-lightbox-b"><img src={src} alt={alt} /></div>}
    </Dialog>
  );
}

function Levels({ symbol, lv, compact }) {
  if (!lv) return null;
  const rows = [["Entry", lv.entry, ""], ["SL", lv.sl, "down"], ["TP1", lv.tp_1r, "up"], ["TP2", lv.tp_2r, "up"], ["TP3", lv.tp_3r, "up"]].filter((r) => r[1] != null);
  if (!rows.length) return null;
  return (
    <dl className={cn("sc-levels", compact && "sc-levels-c")}>
      {rows.map(([k, v, t]) => (
        <div key={k}><dt>{k}</dt><dd className={cn("num", t)}>{px(symbol, v)}</dd></div>
      ))}
    </dl>
  );
}

// ---------- Tín hiệu hiện tại ----------
function Filters({ list, f, setF }) {
  const opts = (k) => [...new Set(list.map((x) => x[k]).filter(Boolean))].sort();
  const sel = (k, label, fmt = (v) => v) => (
    <label className="sc-filter">
      <span className="sr-only">{label}</span>
      <select className="field" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} aria-label={label}>
        <option value="">{label}: tất cả</option>
        {opts(k).map((v) => <option key={v} value={v}>{fmt(v)}</option>)}
      </select>
    </label>
  );
  return (
    <div className="sc-filters" role="group" aria-label="Bộ lọc">
      {sel("symbol", "Mã", symbolLabel)}
      {sel("tf", "Khung")}
      {sel("pattern", "Kịch bản", kbOf)}
      {(f.symbol || f.tf || f.pattern) && <button type="button" className="btn" onClick={() => setF({ symbol: "", tf: "", pattern: "" })}>Xoá lọc</button>}
    </div>
  );
}
const applyF = (list, f) => list.filter((x) => (!f.symbol || x.symbol === f.symbol) && (!f.tf || x.tf === f.tf) && (!f.pattern || x.pattern === f.pattern));

function SetupCard({ s, onOpen }) {
  const t = tsOf(s);
  return (
    <button type="button" className={cn("sc-card", `sc-st-${s.state}`)} onClick={() => onOpen(s)} aria-label={`Mở chi tiết ${kbOf(s.pattern)} ${symbolLabel(s.symbol)} ${s.tf}`}>
      <Thumb src={img(s.image)} alt={`${kbOf(s.pattern)} ${symbolLabel(s.symbol)} ${s.tf}`} />
      <div className="sc-card-b">
        <div className="sc-card-h">
          <strong className="sc-sym">{symbolLabel(s.symbol)}</strong>
          <Chip>{s.tf}</Chip>
          <Chip tone="ro">{kbOf(s.pattern)}</Chip>
          <span className="ml-auto num text-[12px]" title="Điểm xếp hạng 0–100 (không phải xác suất thắng)">{num(s.score, 0)}<span className="text-faint">/100</span></span>
        </div>
        <div className="sc-card-m"><StateChip state={s.state} /><span className="text-faint">Sell</span><time dateTime={t} title={dateTime(t)}>{rel(t)}</time></div>
        <Levels symbol={s.symbol} lv={s.levels} compact />
      </div>
    </button>
  );
}

function LiveTab({ onOpen }) {
  const q = useLive("active");
  const [f, setF] = useState({ symbol: "", tf: "", pattern: "" });
  const all = items(q.data);
  const list = applyF(all, f);
  return (
    <div className="flex flex-col gap-3">
      <Filters list={all} f={f} setF={setF} />
      <Async q={q} rows={6} empty="Chưa có setup nào đang chạy." hint="Hệ thống quét khi nến đóng; setup mới sẽ hiện ở đây." isEmpty={() => all.length === 0} what="tín hiệu kịch bản">
        {() => (list.length === 0
          ? <EmptyState compact title="Không có setup khớp bộ lọc." />
          : GROUPS.map((g) => {
            const rows = list.filter((x) => x.state === g).sort((a, b) => String(tsOf(b)).localeCompare(String(tsOf(a))));
            return (
              <section key={g} className="sc-group" aria-label={STATE[g].label}>
                <h3 className="sc-group-h"><StateChip state={g} /> <span className="text-muted">{rows.length}</span>
                  {g === "forming" && <span className="text-faint text-[11.5px] font-normal">— chưa đủ cấu trúc, chỉ theo dõi</span>}</h3>
                {rows.length ? <div className="sc-grid">{rows.map((s) => <SetupCard key={`${s.setup_id}|${s.symbol}|${s.tf}`} s={s} onOpen={onOpen} />)}</div>
                  : <p className="text-faint text-[12.5px] m-0">Không có.</p>}
              </section>
            );
          }))}
      </Async>
    </div>
  );
}

// ---------- Chi tiết ----------
function snapTime(times, t) {
  // thời điểm nến <= t gần nhất (marker phải nằm đúng thời điểm nến)
  let lo = 0, hi = times.length - 1, ans = null;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (times[m] <= t) { ans = times[m]; lo = m + 1; } else hi = m - 1; }
  return ans;
}

function SetupChart({ d }) {
  const bars = useBars(d.symbol, d.tf, 400, { refetchInterval: 60_000 });
  const ordered = useMemo(() => [...(bars.data?.items || [])].reverse(), [bars.data]);
  const [chartApi, setApi] = useState(null);
  const lines = useRef([]);
  const mk = useRef(null);
  const lv = d.levels || {};
  const marks = d.marks || d.points;
  useEffect(() => {
    const s = chartApi?.candles;
    if (!s) return;
    for (const l of lines.current) s.removePriceLine(l);
    const defs = [["Entry", lv.entry, css("--accent"), LineStyle.Solid], ["SL", lv.sl, css("--down"), LineStyle.Dashed],
      ["TP1", lv.tp_1r, css("--up"), LineStyle.Dotted], ["TP2", lv.tp_2r, css("--up"), LineStyle.Dotted], ["TP3", lv.tp_3r, css("--up"), LineStyle.Dotted]];
    lines.current = defs.filter((x) => x[1] != null).map(([title, p, color, ls]) => s.createPriceLine({ price: p, color, lineWidth: 1, lineStyle: ls, axisLabelVisible: true, title }));
    const times = ordered.map((b) => Math.floor(new Date(b.ts_open).getTime() / 1000));
    const list = (marks || []).map((m) => {
      const t = snapTime(times, Math.floor(new Date(m.t).getTime() / 1000));
      if (t == null) return null;
      const bar = ordered[times.indexOf(t)];
      // đỉnh -> trên nến, đáy -> dưới nến (so giá điểm với giữa nến); trigger luôn ở trên (mũi tên xuống, Sell)
      const top = m.kind === "trigger" || !bar || m.p == null || m.p >= (bar.h + bar.l) / 2;
      return { time: t, position: top ? "aboveBar" : "belowBar", color: m.kind === "trigger" ? css("--down") : css("--info"), shape: m.kind === "trigger" ? "arrowDown" : "circle", text: m.label || "" };
    }).filter(Boolean).sort((a, b) => a.time - b.time);
    if (!mk.current) mk.current = createSeriesMarkers(s, list); else mk.current.setMarkers(list);
    const w = d.window;
    if (w?.from && times.length) {
      const f = snapTime(times, Math.floor(new Date(w.from).getTime() / 1000)) ?? times[0];
      const i0 = times.indexOf(f), i1 = w.to ? times.indexOf(snapTime(times, Math.floor(new Date(w.to).getTime() / 1000)) ?? times[times.length - 1]) : times.length - 1;
      try { chartApi.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, i0 - 5), to: Math.max(i0 + 20, i1) + 8 }); } catch { /* bỏ qua */ }
    }
  }, [chartApi, ordered, lv.entry, lv.sl, lv.tp_1r, lv.tp_2r, lv.tp_3r, marks, d.window]);
  return (
    <Async q={bars} variant="chart" height={300} empty={`Chưa có nến ${d.tf}.`} what="nến">
      {() => <div className="sc-chart"><CandleChart bars={ordered} symbol={d.symbol} tf={d.tf} decimals={dec(d.symbol)} height={300} onReady={setApi} /></div>}
    </Async>
  );
}

function TradeBox({ t }) {
  if (!t) return <p className="text-faint text-[12.5px] m-0">Chưa có lệnh paper cho setup này.</p>;
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(6.5rem,1fr))] gap-3">
        <Stat label="Trạng thái" value={t.status === "open" ? "Đang mở" : "Đã đóng"} />
        <Stat label="Kết quả" value={rr(t.result_r)} tone={rTone(t.result_r)} sub={t.cost_r ? `phí ${num(t.cost_r)}R` : undefined} />
        <Stat label="MFE / MAE" value={`${num(t.mfe_r)} / ${num(t.mae_r)}`} sub="theo R" />
        <Stat label="Số nến" value={t.bars_held ?? "—"} />
      </div>
      {!!t.legs?.length && (
        <ul className="sc-legs">
          {t.legs.map((l, i) => (
            <li key={i}><span>Phần {i + 1} · TP {px(t.symbol, l.tp)}</span><Chip tone={l.status === "tp" ? "up" : l.status === "sl" ? "down" : ""}>{LEG[l.status] || l.status}</Chip>
              <span className={cn("num ml-auto", rTone(l.r))}>{l.r == null ? "" : rr(l.r)}</span></li>
          ))}
        </ul>
      )}
      {t.replay && <p className="text-faint text-[11.5px] m-0">Lệnh dựng lại từ dữ liệu quá khứ (replay), không phải theo dõi trực tiếp.</p>}
    </div>
  );
}

function SetupDetail({ sel, onClose, onZoom }) {
  const q = useSetup(sel);
  const title = sel ? `${kbOf(sel.pattern)} · ${symbolLabel(sel.symbol)} ${sel.tf}` : "";
  return (
    <Dialog open={!!sel} onClose={onClose} variant="drawer" title={title} className="sc-drawer">
      {sel && (
        <div className="p-3 flex flex-col gap-4">
          <Disclaimer>{NOTE}</Disclaimer>
          <Async q={q} rows={10} empty="Không tìm thấy setup." what="chi tiết setup" isEmpty={(d) => !d}>
            {(raw) => {
              const d = raw.item ? { ...raw.item, marks: raw.marks ?? raw.item.marks, window: raw.window } : raw;
              const big = img(d.image);
              const alt = `${kbOf(d.pattern)} ${symbolLabel(d.symbol)} ${d.tf}`;
              return (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <StateChip state={d.state} /><Chip tone="ro">{kbOf(d.pattern)}</Chip><Chip>{d.tf}</Chip><Chip tone="down">Sell</Chip>
                    <span className="num text-[12.5px] ml-auto" title="Điểm xếp hạng 0–100 (không phải xác suất thắng)">Điểm {num(d.score, 0)}/100</span>
                  </div>
                  {d.name && <p className="m-0 text-[12.5px] text-muted">{clean(d.name)}</p>}
                  <Thumb src={big} alt={alt} className="sc-big" eager onClick={() => onZoom({ src: big, alt })} />
                  {["entry", "sl", "tp_1r"].some((k) => d.levels?.[k] != null) ? <section aria-label="Mức giá gợi ý">
                    <h3 className="sc-h3">Mức giá gợi ý</h3>
                    <Levels symbol={d.symbol} lv={d.levels} />
                    {d.levels?.r != null && <p className="text-faint text-[11.5px] m-0 mt-1">R = {px(d.symbol, d.levels.r)}{d.levels.atr != null && <> · ATR = {px(d.symbol, d.levels.atr)}</>} · TP = Entry − m×R.</p>}
                  </section> : <p className="text-faint text-[12px] m-0">Chưa có mức giá gợi ý (setup chưa đủ cấu trúc).</p>}
                  <section aria-label="Biểu đồ nến">
                    <h3 className="sc-h3">Biểu đồ nến {d.tf}</h3>
                    <SetupChart d={d} />
                  </section>
                  <section aria-label="Checklist">
                    <h3 className="sc-h3">Checklist</h3>
                    <ol className="sc-steps">
                      {(d.steps || []).map((s) => (
                        <li key={s.id} className={s.ok ? "ok" : "no"}>
                          <span className="sc-tick" aria-label={s.ok ? "Đạt" : "Chưa đạt"}>{s.ok ? "✓" : "–"}</span>
                          <div><div>{clean(s.label)}</div>{s.detail && <div className="text-faint text-[11.5px]">{clean(s.detail)}</div>}</div>
                        </li>
                      ))}
                    </ol>
                    {d.reason && <p className="text-[12px] text-muted m-0 mt-2">Lý do huỷ: {clean(d.reason)}</p>}
                  </section>
                  <section aria-label="Dòng thời gian">
                    <h3 className="sc-h3">Dòng thời gian</h3>
                    <ol className="sc-timeline">
                      {(d.events || []).map((e) => (
                        <li key={e.id ?? `${e.state}${e.ts}`}>
                          <div className="flex flex-wrap items-center gap-2"><StateChip state={e.state} />
                            <time className="text-[12px]" dateTime={e.ts}>{dateTime(e.bar_ts || e.ts)}</time>
                            {e.score != null && <span className="num text-faint text-[11.5px]">điểm {num(e.score, 0)}</span>}</div>
                          {e.image && <Thumb src={img(e.image)} alt={`Ảnh lúc ${STATE[e.state]?.label || e.state}`} className="sc-ev" onClick={() => onZoom({ src: img(e.image), alt: `${alt} — ${STATE[e.state]?.label || e.state}` })} />}
                        </li>
                      ))}
                      {!d.events?.length && <li className="text-faint">Chưa có sự kiện.</li>}
                    </ol>
                  </section>
                  <section aria-label="Lệnh paper">
                    <h3 className="sc-h3">Lệnh paper</h3>
                    <TradeBox t={d.trade} />
                  </section>
                </>
              );
            }}
          </Async>
        </div>
      )}
    </Dialog>
  );
}

// ---------- Lịch sử + kết quả paper ----------
function EquityChart({ eq }) {
  return (
    <EChart height={220} label="Đường cong R luỹ kế" deps={[eq]} build={() => ({
      grid: { left: 44, right: 12, top: 12, bottom: 26 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${Number(v).toFixed(2)}R` },
      xAxis: { type: "time", axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), hideOverlap: true, formatter: (v) => date(v) } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: css("--line") } }, axisLabel: { color: css("--muted"), formatter: (v) => `${v}R` } },
      series: [{ type: "line", step: "end", showSymbol: eq.length < 40, symbolSize: 4, data: eq.map((p) => [p.t, p.cum_r]),
        lineStyle: { color: css("--accent"), width: 2 }, itemStyle: { color: css("--accent") },
        areaStyle: { color: css("--accent"), opacity: 0.08 },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: css("--line2"), type: "dashed" }, label: { show: false } } }],
    })} />
  );
}

const BY = [{ value: "by_pattern", label: "Theo KB" }, { value: "by_tf", label: "Theo khung" }, { value: "by_symbol", label: "Theo mã" }];
function Breakdown({ st }) {
  const [by, setBy] = useState("by_pattern");
  const rows = (st[by] || []).map((r) => ({ ...r, key: r.key ?? r.pattern ?? r.tf ?? r.symbol ?? r.name }));
  const cols = useMemo(() => [
    { header: by === "by_pattern" ? "KB" : by === "by_tf" ? "Khung" : "Mã", accessorKey: "key", cell: (c) => (by === "by_symbol" ? symbolLabel(c.getValue()) : by === "by_pattern" ? kbOf(c.getValue()) : c.getValue()) },
    { header: "Số lệnh", accessorFn: (r) => r.n_closed ?? r.n, id: "n", meta: { align: "r" } },
    { header: "Winrate", accessorKey: "winrate", meta: { align: "r" }, cell: (c) => pctv(c.getValue()) },
    { header: "R TB", accessorKey: "avg_r", meta: { align: "r" }, cell: (c) => <span className={rTone(c.getValue())}>{rr(c.getValue())}</span> },
    { header: "Tổng R", accessorKey: "sum_r", meta: { align: "r" }, cell: (c) => <span className={rTone(c.getValue())}>{rr(c.getValue())}</span> },
    { header: "PF", accessorKey: "pf", meta: { align: "r" }, cell: (c) => num(c.getValue()) },
  ], [by]);
  return (
    <Panel title="Phân rã" icon={ListChecks} right={<Seg value={by} onChange={setBy} options={BY} label="Phân rã theo" />}>
      <DataTable data={rows} columns={cols} minWidth={420} empty="Chưa có lệnh đã đóng." initialSort={[{ id: "n", desc: true }]} />
    </Panel>
  );
}

function StatsBlock() {
  const q = useStats();
  return (
    <Async q={q} rows={5} what="thống kê paper" isEmpty={(d) => !d?.overall}>
      {(st) => {
        const o = st.overall;
        const n = o.n_closed ?? 0;
        const led = st.ledger || {};
        return (
          <div className="flex flex-col gap-3">
            <Panel title="Kết quả paper" icon={Activity} right={
              <span className="flex items-center gap-2">
                <Chip tone={led.ok ? "up" : led.ok === false ? "down" : ""} title={led.head ? `Đầu chuỗi: ${String(led.head).slice(0, 16)}…` : undefined}>
                  {led.ok ? <ShieldCheck size={12} aria-hidden="true" /> : <ShieldAlert size={12} aria-hidden="true" />}
                  Sổ cái {led.ok ? "toàn vẹn" : led.ok === false ? "LỖI chuỗi hash" : "chưa kiểm"}{led.n != null ? ` · ${led.n}` : ""}
                </Chip>
              </span>}>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(7.5rem,1fr))] gap-3">
                <Stat label="Số lệnh" big value={n} sub={`đang mở ${o.n_open ?? 0}`} term={false} />
                <Stat label="Winrate" big value={pctv(o.winrate)} sub={`${o.wins ?? 0} thắng / ${o.losses ?? 0} thua`} />
                <Stat label="R TB" big value={rr(o.avg_r)} tone={rTone(o.avg_r)} term={false} />
                <Stat label="Tổng R" big value={rr(o.sum_r)} tone={rTone(o.sum_r)} term={false} />
                <Stat label="Profit factor" big value={num(o.pf)} />
                <Stat label="Max DD" big value={o.max_dd_r == null ? "—" : `${num(Math.abs(o.max_dd_r))}R`} tone={o.max_dd_r ? "down" : ""} term={false} />
              </div>
              {n < 30 && <p className="sc-small-n" role="note">Mẫu nhỏ (n = {n} &lt; 30): chưa có ý nghĩa thống kê, không dùng để kết luận hiệu quả.</p>}
              {st.note && <p className="text-faint text-[11.5px] m-0 mt-2">{clean(st.note)}</p>}
              {st.as_of && <p className="text-faint text-[11.5px] m-0 mt-1">Cập nhật {dateTime(st.as_of)}</p>}
            </Panel>
            <div className="sc-2col">
              <Panel title="Đường cong R luỹ kế" icon={Activity} bodyClass="flex flex-col">
                {st.equity?.length ? <EquityChart eq={st.equity} /> : <EmptyState compact title="Chưa có lệnh đã đóng." />}
              </Panel>
              <Breakdown st={st} />
            </div>
          </div>
        );
      }}
    </Async>
  );
}

function TradesTable({ onOpen }) {
  const q = useTrades();
  const [status, setStatus] = useState("all");
  const all = items(q.data);
  const rows = status === "all" ? all : all.filter((t) => t.status === status);
  const cols = useMemo(() => [
    { header: "Mở lúc", accessorKey: "opened_at", cell: (c) => <span className="whitespace-nowrap">{dateTime(c.getValue())}</span> },
    { header: "Mã", accessorKey: "symbol", cell: (c) => <strong>{symbolLabel(c.getValue())}</strong> },
    { header: "Khung", accessorKey: "tf" },
    { header: "KB", accessorKey: "pattern", cell: (c) => kbOf(c.getValue()) },
    { header: "Trạng thái", accessorKey: "status", cell: (c) => <Chip tone={c.getValue() === "open" ? "accent" : ""}>{c.getValue() === "open" ? "Mở" : "Đóng"}</Chip> },
    { header: "Entry", accessorKey: "entry", meta: { align: "r" }, cell: (c) => <span className="num">{px(c.row.original.symbol, c.getValue())}</span> },
    { header: "SL", accessorKey: "sl", meta: { align: "r" }, cell: (c) => <span className="num">{px(c.row.original.symbol, c.getValue())}</span> },
    { header: "Kết quả", accessorKey: "result_r", meta: { align: "r" }, cell: (c) => <span className={cn("num", rTone(c.getValue()))}>{rr(c.getValue())}</span> },
    { header: "MFE", accessorKey: "mfe_r", meta: { align: "r" }, cell: (c) => <span className="num">{num(c.getValue())}</span> },
    { header: "MAE", accessorKey: "mae_r", meta: { align: "r" }, cell: (c) => <span className="num">{num(c.getValue())}</span> },
    { header: "Nến", accessorKey: "bars_held", meta: { align: "r" } },
    { header: "Đóng lúc", accessorKey: "closed_at", cell: (c) => <span className="whitespace-nowrap">{c.getValue() ? dateTime(c.getValue()) : "—"}</span> },
    { header: "", id: "x", enableSorting: false, cell: (c) => (
      <span className="flex items-center gap-1 justify-end">
        {c.row.original.replay && <Chip title="Dựng lại từ dữ liệu quá khứ">replay</Chip>}
        {c.row.original.setup_id && <button type="button" className="btn !h-7 !min-h-0" onClick={() => onOpen(c.row.original)}>Xem</button>}
      </span>) },
  ], [onOpen]);
  return (
    <Panel title="Lệnh paper" icon={History} right={<Seg value={status} onChange={setStatus} label="Lọc trạng thái lệnh"
      options={[{ value: "all", label: "Tất cả" }, { value: "open", label: "Mở" }, { value: "closed", label: "Đóng" }]} />}>
      <Async q={q} variant="table" cols={8} rows={5} empty="Chưa có lệnh paper." hint="Lệnh paper mở khi setup được kích hoạt (nến đóng)." what="lệnh paper">
        {() => <DataTable data={rows} columns={cols} minWidth={980} getRowId={(r) => String(r.id)} initialSort={[{ id: "opened_at", desc: true }]} empty="Không có lệnh ở trạng thái này." />}
      </Async>
    </Panel>
  );
}

function HistorySetups({ onOpen }) {
  const q = useLive("history");
  const [f, setF] = useState({ symbol: "", tf: "", pattern: "" });
  const all = items(q.data);
  const rows = applyF(all, f);
  const cols = useMemo(() => [
    { header: "Thời gian", id: "t", accessorFn: (r) => tsOf(r), cell: (c) => <span className="whitespace-nowrap">{dateTime(c.getValue())}</span> },
    { header: "Mã", accessorKey: "symbol", cell: (c) => <strong>{symbolLabel(c.getValue())}</strong> },
    { header: "Khung", accessorKey: "tf" },
    { header: "KB", accessorKey: "pattern", cell: (c) => kbOf(c.getValue()) },
    { header: "Kết cục", accessorKey: "state", cell: (c) => <StateChip state={c.getValue()} /> },
    { header: "Điểm", accessorKey: "score", meta: { align: "r" }, cell: (c) => <span className="num">{num(c.getValue(), 0)}</span> },
    { header: "Paper", id: "r", accessorFn: (r) => r.trade?.result_r, meta: { align: "r" }, cell: (c) => <span className={cn("num", rTone(c.getValue()))}>{c.getValue() == null ? "—" : rr(c.getValue())}</span> },
    { header: "", id: "x", enableSorting: false, cell: (c) => <button type="button" className="btn !h-7 !min-h-0" onClick={() => onOpen(c.row.original)}>Xem</button> },
  ], [onOpen]);
  return (
    <Panel title="Lịch sử setup" icon={History}>
      <div className="mb-2"><Filters list={all} f={f} setF={setF} /></div>
      <Async q={q} variant="table" cols={7} rows={5} empty="Chưa có setup đã kết thúc." what="lịch sử setup" isEmpty={() => all.length === 0}>
        {() => <DataTable data={rows} columns={cols} minWidth={640} getRowId={(r) => `${r.setup_id}|${r.symbol}|${r.tf}`} initialSort={[{ id: "t", desc: true }]} empty="Không có setup khớp bộ lọc." />}
      </Async>
    </Panel>
  );
}

// ---------- Thư viện ví dụ ----------
function ExamplesTab({ onZoom }) {
  const q = useExamples();
  return (
    <Async q={q} rows={6} empty="Chưa có ví dụ." hint="Ví dụ gồm ảnh mẫu chuẩn và setup đã kích hoạt." what="thư viện ví dụ">
      {(d) => (
        <div className="sc-grid sc-ex">
          {items(d).map((e) => {
            const src = img(e.image || (e.id != null ? `/v1/patterns/examples/${e.id}.png` : null));
            const title = clean(e.title) || `${kbOf(e.pattern)} ${symbolLabel(e.symbol)} ${e.tf || ""}`;
            return (
              <figure key={e.id} className="sc-fig">
                <Thumb src={src} alt={title} onClick={() => onZoom({ src, alt: title })} />
                <figcaption>
                  <div className="flex flex-wrap items-center gap-1.5">{e.pattern && <Chip tone="ro">{kbOf(e.pattern)}</Chip>}{e.symbol && <strong>{symbolLabel(e.symbol)}</strong>}{e.tf && <Chip>{e.tf}</Chip>}
                    {e.ts && <time className="text-faint text-[11.5px] ml-auto" dateTime={e.ts}>{dateTime(e.ts)}</time>}</div>
                  <div className="text-[12.5px]">{title}</div>
                  {e.note && <div className="text-faint text-[11.5px]">{clean(e.note)}</div>}
                </figcaption>
              </figure>
            );
          })}
        </div>
      )}
    </Async>
  );
}

// ---------- Backtest (hiện vật đóng băng, CHỈ master) ----------
const CHART_TITLE = {
  a1_equity_total: "Đường vốn tổng (R luỹ kế)", a2_equity_by_kb: "Đường vốn theo kịch bản", a3_equity_by_tf: "Đường vốn theo khung", a4_equity_by_symbol: "Đường vốn theo mã",
  b_drawdown: "Sụt vốn (drawdown)", c_dist_r_mae_mfe: "Phân phối R, MAE/MFE", d1_heat_kb_tf: "Bản đồ nhiệt kịch bản × khung", d2_heat_symbol_tf: "Bản đồ nhiệt mã × khung",
  e_by_year_session: "Theo năm và phiên", f_baseline_random: "So với vào lệnh ngẫu nhiên", g_pbo_dsr: "Kiểm quá khớp (PBO, DSR)",
  i_golden_kb_1: "Mẫu chuẩn KB-1 so với ảnh mẫu", i_golden_kb_2: "Mẫu chuẩn KB-2 so với ảnh mẫu", i_golden_kb_3: "Mẫu chuẩn KB-3 so với ảnh mẫu",
};
const OUT = { thang: "Thắng", thua: "Thua", "te-nhat": "Tệ nhất" };
const chartTitle = (n) => { const k = n.replace(/\.png$/, "").replace(/-/g, "_"); return CHART_TITLE[k] || n.replace(/\.png$/, ""); };
const parseEx = (n) => { const m = /^(KB-\d+)_([a-z-]+)_([A-Z]\d+)_([A-Za-z0-9:.]+)_([A-Z0-9]+)\.png$/.exec(n); return m ? { kb: m[1], out: m[2], id: m[3], symbol: m[4], tf: m[5] } : { kb: "", out: "", id: n, symbol: "", tf: "" }; };
const fsize = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const sgn = (v, dp = 3) => (v == null ? "—" : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(dp).replace(".", ",")}`);
const pvn = (v) => (v == null ? "—" : v.toFixed(v < 0.1 ? 4 : 2).replace(".", ","));

function BacktestTab({ onZoom }) {
  const q = useBacktest();
  const [kb, setKb] = useState("");
  const [out, setOut] = useState("");
  const cols = useMemo(() => [
    { header: "Tập", accessorKey: "label", cell: (c) => <span className="font-medium">{c.getValue()}</span> },
    { header: "Số lệnh", accessorKey: "n", meta: { align: "r" }, cell: (c) => Number(c.getValue()).toLocaleString("vi-VN") },
    { header: "Kỳ vọng R", accessorKey: "exp_r", meta: { align: "r" }, cell: (c) => <span className={rTone(c.getValue())}>{sgn(c.getValue())}</span> },
    { header: "CI95", id: "ci", accessorFn: (r) => r.ci_lo, meta: { align: "r" }, cell: (c) => `[${sgn(c.row.original.ci_lo)}; ${sgn(c.row.original.ci_hi)}]` },
    { header: "Trước phí", accessorKey: "exp_gross", meta: { align: "r" }, cell: (c) => sgn(c.getValue()) },
    { header: "Winrate", accessorKey: "win", meta: { align: "r" }, cell: (c) => pctv(c.getValue()) },
    { header: "PF", accessorKey: "pf", meta: { align: "r" }, cell: (c) => num(c.getValue()) },
    { header: "Ngẫu nhiên", accessorKey: "baseline", meta: { align: "r" }, cell: (c) => sgn(c.getValue()) },
    { header: "p vs ngẫu nhiên", accessorKey: "p_random", meta: { align: "r" }, cell: (c) => pvn(c.getValue()) },
  ], []);
  return (
    <Async q={q} rows={6} empty="Chưa có hiện vật backtest." hint="Chạy infra/ops/bt_summary.py và bt_art.sh package." what="kết quả backtest" isEmpty={(d) => !d?.rows?.length}>
      {(d) => {
        const exs = (d.examples || []).map((e) => ({ ...e, ...parseEx(e.name) })).filter((e) => (!kb || e.kb === kb) && (!out || e.out === out));
        return (
          <div className="flex flex-col gap-3">
            <Panel title="Kết quả backtest (R, sau chi phí)" icon={FlaskConical}>
              <div className="mb-2"><Chip tone="down"><ShieldAlert size={12} aria-hidden="true" />{d.verdict}</Chip></div>
              <DataTable data={d.rows} columns={cols} minWidth={860} getRowId={(r) => r.label} empty="Không có dữ liệu." />
              <p className="m-0 mt-2 text-[12.5px]">{d.detail}</p>
              <p className="text-faint text-[11.5px] m-0 mt-1">p: xác suất một phía để vào lệnh ngẫu nhiên (cùng mã/khung/chi phí, 300 lần) đạt trung bình ≥ thật; p lớn nghĩa là không hơn ngẫu nhiên. Tập test khoá chỉ được chạy một lần, không chỉnh sau khi xem. Mẫu cũ ≠ kết quả tương lai.</p>
              {!!d.downloads?.length && (
                <div className="flex flex-wrap gap-2 mt-3" role="group" aria-label="Tải sổ lệnh">
                  {d.downloads.map((f) => (
                    <a key={f.name} className="btn" href={img(f.url)} download={f.name}><Download size={13} aria-hidden="true" className="inline mr-1 -mt-[2px]" />{f.name} <span className="text-faint">· {fsize(f.size)}</span></a>
                  ))}
                </div>
              )}
            </Panel>
            <Panel title="Biểu đồ" icon={Images}>
              <div className="sc-grid">
                {(d.charts || []).map((c) => { const t = chartTitle(c.name); const src = img(c.image); return (
                  <figure key={c.name} className="sc-fig"><Thumb src={src} alt={t} onClick={() => onZoom({ src, alt: t })} /><figcaption><div className="text-[12.5px]">{t}</div></figcaption></figure>
                ); })}
              </div>
            </Panel>
            <Panel title={`Ví dụ lệnh (${exs.length})`} icon={Images} right={
              <span className="flex flex-wrap items-center gap-2">
                <Seg value={kb} onChange={setKb} label="Lọc kịch bản" options={[{ value: "", label: "Tất cả" }, ...["KB-1", "KB-2", "KB-3", "KB-4"]]} />
                <Seg value={out} onChange={setOut} label="Lọc kết quả" options={[{ value: "", label: "Mọi kết quả" }, { value: "thang", label: "Thắng" }, { value: "thua", label: "Thua" }, { value: "te-nhat", label: "Tệ nhất" }]} />
              </span>}>
              <div className="sc-grid sc-ex">
                {exs.map((e) => { const t = `${e.kb} ${symbolLabel(e.symbol)} ${e.tf}`; const src = img(e.image); return (
                  <figure key={e.name} className="sc-fig"><Thumb src={src} alt={t} onClick={() => onZoom({ src, alt: t })} /><figcaption>
                    <div className="flex flex-wrap items-center gap-1.5"><Chip tone="ro">{e.kb}</Chip><strong>{symbolLabel(e.symbol)}</strong><Chip>{e.tf}</Chip><Chip tone={e.out === "thang" ? "up" : "down"}>{OUT[e.out] || e.out}</Chip></div>
                    <div className="text-faint text-[11.5px]">Lệnh {e.id} · ví dụ chọn ngẫu nhiên (seed cố định), không chọn ảnh đẹp</div>
                  </figcaption></figure>
                ); })}
              </div>
              {!exs.length && <EmptyState compact title="Không có ví dụ khớp bộ lọc." />}
            </Panel>
          </div>
        );
      }}
    </Async>
  );
}

// ---------- Mô tả KB ----------
function SpecTab() {
  const q = useSpec();
  return (
    <div className="flex flex-col gap-3">
      <Disclaimer>Ngưỡng chuẩn hoá theo ATR14; chỉ dùng nến đã đóng (không vẽ lại). Điểm 0–100 chỉ để xếp hạng, không phải xác suất thắng. Tham số đã hiệu chỉnh theo 3 ảnh mẫu — mẫu nhỏ, cần kiểm ngoài mẫu trước khi tin.</Disclaimer>
      <Async q={q} rows={8} empty="Chưa có mô tả kịch bản." what="mô tả kịch bản">
        {(d) => (
          <div className="sc-spec">
            {items(d).map((k) => {
              const doc = KB_DOC[kbOf(k.id)];
              const steps = Array.isArray(k.steps) ? k.steps : Object.entries(k.steps || {}).map(([id, label]) => ({ id, label }));
              const params = Object.entries(k.params || {});
              return (
                <Panel key={k.id} title={clean(k.name) || k.id} icon={BookOpenText}>
                  <div className="flex flex-col gap-3 text-[12.5px]">
                    {k.summary && <p className="m-0 text-muted">{clean(k.summary)}</p>}
                    {doc && (
                      <dl className="sc-doc">
                        <div><dt>Cấu trúc</dt><dd>{doc.struct}</dd></div>
                        <div><dt>Kích hoạt</dt><dd>{doc.trigger}</dd></div>
                        <div><dt>Huỷ</dt><dd>{doc.cancel}</dd></div>
                      </dl>
                    )}
                    <div><h3 className="sc-h3">Các bước</h3><ol className="sc-ol">{steps.map((s) => <li key={s.id}>{clean(s.label)}</li>)}</ol></div>
                    {!!k.invalidation?.length && <div><h3 className="sc-h3">Điều kiện huỷ</h3><ul className="sc-ol">{k.invalidation.map((x, i) => <li key={i}>{clean(x)}</li>)}</ul></div>}
                    {!!params.length && (
                      <details className="sc-params">
                        <summary>Tham số ({params.length})</summary>
                        <dl>{params.map(([a, b]) => <div key={a}><dt className="num">{a}</dt><dd className="num">{Array.isArray(b) ? b.join(", ") : typeof b === "object" && b ? JSON.stringify(b) : String(b)}</dd></div>)}</dl>
                      </details>
                    )}
                  </div>
                </Panel>
              );
            })}
          </div>
        )}
      </Async>
    </div>
  );
}

// ---------- Trang ----------
const TABS = [["live", "Tín hiệu hiện tại", Crosshair], ["history", "Lịch sử & paper", History], ["examples", "Thư viện ví dụ", Images], ["backtest", "Backtest", FlaskConical], ["spec", "Mô tả KB-1..KB-4", BookOpenText]];

export default function Scenarios() {
  const [tab, setTab] = useState(() => (typeof sessionStorage !== "undefined" && sessionStorage.getItem("sc.tab")) || "live");
  const [sel, setSel] = useState(null);
  const [zoom, setZoom] = useState(null);
  useEffect(() => { try { sessionStorage.setItem("sc.tab", tab); } catch { /* bỏ qua */ } }, [tab]);
  const open = (s) => setSel({ setup_id: s.setup_id, symbol: s.symbol, tf: s.tf, pattern: s.pattern });
  return (
    <>
      <PageHead title="Kịch bản Sell" sub="Theo dõi các kịch bản Sell KB-1..KB-4 khi nến đóng: setup đang hình thành/sẵn sàng/đã kích hoạt, kết quả mô phỏng (paper) và sổ cái kiểm chứng." />
      <div className="sc-banner"><Disclaimer><strong>{NOTE}</strong></Disclaimer></div>
      <Tabs.Root value={tab} onValueChange={setTab} className="flex flex-col flex-1 min-h-0 gap-3">
        <Tabs.List className="flex gap-1 overflow-x-auto shrink-0" aria-label="Mục kịch bản">
          <div className="seg">{TABS.map(([v, l, I]) => <Tabs.Trigger key={v} value={v}><I size={13} aria-hidden="true" className="inline mr-1 -mt-[2px]" />{l}</Tabs.Trigger>)}</div>
        </Tabs.List>
        <Tabs.Content value="live" className="outline-none"><LiveTab onOpen={open} /></Tabs.Content>
        <Tabs.Content value="history" className="outline-none flex flex-col gap-3"><StatsBlock /><TradesTable onOpen={open} /><HistorySetups onOpen={open} /></Tabs.Content>
        <Tabs.Content value="examples" className="outline-none"><ExamplesTab onZoom={setZoom} /></Tabs.Content>
        <Tabs.Content value="backtest" className="outline-none"><BacktestTab onZoom={setZoom} /></Tabs.Content>
        <Tabs.Content value="spec" className="outline-none"><SpecTab /></Tabs.Content>
      </Tabs.Root>
      <SetupDetail sel={sel} onClose={() => setSel(null)} onZoom={setZoom} />
      <Lightbox src={zoom?.src} alt={zoom?.alt} onClose={() => setZoom(null)} />
    </>
  );
}
