// Trang Terminal: workspace nhiều tab, lưới kéo-thả/đổi cỡ (react-grid-layout, MIT), toolbar, danh mục widget, kiosk/trình chiếu.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ReactGridLayout, { useContainerWidth, verticalCompactor } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import "../terminal.css";
import { ChevronLeft, ChevronRight, Copy, Download, FileUp, Lock, LayoutTemplate, MoreHorizontal, Pencil, Play, Pause, Plus, RotateCcw, Trash2, Unlock, X, Presentation, Cloud, CloudOff, Check } from "lucide-react";
import { Dialog } from "../components/dialog";
import { toast } from "../ux/bus";
import { cn } from "../components/ui";
import { usePrefsState } from "../lib/prefs";
import { WIDGETS } from "./registry";
import { TEMPLATES } from "./defaults";
import {
  COLS, ROW_H, MARGIN, useTerminal, syncFromServer, setActive, addWorkspace, duplicateWorkspace, removeWorkspace, renameWorkspace, setLocked,
  moveWorkspace, resetWorkspace, addWidget, applyLayout, exportJSON, importJSON, setKiosk, setRotate, setMax, clearNote,
} from "./store";
import { MenuList, Popover } from "./ui";
import WidgetFrame from "./WidgetFrame";
import Catalog from "./Catalog";

const ROT = [[0, "Tắt"], [15, "15 giây"], [30, "30 giây"], [60, "1 phút"], [120, "2 phút"], [300, "5 phút"]];

function download(name, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function SaveChip({ save, note }) {
  const m = { dirty: ["Đang lưu…", Cloud, ""], saved: ["Đã lưu", Check, "text-up"], local: ["Lưu cục bộ", CloudOff, "text-accent"], idle: ["", null, ""] }[save] || ["", null, ""];
  if (!m[0]) return null;
  const I = m[1];
  return <span className={cn("hidden sm:inline-flex items-center gap-1 text-[11.5px]", m[2] || "text-muted")} title={note || m[0]} role="status"><I size={12} aria-hidden="true" />{m[0]}</span>;
}

function Tabs({ st, onAdd }) {
  const [edit, setEdit] = useState(null);
  const [val, setVal] = useState("");
  const done = (ok) => { if (ok && edit) renameWorkspace(edit, val); setEdit(null); };
  const onKey = (e, i) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      const j = (i + (e.key === "ArrowRight" ? 1 : -1) + st.o.length) % st.o.length;
      setActive(st.o[j]);
      e.currentTarget.parentElement.querySelectorAll('[role="tab"]')[j]?.focus();
    }
  };
  return (
    <div className="tm-tabs flex items-stretch gap-1 min-w-0">
      <div role="tablist" aria-label="Workspace" className="tm-tabs-in flex items-stretch gap-1 min-w-0 overflow-x-auto">
      {st.o.map((id, i) => {
        const on = id === st.a;
        return edit === id ? (
          <input key={id} autoFocus className="field !h-8 w-[140px]" value={val} maxLength={40} aria-label="Tên workspace"
            onChange={(e) => setVal(e.target.value)} onBlur={() => done(true)} onKeyDown={(e) => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); }} />
        ) : (
          <button key={id} type="button" role="tab" aria-selected={on} tabIndex={on ? 0 : -1} onClick={() => setActive(id)} onKeyDown={(e) => onKey(e, i)}
            onDoubleClick={() => { setEdit(id); setVal(st.w[id].n); }} title="Nhấp đúp để đổi tên"
            className={cn("tm-tab shrink-0", on && "on")}>{st.w[id].n}{st.w[id].l && <Lock size={10} className="ml-1 opacity-60" aria-label="đã khoá" />}</button>
        );
      })}
      </div>
      <Popover label="Thêm workspace" width={290} align="start" trigger={(p) => <button type="button" {...p} className="tm-tab shrink-0 !px-2" aria-label="Thêm workspace" title="Thêm workspace"><Plus size={14} aria-hidden="true" /></button>}>
        {(close) => (
          <div className="p-1">
            <div className="px-2 pt-1 pb-1 text-[11px] uppercase tracking-wide text-faint">Workspace mới từ mẫu</div>
            {TEMPLATES.map((t) => (
              <button key={t.id} type="button" role="menuitem" onClick={() => { close(); onAdd(t.id); }} className="w-full text-left rounded px-2 py-1.5 bg-transparent border-0 cursor-pointer text-fg hover:bg-panel2">
                <b className="block text-[12.5px]">{t.name}</b><span className="text-[11.5px] text-muted">{t.desc}</span>
              </button>
            ))}
          </div>
        )}
      </Popover>
    </div>
  );
}

function Grid({ ws, wsId, kiosk, maxId }) {
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1200 });
  const layout = useMemo(() => ws.x.map((w) => {
    const d = WIDGETS[w.t];
    return { i: w.i, x: w.x, y: w.y, w: w.w, h: w.h, minW: d?.minSize.w ?? 2, minH: d?.minSize.h ?? 2 };
  }), [ws.x]);
  const narrow = width < 720;
  const locked = ws.l || kiosk;
  // toàn màn hình/trình chiếu: co giãn chiều cao hàng để toàn bộ bố cục vừa khít màn hình (không cuộn)
  const [vh, setVh] = useState(() => innerHeight);
  useEffect(() => { if (!kiosk) return; const f = () => setVh(innerHeight); addEventListener("resize", f); f(); return () => removeEventListener("resize", f); }, [kiosk]);
  const rows = Math.max(1, ...ws.x.map((w) => w.y + w.h));
  const rowH = kiosk && !narrow ? Math.max(12, Math.floor((vh - 20 - (rows - 1) * MARGIN) / rows)) : ROW_H;

  // MỘT div đo bề rộng duy nhất (ổn định giữa các nhánh) để ResizeObserver không bám vào phần tử đã bị gỡ
  const maxBox = <div className="tm-w grid place-items-center text-muted text-[12.5px]">Đang phóng to…</div>;
  let content = null;
  if (ws.x.length && narrow) {
    const order = [...ws.x].sort((a, b) => a.y - b.y || a.x - b.x);
    content = order.map((w) => (
      <div key={w.i} className="min-w-0" style={{ height: Math.min(520, Math.max((WIDGETS[w.t]?.minSize.h ?? 2) * (ROW_H + MARGIN), w.h * (ROW_H + MARGIN) - MARGIN)) }}>
        {maxId === w.i ? maxBox : <WidgetFrame wsId={wsId} inst={w} def={WIDGETS[w.t]} channels={ws.c} locked />}
      </div>
    ));
  } else if (ws.x.length && mounted) {
    content = (
      <ReactGridLayout width={width} layout={layout} compactor={verticalCompactor}
        gridConfig={{ cols: COLS, rowHeight: rowH, margin: [MARGIN, MARGIN], containerPadding: [0, 0] }}
        dragConfig={{ enabled: !locked, handle: ".tm-drag", cancel: ".tm-nodrag" }}
        resizeConfig={{ enabled: !locked, handles: ["se"] }}
        onLayoutChange={(l) => applyLayout(wsId, l)}>
        {ws.x.map((w) => (
          <div key={w.i}>
            {maxId === w.i ? maxBox : <WidgetFrame wsId={wsId} inst={w} def={WIDGETS[w.t]} channels={ws.c} locked={locked} kiosk={kiosk} />}
          </div>
        ))}
      </ReactGridLayout>
    );
  }
  return <div ref={containerRef} className={cn(narrow ? "grid grid-cols-[minmax(0,1fr)] gap-2" : "tm-grid")}>{content}</div>;
}

export default function TerminalPage() {
  const st = useTerminal();
  const prefs = usePrefsState();
  const [cat, setCat] = useState(false);
  const [del, setDel] = useState(null);
  const fileRef = useRef(null);
  const latest = useRef(st); latest.current = st;
  const ws = st.w[st.a];

  useEffect(() => { if (prefs.loaded) syncFromServer(prefs.prefs, prefs.available); }, [prefs.loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // thoát kiosk bằng Esc / khi trình duyệt thoát toàn màn hình; trình chiếu xoay workspace
  useEffect(() => {
    if (!st.kiosk) return;
    const key = (e) => { if (e.key === "Escape" && !document.querySelector('[aria-modal="true"]')) setKiosk(false); };
    const fs = () => { if (!document.fullscreenElement) setKiosk(false); };
    addEventListener("keydown", key);
    document.addEventListener("fullscreenchange", fs);
    return () => { removeEventListener("keydown", key); document.removeEventListener("fullscreenchange", fs); };
  }, [st.kiosk]);
  useEffect(() => {
    const k = (e) => {
      if (!e.altKey || e.ctrlKey || e.metaKey || !/^[1-9]$/.test(e.key)) return;
      const id = latest.current.o[Number(e.key) - 1];
      if (id) { e.preventDefault(); setActive(id); }
    };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, []);
  useEffect(() => () => { document.documentElement.classList.remove("tm-kiosk"); }, []);
  useEffect(() => { if (st.note) { const t = setTimeout(clearNote, 7000); return () => clearTimeout(t); } }, [st.note]);

  const goto = (dir) => { const i = st.o.indexOf(st.a); setActive(st.o[(i + dir + st.o.length) % st.o.length], false); };
  // xoay dùng trạng thái mới nhất
  useEffect(() => {
    if (!st.kiosk || !st.rot || st.o.length < 2) return;
    const iv = setInterval(() => { const c = latest.current; const i = c.o.indexOf(c.a); setActive(c.o[(i + 1) % c.o.length], false); }, st.rot * 1000);
    return () => clearInterval(iv);
  }, [st.kiosk, st.rot, st.o.length]);

  const items = ws ? [
    { label: "Đổi tên (nhấp đúp tab)", icon: Pencil, disabled: true },
    { label: "Nhân bản workspace", icon: Copy, onClick: () => duplicateWorkspace(st.a) },
    { label: "Dời sang trái", icon: ChevronLeft, onClick: () => moveWorkspace(st.a, -1), disabled: st.o.indexOf(st.a) === 0 },
    { label: "Dời sang phải", icon: ChevronRight, onClick: () => moveWorkspace(st.a, 1), disabled: st.o.indexOf(st.a) === st.o.length - 1 },
    { sep: true },
    ...TEMPLATES.filter((t) => t.id !== "blank").map((t) => ({ label: `Đặt lại theo mẫu “${t.name}”`, icon: RotateCcw, onClick: () => resetWorkspace(st.a, t.id) })),
    { sep: true },
    { label: "Xuất workspace này (.json)", icon: Download, onClick: () => download(`terminal-${ws.n.replace(/[^\w\-]+/g, "_")}.json`, exportJSON([st.a])) },
    { label: "Xuất tất cả (.json)", icon: Download, onClick: () => download("terminal-workspaces.json", exportJSON()) },
    { label: "Nhập từ tệp .json…", icon: FileUp, onClick: () => fileRef.current?.click() },
    { sep: true },
    { label: "Xoá workspace", icon: Trash2, danger: true, disabled: st.o.length <= 1, onClick: () => setDel(st.a) },
  ] : [];

  const onFile = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    if (f.size > 400_000) { toast({ tone: "warn", title: "Tệp quá lớn", body: "Tối đa ~400KB." }); return; }
    const r = importJSON(await f.text());
    toast(r.error ? { tone: "error", title: "Không nhập được", body: r.error } : { tone: "ok", title: `Đã nhập ${r.added} workspace` });
  };

  if (!ws) return null;
  return (
    <div className={cn("tm-root", st.kiosk && "tm-kiosk-root")}>
      {!st.kiosk && (
        <div className="tm-bar">
          <Tabs st={st} onAdd={(t) => addWorkspace(t)} />
          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <SaveChip save={st.save} note={st.note} />
            <button type="button" className="btn !px-2.5" onClick={() => setCat(true)} aria-label="Thêm widget"><Plus size={14} aria-hidden="true" /><span className="hidden md:inline">Widget</span></button>
            <button type="button" className="btn !px-2" aria-pressed={ws.l} onClick={() => setLocked(st.a, !ws.l)} aria-label={ws.l ? "Mở khoá bố cục" : "Khoá bố cục"} title={ws.l ? "Bố cục đang khoá — nhấn để mở" : "Khoá bố cục để tránh kéo nhầm"}>
              {ws.l ? <Lock size={14} aria-hidden="true" /> : <Unlock size={14} aria-hidden="true" />}
            </button>
            <button type="button" className="btn !px-2" onClick={() => setKiosk(true)} aria-label="Chế độ toàn màn hình / trình chiếu" title="Toàn màn hình (Esc để thoát)"><Presentation size={14} aria-hidden="true" /></button>
            <Popover label="Menu workspace" width={270} trigger={(p) => <button type="button" {...p} className="btn !px-2" aria-label="Menu workspace"><MoreHorizontal size={15} aria-hidden="true" /></button>}>
              {(close) => <MenuList items={items} close={close} />}
            </Popover>
          </div>
        </div>
      )}
      {st.note && !st.kiosk && <div role="status" className="tm-note"><span>{st.note}</span><button type="button" className="tm-ib" onClick={clearNote} aria-label="Đóng thông báo"><X size={13} /></button></div>}

      <div className="tm-stage">
        {ws.x.length === 0 && !st.kiosk && (
          <div className="tm-empty">
            <LayoutTemplate size={30} className="text-muted" aria-hidden="true" />
            <h2 className="m-0 text-[15px]">Workspace trống</h2>
            <p className="m-0 text-muted max-w-[46ch]">Thêm widget (biểu đồ, bảng giá, tin, lịch…) rồi kéo thả để sắp xếp, hoặc đặt lại theo một mẫu có sẵn.</p>
            <div className="flex gap-2 flex-wrap justify-center">
              <button type="button" className="btn !border-accent" onClick={() => setCat(true)}><Plus size={14} /> Thêm widget</button>
              {TEMPLATES.filter((t) => t.id !== "blank").slice(0, 3).map((t) => <button key={t.id} type="button" className="btn" onClick={() => resetWorkspace(st.a, t.id)}>Mẫu “{t.name}”</button>)}
            </div>
          </div>
        )}
        <Grid ws={ws} wsId={st.a} kiosk={st.kiosk} maxId={st.maxId} />
      </div>

      {st.kiosk && (
        <div className="tm-kctl" role="toolbar" aria-label="Điều khiển trình chiếu">
          <button type="button" className="tm-ib" onClick={() => goto(-1)} aria-label="Workspace trước"><ChevronLeft size={15} /></button>
          <span className="text-[12px] px-1 truncate max-w-[160px]">{ws.n}</span>
          <button type="button" className="tm-ib" onClick={() => goto(1)} aria-label="Workspace kế"><ChevronRight size={15} /></button>
          <label className="flex items-center gap-1 text-[11.5px] text-muted pl-2">
            {st.rot ? <Play size={12} aria-hidden="true" /> : <Pause size={12} aria-hidden="true" />}
            <select className="field !h-7 !text-[11.5px]" aria-label="Tự chuyển workspace" value={st.rot} onChange={(e) => setRotate(Number(e.target.value))}>
              {ROT.map(([v, l]) => <option key={v} value={v}>{v ? `Xoay ${l}` : "Không xoay"}</option>)}
            </select>
          </label>
          <button type="button" className="tm-ib" onClick={() => setKiosk(false)} aria-label="Thoát toàn màn hình (Esc)"><X size={15} /></button>
        </div>
      )}

      {st.maxId && ws.x.find((w) => w.i === st.maxId) && createPortal(
        <div className="tm-maxlayer" role="dialog" aria-modal="true" aria-label="Widget phóng to" onKeyDown={(e) => { if (e.key === "Escape") setMax(null); }}>
          <div className="tm-maxback" onMouseDown={() => setMax(null)} aria-hidden="true" />
          <div className="tm-maxbox">
            <WidgetFrame wsId={st.a} inst={ws.x.find((w) => w.i === st.maxId)} def={WIDGETS[ws.x.find((w) => w.i === st.maxId).t]} channels={ws.c} locked maximized />
          </div>
        </div>, document.body)}
      <MaxEsc id={st.maxId} />
      <Catalog open={cat} onClose={() => setCat(false)} onAdd={(t) => addWidget(st.a, t)} />
      <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={onFile} />
      <Dialog open={!!del} onClose={() => setDel(null)} title="Xoá workspace?" footer={<><button type="button" className="btn" onClick={() => setDel(null)}>Huỷ</button><button type="button" className="btn !border-down text-down" onClick={() => { removeWorkspace(del); setDel(null); }}>Xoá</button></>}>
        <p className="m-0 p-3">Xoá “{st.w[del]?.n}” cùng {st.w[del]?.x.length || 0} widget. Có thể xuất ra tệp trước khi xoá.</p>
      </Dialog>
    </div>
  );
}

/** Esc thu nhỏ widget đang phóng to. */
function MaxEsc({ id }) {
  useEffect(() => {
    if (!id) return;
    const k = (e) => { if (e.key === "Escape" && !document.querySelector('[aria-modal="true"]:not(.tm-maxlayer)')) { e.stopPropagation(); setMax(null); } };
    addEventListener("keydown", k, true);
    return () => removeEventListener("keydown", k, true);
  }, [id]);
  return null;
}
