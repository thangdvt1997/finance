// Thành phần dùng chung cho Terminal và widget: Popover/Menu (portal), chọn mã, chọn kênh màu, nhãn trạng thái lưu.
import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check } from "lucide-react";
import { cn } from "../components/ui";
import { useSymbols } from "../lib/queries";
import { symbolLabel } from "../lib/format";
import { CHANNELS, chColor } from "./store";

/** Ngữ cảnh widget: widget có thể gọi useWidget() thay vì nhận props. */
export const WidgetContext = createContext(null);
export const useWidget = () => useContext(WidgetContext);

const FOCUSABLE = 'button:not([disabled]),[role="menuitem"],[role="menuitemcheckbox"],input,select,a[href]';

/** Popover neo vào nút; render trong portal (không bị overflow của widget cắt). children(close) trả về nội dung. */
export function Popover({ trigger, children, align = "end", label, width = 220, className }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btn = useRef(null);
  const pop = useRef(null);
  const id = useId();
  const close = useCallback(() => { setOpen(false); btn.current?.focus({ preventScroll: true }); }, []);

  useLayoutEffect(() => {
    if (!open || !btn.current) return;
    const r = btn.current.getBoundingClientRect();
    const w = Math.min(width, innerWidth - 16);
    let left = align === "end" ? r.right - w : r.left;
    left = Math.max(8, Math.min(left, innerWidth - w - 8));
    const below = innerHeight - r.bottom;
    const top = below > 220 || below > r.top ? r.bottom + 4 : undefined;
    setPos({ left, width: w, top, bottom: top === undefined ? innerHeight - r.top + 4 : undefined, maxH: Math.max(160, (top === undefined ? r.top : below) - 12) });
  }, [open, align, width]);

  useEffect(() => {
    if (!open) return;
    const away = (e) => { if (!pop.current?.contains(e.target) && !btn.current?.contains(e.target)) setOpen(false); };
    const key = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); close(); }
      else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const els = [...(pop.current?.querySelectorAll(FOCUSABLE) || [])];
        if (!els.length) return;
        e.preventDefault();
        const i = els.indexOf(document.activeElement);
        els[(i + (e.key === "ArrowDown" ? 1 : -1) + els.length) % els.length].focus();
      }
    };
    const rz = () => setOpen(false);
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("keydown", key, true);
    addEventListener("resize", rz);
    return () => { document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", key, true); removeEventListener("resize", rz); };
  }, [open, close]);

  useEffect(() => { if (open && pos) pop.current?.querySelector(FOCUSABLE)?.focus({ preventScroll: true }); }, [open, !!pos]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      {trigger({ ref: btn, "aria-haspopup": "true", "aria-expanded": open, "aria-controls": open ? id : undefined, onClick: (e) => { e.stopPropagation(); setOpen((v) => !v); } })}
      {open && createPortal(
        <div ref={pop} id={id} role="menu" aria-label={label}
          className={cn("fixed z-[95] rounded-md border border-line2 bg-panel shadow-2xl overflow-auto tm-pop", className)}
          style={{ left: pos?.left ?? -999, top: pos?.top, bottom: pos?.bottom, width: pos?.width ?? width, maxHeight: pos?.maxH, visibility: pos ? "visible" : "hidden" }}>
          {children(close)}
        </div>, document.body)}
    </>
  );
}

/** Menu thao tác: items = [{label, icon, onClick, danger, checked, sep, disabled}] */
export function MenuList({ items, close }) {
  return (
    <ul className="m-0 p-1 list-none">
      {items.map((it, i) => it.sep
        ? <li key={i} role="separator" className="my-1 border-t border-line" />
        : (
          <li key={i} role="none">
            <button type="button" role={it.checked != null ? "menuitemcheckbox" : "menuitem"} aria-checked={it.checked ?? undefined} disabled={it.disabled}
              onClick={() => { close(); it.onClick?.(); }}
              className={cn("w-full flex items-center gap-2 px-2 h-8 rounded text-left text-[12.5px] bg-transparent border-0 cursor-pointer hover:bg-panel2 focus-visible:bg-panel2 disabled:opacity-40", it.danger ? "text-down" : "text-fg")}>
              {it.icon ? <it.icon size={14} className="shrink-0 text-muted" aria-hidden="true" /> : <span className="w-[14px] shrink-0" />}
              <span className="flex-1 truncate">{it.label}</span>
              {it.checked && <Check size={13} className="text-accent" aria-hidden="true" />}
              {it.hint && <span className="text-[11px] text-faint">{it.hint}</span>}
            </button>
          </li>
        ))}
    </ul>
  );
}

/** Chọn kênh liên kết màu (hoặc "không liên kết"). */
export function ChannelPicker({ value, onChange, close }) {
  return (
    <div className="p-2" role="group" aria-label="Kênh liên kết">
      <div className="text-[11px] text-faint px-1 pb-1">Các widget cùng màu dùng chung mã đang xem.</div>
      <div className="flex flex-wrap gap-1.5 px-1 pb-1">
        {CHANNELS.map((c) => (
          <button key={c.id} type="button" role="menuitemradio" aria-checked={value === c.id} title={c.label} aria-label={c.label}
            onClick={() => { onChange(c.id); close?.(); }}
            className="w-7 h-7 rounded-full border-2 cursor-pointer grid place-items-center" style={{ background: c.color, borderColor: value === c.id ? "var(--fg)" : "transparent" }}>
            {value === c.id && <Check size={13} color="#10151c" aria-hidden="true" />}
          </button>
        ))}
      </div>
      <button type="button" role="menuitem" onClick={() => { onChange(null); close?.(); }} className="btn !h-7 w-full justify-center mt-1" disabled={!value}>Không liên kết</button>
    </div>
  );
}

export function ChannelDot({ channel, size = 9, className }) {
  const c = chColor(channel);
  return <span aria-hidden="true" className={cn("inline-block rounded-full shrink-0", !c && "border border-line2", className)} style={{ width: size, height: size, background: c || "transparent" }} />;
}

/** Ô nhập mã có gợi ý từ /v1/symbols. onChange chỉ gọi khi mã hợp lệ (Enter hoặc chọn từ gợi ý). */
export function SymbolInput({ value, onChange, placeholder = "Mã (vd: EURUSD)", className, label = "Mã", autoFocus }) {
  const list = useSymbols();
  const lid = useId();
  const [t, setT] = useState(value || "");
  useEffect(() => { setT(value || ""); }, [value]);
  const syms = useMemo(() => (list.data || []).map((s) => s.symbol), [list.data]);
  const commit = (v) => {
    const raw = v.trim();
    if (!raw) return;
    const hit = syms.find((s) => s.toLowerCase() === raw.toLowerCase()) || syms.find((s) => symbolLabel(s).toLowerCase() === raw.toLowerCase());
    if (hit) onChange(hit); else if (/^[A-Za-z0-9:._-]{1,32}$/.test(raw)) onChange(raw.toUpperCase());
  };
  return (
    <>
      <input className={cn("field", className)} list={lid} value={t} placeholder={placeholder} aria-label={label} autoComplete="off" spellCheck={false} autoFocus={autoFocus}
        onChange={(e) => { setT(e.target.value); if (syms.includes(e.target.value)) onChange(e.target.value); }}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(t); } }} onBlur={() => t && t !== value && commit(t)} />
      <datalist id={lid}>{syms.slice(0, 400).map((s) => <option key={s} value={s} />)}</datalist>
    </>
  );
}
