// Các khối của Nhật ký: danh sách lệnh (lọc, tìm, xuất CSV), phân tích theo giờ/thứ/phiên/mã/EA, chỉ số hiệu suất chi tiết.
import { useState } from "react";
import { BarChart3, BookOpen, Download, Flag, Gauge as GaugeIcon, ListChecks, Search, SlidersHorizontal } from "lucide-react";
import { Async, Chip, Kpi, Notice, Panel, Seg, Sheet, Skeleton, cn } from "../components/ui";
import { EChart, css } from "../components/charts";
import NoteEditor from "../components/notes";
import { api } from "../lib/api";
import { downloadText, toCsv } from "../lib/csv";
import { useJnDeals, useJnNotes } from "../lib/queries";
import { dateTime, dur, f1, signCls, vnDayKey } from "../lib/format";
import { t, tn } from "../lib/i18n";

export const SIDE = { get buy() { return t("Mua"); }, get sell() { return t("Bán"); } };
export const RULES = {
  get news_window() { return t("Vào lệnh trong cửa sổ rủi ro tin"); }, get reentry_after_loss() { return t("Vào lại ngay sau lệnh thua"); }, get size_up_after_loss() { return t("Tăng khối lượng sau lệnh thua"); },
  get averaging_down() { return t("Nhồi lệnh bình quân giá xấu"); }, get overtrading_day() { return t("Quá nhiều lệnh trong ngày"); }, get overtrading_hour() { return t("Quá nhiều lệnh trong 1 giờ"); }, get no_sl() { return t("Vào lệnh không đặt SL"); },
};
export const fN = (n, dp = 2) => f1(n, dp);
export const fS = (n, dp = 2) => (n == null || Number.isNaN(n) ? "—" : `${n > 0 ? "+" : ""}${f1(n, dp)}`);

export function DealSheet({ acc, d, onClose }) {
  const notes = useJnNotes(acc, "deal");
  const found = (notes.data?.items || []).find((n) => String(n.ref) === String(d.ticket));
  return (
    <Sheet title={`${d.symbol} · ${SIDE[d.side] || d.side} #${d.ticket}`} onClose={onClose}>
      <div className="grid gap-3">
        <div className="kpi-grid">
          <Kpi label={t("Lãi/lỗ ròng")} value={fS(d.net)} tone={signCls(d.net)} />
          <Kpi label={t("Khối lượng")} value={t("{v} lot", { v: fN(d.volume, 2) })} sub={d.r != null ? `${d.r > 0 ? "+" : ""}${Number(d.r).toFixed(2)}R` : undefined} />
          <Kpi label={t("Vào")} value={<span className="text-[14px]">{dateTime(d.time_open)}</span>} />
          <Kpi label={t("Ra")} value={<span className="text-[14px]">{dateTime(d.time_close)}</span>} sub={t("giữ {d}", { d: dur(d.hold_s) })} />
        </div>
        {d.flags?.length > 0 && <Notice tone="warn" icon={Flag} title={t("Vi phạm kỷ luật")}>{d.flags.map((f) => RULES[f.rule] || f.rule).join("; ")}</Notice>}
        {notes.isPending ? <Skeleton rows={3} /> : <NoteEditor acc={acc} kind="deal" refId={d.ticket} initial={found} />}
      </div>
    </Sheet>
  );
}

const outcomes = () => [{ value: "", label: t("Tất cả") }, { value: "win", label: t("Thắng") }, { value: "loss", label: t("Thua") }, { value: "be", label: t("Hoà vốn") }];
const sides = () => [{ value: "", label: t("Mua + bán") }, { value: "buy", label: t("Mua") }, { value: "sell", label: t("Bán") }];
const csvCols = () => [
  { label: "Ticket", key: "ticket" }, { label: t("Mã"), key: "symbol" }, { label: t("Hướng"), get: (d) => SIDE[d.side] || d.side }, { label: "Lot", key: "volume" },
  { label: t("Giờ vào"), get: (d) => d.time_open }, { label: t("Giờ ra"), get: (d) => d.time_close }, { label: t("Giữ (giây)"), key: "hold_s" },
  { label: t("Lãi/lỗ ròng"), key: "net" }, { label: "R", key: "r" }, { label: t("Nhóm/EA"), key: "group" },
  { label: t("Vi phạm kỷ luật"), get: (d) => (d.flags || []).map((f) => RULES[f.rule] || f.rule).join("; ") },
];

export function Deals({ acc, filters, groups }) {
  const [limit, setLimit] = useState(20);
  const [open, setOpen] = useState(null);
  const [f, setF] = useState({ symbol: "", side: "", outcome: "", flagged: false, text: "" });
  const [busy, setBusy] = useState(false);
  const eff = { ...filters, ...(f.symbol ? { symbol: f.symbol } : {}), ...(f.side ? { side: f.side } : {}), ...(f.outcome ? { outcome: f.outcome } : {}), ...(f.flagged ? { flagged: true } : {}) };
  const q = useJnDeals(acc, { ...eff, limit, offset: 0, sort: "time_close", order: "desc" });
  const all = q.data?.items || [];
  const kw = f.text.trim().toLowerCase();
  const items = kw ? all.filter((d) => String(d.ticket).includes(kw) || String(d.symbol).toLowerCase().includes(kw) || String(d.group || "").toLowerCase().includes(kw)) : all;
  const total = q.data?.total ?? all.length;
  const symOpts = (groups?.symbol || []).map((g) => g.key);
  const exportCsv = async () => {
    setBusy(true);
    try {
      let rows = [];
      for (let off = 0; off < 5000; off += 500) {
        const r = await api(`/journal/${encodeURIComponent(acc)}/deals`, { ...eff, limit: 500, offset: off, sort: "time_close", order: "desc" });
        rows = rows.concat(r.items || []);
        if (!r.items || r.items.length < 500) break;
      }
      downloadText(`lich-su-lenh-${vnDayKey(new Date())}.csv`, toCsv(rows, csvCols()));
    } catch { /* lỗi mạng: người dùng thử lại */ } finally { setBusy(false); }
  };
  return (
    <>
      <Panel title={t("Lọc lệnh")} icon={SlidersHorizontal} right={<button className="btn sm" onClick={exportCsv} disabled={busy || total === 0}><Download size={15} aria-hidden="true" /> {busy ? t("Đang xuất…") : t("Xuất CSV")}</button>}>
        <div className="grid gap-3">
          <label className="relative block"><span className="sr-only">{t("Tìm theo ticket, mã hoặc EA")}</span><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
            <input className="field !pl-9" placeholder={t("Tìm ticket, mã hoặc EA")} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></label>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="label"><span>{t("Mã")}</span><select className="field" value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })}><option value="">{t("Tất cả mã")}</option>{symOpts.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
            <div className="label"><span>{t("Hướng")}</span><Seg value={f.side} onChange={(v) => setF({ ...f, side: v })} options={sides()} label={t("Lọc theo hướng")} scroll /></div>
            <div className="label"><span>{t("Kết quả")}</span><Seg value={f.outcome} onChange={(v) => setF({ ...f, outcome: v })} options={outcomes()} label={t("Lọc theo kết quả")} scroll /></div>
          </div>
          <label className="flex items-center gap-3 min-h-[44px] cursor-pointer text-[13.5px]"><input type="checkbox" className="w-[22px] h-[22px]" checked={f.flagged} onChange={(e) => setF({ ...f, flagged: e.target.checked })} /> {t("Chỉ lệnh vi phạm kỷ luật")}</label>
        </div>
      </Panel>
      <Panel title={t("Lệnh đã đóng")} icon={BookOpen} right={<span className="text-[12px] text-faint num">{items.length}/{total}</span>} pad={false}>
        <div className="p-3">
          <Async q={q} rows={6} isEmpty={() => items.length === 0} empty={t("Không có lệnh nào khớp bộ lọc.")}>
            {() => (
              <>
                <ul className="list-none m-0 p-0 grid gap-2">
                  {items.map((d) => (
                    <li key={d.ticket}>
                      <button type="button" className="pos-card w-full text-left cursor-pointer text-inherit font-[inherit]" onClick={() => setOpen(d)} aria-label={t("Lệnh {sym} {side}, lãi lỗ {net}. Mở chi tiết và ghi chú", { sym: d.symbol, side: SIDE[d.side] || "", net: fS(d.net) })}>
                        <div className="flex items-center gap-2"><b>{d.symbol}</b><Chip tone={d.side === "buy" ? "up" : "down"}>{SIDE[d.side] || d.side}</Chip><span className="num text-muted text-[12.5px]">{t("{v} lot", { v: fN(d.volume, 2) })}</span>
                          <b className={cn("num ml-auto", signCls(d.net))}>{fS(d.net)}</b></div>
                        <div className="flex items-center gap-2 text-[12px] text-faint"><span className="num">{dateTime(d.time_close)}</span><span>· {t("giữ {d}", { d: dur(d.hold_s) })}</span>{d.group && d.group !== "manual" && <Chip>{d.group}</Chip>}{d.flags?.length > 0 && <Chip tone="down">{t("vi phạm")}</Chip>}</div>
                      </button>
                    </li>))}
                </ul>
                {all.length < total && !kw && <button className="btn mt-3" onClick={() => setLimit((l) => l + 20)}>{t("Tải thêm")}</button>}
              </>
            )}
          </Async>
        </div>
      </Panel>
      {open && <DealSheet acc={acc} d={open} onClose={() => setOpen(null)} />}
    </>
  );
}

const dims = () => [{ value: "hour", label: t("Giờ") }, { value: "weekday", label: t("Thứ") }, { value: "session", label: t("Phiên") }, { value: "symbol", label: t("Mã") }, { value: "magic", label: t("EA") }, { value: "side", label: t("Hướng") }];
const SESS = { get asia() { return t("Á"); }, get london() { return t("Âu (London)"); }, get ny() { return t("Mỹ (New York)"); }, get overlap() { return t("Giao phiên"); }, get off() { return t("Ngoài phiên"); } };

/** Phân tích theo giờ vào lệnh, thứ, phiên, mã, EA, hướng. Dữ liệu: summary.groups (máy chủ tính trên lệnh đã đóng). */
export function Analysis({ s }) {
  const g = s.groups || {};
  const [dim, setDim] = useState("hour");
  const lab = (r) => (dim === "hour" ? `${String(r.key).padStart(2, "0")}h` : dim === "weekday" ? r.label : dim === "session" ? SESS[r.key] || r.key : dim === "side" ? SIDE[r.key] || r.key : dim === "magic" ? (r.key === "manual" ? t("Thủ công") : r.key) : r.key);
  const rows = (g[dim] || []).filter((r) => r.n > 0 || dim === "hour" || dim === "weekday");
  const shown = dim === "symbol" || dim === "magic" ? rows.slice(0, 12) : rows;
  const best = [...rows].filter((r) => r.n >= 3).sort((a, b) => b.net - a.net);
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 52, right: 8, top: 10, bottom: dim === "symbol" || dim === "magic" ? 44 : 26 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
      formatter: (p) => { const r = shown[p[0].dataIndex]; return `${lab(r)}<br/>${t("Lãi/lỗ")}: <b>${fS(r.net)}</b><br/>${r.win_rate != null ? t("{n} lệnh · thắng {w}%", { n: r.n, w: (r.win_rate * 100).toFixed(0) }) : tn("{n} lệnh đã đóng", r.n)}`; } },
    xAxis: { type: "category", data: shown.map(lab), axisLabel: { color: css("--muted"), fontSize: 10.5, interval: dim === "hour" ? 2 : 0, hideOverlap: true, rotate: dim === "symbol" || dim === "magic" ? 30 : 0 }, axisLine: { lineStyle: { color: css("--line2") } } },
    yAxis: { type: "value", axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } },
    series: [{ type: "bar", barMaxWidth: 22, data: shown.map((r) => ({ value: r.net, itemStyle: { color: r.net >= 0 ? css("--up") : css("--down") } })) }],
  });
  return (
    <div className="grid gap-3">
      <Panel title={t("Lãi/lỗ theo nhóm")} icon={BarChart3} right={<Seg value={dim} onChange={setDim} options={dims()} label={t("Nhóm phân tích")} scroll />}>
        {shown.length === 0 ? <div className="text-muted">{t("Chưa có dữ liệu cho nhóm này.")}</div> : <EChart build={build} deps={[dim, s]} height={230} label={t("Lãi/lỗ theo {dim}", { dim: dims().find((d) => d.value === dim).label })} />}
        <p className="m-0 mt-1 text-[12px] text-faint">{dim === "hour" || dim === "weekday" ? t("Theo thời điểm VÀO lệnh.") : dim === "session" ? t("Phiên theo giờ UTC lúc vào lệnh.") : t("Tính trên lệnh đã đóng.")}</p>
      </Panel>
      {best.length >= 2 && (
        <div className="kpi-grid c3">
          <Kpi label={t("Nhóm hiệu quả nhất")} value={lab(best[0])} tone="up" sub={`${fS(best[0].net)} · ${tn("{n} lệnh đã đóng", best[0].n)}`} />
          <Kpi label={t("Nhóm kém nhất")} value={lab(best[best.length - 1])} tone="down" sub={`${fS(best[best.length - 1].net)} · ${tn("{n} lệnh đã đóng", best[best.length - 1].n)}`} />
          <Kpi label={t("Số nhóm có lệnh")} value={rows.filter((r) => r.n > 0).length} sub={t("chỉ xét nhóm từ 3 lệnh trở lên")} />
        </div>
      )}
      <Panel title={t("Chi tiết")} icon={ListChecks} pad={false}>
        <div className="scroll-x"><table className="tbl" style={{ minWidth: 420 }}>
          <thead><tr><th>{t("Nhóm")}</th><th className="r">{t("Lệnh")}</th><th className="r">{t("Thắng")}</th><th className="r">{t("Lãi/lỗ")}</th></tr></thead>
          <tbody>{shown.filter((r) => r.n > 0).map((r) => <tr key={r.key}><td><b>{lab(r)}</b></td><td className="r num">{r.n}</td><td className="r num">{r.win_rate != null ? `${(r.win_rate * 100).toFixed(0)}%` : "—"}</td><td className={cn("r num font-semibold", signCls(r.net))}>{fS(r.net)}</td></tr>)}</tbody>
        </table></div>
      </Panel>
    </div>
  );
}

export function Performance({ s }) {
  const sm = s.summary, st = s.streaks || {}, hd = s.hold || {}, co = s.costs || {};
  const pick = (...v) => v.find((x) => x != null);
  const rows = [
    ["Payoff ratio", sm.avg_win && sm.avg_loss ? f1(Math.abs(sm.avg_win / sm.avg_loss), 2) : "—", t("lãi TB lệnh thắng ÷ lỗ TB lệnh thua")],
    [t("Chuỗi thắng dài nhất"), pick(st.max_win_streak, st.max_wins, st.best_win_streak, "—"), t("lệnh liên tiếp")],
    [t("Chuỗi thua dài nhất"), pick(st.max_loss_streak, st.max_losses, st.best_loss_streak, "—"), t("lệnh liên tiếp")],
    [t("Giữ lệnh trung bình"), pick(hd.avg_s, hd.avg) != null ? dur(pick(hd.avg_s, hd.avg)) : "—", t("thời gian từ vào đến ra")],
    [t("Lệnh tốt nhất"), fS(sm.best), ""], [t("Lệnh tệ nhất"), fS(sm.worst), ""],
    [t("Phí và swap"), pick(co.total, (co.commission || 0) + (co.swap || 0)) != null ? fS(pick(co.total, (co.commission || 0) + (co.swap || 0))) : "—", t("đã trừ vào lãi/lỗ ròng")],
    [t("Kỳ vọng mỗi lệnh"), fS(sm.expectancy), t("lãi/lỗ trung bình")],
  ];
  return (
    <Panel title={t("Chỉ số hiệu suất chi tiết")} icon={GaugeIcon}>
      <dl className="m-0 grid gap-x-6 sm:grid-cols-2">
        {rows.map(([k, v, sub]) => <div key={k} className="flex items-baseline justify-between gap-3 py-2 border-b border-line"><dt className="text-[13px] text-muted">{k}{sub && <span className="block text-[11.5px] text-faint">{sub}</span>}</dt><dd className="m-0 num font-semibold">{v}</dd></div>)}
      </dl>
    </Panel>
  );
}
