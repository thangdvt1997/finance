// Trạng thái chuẩn hoá: rỗng (có hướng dẫn hành động), lỗi (thử lại + chẩn đoán), khung tải cho bảng/biểu đồ, banner mất kết nối.
import { useEffect, useState } from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { AlertTriangle, Check, ChevronDown, Copy, Inbox, RefreshCw, ShieldAlert, WifiOff } from "lucide-react";
import { useStream, reconnectNow } from "../../lib/stream";

const cn = (...a) => twMerge(clsx(a));

/** Chẩn đoán lỗi tải dữ liệu thành lời khuyên dễ hiểu theo mã trạng thái. */
export function diagnose(err) {
  const s = err?.status;
  if (typeof navigator !== "undefined" && navigator.onLine === false) return { icon: WifiOff, title: "Thiết bị đang ngoại tuyến", tip: "Kiểm tra Wi-Fi/mạng của bạn. Giao diện sẽ tự tải lại khi có mạng." };
  if (s === 0) return { icon: WifiOff, title: "Không kết nối được máy chủ", tip: "Mạng chập chờn hoặc máy chủ đang khởi động lại. Thử lại sau vài giây." };
  if (s === 401) return { icon: ShieldAlert, title: "Phiên đăng nhập đã hết hạn", tip: "Tải lại trang để đăng nhập lại." };
  if (s === 403) return { icon: ShieldAlert, title: "Tài khoản không có quyền xem mục này", tip: "Mục này dành cho quản trị viên. Liên hệ người quản trị nếu bạn cần truy cập." };
  if (s === 404) return { icon: AlertTriangle, title: "Chưa có dữ liệu hoặc tính năng chưa được bật", tip: "Máy chủ chưa hỗ trợ mục này. Báo cho quản trị viên nếu bạn thấy bất thường." };
  if (s === 429) return { icon: AlertTriangle, title: "Bạn thao tác quá nhanh", tip: "Đợi vài giây rồi thử lại." };
  if (s >= 500) return { icon: AlertTriangle, title: "Máy chủ gặp sự cố tạm thời", tip: "Thường tự hết sau ít phút. Bấm Thử lại; nếu vẫn lỗi hãy xem trang Hệ thống." };
  return { icon: AlertTriangle, title: "Không tải được dữ liệu", tip: "Thử lại. Nếu lỗi lặp lại, xem trang Hệ thống để biết dịch vụ nào đang gặp vấn đề." };
}

export function ErrorState({ error, onRetry, retrying, what, compact, className }) {
  const d = diagnose(error);
  const Ic = d.icon;
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const detail = `${what ? `Mục: ${what}\n` : ""}Mã: ${error?.status ?? "n/a"}\nThông báo: ${error?.message || "—"}\nThời điểm: ${new Date().toISOString()}\nTrang: ${location.hash || "#/"}`;
  const copy = async () => { try { await navigator.clipboard.writeText(detail); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* không có clipboard */ } };
  return (
    <div role="alert" className={cn("ux-state ux-state-error", compact && "compact", className)}>
      <Ic size={compact ? 18 : 24} className="text-down shrink-0" aria-hidden="true" />
      <div className="min-w-0 grid gap-1">
        <b className="text-[13.5px]">{d.title}</b>
        <p className="m-0 text-muted text-[12.5px]">{d.tip}</p>
        <div className="flex flex-wrap items-center gap-2 mt-1">
          {onRetry && <button type="button" className="btn" onClick={onRetry} disabled={retrying}><RefreshCw size={13} className={retrying ? "ux-spin" : ""} aria-hidden="true" /> {retrying ? "Đang thử lại…" : "Thử lại"}</button>}
          <button type="button" className="ux-link inline-flex items-center gap-1" aria-expanded={open} onClick={() => setOpen(!open)}><ChevronDown size={13} className={cn("transition-transform", open && "rotate-180")} aria-hidden="true" /> Chi tiết kỹ thuật</button>
          <a className="ux-link" href="#/he-thong">Xem trạng thái hệ thống</a>
        </div>
        {open && (
          <div className="mt-1">
            <pre className="m-0 p-2 rounded-md bg-panel2 border border-line text-[11.5px] whitespace-pre-wrap break-words text-muted">{detail}</pre>
            <button type="button" className="ux-link inline-flex items-center gap-1 mt-1" onClick={copy}>{copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />} {copied ? "Đã sao chép" : "Sao chép để báo lỗi"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

/** Trạng thái rỗng có hướng dẫn: tiêu đề, giải thích, tối đa vài nút hành động. */
export function EmptyState({ icon: Icon = Inbox, title = "Chưa có dữ liệu", hint, actions, compact, className }) {
  return (
    <div className={cn("ux-state", compact && "compact", className)}>
      <Icon size={compact ? 18 : 26} className="text-faint shrink-0" aria-hidden="true" />
      <div className="min-w-0 grid gap-1">
        <b className="text-[13.5px]">{title}</b>
        {hint && <p className="m-0 text-muted text-[12.5px] max-w-[60ch]">{hint}</p>}
        {actions?.length ? (
          <div className="flex flex-wrap gap-2 mt-1">
            {actions.map((a) => a.href
              ? <a key={a.label} href={a.href} className="btn no-underline">{a.label}</a>
              : <button key={a.label} type="button" className="btn" onClick={a.onClick}>{a.label}</button>)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Khung tải cho bảng: tiêu đề cột + n dòng. */
export function TableSkeleton({ rows = 6, cols = 5, className }) {
  return (
    <div className={cn("grid gap-[6px]", className)} role="status" aria-label="Đang tải bảng">
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {Array.from({ length: cols }, (_, i) => <div key={i} className="skel" style={{ height: 11, width: `${55 + ((i * 17) % 35)}%` }} />)}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, c) => <div key={c} className="skel" style={{ height: 14, width: `${50 + ((r * 13 + c * 29) % 45)}%`, justifySelf: c === 0 ? "start" : c === cols - 1 ? "end" : "stretch" }} />)}
        </div>
      ))}
      <span className="sr-only">Đang tải dữ liệu bảng…</span>
    </div>
  );
}

/** Khung tải cho biểu đồ: giữ đúng chiều cao để không giật bố cục (CLS). */
export function ChartSkeleton({ height = 260, className }) {
  const bars = Array.from({ length: 28 }, (_, i) => 20 + ((i * 37) % 55));
  return (
    <div className={cn("ux-chart-skel", className)} style={{ height }} role="status" aria-label="Đang tải biểu đồ">
      <div className="flex items-end gap-[3px] h-full w-full" aria-hidden="true">
        {bars.map((h, i) => <div key={i} className="skel flex-1" style={{ height: `${h}%` }} />)}
      </div>
      <span className="sr-only">Đang tải biểu đồ…</span>
    </div>
  );
}

/** Banner trên cùng khi mất mạng hoặc mất kết nối realtime; tự biến mất khi nối lại. Chờ 4 giây trước khi hiện để tránh nháy lúc tải trang. */
export function ConnectionBanner() {
  const st = useStream();
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [late, setLate] = useState(false);
  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false);
    addEventListener("online", on); addEventListener("offline", off);
    return () => { removeEventListener("online", on); removeEventListener("offline", off); };
  }, []);
  const bad = !online || st.status !== "open";
  useEffect(() => {
    if (!bad) { setLate(false); return; }
    const t = setTimeout(() => setLate(true), online ? 4000 : 0);
    return () => clearTimeout(t);
  }, [bad, online]);
  if (!bad || !late) return <div className="sr-only" role="status" aria-live="polite" />;
  return (
    <div role="status" aria-live="polite" className="ux-banner">
      <WifiOff size={14} aria-hidden="true" className="shrink-0" />
      <span className="min-w-0">{!online ? "Thiết bị đang ngoại tuyến. Số liệu hiển thị có thể đã cũ." : "Mất kết nối dữ liệu thời gian thực. Đang tự nối lại… số liệu có thể đã cũ."}</span>
      {online && <button type="button" className="ux-link ml-auto shrink-0" onClick={reconnectNow}>Nối lại ngay</button>}
    </div>
  );
}
