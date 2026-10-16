// Banner trạng thái kết nối EA + độ tươi dữ liệu của tài khoản đang xem. Gọn khi bình thường, nổi bật khi bất thường, mở rộng xem chi tiết.
import { useCallback, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, Flag, MoonStar, PlugZap } from "lucide-react";
import { cn } from "./ui";
import TicketSheet from "./tickets";
import { useAuth } from "../lib/auth";
import { useClock } from "../lib/clock";
import { useAccountSnaps } from "../lib/queries";
import { connStatus, ageText } from "../lib/freshness";
import { closedFor } from "../lib/q_today";
import { dateTime } from "../lib/format";
import { t } from "../lib/i18n";

const TONE = {
  on: { dot: "on", fg: "var(--up)" },
  idle: { dot: "", fg: "var(--info)" },
  slow: { dot: "warn", fg: "var(--accent)", bg: "var(--accent-bg)" },
  off: { dot: "off", fg: "var(--down)", bg: "var(--down-bg)" },
  none: { dot: "off", fg: "var(--down)", bg: "var(--down-bg)" },
};
const CAT_FOR = { off: "ea_disconnected", none: "ea_disconnected", slow: "stale_data", idle: "other", on: "other" };

export default function StatusBanner() {
  const { active } = useAuth();
  const snaps = useAccountSnaps();
  const now = useClock();
  const [open, setOpen] = useState(false);
  const [report, setReport] = useState(false);
  const closeReport = useCallback(() => setReport(false), []);
  const snap = useMemo(() => (snaps.data || []).find((s) => s.account_id === active?.id) || null, [snaps.data, active?.id]);
  const symbols = useMemo(() => [...new Set((snap?.positions || []).map((p) => p.symbol))], [snap]);
  if (!active || (snaps.isPending && !snaps.data)) return null;
  const latency = snap?.latency_ms ?? snap?.ea_latency_ms ?? null;
  const s = connStatus({ ts: snap?.ts, nowMs: now, closed: closedFor(symbols, now), latencyMs: latency });
  const tone = TONE[s.state];
  const Icon = s.state === "idle" ? MoonStar : s.abnormal ? (s.state === "slow" ? AlertTriangle : PlugZap) : null;
  const ctx = { ea_state: s.state, age_s: s.ageS, latency_ms: s.latencyMs, label: s.label };
  const detail = s.state === "idle" ? t("Thị trường đóng cửa nên chưa có dữ liệu mới là bình thường, không phải lỗi. Số liệu sẽ cập nhật khi thị trường mở lại.")
    : s.state === "slow" ? t("Dữ liệu từ MT đến chậm. Số liệu có thể trễ vài phút; hãy kiểm tra mạng của máy chạy MT.")
    : s.state === "off" ? t("Chưa nhận dữ liệu mới từ MT trong hơn 10 phút. Số liệu có thể đã cũ. Kiểm tra MT còn mở, EA còn gắn trên biểu đồ và mạng ổn định.")
    : s.state === "none" ? t("Chưa có dữ liệu từ tài khoản này. Gắn EA lên biểu đồ MT4/MT5 theo hướng dẫn ở mục Cài đặt, dữ liệu sẽ hiện sau vài chục giây.")
    : t("Dữ liệu đang cập nhật bình thường.");
  const ageLabel = s.ageS == null ? t("chưa có") : ageText(s.ageS);
  const wide = s.abnormal;

  return (
    <>
      <section aria-label={t("Trạng thái dữ liệu")} className={cn("rounded-xl", wide ? "border px-3 py-2.5" : "")}
        style={wide ? { borderColor: `color-mix(in srgb, ${tone.fg} 55%, transparent)`, background: tone.bg } : undefined}>
        <button type="button" className="flex w-full items-center gap-2 text-left min-h-[44px] bg-transparent border-0 p-0 text-[13px] cursor-pointer" style={{ color: "inherit", font: "inherit" }}
          onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls="status-detail">
          {Icon ? <Icon size={wide ? 20 : 16} className="shrink-0" style={{ color: tone.fg }} aria-hidden="true" /> : <span className={cn("live-dot", tone.dot)} aria-hidden="true" />}
          <span className="min-w-0 flex-1">
            <span className={cn("block truncate", wide ? "font-semibold text-[14px]" : "text-muted")} style={wide ? { color: tone.fg } : undefined}>{s.label}<span className="font-normal text-muted"> · {ageLabel}</span></span>
            {wide && <span className="block text-[12.5px] text-muted">{t("Số liệu bên dưới có thể đã cũ.")}</span>}
          </span>
          {!wide && s.latencyMs != null && <span className="num text-[12px] text-faint shrink-0">{Math.round(s.latencyMs)} ms</span>}
          <ChevronDown size={16} className={cn("shrink-0 text-muted transition-transform", open && "rotate-180")} aria-hidden="true" />
          <span className="sr-only">{open ? t("Thu gọn chi tiết") : t("Xem chi tiết")}</span>
        </button>
        {(open || wide) && (
          <div id="status-detail" className="grid gap-2 pt-1 text-[13px]">
            {open && (
              <>
                <p className="m-0 text-muted">{detail}</p>
                <dl className="m-0 grid grid-cols-2 gap-x-3 gap-y-1 text-[12.5px] sm:grid-cols-4">
                  <div><dt className="text-faint">{t("Dữ liệu cuối")}</dt><dd className="m-0 num">{snap?.ts ? dateTime(snap.ts) : "—"}</dd></div>
                  <div><dt className="text-faint">{t("Tuổi dữ liệu")}</dt><dd className="m-0 num">{ageLabel}</dd></div>
                  <div><dt className="text-faint">{t("Độ trễ")}</dt><dd className="m-0 num">{s.latencyMs != null ? `${Math.round(s.latencyMs)} ms` : "—"}</dd></div>
                  <div><dt className="text-faint">{t("Tài khoản")}</dt><dd className="m-0 num truncate">{active.login}</dd></div>
                </dl>
              </>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={cn("btn sm", wide && "primary")} onClick={() => setReport(true)}><Flag size={15} aria-hidden="true" /> {t("Báo quản trị")}</button>
              {wide && !open && <span className="text-[12.5px] text-muted flex-1 basis-[12rem]">{detail}</span>}
            </div>
          </div>
        )}
      </section>
      {report && <TicketSheet accountId={active.id} ctx={ctx} initialCat={CAT_FOR[s.state]} onClose={closeReport} />}
    </>
  );
}
