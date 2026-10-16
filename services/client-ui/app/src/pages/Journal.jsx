import { useMemo, useState } from "react";
import { BookOpen, CalendarDays, ChevronLeft, ChevronRight, Flag, ListChecks, NotebookPen } from "lucide-react";
import { Async, Chip, Disclaimer, Kpi, Notice, PageHead, Panel, Seg, Sheet, Skeleton, cn } from "../components/ui";
import { EChart, css } from "../components/charts";
import NoteEditor from "../components/notes";
import { Analysis, Deals, Performance, RULES, SIDE, fN, fS } from "./journalparts";
import { useActiveAccount } from "../lib/account";
import { accountTitle } from "../lib/auth";
import { useJnDeals, useJnDiscipline, useJnNotes, useJnSummary } from "../lib/queries";
import { dateTime, dur, f0, f1, money, signCls, vnDayKey, vnDayStart } from "../lib/format";
import { t, tn } from "../lib/i18n";

const ranges = () => [{ value: "7", label: t("7 ngày") }, { value: "30", label: t("30 ngày") }, { value: "90", label: t("90 ngày") }, { value: "all", label: t("Tất cả") }];
const tabs = () => [{ value: "overview", label: t("Tổng quan") }, { value: "analysis", label: t("Phân tích") }, { value: "deals", label: t("Lệnh") }, { value: "discipline", label: t("Kỷ luật") }];
const isoWeek = (d) => { const u = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const day = u.getUTCDay() || 7; u.setUTCDate(u.getUTCDate() + 4 - day); const y = u.getUTCFullYear(); const w = Math.ceil(((u - Date.UTC(y, 0, 1)) / 86400000 + 1) / 7); return `${y}-W${String(w).padStart(2, "0")}`; };

function EquityPanel({ eq }) {
  const pts = eq?.points || [];
  if (pts.length < 2) return <div className="text-muted">{t("Chưa đủ lệnh đã đóng để vẽ đường vốn (cần ít nhất 2 lệnh).")}</div>;
  const build = () => ({
    animation: false, backgroundColor: "transparent",
    grid: [{ left: 54, right: 10, top: 10, height: "58%" }, { left: 54, right: 10, top: "74%", bottom: 22 }],
    tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
      formatter: (a) => { const p = pts[a[0]?.dataIndex]; return p ? `${dateTime(p.t)}<br/>${t("Vốn")}: <b>${fN(p.equity)}</b><br/>${t("Sụt giảm")}: <b>-${fN(p.dd)}</b>` : ""; } },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: [{ type: "time", gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: css("--line2") } }, splitLine: { show: false } },
      { type: "time", gridIndex: 1, axisLabel: { color: css("--muted"), fontSize: 11, hideOverlap: true }, axisLine: { lineStyle: { color: css("--line2") } }, splitLine: { show: false } }],
    yAxis: [{ type: "value", gridIndex: 0, scale: true, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } },
      { type: "value", gridIndex: 1, max: 0, splitNumber: 2, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } }],
    series: [
      { type: "line", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, data: pts.map((p) => [new Date(p.t).getTime(), p.equity]), lineStyle: { color: css("--accent"), width: 1.8 }, areaStyle: { color: css("--accent"), opacity: 0.07 } },
      { type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, data: pts.map((p) => [new Date(p.t).getTime(), -Math.abs(p.dd || 0)]), lineStyle: { color: css("--down"), width: 1.2 }, areaStyle: { color: css("--down"), opacity: 0.2 } },
    ],
  });
  return <EChart build={build} deps={[eq]} height={280} label={t("Đường vốn theo lệnh đã đóng và sụt giảm")} />;
}

function MonthCalendar({ calendar, onPick }) {
  const byKey = useMemo(() => new Map((calendar || []).map((d) => [d.date, d])), [calendar]);
  const last = (calendar || []).map((d) => d.date).sort().pop() || vnDayKey(new Date());
  const [ym, setYm] = useState(last.slice(0, 7));
  const [y, m] = ym.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1));
  const lead = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => `${ym}-${String(i + 1).padStart(2, "0")}`)];
  const max = Math.max(1e-9, ...[...byKey.values()].map((d) => Math.abs(d.net)));
  const monthNet = [...byKey.values()].filter((d) => d.date.startsWith(ym)).reduce((s, d) => s + d.net, 0);
  const shift = (n) => { const d = new Date(Date.UTC(y, m - 1 + n, 1)); setYm(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`); };
  return (
    <div>
      <div className="flex items-center gap-1 mb-2">
        <button className="ibtn" onClick={() => shift(-1)} aria-label={t("Tháng trước")}><ChevronLeft size={20} aria-hidden="true" /></button>
        <div className="flex-1 text-center"><b>{t("Tháng {m}/{y}", { m, y })}</b><div className={cn("num text-[13px]", signCls(monthNet))}>{fS(monthNet)}</div></div>
        <button className="ibtn" onClick={() => shift(1)} aria-label={t("Tháng sau")}><ChevronRight size={20} aria-hidden="true" /></button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11.5px] text-faint mb-1" aria-hidden="true">{[t("T2"), t("T3"), t("T4"), t("T5"), t("T6"), t("T7"), t("CN")].map((d, i) => <div key={i}>{d}</div>)}</div>
      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((k, i) => {
          if (!k) return <div key={`b${i}`} />;
          const d = byKey.get(k);
          const a = d ? 0.16 + 0.7 * Math.min(1, Math.abs(d.net) / max) : 0;
          const c = d ? (d.net > 0 ? "var(--up)" : d.net < 0 ? "var(--down)" : "var(--faint)") : null;
          return (
            <button key={k} type="button" onClick={() => onPick(k, d)} aria-label={t("Ngày {d}: {info}", { d: k.slice(8), info: d ? t("{count}, {net}", { count: tn("{n} lệnh", d.n), net: fS(d.net) }) : t("không có lệnh") })}
              className="min-h-[46px] rounded-lg border cursor-pointer text-inherit flex flex-col items-center justify-center p-0.5 leading-tight"
              style={{ background: d ? `color-mix(in srgb, ${c} ${Math.round(a * 100)}%, var(--panel))` : "transparent", borderColor: d ? "transparent" : "var(--line)" }}>
              <span className="text-[12px] text-muted">{+k.slice(8)}</span>
              {d && <span className="num text-[10.5px] font-semibold overflow-hidden max-w-full">{Math.abs(d.net) >= 1000 ? `${f1(d.net / 1000, 1)}k` : f0(d.net)}</span>}
            </button>
          );
        })}
      </div>
      <p className="m-0 mt-2 text-[12px] text-faint">{t("Màu đậm = lãi/lỗ lớn. Bấm một ngày để xem và ghi chú.")}</p>
    </div>
  );
}

function DayNote({ acc, day, info, onClose }) {
  const q = useJnNotes(acc, "day");
  const found = (q.data?.items || []).find((n) => String(n.ref) === day);
  return (
    <Sheet title={t("Ngày {d}", { d: day.split("-").reverse().join("/") })} onClose={onClose}>
      <div className="grid gap-3">
        <div className="kpi-grid"><Kpi label={t("Lãi/lỗ ròng")} value={info ? fS(info.net) : "—"} tone={info ? signCls(info.net) : ""} /><Kpi label={t("Số lệnh")} value={info ? info.n : 0} /></div>
        <NoteEditor acc={acc} kind="day" refId={day} initial={found} label={t("Ghi chú ngày")} />
      </div>
    </Sheet>
  );
}

function Overview({ acc, s, onDay }) {
  const sm = s.summary;
  return (
    <div className="grid gap-3">
      <div className="kpi-grid c3">
        <Kpi big label={t("Lãi/lỗ ròng")} value={fS(sm.net)} tone={signCls(sm.net)} sub={t("Lãi gộp {p} · lỗ gộp {l}", { p: fN(sm.gross_profit, 0), l: fN(sm.gross_loss, 0) })} />
        <Kpi label={t("Số lệnh")} value={fN(sm.n, 0)} sub={t("{w} thắng · {l} thua", { w: sm.wins, l: sm.losses })} />
        <Kpi label={t("Tỷ lệ thắng")} value={sm.win_rate == null ? "—" : `${(sm.win_rate * 100).toFixed(1)}%`} sub={t("Tốt nhất {b} · tệ nhất {w}", { b: fS(sm.best, 0), w: fS(sm.worst, 0) })} />
        <Kpi label="Profit factor" value={sm.profit_factor == null ? "—" : fN(sm.profit_factor)} sub={sm.profit_factor == null ? t("chưa có lệnh lỗ") : t("lãi gộp ÷ lỗ gộp")} />
        <Kpi label={t("Kỳ vọng / lệnh")} value={fS(sm.expectancy)} tone={signCls(sm.expectancy)} sub={t("Trung bình thắng {w} / thua {l}", { w: fN(sm.avg_win, 1), l: fN(sm.avg_loss, 1) })} />
        <Kpi label={t("Sụt giảm tối đa")} value={fN(s.equity?.max_dd)} tone={s.equity?.max_dd > 0 ? "down" : ""} sub={s.equity?.max_dd_pct != null ? t("{p}% · hiện tại {c}", { p: f1(s.equity.max_dd_pct, 2), c: fN(s.equity.current_dd) }) : t("hiện tại {c}", { c: fN(s.equity?.current_dd) })} />
      </div>
      <Panel title={t("Đường vốn và sụt giảm")}><EquityPanel eq={s.equity} /></Panel>
      <Panel title={t("Lịch lãi/lỗ")} icon={CalendarDays} bodyClass="!p-2">
        {s.calendar?.length ? <MonthCalendar calendar={s.calendar} onPick={(k, d) => onDay(k, d)} /> : <div className="text-muted">{t("Chưa có ngày nào có lệnh trong khoảng này.")}</div>}
      </Panel>
      {s.groups?.symbol?.length > 0 && (
        <Panel title={t("Theo mã giao dịch")} icon={ListChecks} pad={false}>
          <ul className="list-none m-0 p-0">
            {s.groups.symbol.slice(0, 10).map((r) => (
              <li key={r.key} className="flex items-center gap-3 px-3.5 py-2.5 border-b border-line last:border-0 min-h-[44px]">
                <b className="w-[5.5rem] truncate">{r.key}</b>
                <span className="text-[12.5px] text-muted">{r.win_rate != null ? t("{n} lệnh · thắng {w}%", { n: r.n, w: (r.win_rate * 100).toFixed(0) }) : tn("{n} lệnh", r.n)}</span>
                <b className={cn("num ml-auto", signCls(r.net))}>{fS(r.net)}</b>
              </li>))}
          </ul>
        </Panel>
      )}
      {s.notes?.length > 0 && <div className="text-[12px] text-faint" role="note">{s.notes.join(" · ")}</div>}
    </div>
  );
}

function Gauge({ score }) {
  const v = score == null ? 0 : Math.max(0, Math.min(100, score));
  const col = score == null ? "var(--faint)" : v >= 80 ? "var(--up)" : v >= 60 ? "var(--accent)" : "var(--down)";
  const R = 52, C = 2 * Math.PI * R;
  return (
    <div className="relative w-[132px] h-[132px] shrink-0" role="img" aria-label={score == null ? t("Chưa có điểm kỷ luật") : t("Điểm kỷ luật {v} trên 100", { v: v.toFixed(0) })}>
      <svg viewBox="0 0 132 132" width="132" height="132" aria-hidden="true"><circle cx="66" cy="66" r={R} fill="none" stroke="var(--line2)" strokeWidth="10" />
        <circle cx="66" cy="66" r={R} fill="none" stroke={col} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(v / 100) * C} ${C}`} transform="rotate(-90 66 66)" /></svg>
      <div className="absolute inset-0 grid place-items-center text-center"><div><div className="num text-[30px] leading-none" style={{ color: col }}>{score == null ? "—" : v.toFixed(0)}</div><div className="text-[11px] text-muted">/ 100</div></div></div>
    </div>
  );
}

function Discipline({ acc, filters }) {
  const q = useJnDiscipline(acc, filters);
  return (
    <Panel title={t("Kỷ luật giao dịch")} icon={Flag}>
      <Async q={q} rows={5} isEmpty={(d) => !d} empty={t("Chưa có dữ liệu kỷ luật.")}>
        {(d) => (
          <div className="grid gap-4">
            <p className="m-0 text-[12.5px] text-faint">{t("Hệ thống phát hiện SAU khi lệnh xảy ra, chỉ để bạn soi lại, không chặn lệnh.")}</p>
            <div className="flex flex-wrap items-center gap-5">
              <Gauge score={d.score} />
              <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 flex-1 min-w-[14rem]">
                <Kpi label={t("Lệnh vi phạm")} value={`${d.n_flagged} / ${d.n_trades}`} />
                <Kpi label={t("P/L lệnh vi phạm")} value={fS(d.net_flagged)} tone={signCls(d.net_flagged)} />
                <Kpi label={t("P/L lệnh sạch")} value={fS(d.net_clean)} tone={signCls(d.net_clean)} />
                <Kpi label={t("Chênh lệch")} value={fS((d.net_clean || 0) - (d.net_flagged || 0))} tone={signCls((d.net_clean || 0) - (d.net_flagged || 0))} sub={t("sạch trừ vi phạm")} />
              </div>
            </div>
            {d.note && <div className="text-[12.5px] text-faint">{d.note}</div>}
            <div>
              <h3 className="m-0 mb-1.5 text-[13px] text-muted font-semibold">{t("Quy tắc")}</h3>
              {(d.rules || []).length === 0 ? <div className="text-muted text-[13px]">{t("Không có vi phạm nào.")}</div> : (
                <ul className="list-none m-0 p-0">{d.rules.map((r) => (
                  <li key={r.rule} className="flex items-center gap-3 py-2 border-b border-line last:border-0 min-h-[44px]"><span className="flex-1 min-w-0 text-[13.5px]">{r.label || RULES[r.rule] || r.rule}</span><span className="num text-muted">{r.count}×</span><b className={cn("num w-20 text-right", signCls(r.net))}>{fS(r.net)}</b></li>))}</ul>
              )}
            </div>
          </div>
        )}
      </Async>
    </Panel>
  );
}

function WeekNote({ acc }) {
  const label = isoWeek(new Date());
  const q = useJnNotes(acc, "week");
  const found = (q.data?.items || []).find((n) => String(n.ref) === label);
  return (
    <Panel title={t("Nhìn lại tuần {w}", { w: label })} icon={NotebookPen}>
      {q.isPending ? <Skeleton rows={3} /> : <NoteEditor acc={acc} kind="week" refId={label} initial={found} label={t("Điều rút ra trong tuần")} />}
    </Panel>
  );
}

export default function Journal() {
  const { acc } = useActiveAccount();
  const [range, setRange] = useState("30");
  const [tab, setTab] = useState("overview");
  const [day, setDay] = useState(null);
  const today = vnDayKey(new Date());
  const filters = useMemo(() => (range === "all" ? {} : { from: vnDayKey(vnDayStart(-(Number(range) - 1))), to: today }), [range, today]);
  const q = useJnSummary(acc?.id, filters);
  const sd = q.data;

  return (
    <>
      <PageHead title={t("Nhật ký giao dịch")} sub={acc ? t("{acc} · thống kê từ lệnh ĐÃ ĐÓNG (EA gửi lịch sử về hệ thống)", { acc: accountTitle(acc) }) : t("Chưa có tài khoản")}
        right={<Seg value={range} onChange={setRange} options={ranges()} label={t("Khoảng thời gian")} scroll />} />
      <Disclaimer>{t("Chỉ số tính trên lệnh")} <b>{t("đã đóng")}</b>{t(", không gồm lãi/lỗ đang mở. Dùng để tự soi lại giao dịch, không phải khuyến nghị đầu tư. Bạn chỉ có thể ghi chú và gắn tag; hệ thống không đặt hay sửa lệnh.")}</Disclaimer>
      {acc && q.isError && q.error?.status === 404 && <Notice tone="info" title={t("Chưa có lịch sử giao dịch")}>{t("Khi EA gửi lịch sử lệnh đã đóng về hệ thống, thống kê sẽ tự xuất hiện ở đây.")}</Notice>}
      {acc && !(q.isError && q.error?.status === 404) && (
        <Async q={q} rows={8} isEmpty={(d) => !d || !d.summary} empty={t("Chưa có lệnh đã đóng nào.")} hint={t("Khi EA gửi lịch sử deal về hệ thống, thống kê sẽ tự xuất hiện ở đây.")}>
          {() => sd.summary.n === 0 ? (
            <Notice tone="info" title={t("Không có lệnh nào trong khoảng này")}>{t("Thử chọn khoảng thời gian dài hơn.")}{range !== "all" && <> <button className="btn sm ml-1" onClick={() => setRange("all")}>{t("Xem tất cả")}</button></>}</Notice>
          ) : (
            <>
              <Seg value={tab} onChange={setTab} options={tabs()} label={t("Mục nhật ký")} className="self-start" />
              {tab === "overview" && <><Overview acc={acc.id} s={sd} onDay={(k, d) => setDay({ k, d })} /><WeekNote acc={acc.id} /></>}
              {tab === "analysis" && <><Performance s={sd} /><Analysis s={sd} /></>}
              {tab === "deals" && <Deals acc={acc.id} filters={filters} groups={sd.groups} />}
              {tab === "discipline" && <Discipline acc={acc.id} filters={filters} />}
            </>
          )}
        </Async>
      )}
      {day && <DayNote acc={acc.id} day={day.k} info={day.d} onClose={() => setDay(null)} />}
    </>
  );
}
