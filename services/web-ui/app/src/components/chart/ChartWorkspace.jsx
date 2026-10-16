// Không gian biểu đồ chuyên nghiệp: nhiều biểu đồ (1, 2 dọc/ngang, 2x2, 1+3, 3x2) có đồng bộ crosshair / vùng thời gian / mã+khung theo nhóm màu,
// thanh công cụ, replay, mẫu (template), cây đối tượng, đa khung, ảnh chụp, toàn màn hình, phím tắt kiểu TradingView.
// Dùng độc lập (widget) hoặc trong trang Thị trường. Mỗi ô độc lập hoặc liên kết với ô cùng nhóm màu.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Camera, ChevronsRight, ClipboardCopy, Gauge, History, Keyboard, LayoutGrid, Link2, Maximize2, Minimize2, ScanLine, SlidersHorizontal, Sparkles, Star, X } from "lucide-react";
import { Freshness, Seg, cn } from "../ui";
import { Dialog } from "../dialog";
import { FRESH } from "../../lib/freshness";
import { useSymbols, useNow } from "../../lib/queries";
import { useQuote } from "../../lib/stream";
import { decimals, price, pct, signCls, symbolLabel, dateTime } from "../../lib/format";
import { lget, lset } from "../../lib/lstore";
import { CLASS_LABEL, classOf } from "../../lib/assetClass";
import { TFS } from "../../lib/api";
import ChartCell from "./ChartCell";
import { SymbolPicker } from "./ChartParts";
import DrawToolbar from "./DrawToolbar";
import IndicatorPanel, { DEFAULT_INDICATORS } from "./IndicatorPanel";
import SummaryPanel from "./SummaryPanel";
import MtfPanel from "./MtfPanel";
import { ObjectsTab, TemplatesTab, ViewTab } from "./ChartPanels";
import { makeCols } from "./indicators";
import { TOOL_BY_ALT, TOOL_BY_KEY } from "./drawings";
import { KNOWN_TFS, tfSecOf } from "./chartData";
import { deleteTemplate, saveTemplate, useChartPrefs, useTemplates } from "./chartPrefs";
import "./chartws.css";

const WS_KEY = "ts-ws-v2";
const LAYOUTS = [["1", "1 biểu đồ", 1], ["2v", "2 biểu đồ xếp dọc", 2], ["2h", "2 biểu đồ cạnh nhau", 2], ["2x2", "4 biểu đồ (2×2)", 4], ["1+3", "1 lớn + 3 nhỏ", 4], ["3x2", "6 biểu đồ (3×2)", 6]];
const LAYOUT_N = Object.fromEntries(LAYOUTS.map(([k, , n]) => [k, n]));
const FILL_TFS = ["H1", "H4", "D1", "M15", "M5", "M1"];
const DEF_CFG = { type: "candles", log: false, auto: true, volume: true, signals: { on: false, kinds: ["ma", "rsi", "macd"] }, serverPivot: false, nBars: 1500, side: false, style: {}, sessions: { on: false, ids: ["tokyo", "london", "newyork"], lines: true }, prevClose: false, dayOpen: false, pct: false, events: false, eventsAll: false, news: false, alerts: true, boxSize: 0, corr: false };
const uid = () => Math.random().toString(36).slice(2, 8);
const CFG_KEYS = ["type", "log", "auto", "volume", "signals", "serverPivot", "style", "sessions", "prevClose", "dayOpen", "pct", "events", "eventsAll", "news", "alerts", "boxSize", "corr", "corrWin"];
const normCfg = (c) => ({ ...DEF_CFG, ...c, signals: { ...DEF_CFG.signals, ...(c?.signals || {}) }, sessions: { ...DEF_CFG.sessions, ...(c?.sessions || {}) } });
const mkCell = (o) => ({ id: uid(), symbol: "EURUSD", tf: "H1", grp: null, cmp: null, cfg: normCfg({}), ind: DEFAULT_INDICATORS(), ...o });

function parseArg(arg) {
  const [s, qs] = String(arg || "").split("?");
  const tf = new URLSearchParams(qs || "").get("tf");
  return { symbol: s ? decodeURIComponent(s) : null, tf: KNOWN_TFS.includes(tf) ? tf : null };
}
function loadWs(initialSymbol, initialTf, storageKey) {
  const saved = lget(storageKey, null);
  if (saved && Array.isArray(saved.cells) && saved.cells.length && LAYOUT_N[saved.layout]) {
    const ws = { ...saved, cells: saved.cells.slice(0, 6).map((c) => mkCell({ ...c, cfg: normCfg(c.cfg), ind: Array.isArray(c.ind) ? c.ind : DEFAULT_INDICATORS() })) };
    ws.active = Math.max(0, Math.min(ws.cells.length - 1, ws.active || 0));
    if (initialSymbol) ws.cells[ws.active] = { ...ws.cells[ws.active], symbol: initialSymbol, tf: initialTf || ws.cells[ws.active].tf };
    return ws;
  }
  // chuyển từ cấu hình cũ (một biểu đồ)
  const last = lget("ts-mkt-last", {});
  const ind = lget("ts-ind-v1", null);
  const c0 = mkCell({ symbol: initialSymbol || last.symbol || "EURUSD", tf: initialTf || (KNOWN_TFS.includes(last.tf) ? last.tf : "H1"), cfg: normCfg(lget("ts-chart-cfg", {})), ind: Array.isArray(ind) ? ind : DEFAULT_INDICATORS() });
  return { layout: "1", cells: [c0], active: 0, sync: { crosshair: true, range: false, tf: false }, magnet: lget("ts-chart-cfg", {}).magnet === true };
}

const Ib = ({ label, active, onClick, children, className, disabled }) => (
  <button type="button" title={label} aria-label={label} aria-pressed={active} disabled={disabled}
    className={cn("inline-flex h-8 min-w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent px-1.5 text-muted hover:bg-panel2 hover:text-fg disabled:cursor-default disabled:opacity-40",
      active && "!border-line2 !bg-[var(--accent-bg)] !text-accent", className)} onClick={onClick}>{children}</button>
);

function Menu({ label, icon, children, active, title }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const key = (e) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } };
    document.addEventListener("pointerdown", away, true); document.addEventListener("keydown", key, true);
    return () => { document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", key, true); };
  }, [open]);
  return (
    <div className="relative shrink-0" ref={ref}>
      <button type="button" className={cn("btn !h-8", (open || active) && "!border-[var(--accent)] text-accent")} aria-haspopup="true" aria-expanded={open} title={title || label} onClick={() => setOpen((o) => !o)}>{icon}<span className="hidden md:inline">{label}</span></button>
      {open && <div className="absolute left-0 top-9 z-50 min-w-[220px] rounded-md border border-line2 bg-panel p-2 shadow-xl">{typeof children === "function" ? children(() => setOpen(false)) : children}</div>}
    </div>
  );
}

export default function ChartWorkspace({ initialSymbol, initialTf, request, onActive, favs, onToggleFav, storageKey = WS_KEY, className, title, embedded }) {
  const [ws, setWs] = useState(() => loadWs(initialSymbol, initialTf, storageKey));
  const [tool, setTool] = useState("cursor");
  const [drawVisible, setDrawVisible] = useState(true);
  const [alertMode, setAlertMode] = useState(false);
  const [panel, setPanel] = useState({ open: false, tab: "ind", focus: null });
  const [full, setFull] = useState(false);
  const [help, setHelp] = useState(false);
  const [side, setSide] = useState(false);
  const [picker, setPicker] = useState(false);
  const [stats, setStats] = useState({});
  const [drawings, setDrawings] = useState([]);
  const [hist, setHist] = useState({ undo: false, redo: false });
  const [replaying, setReplaying] = useState({});
  const [toast, setToast] = useState("");
  const [lockAll, setLockAll] = useState(false);
  const now = useNow(5000);
  const syms = useSymbols();
  const prefs = useChartPrefs();
  const templates = useTemplates();
  const refs = useRef(new Map());
  const replayCtl = useRef({});
  const wsRef = useRef(ws);
  wsRef.current = ws;
  const cell = ws.cells[ws.active] || ws.cells[0];
  const symbol = cell.symbol, tf = cell.tf;

  useEffect(() => { lset(storageKey, ws); }, [ws, storageKey]);
  useEffect(() => { lset("ts-mkt-last", { symbol, tf }); onActive?.({ symbol, tf, cell }); }, [symbol, tf]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!toast) return undefined; const id = setTimeout(() => setToast(""), 3500); return () => clearTimeout(id); }, [toast]);

  // yêu cầu bên ngoài (chọn mã ở danh sách / điều hướng #/thi-truong/XAUUSD?tf=H4)
  useEffect(() => {
    if (!request?.symbol) return;
    patchCell(wsRef.current.cells[wsRef.current.active].id, { symbol: request.symbol, ...(request.tf ? { tf: request.tf } : {}) });
  }, [request?.symbol, request?.tf, request?.n]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- hub đồng bộ giữa các ô ----
  const hub = useMemo(() => ({
    register: (id, ref) => refs.current.set(id, ref),
    unregister: (id) => refs.current.delete(id),
    crosshair: (from, t) => {
      if (!wsRef.current.sync.crosshair || wsRef.current.cells.length < 2) return;
      for (const [id, r] of refs.current) if (id !== from) { if (t == null) r.current?.clearCrosshair(); else r.current?.setCrosshair(t); }
    },
    range: (from, rg) => {
      if (!wsRef.current.sync.range || wsRef.current.cells.length < 2) return;
      for (const [id, r] of refs.current) if (id !== from) r.current?.setRange(rg);
    },
  }), []);
  const activeApi = () => refs.current.get(wsRef.current.cells[wsRef.current.active]?.id)?.current;

  // ---- sửa ô: mã/khung đồng bộ theo nhóm màu ----
  const patchCell = useCallback((id, patch) => setWs((w) => {
    const target = w.cells.find((c) => c.id === id);
    if (!target) return w;
    const grp = patch.grp !== undefined ? patch.grp : target.grp;
    const prop = {};
    if (patch.symbol !== undefined) prop.symbol = patch.symbol;
    if (patch.tf !== undefined && w.sync.tf) prop.tf = patch.tf;
    return { ...w, cells: w.cells.map((c) => (c.id === id ? { ...c, ...patch } : grp && c.grp === grp && Object.keys(prop).length ? { ...c, ...prop } : c)) };
  }), []);
  const patchCfg = useCallback((fn) => setWs((w) => ({ ...w, cells: w.cells.map((c, i) => (i === w.active ? { ...c, cfg: typeof fn === "function" ? fn(c.cfg) : fn } : c)) })), []);
  const setIndicators = useCallback((fn) => setWs((w) => ({ ...w, cells: w.cells.map((c, i) => (i === w.active ? { ...c, ind: typeof fn === "function" ? fn(c.ind) : fn } : c)) })), []);
  const setCmp = useCallback((cmp) => setWs((w) => ({ ...w, cells: w.cells.map((c, i) => (i === w.active ? { ...c, cmp } : c)) })), []);
  const setLayout = (layout) => setWs((w) => {
    const n = LAYOUT_N[layout], base = w.cells[w.active];
    let cells = w.cells.slice(0, n);
    const used = new Set(cells.map((c) => c.tf));
    while (cells.length < n) {
      const tfx = FILL_TFS.find((t) => !used.has(t)) || base.tf;
      used.add(tfx);
      cells.push(mkCell({ symbol: base.symbol, tf: tfx, cfg: JSON.parse(JSON.stringify(base.cfg)), ind: base.ind.map((x) => ({ ...x, id: uid() })), grp: base.grp }));
    }
    return { ...w, layout, cells, active: Math.min(w.active, cells.length - 1) };
  });
  const activate = useCallback((id) => setWs((w) => { const i = w.cells.findIndex((c) => c.id === id); return i < 0 || i === w.active ? w : { ...w, active: i }; }), []);
  const setSync = (p) => setWs((w) => ({ ...w, sync: { ...w.sync, ...p } }));

  const info = syms.data?.find((s) => s.symbol === symbol);
  const tfsOf = useCallback((sym) => {
    const inf = syms.data?.find((s) => s.symbol === sym);
    const have = inf?.tfs?.length ? KNOWN_TFS.filter((t) => inf.tfs.includes(t)) : TFS;
    return have.length ? have : TFS;
  }, [syms.data]);
  const availableTfs = useMemo(() => tfsOf(symbol), [tfsOf, symbol]);
  useEffect(() => { if (availableTfs.length && !availableTfs.includes(tf)) patchCell(cell.id, { tf: availableTfs.includes("H1") ? "H1" : availableTfs[0] }); }, [availableTfs, tf]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- danh sách bản vẽ của ô hoạt động ----
  useEffect(() => { const a = activeApi(); setDrawings(a?.drawings.list() ? [...a.drawings.list()] : []); setHist({ undo: false, redo: false }); }, [ws.active, ws.layout]); // eslint-disable-line react-hooks/exhaustive-deps
  const onDrawings = useCallback((l) => setDrawings([...l]), []);
  const dapi = activeApi()?.drawings;

  const shared = useMemo(() => ({
    tool, magnet: ws.magnet, drawVisible, tfsOf, tfs: availableTfs,
    onToolDone: () => setTool("cursor"),
    registerReplay: (id, ctl) => { replayCtl.current[id] = ctl; setReplaying((r) => (r[id] === ctl.active() ? r : { ...r, [id]: ctl.active() })); },
  }), [tool, ws.magnet, drawVisible, tfsOf, availableTfs]);

  const indAction = (id, act, indId) => {
    setWs((w) => ({ ...w, cells: w.cells.map((c) => (c.id !== id ? c : { ...c, ind: act === "toggle" ? c.ind.map((x) => (x.id === indId ? { ...x, visible: !x.visible } : x)) : act === "remove" ? c.ind.filter((x) => x.id !== indId) : c.ind }))}));
    if (act === "edit") setPanel({ open: true, tab: "ind", focus: indId });
  };

  // ---- ảnh chụp ----
  const shot = () => activeApi()?.screenshot();
  const copyShot = async () => { const ok = await activeApi()?.copyImage(); setToast(ok ? "Đã sao chép ảnh biểu đồ vào clipboard." : "Trình duyệt không cho sao chép ảnh; hãy dùng nút tải ảnh."); };

  // ---- mẫu ----
  const saveTpl = (name, withWs) => {
    const w = wsRef.current, c = w.cells[w.active];
    const cfg = {};
    for (const k of CFG_KEYS) if (c.cfg[k] !== undefined) cfg[k] = c.cfg[k];
    const tpl = { name, cfg, ind: c.ind.map(({ id, ...rest }) => rest) }; // eslint-disable-line no-unused-vars
    if (withWs) tpl.ws = { layout: w.layout, cells: w.cells.map((x) => ({ symbol: x.symbol, tf: x.tf, type: x.cfg.type, grp: x.grp })) };
    const ok = saveTemplate(tpl);
    setToast(ok === false ? "Mẫu vượt giới hạn dung lượng máy chủ: đã lưu cục bộ." : `Đã lưu mẫu "${name}".`);
  };
  const applyTpl = (t) => {
    setWs((w) => {
      let cells = w.cells, layout = w.layout, active = w.active;
      if (t.ws?.cells?.length) {
        layout = LAYOUT_N[t.ws.layout] ? t.ws.layout : "1";
        cells = t.ws.cells.slice(0, LAYOUT_N[layout]).map((x) => mkCell({ symbol: x.symbol || w.cells[0].symbol, tf: x.tf, grp: x.grp, cfg: normCfg({ ...t.cfg, type: x.type || t.cfg?.type }), ind: (t.ind || []).map((i) => ({ ...i, id: uid() })) }));
        active = Math.min(w.active, cells.length - 1);
      } else {
        cells = w.cells.map((c, i) => (i === w.active ? { ...c, cfg: normCfg({ ...c.cfg, ...t.cfg }), ind: (t.ind || []).map((x) => ({ ...x, id: uid() })) } : c));
      }
      return { ...w, cells, layout, active };
    });
    setToast(`Đã áp dụng mẫu "${t.name}".`);
  };

  // ---- phím tắt ----
  useEffect(() => {
    const onKey = (e) => {
      if (e.defaultPrevented || e.isComposing) return;
      const t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      const a = activeApi();
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && !e.altKey) {
        if (k === "z") { e.preventDefault(); if (e.shiftKey) a?.redo(); else a?.undo(); }
        else if (k === "y") { e.preventDefault(); a?.redo(); }
        else if (k === "d") { e.preventDefault(); a?.duplicateSelected(); }
        return;
      }
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        if (k === "a") { e.preventDefault(); setAlertMode((v) => !v); return; }
        if (TOOL_BY_ALT[k]) { e.preventDefault(); setAlertMode(false); setTool((c) => (c === TOOL_BY_ALT[k] ? "cursor" : TOOL_BY_ALT[k])); }
        return;
      }
      if (e.key === "Escape") {
        if (a?.cancel()) return;
        if (alertMode) { setAlertMode(false); return; }
        if (panel.open) setPanel((p) => ({ ...p, open: false })); else if (full) setFull(false);
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") { a?.removeSelected(); return; }
      if (e.shiftKey && k === "r") { e.preventDefault(); replayCtl.current[wsRef.current.cells[wsRef.current.active].id]?.toggle(); return; }
      if (e.shiftKey && k === "f") { e.preventDefault(); setFull((f) => !f); return; }
      if (e.shiftKey && e.key === "ArrowRight") { a?.toEnd(); return; }
      if (e.shiftKey) return;
      if (TOOL_BY_KEY[k]) { e.preventDefault(); setTool((c) => (c === TOOL_BY_KEY[k] ? "cursor" : TOOL_BY_KEY[k])); return; }
      if (k === "n") setWs((w) => ({ ...w, magnet: !w.magnet }));
      else if (k === "l") patchCfg((c) => ({ ...c, log: !c.log, pct: false }));
      else if (k === "i") setPanel((p) => ({ open: !(p.open && p.tab === "ind"), tab: "ind", focus: null }));
      else if (k === "s") patchCfg((c) => ({ ...c, signals: { ...c.signals, on: !c.signals.on } }));
      else if (k === "p") setSide((v) => !v);
      else if (k === "z") a?.fit();
      else if (e.key === "," || e.key === ".") {
        const i = availableTfs.indexOf(tf), j = Math.max(0, Math.min(availableTfs.length - 1, i + (e.key === "." ? 1 : -1)));
        patchCell(wsRef.current.cells[wsRef.current.active].id, { tf: availableTfs[j] });
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [availableTfs, tf, panel.open, full, alertMode, patchCfg, patchCell]); // eslint-disable-line react-hooks/exhaustive-deps

  const q = useQuote(symbol);
  const dec = decimals(symbol);
  const lastBar = stats.last, prevBar = stats.prev;
  const bid = q?.bid ?? lastBar?.c;
  const chg = lastBar && prevBar ? ((bid - prevBar.c) / prevBar.c) * 100 : null;
  const isFav = !!favs?.includes(symbol);
  const klass = CLASS_LABEL[classOf(info || { symbol })];
  const cols = useMemo(() => (side ? makeCols(stats.bars || []) : null), [side, stats.bars]);
  const barThr = (t) => { const sec = tfSecOf(t); return { warnAfterS: sec * 2 + 60, staleAfterS: sec * 4 + 300 }; };
  const rep = replaying[cell.id];
  const multi = ws.cells.length > 1;

  const extra = {
    tabs: [["view", "Hiển thị"], ["obj", "Đối tượng"], ["tpl", "Mẫu"], ["mtf", "Đa khung"]],
    render: (tab) => (tab === "view" ? <ViewTab cfg={cell.cfg} patchCfg={patchCfg} symbols={syms.data} cmp={cell.cmp} setCmp={setCmp} symbol={symbol} />
      : tab === "obj" ? <ObjectsTab drawings={drawings} dapi={dapi} indicators={cell.ind} setIndicators={setIndicators} activeId={dapi?.selectedId?.()} />
      : tab === "tpl" ? <TemplatesTab templates={templates} onSave={saveTpl} onApply={applyTpl} onDelete={(n) => { deleteTemplate(n); setToast(`Đã xoá mẫu "${n}".`); }} onImport={(t) => saveTemplate(t)} serverOk={prefs.loaded && prefs.available} status={prefs.status} />
      : <MtfPanel symbol={symbol} availableTfs={availableTfs} activeTf={tf} onPickTf={(t) => patchCell(cell.id, { tf: t })} />),
  };
  const openTab = (tab) => setPanel((p) => ({ open: !(p.open && p.tab === tab), tab, focus: null }));

  return (
    <section className={cn("panel mkt-chart", embedded && "ws-embedded", full && "mkt-full", className)} aria-label={title || `Biểu đồ ${symbolLabel(symbol)}`}>
      {/* Dải giá */}
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-3 py-1.5">
        {onToggleFav && <button type="button" className={cn("grid h-7 w-7 cursor-pointer place-items-center rounded border-0 bg-transparent", isFav ? "text-accent" : "text-faint hover:text-muted")}
          aria-pressed={isFav} aria-label={isFav ? "Bỏ yêu thích" : "Thêm vào yêu thích"} onClick={() => onToggleFav(symbol)}><Star size={15} fill={isFav ? "currentColor" : "none"} /></button>}
        <div className="min-w-0">
          <h2 className="m-0 truncate text-[15px] font-semibold leading-tight"><button type="button" className="cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-inherit hover:text-accent" onClick={() => setPicker(true)} title="Đổi mã" aria-label={`Đổi mã, đang là ${symbolLabel(symbol)}`}>{stats.label || symbolLabel(symbol)}</button> <span className="text-[12px] font-normal text-faint">· {tf}</span></h2>
          <div className="truncate text-[11px] leading-tight text-faint">{info?.name ? `${info.name} · ` : ""}{klass}</div>
        </div>
        <div className="flex items-baseline gap-2">
          <span className={cn("num text-[20px] leading-none", q?.dir > 0 ? "up" : q?.dir < 0 ? "down" : "")}>{price(symbol, bid)}</span>
          <span className={cn("num text-[12.5px]", signCls(chg))} title="So với nến liền trước">{pct(chg)}</span>
        </div>
        <dl className="m-0 hidden items-center gap-x-4 text-[11.5px] sm:flex">
          <div><dt className="inline text-faint">Ask </dt><dd className="num m-0 inline">{price(symbol, q?.ask)}</dd></div>
          <div><dt className="inline text-faint">Cao </dt><dd className="num m-0 inline">{price(symbol, stats.hi)}</dd></div>
          <div><dt className="inline text-faint">Thấp </dt><dd className="num m-0 inline">{price(symbol, stats.lo)}</dd></div>
          {stats.count ? <div title="Số nến đang nạp (kéo sang trái để tải thêm)"><dt className="inline text-faint">Nến </dt><dd className="num m-0 inline">{stats.count.toLocaleString("en-US")}{stats.loadingMore ? "…" : ""}</dd></div> : null}
        </dl>
        <div className="ml-auto hidden items-center gap-2 text-[11.5px] text-faint xl:flex">
          <span className="inline-flex items-center gap-1">Nến <Freshness compact now={now} ts={lastBar?.ts} source={lastBar?.src} symbol={symbol} label={`Nến ${tf} (${dateTime(lastBar?.ts)})`} {...barThr(tf)} /></span>
          <span className="inline-flex items-center gap-1">Tick <Freshness compact now={now} ts={q?.ts} source={q?.source} symbol={symbol} {...FRESH.quote} /></span>
        </div>
      </div>

      {/* Thanh công cụ */}
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-line px-2 py-1" role="toolbar" aria-label="Thanh công cụ biểu đồ">
        <Menu label="Bố cục" icon={<LayoutGrid size={14} aria-hidden="true" />} title="Bố cục nhiều biểu đồ" active={multi}>
          {(close) => (
            <div className="grid gap-2">
              <div className="grid grid-cols-3 gap-1.5" role="group" aria-label="Chọn bố cục">
                {LAYOUTS.map(([k, l]) => (
                  <button key={k} type="button" title={l} aria-label={l} aria-pressed={ws.layout === k} className={cn("grid cursor-pointer place-items-center rounded border border-line bg-panel2 p-2 text-muted hover:text-fg", ws.layout === k && "!border-[var(--accent)] text-accent")} onClick={() => { setLayout(k); close(); }}>
                    <span className="ws-lay" data-l={k}>{Array.from({ length: LAYOUT_N[k] }).map((_, i) => <i key={i} />)}</span>
                  </button>
                ))}
              </div>
              <div className="grid gap-1 border-t border-line pt-2 text-[12.5px]">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-faint">Đồng bộ giữa các ô</span>
                <label className="flex cursor-pointer items-center gap-2"><input type="checkbox" checked={ws.sync.crosshair} onChange={(e) => setSync({ crosshair: e.target.checked })} /> Crosshair</label>
                <label className="flex cursor-pointer items-center gap-2"><input type="checkbox" checked={ws.sync.range} onChange={(e) => setSync({ range: e.target.checked })} /> Vùng thời gian (cuộn/zoom)</label>
                <label className="flex cursor-pointer items-center gap-2" title="Ô cùng nhóm màu cũng đổi khung theo"><input type="checkbox" checked={ws.sync.tf} onChange={(e) => setSync({ tf: e.target.checked })} /> Khung thời gian theo nhóm màu</label>
                <p className="m-0 text-[11px] text-faint"><Link2 size={11} className="mr-1 inline" />Chấm màu ở đầu mỗi ô = nhóm liên kết: đổi mã ở một ô sẽ đổi mã cho mọi ô cùng màu.</p>
              </div>
            </div>
          )}
        </Menu>
        <Seg value={tf} onChange={(t) => patchCell(cell.id, { tf: t })} options={availableTfs} label="Khung thời gian" className="shrink-0" />
        <select className="field !h-8 shrink-0" aria-label="Loại biểu đồ" value={cell.cfg.type} onChange={(e) => patchCfg((c) => ({ ...c, type: e.target.value }))}>
          {[["Cơ bản", ["candles", "hollow", "ha", "bars", "line", "area", "baseline", "columns"]], ["Không theo thời gian", ["renko", "range", "linebreak", "kagi", "pnf"]]].map(([g, ids]) => (
            <optgroup key={g} label={g}>{ids.map((v) => <option key={v} value={v}>{{ candles: "Nến", hollow: "Nến rỗng", ha: "Heikin-Ashi", bars: "Thanh OHLC", line: "Đường", area: "Vùng (Area)", baseline: "Baseline", columns: "Cột", renko: "Renko", range: "Range bars", linebreak: "Line Break", kagi: "Kagi", pnf: "Point & Figure" }[v]}</option>)}</optgroup>
          ))}
        </select>
        <button type="button" className={cn("btn shrink-0 !h-8", panel.open && panel.tab === "ind" && "!border-[var(--accent)] text-accent")} aria-pressed={panel.open && panel.tab === "ind"} onClick={() => openTab("ind")}>
          <SlidersHorizontal size={14} aria-hidden="true" /> Chỉ báo <span className="num text-[11px] text-faint">{cell.ind.filter((x) => x.visible).length}</span>
        </button>
        <button type="button" className={cn("btn shrink-0 !h-8", cell.cfg.signals.on && "!border-[var(--accent)] text-accent")} aria-pressed={cell.cfg.signals.on} title="Bật/tắt tín hiệu (S) · chuột phải để chọn loại"
          onClick={() => patchCfg((c) => ({ ...c, signals: { ...c.signals, on: !c.signals.on } }))} onContextMenu={(e) => { e.preventDefault(); setPanel({ open: true, tab: "sig", focus: null }); }}>
          <Sparkles size={14} aria-hidden="true" /> <span className="hidden sm:inline">Tín hiệu</span>
        </button>
        <button type="button" className={cn("btn shrink-0 !h-8", panel.open && panel.tab === "view" && "!border-[var(--accent)] text-accent")} aria-pressed={panel.open && panel.tab === "view"} title="Hiển thị, phiên, lịch/tin, so sánh, spread" onClick={() => openTab("view")}>
          <Activity size={14} aria-hidden="true" /> {cell.cmp ? <span className="text-info">vs {symbolLabel(cell.cmp.symbol)}</span> : <span className="hidden sm:inline">Hiển thị</span>}
        </button>
        <span className="mx-1 h-5 w-px shrink-0 bg-line" />
        <Ib label="Thang logarit (L)" active={cell.cfg.log} onClick={() => patchCfg((c) => ({ ...c, log: !c.log, pct: false }))}><span className="text-[11.5px] font-semibold">log</span></Ib>
        <Ib label="Thang phần trăm" active={cell.cfg.pct} onClick={() => patchCfg((c) => ({ ...c, pct: !c.pct, log: false }))}><span className="text-[11.5px] font-semibold">%</span></Ib>
        <Ib label="Tự động co giãn trục giá" active={cell.cfg.auto !== false} onClick={() => patchCfg((c) => ({ ...c, auto: c.auto === false }))}><span className="text-[11.5px] font-semibold">auto</span></Ib>
        <Ib label="Vừa toàn bộ dữ liệu (Z)" onClick={() => activeApi()?.fit()}><ScanLine size={15} aria-hidden="true" /></Ib>
        <Ib label="Về nến mới nhất (Shift+→)" onClick={() => { activeApi()?.zoomRecent(); activeApi()?.toEnd(); }}><ChevronsRight size={15} aria-hidden="true" /></Ib>
        <Ib label="Chụp ảnh biểu đồ (tải PNG)" onClick={shot}><Camera size={15} aria-hidden="true" /></Ib>
        <Ib label="Sao chép ảnh biểu đồ vào clipboard" onClick={copyShot}><ClipboardCopy size={15} aria-hidden="true" /></Ib>
        <Ib label="Replay: phát lại nến để nghiên cứu (Shift+R)" active={!!rep} onClick={() => replayCtl.current[cell.id]?.toggle()} className="!gap-1"><History size={15} aria-hidden="true" /><span className="hidden text-[12px] lg:inline">Replay</span></Ib>
        <Ib label="Mẫu: lưu / áp dụng / nhập xuất JSON" active={panel.open && panel.tab === "tpl"} onClick={() => openTab("tpl")} className="!gap-1"><span className="text-[12px]">Mẫu</span></Ib>
        <Ib label="Đa khung thời gian (M15/H1/H4/D1)" active={panel.open && panel.tab === "mtf"} onClick={() => openTab("mtf")} className="!gap-1"><span className="text-[12px]">MTF</span></Ib>
        <span className="ml-auto" />
        <Ib label="Tóm tắt kỹ thuật (P)" active={side} onClick={() => setSide((v) => !v)} className="!gap-1"><Gauge size={15} aria-hidden="true" /><span className="hidden text-[12px] md:inline">Tóm tắt</span></Ib>
        <Ib label="Phím tắt biểu đồ" onClick={() => setHelp(true)}><Keyboard size={15} aria-hidden="true" /></Ib>
        <Ib label={full ? "Thoát toàn màn hình (Esc)" : "Toàn màn hình (Shift+F)"} active={full} onClick={() => setFull((f) => !f)}>{full ? <Minimize2 size={15} aria-hidden="true" /> : <Maximize2 size={15} aria-hidden="true" />}</Ib>
      </div>

      {/* Thân: thanh vẽ | lưới biểu đồ | tóm tắt */}
      <div className="mkt-body">
        <DrawToolbar tool={tool} setTool={(t) => { setAlertMode(false); setTool(t); }} magnet={ws.magnet} setMagnet={(v) => setWs((w) => ({ ...w, magnet: v }))} visible={drawVisible} setVisible={setDrawVisible}
          onUndo={() => activeApi()?.undo()} onRedo={() => activeApi()?.redo()} canUndo={hist.undo} canRedo={hist.redo}
          onClear={() => { if (window.confirm("Xoá toàn bộ hình vẽ của mã/khung này?")) activeApi()?.clearAll(); }}
          onTree={() => openTab("obj")} treeOpen={panel.open && panel.tab === "obj"} alertMode={alertMode} onAlertMode={() => { setTool("cursor"); setAlertMode((v) => !v); }}
          lockAll={lockAll} onLockAll={() => { const nv = !lockAll; setLockAll(nv); const a = activeApi(); (a?.drawings.list() || []).forEach((d) => a.drawings.patch(d.id, { locked: nv })); }} />
        <div className="mkt-canvas">
          <div className="ws-grid" data-layout={ws.layout}>
            {ws.cells.map((c, i) => (
              <ChartCell key={c.id} cell={c} active={i === ws.active} solo={ws.cells.length === 1} symbols={syms.data} shared={shared} hub={hub}
                onActivate={activate} onPatch={patchCell} onStats={setStats} alertMode={alertMode} onAlertMode={setAlertMode} onDrawings={onDrawings} onHistory={setHist} indAction={indAction} />
            ))}
          </div>
          <IndicatorPanel open={panel.open} onClose={() => setPanel((p) => ({ ...p, open: false }))} tab={panel.tab} setTab={(t) => setPanel((p) => ({ ...p, tab: t }))} focusId={panel.focus}
            indicators={cell.ind} setIndicators={setIndicators} cfg={cell.cfg} setCfg={patchCfg} symbols={syms.data} compareSym={cell.cmp?.symbol || null} setCompareSym={() => {}}
            nBars={cell.cfg.nBars} setNBars={(n) => patchCfg((c) => ({ ...c, nBars: n }))} extra={extra} />
          {toast && <div className="absolute left-1/2 top-2 z-40 -translate-x-1/2 rounded-md border border-line2 bg-panel/95 px-3 py-1.5 text-[12.5px] shadow-lg" role="status">{toast}</div>}
        </div>
        {side && (
          <aside className="mkt-side" aria-label="Tóm tắt kỹ thuật">
            <button type="button" aria-label="Đóng tóm tắt" className="absolute right-2 top-2 z-[1] grid h-7 w-7 cursor-pointer place-items-center rounded-md border-0 bg-transparent text-muted hover:text-fg" onClick={() => setSide(false)}><X size={15} /></button>
            <SummaryPanel cols={cols} tf={tf} symbol={symbol} decimals={dec} server={stats.server} serverQ={stats.serverQ} serverPivot={cell.cfg.serverPivot}
              onTogglePivot={() => patchCfg((c) => ({ ...c, serverPivot: !c.serverPivot }))} />
          </aside>
        )}
      </div>

      <SymbolPicker open={picker} onClose={() => setPicker(false)} symbols={syms.data} onPick={(s) => patchCell(cell.id, { symbol: s })} />
      <Dialog open={help} onClose={() => setHelp(false)} title="Phím tắt biểu đồ" description="Không hoạt động khi đang gõ trong ô nhập liệu.">
        <div className="grid gap-x-6 gap-y-1 p-3 text-[13px] sm:grid-cols-2">
          {[["Alt+T / D", "Đường xu hướng"], ["Alt+H / H", "Đường ngang"], ["Alt+V / V", "Đường dọc"], ["Alt+F / F", "Fibonacci thoái lui"], ["Alt+R / R", "Hình chữ nhật"], ["Alt+C / C", "Kênh song song"],
            ["Alt+X / X", "Fibonacci mở rộng"], ["Alt+M / M", "Thước đo"], ["Alt+P", "Pitchfork Andrews"], ["Alt+G", "Gann fan"], ["Alt+K", "Kênh hồi quy"], ["Alt+U / Alt+J", "Vùng cung / cầu"],
            ["Alt+W", "Mũi tên"], ["Alt+B", "Nhãn văn bản"], ["Alt+L", "Ghi chú"], ["Alt+A", "Đặt cảnh báo giá (chỉ báo, không đặt lệnh)"], ["Alt+A rồi bấm giá", "Tạo cảnh báo tại mức giá"],
            ["N", "Nam châm (bắt OHLC)"], ["Esc", "Huỷ / bỏ chọn / thoát"], ["Del", "Xoá hình đang chọn"], ["Ctrl+Z", "Hoàn tác"], ["Ctrl+Shift+Z / Ctrl+Y", "Làm lại"], ["Ctrl+D", "Nhân bản hình"],
            ["I", "Bảng chỉ báo"], ["S", "Bật/tắt tín hiệu"], ["L", "Thang logarit"], ["P", "Tóm tắt kỹ thuật"], ["Z", "Vừa toàn bộ dữ liệu"], [", / .", "Khung trước / sau"],
            ["Shift+→", "Về nến mới nhất"], ["Shift+R", "Replay (Space phát/dừng, ←/→ bước nến)"], ["Shift+F", "Toàn màn hình"]].map(([k, l]) => (
            <div key={k + l} className="flex items-center justify-between gap-3 py-[3px]"><span>{l}</span><kbd className="num shrink-0 rounded border border-line2 bg-panel2 px-1.5 py-px text-[11px]">{k}</kbd></div>
          ))}
        </div>
        <p className="m-0 border-t border-line p-3 text-[11.5px] text-muted">Vẽ: chọn công cụ rồi bấm lần lượt các điểm (chạm nhiều lần trên điện thoại). Kéo điểm tròn để chỉnh, kéo thân để di chuyển. Hình vẽ lưu theo từng mã và khung, đồng bộ lên tài khoản (máy chủ) khi sẵn sàng, luôn có bản sao trong trình duyệt.</p>
      </Dialog>
    </section>
  );
}
