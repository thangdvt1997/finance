import { useMemo } from "react";
import { EChart, css } from "./charts";
import { Async } from "./ui";
import { useEquity, useJnSummary } from "../lib/queries";
import { date, dateTime, f1, money, numLocale, signCls, smoney, time, vnDayKey, vnDayStart } from "../lib/format";
import { t } from "../lib/i18n";

// 1D/1W dùng ảnh chụp equity thật; 1M/YTD/ALL cần lịch sử dài: nếu ảnh chụp không phủ hết khoảng thì dùng đường vốn theo lệnh đã đóng (nhãn rõ ràng).
export const RANGES = { "1D": 1, "1W": 7, "1M": 30, YTD: "ytd", ALL: "all" };
const ytdDays = () => Math.max(1, Math.ceil((Date.now() - Date.UTC(new Date().getFullYear(), 0, 1)) / 86400e3));
export const rangeDays = (r) => (RANGES[r] === "ytd" ? ytdDays() : RANGES[r] === "all" ? 3650 : RANGES[r]);

/** Rút còn <= n điểm: giữ min/max mỗi nhóm để không mất đỉnh/đáy. */
export function downsample(pts, n = 700) {
  if (pts.length <= n) return pts;
  const k = Math.ceil(pts.length / (n / 2)), out = [];
  for (let i = 0; i < pts.length; i += k) {
    const g = pts.slice(i, i + k);
    let lo = g[0], hi = g[0];
    for (const p of g) { if (p.equity < lo.equity) lo = p; if (p.equity > hi.equity) hi = p; }
    out.push(...(lo.ts <= hi.ts ? [lo, hi] : [hi, lo]));
  }
  out[out.length - 1] = pts[pts.length - 1];
  return out;
}

/** Số liệu đường vốn theo khoảng, dùng chung cho biểu đồ và dải thống kê. */
export function useEquityRange(id, range) {
  const days = rangeDays(range);
  const long = days > 7;
  const from = useMemo(() => new Date(Date.now() - days * 86400e3).toISOString().slice(0, 16) + ":00Z", [days, id]); // eslint-disable-line react-hooks/exhaustive-deps
  const snap = useEquity(id, from);
  const jf = useMemo(() => (RANGES[range] === "all" ? {} : { from: vnDayKey(vnDayStart(-(days - 1))), to: vnDayKey(new Date()) }), [range, days]);
  const jn = useJnSummary(long ? id : null, jf);
  const pts = snap.data || [];
  const fromMs = Date.now() - days * 86400e3;
  const covers = pts.length > 1 && new Date(pts[0].ts).getTime() <= fromMs + Math.min(days * 86400e3 * 0.15, 36 * 3600e3);
  const jpts = jn.data?.equity?.points || [];
  const useJn = long && !covers && jpts.length > 1;
  const data = useJn ? jpts.map((p) => ({ ts: p.t, equity: p.equity, balance: null })) : pts;
  return { q: long && !covers && snap.isSuccess && jn.isPending ? jn : snap, data, source: useJn ? "closed" : "snapshot", days };
}

/** Đường vốn (equity) + số dư (balance) của một tài khoản. Màu lấy từ token CSS nên đổi sáng/tối tự vẽ lại. */
export default function EquityChart({ id, range = "1W", height = 240 }) {
  const { q, data, source, days } = useEquityRange(id, range);
  const pts = useMemo(() => downsample(data), [data]);
  const view = { ...q, data: pts };
  return (
    <Async q={view} rows={6} isEmpty={() => pts.length < 2} empty={t("Chưa có lịch sử vốn trong khoảng này.")} hint={t("Mỗi lần EA gửi dữ liệu sẽ thêm một điểm trên đường vốn.")}>
      {() => {
        const first = pts[0].equity, last = pts[pts.length - 1].equity, d = last - first;
        const build = () => {
          const eq = pts.map((p) => [new Date(p.ts).getTime(), p.equity]);
          const bal = pts.filter((p) => p.balance != null).map((p) => [new Date(p.ts).getTime(), p.balance]);
          const vals = pts.flatMap((p) => [p.equity, p.balance]).filter((v) => v != null);
          const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.15 || Math.max(Math.abs(hi) * 0.002, 1);
          const dp = hi - lo + 2 * pad < 10 ? 2 : 0;
          const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
          const series = [{ name: t("Vốn (equity)"), type: "line", data: eq, showSymbol: false, lineStyle: { width: 2, color: css("--accent") }, itemStyle: { color: css("--accent") }, areaStyle: { color: css("--accent-bg") } }];
          if (bal.length) series.push({ name: t("Số dư (balance)"), type: "line", data: bal, showSymbol: false, step: "end", lineStyle: { width: 1.2, color: css("--muted"), type: "dashed" }, itemStyle: { color: css("--muted") } });
          return {
            animation: false, backgroundColor: "transparent", grid: { left: 54, right: 10, top: 12, bottom: 24 },
            tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
              formatter: (a) => `${dateTime(a[0].value[0])}<br/>${a.map((s) => `${s.marker}${s.seriesName}: <b>${money(s.value[1])}</b>`).join("<br/>")}` },
            xAxis: { type: "time", ...axis, axisLabel: { ...axis.axisLabel, hideOverlap: true, formatter: (v) => (days > 1 ? date(v) : time(v)) }, splitLine: { show: false } },
            yAxis: { type: "value", min: lo - pad, max: hi + pad, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => v.toLocaleString(numLocale(), { minimumFractionDigits: dp, maximumFractionDigits: dp }) } },
            series,
          };
        };
        return (
          <div className="flex flex-col">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-1 text-[12.5px]">
              <span className="text-muted">{t("Thay đổi trong khoảng:")}</span>
              <b className={`num ${signCls(d)}`}>{smoney(d)}{first ? ` (${d >= 0 ? "+" : ""}${f1((d / first) * 100, 2)}%)` : ""}</b>
              <span className="text-faint">{date(pts[0].ts)} → {date(pts[pts.length - 1].ts)}</span>
            </div>
            <div className="flex gap-4 text-[12px] text-muted mb-1" aria-hidden="true">
              <span><i className="inline-block w-3 h-[3px] align-middle mr-1.5 rounded" style={{ background: "var(--accent)" }} />{source === "closed" ? t("Vốn theo lệnh đã đóng") : t("Vốn (equity)")}</span>
              {source === "snapshot" && <span><i className="inline-block w-3 border-t-2 border-dashed border-muted align-middle mr-1.5" />{t("Số dư (balance)")}</span>}
            </div>
            {source === "closed" && <p className="m-0 mb-1 text-[12px] text-faint">{t("Lịch sử chụp vốn chưa đủ dài cho khoảng này, nên đường vẽ theo từng lệnh đã đóng (chưa gồm lãi/lỗ đang mở và nạp/rút).")}</p>}
            <EChart build={build} deps={[pts, range, source]} height={height} label={t("Đường vốn của tài khoản {id}, khoảng {range}", { id, range })} />
          </div>
        );
      }}
    </Async>
  );
}
