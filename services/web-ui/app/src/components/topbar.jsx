import { useMemo } from "react";
import { useWatchSymbols } from "../lib/prefs";
import { useQuotesLatest, useNow } from "../lib/queries";
import { useQuote, useStream } from "../lib/stream";
import { sessions } from "../lib/session";
import { price, symbolLabel, timeS } from "../lib/format";
import { Freshness, cn } from "./ui";
import { FRESH } from "../lib/freshness";
import { fmtCfg, isVnTz, tzOffsetLabel } from "../ux/fmtconfig";

function TapeItem({ symbol }) {
  const q = useQuote(symbol);
  if (!q) return null;
  const px = q.bid ?? q.ask;
  return (
    <a href="#/thi-truong" className="flex items-center gap-2 px-3 h-[44px] no-underline text-fg whitespace-nowrap" tabIndex={-1}>
      <span className="text-[12px] font-semibold">{symbolLabel(symbol)}</span>
      <span className={cn("num text-[12.5px]", q.dir > 0 ? "up" : q.dir < 0 ? "down" : "")}>
        {price(symbol, px)} <span aria-hidden="true">{q.dir > 0 ? "▲" : q.dir < 0 ? "▼" : ""}</span>
      </span>
    </a>
  );
}

/** Băng giá chạy ngang; tạm dừng khi rê chuột; tắt animation khi người dùng chọn giảm chuyển động. */
export function TickerTape() {
  const watch = useWatchSymbols();
  const items = useMemo(() => watch.slice(0, 40), [watch]);
  useQuotesLatest(items);
  useStream();
  return (
    <div className="tape" role="marquee" aria-label="Băng giá trực tiếp">
      <div className="tape-track">
        {[0, 1].map((k) => (
          <div key={k} className="flex" aria-hidden={k === 1 ? "true" : undefined}>
            {items.map((s) => <TapeItem key={s} symbol={s} />)}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SessionClocks() {
  useNow(15_000);
  const list = sessions();
  return (
    <ul className="flex items-center gap-3 m-0 p-0 list-none text-[11.5px]" aria-label="Phiên giao dịch">
      {list.map((s) => (
        <li key={s.id} className="flex items-center gap-[6px] whitespace-nowrap" title={`${s.name}: ${s.open ? "đang mở" : s.weekend ? "nghỉ cuối tuần" : "đã đóng"}`}>
          <span className={cn("live-dot", s.open && "on")} aria-hidden="true" />
          <span className="text-muted">{s.name}</span>
          <span className="num text-fg">{s.clock}</span>
          <span className="sr-only">{s.open ? "đang mở" : "đóng"}</span>
        </li>
      ))}
    </ul>
  );
}

export function LiveStatus() {
  const st = useStream();
  const now = useNow(2000);
  const on = st.status === "open";
  if (st.status === "off") return null;
  let newest = null, newestSym;
  for (const [sym, q] of st.quotes) {
    const t = Date.parse(q.ts);
    if (Number.isFinite(t) && (newest == null || t > newest)) { newest = t; newestSym = sym; }
  }
  const label = on ? "Trực tiếp" : st.status === "connecting" ? "Đang nối…" : "Mất kết nối";
  return (
    <div className="flex items-center gap-2 text-[12px] whitespace-nowrap">
      <span className={cn("live-dot", on && "on")} style={!on ? { background: "var(--down)" } : undefined} aria-hidden="true" />
      <span className={on ? "text-fg" : "text-down"} role="status" aria-live="polite">{label}</span>
      <span className="hidden sm:inline-flex"><Freshness compact ts={newest} source="tick" label="Tick giá mới nhất trên băng giá" symbol={newestSym} {...FRESH.quote} /></span>
      <span className="hidden md:inline text-faint num" title={isVnTz() ? "Giờ Việt Nam (UTC+7)" : `Múi giờ ${fmtCfg.tz} (${tzOffsetLabel()})`} aria-hidden="true">{timeS(now)}{!isVnTz() && <span className="ml-1 text-accent">{tzOffsetLabel()}</span>}</span>
    </div>
  );
}
