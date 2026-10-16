import { useEffect, useId, useRef } from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { AlertTriangle, Eye, Inbox, Info, RefreshCw, X } from "lucide-react";
import { useClock } from "../lib/clock";
import { ageText } from "../lib/freshness";
import { dateLocale, t } from "../lib/i18n";

export const cn = (...a) => twMerge(clsx(a));

export function Panel({ title, icon: Icon, right, children, className, bodyClass, pad = true, id }) {
  const hid = useId();
  return (
    <section className={cn("panel flex flex-col", className)} aria-labelledby={title ? hid : undefined} id={id}>
      {(title || right) && (
        <div className="panel-h">
          {Icon && <Icon size={15} className="text-muted shrink-0" aria-hidden="true" />}
          <h2 id={hid} className="truncate">{title}</h2>
          <div className="ml-auto flex items-center gap-2 min-w-0">{right}</div>
        </div>
      )}
      <div className={cn(pad && "panel-b", "min-h-0", bodyClass)}>{children}</div>
    </section>
  );
}

export function Skeleton({ rows = 4, h = 16, className }) {
  return (
    <div className={cn("grid gap-2", className)} role="status" aria-label={t("Đang tải")}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skel" style={{ height: h, width: `${96 - ((i * 13) % 30)}%` }} />)}
    </div>
  );
}

/** Trạng thái chuẩn: loading | error | empty | dữ liệu. */
export function Async({ q, empty = t("Chưa có dữ liệu."), hint, rows = 4, isEmpty, children }) {
  if (q.isPending) return <Skeleton rows={rows} />;
  if (q.isError)
    return (
      <div role="alert" className="flex flex-col items-start gap-2 text-sm">
        <div className="flex items-start gap-2 text-down"><AlertTriangle size={16} className="mt-[3px] shrink-0" aria-hidden="true" /> {q.error?.message || t("Không tải được dữ liệu.")}</div>
        <button className="btn" onClick={() => q.refetch()}><RefreshCw size={14} aria-hidden="true" /> {t("Thử lại")}</button>
      </div>
    );
  const data = q.data;
  const emptyNow = isEmpty ? isEmpty(data) : Array.isArray(data) ? data.length === 0 : data?.items ? data.items.length === 0 : !data;
  if (emptyNow)
    return (
      <div className="flex flex-col items-start gap-1 py-2 text-muted">
        <div className="flex items-start gap-2"><Inbox size={16} className="mt-[3px] shrink-0" aria-hidden="true" /> {empty}</div>
        {hint && <div className="text-[12.5px] text-faint">{hint}</div>}
      </div>
    );
  return children(data);
}

export const Chip = ({ tone, children, title, className }) => <span className={cn("chip", tone, className)} title={title}>{children}</span>;

export function Seg({ value, onChange, options, label, className, scroll }) {
  return (
    <div className={cn("seg", scroll && "scroll", className)} role="group" aria-label={label}>
      {options.map((o) => {
        const v = typeof o === "string" ? o : o.value;
        const l = typeof o === "string" ? o : o.label;
        return <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>;
      })}
    </div>
  );
}

export function PageHead({ title, sub, right }) {
  return (
    <div className="page-head flex flex-wrap items-end gap-3">
      <div className="min-w-0 flex-1 basis-[16rem]"><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

/** Hộp thông báo: tone = info | warn | down | up. */
export function Notice({ tone = "info", icon: Icon, title, children, action, className }) {
  const T = { info: ["var(--info)", "var(--info-bg)"], warn: ["var(--accent)", "var(--accent-bg)"], down: ["var(--down)", "var(--down-bg)"], up: ["var(--up)", "var(--up-bg)"] }[tone];
  const I = Icon || (tone === "info" ? Info : AlertTriangle);
  return (
    <div role={tone === "down" ? "alert" : "note"} className={cn("flex gap-2.5 items-start rounded-xl border px-3 py-2.5 text-[13px]", className)} style={{ borderColor: `color-mix(in srgb, ${T[0]} 45%, transparent)`, background: T[1] }}>
      <I size={17} className="shrink-0 mt-[1px]" style={{ color: T[0] }} aria-hidden="true" />
      <div className="min-w-0 flex-1">{title && <div className="font-semibold">{title}</div>}<div className={title ? "text-muted" : ""}>{children}</div></div>
      {action}
    </div>
  );
}

export const Disclaimer = ({ children }) => <Notice tone="warn">{children}</Notice>;

/** Nhãn bắt buộc: chỉ theo dõi, không đặt lệnh. */
export const ReadOnlyChip = () => (
  <Chip tone="info" title={t("Hệ thống chỉ theo dõi và phân tích. Không thể đặt, sửa hay đóng lệnh trên tài khoản của bạn.")}><Eye size={12} aria-hidden="true" /> {t("Chỉ theo dõi, không đặt lệnh")}</Chip>
);

export function Kpi({ label, value, sub, tone, big }) {
  return (
    <div className="kpi">
      <div className="k">{label}</div>
      <div className={cn("v", tone, big && "!text-[22px]")}>{value}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

export function Meter({ value, max = 100, color = "var(--accent)", label }) {
  const p = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="meter" role="progressbar" aria-label={label} aria-valuenow={Math.round(p)} aria-valuemin={0} aria-valuemax={100}>
      <i style={{ width: `${p}%`, background: color }} />
    </div>
  );
}

/** Huy hiệu tuổi dữ liệu (không có tên nguồn). */
export function AgeChip({ ts, warn = 60, stale = 300, label = t("Cập nhật") }) {
  const now = useClock();
  const tm = ts ? new Date(ts).getTime() : NaN;
  if (!Number.isFinite(tm)) return <Chip tone="down">{t("chưa có dữ liệu")}</Chip>;
  const a = Math.max(0, (now - tm) / 1000);
  const tone = a <= warn ? "up" : a <= stale ? "accent" : "down";
  return <Chip tone={tone} title={`${label}: ${new Date(tm).toLocaleString(dateLocale())}`}>{ageText(a)}</Chip>;
}

/** Hộp thoại dạng sheet (đáy trên mobile, giữa trên desktop). Esc / bấm nền để đóng; khoá cuộn nền. */
export function Sheet({ title, onClose, children }) {
  const ref = useRef(null);
  const tid = useId();
  useEffect(() => {
    const prev = document.activeElement;
    const on = (e) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", on);
    document.body.style.overflow = "hidden";
    ref.current?.querySelector("a,button,input,select,textarea")?.focus();
    return () => { removeEventListener("keydown", on); document.body.style.overflow = ""; prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="sheet-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={tid} ref={ref}>
        <div className="grab" aria-hidden="true" />
        <div className="flex items-center gap-2 mb-2">
          <h2 id={tid} className="m-0 text-[16px] font-semibold flex-1">{title}</h2>
          <button className="ibtn" onClick={onClose} aria-label={t("Đóng")}><X size={18} aria-hidden="true" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, hint, error, children }) {
  return (
    <label className="label">
      <span>{label}</span>
      {children}
      {hint && !error && <span className="text-[12px] text-faint font-normal">{hint}</span>}
      {error && <span className="text-[12px] text-down font-normal" role="alert">{error}</span>}
    </label>
  );
}
