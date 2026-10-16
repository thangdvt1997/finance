// Hộp thoại thuần React: role=dialog, aria-modal, bẫy focus, Esc đóng, khoá cuộn nền, trả focus khi đóng.
import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "./ui";

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Dialog({ open, onClose, title, description, children, footer, variant = "modal", initialFocus, labelledBy, className }) {
  const ref = useRef(null);
  const tid = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    const root = ref.current;
    const sc = document.documentElement.style;
    const oldOverflow = sc.overflow;
    sc.overflow = "hidden";
    const target = (initialFocus && root.querySelector(initialFocus)) || root.querySelector("[data-autofocus]") || root.querySelector(FOCUSABLE) || root;
    target.focus({ preventScroll: true });
    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); closeRef.current?.(); return; }
      if (e.key !== "Tab") return;
      const els = [...root.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (!els.length) { e.preventDefault(); return; }
      const first = els[0], last = els[els.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === root)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    root.addEventListener("keydown", onKey);
    return () => {
      root.removeEventListener("keydown", onKey);
      sc.overflow = oldOverflow;
      if (prev && prev.isConnected) prev.focus({ preventScroll: true });
    };
  }, [open, initialFocus]);

  if (!open) return null;
  const drawer = variant === "drawer";
  return createPortal(
    <div className={cn("fixed inset-0 z-[80] flex", drawer ? "justify-end items-stretch" : "items-start justify-center p-0 sm:p-6 sm:pt-[8vh]")}>
      <div className="absolute inset-0 bg-black/60" onMouseDown={() => onClose?.()} aria-hidden="true" />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={labelledBy || (title ? tid : undefined)} aria-describedby={description ? `${tid}-d` : undefined} tabIndex={-1}
        className={cn("relative flex flex-col bg-panel border border-line2 shadow-2xl outline-none min-h-0",
          drawer ? "w-full max-w-[640px] h-dvh border-y-0 border-r-0" : "w-full max-w-[560px] max-h-dvh sm:max-h-[84dvh] sm:rounded-lg", className)}>
        {title && (
          <div className="panel-h shrink-0">
            <h2 id={tid} className="!text-[14px]">{title}</h2>
            <button type="button" className="btn !px-2 ml-auto" onClick={() => onClose?.()} aria-label="Đóng"><X size={15} aria-hidden="true" /></button>
          </div>
        )}
        {description && <p id={`${tid}-d`} className="m-0 px-3 pt-2 text-[12.5px] text-muted">{description}</p>}
        <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
        {footer && <div className="shrink-0 border-t border-line p-3 flex flex-wrap items-center gap-2 justify-end">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
