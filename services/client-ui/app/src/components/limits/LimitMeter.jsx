import { AlertOctagon, AlertTriangle, CheckCircle2, CircleHelp, Target } from "lucide-react";
import { Chip, cn } from "../ui";
import { f0, f1, countdown } from "../../lib/format";
import { useClock } from "../../lib/clock";
import { limitMeta } from "../../lib/q_notif";
import { t } from "../../lib/i18n";

/** Giá trị theo loại giới hạn: số lệnh -> "7 lệnh"; còn lại -> "2.35%". */
export function limitValue(k, v, unit) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  if (k === "max_orders_day" || unit === "orders" || unit === "n") return t("{n} lệnh", { n: f0(v) });
  return `${f1(Number(v), Number(v) % 1 ? 2 : 0)}%`;
}

/** Trạng thái hiển thị: màu + biểu tượng + nhãn chữ (không chỉ dùng màu). Với mục tiêu tháng, "hit" = đạt mục tiêu (tốt). */
export function levelView(k, level) {
  const target = k === "monthly_target_pct";
  switch (level) {
    case "ok": return { tone: "up", color: "var(--up)", Icon: target ? Target : CheckCircle2, label: target ? t("Đang tiến tới mục tiêu") : t("Trong giới hạn") };
    case "warn": return { tone: "accent", color: "var(--accent)", Icon: AlertTriangle, label: target ? t("Đã quá nửa chặng đường") : t("Gần giới hạn") };
    case "danger": return { tone: "down", color: "var(--down)", Icon: AlertTriangle, label: target ? t("Sắp đạt mục tiêu") : t("Rất sát giới hạn") };
    case "hit": return target ? { tone: "up", color: "var(--up)", Icon: CheckCircle2, label: t("Đạt mục tiêu") } : { tone: "down", color: "var(--down)", Icon: AlertOctagon, label: t("Đã chạm giới hạn") };
    default: return { tone: "", color: "var(--muted)", Icon: CircleHelp, label: t("Chưa có số liệu") };
  }
}

/** Thanh tiến độ dạng bullet-bar: nền chia vùng 0-70 / 70-90 / 90-100%, thanh đậm = đã dùng bao nhiêu, vạch tại 70% và 90%. */
export function BulletBar({ ratio, color, label, valueText, compact }) {
  const known = ratio != null && Number.isFinite(Number(ratio));
  const p = known ? Math.max(0, Math.min(1, Number(ratio))) * 100 : 0;
  return (
    <div className="relative" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={known ? Math.round(Math.min(100, Number(ratio) * 100)) : undefined} aria-valuetext={valueText}>
      <div className={cn("relative rounded-md overflow-hidden", compact ? "h-2" : "h-3")}
        style={{ background: "linear-gradient(90deg, var(--panel2) 0 70%, var(--accent-bg) 70% 90%, var(--down-bg) 90% 100%)", boxShadow: "inset 0 0 0 1px var(--line)" }}>
        {known && <div className="h-full rounded-md motion-safe:transition-[width] motion-safe:duration-500" style={{ width: `${p}%`, background: color, minWidth: p > 0 ? 4 : 0 }} />}
        <span className="absolute top-0 bottom-0 w-px" style={{ left: "70%", background: "var(--line2)" }} aria-hidden="true" />
        <span className="absolute top-0 bottom-0 w-px" style={{ left: "90%", background: "var(--line2)" }} aria-hidden="true" />
      </div>
      {!compact && (
        <div className="relative h-4 text-[10.5px] text-faint mt-0.5 select-none" aria-hidden="true">
          <span className="absolute left-0">0%</span><span className="absolute -translate-x-1/2" style={{ left: "70%" }}>70%</span>
          <span className="absolute -translate-x-1/2" style={{ left: "90%" }}>90%</span><span className="absolute right-0">100%</span>
        </div>
      )}
    </div>
  );
}

/**
 * Đồng hồ tiến độ một giới hạn. Dùng lại ở màn Hôm nay và trang Giới hạn.
 * k: khoá giới hạn · item: {key,value,pending_value,pending_effective_at} · progress: {current,limit,ratio,remaining,unit,level,as_of} · compact: gọn một hàng.
 */
export default function LimitMeter({ k, item, progress, compact = false, showPending = true, className }) {
  const meta = limitMeta(k);
  const now = useClock();
  const value = item?.value ?? progress?.limit ?? null;
  const set = value != null;
  const pr = set ? progress : null;
  const lv = levelView(k, set ? pr?.level : null);
  const { Icon } = lv;
  const unit = pr?.unit;
  const pend = showPending && item?.pending_effective_at ? item : null;
  const pendTxt = pend ? (pend.pending_value == null ? t("bỏ giới hạn") : limitValue(k, pend.pending_value, unit)) : "";
  const left = pend ? countdown(pend.pending_effective_at, now) : null;

  if (!set) {
    return (
      <div className={cn(compact ? "flex items-center gap-2 text-[12.5px]" : "grid gap-1", className)}>
        <span className={compact ? "font-semibold shrink-0" : "font-semibold"}>{compact ? meta.short : meta.label}</span>
        <span className="text-muted">{t("Chưa đặt")}</span>
      </div>
    );
  }
  const cur = limitValue(k, pr?.current, unit), lim = limitValue(k, value, unit);
  const rest = pr?.remaining != null ? (k === "monthly_target_pct" ? t("Còn thiếu {v}", { v: limitValue(k, pr.remaining, unit) }) : t("Còn {v}", { v: limitValue(k, pr.remaining, unit) })) : null;
  const pctText = pr?.ratio != null ? `${Math.round(Number(pr.ratio) * 100)}%` : null;
  const vt = `${cur} / ${lim}${pctText ? `, ${pctText}` : ""}. ${lv.label}`;

  if (compact) {
    return (
      <div className={cn("grid gap-1", className)}>
        <div className="flex items-center gap-2 text-[12.5px] min-w-0">
          <Icon size={14} style={{ color: lv.color }} className="shrink-0" aria-hidden="true" />
          <span className="font-semibold truncate">{meta.short}</span>
          <span className="num ml-auto shrink-0" style={{ color: lv.color }}>{cur} <span className="text-faint">/ {lim}</span></span>
        </div>
        <BulletBar ratio={pr?.ratio} color={lv.color} label={meta.label} valueText={vt} compact />
        <div className="text-[11.5px]" style={{ color: lv.color }}>{lv.label}{left && <span className="text-faint"> · {t("chờ đổi sang {v}", { v: pendTxt })}</span>}</div>
      </div>
    );
  }
  return (
    <div className={cn("grid gap-1.5", className)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-semibold text-[14px]">{meta.label}</span>
        <Chip tone={lv.tone}><Icon size={12} aria-hidden="true" /> {lv.label}</Chip>
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="num text-[20px] font-bold" style={{ color: lv.color }}>{cur}</span>
        <span className="text-muted text-[13px]">{t("trên giới hạn")} <b className="num text-fg">{lim}</b></span>
        {rest && <span className="text-[12.5px] text-muted ml-auto">{rest}</span>}
      </div>
      <BulletBar ratio={pr?.ratio} color={lv.color} label={meta.label} valueText={vt} />
      {left && <div className="text-[12.5px] text-muted">{t("Chờ hiệu lực: đổi sang {v} sau {d}", { v: pendTxt, d: left })}</div>}
    </div>
  );
}
