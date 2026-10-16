// Thanh công cụ vẽ dọc bên trái biểu đồ (học bố cục TradingView). Icon SVG tự vẽ, không phụ thuộc tên icon bên ngoài.
import { Eye, EyeOff, Magnet, MousePointer2, Trash2, Undo2 } from "lucide-react";
import { cn } from "../ui";
import { TOOLS } from "./drawings";
import { t } from "../../lib/i18n";

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
};

function Btn({ label, active, onClick, children, danger }) {
return (
    <button type="button" title={label} aria-label={label} aria-pressed={active}
      className={cn("grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-md border-0 bg-transparent text-muted hover:bg-panel2 hover:text-fg",
        active && "!bg-[var(--accent-bg)] !text-accent", danger && "hover:!text-down")}
      onClick={onClick}>{children}</button>
);
}

export default function DrawToolbar({ tool, setTool, magnet, setMagnet, visible, setVisible, onUndo, onClear, className }) {
  return (
    <div className={cn("flex shrink-0 gap-0.5 border-line bg-panel p-1 lg:flex-col lg:overflow-y-auto lg:border-r max-lg:flex-row max-lg:overflow-x-auto max-lg:border-b", className)} role="toolbar" aria-label={t("Công cụ vẽ")} aria-orientation="vertical">
      <Btn label={t("Con trỏ (Esc)")} active={tool === "cursor"} onClick={() => setTool("cursor")}><MousePointer2 size={17} aria-hidden="true" /></Btn>
      <span className="my-1 hidden h-px bg-line lg:block" />
      {TOOLS.filter((tl) => tl.id !== "cursor").map((tl) => (
        <Btn key={tl.id} label={`${tl.label} (${tl.key})`} active={tool === tl.id} onClick={() => setTool(tool === tl.id ? "cursor" : tl.id)}>{ICONS[tl.id]}</Btn>
      ))}
      <span className="my-1 hidden h-px bg-line lg:block" />
      <Btn label={t("Nam châm: bắt vào Open/High/Low/Close (G)")} active={magnet} onClick={() => setMagnet(!magnet)}><Magnet size={17} aria-hidden="true" /></Btn>
      <Btn label={visible ? t("Ẩn mọi hình vẽ") : t("Hiện hình vẽ")} active={!visible} onClick={() => setVisible(!visible)}>{visible ? <Eye size={17} aria-hidden="true" /> : <EyeOff size={17} aria-hidden="true" />}</Btn>
      <Btn label={t("Hoàn tác (Ctrl+Z)")} onClick={onUndo}><Undo2 size={17} aria-hidden="true" /></Btn>
      <Btn label={t("Xoá toàn bộ hình vẽ của mã/khung này")} danger onClick={onClear}><Trash2 size={17} aria-hidden="true" /></Btn>
    </div>
  );
}
