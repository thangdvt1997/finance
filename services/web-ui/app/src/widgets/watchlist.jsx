import { Fragment, useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Columns3, ListOrdered, X } from "lucide-react";
import { api } from "../lib/api";
import { classOf, CLASS_LABEL, CLASSES } from "../lib/assetClass";
import { useWatchSymbols } from "../lib/prefs";
import { useNow, useSymbols } from "../lib/queries";
import { useStream } from "../lib/stream";
import { useRtQuoteFeed } from "../lib/rtbridge";
import { toMs, freshness, marketClosed, ageText, FRESH } from "../lib/freshness";
import { pct, price, signCls, symbolLabel } from "../lib/format";
import { Sparkline, Skeleton, cn } from "../components/ui";
import { paced } from "../terminal/hooks";
import { Popover, SymbolInput, useWidget } from "../terminal/ui";

export const meta = {
  id: "watchlist", title: "Bảng giá", icon: ListOrdered, group: "Thị trường", linkable: true,
  desc: "Bảng giá nâng cao: cột tuỳ chọn (giá, %, spread, H/L, khối lượng, sparkline, RSI, xu hướng, độ mới), nhóm, sắp xếp, cờ màu, kéo thả thứ tự.",
  defaultSize: { w: 9, h: 16 }, minSize: { w: 5, h: 6 },
  configSchema: [
    { key: "src", label: "Nguồn danh sách", type: "select", default: "all", options: [{ value: "all", label: "Mọi mã" }, { value: "group", label: "Nhóm theo dõi đang chọn (chung)" }, { value: "class", label: "Theo loại tài sản" }, { value: "custom", label: "Danh sách riêng của widget" }] },
    { key: "cls", label: "Loại tài sản (khi chọn “Theo loại”)", type: "select", default: "forex", options: [{ value: "forex", label: "Forex" }, { value: "crypto", label: "Tiền ảo" }, { value: "commodity", label: "Kim loại & hàng hoá" }, { value: "index", label: "Chỉ số & ETF" }, { value: "us", label: "Cổ phiếu Mỹ" }, { value: "vn", label: "Cổ phiếu VN" }, { value: "bond", label: "Trái phiếu" }] },
    { key: "symbols", label: "Danh sách riêng", type: "symbols", default: [] },
    { key: "cols", label: "Cột hiển thị", type: "multi", default: ["price", "chg", "spread", "spark", "trend"], options: [{ value: "price", label: "Giá" }, { value: "ask", label: "Ask" }, { value: "spread", label: "Spread" }, { value: "chg", label: "% 48h" }, { value: "hl", label: "H/L 24h" }, { value: "vol", label: "Khối lượng 24h" }, { value: "spark", label: "Sparkline" }, { value: "rsi", label: "RSI 14" }, { value: "trend", label: "Xu hướng" }, { value: "age", label: "Độ mới" }] },
    { key: "grp", label: "Nhóm theo loại tài sản", type: "bool", default: false },
    { key: "dense", label: "Hàng gọn", type: "bool", default: false },
  ],
};

const COLS = [
  ["price", "Giá", "r"], ["ask", "Ask", "r"], ["spread", "Spread", "r"], ["chg", "% 48h", "r"], ["hl", "H/L 24h", "r"], ["vol", "KL 24h", "r"],
  ["spark", "48h", "r"], ["rsi", "RSI", "r"], ["trend", "XH", "r"], ["age", "Mới", "r"],
];
const SORTABLE = new Set(["name", "price", "chg", "rsi", "vol"]);
const PREFER = ["EURUSD", "XAUUSD", "CRYPTO:BTCUSDT", "BTCUSDT", "VN:VNM", "VN:VCB", "US:AAPL"];
const FLAGS = ["", "#ff5c7a", "#f0b84f", "#2bd08f", "#5aa9ff"];
const compact = (n) => (n == null ? "—" : n >= 1e9 ? `${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(Math.round(n)));

function rsi(c, n = 14) {
  if (c.length <= n) return null;
  let g = 0, l = 0;
  for (let i = 1; i <= n; i++) { const d = c[i] - c[i - 1]; if (d >= 0) g += d; else l -= d; }
  g /= n; l /= n;
  for (let i = n + 1; i < c.length; i++) { const d = c[i] - c[i - 1]; g = (g * (n - 1) + Math.max(d, 0)) / n; l = (l * (n - 1) + Math.max(-d, 0)) / n; }
  return l === 0 ? 100 : 100 - 100 / (1 + g / l);
}
const ema = (c, n) => { if (c.length < n) return null; const k = 2 / (n + 1); let e = c.slice(0, n).reduce((a, b) => a + b, 0) / n; for (let i = n; i < c.length; i++) e = c[i] * k + e * (1 - k); return e; };

function derive(items) {
  const bars = [...(items || [])].reverse();
  if (bars.length < 2) return null;
  const closes = bars.map((b) => b.c);
  const last24 = bars.slice(-24);
  const e9 = ema(closes, 9), e21 = ema(closes, 21);
  return {
    closes, change: ((closes[closes.length - 1] - closes[0]) / closes[0]) * 100,
    hi: Math.max(...last24.map((b) => b.h ?? b.c)), lo: Math.min(...last24.map((b) => b.l ?? b.c)),
    vol: last24.reduce((s, b) => s + (b.v || 0), 0), rsi: rsi(closes),
    trend: e9 != null && e21 != null ? (e9 > e21 * 1.00005 ? 1 : e9 < e21 * 0.99995 ? -1 : 0) : null,
  };
}

function useDerived(symbols, enabled) {
  const res = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ["spark", s], enabled,
      queryFn: ({ signal }) => paced(() => api("/bars", { symbol: s, tf: "H1", limit: 48, order: "desc" }, signal)),
      staleTime: 60_000, refetchInterval: 120_000,
    })),
  });
  return useMemo(() => Object.fromEntries(symbols.map((s, i) => [s, { d: derive(res[i].data?.items), loading: res[i].isPending && enabled }])), [res.map((r) => r.dataUpdatedAt).join(","), symbols.join(","), enabled]); // eslint-disable-line react-hooks/exhaustive-deps
}

function Row({ s, cols, d, loading, q, now, sel, onSel, flag, onFlag, dense, drag, onRemove }) {
  const px = q?.bid ?? q?.ask;
  const spread = q?.bid != null && q?.ask != null ? q.ask - q.bid : null;
  const sp = spread == null ? "—" : s.startsWith("VN:") || s.startsWith("US:") || /^(CRYPTO|XAU|XAG)/.test(s) ? spread.toFixed(2) : s.includes("JPY") ? (spread * 100).toFixed(1) : (spread * 10000).toFixed(1);
  const fr = cols.includes("age") ? freshness({ ts: q?.ts, nowMs: now, closed: marketClosed(s, now), ...FRESH.quote }) : null;
  const flash = q?.dir > 0 ? "tick-up" : q?.dir < 0 ? "tick-down" : "";
  const py = dense ? "!py-[2px]" : "";
  return (
    <tr aria-selected={sel} onClick={onSel} {...drag}>
      <td className={cn("!pr-1 !pl-2 w-[22px]", py)}>
        <button type="button" className="tm-flag" style={{ background: flag || "transparent", borderColor: flag || undefined }} aria-label={`Cờ màu cho ${symbolLabel(s)}`}
          onClick={(e) => { e.stopPropagation(); onFlag(); }} />
      </td>
      <td className={py}>
        <button type="button" className="font-semibold bg-transparent border-0 p-0 text-fg cursor-pointer text-left" onClick={(e) => { e.stopPropagation(); onSel(); }}>{symbolLabel(s)}</button>
      </td>
      {cols.includes("price") && <td className={cn("r", py)}><span key={q?.tickId} className={cn("num px-1 rounded-sm inline-block", flash, q?.dir > 0 ? "up" : q?.dir < 0 ? "down" : "")}>{price(s, px)}</span></td>}
      {cols.includes("ask") && <td className={cn("r num text-muted", py)}>{price(s, q?.ask)}</td>}
      {cols.includes("spread") && <td className={cn("r num text-faint", py)}>{sp}</td>}
      {cols.includes("chg") && <td className={cn("r num", signCls(d?.change), py)}>{loading ? "…" : pct(d?.change)}</td>}
      {cols.includes("hl") && <td className={cn("r num text-[11.5px] leading-tight", py)}>{d ? <><span className="up">{price(s, d.hi)}</span><br /><span className="down">{price(s, d.lo)}</span></> : "—"}</td>}
      {cols.includes("vol") && <td className={cn("r num text-muted", py)}>{d ? compact(d.vol) : "—"}</td>}
      {cols.includes("spark") && <td className={cn("r", py)}><Sparkline values={d?.closes} width={64} height={dense ? 18 : 24} /></td>}
      {cols.includes("rsi") && <td className={cn("r num", d?.rsi >= 70 ? "down" : d?.rsi <= 30 ? "up" : "text-muted", py)} title="RSI ≥ 70 quá mua, ≤ 30 quá bán">{d?.rsi == null ? "—" : d.rsi.toFixed(0)}</td>}
      {cols.includes("trend") && <td className={cn("r", py)}>{d?.trend == null ? "—" : <span className={d.trend > 0 ? "up" : d.trend < 0 ? "down" : "text-muted"} title="EMA9 so với EMA21 (H1)">{d.trend > 0 ? "▲" : d.trend < 0 ? "▼" : "●"}</span>}</td>}
      {cols.includes("age") && <td className={cn("r text-[11px]", fr?.level === "ok" ? "up" : fr?.level === "warn" ? "text-accent" : fr?.level === "stale" ? "down" : "text-faint", py)}>{fr?.level === "idle" ? "nghỉ" : fr?.ageS == null ? "—" : ageText(fr.ageS).replace(" trước", "")}</td>}
      <td className={cn("!px-1 w-[22px]", py)}>{onRemove && <button type="button" className="tm-ib tm-rm !w-5 !h-5 opacity-0" aria-label={`Bỏ ${symbolLabel(s)}`} onClick={(e) => { e.stopPropagation(); onRemove(); }}><X size={12} /></button>}</td>
    </tr>
  );
}

export default function WatchlistWidget() {
  const { config, setConfig, symbol, setSymbol, size, channel } = useWidget();
  const all = useSymbols();
  const groupSyms = useWatchSymbols();
  const st = useStream();
  const now = useNow(2000);
  const [dragFrom, setDragFrom] = useState(null);
  const [over, setOver] = useState(null);
  const cols = COLS.map((c) => c[0]).filter((k) => (config.cols || []).includes(k)); // thứ tự chuẩn của cột (khớp thứ tự dựng ô)
  const narrow = size.w > 0 && size.w < 340;
  const shown = narrow ? cols.filter((c) => ["price", "chg"].includes(c)) : cols;
  const sort = config.sort || "";
  const flags = config.flags || {};

  const infoBy = useMemo(() => Object.fromEntries((all.data || []).map((s) => [s.symbol, s])), [all.data]);
  const base = useMemo(() => {
    if (config.src === "group") return groupSyms;
    if (config.src === "custom") return config.symbols || [];
    const list = (all.data || []).map((s) => s.symbol);
    return config.src === "class" ? list.filter((s) => classOf(infoBy[s] || s) === config.cls) : list;
  }, [config.src, config.cls, config.symbols, groupSyms, all.data, infoBy]);
  const needBars = shown.some((c) => ["chg", "hl", "vol", "spark", "rsi", "trend"].includes(c)) || ["chg", "rsi", "vol"].includes(sort.split(":")[0]);
  const limited = useMemo(() => base.slice(0, 60), [base]);
  const dv = useDerived(limited, needBars);
  useRtQuoteFeed(limited); // giá đẩy từ /api/v1/rt (legacy stream vẫn là dự phòng)

  const val = (s, k) => {
    if (k === "name") return symbolLabel(s);
    const q = st.quotes.get(s);
    if (k === "price") return q?.bid ?? q?.ask ?? null;
    const d = dv[s]?.d;
    return k === "chg" ? d?.change ?? null : k === "rsi" ? d?.rsi ?? null : k === "vol" ? d?.vol ?? null : null;
  };
  const rows = useMemo(() => {
    let r = [...limited];
    const [k, dir] = sort.split(":");
    if (k && SORTABLE.has(k)) {
      const m = Number(dir) || 1;
      r.sort((a, b) => { const x = val(a, k), y = val(b, k); if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (typeof x === "string" ? x.localeCompare(y) : x - y) * m; });
    }
    if (config.grp) {
      const order = CLASSES.map((c) => c.id);
      const cl = (s) => classOf(infoBy[s] || s);
      r = r.map((s, i) => [s, i]).sort((a, b) => order.indexOf(cl(a[0])) - order.indexOf(cl(b[0])) || a[1] - b[1]).map((x) => x[0]);
    }
    return r;
  }, [limited, sort, config.grp, infoBy, st.version, dv]); // eslint-disable-line react-hooks/exhaustive-deps

  // gắn kênh màu mà chưa có mã chung: chọn mã tiêu biểu của danh sách để các widget cùng kênh (biểu đồ, tin…) có dữ liệu ngay
  useEffect(() => {
    if (!channel || symbol || !rows.length) return;
    setSymbol(PREFER.find((p) => rows.includes(p)) || rows[0]);
  }, [channel, symbol, rows.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggleSort = (k) => {
    const [cur, dir] = sort.split(":");
    setConfig({ sort: cur !== k ? `${k}:${k === "name" ? 1 : -1}` : dir === "-1" ? `${k}:1` : dir === "1" && k !== "name" ? undefined : k === "name" && dir === "1" ? `${k}:-1` : undefined });
  };
  const custom = config.src === "custom";
  const canDrag = custom && !sort && !config.grp;
  const move = (from, to) => {
    if (from == null || to == null || from === to) return;
    const arr = [...(config.symbols || [])]; const [m] = arr.splice(from, 1); arr.splice(to, 0, m);
    setConfig({ symbols: arr });
  };
  const flagOf = (s) => FLAGS[Number(flags[s]) || 0] || "";
  const cycleFlag = (s) => { const n = ((Number(flags[s]) || 0) + 1) % FLAGS.length; const f = { ...flags }; if (n) f[s] = n; else delete f[s]; setConfig({ flags: Object.keys(f).length ? f : undefined }); };
  const header = (k, label, cls) => {
    const sortable = SORTABLE.has(k);
    const [ck, cd] = sort.split(":");
    return (
      <th key={k} className={cls} aria-sort={ck === k ? (cd === "1" ? "ascending" : "descending") : undefined}>
        {sortable ? <button type="button" onClick={() => toggleSort(k)}>{label}{ck === k && (cd === "1" ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}</button> : label}
      </th>
    );
  };

  if (all.isPending && config.src !== "custom") return <div className="tm-pad"><Skeleton rows={8} /></div>;
  let lastGrp = null;
  return (
    <div className="tm-fill">
      <div className="flex items-center gap-1.5 px-2 py-1 border-b border-line shrink-0 tm-nodrag">
        <select className="field !h-6 !text-[11.5px] !px-1.5 min-w-0 flex-1 max-w-[190px]" aria-label="Nguồn danh sách" value={config.src} onChange={(e) => setConfig({ src: e.target.value })}>
          <option value="all">Mọi mã</option><option value="group">Nhóm theo dõi chung</option><option value="class">Theo loại tài sản</option><option value="custom">Danh sách riêng</option>
        </select>
        {config.src === "class" && (
          <select className="field !h-6 !text-[11.5px] !px-1.5 min-w-0" aria-label="Loại tài sản" value={config.cls} onChange={(e) => setConfig({ cls: e.target.value })}>
            {CLASSES.map((c) => <option key={c.id} value={c.id}>{CLASS_LABEL[c.id]}</option>)}
          </select>
        )}
        <span className="tm-sub ml-auto whitespace-nowrap">{rows.length} mã</span>
        <Popover label="Chọn cột" width={210} trigger={(p) => <button type="button" {...p} className="tm-ib" aria-label="Chọn cột hiển thị" title="Cột hiển thị"><Columns3 size={14} /></button>}>
          {() => (
            <div className="p-2 grid gap-1">
              {COLS.map(([k, l]) => (
                <label key={k} className="flex items-center gap-2 text-[12.5px] cursor-pointer h-7">
                  <input type="checkbox" checked={cols.includes(k)} onChange={(e) => setConfig({ cols: COLS.map((c) => c[0]).filter((c) => (c === k ? e.target.checked : cols.includes(c))) })} /> {l}
                </label>
              ))}
              <label className="flex items-center gap-2 text-[12.5px] cursor-pointer h-7 border-t border-line pt-1"><input type="checkbox" checked={!!config.grp} onChange={(e) => setConfig({ grp: e.target.checked })} /> Nhóm theo loại</label>
              <label className="flex items-center gap-2 text-[12.5px] cursor-pointer h-7"><input type="checkbox" checked={!!config.dense} onChange={(e) => setConfig({ dense: e.target.checked })} /> Hàng gọn</label>
            </div>
          )}
        </Popover>
      </div>
      <div className="tm-scroll">
        {rows.length === 0 ? (
          <div className="tm-pad text-muted text-[12.5px]">{custom ? "Danh sách riêng đang trống. Nhập mã ở dưới để thêm." : "Không có mã phù hợp."}</div>
        ) : (
          <table className="tm-tbl">
            <thead>
              <tr>
                <th className="!w-[22px] !px-1" aria-label="Cờ" />
                {header("name", "Mã")}
                {shown.map((k) => { const c = COLS.find((x) => x[0] === k); return header(k, c[1], c[2]); })}
                <th className="!w-[22px] !px-1" aria-label="Xoá" />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const g = config.grp ? classOf(infoBy[s] || s) : null;
                const head = g && g !== lastGrp ? (lastGrp = g) : null;
                const idx = (config.symbols || []).indexOf(s);
                return (
                  <FragmentRow key={s} head={head && CLASS_LABEL[head]} span={shown.length + 3}>
                    <Row s={s} cols={shown} d={dv[s]?.d} loading={dv[s]?.loading} q={st.quotes.get(s)} now={now} sel={symbol === s} onSel={() => setSymbol(s)}
                      flag={flagOf(s)} onFlag={() => cycleFlag(s)} dense={config.dense} onRemove={custom ? () => setConfig({ symbols: (config.symbols || []).filter((x) => x !== s) }) : null}
                      drag={canDrag ? { draggable: true, onDragStart: () => setDragFrom(idx), onDragOver: (e) => { e.preventDefault(); setOver(idx); }, onDragEnd: () => { setDragFrom(null); setOver(null); }, onDrop: () => { move(dragFrom, idx); setDragFrom(null); setOver(null); }, className: over === idx && dragFrom !== idx ? "tm-dragover" : undefined } : {}} />
                  </FragmentRow>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      {custom && (
        <div className="px-2 py-1.5 border-t border-line shrink-0 tm-nodrag">
          <SymbolInput className="!h-7 w-full !text-[12px]" placeholder="+ Thêm mã (gõ tên rồi Enter)" label="Thêm mã vào danh sách riêng"
            onChange={(s) => { const cur = config.symbols || []; if (!cur.includes(s) && cur.length < 60) setConfig({ symbols: [...cur, s] }); }} />
        </div>
      )}
    </div>
  );
}

function FragmentRow({ head, span, children }) {
  return (
    <Fragment>
      {head && <tr className="tm-grp"><td colSpan={span}>{head}</td></tr>}
      {children}
    </Fragment>
  );
}
