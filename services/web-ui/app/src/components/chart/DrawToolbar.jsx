// Thanh công cụ vẽ dọc bên trái biểu đồ (học bố cục TradingView): các NHÓM công cụ mở bảng chọn (flyout), Icon SVG tự vẽ.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bell, Eye, EyeOff, ListTree, Lock, LockOpen, Magnet, MousePointer2, Redo2, Trash2, Undo2 } from "lucide-react";
import { cn } from "../ui";
import { TOOLS, TOOL_GROUPS } from "./drawings";

const I = (d, extra) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}{extra}</svg>
);
const dot = (x, y) => <circle cx={x} cy={y} r="1.9" fill="currentColor" stroke="none" />;
const ICONS = {
  trend: I(<path d="M4 19 20 5" />, <>{dot(4, 19)}{dot(20, 5)}</>),
  ray: I(<path d="M4 18 21 4" />, <>{dot(4, 18)}<path d="m16 3.5 5 .5-.5 5" /></>),
  extended: I(<path d="M2 20 22 4" />, <>{dot(8, 15.2)}{dot(16, 8.8)}</>),
  hline: I(<path d="M3 12h18" />, dot(12, 12)),
  vline: I(<path d="M12 3v18" />, dot(12, 12)),
  rect: I(<rect x="4" y="6" width="16" height="12" rx="1" />),
  channel: I(<><path d="M3 15 17 5" /><path d="M7 20 21 10" /></>, <path d="M5 17.5 19 7.5" strokeDasharray="2 2.5" strokeWidth="1.2" />),
  fib: I(<path d="M3 4h18M3 9h18M3 14h18M3 20h18" />, <path d="M6 20 18 4" strokeWidth="1.2" strokeDasharray="2 2" />),
  fibext: I(<path d="M3 5h18M3 11h18M3 16h18M3 21h18" strokeWidth="1.5" />, <path d="M5 21 11 11 17 16" strokeWidth="1.2" strokeDasharray="2 2" />),
  ruler: I(<><rect x="3" y="8" width="18" height="8" rx="1" /><path d="M7 8v3M11 8v4M15 8v3M19 8v4" /></>),
  regression: I(<><path d="M3 17 21 7" /><path d="M3 12 21 2" strokeDasharray="2 2" strokeWidth="1.3" /><path d="M3 22 21 12" strokeDasharray="2 2" strokeWidth="1.3" /></>),
  pitchfork: I(<><path d="M4 12h6M10 12l10-7M10 12l10 0M10 12l10 7" /></>, <>{dot(4, 12)}</>),
  gannfan: I(<path d="M4 20 20 4M4 20 20 9M4 20 20 14M4 20 14 4M4 20 9 4" />, dot(4, 20)),
  triangle: I(<path d="M12 4 21 19H3Z" />),
  elliott5: I(<path d="M2 18 6 8l4 7 5-12 3 8 4-3" strokeWidth="1.6" />),
  elliottabc: I(<path d="M3 5 10 17l4-7 7 9" strokeWidth="1.6" />),
  supply: I(<><rect x="3" y="5" width="18" height="7" rx="1" fill="currentColor" fillOpacity=".18" /><path d="M3 19h18" strokeDasharray="2 3" strokeWidth="1.2" /></>),
  demand: I(<><rect x="3" y="12" width="18" height="7" rx="1" fill="currentColor" fillOpacity=".18" /><path d="M3 5h18" strokeDasharray="2 3" strokeWidth="1.2" /></>),
  arrow: I(<path d="M5 19 19 5M10 5h9v9" />),
  text: I(<path d="M5 6V4h14v2M12 4v16M9 20h6" />),
  note: I(<><path d="M5 4h14v12l-5 5H5z" /><path d="M14 21v-5h5" /></>),
  fibarc: I(<><path d="M4 20A16 16 0 0 1 20 4" /><path d="M4 20A10 10 0 0 1 14 10" strokeWidth="1.3" strokeDasharray="2 2" /></>),
  fibtime: I(<path d="M5 3v18M9 3v18M13 3v18M21 3v18" strokeWidth="1.4" />),
  projection: I(<><path d="M3 17 9 9" /><path d="M13 20 19 12" strokeDasharray="2 2" /><path d="M9 9l4 11" strokeWidth="1.2" strokeDasharray="2 2" /></>),
  avwap: I(<path d="M5 17c4-1 6-9 10-8s4 4 6 2" />, dot(5, 17)),
  vprofile: I(<path d="M4 5h6M4 9h11M4 13h16M4 17h9M4 21h5" strokeWidth="2.2" />),
};

function Btn({ label, active, onClick, children, danger, disabled, small }) {
  return (
    <button type="button" title={label} aria-label={label} aria-pressed={active} disabled={disabled}
      className={cn("grid shrink-0 cursor-pointer place-items-center rounded-md border-0 bg-transparent text-muted hover:bg-panel2 hover:text-fg disabled:cursor-default disabled:opacity-40", small ? "h-8 w-9" : "h-9 w-9",
        active && "!bg-[var(--accent-bg)] !text-accent", danger && "hover:!text-down")}
      onClick={onClick}>{children}</button>
  );
}

function Flyout({ group, anchor, tool, onPick, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const away = (e) => { if (!ref.current?.contains(e.target) && !anchor?.contains(e.target)) onClose(); };
    const key = (e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("keydown", key, true);
    return () => { document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", key, true); };
  }, [anchor, onClose]);
  const r = anchor?.getBoundingClientRect();
  if (!r) return null;
  const vertical = window.innerWidth >= 1024;
  const style = vertical ? { left: r.right + 6, top: Math.min(r.top, window.innerHeight - 320) } : { left: Math.max(6, Math.min(r.left, window.innerWidth - 250)), top: r.bottom + 6 };
  return createPortal(
    <div ref={ref} role="menu" aria-label={group.label} style={style} className="fixed z-[80] w-[236px] rounded-md border border-line2 bg-panel p-1 shadow-xl">
      <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-faint">{group.label}</div>
      {group.tools.map((id) => {
        const t = TOOLS.find((x) => x.id === id);
        return (
          <button key={id} type="button" role="menuitem" className={cn("flex w-full cursor-pointer items-center gap-2.5 rounded border-0 bg-transparent px-2 py-1.5 text-left font-[inherit] text-[12.5px] text-fg hover:bg-panel2", tool === id && "!bg-[var(--accent-bg)] text-accent")}
            onClick={() => onPick(id)}>
            <span className="grid h-5 w-5 place-items-center">{ICONS[id]}</span>
            <span className="min-w-0 flex-1 truncate">{t.label}</span>
            <kbd className="num shrink-0 text-[10px] text-faint">{t.key.length === 1 ? t.key : t.alt ? `Alt+${t.alt}` : ""}</kbd>
          </button>
        );
      })}
    </div>, document.body);
}

export default function DrawToolbar({ tool, setTool, magnet, setMagnet, visible, setVisible, onUndo, onRedo, canUndo, canRedo, onClear, onTree, treeOpen, alertMode, onAlertMode, lockAll, onLockAll, className }) {
  const [open, setOpen] = useState(null);
  const [last, setLast] = useState({});
  const btns = useRef({});
  const pick = (g, id) => { setLast((l) => ({ ...l, [g.id]: id })); setTool(id); setOpen(null); };
  return (
    <div className={cn("flex shrink-0 gap-0.5 border-line bg-panel p-1 lg:flex-col lg:overflow-y-auto lg:border-r max-lg:flex-row max-lg:overflow-x-auto max-lg:border-b", className)} role="toolbar" aria-label="Công cụ vẽ" aria-orientation="vertical">
      <Btn label="Con trỏ (Esc)" active={tool === "cursor"} onClick={() => setTool("cursor")}><MousePointer2 size={17} aria-hidden="true" /></Btn>
      <span className="my-1 hidden h-px bg-line lg:block" />
      {TOOL_GROUPS.map((g) => {
        const cur = last[g.id] && g.tools.includes(last[g.id]) ? last[g.id] : g.tools[0];
        const act = g.tools.includes(tool);
        return (
          <span key={g.id} className="relative shrink-0" ref={(n) => { btns.current[g.id] = n; }}>
            <Btn label={`${g.label}: ${TOOLS.find((t) => t.id === (act ? tool : cur)).label}`} active={act} onClick={() => setOpen(open === g.id ? null : g.id)}>{ICONS[act ? tool : cur]}</Btn>
            <span className="pointer-events-none absolute bottom-0.5 right-0.5 h-0 w-0 border-b-[4px] border-l-[4px] border-b-current border-l-transparent opacity-60" aria-hidden="true" />
            {open === g.id && <Flyout group={g} anchor={btns.current[g.id]} tool={tool} onPick={(id) => pick(g, id)} onClose={() => setOpen(null)} />}
          </span>
        );
      })}
      <span className="my-1 hidden h-px bg-line lg:block" />
      <Btn label="Đặt cảnh báo giá: bấm vào mức giá (Alt+A)" active={alertMode} onClick={onAlertMode}><Bell size={17} aria-hidden="true" /></Btn>
      <Btn label="Nam châm: bắt vào Open/High/Low/Close (N)" active={magnet} onClick={() => setMagnet(!magnet)}><Magnet size={17} aria-hidden="true" /></Btn>
      <Btn label={visible ? "Ẩn mọi hình vẽ" : "Hiện hình vẽ"} active={!visible} onClick={() => setVisible(!visible)}>{visible ? <Eye size={17} aria-hidden="true" /> : <EyeOff size={17} aria-hidden="true" />}</Btn>
      <Btn label={lockAll ? "Mở khoá mọi hình vẽ" : "Khoá mọi hình vẽ"} active={lockAll} onClick={onLockAll}>{lockAll ? <Lock size={17} aria-hidden="true" /> : <LockOpen size={17} aria-hidden="true" />}</Btn>
      <Btn label="Danh sách đối tượng" active={treeOpen} onClick={onTree}><ListTree size={17} aria-hidden="true" /></Btn>
      <Btn label="Hoàn tác (Ctrl+Z)" onClick={onUndo} disabled={canUndo === false}><Undo2 size={17} aria-hidden="true" /></Btn>
      <Btn label="Làm lại (Ctrl+Shift+Z)" onClick={onRedo} disabled={canRedo === false}><Redo2 size={17} aria-hidden="true" /></Btn>
      <Btn label="Xoá toàn bộ hình vẽ của mã/khung này" danger onClick={onClear}><Trash2 size={17} aria-hidden="true" /></Btn>
    </div>
  );
}
