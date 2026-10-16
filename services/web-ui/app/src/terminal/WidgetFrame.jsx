// Khung widget: tiêu đề + kênh màu + menu ⋯ (cấu hình, phóng to, nhân bản, xuất ảnh, cỡ, xoá) + biên lỗi + đo kích thước.
import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Copy, Download, GripVertical, Maximize2, Minimize2, MoreHorizontal, Settings2, Trash2, Link2, Ruler, Puzzle } from "lucide-react";
import { Skeleton, cn } from "../components/ui";
import { symbolLabel } from "../lib/format";
import { resolveConfig } from "./registry";
import { duplicateWidget, removeWidget, setChannelSymbol, updateWidget, setMax } from "./store";
import { ChannelDot, ChannelPicker, MenuList, Popover, WidgetContext } from "./ui";
import ConfigPanel from "./ConfigPanel";
import { toast } from "../ux/bus";

class Boundary extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidUpdate(p) { if (p.k !== this.props.k && this.state.err) this.setState({ err: null }); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div role="alert" className="p-3 text-[12.5px]">
        <b className="text-down">Widget gặp lỗi.</b>
        <p className="text-muted mt-1 mb-2 break-words">{String(this.state.err?.message || this.state.err).slice(0, 160)}</p>
        {/dynamically imported module|Loading chunk|Importing a module script failed/i.test(String(this.state.err?.message))
          ? <button className="btn" onClick={() => location.reload()}>Tải lại trang (có bản mới)</button>
          : <button className="btn" onClick={() => this.setState({ err: null })}>Thử lại</button>}
      </div>
    );
  }
}

const SIZES = [["Nhỏ", 0.6], ["Vừa", 1], ["Lớn", 1.5]];

export default function WidgetFrame({ wsId, inst, def, channels, locked, maximized, kiosk }) {
  const body = useRef(null);
  const root = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [cfgOpen, setCfgOpen] = useState(false);
  const cfg = useMemo(() => resolveConfig(def, inst.c), [def, inst.c]);
  const channel = def?.linkable ? inst.k || null : null;
  const symbol = def?.linkable ? (channel && channels[channel]) || cfg.symbol || null : null;

  useEffect(() => {
    const el = body.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => { const r = e.contentRect; setSize((s) => (Math.abs(s.w - r.width) > 1 || Math.abs(s.h - r.height) > 1 ? { w: Math.round(r.width), h: Math.round(r.height) } : s)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const setConfig = useCallback((patch) => updateWidget(wsId, inst.i, { cfg: patch }), [wsId, inst.i]);
  const setSymbol = useCallback((s) => {
    if (!s) return;
    updateWidget(wsId, inst.i, { cfg: { symbol: s } });
    if (channel) setChannelSymbol(wsId, channel, s);
  }, [wsId, inst.i, channel]);
  const setChannel = useCallback((c) => {
    updateWidget(wsId, inst.i, { channel: c });
    if (c && symbol) setChannelSymbol(wsId, c, channels[c] || symbol);
  }, [wsId, inst.i, symbol, channels]);

  const exportImage = async () => {
    try {
      const { toPng } = await import("html-to-image");
      const url = await toPng(root.current, { pixelRatio: 2, cacheBust: true, backgroundColor: getComputedStyle(document.documentElement).getPropertyValue("--panel").trim() || "#0e141c", filter: (n) => !(n.classList && n.classList.contains("tm-noexport")) });
      const a = document.createElement("a");
      a.href = url; a.download = `${(inst.n || def?.title || "widget").replace(/[^\w\-]+/g, "_")}.png`; a.click();
    } catch (e) { toast({ tone: "error", title: "Không xuất được ảnh", body: String(e?.message || e).slice(0, 120) }); }
  };
  const resize = (f) => updateWidget(wsId, inst.i, { size: { w: Math.round(def.defaultSize.w * f), h: Math.round(def.defaultSize.h * f) } });

  const title = inst.n || def?.title || inst.t;
  const ctx = useMemo(() => ({ id: inst.i, type: inst.t, wsId, config: cfg, setConfig, symbol, setSymbol, channel, size, locked, maximized: !!maximized, kiosk: !!kiosk }), [inst.i, inst.t, wsId, cfg, setConfig, symbol, setSymbol, channel, size, locked, maximized, kiosk]);

  const items = def ? [
    { label: "Cấu hình…", icon: Settings2, onClick: () => setCfgOpen(true) },
    { label: maximized ? "Thu nhỏ" : "Phóng to", icon: maximized ? Minimize2 : Maximize2, onClick: () => setMax(maximized ? null : inst.i) },
    { label: "Nhân bản", icon: Copy, onClick: () => duplicateWidget(wsId, inst.i) },
    { label: "Xuất ảnh PNG", icon: Download, onClick: exportImage },
    { sep: true },
    ...SIZES.map(([l, f]) => ({ label: `Cỡ ${l.toLowerCase()}`, icon: Ruler, onClick: () => resize(f), disabled: locked })),
    { sep: true },
    { label: "Xoá widget", icon: Trash2, danger: true, onClick: () => removeWidget(wsId, inst.i), disabled: locked },
  ] : [{ label: "Xoá widget", icon: Trash2, danger: true, onClick: () => removeWidget(wsId, inst.i) }];

  const Icon = def?.icon || Puzzle;
  const draggable = !locked && !maximized && !kiosk;
  return (
    <WidgetContext.Provider value={ctx}>
      <section ref={root} className={cn("tm-w", def?.bare && !maximized && "tm-bare", maximized && "tm-w-max")} aria-label={title} data-widget={inst.t}>
        <header className={cn("tm-wh", draggable && "tm-drag")} onDoubleClick={() => def && setMax(maximized ? null : inst.i)}>
          {draggable && <GripVertical size={13} className="text-faint shrink-0 tm-grip tm-noexport" aria-hidden="true" />}
          <Icon size={14} className="text-muted shrink-0" aria-hidden="true" />
          <h3 className="tm-wt truncate">{title}{symbol && <span className="text-muted font-normal"> · {symbolLabel(symbol)}</span>}</h3>
          <div className="ml-auto flex items-center gap-1 shrink-0 tm-nodrag tm-noexport" onDoubleClick={(e) => e.stopPropagation()}>
            {def?.linkable && !kiosk && (
              <Popover label="Kênh liên kết" width={230} trigger={(p) => (
                <button type="button" {...p} className="tm-ib" aria-label={channel ? `Kênh liên kết: ${channel}` : "Liên kết mã với widget khác"} title="Liên kết mã">
                  {channel ? <ChannelDot channel={channel} size={11} /> : <Link2 size={13} aria-hidden="true" />}
                </button>)}>
                {(close) => <ChannelPicker value={channel} onChange={setChannel} close={close} />}
              </Popover>
            )}
            {maximized && <button type="button" className="tm-ib" onClick={() => setMax(null)} aria-label="Thu nhỏ"><Minimize2 size={14} aria-hidden="true" /></button>}
            {!kiosk && (
              <Popover label={`Menu widget ${title}`} width={200} trigger={(p) => (
                <button type="button" {...p} className="tm-ib" aria-label={`Menu widget ${title}`}><MoreHorizontal size={15} aria-hidden="true" /></button>)}>
                {(close) => <MenuList items={items} close={close} />}
              </Popover>
            )}
          </div>
        </header>
        <div ref={body} className="tm-wb">
          {def ? (
            <Boundary k={`${inst.t}`}>
              <Suspense fallback={<div className="p-3"><Skeleton rows={4} /></div>}>
                <def.Comp {...ctx} />
              </Suspense>
            </Boundary>
          ) : (
            <div className="p-3 text-[12.5px] text-muted">Widget “{inst.t}” chưa có trong phiên bản này. Có thể xoá khỏi workspace.</div>
          )}
        </div>
        {cfgOpen && <ConfigPanel open onClose={() => setCfgOpen(false)} def={def} cfg={cfg} onCfg={setConfig} title={inst.n} onTitle={(t) => updateWidget(wsId, inst.i, { title: t })} channel={channel} onChannel={setChannel} />}
      </section>
    </WidgetContext.Provider>
  );
}
