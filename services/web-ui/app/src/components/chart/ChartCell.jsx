// Một ô biểu đồ: tự tải nến (phân trang lịch sử tới 20.000 nến khi kéo trái), realtime, replay, so sánh/spread/ratio, mốc lịch HIGH + tin,
// đường cảnh báo giá, rồi giao cho ProChart. Trạng thái (mã/khung/chỉ báo/kiểu) do ChartWorkspace giữ và truyền xuống.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiWrite } from "../../lib/api";
import { onBar, onTick } from "../../lib/stream";
import { subscribe as rtSubscribe } from "../../lib/realtime";
import { decimals, dateTime, symbolLabel, clean } from "../../lib/format";
import { buildPayload, emptyForm, newCond, ruleToIn, useRules } from "../../lib/rules";
import { cn } from "../ui";
import ProChart from "./ProChart";
import { AlertPopover, ReplayBar, SymbolPicker } from "./ChartParts";
import { MAX_BARS_TOTAL, eventRelevant, mergeBars, tfSecOf, toBars } from "./chartData";
import { combineBars } from "./charttypes";

export const LINK_COLORS = { red: "#ff5c7a", blue: "#5aa9ff", green: "#2bd08f", yellow: "#f0b84f" };
const lowerIdx = (bars, t) => {
  let lo = 0, hi = bars.length - 1;
  if (hi < 0) return -1;
  if (t <= bars[0].t) return 0;
  if (t >= bars[hi].t) return hi;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (bars[m].t <= t) lo = m; else hi = m; }
  return lo;
};

export default function ChartCell({ cell, active, solo, symbols, shared, onActivate, onPatch, hub, onStats, alertMode, onAlertMode, onDrawings, onHistory, indAction, onReplay, children }) {
  const { symbol, tf, cfg, ind } = cell;
  const tfSec = tfSecOf(tf);
  const apiRef = useRef(null);
  const qc = useQueryClient();
  const dec = decimals(symbol);
  const [older, setOlder] = useState({ key: "", bars: [], done: false, busy: false });
  const [rp, setRp] = useState({ on: false, pick: false, playing: false, speed: 5, t: 0 });
  const [picker, setPicker] = useState(false);
  const [pending, setPending] = useState(null); // {price}
  const [aState, setAState] = useState({ busy: false, error: "" });
  const [notice, setNotice] = useState("");
  const key = `${symbol}|${tf}`;
  const cmp = cell.cmp || null; // {symbol, mode: pct|spread|ratio}

  useEffect(() => { hub.register(cell.id, apiRef); return () => hub.unregister(cell.id); }, [cell.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- nến mới nhất + phân trang lịch sử ----
  const barsQ = useQuery({
    queryKey: ["bars-pro", symbol, tf, cfg.nBars],
    queryFn: ({ signal }) => api("/bars", { symbol, tf, limit: cfg.nBars, order: "desc" }, signal),
    refetchInterval: 60_000, staleTime: 10_000, enabled: !!symbol,
  });
  const latest = useMemo(() => toBars(barsQ.data?.items || []), [barsQ.data]);
  const olderBars = older.key === key ? older.bars : [];
  const bars0 = useMemo(() => mergeBars(olderBars, latest), [olderBars, latest]);
  const loadMore = useCallback(async () => {
    if (older.busy || (older.key === key && older.done) || rp.on || !latest.length) return;
    const first = (older.key === key && older.bars[0]) || latest[0];
    if (bars0.length >= MAX_BARS_TOTAL) { setOlder((o) => ({ ...o, key, done: true })); return; }
    setOlder((o) => ({ ...(o.key === key ? o : { bars: [], done: false }), key, busy: true }));
    try {
      const r = await api("/bars", { symbol, tf, limit: 2500, order: "desc", to: new Date((first.t - 1) * 1000).toISOString() });
      const nb = toBars(r.items || []);
      setOlder((o) => (o.key !== key ? o : { key, bars: nb.length ? mergeBars(nb, o.bars) : o.bars, done: nb.length < 50, busy: false }));
    } catch { setOlder((o) => (o.key !== key ? o : { ...o, busy: false })); }
  }, [older, key, rp.on, latest, symbol, tf, bars0.length]);
  const loadMoreRef = useRef(loadMore);
  loadMoreRef.current = loadMore;

  // ---- mã so sánh ----
  const cmpQ = useQuery({
    queryKey: ["bars-pro", cmp?.symbol, tf, cfg.nBars],
    queryFn: ({ signal }) => api("/bars", { symbol: cmp.symbol, tf, limit: cfg.nBars, order: "desc" }, signal),
    staleTime: 30_000, refetchInterval: 60_000, enabled: !!cmp?.symbol && cmp.symbol !== symbol,
  });
  const cmpBars = useMemo(() => toBars(cmpQ.data?.items || []), [cmpQ.data]);
  const synth = cmp && (cmp.mode === "spread" || cmp.mode === "ratio") && cmpBars.length ? cmp.mode : null;
  const bars = useMemo(() => (synth ? combineBars(bars0, cmpBars, synth) : bars0), [synth, bars0, cmpBars]);
  const compare = useMemo(() => (cmp && cmpBars.length ? { symbol: cmp.symbol, bars: cmpBars, mode: cmp.mode || "pct" } : null), [cmp, cmpBars]);
  const drawSymbol = synth ? `${symbol}${synth === "spread" ? "-" : "/"}${cmp.symbol}` : symbol;
  const label = synth ? `${symbolLabel(symbol)} ${synth === "spread" ? "−" : "÷"} ${symbolLabel(cmp.symbol)}` : symbolLabel(symbol);
  const decView = synth === "ratio" ? Math.max(3, dec) : dec;

  // ---- replay ----
  const exitReplay = useCallback(() => setRp((r) => ({ ...r, on: false, pick: false, playing: false })), []);
  const startReplay = useCallback(() => setRp({ on: true, pick: true, playing: false, speed: 5, t: 0 }), []);
  useEffect(() => { onReplay?.(cell.id, rp.on); shared.registerReplay?.(cell.id, { start: startReplay, exit: exitReplay, active: () => rp.on, toggle: () => (rp.on ? exitReplay() : startReplay()) }); }, [rp.on, cell.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const headIdx = rp.on && !rp.pick && bars.length ? lowerIdx(bars, rp.t) : bars.length - 1;
  const viewBars = useMemo(() => {
    if (!rp.on || rp.pick || !bars.length) return bars;
    const hi = lowerIdx(bars, rp.t);
    return bars.slice(Math.max(0, hi - 4000), hi + 1);
  }, [rp.on, rp.pick, rp.t, bars]);
  const step = useCallback((d) => setRp((r) => {
    if (!bars.length) return r;
    const i = Math.max(0, Math.min(bars.length - 1, lowerIdx(bars, r.t) + d));
    return { ...r, t: bars[i].t, playing: d > 0 && i >= bars.length - 1 ? false : r.playing };
  }), [bars]);
  const seek = useCallback((i, start) => setRp((r) => {
    const k = Math.max(0, Math.min(bars.length - 1, i));
    return bars[k] ? { ...r, t: bars[k].t, pick: start ? false : r.pick } : r;
  }), [bars]);
  useEffect(() => {
    if (!rp.on || rp.pick || !rp.playing) return undefined;
    const id = setInterval(() => { step(1); apiRef.current?.toEnd(); }, Math.max(40, 1000 / rp.speed));
    return () => clearInterval(id);
  }, [rp.on, rp.pick, rp.playing, rp.speed, step]);
  useEffect(() => { if (rp.on && !rp.pick) requestAnimationFrame(() => apiRef.current?.toEnd()); }, [rp.on, rp.pick]);
  // phím tắt replay (chỉ khi ô đang hoạt động)
  useEffect(() => {
    if (!active || !rp.on) return undefined;
    const onKey = (e) => {
      const t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      if (e.key === " " && !rp.pick) { e.preventDefault(); setRp((r) => ({ ...r, playing: !r.playing })); }
      else if (e.key === "ArrowRight" && !e.shiftKey && !rp.pick) { e.preventDefault(); step(1); apiRef.current?.toEnd(); }
      else if (e.key === "ArrowLeft" && !rp.pick) { e.preventDefault(); step(-1); }
      else if (e.key === "Escape") { e.stopPropagation(); exitReplay(); }
    };
    addEventListener("keydown", onKey, true);
    return () => removeEventListener("keydown", onKey, true);
  }, [active, rp.on, rp.pick, step, exitReplay]);

  // ---- realtime: tick -> nến cuối; md.bars -> thay nến (tắt khi replay / spread) ----
  const lastRef = useRef(null);
  const rtAtRef = useRef(0); // lần cuối nhận nến từ kênh rt (c:SYM:TF); còn "tươi" thì bỏ qua đường legacy
  useEffect(() => { lastRef.current = latest.length ? { ...latest[latest.length - 1] } : null; }, [latest]);
  useEffect(() => {
    if (rp.on || synth) return undefined;
    const stepS = tfSec;
    const offTick = onTick(symbol, (qt) => {
      if (Date.now() - rtAtRef.current < 5000) return;
      const px = qt.bid ?? qt.ask;
      if (px == null || stepS > 86400) return;
      const t = Math.floor(new Date(qt.ts || Date.now()).getTime() / 1000);
      const l = lastRef.current;
      if (l && t < l.t) return;
      if (!l || t >= l.t + stepS) {
        const nt = l ? l.t + Math.floor((t - l.t) / stepS) * stepS : Math.floor(t / stepS) * stepS;
        lastRef.current = { t: nt, o: px, h: px, l: px, c: px, v: 0 };
      } else lastRef.current = { ...l, h: Math.max(l.h, px), l: Math.min(l.l, px), c: px };
      apiRef.current?.updateLast(lastRef.current);
    });
    const offBar = onBar((p) => {
      if (Date.now() - rtAtRef.current < 5000) return;
      if (p.symbol !== symbol || p.tf !== tf) return;
      const t = Math.floor(new Date(p.ts_open).getTime() / 1000);
      lastRef.current = { t, o: p.o, h: p.h, l: p.l, c: p.c, v: p.v || 0 };
      apiRef.current?.updateLast(lastRef.current);
    });
    return () => { offTick(); offBar(); };
  }, [symbol, tf, tfSec, rp.on, synth]);
  // rt: nến đang hình thành do máy chủ dựng (topic c:SYM:TF) -> thay nến cuối. Không setState nên không re-render ô biểu đồ.
  useEffect(() => {
    if (rp.on || synth || !symbol || !/^(M1|M5|M15|H1|H4|D1)$/.test(tf)) return undefined;
    return rtSubscribe(`c:${symbol}:${tf}`, (c) => {
      if (!c || typeof c.t !== "number" || c.c == null) return;
      const t = Math.floor(c.t / 1000);
      const l = lastRef.current;
      if (l && t < l.t) return;
      rtAtRef.current = Date.now();
      lastRef.current = { t, o: c.o, h: c.h, l: c.l, c: c.c, v: c.v || 0 };
      apiRef.current?.updateLast(lastRef.current);
    });
  }, [symbol, tf, rp.on, synth]);

  // ---- phân tích máy chủ (pivot, tóm tắt) ----
  const anQ = useQuery({
    queryKey: ["an-sym", symbol, tf], queryFn: ({ signal }) => api(`/analytics/symbol/${encodeURIComponent(symbol)}`, { tf }, signal),
    retry: false, staleTime: 60_000, refetchInterval: 120_000, enabled: !!symbol && !synth && /^(H1|H4|D1)$/.test(tf), // máy chủ chỉ phân tích H1/H4/D1: tránh 404 nhiễu console ở khung khác
  });
  const server = anQ.data?.tfs?.[tf] || null;

  // ---- số liệu cho dải giá của workspace ----
  useEffect(() => {
    if (!active) return;
    let hi = -Infinity, lo = Infinity;
    for (const b of bars) { if (b.h > hi) hi = b.h; if (b.l < lo) lo = b.l; }
    onStats?.({ id: cell.id, last: bars[bars.length - 1] || null, prev: bars[bars.length - 2] || null, hi: bars.length ? hi : null, lo: bars.length ? lo : null,
      pending: barsQ.isPending, error: barsQ.isError, retry: () => barsQ.refetch(), count: bars.length, loadingMore: older.busy, server, serverQ: anQ, label, bars });
  }, [active, bars, barsQ.isPending, barsQ.isError, older.busy, server, anQ.isPending, label]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- mốc lịch HIGH + tin quan trọng ----
  const firstT = bars0[0]?.t;
  const fromIso = useMemo(() => {
    const t = Math.max(firstT || 0, Math.floor(Date.now() / 1000) - 150 * 86400);
    return new Date(Math.floor(t / 86400) * 86400 * 1000).toISOString();
  }, [firstT]);
  const toIso = useMemo(() => new Date(Math.floor((Date.now() + 14 * 86400e3) / 86400e3) * 86400e3).toISOString(), []);
  const evQ = useQuery({
    queryKey: ["chart-cal", fromIso, toIso], queryFn: ({ signal }) => api("/calendar", { from: fromIso, to: toIso, limit: 500, order: "asc" }, signal),
    enabled: !!cfg.events && !!firstT, staleTime: 300_000, retry: false,
  });
  const newsQ = useQuery({
    queryKey: ["chart-news", symbol], queryFn: ({ signal }) => api("/news", { symbol, limit: 100 }, signal),
    enabled: !!cfg.news && !!symbol, staleTime: 120_000, retry: false,
  });
  const marks = useMemo(() => {
    const out = [];
    if (cfg.events) {
      for (const e of evQ.data?.items || []) {
        if (String(e.impact || "").toLowerCase() !== "high") continue;
        if (cfg.eventsAll !== true && !eventRelevant(symbol, e.country)) continue;
        const t = Math.floor(Date.parse(e.ts) / 1000);
        if (!Number.isFinite(t)) continue;
        const title = clean(e.title || "");
        const bits = [e.forecast && `Dự báo ${e.forecast}`, e.previous && `Trước ${e.previous}`, e.actual && `Thực tế ${e.actual}`].filter(Boolean).join(" · ");
        out.push({ kind: "event", t, color: "#ff8a5c", short: `${e.country ? `${e.country} ` : ""}${title}`.slice(0, 26), title: `${e.country ? `${e.country} · ` : ""}${title}`, sub: bits || "Tin tác động CAO", when: dateTime(e.ts) });
      }
    }
    if (cfg.news) {
      for (const n of newsQ.data?.items || []) {
        const s = n.sentiment;
        if (s == null || Math.abs(s) < 0.35 || !n.published_at) continue;
        const t = Math.floor(Date.parse(n.published_at) / 1000);
        if (!Number.isFinite(t)) continue;
        out.push({ kind: "news", t, color: s > 0 ? "#2bd08f" : "#ff5c7a", title: clean(n.title || ""), sub: `Sắc thái ${s > 0 ? "+" : ""}${s.toFixed(2)} (${s > 0 ? "tích cực" : "tiêu cực"})`, when: dateTime(n.published_at) });
      }
    }
    return out.sort((a, b) => a.t - b.t);
  }, [cfg.events, cfg.eventsAll, cfg.news, evQ.data, newsQ.data, symbol]);

  // ---- cảnh báo giá của tôi (đọc /user/rules; chỉ quy tắc 1 điều kiện giá của mã này) ----
  const rules = useRules();
  const alerts = useMemo(() => {
    if (cfg.alerts === false) return [];
    const out = [];
    for (const r of rules.data?.items || []) {
      if (!r.enabled || r.status === "expired" || (r.conditions || []).length !== 1) continue;
      const c = r.conditions[0];
      if (c.type !== "price" || c.symbol !== symbol) continue;
      const price = Number(c.value);
      if (Number.isFinite(price)) out.push({ id: r.id, price, label: r.name?.slice(0, 24) || "" });
    }
    return out;
  }, [rules.data, symbol, cfg.alerts]);
  const ruleOf = (id) => (rules.data?.items || []).find((r) => r.id === id);
  const createAlert = async ({ name, op, price, channels, mode }) => {
    setAState({ busy: true, error: "" });
    try {
      const f = { ...emptyForm(), name, conditions: [{ ...newCond("price", symbol), op, value: String(+Number(price).toFixed(Math.max(dec, 2) + 2)) }], channels, mode, cooldown_min: "60", level: "warn", note: "Tạo từ biểu đồ (kéo/bấm vào mức giá)" };
      const { payload, errors } = buildPayload(f);
      const first = Object.values(errors)[0];
      if (first) throw new Error(first);
      await apiWrite("POST", "/user/rules", payload);
      await qc.invalidateQueries({ queryKey: ["user-rules"] });
      setPending(null); onAlertMode(false); setAState({ busy: false, error: "" });
      setNotice(`Đã tạo cảnh báo ${symbolLabel(symbol)} tại ${Number(price).toFixed(dec)}.`);
    } catch (e) { setAState({ busy: false, error: e.message || "Không tạo được cảnh báo." }); }
  };
  const moveAlert = async (id, price) => {
    const r = ruleOf(id);
    if (!r) return;
    try {
      const c = { ...r.conditions[0], value: +Number(price).toFixed(Math.max(dec, 2) + 2) };
      await apiWrite("PUT", `/user/rules/${id}`, ruleToIn(r, { conditions: [c] }));
      await qc.invalidateQueries({ queryKey: ["user-rules"] });
      setNotice(`Đã đổi mức cảnh báo "${r.name}" thành ${Number(price).toFixed(dec)}.`);
    } catch (e) { setNotice(`Không đổi được cảnh báo: ${e.message}`); await qc.invalidateQueries({ queryKey: ["user-rules"] }); }
  };
  useEffect(() => { if (!notice) return undefined; const id = setTimeout(() => setNotice(""), 5000); return () => clearTimeout(id); }, [notice]);
  useEffect(() => { if (!alertMode) setPending((p) => (p && !aState.busy ? null : p)); }, [alertMode]); // eslint-disable-line react-hooks/exhaustive-deps

  const lastClose = bars.length ? bars[bars.length - 1].c : null;
  const pick = useCallback((t) => { const i = lowerIdx(bars, t); if (i >= 0) seek(i, true); }, [bars, seek]);
  const onCross = useCallback((t) => hub.crosshair(cell.id, t), [hub, cell.id]);
  const onRange = useCallback((r) => hub.range(cell.id, r), [hub, cell.id]);
  const ov = useMemo(() => ({ marks, alerts, alertMode: active && alertMode }), [marks, alerts, active, alertMode]);
  const linkCol = cell.grp ? LINK_COLORS[cell.grp] : null;

  return (
    <div className={cn("ws-cell", active && "ws-cell-on", !solo && active && "ring-1 ring-inset ring-[var(--accent)]")} data-cell={cell.id} onPointerDown={() => onActivate(cell.id)}>
      {!solo && (
        <div className="ws-cellhead">
          <details className="relative">
            <summary className="list-none cursor-pointer rounded px-1 py-0.5 hover:bg-panel2" title="Nhóm liên kết (đồng bộ mã/khung giữa các ô cùng màu)" aria-label="Nhóm liên kết">
              <span className="inline-block h-2.5 w-2.5 rounded-full border border-line2" style={{ background: linkCol || "transparent" }} />
            </summary>
            <div className="absolute left-0 top-6 z-40 flex gap-1.5 rounded-md border border-line2 bg-panel p-1.5 shadow-lg">
              {[null, ...Object.keys(LINK_COLORS)].map((g) => (
                <button key={g || "none"} type="button" aria-label={g ? `Nhóm ${g}` : "Không liên kết"} aria-pressed={cell.grp === g || (!cell.grp && !g)}
                  className="h-5 w-5 cursor-pointer rounded-full border-2 p-0" style={{ background: g ? LINK_COLORS[g] : "transparent", borderColor: (cell.grp || null) === g ? "var(--fg)" : "var(--line2)" }}
                  onClick={(e) => { onPatch(cell.id, { grp: g }); e.currentTarget.closest("details").removeAttribute("open"); }} />
              ))}
            </div>
          </details>
          <button type="button" className="cursor-pointer rounded border-0 bg-transparent px-1 py-0.5 text-[12.5px] font-semibold text-fg hover:bg-panel2" onClick={() => setPicker(true)} aria-label={`Đổi mã, đang là ${symbolLabel(symbol)}`}>{label}</button>
          <select className="field !h-6 !px-1 !text-[11.5px]" aria-label="Khung thời gian của ô" value={tf} onChange={(e) => onPatch(cell.id, { tf: e.target.value })}>
            {shared.tfsOf(symbol).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {barsQ.isPending && <span className="text-[11px] text-faint">đang tải…</span>}
          {older.busy && <span className="text-[11px] text-faint">tải thêm lịch sử…</span>}
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <ProChart className="absolute inset-0" apiRef={apiRef} symbol={symbol} tf={tf} tfSec={tfSec} bars={viewBars} decimals={decView} cfg={cfg} indicators={ind} serverTf={server} compare={compare}
          drawSymbol={drawSymbol} label={synth ? label : undefined}
          tool={active ? shared.tool : "cursor"} magnet={shared.magnet} drawVisible={shared.drawVisible} onToolDone={shared.onToolDone}
          onIndicatorAction={(act, id) => indAction(cell.id, act, id)} ov={ov} replayOn={rp.on}
          onAlertCreate={(p) => { setAState({ busy: false, error: "" }); setPending({ price: p }); }} onAlertMove={moveAlert}
          onCrosshairTime={onCross} onVisibleRange={onRange} onNeedMore={() => loadMoreRef.current()} pickMode={rp.on && rp.pick} onPickBar={pick}
          onFocusCell={() => onActivate(cell.id)} onDrawingsChange={active ? onDrawings : undefined} onHistory={active ? onHistory : undefined} />
        {barsQ.isPending && <div className="mkt-state" role="status">Đang tải nến {symbolLabel(symbol)} {tf}…</div>}
        {barsQ.isError && <div className="mkt-state text-down" role="alert">Không tải được nến. <button type="button" className="btn ml-2" onClick={() => barsQ.refetch()}>Thử lại</button></div>}
        {!barsQ.isPending && !barsQ.isError && !bars.length && <div className="mkt-state">Chưa có nến {tf} cho {symbolLabel(symbol)}. Thử khung khác hoặc chờ backfill.</div>}
        {rp.on && rp.pick && <div className="pointer-events-none absolute left-1/2 top-2 z-30 -translate-x-1/2 rounded-md bg-[var(--accent-bg)] px-3 py-1 text-[12px] font-medium text-accent">Chế độ replay: chọn nến bắt đầu</div>}
        {rp.on && !rp.pick && <div className="pointer-events-none absolute right-16 top-1.5 z-20 rounded bg-[var(--accent-bg)] px-2 py-0.5 text-[11px] font-semibold text-accent">REPLAY</div>}
        <ReplayBar rp={rp} total={bars.length} headIdx={Math.max(0, headIdx)} headTime={rp.on && !rp.pick && bars[headIdx] ? dateTime(bars[headIdx].ts || bars[headIdx].t * 1000) : ""}
          onStep={(d) => { step(d); apiRef.current?.toEnd(); }} onPlay={() => setRp((r) => ({ ...r, playing: !r.playing }))} onSpeed={(s) => setRp((r) => ({ ...r, speed: s }))}
          onSeek={seek} onExit={exitReplay} onRestart={() => seek(Math.max(0, bars.length - 1 - Math.min(200, Math.floor(bars.length / 3))))} />
        {active && alertMode && !pending && <div className="pointer-events-none absolute left-1/2 top-2 z-30 -translate-x-1/2 rounded-md bg-[var(--accent-bg)] px-3 py-1 text-[12px] font-medium text-accent">Bấm vào mức giá để đặt cảnh báo (Esc huỷ)</div>}
        {pending && active && <AlertPopover symbol={symbol} price={pending.price} last={lastClose} dec={dec} busy={aState.busy} error={aState.error} onCreate={createAlert} onCancel={() => { setPending(null); onAlertMode(false); }} />}
        {notice && <div className="absolute bottom-12 left-1/2 z-30 -translate-x-1/2 rounded-md border border-line2 bg-panel/95 px-3 py-1.5 text-[12px] shadow-lg" role="status">{notice}</div>}
        {children}
      </div>
      <SymbolPicker open={picker} onClose={() => setPicker(false)} symbols={symbols} onPick={(s) => onPatch(cell.id, { symbol: s })} />
    </div>
  );
}
