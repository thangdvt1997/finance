// Sức mạnh tiền tệ: thanh phân kỳ xếp hạng + lịch sử + cặp chênh lệch lớn nhất. Thống kê tham khảo.
import { useMemo, useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { EChart, css } from "../charts";
import { Seg, cn } from "../ui";
import { QState, AsOf } from "./bits";
import { CCY_COLOR, CCY_NAME, ccyInk, chartHref, fpct, useFxMatrix, useStrength } from "../../lib/intel";

const TFS = ["H1", "H4", "D1"];
const WINS = [3, 5, 10, 20];

const stamp = (ts, tf) => {
  try {
    const o = { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit" };
    if (tf !== "D1") { o.hour = "2-digit"; o.minute = "2-digit"; o.hour12 = false; }
    return new Date(ts).toLocaleString("vi-VN", o);
  } catch { return String(ts); }
};

export function StrengthView({ tf: tf0 = "D1", compact }) {
  const [tf, setTf] = useState(TFS.includes(tf0) ? tf0 : "D1");
  const [win, setWin] = useState(5);
  const [off, setOff] = useState([]);
  const q = useStrength(tf, win);
  const fx = useFxMatrix();
  const d = q.data;
  const list = useMemo(() => d?.currencies || [], [d]);
  const maxAbs = useMemo(() => Math.max(0.05, ...list.map((c) => Math.abs(c.score || 0))), [list]);
  const linkable = useMemo(() => new Set(fx.data?.coverage?.["1d"] || []), [fx.data]);
  const pairLink = (a, b) => {
    const p = [a + b, b + a].find((x) => linkable.has(x));
    return p ? chartHref(p) : null;
  };
  const toggle = (c) => setOff((cur) => (cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c]));
  const ts = useMemo(() => d?.history_ts || [], [d]);

  const build = () => {
    const fg = css("--muted"), line = css("--line"), panel = css("--panel"), line2 = css("--line2");
    return {
      animation: false,
      grid: { left: 44, right: 14, top: 12, bottom: 26 },
      tooltip: {
        trigger: "axis", confine: true, backgroundColor: panel, borderColor: line2, textStyle: { color: css("--fg"), fontSize: 12 },
        valueFormatter: (v) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`),
      },
      xAxis: { type: "category", data: ts.map((t) => stamp(t, tf)), axisLine: { lineStyle: { color: line2 } }, axisLabel: { color: fg, fontSize: 11 } },
      yAxis: { type: "value", scale: true, axisLabel: { color: fg, fontSize: 11, formatter: (v) => `${v}%` }, splitLine: { lineStyle: { color: line } } },
      series: list.filter((c) => !off.includes(c.ccy)).map((c, i) => ({
        name: c.ccy, type: "line", smooth: false, showSymbol: ts.length < 30, symbolSize: 5, data: c.history || [],
        lineStyle: { width: 2, color: CCY_COLOR[c.ccy] }, itemStyle: { color: CCY_COLOR[c.ccy] },
        markLine: i === 0 ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: line2, type: "dashed" }, data: [{ yAxis: 0 }] } : undefined,
      })),
    };
  };

  return (
    <div className={cn("flex flex-col gap-3", compact && "tm-pad")}>
      <div className="flex flex-wrap items-center gap-2">
        <Seg label="Khung thời gian" value={tf} onChange={setTf} options={TFS} />
        <label className="flex items-center gap-1 text-[12px] text-muted">Cửa sổ
          <select className="field" aria-label="Số nến trong cửa sổ" value={win} onChange={(e) => setWin(Number(e.target.value))}>
            {WINS.map((w) => <option key={w} value={w}>{w} nến</option>)}
          </select>
        </label>
        <span className="ml-auto flex items-center gap-2">
          {d?.coverage && <span className="chip" title="Số cặp có đủ dữ liệu / số cặp cần">Phủ {d.coverage}</span>}
          <AsOf ts={d?.as_of} />
        </span>
      </div>

      <QState q={q} compact={compact} rows={6} empty="Chưa có dữ liệu sức mạnh tiền tệ." isEmpty={(x) => !x || !(x.currencies || []).length} />
      {d && list.length > 0 && (
        <>
          {(d.missing || []).length > 0 && (
            <div role="note" className="flex gap-2 items-start text-[12px] text-muted rounded-md border border-line2 bg-panel2 px-2 py-1.5">
              <AlertTriangle size={14} className="text-accent shrink-0 mt-[1px]" aria-hidden="true" />
              <span>Thiếu dữ liệu cho: <b className="num">{d.missing.join(", ")}</b> ({tf}). Điểm các tiền tệ liên quan chưa đầy đủ, không được suy đoán thay thế.</span>
            </div>
          )}
          <ol className="m-0 p-0 list-none grid gap-[5px]" aria-label={`Xếp hạng sức mạnh tiền tệ khung ${tf}`}>
            {list.map((c) => {
              const w = Math.min(50, (Math.abs(c.score) / maxAbs) * 50);
              const pos = c.score >= 0;
              return (
                <li key={c.ccy} className="grid items-center gap-2 grid-cols-[1.6rem_4.4rem_1fr_4.2rem]" title={`${c.ccy} · ${CCY_NAME[c.ccy] || ""} · hạng ${c.rank} · điểm ${fpct(c.score)}`}>
                  <span className="num text-[11px] text-faint text-right">#{c.rank}</span>
                  <span className="min-w-0">
                    <b className="text-[12.5px]" style={{ color: ccyInk(c.ccy) }}>{c.ccy}</b>
                    {!compact && <span className="text-[11px] text-faint block truncate leading-tight">{CCY_NAME[c.ccy]}</span>}
                  </span>
                  <span className="in-bar" style={{ height: 18 }} role="presentation">
                    <i style={{ left: "50%", width: 1, background: "var(--line2)" }} />
                    <i style={{ left: pos ? "50%" : `${50 - w}%`, width: `${w}%`, background: CCY_COLOR[c.ccy] || (pos ? "var(--up)" : "var(--down)"), opacity: 0.9 }} />
                  </span>
                  <span className={cn("num text-[12px] text-right", pos ? "up" : "down")}>{fpct(c.score)}</span>
                </li>
              );
            })}
          </ol>

          <div>
            <div className="flex flex-wrap items-center gap-1 mb-1" role="group" aria-label="Bật hoặc tắt đường lịch sử từng tiền tệ">
              <span className="text-[11.5px] text-muted mr-1">Lịch sử ({ts.length} điểm)</span>
              {list.map((c) => (
                <button key={c.ccy} type="button" className="chip cursor-pointer" aria-pressed={!off.includes(c.ccy)} onClick={() => toggle(c.ccy)}
                  style={{ opacity: off.includes(c.ccy) ? 0.45 : 1, borderColor: CCY_COLOR[c.ccy], textDecoration: off.includes(c.ccy) ? "line-through" : "none" }}>
                  <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 99, background: CCY_COLOR[c.ccy], display: "inline-block" }} /> {c.ccy}
                </button>
              ))}
            </div>
            {ts.length < 2
              ? <div className="text-[12px] text-faint">Chưa đủ điểm lịch sử để vẽ đường.</div>
              : <div className="flex flex-col" style={{ minHeight: compact ? 150 : 230 }}><EChart build={build} deps={[d, off, tf]} height={compact ? 150 : 230} label="Lịch sử điểm sức mạnh các tiền tệ" /></div>}
          </div>

          {!compact && (d.ideas || []).length > 0 && (
            <div>
              <div className="text-[12px] font-semibold mb-1">Cặp chênh lệch lớn nhất (tham khảo)</div>
              <ul className="m-0 p-0 list-none grid gap-1">
                {d.ideas.map((x) => {
                  const href = pairLink(x.strong, x.weak);
                  return (
                    <li key={x.strong + x.weak} className="flex items-center gap-2 text-[12.5px] rounded border border-line px-2 py-1">
                      <b style={{ color: ccyInk(x.strong) }}>{x.strong}</b><span className="text-faint">mạnh</span>
                      <span aria-hidden="true">›</span>
                      <b style={{ color: ccyInk(x.weak) }}>{x.weak}</b><span className="text-faint">yếu</span>
                      <span className="num ml-auto">{Number(x.gap).toFixed(2)}%</span>
                      {href ? <a href={href} className="text-[11.5px]">Biểu đồ</a> : <span className="text-[11px] text-faint" title="Không có biểu đồ trực tiếp cho cặp chéo này">—</span>}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <p className="m-0 text-[11px] text-faint flex gap-1 items-start">
            <Info size={12} className="shrink-0 mt-[2px]" aria-hidden="true" />
            <span>Điểm = % biến động của tiền tệ so với rổ tiền tệ còn lại, tính từ các cặp quy về USD trong cửa sổ {d.window ?? win} nến. Thống kê tham khảo, không phải khuyến nghị.</span>
          </p>
        </>
      )}
    </div>
  );
}

export default StrengthView;
