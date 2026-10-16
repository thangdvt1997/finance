// Thị trường: danh sách theo dõi nhiều nhóm + biểu đồ chuyên nghiệp (chỉ báo, vẽ, Fibonacci, tín hiệu) + tóm tắt kỹ thuật + sức mạnh tiền tệ.
// Chỉ để xem, không đặt lệnh. Bản sao có kiểm soát của components/chart/* từ web-ui.
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BellPlus, Camera, ChevronsRight, FolderPlus, Gauge, Maximize2, Minimize2, Pencil, Plus, ScanLine, Search, SlidersHorizontal, Sparkles, Star, Trash2 } from "lucide-react";
import { Async, Disclaimer, PageHead, Panel, Seg, Sheet, cn } from "../components/ui";
import { RiskBanner } from "../components/riskwin";
import { api } from "../lib/api";
import { subscribe as rtSubscribe } from "../lib/realtime";
import { useRealtimeLive } from "../lib/useLiveQuote";
import { useQuotes, useRiskSymbol, useSymbols } from "../lib/queries";
import { decimals, pct, price, signCls, symbolLabel } from "../lib/format";
import { lget, lset } from "../lib/lstore";
import { t, trName } from "../lib/i18n";
import { useWatchlists } from "../lib/watchlist";
import { strength } from "../lib/strength";
import { makeCols } from "../components/chart/indicators";
import { TOOL_BY_KEY } from "../components/chart/drawings";
import DrawToolbar from "../components/chart/DrawToolbar";
import IndicatorPanel, { DEFAULT_INDICATORS } from "../components/chart/IndicatorPanel";
import SummaryPanel from "../components/chart/SummaryPanel";
const ProChart = lazy(() => import("../components/chart/ProChart"));

const TF_SEC = { M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400, W1: 604800, MN: 2592000, MN1: 2592000 };
const KNOWN_TFS = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"];
const tfSecOf = (tf) => TF_SEC[tf] || 3600;
const TYPES = [{ value: "candles", get label() { return t("Nến"); } }, { value: "ha", label: "Heikin-Ashi" }, { value: "bars", get label() { return t("Thanh OHLC"); } }, { value: "line", get label() { return t("Đường"); } }, { value: "area", get label() { return t("Vùng"); } }];
const CFG_KEY = "tc-chart-cfg", IND_KEY = "tc-ind-v1", LAST_KEY = "tc-mkt-last";
const DEF_CFG = { type: "candles", log: false, auto: true, volume: true, signals: { on: false, kinds: ["ma", "rsi", "macd"] }, serverPivot: false, nBars: 1500, magnet: false, side: false };
const loadCfg = () => { const c = lget(CFG_KEY, {}); return { ...DEF_CFG, ...c, signals: { ...DEF_CFG.signals, ...(c.signals || {}) } }; };

const toBars = (items) => {
  const out = [];
  let prev = -1;
  for (let i = items.length - 1; i >= 0; i--) {
    const b = items[i], t = Math.floor(Date.parse(b.ts_open) / 1000);
    if (!Number.isFinite(t) || t <= prev) continue;
    prev = t;
    out.push({ t, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0, ts: b.ts_open });
  }
  return out;
};

const Ib = ({ label, active, onClick, children, text }) => (
  <button type="button" title={label} aria-label={label} aria-pressed={active} onClick={onClick}
    className={cn("inline-flex items-center justify-center gap-1.5 shrink-0 rounded-lg border border-transparent bg-transparent px-2 text-muted cursor-pointer font-[inherit] text-[13px] font-semibold hover:bg-panel2 hover:text-fg", active && "!border-line2 !bg-[var(--accent-bg)] !text-accent")}>
    {children}{text && <span>{text}</span>}
  </button>
);

function SymbolSheet({ symbols, have, onPick, onClose, title, action }) {
  const [s, setS] = useState("");
  const list = useMemo(() => {
    const t = s.trim().toLowerCase();
    return (symbols || []).filter((x) => !t || x.symbol.toLowerCase().includes(t) || (x.name || "").toLowerCase().includes(t)).slice(0, 60);
  }, [symbols, s]);
  return (
    <Sheet title={title} onClose={onClose}>
      <label className="label mb-2"><span>{t("Tìm mã hoặc tên")}</span><input className="field" value={s} onChange={(e) => setS(e.target.value)} placeholder={t("vd: EURUSD, vàng, bitcoin")} autoFocus /></label>
      {list.length === 0 ? <p className="text-muted">{t("Không có mã phù hợp.")}</p> : (
        <ul className="list-none m-0 p-0 grid">{list.map((x) => (
          <li key={x.symbol}><button className="row" onClick={() => { onPick(x.symbol); onClose(); }}>
            {action === "add" && (have.includes(x.symbol) ? <Star size={18} className="text-accent" fill="currentColor" aria-hidden="true" /> : <Plus size={18} className="text-accent" aria-hidden="true" />)}
            <span className="min-w-0 flex-1"><b>{symbolLabel(x.symbol)}</b><span className="block text-[12.5px] text-muted truncate">{trName(x.name)}</span></span>
            {x.last != null && <span className="num text-[13px]">{price(x.symbol, x.last)}</span>}</button></li>))}</ul>
      )}
    </Sheet>
  );
}

function GroupSheet({ wl, onClose }) {
  const [name, setName] = useState("");
  const [ren, setRen] = useState({});
  return (
    <Sheet title={t("Nhóm danh sách theo dõi")} onClose={onClose}>
      <ul className="list-none m-0 p-0 grid gap-2 mb-3">
        {wl.groups.map((g) => (
          <li key={g.id} className="flex items-center gap-2">
            <input className="field" aria-label={t("Tên nhóm {name}", { name: g.name })} value={ren[g.id] ?? g.name} maxLength={24} onChange={(e) => setRen({ ...ren, [g.id]: e.target.value })} onBlur={() => ren[g.id] != null && wl.renameGroup(g.id, ren[g.id])} />
            <span className="text-[12px] text-faint num w-10 text-right">{g.symbols.length}</span>
            <button className="ibtn" aria-label={t("Xoá nhóm {name}", { name: g.name })} disabled={wl.groups.length < 2} onClick={() => wl.removeGroup(g.id)}><Trash2 size={18} aria-hidden="true" /></button>
          </li>))}
      </ul>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (wl.groups.length < 8) wl.addGroup(name.trim()); setName(""); }}>
        <input className="field" placeholder={t("Tên nhóm mới")} aria-label={t("Tên nhóm mới")} value={name} maxLength={24} onChange={(e) => setName(e.target.value)} />
        <button className="btn" type="submit" disabled={wl.groups.length >= 8}><FolderPlus size={16} aria-hidden="true" /> {t("Thêm")}</button>
      </form>
      <p className="text-[12px] text-faint mt-3 mb-0">{t("Danh sách được lưu trong trình duyệt này (tối đa 8 nhóm, 40 mã mỗi nhóm).")}</p>
    </Sheet>
  );
}

function Strength({ symbols }) {
  const s = useMemo(() => strength(symbols || []), [symbols]);
  if (!s.length) return <div className="text-muted text-[13px]">{t("Chưa đủ dữ liệu biến động để tính sức mạnh tiền tệ.")}</div>;
  const mx = Math.max(...s.map((x) => Math.abs(x.v)), 0.01);
  return (
    <ul className="list-none m-0 p-0 grid gap-1.5" aria-label={t("Sức mạnh tiền tệ trong ngày")}>
      {s.map((x) => (
        <li key={x.ccy} className="grid grid-cols-[3rem_1fr_4.5rem] items-center gap-2 text-[13px]">
          <b>{x.ccy}</b>
          <div className="relative h-3 rounded bg-panel2" aria-hidden="true">
            <i className="absolute top-0 bottom-0 w-px bg-line2 left-1/2" />
            <i className="absolute top-0 bottom-0 rounded" style={{ background: x.v >= 0 ? "var(--up)" : "var(--down)", left: x.v >= 0 ? "50%" : `${50 - (Math.abs(x.v) / mx) * 50}%`, width: `${(Math.abs(x.v) / mx) * 50}%` }} />
          </div>
          <span className={cn("num text-right", signCls(x.v))}>{pct(x.v)}</span>
        </li>))}
    </ul>
  );
}

function Heat({ symbols, onPick }) {
  const items = useMemo(() => (symbols || []).filter((x) => x.change_pct != null).sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct)).slice(0, 24), [symbols]);
  if (!items.length) return <div className="text-muted text-[13px]">{t("Chưa có dữ liệu biến động.")}</div>;
  const mx = Math.max(...items.map((x) => Math.abs(x.change_pct)), 0.1);
  return (
    <div className="heat" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(84px, 1fr))" }}>
      {items.map((x) => {
        const a = 0.12 + 0.4 * (Math.abs(x.change_pct) / mx);
        return (
          <button key={x.symbol} type="button" onClick={() => onPick(x.symbol)} className="min-h-[52px] rounded-md border-0 cursor-pointer font-[inherit] text-fg px-1 grid place-items-center" aria-label={`${symbolLabel(x.symbol)} ${pct(x.change_pct)}`}
            style={{ background: `color-mix(in srgb, ${x.change_pct >= 0 ? "var(--up)" : "var(--down)"} ${Math.round(a * 100)}%, var(--panel2))` }}>
            <b className="text-[12px]">{symbolLabel(x.symbol)}</b><span className="num text-[11.5px]">{pct(x.change_pct)}</span>
          </button>);
      })}
    </div>
  );
}

export default function Market({ query }) {
  const wl = useWatchlists();
  const init = useMemo(() => { const l = lget(LAST_KEY, {}); return { symbol: query?.symbol || l.symbol || wl.group.symbols[0] || "EURUSD", tf: KNOWN_TFS.includes(query?.tf) ? query.tf : KNOWN_TFS.includes(l.tf) ? l.tf : "H1" }; }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [symbol, setSymbol] = useState(init.symbol);
  const [tf, setTf] = useState(init.tf);
  const [cfg, setCfg] = useState(loadCfg);
  const [indicators, setIndicators] = useState(() => { const l = lget(IND_KEY, null); return Array.isArray(l) ? l : DEFAULT_INDICATORS(); });
  const [tool, setTool] = useState("cursor");
  const [drawOn, setDrawOn] = useState(false);
  const [drawVisible, setDrawVisible] = useState(true);
  const [panel, setPanel] = useState({ open: false, tab: "ind", focus: null });
  const [compareSym, setCompareSym] = useState(null);
  const [full, setFull] = useState(false);
  const [sheet, setSheet] = useState(null); // add | view | groups
  const apiRef = useRef(null);
  const lastRef = useRef(null);

  useEffect(() => { lset(CFG_KEY, cfg); }, [cfg]);
  useEffect(() => { lset(IND_KEY, indicators); }, [indicators]);
  useEffect(() => { lset(LAST_KEY, { symbol, tf }); }, [symbol, tf]);

  const syms = useSymbols();
  const info = useMemo(() => new Map((syms.data || []).map((s) => [s.symbol, s])), [syms.data]);
  const si = info.get(symbol);
  const quotes = useQuotes(wl.group.symbols);
  const qmap = useMemo(() => new Map((quotes.data || []).map((x) => [x.symbol, x])), [quotes.data]);
  const selQuote = useQuotes([symbol]);
  const sq = selQuote.data?.[0];

  const rtLive = useRealtimeLive();
  const barsQ = useQuery({
    queryKey: ["bars-pro", symbol, tf, cfg.nBars],
    queryFn: ({ signal }) => api("/bars", { symbol, tf, limit: cfg.nBars, order: "desc" }, signal),
    refetchInterval: rtLive ? 180_000 : 60_000, staleTime: 10_000, enabled: !!symbol,
  });
  const bars = useMemo(() => toBars(barsQ.data?.items || []), [barsQ.data]);
  const cmpQ = useQuery({
    queryKey: ["bars-pro", compareSym, tf, cfg.nBars],
    queryFn: ({ signal }) => api("/bars", { symbol: compareSym, tf, limit: cfg.nBars, order: "desc" }, signal),
    staleTime: 30_000, enabled: !!compareSym && compareSym !== symbol,
  });
  const compare = useMemo(() => (compareSym && cmpQ.data ? { symbol: compareSym, bars: toBars(cmpQ.data.items || []) } : null), [compareSym, cmpQ.data]);
  const anQ = useQuery({
    queryKey: ["an-sym", symbol, tf],
    queryFn: ({ signal }) => api(`/analytics/symbol/${encodeURIComponent(symbol)}`, { tf }, signal),
    retry: false, staleTime: 60_000, refetchInterval: 120_000, enabled: !!symbol,
  });
  const server = anQ.data?.tfs?.[tf] || null;
  const risk = useRiskSymbol(symbol);
  const rkData = useMemo(() => (risk.data ? { symbols: [risk.data] } : null), [risk.data]);
  const dec = si?.precision ?? decimals(symbol);
  const tfSec = tfSecOf(tf);
  const cols = useMemo(() => makeCols(bars), [bars]);
  const availableTfs = useMemo(() => { const have = si?.tfs?.length ? KNOWN_TFS.filter((t) => si.tfs.includes(t)) : KNOWN_TFS.slice(0, 7); return have.length ? have : KNOWN_TFS; }, [si]);
  useEffect(() => { if (!availableTfs.includes(tf)) setTf(availableTfs.includes("H1") ? "H1" : availableTfs[0]); }, [availableTfs, tf]);

  // nến cuối chạy theo giá mới nhất (poll 15 giây)
  useEffect(() => { lastRef.current = bars.length ? { ...bars[bars.length - 1] } : null; }, [bars]);
  useEffect(() => {
    const px = sq?.bid ?? sq?.ask;
    const l = lastRef.current;
    if (px == null || !l || tfSec > 86400) return;
    const t = Math.floor(new Date(sq.ts || Date.now()).getTime() / 1000);
    if (t < l.t) return;
    lastRef.current = t >= l.t + tfSec ? { t: l.t + Math.floor((t - l.t) / tfSec) * tfSec, o: px, h: px, l: px, c: px, v: 0 } : { ...l, h: Math.max(l.h, px), l: Math.min(l.l, px), c: px };
    apiRef.current?.updateLast(lastRef.current);
  }, [sq, tfSec]);

  // rt: nến đang hình thành do máy chủ dựng (c:SYM:TF) -> thay nến cuối (không setState, không re-render trang)
  useEffect(() => {
    if (!symbol || !/^(M1|M5|M15|H1|H4|D1)$/.test(tf)) return undefined;
    return rtSubscribe(`c:${symbol}:${tf}`, (c) => {
      const l = lastRef.current;
      if (!c || typeof c.t !== "number" || c.c == null || !l) return;
      const t = Math.floor(c.t / 1000);
      if (t < l.t) return;
      lastRef.current = { t, o: c.o, h: c.h, l: c.l, c: c.c, v: c.v || 0 };
      apiRef.current?.updateLast(lastRef.current);
    });
  }, [symbol, tf]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.defaultPrevented || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      const a = apiRef.current;
      if (e.key === "Escape") { if (a?.cancel()) return; if (panel.open) setPanel((p) => ({ ...p, open: false })); else if (full) setFull(false); return; }
      if (e.key === "Delete") a?.removeSelected();
      const k = e.key.toLowerCase();
      if (drawOn && TOOL_BY_KEY[k]) setTool((c) => (c === TOOL_BY_KEY[k] ? "cursor" : TOOL_BY_KEY[k]));
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [panel.open, full, drawOn]);

  const onIndAction = (act, id) => {
    if (act === "toggle") setIndicators((l) => l.map((x) => (x.id === id ? { ...x, visible: !x.visible } : x)));
    else if (act === "remove") setIndicators((l) => l.filter((x) => x.id !== id));
    else if (act === "edit") setPanel({ open: true, tab: "ind", focus: id });
  };
  const pick = (s) => { setSymbol(s); setCompareSym((c) => (c === s ? null : c)); };
  const lastBar = bars[bars.length - 1], prevBar = bars[bars.length - 2];
  const bid = sq?.bid ?? lastBar?.c;
  const chg = si?.change_pct ?? (lastBar && prevBar ? ((bid - prevBar.c) / prevBar.c) * 100 : null);
  const inGroup = wl.group.symbols.includes(symbol);

  return (
    <>
      <PageHead title={t("Thị trường")} sub={t("Danh sách theo dõi, biểu đồ nến với chỉ báo, công cụ vẽ và tóm tắt kỹ thuật. Chỉ để xem, không đặt lệnh.")} />

      <Panel title={t("Danh sách theo dõi")} icon={Star} pad={false}
        right={<><button className="btn sm" onClick={() => setSheet("add")}><Plus size={16} aria-hidden="true" /> {t("Thêm mã")}</button><button className="ibtn" onClick={() => setSheet("groups")} aria-label={t("Quản lý nhóm")}><Pencil size={17} aria-hidden="true" /></button></>}>
        <div className="p-2 grid gap-2">
          <Seg value={wl.group.id} onChange={wl.setActive} options={wl.groups.map((g) => ({ value: g.id, label: `${g.name} · ${g.symbols.length}` }))} label={t("Nhóm danh sách")} scroll />
          {wl.group.symbols.length === 0 ? <p className="m-0 text-muted text-[13px] px-1">{t("Nhóm này trống. Bấm “Thêm mã” để thêm.")}</p> : (
            <ul className="hscroll list-none m-0 p-0" aria-label={t("Mã theo dõi")}>
              {wl.group.symbols.map((s) => {
                const x = info.get(s), qq = qmap.get(s), px = qq?.bid ?? x?.last;
                return (
                  <li key={s}>
                    <button type="button" aria-pressed={symbol === s} onClick={() => pick(s)}
                      className={cn("min-h-[60px] min-w-[104px] text-left rounded-xl border px-3 py-1.5 cursor-pointer font-[inherit] text-fg", symbol === s ? "border-[var(--accent)] bg-[var(--accent-bg)]" : "border-line bg-panel2")}>
                      <div className="font-semibold text-[13.5px]">{symbolLabel(s)}</div>
                      <div className="num text-[12.5px]">{px != null ? price(s, px) : "—"}</div>
                      <div className={cn("num text-[11.5px]", signCls(x?.change_pct))}>{x?.change_pct != null ? pct(x.change_pct) : "—"}</div>
                    </button>
                  </li>);
              })}
            </ul>
          )}
        </div>
      </Panel>

      <RiskBanner data={rkData} who={symbolLabel(symbol)} />

      <section className={cn("panel cw", full && "cw-full")} aria-label={t("Biểu đồ {symbol}", { symbol: symbolLabel(symbol) })}>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-3 py-2">
          <button type="button" className={cn("ibtn", inGroup && "!text-accent")} aria-pressed={inGroup} aria-label={inGroup ? t("Bỏ {symbol} khỏi nhóm {group}", { symbol: symbolLabel(symbol), group: wl.group.name }) : t("Thêm {symbol} vào nhóm {group}", { symbol: symbolLabel(symbol), group: wl.group.name })}
            onClick={() => (inGroup ? wl.remove(symbol) : wl.add(symbol))}><Star size={18} fill={inGroup ? "currentColor" : "none"} aria-hidden="true" /></button>
          <button type="button" onClick={() => setSheet("view")} className="min-w-0 text-left bg-transparent border-0 text-fg cursor-pointer p-0 font-[inherit] min-h-[44px]" aria-label={t("Đổi mã đang xem")}>
            <h2 className="m-0 truncate text-[16px] font-semibold leading-tight">{symbolLabel(symbol)} <span className="text-[12px] font-normal text-faint">· {tf}</span> <Search size={13} className="inline text-faint" aria-hidden="true" /></h2>
            <div className="truncate text-[11.5px] leading-tight text-faint">{trName(si?.name) || t("Chạm để đổi mã")}</div>
          </button>
          <div className="flex items-baseline gap-2">
            <span className="num text-[22px] leading-none">{price(symbol, bid)}</span>
            <span className={cn("num text-[13px]", signCls(chg))}>{chg != null ? pct(chg) : ""}</span>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <a className="btn sm" aria-label={t("Cảnh báo giá")} title={t("Cảnh báo giá")} href={`#/canh-bao?symbol=${encodeURIComponent(symbol)}`}><BellPlus size={16} aria-hidden="true" /><span className="hide-mobile"> {t("Cảnh báo giá")}</span></a>
          </div>
        </div>

        <div className="hscroll border-b border-line px-2 py-1.5 items-center" role="toolbar" aria-label={t("Thanh công cụ biểu đồ")}>
          <Seg value={tf} onChange={setTf} options={availableTfs} label={t("Khung thời gian")} scroll />
          <select className="field !w-auto" aria-label={t("Loại biểu đồ")} value={cfg.type} onChange={(e) => setCfg((c) => ({ ...c, type: e.target.value }))}>
            {TYPES.map((ty) => <option key={ty.value} value={ty.value}>{ty.label}</option>)}
          </select>
          <Ib label={t("Các chỉ báo")} active={panel.open && panel.tab === "ind"} onClick={() => setPanel((p) => ({ open: !(p.open && p.tab === "ind"), tab: "ind", focus: null }))} text={t("Chỉ báo {n}", { n: indicators.filter((x) => x.visible).length })}><SlidersHorizontal size={16} aria-hidden="true" /></Ib>
          <Ib label={t("Bật hoặc tắt tín hiệu kỹ thuật")} active={cfg.signals.on} onClick={() => setCfg((c) => ({ ...c, signals: { ...c.signals, on: !c.signals.on } }))} text={t("Tín hiệu")}><Sparkles size={16} aria-hidden="true" /></Ib>
          <Ib label={t("Công cụ vẽ và Fibonacci")} active={drawOn} onClick={() => { setDrawOn((v) => !v); setTool("cursor"); }} text={t("Vẽ")}><Pencil size={16} aria-hidden="true" /></Ib>
          <Ib label={t("So sánh hai mã, thang log, số nến")} active={panel.open && panel.tab !== "ind"} onClick={() => setPanel((p) => ({ open: !(p.open && p.tab !== "ind"), tab: "view", focus: null }))} text={compareSym ? `vs ${symbolLabel(compareSym)}` : t("Hiển thị")}><Activity size={16} aria-hidden="true" /></Ib>
          <Ib label={t("Vừa toàn bộ dữ liệu")} onClick={() => apiRef.current?.fit()}><ScanLine size={17} aria-hidden="true" /></Ib>
          <Ib label={t("Về nến mới nhất")} onClick={() => { apiRef.current?.zoomRecent(); apiRef.current?.toEnd(); }}><ChevronsRight size={17} aria-hidden="true" /></Ib>
          <Ib label={t("Chụp ảnh biểu đồ")} onClick={() => apiRef.current?.screenshot()}><Camera size={17} aria-hidden="true" /></Ib>
          <Ib label={full ? t("Thoát toàn màn hình (Esc)") : t("Toàn màn hình")} active={full} onClick={() => setFull((f) => !f)}>{full ? <Minimize2 size={17} aria-hidden="true" /> : <Maximize2 size={17} aria-hidden="true" />}</Ib>
        </div>

        <div className="cw-body">
          {drawOn && <DrawToolbar tool={tool} setTool={setTool} magnet={cfg.magnet} setMagnet={(v) => setCfg((c) => ({ ...c, magnet: v }))} visible={drawVisible} setVisible={setDrawVisible}
            onUndo={() => apiRef.current?.undo()} onClear={() => { if (window.confirm(t("Xoá toàn bộ hình vẽ của mã/khung này?"))) apiRef.current?.clearAll(); }} />}
          <div className="cw-canvas">
            <Suspense fallback={<div className="mkt-state" role="status">{t("Đang tải biểu đồ…")}</div>}>
              <ProChart apiRef={apiRef} symbol={symbol} tf={tf} tfSec={tfSec} bars={bars} decimals={dec} cfg={cfg} indicators={indicators} serverTf={server}
                compare={compare} tool={tool} magnet={cfg.magnet} drawVisible={drawVisible} onToolDone={() => setTool("cursor")} onIndicatorAction={onIndAction} />
            </Suspense>
            {barsQ.isPending && <div className="mkt-state" role="status">{t("Đang tải nến {symbol} {tf}…", { symbol: symbolLabel(symbol), tf })}</div>}
            {barsQ.isError && <div className="mkt-state text-down" role="alert">{t("Không tải được nến.")} <button className="btn ml-2" onClick={() => barsQ.refetch()}>{t("Thử lại")}</button></div>}
            {!barsQ.isPending && !barsQ.isError && !bars.length && <div className="mkt-state">{t("Chưa có nến {tf} cho {symbol}. Thử khung khác.", { tf, symbol: symbolLabel(symbol) })}</div>}
            <IndicatorPanel open={panel.open} onClose={() => setPanel((p) => ({ ...p, open: false }))} tab={panel.tab} setTab={(t) => setPanel((p) => ({ ...p, tab: t }))} focusId={panel.focus}
              indicators={indicators} setIndicators={setIndicators} cfg={cfg} setCfg={setCfg} symbols={syms.data} compareSym={compareSym} setCompareSym={setCompareSym}
              nBars={cfg.nBars} setNBars={(n) => setCfg((c) => ({ ...c, nBars: n }))} />
          </div>
        </div>
        <p className="m-0 px-3 py-1.5 text-[11.5px] text-faint border-t border-line">{t("Chụm hai ngón để thu phóng, kéo để di chuyển. Khi bật “Vẽ”: chọn công cụ rồi chạm lần lượt các điểm; kéo điểm tròn để chỉnh. Hình vẽ lưu theo từng mã và khung trên thiết bị này.")}</p>
      </section>

      <div className="cols-2">
        <Panel title={t("Tóm tắt kỹ thuật")} icon={Gauge}>
          <SummaryPanel cols={cols} tf={tf} symbol={symbol} decimals={dec} server={server} serverQ={anQ} serverPivot={cfg.serverPivot} onTogglePivot={() => setCfg((c) => ({ ...c, serverPivot: !c.serverPivot }))} />
        </Panel>
        <div className="grid gap-[.85rem] content-start min-w-0">
          <Panel title={t("Sức mạnh tiền tệ hôm nay")} icon={Activity}><Strength symbols={syms.data} /></Panel>
          <Panel title={t("Bản đồ nhiệt biến động")} icon={Activity}>
            <Async q={syms} rows={3} isEmpty={() => false}>{() => <Heat symbols={syms.data} onPick={(s) => { pick(s); window.scrollTo({ top: 0, behavior: "smooth" }); }} />}</Async>
          </Panel>
        </div>
      </div>
      <Disclaimer>{t("Dữ liệu và phân tích chỉ mang tính tham khảo, không phải khuyến nghị đầu tư. Hệ thống không đặt, sửa hay đóng lệnh.")}</Disclaimer>
      {sheet === "add" && <SymbolSheet title={t("Thêm vào “{group}”", { group: wl.group.name })} action="add" symbols={syms.data} have={wl.group.symbols} onPick={(s) => { wl.add(s); pick(s); }} onClose={() => setSheet(null)} />}
      {sheet === "view" && <SymbolSheet title={t("Xem mã")} symbols={syms.data} have={wl.group.symbols} onPick={pick} onClose={() => setSheet(null)} />}
      {sheet === "groups" && <GroupSheet wl={wl} onClose={() => setSheet(null)} />}
    </>
  );
}
