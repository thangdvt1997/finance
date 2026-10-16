import { useEffect, useState } from "react";
import { AlertTriangle, Check, Copy, FlaskConical, Pause, Hourglass, WifiOff, Wifi, Activity, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { Chip, cn } from "../ui";
import { ageText } from "../../lib/freshness";
import { HEALTH_VN, RISK_VN, STATUS_VN } from "../../lib/clientsQueries";
import { getMode, setModePref, useBackendMode } from "../../lib/clientsApi";
import { resetMock } from "../../lib/clientsMock";

const HEALTH_ICON = { online: Wifi, lag: Activity, offline: WifiOff, never: WifiOff, pending: Hourglass, suspended: Pause };
const HEALTH_TONE = { online: "up", lag: "accent", offline: "down", never: "down", pending: "", suspended: "" };

/** Chip trạng thái kết nối EA: luôn có biểu tượng + chữ (không chỉ dựa vào màu). */
export function HealthChip({ row }) {
  const Icon = HEALTH_ICON[row.health] || Activity;
  const extra = row.age != null && (row.health === "online" || row.health === "lag" || row.health === "offline") ? ` · ${ageText(row.age)}` : "";
  return <Chip tone={HEALTH_TONE[row.health]} title={`Lần cuối nhận dữ liệu: ${row.lastData ? new Date(row.lastData).toLocaleString("vi-VN") : "chưa có"}`}><Icon size={11} aria-hidden="true" />{HEALTH_VN[row.health]}{extra}</Chip>;
}
export function StatusChip({ status }) {
  return <Chip tone={status === "active" ? "up" : status === "suspended" ? "down" : "accent"}>{STATUS_VN[status] || status}</Chip>;
}
export function RiskChip({ level, reasons }) {
  const Icon = level === "crit" ? ShieldAlert : level === "warn" ? AlertTriangle : level === "ok" ? ShieldCheck : ShieldQuestion;
  return <Chip tone={level === "crit" ? "down" : level === "warn" ? "accent" : level === "ok" ? "up" : ""} title={reasons?.join("; ")}><Icon size={11} aria-hidden="true" />{RISK_VN[level]}</Chip>;
}

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
    <button type="button" className={cn("btn", small && "!h-7 !px-2 text-[11.5px]", className)} onClick={copy} aria-live="polite">
      {done ? <Check size={13} className="text-up" aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}{done ? "Đã chép" : label}
    </button>
  );
}

/** Banner cho chế độ minh hoạ: chỉ hiện khi dịch vụ xác thực chưa sẵn sàng hoặc đang ép mock. */
export function ModeBanner() {
  const m = useBackendMode();
  const mock = m.pref === "mock" || (m.pref === "auto" && m.fell);
  if (!mock) return null;
  return (
    <div role="note" className="flex flex-wrap items-center gap-2 rounded-md border border-line2 bg-panel2 px-3 py-2 text-[12.5px]">
      <FlaskConical size={15} className="text-accent shrink-0" aria-hidden="true" />
      <span className="min-w-0"><b>Dữ liệu minh hoạ.</b> {m.pref === "mock" ? "Đang ép chế độ minh hoạ." : "Dịch vụ xác thực (auth) chưa sẵn sàng nên trang dùng dữ liệu giả; mọi thao tác chỉ ảnh hưởng bộ nhớ trình duyệt."}</span>
      <span className="ml-auto flex gap-2">
        <button className="btn !h-7" onClick={() => { resetMock(); setModePref(m.pref); location.reload(); }}>Đặt lại dữ liệu</button>
        <button className="btn !h-7" onClick={() => { setModePref("real"); location.reload(); }}>Thử nối dịch vụ thật</button>
      </span>
    </div>
  );
}
export const modeNow = getMode;

/** Một dòng "nhãn : giá trị" cho hồ sơ. */
export function KV({ k, children, mono }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-2 py-[5px] border-b border-line last:border-0 text-[12.5px]">
      <dt className="text-muted">{k}</dt><dd className={cn("m-0 min-w-0 break-words", mono && "num")}>{children ?? "—"}</dd>
    </div>
  );
}

export const shortId = (id) => (id || "").replace(/^mt([45]):/, "MT$1 · ");
export const fmtDT = (t) => (t ? new Date(t).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false }) : "—");
