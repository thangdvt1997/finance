import { CalendarClock } from "lucide-react";
import { Async, ImpactDots } from "../components/ui";
import { useNow, useOverview } from "../lib/queries";
import { countdown, date, time, dow } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "calendar-upcoming", title: "Lịch kinh tế sắp tới", icon: CalendarClock, group: "Tin & lịch", desc: "Sự kiện tác động vừa/cao trong 48 giờ tới, đếm ngược sự kiện cao kế tiếp.",
  defaultSize: { w: 6, h: 10 }, minSize: { w: 4, h: 4 },
  configSchema: [{ key: "high", label: "Chỉ sự kiện tác động cao", type: "bool", default: false }],
};

export default function CalendarUpcoming() {
  const { config } = useWidget();
  const ov = useOverview();
  const now = useNow(1000);
  return (
    <div className="tm-fill tm-scroll tm-pad">
      <Async q={ov} rows={5} empty="Không có sự kiện vừa/cao trong 48 giờ tới." isEmpty={(d) => !d.upcoming_events?.length}>
        {(d) => {
          const ev = d.upcoming_events.filter((e) => !config.high || e.impact === "high");
          const next = ev.find((e) => e.impact === "high" && new Date(e.ts) > now);
          return (
            <>
              {next && (
                <div className="mb-2 rounded-md border border-line2 bg-panel2 px-3 py-2">
                  <div className="tm-sub">Sự kiện TÁC ĐỘNG CAO kế tiếp</div>
                  <div className="num text-[22px] text-accent leading-none my-1">{countdown(next.ts, now)}</div>
                  <div className="font-semibold text-[12.5px] leading-snug">{next.country} · {next.title}</div>
                  <div className="tm-sub">{dow(next.ts)} {date(next.ts)} {time(next.ts)} · dự báo {next.forecast ?? "—"} · kỳ trước {next.previous ?? "—"}</div>
                </div>
              )}
              <ul className="m-0 p-0 list-none divide-y divide-line">
                {ev.slice(0, 30).map((e) => (
                  <li key={e.event_id} className="flex items-center gap-2 py-[5px] text-[12.5px]">
                    <ImpactDots impact={e.impact} />
                    <span className="num text-[11.5px] text-muted w-[78px] shrink-0">{date(e.ts)} {time(e.ts)}</span>
                    <span className="chip">{e.country || "—"}</span>
                    <span className="truncate flex-1" title={e.title}>{e.title}</span>
                    <span className="num text-[11.5px] text-muted shrink-0">{countdown(e.ts, now) ?? "đã ra"}</span>
                  </li>
                ))}
              </ul>
            </>
          );
        }}
      </Async>
    </div>
  );
}
