import { useMemo } from "react";
import { CalendarClock } from "lucide-react";
import { Async, ImpactDots, cn } from "../components/ui";
import { Surprise } from "../components/intel/CalendarPro";
import { useCalendar, useNow } from "../lib/queries";
import { countdown, date, dow, time } from "../lib/format";
import { dayKeyOf } from "../lib/calendarPro";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "calendar-pro", title: "Lịch kinh tế (nâng cao)", icon: CalendarClock, group: "Tin & lịch",
  desc: "Sự kiện sắp tới theo ngày: đếm ngược, thực tế / dự báo / kỳ trước, màu bất ngờ; lọc tác động và quốc gia.",
  defaultSize: { w: 10, h: 14 }, minSize: { w: 6, h: 6 },
  configSchema: [
    { key: "imp", label: "Tác động", type: "select", default: "high,med", options: [{ value: "high", label: "Chỉ cao" }, { value: "high,med", label: "Cao + vừa" }, { value: "high,med,low", label: "Tất cả" }] },
    { key: "hours", label: "Khoảng thời gian tới (giờ)", type: "number", default: 72, min: 6, max: 240, step: 6 },
    { key: "country", label: "Quốc gia (vd US, EU; trống = tất cả)", type: "text", default: "" },
  ],
};

export default function CalendarProWidget() {
  const { config } = useWidget();
  const now = useNow();
  const hours = Number(config.hours) || 72;
  const from = new Date(Math.floor(now / 600e3) * 600e3 - 3 * 3600e3).toISOString();
  const to = new Date(Date.parse(from) + (hours + 3) * 3600e3).toISOString();
  const q = useCalendar({ from, to, impact: config.imp || "high,med", order: "asc", limit: 300 });
  const cc = (config.country || "").toUpperCase().split(/[\s,]+/).filter(Boolean);
  const days = useMemo(() => {
    const m = new Map();
    for (const e of q.data?.items || []) { if (/^QA\b/i.test(e.title || "")) continue; if (cc.length && !cc.includes(e.country)) continue; const k = dayKeyOf(e.ts); if (!m.has(k)) m.set(k, []); m.get(k).push(e); }
    return [...m.entries()];
  }, [q.data, config.country]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="tm-fill tm-scroll">
      <Async q={q} rows={6} empty="Không có sự kiện trong khoảng này." isEmpty={() => !days.length}>
        {() => days.map(([k, evs]) => (
          <section key={k} aria-label={k}>
            <div className="sticky top-0 z-[1] px-2 py-[3px] bg-panel2 border-b border-line text-[11px] font-semibold uppercase tracking-wide text-muted">{dow(evs[0].ts)} {date(evs[0].ts)} · {evs.length} tin</div>
            {evs.map((e) => {
              const past = Date.parse(e.ts) < now - 30 * 60e3;
              const cd = countdown(e.ts, now);
              return (
                <a key={e.event_id} href="#/lich" className={cn("in-row no-underline text-fg", past && "opacity-70")}>
                  <span className="num text-[12px] w-[38px] shrink-0">{time(e.ts)}</span>
                  <span className="chip !px-[5px] shrink-0">{e.country || "—"}</span>
                  <ImpactDots impact={e.impact} />
                  <span className="flex-1 min-w-0 truncate text-[12.5px]" title={e.title}>{e.title}</span>
                  <span className={cn("num text-[12px] shrink-0", e.actual ? "font-bold" : "text-faint")}>{e.actual ?? "—"}</span>
                  <span className="num text-[11.5px] text-muted shrink-0 hidden sm:inline" title="Dự báo">{e.forecast ?? ""}</span>
                  {e.extra?.surprise && <Surprise sp={e.extra.surprise} />}
                  <span className="num text-[11px] text-accent shrink-0 w-[58px] text-right">{cd || ""}</span>
                </a>
              );
            })}
          </section>
        ))}
      </Async>
    </div>
  );
}
