// Thành phần dùng chung cho các trang quản trị đội tài khoản. Màu luôn kèm biểu tượng + chữ.
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Check, Download, Info, Lock, Minus, RefreshCw, ShieldCheck, XOctagon, KeyRound } from "lucide-react";
import "../../fleet.css";
import { cn } from "../ui";
import { openTotpWizard, errText, downloadText } from "../../lib/fleetApi";
import { COMP_VN, usePerm } from "../../lib/fleetQueries";

/** Chú thích cố định: không có đặt lệnh ở bất kỳ màn hình nào. */
export function RoNote({ className, children = "Chỉ-đọc · không có đặt lệnh" }) {
  return <span className={cn("fl-ro", className)}><Lock size={11} aria-hidden="true" />{children}</span>;
}

export function useDebounced(v, ms = 300) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

export function Pill({ tone = "mute", icon: Icon, children, title, className }) {
  return <span className={cn("fl-pill", `t-${tone}`, className)} title={title}>{Icon && <Icon size={11} aria-hidden="true" />}{children}</span>;
}

const COMP = { green: { tone: "ok", icon: CheckCircle2 }, yellow: { tone: "warn", icon: AlertTriangle }, red: { tone: "bad", icon: XOctagon }, na: { tone: "mute", icon: Minus } };
/** Tuân thủ luật: xanh/vàng/đỏ + biểu tượng + chữ; nhãn "cũ" khi dữ liệu stale. */
export function CompStatus({ status, stale, sub }) {
  const s = COMP[status] || COMP.na;
  return (
    <span className="inline-flex items-center gap-1 flex-wrap">
      <Pill tone={s.tone} icon={s.icon}>{COMP_VN[status] || COMP_VN.na}{sub ? <span className="fl-pill-sub"> {sub}</span> : null}</Pill>
      {stale && <span className="fl-stale" title="Quá 10 phút chưa được đánh giá lại">cũ</span>}
    </span>
  );
}
export const compTone = (st) => (COMP[st] || COMP.na).tone;

/** Thanh dùng hạn mức: vạch 70% (mặc định "sát ngưỡng") và 100%. pct có thể >100 (tô đầy, nhãn vẫn ghi đúng số). */
export function UsageBar({ pct, status, headroom, unit, warnAt = 70, label, compact }) {
  const has = pct != null && Number.isFinite(pct);
  const tone = compTone(status || (!has ? "na" : pct >= 100 ? "red" : pct >= warnAt ? "yellow" : "green"));
  const w = has ? Math.max(0, Math.min(100, pct)) : 0;
  return (
    <div className={cn("fl-usage", `t-${tone}`)}>
      {!compact && <div className="fl-usage-top"><span className="num">{has ? `${pct.toFixed(1)}%` : "—"}<span className="fl-sr"> đã dùng hạn mức</span></span>{label && <span className="text-muted">{label}</span>}</div>}
      <div className="fl-usage-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={has ? Math.round(w) : undefined} aria-label={label || "Mức dùng hạn mức"} aria-valuetext={has ? `${pct.toFixed(1)}%` : "chưa có dữ liệu"}>
        <div className="fl-usage-fill" style={{ width: `${w}%` }} />
        <span className="fl-usage-mark" style={{ left: `${warnAt}%` }} aria-hidden="true" />
      </div>
      {!compact && headroom != null && <div className="fl-usage-sub"><span>Dư địa còn lại</span><span className="num">{typeof headroom === "number" ? `${headroom.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ""}` : headroom}</span></div>}
    </div>
  );
}

export function GroupChip({ g, onRemove }) {
  const c = /^#[0-9a-f]{3,8}$/i.test(g?.color || "") ? g.color : null;
  return (
    <span className="fl-gchip" style={c ? { "--c": c } : undefined} title={g?.name}>
      <i aria-hidden="true" /><span>{g?.name}</span>
      {onRemove && <button type="button" className="fl-chip-x" onClick={onRemove} aria-label={`Gỡ khỏi nhóm ${g?.name}`}>×</button>}
    </span>
  );
}
export function TagChip({ t, onRemove }) {
  return <span className="fl-tchip">#{t}{onRemove && <button type="button" className="fl-chip-x" onClick={onRemove} aria-label={`Gỡ tag ${t}`}>×</button>}</span>;
}

export function Banner({ tone = "info", icon, title, children, actions, className, role }) {
  const Icon = icon || (tone === "bad" ? XOctagon : tone === "warn" ? AlertTriangle : tone === "ok" ? ShieldCheck : Info);
  return (
    <div role={role || (tone === "bad" ? "alert" : "note")} className={cn("fl-banner", `t-${tone}`, className)}>
      <Icon size={16} aria-hidden="true" />
      <div className="fl-banner-b">{title && <b className="block">{title}</b>}{children}</div>
      {actions && <div className="fl-banner-a">{actions}</div>}
    </div>
  );
}

/** Route/API chưa có: không crash, nói rõ & tự thử lại khi người dùng bấm. */
export function Unavailable({ what = "Tính năng này", error, onRetry, retrying }) {
  const net = error?.code === "network";
  return (
    <div className="fl-empty" role="status">
      <b>{net ? "Không kết nối được máy chủ" : `${what} chưa khả dụng`}</b>
      <span>{net ? "Kiểm tra mạng rồi thử lại." : "Máy chủ chưa mở mục này (đang được triển khai). Trang sẽ tự dùng được khi API sẵn sàng — bấm “Kiểm tra lại” để thử ngay."}</span>
      {onRetry && <button type="button" className="btn mt-1" onClick={onRetry} disabled={retrying}><RefreshCw size={13} aria-hidden="true" />{retrying ? "Đang kiểm tra…" : "Kiểm tra lại"}</button>}
    </div>
  );
}

/** Dòng lỗi của một thao tác; lỗi totp_required kèm nút dẫn tới trình hướng dẫn bật TOTP. */
export function ErrLine({ error, className }) {
  if (!error) return null;
  return (
    <div role="alert" className={cn("fl-banner t-bad", className)}>
      <XOctagon size={16} aria-hidden="true" />
      <div className="fl-banner-b">{errText(error)}</div>
      {error.code === "totp_required" && <div className="fl-banner-a"><button type="button" className="btn" onClick={openTotpWizard}><KeyRound size={13} aria-hidden="true" />Bật TOTP ngay</button></div>}
    </div>
  );
}

export function Hint({ text }) {
  return <span className="fl-hint" tabIndex={0} role="img" aria-label={text} data-tip={text}>?</span>;
}

export function Field({ label, hint, help, error, htmlFor, children, className }) {
  return (
    <div className={cn("fl-field", className)}>
      {label && <label htmlFor={htmlFor}>{label}{hint && <Hint text={hint} />}</label>}
      {children}
      {help && <span className="fl-help">{help}</span>}
      {error && <span className="fl-err" role="alert">{error}</span>}
    </div>
  );
}

/** Nút có kiểm tra quyền: bị khoá kèm lý do (title + chữ cho trình đọc). KHÔNG thay thế kiểm tra phía máy chủ. */
export function GBtn({ perm, master, className, children, disabled, title, onClick, type = "button", ...rest }) {
  const p = usePerm();
  const why = p.reason(perm, { master });
  const off = !!why || disabled;
  return (
    <button type={type} className={cn("btn", className, why && "opacity-60")} disabled={off} aria-disabled={off || undefined} title={why || title} onClick={onClick} {...rest}>
      {children}{why && <span className="fl-sr"> ({why})</span>}
    </button>
  );
}
export const PRIMARY = "!bg-accent !text-[color:var(--accent-fg)] !border-transparent";

export function CopyBtn({ text, label = "Sao chép", small, className }) {
  const [done, setDone] = useState(false);
  useEffect(() => { if (!done) return; const t = setTimeout(() => setDone(false), 1800); return () => clearTimeout(t); }, [done]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch { /* bỏ qua */ } ta.remove();
    }
    setDone(true);
  };
  return (
    <button type="button" className={cn("btn", small && "!h-7 !px-2 text-[11.5px]", className)} onClick={copy}>
      {done ? <Check size={13} className="text-up" aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}<span aria-live="polite">{done ? "Đã chép" : label}</span>
    </button>
  );
}

/**
 * Hiển thị bí mật MỘT lần: cảnh báo to, từng giá trị có nút chép, nút tải tệp, và PHẢI tick "đã lưu" mới được đóng.
 * items: [{k, v, note?}]. KHÔNG ghi vào storage/URL; chỉ sống trong state của component cha.
 */
export function SecretPanel({ items, title = "Bí mật chỉ hiển thị MỘT lần", filename, onAck, ackLabel = "Tôi đã lưu các giá trị này ở nơi an toàn" }) {
  const [ack, setAck] = useState(false);
  const rows = (items || []).filter((x) => x.v);
  const text = rows.map((x) => `${x.k}: ${x.v}`).join("\n");
  const first = useRef(null);
  useEffect(() => { first.current?.focus(); }, []);
  return (
    <div className="grid gap-2">
      <Banner tone="bad" icon={AlertTriangle} title={title} role="alert">Rời khỏi hộp thoại/trang này là MẤT — máy chủ không lưu bản rõ và không thể xem lại. Chép hoặc tải về ngay.</Banner>
      {rows.map((x, i) => (
        <div key={x.k} className="fl-secret">
          <span className="fl-secret-k">{x.k}{x.note ? ` · ${x.note}` : ""}</span>
          <span className="fl-secret-v" tabIndex={i === 0 ? 0 : undefined} ref={i === 0 ? first : undefined}>{x.v}</span>
          <CopyBtn text={x.v} small />
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <CopyBtn text={text} label="Chép tất cả" />
        {filename && <button type="button" className="btn" onClick={() => downloadText(filename, text, "text/plain;charset=utf-8")}><Download size={13} aria-hidden="true" />Tải tệp văn bản</button>}
      </div>
      <label className="fl-check"><input type="checkbox" checked={ack} onChange={(e) => { setAck(e.target.checked); onAck?.(e.target.checked); }} /><span>{ackLabel}</span></label>
    </div>
  );
}

/** Chặn đóng tab/tải lại khi còn bí mật chưa lưu. */
export function useLeaveGuard(active) {
  useEffect(() => {
    if (!active) return;
    const h = (e) => { e.preventDefault(); e.returnValue = ""; };
    addEventListener("beforeunload", h);
    return () => removeEventListener("beforeunload", h);
  }, [active]);
}

export const fmtPct = (v, dp = 1) => (v == null || !Number.isFinite(Number(v)) ? "—" : `${Number(v).toFixed(dp)}%`);
export const fmtNum = (v, dp = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toLocaleString("vi-VN", { maximumFractionDigits: dp }));
export const fmtDT = (t) => (t ? new Date(t).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");
export const fmtDTfull = (t) => (t ? new Date(t).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false }) : "—");
export const ago = (t, now = Date.now()) => {
  const x = t ? Date.parse(t) : NaN;
  if (!Number.isFinite(x)) return "—";
  const s = Math.max(0, (now - x) / 1000);
  if (s < 5) return "vừa xong";
  if (s < 60) return `${Math.round(s)} giây trước`;
  if (s < 3600) return `${Math.round(s / 60)} phút trước`;
  if (s < 86400) return `${Math.round(s / 3600)} giờ trước`;
  return `${Math.round(s / 86400)} ngày trước`;
};
