import { ShieldAlert, TimerReset } from "lucide-react";
import { cn } from "./ui";
import { useNow } from "../lib/queries";
import { time } from "../lib/format";

/**
 * Bộ lọc rủi ro tin (api-gateway /v1/risk-windows). Quy ước nghiên cứu: không vào lệnh / giảm cỡ lệnh trong cửa sổ
 * T-15 … T+30 phút quanh sự kiện tác động CAO (vàng quanh FOMC/NFP tới T+45). Chỉ là cảnh báo hiển thị, hệ thống không đặt lệnh.
 */
const ms = (v) => new Date(v).getTime();
const mmss = (t) => {
  const s = Math.max(0, Math.ceil(t / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
const mins = (t) => Math.max(1, Math.ceil(t / 60000));
const human = (t) => {
  const m = Math.ceil(t / 60000);
  return m < 90 ? `${m} phút` : m < 2880 ? `${Math.floor(m / 60)} giờ ${m % 60 ? `${m % 60} phút` : ""}`.trim() : `${Math.round(m / 1440)} ngày`;
};

/** Trạng thái hiệu lực theo đồng hồ trình duyệt (đếm ngược mượt giữa 2 lần poll 30s). */
export function riskView(s, now) {
  if (!s) return { kind: "none" };
  const end = s.window_end && ms(s.window_end);
  const start = s.window_start && ms(s.window_start);
  if (s.state === "active" && end && end > now) return { kind: "active", left: end - now, end };
  if (s.state === "imminent" && start && start > now) return { kind: "imminent", left: start - now, start };
  if (s.state === "imminent" && start && end && start <= now && end > now) return { kind: "active", left: end - now, end };
  const nx = s.next_window;
  if (nx && ms(nx.start) > now) return { kind: "next", left: ms(nx.start) - now, title: nx.title };
  return { kind: "clear" };
}

const titleList = (s) => [...new Set((s?.current || []).map((e) => e.title))];

/** Banner đầy đủ cho 1 symbol (trang Thị trường). */
export function RiskBanner({ state, symbolLabel, className }) {
  const now = useNow(1000);
  const v = riskView(state, now);
  if (v.kind === "none" || v.kind === "clear") return null;
  const names = titleList(state);
  if (v.kind === "next") {
    // chỉ hiện gợi ý nhẹ nếu trong 6 giờ tới, tránh nhiễu
    if (v.left > 6 * 3600e3) return null;
    return (
      <div role="status" className={cn("flex items-center gap-2 rounded-md border border-line bg-panel2 px-3 py-[6px] text-[12.5px] text-muted", className)}>
        <TimerReset size={14} aria-hidden="true" className="shrink-0" />
        <span>Cửa sổ rủi ro tin kế tiếp{symbolLabel ? ` cho ${symbolLabel}` : ""}: <b className="text-fg font-semibold">{state.next_window.title}</b> · sau {human(v.left)} (từ {time(state.next_window.start)})</span>
      </div>
    );
  }
  const active = v.kind === "active";
  return (
    <div role="status" aria-live="polite"
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-3 py-2",
        active ? "border-[var(--down)] bg-[var(--down-bg)]" : "border-[var(--accent)] bg-[var(--accent-bg)]")}>
      <ShieldAlert size={18} aria-hidden="true" className={cn("shrink-0", active ? "text-down" : "text-accent")} />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-[13.5px]">
          {active ? <>Cửa sổ rủi ro tin: còn {mins(v.left)} phút</> : <>Sắp vào cửa sổ rủi ro tin: sau {mins(v.left)} phút</>}
          {symbolLabel && <span className="font-normal text-muted"> · {symbolLabel}</span>}
        </div>
        <div className="text-[12px] text-muted truncate" title={names.join(", ")}>
          {names.slice(0, 3).join(", ") || "Sự kiện tác động cao"}{names.length > 3 ? ` +${names.length - 3}` : ""} ·{" "}
          {active ? `không vào lệnh / giảm cỡ lệnh đến ${time(v.end)}` : `cửa sổ bắt đầu ${time(v.start)}, kết thúc ${state.window_end ? time(state.window_end) : "—"}`}
        </div>
      </div>
      <span className={cn("num text-[18px] tabular-nums", active ? "text-down" : "text-accent")} aria-hidden="true">{mmss(v.left)}</span>
    </div>
  );
}

/** Banner tổng hợp (trang Tổng quan): mọi symbol đang xem, gom theo trạng thái. */
export function RiskSummary({ data, labels = (s) => s, only }) {
  const now = useNow(1000);
  const list = (data?.symbols || []).filter((s) => !only || only.includes(s.symbol));
  const rows = list.map((s) => ({ s, v: riskView(s, now) }));
  const act = rows.filter((r) => r.v.kind === "active");
  const imm = rows.filter((r) => r.v.kind === "imminent");
  if (!act.length && !imm.length) {
    const nx = rows.filter((r) => r.v.kind === "next").sort((a, b) => a.v.left - b.v.left)[0];
    if (!nx || nx.v.left > 6 * 3600e3) return null;
    return (
      <div role="status" className="flex items-center gap-2 rounded-md border border-line bg-panel2 px-3 py-[6px] text-[12.5px] text-muted">
        <TimerReset size={14} aria-hidden="true" className="shrink-0" />
        <span>Cửa sổ rủi ro tin kế tiếp: <b className="text-fg font-semibold">{nx.s.next_window.title}</b> · sau {human(nx.v.left)} · ảnh hưởng {rows.filter((r) => r.v.kind === "next" && r.s.next_window.start === nx.s.next_window.start).map((r) => labels(r.s.symbol)).slice(0, 6).join(", ")}</span>
      </div>
    );
  }
  const top = act.length ? act : imm;
  const active = act.length > 0;
  const left = Math.max(...top.map((r) => r.v.left));
  const names = [...new Set(top.flatMap((r) => titleList(r.s)))];
  return (
    <div role="status" aria-live="polite"
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-3 py-2",
        active ? "border-[var(--down)] bg-[var(--down-bg)]" : "border-[var(--accent)] bg-[var(--accent-bg)]")}>
      <ShieldAlert size={18} aria-hidden="true" className={cn("shrink-0", active ? "text-down" : "text-accent")} />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-[13.5px]">
          {active ? <>Cửa sổ rủi ro tin: còn {mins(left)} phút</> : <>Sắp vào cửa sổ rủi ro tin: sau {mins(Math.min(...top.map((r) => r.v.left)))} phút</>}
        </div>
        <div className="text-[12px] text-muted">
          {names.slice(0, 3).join(", ")}{names.length > 3 ? ` +${names.length - 3}` : ""} · ảnh hưởng{" "}
          {top.map((r) => labels(r.s.symbol)).slice(0, 8).join(", ")}{top.length > 8 ? ` +${top.length - 8}` : ""}
          {active && imm.length > 0 ? ` · ${imm.length} mã sắp vào` : ""}
        </div>
      </div>
      <span className={cn("num text-[18px] tabular-nums", active ? "text-down" : "text-accent")} aria-hidden="true">{mmss(left)}</span>
    </div>
  );
}

/** Huy hiệu nhỏ theo dòng (bảng giá): "⚠ 12′" khi đang trong cửa sổ, "sắp" khi imminent. */
export function RiskBadge({ state }) {
  const now = useNow(5000);
  const v = riskView(state, now);
  if (v.kind !== "active" && v.kind !== "imminent") return null;
  const active = v.kind === "active";
  return (
    <span className={cn("chip", active ? "down" : "accent")} title={active ? `Cửa sổ rủi ro tin: còn ${mins(v.left)} phút — không vào lệnh/giảm cỡ lệnh` : `Sắp vào cửa sổ rủi ro tin sau ${mins(v.left)} phút`}>
      <ShieldAlert size={11} aria-hidden="true" />{active ? `${mins(v.left)}′` : `sau ${mins(v.left)}′`}
      <span className="sr-only">{active ? " phút còn lại trong cửa sổ rủi ro tin" : " phút nữa vào cửa sổ rủi ro tin"}</span>
    </span>
  );
}
