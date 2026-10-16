// Lịch kinh tế chuyên nghiệp: lưới tuần / bảng ngày, lọc quốc gia-tác động-nhóm chỉ số, đếm ngược, màu "bất ngờ", cụm cửa sổ rủi ro,
// panel chi tiết với lịch sử thực tế-dự báo-kỳ trước, nhắc trước sự kiện (trình duyệt) và tạo cảnh báo máy chủ. Giờ hiển thị: giờ VN.
import { useEffect, useMemo, useState } from "react";
import { AlarmClock, ArrowDown, ArrowUp, BellPlus, CalendarClock, ChevronLeft, ChevronRight, Download, Equal, Search, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import * as echarts from "echarts/core";
import { LegendComponent } from "echarts/components";
import { Dialog } from "../dialog";
import { EChart, css } from "../charts";
import { Async, ImpactDots, Panel, Seg, Skeleton, cn } from "../ui";
import { QState } from "./bits";
import { useCalHistory } from "../../lib/intel";
import { useCalendar, useNow } from "../../lib/queries";
import { apiWrite } from "../../lib/api";
import { buildPayload, emptyForm, mapServerErrors } from "../../lib/rules";
import { CCY_OF, COUNTRY_NAME, GROUP_LABEL, GROUPS, addReminder, dayKey, dayKeyOf, download, groupOf, impCls, impN, removeReminder, riskWindows, slotsOf, toCsv, tzLabel, useReminderTicker, useReminders, vnWeekStart, weekDays, weekEnd } from "../../lib/calendarPro";
import { countdown, date, dateTime, dow, time } from "../../lib/format";
import { toast } from "../../ux/bus";
import { useLocal, useMedia } from "./bits";

echarts.use([LegendComponent]);

const VERDICT = {
  good: { cls: "up", bg: "bg-[var(--up-bg)]", label: "Tốt cho đồng tiền" },
  bad: { cls: "down", bg: "bg-[var(--down-bg)]", label: "Xấu cho đồng tiền" },
  neutral: { cls: "flat", bg: "bg-panel2", label: "Đúng dự báo" },
};
function fmtSurprise(sp) {
  const u = sp.unit === "%" ? "%" : sp.unit || "";
  const a = Math.abs(sp.value);
  const dp = a >= 100 ? 0 : a >= 10 ? 1 : 2;
  const num = (a === 0 ? 0 : +a.toFixed(dp)).toString();
  return `${sp.value > 0 ? "+" : sp.value < 0 ? "−" : ""}${num}${u}`;
}
export function Surprise({ sp }) {
  if (!sp) return <span className="text-faint">—</span>;
  const v = VERDICT[sp.verdict] || VERDICT.neutral;
  const Icon = sp.direction === "above" ? ArrowUp : sp.direction === "below" ? ArrowDown : Equal;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-[1px] text-[12px] font-semibold", v.bg, v.cls)}
      title={`${v.label}. Thực tế − dự báo = ${fmtSurprise(sp)}; z = ${sp.z > 0 ? "+" : ""}${sp.z}${sp.polarity < 0 ? " (chỉ số càng cao càng xấu)" : ""}`}>
      <Icon size={11} aria-hidden="true" />{fmtSurprise(sp)}<span className="sr-only"> — {v.label}</span>
    </span>
  );
}
const verdictCls = (e) => VERDICT[e.extra?.surprise?.verdict]?.cls || "";
const IMP_TOGGLE = [{ k: "high", label: "Cao" }, { k: "med", label: "Vừa" }, { k: "low", label: "Thấp" }];

// ---------------------------------------------------------------- thẻ sự kiện (lưới tuần)
function EventCard({ e, now, selected, onSelect, remind }) {
  const past = Date.parse(e.ts) < now - 30 * 60e3;
  return (
    <button type="button" className={cn("cal-ev", impCls(e.impact), past && "past")} aria-pressed={selected} onClick={() => onSelect(e)}
      aria-label={`${time(e.ts)} ${e.country || ""} ${e.title}`}>
      <span className="flex items-center gap-1 text-[11px] text-muted"><span className="num">{time(e.ts)}</span><span className="chip !px-[5px] !py-0">{e.country || "—"}</span><ImpactDots impact={e.impact} />{remind && <AlarmClock size={11} className="text-accent ml-auto" aria-label="Đã đặt nhắc" />}</span>
      <span className="font-medium leading-tight line-clamp-2">{e.title}</span>
      <span className="flex gap-2 text-[11px] num">
        <span className={cn(e.actual ? `font-bold ${verdictCls(e) || "text-fg"}` : "text-faint")}>{e.actual ?? "—"}</span>
        <span className="text-muted" title="Dự báo">DB {e.forecast ?? "—"}</span>
        <span className="text-faint hidden xl:inline" title="Kỳ trước">KT {e.previous ?? "—"}</span>
      </span>
    </button>
  );
}

// ---------------------------------------------------------------- bảng sự kiện (ngày / tuần) có hàng tiêu đề theo cụm giờ
function EventTable({ events, now, selId, onSelect, remindIds, nextId }) {
  const slots = useMemo(() => slotsOf(events), [events]);
  if (!events.length) return null;
  return (
    <table className="tbl min-w-[780px]">
      <thead><tr><th>Giờ</th><th>QG</th><th>Tác động</th><th>Sự kiện</th><th className="r">Thực tế</th><th className="r">Dự báo</th><th className="r">Kỳ trước</th><th className="r" title="Thực tế − dự báo; màu theo tác động lên đồng tiền">Bất ngờ</th><th className="r">Còn lại</th></tr></thead>
      <tbody>
        {slots.map((s) => {
          const cd = countdown(s.ts, now);
          const multi = s.events.length > 1;
          return [
            multi && s.top >= 2 ? (
              <tr key={`h${s.ts}`} className="bg-panel2">
                <td colSpan={9} className="!py-[3px] text-[11.5px] text-muted"><b className={cn(s.top === 3 ? "down" : "text-accent")}>Cụm {time(s.ts)} · {s.events.length} tin</b> — cửa sổ biến động có thể xuất hiện quanh thời điểm này{cd ? ` (còn ${cd})` : ""}</td>
              </tr>
            ) : null,
            ...s.events.map((e) => {
              const x = e.extra || {};
              const sp = x.surprise;
              const vd = sp && VERDICT[sp.verdict];
              return (
                <tr key={e.event_id} onClick={() => onSelect(e)} aria-selected={selId === e.event_id} className={cn("cursor-pointer", selId === e.event_id && "bg-[var(--accent-bg)]", e.event_id === nextId && "outline outline-1 -outline-offset-1 outline-[var(--accent)]", Date.parse(e.ts) < now - 30 * 60e3 && "opacity-75")}>
                  <td className="num whitespace-nowrap">{time(e.ts)}</td>
                  <td><span className="chip">{e.country || "—"}</span></td>
                  <td><ImpactDots impact={e.impact} /></td>
                  <td className="font-medium"><button type="button" className="bg-transparent border-0 p-0 text-left text-fg font-medium cursor-pointer hover:text-accent" onClick={(ev) => { ev.stopPropagation(); onSelect(e); }}>{e.title}</button>{remindIds.has(e.event_id) && <AlarmClock size={12} className="inline ml-1 text-accent" aria-label="Đã đặt nhắc" />}</td>
                  <td className={cn("r num", e.actual ? "font-bold" : "text-faint", e.actual && (vd ? vd.cls : "text-fg"))} title={e.actual && x.actual_period ? `Kỳ ${x.actual_period}` : undefined}>{e.actual ?? "—"}</td>
                  <td className="r num text-muted">{e.forecast ?? "—"}</td>
                  <td className="r num text-muted">{e.previous ?? "—"}</td>
                  <td className="r"><Surprise sp={sp} /></td>
                  <td className="r num text-muted">{cd && s.ts === e.ts ? countdown(e.ts, now) : e.actual ? "đã ra" : Date.parse(e.ts) < now ? "chờ số" : countdown(e.ts, now)}</td>
                </tr>
              );
            }),
          ];
        })}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------- lịch sử chỉ số (thực tế / dự báo / kỳ trước)
function HistoryTable({ items }) {
  const rows = items.slice(-8).reverse();
  if (!rows.length) return <div className="text-[12px] text-faint">Chưa có lịch sử cho chỉ số này.</div>;
  return (
    <div className="grid gap-1">
      <div className="text-[12px] text-faint">Chưa đủ số liệu để vẽ biểu đồ; các kỳ đã có:</div>
      <table className="tbl"><thead><tr><th>Kỳ</th><th className="r">Thực tế</th><th className="r">Dự báo</th><th className="r">Kỳ trước</th></tr></thead>
        <tbody>{rows.map((i) => <tr key={i.ts}><td className="num">{date(i.ts)}/{String(new Date(i.ts).getFullYear()).slice(2)}</td><td className="r num">{i.actual_text ?? "—"}</td><td className="r num text-muted">{i.forecast_text ?? "—"}</td><td className="r num text-muted">{i.previous_text ?? "—"}</td></tr>)}</tbody></table>
    </div>
  );
}

function HistoryChart({ e }) {
  const h = useCalHistory(e.title, e.country || undefined);
  const nums = useMemo(() => (h.data?.items || []).filter((i) => i.actual != null || i.forecast != null || i.previous != null || i.actual_from_next != null), [h.data]);
  if (h.isPending) return <Skeleton rows={4} />;
  if (h.isError) return <div className="text-[12px] text-faint">Chưa có lịch sử cho chỉ số này (cần ≥ 2 kỳ).</div>;
  if (nums.length < 2) return <HistoryTable items={h.data?.items || []} />;
  const st = h.data.stats;
  const labels = nums.map((i) => date(i.ts) + "/" + String(new Date(i.ts).getFullYear()).slice(2));
  const build = () => {
    const accent = css("--accent"), info = css("--info"), faint = css("--faint"), line = css("--line2"), fg = css("--fg"), up = css("--up"), down = css("--down");
    const tip = { trigger: "axis", confine: true, backgroundColor: css("--panel"), borderColor: line, textStyle: { color: fg, fontSize: 12 },
      formatter: (ps) => { const i = nums[ps[0].dataIndex]; return `<b>${dateTime(i.ts)}</b>${i.period ? ` · kỳ ${i.period}` : ""}<br/>Thực tế: ${i.actual_text ?? (i.actual_from_next != null ? `${i.actual_from_next} (theo kỳ sau)` : "—")}<br/>Dự báo: ${i.forecast_text ?? "—"}<br/>Kỳ trước: ${i.previous_text ?? "—"}${i.surprise != null ? `<br/>Bất ngờ: ${i.surprise > 0 ? "+" : ""}${+i.surprise.toFixed(3)}` : ""}`; } };
    return {
      animation: false, tooltip: tip, legend: { top: 0, textStyle: { color: css("--muted"), fontSize: 11 }, itemWidth: 14, itemHeight: 8 },
      grid: { left: 44, right: 12, top: 26, bottom: 24 },
      xAxis: { type: "category", data: labels, axisLabel: { color: css("--muted"), fontSize: 10 }, axisLine: { lineStyle: { color: line } } },
      yAxis: { type: "value", scale: true, axisLabel: { color: css("--muted"), fontSize: 10 }, splitLine: { lineStyle: { color: css("--line") } } },
      series: [
        { name: "Thực tế", type: "line", data: nums.map((i) => i.actual), connectNulls: false, symbolSize: 7, lineStyle: { width: 2, color: accent }, itemStyle: { color: accent } },
        { name: "Thực tế (theo kỳ sau)", type: "line", data: nums.map((i) => i.actual_from_next), symbolSize: 7, symbol: "emptyCircle", lineStyle: { type: "dotted", color: accent, opacity: 0.6 }, itemStyle: { color: accent } },
        { name: "Dự báo", type: "line", data: nums.map((i) => i.forecast), symbolSize: 5, lineStyle: { type: "dashed", width: 1.5, color: info }, itemStyle: { color: info } },
        { name: "Kỳ trước", type: "line", data: nums.map((i) => i.previous), symbolSize: 4, lineStyle: { width: 1, color: faint }, itemStyle: { color: faint } },
      ].map((s) => ({ ...s, smooth: false })),
      color: [accent, accent, info, faint, up, down],
    };
  };
  return (
    <div className="grid gap-2">
      <EChart build={build} deps={[nums]} height={210} label={`Lịch sử ${e.title}`} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-muted">
        <span>{h.data.count} kỳ · có số thực tế: <b className="num text-fg">{st.n_actual}</b></span>
        {st.beat_pct != null && <span>Vượt dự báo: <b className="num text-fg">{st.beat_pct}%</b> ({st.n_surprise} kỳ)</span>}
        {st.avg_surprise != null && <span>Bất ngờ TB: <b className="num text-fg">{st.avg_surprise > 0 ? "+" : ""}{st.avg_surprise}</b></span>}
      </div>
      {st.n_actual < 3 && <div className="text-[11.5px] text-faint">Số liệu thực tế mới tích luỹ từ gần đây nên biểu đồ chủ yếu hiển thị dự báo và kỳ trước; điểm rỗng = theo giá trị “kỳ trước” của lần công bố sau.</div>}
    </div>
  );
}

function ReminderDialog({ e, onClose }) {
  const [lead, setLead] = useState("15");
  const [server, setServer] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const qc = useQueryClient();
  const ccy = CCY_OF[e.country] || "";
  const save = async () => {
    setErr("");
    addReminder(e, Number(lead));
    if (server) {
      setBusy(true);
      const f = { ...emptyForm(), name: `Nhắc tin ${e.country || ""} tác động ${e.impact === "high" ? "cao" : "vừa"} trước ${lead} phút`.slice(0, 80), conditions: [{ type: "news_window", impact: e.impact === "high" ? "high" : "med", within_min: lead, country: e.country || "", phase: "upcoming" }], mode: "repeat", cooldown_min: "60", level: "warn", channels: ["ntfy", "log"], note: "Tạo từ Lịch kinh tế" };
      const { payload, errors } = buildPayload(f);
      if (Object.keys(errors).length) { setErr(Object.values(errors)[0]); setBusy(false); return; }
      try { await apiWrite("POST", "/user/rules", payload); await qc.invalidateQueries({ queryKey: ["user-rules"] }); }
      catch (x) { const m = mapServerErrors(x); setErr(m.general[0] || Object.values(m.errors)[0] || x.message); setBusy(false); return; }
      setBusy(false);
    }
    toast({ tone: "ok", title: "Đã đặt nhắc", body: `${e.title} · trước ${lead} phút${server ? " · và quy tắc cảnh báo máy chủ" : ""}` });
    onClose();
  };
  return (
    <Dialog open onClose={onClose} title="Đặt nhắc trước sự kiện" footer={<><button type="button" className="btn" onClick={onClose}>Huỷ</button><button type="button" className="btn !bg-accent !text-[var(--accent-fg)] !border-transparent" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Đặt nhắc"}</button></>}>
      <div className="p-3 grid gap-3 text-[13px]">
        <div><b>{e.title}</b><div className="text-muted text-[12px]">{e.country} {ccy && `(${ccy})`} · {dateTime(e.ts)} {tzLabel()}</div></div>
        <label className="grid gap-1">Nhắc trước
          <select className="field" value={lead} onChange={(x) => setLead(x.target.value)}>{["5", "15", "30", "60"].map((m) => <option key={m} value={m}>{m} phút</option>)}</select>
        </label>
        <p className="m-0 text-[12px] text-muted">Nhắc hiện thông báo trong ứng dụng (kèm âm báo theo cài đặt) khi trang đang mở.</p>
        <label className="flex items-start gap-2 cursor-pointer"><input type="checkbox" checked={server} onChange={(x) => setServer(x.target.checked)} style={{ accentColor: "var(--accent)" }} />
          <span>Đồng thời tạo <b>quy tắc cảnh báo máy chủ</b> (đẩy ntfy/nhật ký kể cả khi tắt trang). Quy tắc áp dụng cho <i>mọi</i> tin tác động {e.impact === "high" ? "cao" : "vừa"} của {e.country || "mọi quốc gia"} trong cửa sổ {lead} phút trước giờ ra.</span></label>
        {err && <div role="alert" className="text-down text-[12.5px]">{err}</div>}
      </div>
    </Dialog>
  );
}

function CalDetail({ e, now, onClose }) {
  const [rem, setRem] = useState(false);
  const rems = useReminders().filter((r) => r.id === e.event_id);
  const x = e.extra || {};
  const sp = x.surprise;
  const cd = countdown(e.ts, now);
  return (
    <article className="flex flex-col h-full min-h-0" aria-label="Chi tiết sự kiện">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-line shrink-0"><ImpactDots impact={e.impact} /><span className="text-[12px] text-muted">{GROUP_LABEL[groupOf(e.title)]}</span>
        {onClose && <button type="button" className="btn !px-2 ml-auto" onClick={onClose} aria-label="Đóng"><X size={14} aria-hidden="true" /></button>}</div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 grid gap-3 content-start">
        <div><h2 className="m-0 text-[16px] font-semibold leading-snug">{e.title}</h2>
          <div className="text-[12.5px] text-muted mt-1">{COUNTRY_NAME[e.country] || e.country || "Toàn cầu"}{CCY_OF[e.country] ? ` · ${CCY_OF[e.country]}` : ""} · <span className="num">{dateTime(e.ts)}</span> {tzLabel()}</div>
          <div className="text-[13px] mt-1 num">{cd ? <>Còn <b className="text-accent">{cd}</b></> : e.actual ? "Đã công bố" : "Đã tới giờ, chờ số liệu"}</div></div>
        <div className="grid grid-cols-3 gap-2 text-center">
          {[["Thực tế", e.actual, true], ["Dự báo", e.forecast], ["Kỳ trước", e.previous]].map(([l, v, b]) => (
            <div key={l} className="rounded-md border border-line bg-panel2 py-2"><div className="text-[11px] text-muted">{l}</div><div className={cn("num text-[16px]", b && v && (verdictCls(e) || "text-fg"), !v && "text-faint")}>{v ?? "—"}</div></div>
          ))}
        </div>
        {sp && <div className="flex items-center gap-2 text-[12.5px]"><span className="text-muted">Bất ngờ:</span><Surprise sp={sp} />{x.actual_period && <span className="text-faint">kỳ {x.actual_period}</span>}</div>}
        <section aria-label="Lịch sử chỉ số"><h3 className="m-0 mb-1 text-[12.5px] font-semibold">Lịch sử: thực tế · dự báo · kỳ trước</h3><HistoryChart e={e} /></section>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn" onClick={() => setRem(true)}><BellPlus size={13} aria-hidden="true" /> Đặt nhắc</button>
          <a className="btn no-underline" href="#/canh-bao"><AlarmClock size={13} aria-hidden="true" /> Quy tắc cảnh báo</a>
        </div>
        {!!rems.length && <ul className="m-0 p-0 list-none grid gap-1 text-[12px]">{rems.map((r) => <li key={r.lead} className="flex items-center gap-2"><AlarmClock size={12} className="text-accent" aria-hidden="true" />Nhắc trước {r.lead} phút <button type="button" className="btn !h-6 !px-2 ml-auto" onClick={() => removeReminder(r.id, r.lead)}>Bỏ</button></li>)}</ul>}
        <p className="m-0 text-[11px] text-faint">Dự báo/kỳ trước chỉ dùng cá nhân; màu “bất ngờ” là tác động lên đồng tiền, không phải lời khuyên giao dịch.</p>
      </div>
      {rem && <ReminderDialog e={e} onClose={() => setRem(false)} />}
    </article>
  );
}

// ---------------------------------------------------------------- trang chính
export default function CalendarProView() {
  const [view, setView] = useLocal("ts-cal-view", "week");
  const [wk, setWk] = useState(0);
  const [day, setDay] = useState(null);
  const [imp, setImp] = useLocal("ts-cal-imp", { high: true, med: true, low: false });
  const [country, setCountry] = useLocal("ts-cal-cc", []);
  const [group, setGroup] = useLocal("ts-cal-grp", "");
  const [text, setText] = useState("");
  const [sel, setSel] = useState(null);
  const now = useNow();
  useReminderTicker();
  const rems = useReminders();
  const remindIds = useMemo(() => new Set(rems.map((r) => r.id)), [rems]);
  const start = useMemo(() => vnWeekStart(wk), [wk]);
  const days = useMemo(() => weekDays(start), [start]);
  const end = useMemo(() => weekEnd(start), [start]);
  const impact = Object.keys(imp).filter((k) => imp[k]).join(",");
  const q = useCalendar({ from: start.toISOString(), to: end.toISOString(), impact: impact || "none", order: "asc", limit: 1000 }, { enabled: !!impact, refetchInterval: 60_000 });
  const all = useMemo(() => (q.data?.items || []).filter((e) => !/^QA\b/i.test(e.title || "")), [q.data]); // bỏ dòng thử nghiệm của hệ thống kiểm thử
  const countries = useMemo(() => { const m = new Map(); for (const e of all) if (e.country) m.set(e.country, (m.get(e.country) || 0) + 1); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [all]);
  const t = text.trim().toLowerCase();
  const events = useMemo(() => all.filter((e) => (!country.length || country.includes(e.country)) && (!group || groupOf(e.title) === group) && (!t || `${e.title} ${e.country || ""}`.toLowerCase().includes(t))), [all, country, group, t]);
  const byDay = useMemo(() => {
    const m = new Map();
    for (const d of days) m.set(dayKey(d), []);
    for (const e of events) { const k = dayKeyOf(e.ts); if (m.has(k)) m.get(k).push(e); }
    return m;
  }, [events, days]);
  const todayKey = dayKeyOf(now);
  const curDay = day && byDay.has(day) ? day : (byDay.has(todayKey) ? todayKey : dayKey(days[0]));
  const next = events.find((e) => Date.parse(e.ts) > now && e.impact === "high") || events.find((e) => Date.parse(e.ts) > now);
  const risk = useMemo(() => riskWindows(events).filter((w) => w.end > now - 30 * 60e3), [events, now]);
  const onSelect = (e) => setSel(e);
  const selEvent = sel ? (all.find((x) => x.event_id === sel.event_id) || sel) : null;
  const toggleC = (c) => setCountry(country.includes(c) ? country.filter((x) => x !== c) : [...country, c]);
  const wide = useMedia("(min-width: 1280px)");
  const [dlg, setDlg] = useState(false);
  useEffect(() => { setDlg(!!selEvent); }, [selEvent?.event_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const weekLabel = `${date(start.getTime() + 3600e3)} – ${date(start.getTime() + 6 * 86400e3 + 3600e3)}`;
  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_400px] lg:h-[calc(100dvh-230px)] lg:min-h-[520px]">
      <Panel pad={false} className="min-h-[480px] lg:min-h-0 lg:h-full" bodyClass="flex flex-col"
        title={<span className="flex items-center gap-2"><CalendarClock size={14} aria-hidden="true" /> Tuần {weekLabel}</span>}
        right={<><button type="button" className="btn !px-2" onClick={() => { setWk(wk - 1); setDay(null); }} aria-label="Tuần trước"><ChevronLeft size={14} /></button>
          <button type="button" className="btn" onClick={() => { setWk(0); setDay(null); }}>Tuần này</button>
          <button type="button" className="btn !px-2" onClick={() => { setWk(wk + 1); setDay(null); }} aria-label="Tuần sau"><ChevronRight size={14} /></button></>}>
        {/* banner đếm ngược */}
        {next && (
          <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-line bg-panel2 text-[12.5px]" role="status">
            <AlarmClock size={14} className="text-accent" aria-hidden="true" />
            <span className="text-muted">Tin tiếp theo{next.impact === "high" ? " (tác động cao)" : ""}:</span>
            <button type="button" className="bg-transparent border-0 p-0 font-semibold text-fg cursor-pointer hover:text-accent text-left" onClick={() => onSelect(next)}>{next.country} · {next.title}</button>
            <span className="num text-accent ml-auto">{countdown(next.ts, now) || "đang diễn ra"}</span>
          </div>
        )}
        {risk.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 px-3 py-[6px] border-b border-line text-[12px]" aria-label="Cửa sổ rủi ro">
            <span className="text-muted">Cửa sổ rủi ro (tin cao):</span>
            {risk.slice(0, 6).map((w) => <span key={w.start} className="in-tag hot num" title={w.events.map((e) => `${e.country} ${e.title}`).join("\n")}>{date(w.start)} {time(w.start)}{w.end > w.start ? `–${time(w.end)}` : ""} · {w.events.length} tin</span>)}
          </div>
        )}
        {/* bộ lọc */}
        <div className="flex flex-wrap items-center gap-2 p-2 border-b border-line shrink-0">
          <Seg label="Kiểu xem" value={view} onChange={setView} options={[{ value: "week", label: "Lưới tuần" }, { value: "day", label: "Ngày" }, { value: "table", label: "Bảng tuần" }]} />
          <fieldset className="flex gap-2 items-center border-0 p-0 m-0"><legend className="sr-only">Mức tác động</legend>
            {IMP_TOGGLE.map(({ k, label }) => <label key={k} className="flex items-center gap-1 cursor-pointer text-[12px]"><input type="checkbox" checked={!!imp[k]} onChange={(ev) => setImp({ ...imp, [k]: ev.target.checked })} style={{ accentColor: "var(--accent)" }} /><ImpactDots impact={k} />{label}</label>)}</fieldset>
          <label className="sr-only" htmlFor="cal-g">Nhóm chỉ số</label>
          <select id="cal-g" className="field" value={group} onChange={(ev) => setGroup(ev.target.value)}><option value="">Mọi nhóm chỉ số</option>{[...GROUPS.map((g) => g.id), "other"].map((g) => <option key={g} value={g}>{GROUP_LABEL[g]}</option>)}</select>
          <div className="relative min-w-[140px] flex-1 max-w-[260px]"><Search size={13} className="absolute left-2 top-[10px] text-faint" aria-hidden="true" /><label className="sr-only" htmlFor="cal-q">Tìm sự kiện</label><input id="cal-q" type="search" className="field w-full !pl-7" placeholder="Tìm sự kiện…" value={text} onChange={(ev) => setText(ev.target.value)} /></div>
          <button type="button" className="btn ml-auto" onClick={() => download(`lich-kinh-te-${date(start.getTime() + 3600e3).replace("/", "-")}.csv`, toCsv(events))} disabled={!events.length}><Download size={13} aria-hidden="true" /> CSV</button>
        </div>
        <div className="flex flex-wrap items-center gap-1 px-2 py-[6px] border-b border-line shrink-0" role="group" aria-label="Lọc quốc gia">
          <span className="text-[11.5px] text-muted mr-1">Quốc gia:</span>
          {countries.map(([c, n]) => <button key={c} type="button" aria-pressed={country.includes(c)} className={cn("chip cursor-pointer bg-transparent", country.includes(c) && "accent")} title={`${COUNTRY_NAME[c] || c}${CCY_OF[c] ? ` · ${CCY_OF[c]}` : ""}`} onClick={() => toggleC(c)}>{c} <span className="num text-faint">{n}</span></button>)}
          {country.length > 0 && <button type="button" className="chip cursor-pointer bg-transparent" onClick={() => setCountry([])}>Bỏ lọc</button>}
          {!countries.length && <span className="text-[11.5px] text-faint">—</span>}
          <span className="ml-auto text-[11.5px] text-faint num">{events.length} sự kiện</span>
        </div>
        {/* thân */}
        <div className="flex-1 min-h-0 overflow-auto">
          {!impact ? <div className="p-3 text-muted">Chọn ít nhất một mức tác động.</div>
            : q.isPending || q.isError ? <QState q={q} rows={8} />
              : !events.length ? <div className="p-3 text-muted text-[12.5px]">Không có sự kiện nào khớp bộ lọc trong tuần này.<div className="text-faint mt-1">Thử bật mức tác động Thấp, bỏ lọc quốc gia hoặc chuyển tuần.</div></div>
                : view === "week" ? (
                  <div className="grid grid-cols-[repeat(7,minmax(122px,1fr))] min-w-[860px] h-full">
                    {days.map((d) => {
                      const k = dayKey(d);
                      const list = byDay.get(k) || [];
                      const isToday = k === todayKey;
                      const hi = list.filter((e) => e.impact === "high").length;
                      return (
                        <section key={k} aria-label={`${dow(d.getTime() + 3600e3)} ${date(d.getTime() + 3600e3)}`} className={cn("border-r border-line last:border-r-0 flex flex-col min-w-0", isToday && "bg-[var(--accent-bg)]")}>
                          <button type="button" className={cn("sticky top-0 z-[1] bg-panel border-0 border-b border-line text-left px-2 py-[6px] cursor-pointer font-[inherit] text-fg", isToday && "!bg-[var(--accent-bg)]")} onClick={() => { setDay(k); setView("day"); }} title="Xem riêng ngày này">
                            <div className={cn("text-[11px]", isToday ? "text-fg" : "text-muted")}>{dow(d.getTime() + 3600e3)}{isToday ? " · hôm nay" : ""}</div>
                            <div className="flex items-center gap-1 flex-nowrap whitespace-nowrap"><b className="num text-[14px]">{date(d.getTime() + 3600e3)}</b><span className={cn("text-[11px] num", isToday ? "text-fg" : "text-faint")}>· {list.length}</span>{hi > 0 && <span className={cn("in-tag hot num !px-1", isToday && "!text-fg")} title={`${hi} tin tác động cao`}>{hi}▲</span>}</div>
                          </button>
                          <div className="p-1 grid gap-1 content-start">{list.map((e) => <EventCard key={e.event_id} e={e} now={now} selected={selEvent?.event_id === e.event_id} onSelect={onSelect} remind={remindIds.has(e.event_id)} />)}{!list.length && <div className="text-[11.5px] text-faint p-1">—</div>}</div>
                        </section>
                      );
                    })}
                  </div>
                ) : view === "day" ? (
                  <div className="p-2">
                    <div className="flex gap-1 mb-2 overflow-x-auto" role="tablist" aria-label="Chọn ngày">
                      {days.map((d) => { const k = dayKey(d); const on = k === curDay; return (
                        <button key={k} role="tab" aria-selected={on} type="button" onClick={() => setDay(k)} className={cn("shrink-0 min-w-[62px] rounded-md px-2 py-[5px] text-center border font-[inherit] cursor-pointer", on ? "bg-accent text-[var(--accent-fg)] border-transparent" : "bg-panel2 text-fg border-line hover:border-line2")}>
                          <div className="text-[11px] opacity-80">{dow(d.getTime() + 3600e3)}</div><div className="num text-[13px]">{date(d.getTime() + 3600e3)} <span className="opacity-70">({(byDay.get(k) || []).length})</span></div></button>); })}
                    </div>
                    {(byDay.get(curDay) || []).length ? <div className="scroll-x"><EventTable events={byDay.get(curDay)} now={now} selId={selEvent?.event_id} onSelect={onSelect} remindIds={remindIds} nextId={next?.event_id} /></div> : <div className="text-muted text-[12.5px] p-2">Không có sự kiện trong ngày này.</div>}
                  </div>
                ) : (
                  <div className="p-2 scroll-x"><EventTable events={events} now={now} selId={selEvent?.event_id} onSelect={onSelect} remindIds={remindIds} nextId={next?.event_id} /></div>
                )}
        </div>
      </Panel>
      {wide && (
        <div className="min-h-0">
          <Panel title="Chi tiết sự kiện" pad={false} className="h-full" bodyClass="min-h-0 flex flex-col">
            {selEvent ? <CalDetail key={selEvent.event_id} e={selEvent} now={now} onClose={() => setSel(null)} />
              : <div className="p-4 text-muted text-[12.5px] grid gap-2"><CalendarClock size={18} aria-hidden="true" /><span>Chọn một sự kiện để xem số liệu, lịch sử thực tế/dự báo/kỳ trước và đặt nhắc.</span></div>}
          </Panel>
        </div>
      )}
      {!wide && (
        <Dialog open={dlg && !!selEvent} onClose={() => { setDlg(false); setSel(null); }} title="Chi tiết sự kiện" variant="drawer">
          {selEvent && <div className="h-[calc(100dvh-52px)]"><CalDetail key={selEvent.event_id} e={selEvent} now={now} /></div>}
        </Dialog>
      )}
    </div>
  );
}
