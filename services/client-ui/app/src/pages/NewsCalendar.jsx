import { useMemo, useState } from "react";
import { t } from "../lib/i18n";
import { CalendarClock, ExternalLink, Newspaper } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg, cn } from "../components/ui";
import { RiskBanner } from "../components/riskwin";
import { useActiveAccount } from "../lib/account";
import { useCalendar, useNews, useNow, useRiskAll } from "../lib/queries";
import { clean, countdown, dateTime, rel, symbolLabel, time, vnDayStart, date, dow } from "../lib/format";

const tabs = () => [{ value: "news", label: t("Tin tức") }, { value: "cal", label: t("Lịch kinh tế") }];
const IMPACT = { high: [() => t("Cao"), "down", 3], med: [() => t("Vừa"), "accent", 2], low: [() => t("Thấp"), "", 1] };

function Impact({ v }) {
  const [lf, tone] = IMPACT[v] || IMPACT.low;
  const label = lf();
  return <Chip tone={tone} title={t("Tác động {level}", { level: label.toLowerCase() })}>{label}</Chip>;
}

function Sentiment({ s }) {
  if (s == null) return null;
  const tone = s > 0.15 ? "up" : s < -0.15 ? "down" : "";
  return <Chip tone={tone} title={t("Sắc thái bài viết do máy phân tích, tham khảo")}>{s > 0.15 ? t("Tích cực") : s < -0.15 ? t("Tiêu cực") : t("Trung tính")}</Chip>;
}

function News({ held }) {
  const [mine, setMine] = useState(false);
  const [limit, setLimit] = useState(20);
  const q = useNews({ limit: mine ? 100 : limit });
  const all = q.data?.items || [];
  const items = mine ? all.filter((n) => (n.symbols || []).some((s) => held.includes(s))).slice(0, limit) : all;
  return (
    <>
      {held.length > 0 && <Seg value={mine ? "mine" : "all"} onChange={(v) => setMine(v === "mine")} options={[{ value: "all", label: t("Tất cả tin") }, { value: "mine", label: t("Liên quan vị thế của tôi") }]} label={t("Lọc tin")} scroll className="self-start" />}
      <Async q={q} rows={6} isEmpty={() => items.length === 0} empty={mine ? t("Chưa có tin liên quan các mã bạn đang giữ.") : t("Chưa có tin tức.")} hint={t("Tin được cập nhật liên tục từ nhiều đầu báo.")}>
        {() => (
          <>
            <ul className="list-none m-0 p-0 grid gap-2.5">
              {items.map((n) => (
                <li key={n.url} className="panel panel-b grid gap-1.5">
                  <a href={n.url} target="_blank" rel="noopener noreferrer" className="no-underline font-semibold leading-snug text-[14.5px] min-h-[44px] flex items-center">{clean(n.title)}</a>
                  {n.summary && <p className="m-0 text-[13px] text-muted line-clamp-2">{clean(n.summary)}</p>}
                  <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-faint">
                    <span title={dateTime(n.published_at)}>{rel(n.published_at)}</span>
                    <Sentiment s={n.sentiment} />
                    {(n.symbols || []).slice(0, 4).map((s) => <Chip key={s} tone={held.includes(s) ? "accent" : ""}>{symbolLabel(s)}</Chip>)}
                    <a href={n.url} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex items-center gap-1 min-h-[44px] px-1 text-muted no-underline">{t("Đọc bài gốc")} <ExternalLink size={13} aria-hidden="true" /></a>
                  </div>
                </li>))}
            </ul>
            {all.length >= limit && !mine && <button className="btn self-start" onClick={() => setLimit((l) => l + 20)}>{t("Tải thêm")}</button>}
          </>
        )}
      </Async>
    </>
  );
}

const DAYS = Array.from({ length: 8 }, (_, i) => i - 1);
function Calendar() {
  const [off, setOff] = useState(0);
  const [onlyHigh, setOnlyHigh] = useState(false);
  const now = useNow();
  const start = useMemo(() => vnDayStart(off), [off]);
  const end = useMemo(() => new Date(start.getTime() + 86400e3 - 1000), [start]);
  const q = useCalendar({ from: start.toISOString(), to: end.toISOString(), impact: onlyHigh ? "high" : "high,med", order: "asc", limit: 300 });
  const items = q.data?.items || [];
  const nextId = items.find((e) => new Date(e.ts) > now)?.event_id;
  return (
    <>
      <div className="flex gap-1.5 overflow-x-auto pb-1" role="tablist" aria-label={t("Chọn ngày")}>
        {DAYS.map((o) => {
          const d = vnDayStart(o);
          return (
            <button key={o} role="tab" aria-selected={o === off} onClick={() => setOff(o)} className={cn("shrink-0 min-w-[64px] min-h-[56px] rounded-xl px-2 py-1.5 text-center border font-[inherit] cursor-pointer", o === off ? "border-[var(--accent)] bg-[var(--accent-bg)]" : "border-line bg-panel")} style={{ color: "var(--fg)" }}>
              <div className="text-[11.5px] text-muted">{o === 0 ? t("Hôm nay") : dow(d)}</div><div className="num text-[14px]">{date(d)}</div>
            </button>);
        })}
      </div>
      <Seg value={onlyHigh ? "high" : "both"} onChange={(v) => setOnlyHigh(v === "high")} options={[{ value: "both", label: t("Tác động cao + vừa") }, { value: "high", label: t("Chỉ tác động cao") }]} label={t("Mức tác động")} scroll className="self-start" />
      <Async q={q} rows={6} empty={t("Không có sự kiện nào trong ngày này.")} hint={t("Thử chọn ngày khác hoặc bật thêm mức tác động.")}>
        {() => (
          <ul className="list-none m-0 p-0 grid gap-2">
            {items.map((e) => {
              const past = new Date(e.ts) <= now;
              const cd = !past ? countdown(e.ts, now) : null;
              return (
                <li key={e.event_id} className={cn("panel panel-b grid gap-1.5", e.event_id === nextId && "!border-[var(--accent)]")}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="num text-[14px] font-semibold">{time(e.ts)}</span><Impact v={e.impact} />{e.country && <Chip>{e.country}</Chip>}
                    {cd && <span className="num text-[12px] text-accent ml-auto">{t("còn {cd}", { cd })}</span>}
                  </div>
                  <div className="font-semibold leading-snug">{clean(e.title)}</div>
                  <div className="grid grid-cols-3 gap-2 text-[12.5px]">
                    <div><div className="text-faint">{t("Dự báo")}</div><div className="num">{e.forecast ?? "—"}</div></div>
                    <div><div className="text-faint">{t("Kỳ trước")}</div><div className="num">{e.previous ?? "—"}</div></div>
                    <div><div className="text-faint">{t("Thực tế")}</div><div className="num font-semibold">{e.actual ?? (past ? t("chờ") : "—")}</div></div>
                  </div>
                  {e.extra?.surprise?.verdict && <div className="text-[12px]"><Chip tone={e.extra.surprise.verdict === "good" ? "up" : e.extra.surprise.verdict === "bad" ? "down" : ""}>{{ good: t("Tốt cho đồng tiền"), bad: t("Xấu cho đồng tiền"), neutral: t("Đúng dự báo") }[e.extra.surprise.verdict]}</Chip></div>}
                </li>);
            })}
          </ul>
        )}
      </Async>
    </>
  );
}

export default function NewsCalendar({ query }) {
  const [tab, setTab] = useState(query?.tab === "cal" ? "cal" : "news");
  const { view } = useActiveAccount();
  const riskQ = useRiskAll();
  const held = useMemo(() => [...new Set((view?.positions || []).map((p) => p.symbol))], [view]);
  return (
    <>
      <PageHead title={t("Tin & Lịch kinh tế")} sub={t("Tin thị trường và sự kiện vĩ mô theo giờ Việt Nam.")} />
      <RiskBanner data={riskQ.data} only={held.length ? held : undefined} who={held.length ? t("mã bạn đang giữ") : t("các mã theo dõi")} />
      <Seg value={tab} onChange={setTab} options={tabs()} label={t("Chọn mục")} className="self-start" />
      {tab === "news" ? <News held={held} /> : <Calendar />}
      <Disclaimer>{t("Tin và lịch chỉ mang tính thông tin tham khảo, không phải khuyến nghị đầu tư.")}</Disclaimer>
    </>
  );
}
