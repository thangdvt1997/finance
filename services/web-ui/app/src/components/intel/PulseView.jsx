// Market Pulse: khẩu vị rủi ro, chỉ số biến động, độ rộng thị trường, xu hướng chung theo lớp tài sản, tâm lý tin tức 24h.
// Chỉ số tổng hợp từ nến ngày và tin đã lưu, mang tính tham khảo, không phải khuyến nghị đầu tư.
import { cn, Chip } from "../ui";
import { fpct, usePulse } from "../../lib/intel";
import { AsOf, HeatCell, QState } from "./bits";

const PART_LABEL = {
  breadth_equity: "Độ rộng cổ phiếu",
  breadth_crypto: "Độ rộng tiền ảo",
  news: "Tâm lý tin tức",
  calm: "Mức bình lặng",
  trend: "Xu hướng chung",
};
const tone = (s) => (s >= 60 ? "up" : s <= 40 ? "down" : "");
const clamp = (v, a = 0, b = 100) => Math.max(a, Math.min(b, v));

function Block({ title, sub, children, className }) {
  return (
    <section className={cn("rounded-md border border-line bg-panel p-3 min-w-0", className)} aria-label={title}>
      <h3 className="m-0 text-[13px] font-semibold">{title}</h3>
      {sub && <div className="text-[11.5px] text-faint mb-2">{sub}</div>}
      {!sub && <div className="mb-2" />}
      {children}
    </section>
  );
}

const pt = (t, r) => {
  const a = ((180 - t * 1.8) * Math.PI) / 180;
  return [100 + r * Math.cos(a), 100 - r * Math.sin(a)];
};
const arc = (t0, t1, r) => {
  const [x0, y0] = pt(t0, r);
  const [x1, y1] = pt(t1, r);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
};
const SEGS = [
  [0, 25, "var(--down)"],
  [25, 45, "color-mix(in srgb, var(--down) 50%, var(--accent))"],
  [45, 55, "var(--line2)"],
  [55, 75, "color-mix(in srgb, var(--up) 55%, var(--accent))"],
  [75, 100, "var(--up)"],
];

/** Đồng hồ nửa vòng 0-100 bằng SVG (số và nhãn luôn in rõ, không chỉ dựa vào màu). */
export function Gauge({ score, label }) {
  if (score == null) return <div className="text-muted text-[12.5px]">Chưa đủ dữ liệu để tính khẩu vị rủi ro.</div>;
  const s = clamp(Number(score) || 0);
  const [nx, ny] = pt(s, 60);
  return (
    <div className="grid justify-items-center">
      <svg viewBox="0 0 200 118" width="100%" style={{ maxWidth: 260 }} role="img" aria-label={`Khẩu vị rủi ro ${s.toFixed(0)} trên 100, ${label || ""}`}>
        {SEGS.map(([a, b, c]) => <path key={a} d={arc(a + 0.4, b - 0.4, 80)} fill="none" strokeWidth="14" style={{ stroke: c }} />)}
        <line x1="100" y1="100" x2={nx.toFixed(2)} y2={ny.toFixed(2)} strokeWidth="3" strokeLinecap="round" style={{ stroke: "var(--fg)" }} />
        <circle cx="100" cy="100" r="5" style={{ fill: "var(--fg)" }} />
        <text x="14" y="116" fontSize="9" style={{ fill: "var(--muted)" }}>Sợ hãi</text>
        <text x="186" y="116" fontSize="9" textAnchor="end" style={{ fill: "var(--muted)" }}>Tham lam</text>
      </svg>
      <div className={cn("num text-[28px] font-semibold leading-none -mt-3", tone(s))}>{s.toFixed(0)}</div>
      <div className="text-[13px] font-semibold mt-1">{label}</div>
    </div>
  );
}

function ScoreBar({ label, v }) {
  if (v == null) return <div className="grid grid-cols-[minmax(0,9.5rem)_1fr_2.4rem] items-center gap-2 text-[12px]"><span className="truncate text-muted" title={label}>{label}</span><div className="in-bar" role="img" aria-label={`${label}: chưa có dữ liệu`} /><span className="num text-right text-faint">—</span></div>;
  const s = clamp(Number(v) || 0);
  return (
    <div className="grid grid-cols-[minmax(0,9.5rem)_1fr_2.4rem] items-center gap-2 text-[12px]">
      <span className="truncate text-muted" title={label}>{label}</span>
      <div className="in-bar" role="img" aria-label={`${label}: ${s.toFixed(0)} trên 100`}>
        <i style={{ left: 0, width: `${s}%`, background: s >= 60 ? "var(--up)" : s <= 40 ? "var(--down)" : "var(--accent)", opacity: 0.8 }} />
      </div>
      <span className={cn("num text-right", tone(s))}>{s.toFixed(0)}</span>
    </div>
  );
}

function Appetite({ a }) {
  if (!a) return <div className="text-muted text-[12.5px]">Chưa có dữ liệu khẩu vị rủi ro.</div>;
  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,15rem)_1fr] items-center">
      <Gauge score={a.score} label={a.label} />
      <div className="grid gap-1.5">
        {Object.entries(a.parts || {}).map(([k, v]) => <ScoreBar key={k} label={PART_LABEL[k] || k} v={v} />)}
        <div className="text-[11px] text-faint mt-1">Điểm 0 = rất thận trọng, 100 = rất lạc quan. Chỉ số tham khảo.</div>
      </div>
    </div>
  );
}

function Volatility({ v }) {
  if (!v || v.index == null) return <div className="text-muted text-[12.5px]">Chưa có dữ liệu biến động.</div>;
  const idx = clamp(Number(v.index) || 0);
  return (
    <div className="grid gap-3">
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className="num text-[28px] font-semibold leading-none">{idx.toFixed(1)}</span>
        <Chip tone={idx >= 60 ? "down" : idx <= 35 ? "up" : "accent"}>{v.label}</Chip>
        {v.spy_vol20 != null && <span className="text-[12px] text-muted">Biến động S&amp;P 500 (20 phiên, quy năm): <span className="num">{v.spy_vol20}%</span></span>}
      </div>
      <div className="relative h-[10px] rounded-full" role="img" aria-label={`Chỉ số biến động ${idx.toFixed(1)} trên 100`} style={{ background: "linear-gradient(90deg, var(--up), var(--accent) 55%, var(--down))", opacity: 0.85 }}>
        <b className="absolute rounded-sm" style={{ left: `${idx}%`, top: -3, width: 4, height: 16, transform: "translateX(-50%)", background: "var(--fg)", boxShadow: "0 0 0 2px var(--panel)" }} />
      </div>
      <div className="flex justify-between text-[11px] text-faint -mt-2"><span>Thấp</span><span>Cao</span></div>
      <div className="overflow-x-auto">
        <table className="tbl" aria-label="Biến động theo tài sản chuẩn">
          <thead>
            <tr><th>Tài sản</th><th className="r" title="Độ biến động 20 phiên quy năm">Biến động 20 phiên</th><th className="r" title="Vị trí so với 1 năm gần nhất (0 = thấp nhất, 100 = cao nhất)">Phân vị 1 năm</th><th className="r" title="Biên độ thực trung bình / giá">ATR%</th></tr>
          </thead>
          <tbody>
            {(v.items || []).map((r) => (
              <tr key={r.symbol}>
                <td className="font-semibold">{r.label}</td>
                <td className="r num">{r.vol20 == null ? "—" : `${r.vol20.toFixed(1)}%`}</td>
                <td className="r num">{r.rank == null ? "—" : r.rank.toFixed(0)}</td>
                <td className="r num">{r.atr_pct == null ? "—" : `${r.atr_pct.toFixed(2)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PctBar({ v }) {
  if (v == null) return <span className="text-faint">—</span>;
  return (
    <div className="flex items-center gap-1.5 justify-end">
      <div className="in-bar hidden sm:block" style={{ width: 44, height: 8 }} aria-hidden="true"><i style={{ left: 0, width: `${clamp(v)}%`, background: v >= 50 ? "var(--up)" : "var(--down)", opacity: 0.7 }} /></div>
      <span className="num w-[3.2rem] text-right">{v.toFixed(0)}%</span>
    </div>
  );
}

function Breadth({ classes }) {
  return (
    <div className="overflow-x-auto">
      <table className="tbl" aria-label="Độ rộng thị trường theo lớp tài sản">
        <thead>
          <tr>
            <th>Lớp tài sản</th><th className="r">Số mã</th><th style={{ minWidth: 150 }}>Tăng / giảm</th>
            <th className="r">Trên SMA20</th><th className="r">Trên SMA50</th><th className="r">Trên SMA200</th>
            <th className="r" title="Số mã ở đỉnh 52 tuần">Mới đỉnh</th><th className="r" title="Số mã ở đáy 52 tuần">Mới đáy</th>
          </tr>
        </thead>
        <tbody>
          {classes.map((c) => {
            const n = c.n || 0;
            const flat = Math.max(0, n - (c.adv || 0) - (c.dec || 0));
            const w = (x) => (n ? `${(x / n) * 100}%` : "0%");
            return (
              <tr key={c.class}>
                <td className="font-semibold">{c.name}</td>
                <td className="r num">{n}</td>
                <td>
                  <div className="flex items-center gap-2">
                    <div className="flex h-[10px] flex-1 rounded-sm overflow-hidden bg-panel2" role="img" aria-label={`${c.adv} mã tăng, ${c.dec} mã giảm, ${flat} đi ngang`}>
                      <i style={{ width: w(c.adv || 0), background: "var(--up)", opacity: 0.8 }} />
                      <i style={{ width: w(flat), background: "var(--line2)" }} />
                      <i style={{ width: w(c.dec || 0), background: "var(--down)", opacity: 0.8 }} />
                    </div>
                    <span className="num text-[11.5px] whitespace-nowrap"><span className="up">▲{c.adv}</span> <span className="down">▼{c.dec}</span></span>
                  </div>
                </td>
                <td className="r"><PctBar v={c.above20} /></td>
                <td className="r"><PctBar v={c.above50} /></td>
                <td className="r"><PctBar v={c.above200} /></td>
                <td className="r num up">{c.new_high ?? 0}</td>
                <td className="r num down">{c.new_low ?? 0}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Trend({ classes }) {
  return (
    <div className="overflow-x-auto">
      <div className="hm-grid min-w-[300px]" style={{ gridTemplateColumns: "minmax(7rem,1.4fr) repeat(3, minmax(4.5rem,1fr))" }} role="table" aria-label="Xu hướng trung bình theo lớp tài sản">
        <div role="row" className="contents">
          <span role="columnheader" className="hm-h text-left">Lớp tài sản</span>
          <span role="columnheader" className="hm-h">1 ngày</span>
          <span role="columnheader" className="hm-h">1 tuần</span>
          <span role="columnheader" className="hm-h">1 tháng</span>
        </div>
        {classes.map((c) => (
          <div key={c.class} role="row" className="contents">
            <span role="rowheader" className="hm-r text-[12px]">{c.name}</span>
            <span role="cell"><HeatCell v={c.avg_d1} cap={1.5} /></span>
            <span role="cell"><HeatCell v={c.avg_w1} cap={4} /></span>
            <span role="cell"><HeatCell v={c.avg_m1} cap={8} /></span>
          </div>
        ))}
      </div>
    </div>
  );
}

function News({ n }) {
  if (!n) return <div className="text-muted text-[12.5px]">Chưa có dữ liệu tin tức.</div>;
  const avg = Number(n.avg) || 0;
  const pos = (clamp(avg, -1, 1) + 1) * 50;
  const diff = n.avg != null && n.avg_prev != null ? n.avg - n.avg_prev : null;
  const cnt = n.n_prev ? ((n.n_24h - n.n_prev) / n.n_prev) * 100 : null;
  const tot = (n.pos || 0) + (n.neg || 0);
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div><div className="text-[11.5px] text-muted">Điểm trung bình</div><div className={cn("num text-[18px] font-semibold", avg > 0.05 ? "up" : avg < -0.05 ? "down" : "")}>{n.avg == null ? "—" : `${avg > 0 ? "+" : avg < 0 ? "−" : ""}${Math.abs(avg).toFixed(2)}`}</div><div className="text-[11.5px] text-faint num">{diff == null ? "—" : `${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(2)} so với 24h trước`}</div></div>
        <div><div className="text-[11.5px] text-muted">Số tin 24h</div><div className="num text-[18px] font-semibold">{n.n_24h}</div><div className="text-[11.5px] text-faint num">{cnt == null ? "—" : <>{fpct(cnt, 0)} so với 24h trước</>}</div></div>
        <div><div className="text-[11.5px] text-muted">Tin tích cực</div><div className="num text-[18px] font-semibold up">{n.pos ?? 0}</div></div>
        <div><div className="text-[11.5px] text-muted">Tin tiêu cực</div><div className="num text-[18px] font-semibold down">{n.neg ?? 0}</div></div>
      </div>
      <div>
        <div className="in-meter" role="img" aria-label={`Tâm lý tin tức ${avg.toFixed(2)}, thang từ −1 đến +1`}><b style={{ left: `${pos}%` }} /></div>
        <div className="flex justify-between text-[11px] text-faint mt-1.5"><span>Tiêu cực</span><span>Trung tính</span><span>Tích cực</span></div>
      </div>
      {tot > 0 && (
        <div className="flex h-[8px] rounded-sm overflow-hidden bg-panel2" role="img" aria-label={`Tích cực ${n.pos}, tiêu cực ${n.neg}`}>
          <i style={{ width: `${(n.pos / tot) * 100}%`, background: "var(--up)", opacity: 0.8 }} />
          <i style={{ width: `${(n.neg / tot) * 100}%`, background: "var(--down)", opacity: 0.8 }} />
        </div>
      )}
      {!!(n.topics || []).length && (
        <div className="flex flex-wrap gap-1.5" aria-label="Chủ đề nóng">
          {n.topics.map((t) => <Chip key={t.id} title={`${t.n} tin trong 24h`}>{t.name} · <span className="num">{t.n}</span></Chip>)}
        </div>
      )}
    </div>
  );
}

/** part: "all" | "appetite" | "breadth". */
export function PulseView({ compact = false, part = "all" }) {
  const q = usePulse();
  const st = QState({ q, compact, rows: 6, isEmpty: (x) => !x || (!x.classes?.length && !x.appetite), empty: "Chưa có dữ liệu nhịp thị trường.", hint: "Cần dữ liệu nến ngày đã nạp." });
  if (st) return st;
  const d = q.data;
  const classes = d.classes || [];
  const showAll = part === "all";
  return (
    <div className={cn("grid gap-3", q.isPlaceholderData && "opacity-70")}>
      <div className="flex flex-wrap items-center gap-2">
        <AsOf ts={d.as_of} label="Cập nhật" />
        <span className="text-[11.5px] text-faint" title="Các chỉ số được tổng hợp từ nến ngày và tin đã lưu, không phải khuyến nghị.">Tổng hợp từ nến ngày và tin đã lưu · tham khảo</span>
      </div>
      {(showAll || part === "appetite") && (
        <div className={cn("grid gap-3", showAll && !compact && "xl:grid-cols-2")}>
          <Block title="Khẩu vị rủi ro" sub="Tổng hợp độ rộng, tin tức, mức bình lặng và xu hướng"><Appetite a={d.appetite} /></Block>
          {showAll && <Block title="Chỉ số biến động" sub="Kiểu VIX, 0 = rất bình lặng, 100 = biến động mạnh"><Volatility v={d.volatility} /></Block>}
        </div>
      )}
      {(showAll || part === "breadth") && (
        <>
          <Block title="Độ rộng thị trường theo lớp tài sản" sub="Tỉ lệ mã tăng/giảm trong ngày, mã nằm trên đường trung bình động, mã mới đỉnh/đáy 52 tuần"><Breadth classes={classes} /></Block>
          {showAll && (
            <div className={cn("grid gap-3", !compact && "xl:grid-cols-2")}>
              <Block title="Xu hướng chung theo lớp tài sản" sub="Thay đổi trung bình của các mã trong lớp"><Trend classes={classes} /></Block>
              <Block title="Tâm lý tin tức 24h" sub="Điểm từ −1 (tiêu cực) đến +1 (tích cực)"><News n={d.news} /></Block>
            </div>
          )}
        </>
      )}
      <div className="text-[11.5px] text-faint">{d.disclaimer || "Chỉ số tổng hợp mang tính tham khảo, không phải khuyến nghị đầu tư."}</div>
    </div>
  );
}

export default PulseView;
