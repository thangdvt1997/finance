// Vùng toast thống nhất (aria-live). Lỗi dùng role=alert; còn lại role=status (không ngắt lời trình đọc màn hình).
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, X } from "lucide-react";
import { cn } from "../ui";
import { dismissToast, useToasts } from "../../ux/bus";

const TONE = {
  info: { icon: Info, cls: "text-info" },
  ok: { icon: CheckCircle2, cls: "text-up" },
  warn: { icon: AlertTriangle, cls: "text-accent" },
  error: { icon: OctagonAlert, cls: "text-down" },
};

export function Toaster() {
  const list = useToasts();
  return (
    <div className="ux-toasts" aria-label="Thông báo nhanh" role="region">
      {list.map((t) => {
        const T = TONE[t.tone] || TONE.info;
        const Ic = T.icon;
        return (
          <div key={t.id} role={t.tone === "error" ? "alert" : "status"} className="ux-toast">
            <Ic size={16} className={cn("shrink-0 mt-[2px]", T.cls)} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-[13px] break-words">{t.title}</div>
              {t.body && <div className="text-[12.5px] text-muted break-words line-clamp-3">{t.body}</div>}
              {(t.href || t.onAction) && (
                <button type="button" className="ux-link mt-1" onClick={() => { t.onAction?.(); if (t.href) location.hash = t.href.replace(/^#?/, "#"); dismissToast(t.id); }}>{t.actionLabel || "Xem"}</button>
              )}
            </div>
            <button type="button" className="ux-x" aria-label="Đóng thông báo" onClick={() => dismissToast(t.id)}><X size={14} aria-hidden="true" /></button>
          </div>
        );
      })}
    </div>
  );
}
