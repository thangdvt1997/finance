import { ShieldAlert, TimerReset } from "lucide-react";
import { cn } from "./ui";
import { useNow } from "../lib/queries";
import { symbolLabel, time } from "../lib/format";
import { t } from "../lib/i18n";

/** Cửa sổ rủi ro tin: T-15 … T+30 phút quanh sự kiện tác động CAO. Chỉ là cảnh báo hiển thị, hệ thống không đặt lệnh. */
const ms = (v) => new Date(v).getTime();
const mmss = (x) => { const s = Math.max(0, Math.ceil(x / 1000)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
const mins = (t) => Math.max(1, Math.ceil(t / 60000));
const human = (x) => { const m = Math.ceil(x / 60000); if (m < 90) return t("{n} phút", { n: m }); if (m < 2880) { const h = Math.floor(m / 60), r = m % 60; return r ? t("{h} giờ {m} phút", { h, m: r }) : t("{n} giờ", { n: h }); } return t("{n} ngày", { n: Math.round(m / 1440) }); };

export function riskView(s, now) {
  if (!s) return { kind: "none" };
  const end = s.window_end && ms(s.window_end), start = s.window_start && ms(s.window_start);
  if (s.state === "active" && end && end > now) return { kind: "active", left: end - now, end };
  if (s.state === "imminent" && start && start > now) return { kind: "imminent", left: start - now, start };
  if (s.state === "imminent" && start && end && start <= now && end > now) return { kind: "active", left: end - now, end };
  const nx = s.next_window;
  if (nx && ms(nx.start) > now) return { kind: "next", left: ms(nx.start) - now, title: nx.title };
  return { kind: "clear" };
}
const titles = (s) => [...new Set((s?.current || []).map((e) => e.title))];

/** Banner tổng hợp cho danh sách symbol (only = mã cần quan tâm; bỏ trống = tất cả). */
export function RiskBanner({ data, only, who = t("mã bạn đang giữ") }) {
  const now = useNow(1000);
  const list = (data?.symbols || []).filter((s) => !only || only.includes(s.symbol));
  const rows = list.map((s) => ({ s, v: riskView(s, now) }));
  const act = rows.filter((r) => r.v.kind === "active");
  const imm = rows.filter((r) => r.v.kind === "imminent");
  if (!act.length && !imm.length) {
    const nx = rows.filter((r) => r.v.kind === "next").sort((a, b) => a.v.left - b.v.left)[0];
    if (!nx || nx.v.left > 6 * 3600e3) return null;
    return (
      <div role="status" className="flex items-start gap-2 rounded-xl border border-line bg-panel2 px-3 py-2.5 text-[13px] text-muted">
        <TimerReset size={16} className="shrink-0 mt-[2px]" aria-hidden="true" />
        <span>{t("Cửa sổ rủi ro tin kế tiếp:")} <b className="text-fg">{nx.s.next_window.title}</b> · {t("sau {u}", { u: human(nx.v.left) })} ({t("từ {time}", { time: time(nx.s.next_window.start) })})</span>
      </div>
    );
  }
  const top = act.length ? act : imm;
  const active = act.length > 0;
  const left = active ? Math.max(...top.map((r) => r.v.left)) : Math.min(...top.map((r) => r.v.left));
  const names = [...new Set(top.flatMap((r) => titles(r.s)))];
  return (
    <div role="status" aria-live="polite" className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border px-3 py-2.5")}
      style={{ borderColor: active ? "var(--down)" : "var(--accent)", background: active ? "var(--down-bg)" : "var(--accent-bg)" }}>
      <ShieldAlert size={20} className={cn("shrink-0", active ? "text-down" : "text-accent")} aria-hidden="true" />
      <div className="min-w-0 flex-1 basis-[12rem]">
        <div className="font-semibold text-[14px]">{active ? t("Cửa sổ rủi ro tin: còn {n} phút", { n: mins(left) }) : t("Sắp vào cửa sổ rủi ro tin: sau {n} phút", { n: mins(left) })}</div>
        <div className="text-[12.5px] text-muted">
          {names.slice(0, 3).join(", ") || t("Sự kiện tác động cao")}{names.length > 3 ? ` +${names.length - 3}` : ""} · {t("ảnh hưởng {who}", { who })}: {top.map((r) => symbolLabel(r.s.symbol)).slice(0, 6).join(", ")}{top.length > 6 ? ` +${top.length - 6}` : ""}.
          {active ? ` ${t("Giá có thể biến động mạnh, cân nhắc giảm rủi ro.")}` : ""}
        </div>
      </div>
      <span className={cn("num text-[20px]", active ? "text-down" : "text-accent")} aria-hidden="true">{mmss(left)}</span>
    </div>
  );
}
