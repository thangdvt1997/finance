// Giờ mở cửa các sàn: trạng thái, đếm ngược, timeline 24h, chồng phiên, ngày lễ sắp tới. Tham khảo.
import { useMemo, useState } from "react";
import { CalendarDays, Info } from "lucide-react";
import { Seg, cn } from "../ui";
import { useNow } from "../../lib/queries";
import { MARKETS, MARKET_NOTE, marketById, openIntervals, statusAt, tzParts, upcomingHolidays, zonedToUtc } from "../../lib/marketHours";

const DAY = 864e5;
const VN_TZ = "Asia/Ho_Chi_Minh";
const DOW_VI = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const tfCache = new Map();
const clockFmt = (tz) => {
  let f = tfCache.get(tz);
  if (!f) { f = new Intl.DateTimeFormat("vi-VN", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }); tfCache.set(tz, f); }
  return f;
};
const p2 = (n) => String(n).padStart(2, "0");
const countdown = (ms) => {
  if (ms == null) return "—";
  const s = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return `${d > 0 ? `${d}n ` : ""}${p2(h)}:${p2(m)}:${p2(s % 60)}`;
};
const intersect = (a, b) => {
  const out = [];
  for (const x of a) for (const y of b) { const s = Math.max(x[0], y[0]), e = Math.min(x[1], y[1]); if (e > s) out.push([s, e]); }
  return out;
};
const dmy = (k) => { const [y, m, d] = k.split("-"); return `${d}/${m}/${y}`; };
const OVERLAPS = [["tokyo", "london", "Tokyo + London"], ["london", "newyork", "London + New York"]];

export function MarketHoursView({ compact }) {
  const now = useNow(1000);
  const [zone, setZone] = useState("VN");
  const [holF, setHolF] = useState("all");
  const tz = zone === "VN" ? VN_TZ : "UTC";
  const minute = Math.floor(now / 60000);

  const status = useMemo(() => Object.fromEntries(MARKETS.map((m) => [m.id, statusAt(m, new Date(minute * 60000))])), [minute]);
  const todaySess = useMemo(() => {
    const out = {};
    for (const m of MARKETS) {
      if (m.always) { out[m.id] = "24/7"; continue; }
      const t = minute * 60000, p = tzParts(m.tz, t);
      const ss = Array.isArray(m.sessions) ? (p.dow >= 1 && p.dow <= 5 ? m.sessions : []) : m.sessions[p.dow] || [];
      const f = (x) => `${p2(Math.floor(x / 60) % 24)}:${p2(x % 60)}`;
      out[m.id] = ss.length ? ss.map(([a, b]) => `${f(a)}–${b === 1440 ? "24:00" : f(b)}`).join(", ") : "—";
    }
    return out;
  }, [minute]);

  // timeline: ngày hiện tại theo múi giờ đã chọn
  const dayKey = (() => { const p = tzParts(tz, now); return `${p.y}-${p.m}-${p.d}`; })();
  const tl = useMemo(() => {
    const p = tzParts(tz, Date.now());
    const start = zonedToUtc(tz, p.y, p.m, p.d, 0);
    const end = start + DAY;
    const rows = MARKETS.map((m) => ({
      m,
      iv: openIntervals(m, start + DAY / 2, 1, 1).map(([a, b]) => [Math.max(a, start), Math.min(b, end)]).filter(([a, b]) => b > a),
    }));
    const byId = Object.fromEntries(rows.map((r) => [r.m.id, r.iv]));
    const ov = OVERLAPS.map(([a, b, label]) => ({ label, iv: intersect(byId[a] || [], byId[b] || []) }));
    return { start, rows, ov };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dayKey, tz]);
  const nowPct = ((now - tl.start) / DAY) * 100;
  const pos = (a, b) => ({ left: `${((a - tl.start) / DAY) * 100}%`, width: `${((b - a) / DAY) * 100}%` });
  const hourLabels = [0, 3, 6, 9, 12, 15, 18, 21];

  const hols = useMemo(() => {
    const list = [];
    for (const m of MARKETS) {
      if (holF !== "all" && holF !== m.id) continue;
      for (const h of upcomingHolidays(m, new Date(minute * 60000), 12, 60)) list.push({ ...h, market: m });
    }
    return list.sort((a, b) => a.ts - b.ts || a.market.name.localeCompare(b.market.name));
  }, [minute, holF]);

  return (
    <div className={cn("flex flex-col gap-3", compact && "tm-pad")}>
      <div className="overflow-auto" role="region" aria-label="Trạng thái các sàn" tabIndex={0}>
        <table className="tbl" style={{ minWidth: compact ? 340 : 600 }}>
          <thead>
            <tr>
              <th scope="col" className="text-left">Thị trường</th>
              <th scope="col" className="text-left">Trạng thái</th>
              {!compact && <th scope="col" className="text-right">Giờ địa phương</th>}
              {!compact && <th scope="col" className="text-right">Phiên hôm nay</th>}
              <th scope="col" className="text-right">Tới lần đổi trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {MARKETS.map((m) => {
              const s = status[m.id];
              const left = s.nextChange == null ? null : s.nextChange - now;
              return (
                <tr key={m.id}>
                  <th scope="row" className="text-left whitespace-nowrap font-semibold">{m.name}</th>
                  <td className="whitespace-nowrap">
                    <span aria-hidden="true" style={{ display: "inline-block", width: 8, height: 8, borderRadius: 99, marginRight: 6, background: s.open ? "var(--up)" : "var(--faint)" }} />
                    <b className={s.open ? "up" : "text-muted"}>{s.open ? "Mở" : "Đóng"}</b>
                    <span className="text-faint text-[11.5px]"> · {s.reason}</span>
                  </td>
                  {!compact && <td className="num text-right whitespace-nowrap">{clockFmt(m.tz).format(now)}</td>}
                  {!compact && <td className="num text-right text-[11.5px] leading-tight min-w-[7.5rem]">{todaySess[m.id]}</td>}
                  <td className="num text-right whitespace-nowrap" title={s.nextChange ? `${s.open ? "Đóng" : "Mở"} lúc ${clockFmt(tz).format(s.nextChange)} (${zone === "VN" ? "giờ VN" : "UTC"})` : "Không đổi"}>
                    {left == null ? "—" : <><span className="text-faint text-[11px]">{s.open ? "đóng sau " : "mở sau "}</span>{countdown(left)}</>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <span className="text-[12px] font-semibold">Timeline 24 giờ</span>
          <Seg label="Múi giờ timeline" value={zone} onChange={setZone} options={[{ value: "VN", label: "Giờ VN (UTC+7)" }, { value: "UTC", label: "UTC" }]} />
        </div>
        <div className="overflow-x-auto">
          <div style={{ minWidth: 520 }} role="img" aria-label={`Biểu đồ giờ mở cửa các sàn trong ngày hôm nay, theo ${zone === "VN" ? "giờ Việt Nam" : "UTC"}`}>
            <div className="grid" style={{ gridTemplateColumns: "6.2rem 1fr", rowGap: 3 }}>
              <div />
              <div className="relative h-4 text-[10px] text-faint num">
                {hourLabels.map((h) => <span key={h} style={{ position: "absolute", left: `${(h / 24) * 100}%`, transform: "translateX(-1px)" }}>{p2(h)}h</span>)}
              </div>
              {tl.rows.map(({ m, iv }) => (
                <TlRow key={m.id} label={m.short} color={m.color} iv={iv} pos={pos} nowPct={nowPct} />
              ))}
              {tl.ov.map((o) => (
                <TlRow key={o.label} label="Chồng phiên" sub={o.label} color="var(--accent)" iv={o.iv} pos={pos} nowPct={nowPct} strong />
              ))}
            </div>
          </div>
        </div>
        <p className="m-0 mt-1 text-[11px] text-faint">Vạch đứng = thời điểm hiện tại. Dải màu đậm ở hàng "Chồng phiên" là lúc hai phiên cùng mở (thường biến động và thanh khoản cao hơn).</p>
      </div>

      {!compact && (
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <CalendarDays size={14} className="text-muted" aria-hidden="true" />
            <span className="text-[12px] font-semibold">Ngày lễ sắp tới (60 ngày)</span>
            <select className="field ml-auto" aria-label="Lọc ngày lễ theo sàn" value={holF} onChange={(e) => setHolF(e.target.value)}>
              <option value="all">Mọi sàn</option>
              {MARKETS.filter((m) => m.cal).map((m) => <option key={m.id} value={m.id}>{marketById(m.id).name}</option>)}
            </select>
          </div>
          {hols.length === 0
            ? <div className="text-[12.5px] text-muted">Không có ngày lễ trong 60 ngày tới theo dữ liệu hiện có.</div>
            : (
              <ul className="m-0 p-0 list-none grid gap-1">
                {hols.map((h) => (
                  <li key={`${h.market.id}-${h.date}`} className="flex flex-wrap items-center gap-2 text-[12.5px] rounded border border-line px-2 py-1">
                    <span className="num">{DOW_VI[h.dow]} {dmy(h.date)}</span>
                    <span className="chip">{h.market.short}</span>
                    <span>{h.name}</span>
                    <span className="num text-faint ml-auto text-[11.5px]">{h.daysAway === 0 ? "hôm nay" : `còn ${h.daysAway} ngày`}</span>
                  </li>
                ))}
              </ul>
            )}
        </div>
      )}
      <p className="m-0 text-[11px] text-faint flex gap-1 items-start"><Info size={12} className="shrink-0 mt-[2px]" aria-hidden="true" /><span>{MARKET_NOTE}</span></p>
    </div>
  );
}

function TlRow({ label, sub, color, iv, pos, nowPct, strong }) {
  return (
    <>
      <div className="text-[11.5px] font-semibold truncate self-center" title={sub || label}>{label}{sub && <span className="block text-[10px] font-normal text-faint truncate">{sub}</span>}</div>
      <div className="relative rounded-sm" style={{ height: strong ? 18 : 14, background: "var(--panel2)" }}>
        {iv.map(([a, b], i) => (
          <i key={i} style={{ position: "absolute", top: 0, bottom: 0, ...pos(a, b), background: color, opacity: strong ? 1 : 0.8, borderRadius: 2, outline: strong ? "1px solid var(--fg)" : undefined, outlineOffset: -1 }} />
        ))}
        {nowPct >= 0 && nowPct <= 100 && <b style={{ position: "absolute", top: -1, bottom: -1, left: `${nowPct}%`, width: 2, background: "var(--fg)", opacity: 0.85 }} />}
      </div>
    </>
  );
}

export default MarketHoursView;
