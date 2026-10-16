import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { Activity, Bell, CalendarClock, LineChart, Newspaper, Users, Wallet, Grid2x2, ListOrdered } from "lucide-react";
import { Async, Chip, Freshness, ImpactDots, Panel, PageHead, Sparkline, Stat, Disclaimer } from "../components/ui";
import { FRESH } from "../lib/freshness";
import { api } from "../lib/api";
import { useWatchSymbols } from "../lib/prefs";
import { useAccounts, useAlerts, useNow, useOverview, useQuotesLatest, useRiskAll, useSystem } from "../lib/queries";
import { useQuote } from "../lib/stream";
import { clean, countdown, expertLabel, isQaId, dateTime, money, pct, price, rel, signCls, symbolLabel, symbolMarket, time, dow, date } from "../lib/format";
import { cn } from "../components/ui";
import { RiskBadge, RiskSummary } from "../components/risk";

function useSparks(symbols) {
  const res = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ["spark", s],
      queryFn: ({ signal }) => api("/bars", { symbol: s, tf: "H1", limit: 48, order: "desc" }, signal),
      staleTime: 60_000, refetchInterval: 120_000,
    })),
  });
  return Object.fromEntries(symbols.map((s, i) => {
    const items = [...(res[i].data?.items || [])].reverse();
    const closes = items.map((b) => b.c);
    const change = closes.length > 1 ? ((closes[closes.length - 1] - closes[0]) / closes[0]) * 100 : null;
    return [s, { closes, change, loading: res[i].isPending }];
  }));
}

function Row({ symbol, spark, risk }) {
  const q = useQuote(symbol);
  const px = q?.bid ?? q?.ask;
  const spread = q?.bid != null && q?.ask != null ? q.ask - q.bid : null;
  const flash = q?.dir > 0 ? "tick-up" : q?.dir < 0 ? "tick-down" : "";
  return (
    <tr>
      <td>
        <a href="#/thi-truong" className="no-underline font-semibold">{symbolLabel(symbol)}</a>
        <span className="ml-2 text-[11px] text-faint">{symbolMarket(symbol)}</span>
        {risk && <span className="ml-2"><RiskBadge state={risk} /></span>}
        <span className="block sm:hidden mt-[3px]"><Freshness compact ts={q?.ts} source={q?.source} symbol={symbol} {...FRESH.quote} /></span>
      </td>
      <td className="r"><span key={q?.tickId} className={cn("num px-1 rounded-sm inline-block", flash, q?.dir > 0 ? "up" : q?.dir < 0 ? "down" : "")}>{price(symbol, px)}</span></td>
      <td className="r num text-muted hidden sm:table-cell">{price(symbol, q?.ask)}</td>
      <td className="r num text-faint hidden 2xl:table-cell">{spread == null ? "—" : symbolMarket(symbol) !== "Forex" ? spread.toFixed(2) : symbol.includes("JPY") ? (spread * 100).toFixed(1) : (spread * 10000).toFixed(1)}</td>
      <td className={cn("r num", signCls(spark?.change))}>{pct(spark?.change)}</td>
      <td className="r hidden sm:table-cell"><Sparkline values={spark?.closes} /></td>
      <td className="r hidden sm:table-cell"><Freshness stack ts={q?.ts} source={q?.source} symbol={symbol} {...FRESH.quote} /></td>
    </tr>
  );
}

function Heat({ sparks, watch }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] auto-rows-[minmax(2.9rem,1fr)] gap-[3px] flex-1" role="list" aria-label="Biến động 48 giờ gần nhất">
      {watch.map((s) => {
        const c = sparks[s]?.change;
        const a = c == null ? 0 : Math.min(1, Math.abs(c) / 1.5);
        const col = c == null ? "var(--panel2)" : `color-mix(in srgb, ${c >= 0 ? "var(--up)" : "var(--down)"} ${Math.round(14 + a * 26)}%, var(--panel2))`;
        return (
          <div key={s} role="listitem" className="rounded-[5px] px-2 py-[7px] min-w-0 flex flex-col justify-center" style={{ background: col }}>
            <div className="text-[11.5px] font-semibold truncate">{symbolLabel(s)}</div>
            <div className="num text-[12px]">{pct(c)}</div>
          </div>
        );
      })}
    </div>
  );
}

function Events({ events }) {
  const now = useNow();
  const high = events.filter((e) => e.impact === "high");
  const next = high.find((e) => new Date(e.ts) > now);
  return (
    <div>
      {next && (
        <div className="mb-3 rounded-md border border-line2 bg-panel2 px-3 py-2">
          <div className="text-[11.5px] text-muted">Sự kiện TÁC ĐỘNG CAO kế tiếp</div>
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="num text-[24px] text-accent leading-none">{countdown(next.ts, now)}</span>
            <span className="font-semibold">{next.country} · {next.title}</span>
          </div>
          <div className="text-[11.5px] text-faint">{dow(next.ts)} {date(next.ts)} lúc {time(next.ts)} · dự báo {next.forecast ?? "—"} · kỳ trước {next.previous ?? "—"}</div>
        </div>
      )}
      <ul className="m-0 p-0 list-none divide-y divide-line">
        {events.slice(0, 12).map((e) => {
          const cd = countdown(e.ts, now);
          return (
            <li key={e.event_id} className="flex items-center gap-2 py-[6px]">
              <ImpactDots impact={e.impact} />
              <span className="num text-[12px] text-muted w-[84px] shrink-0">{date(e.ts)} {time(e.ts)}</span>
              <span className="chip">{e.country || "—"}</span>
              <span className="truncate flex-1">{e.title}</span>
              <span className="num text-[12px] text-muted shrink-0">{cd ?? "đã ra"}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Accts({ q }) {
  return (
    <Async q={q} empty="Chưa có tài khoản MT nào gửi dữ liệu." hint="Bật mt-bridge (MT_ENABLED=true) và cấu hình tài khoản investor." rows={3}>
      {(list) => (
        <div className="grid gap-3">
          {list.map((a) => {
            const fl = (a.positions || []).reduce((s, p) => s + (p.profit || 0), 0);
            return (
              <a key={a.account_id} href="#/tai-khoan" className="no-underline text-fg grid grid-cols-3 gap-2 rounded-md border border-line p-2 hover:border-line2">
                <div className="col-span-3 flex flex-wrap items-center gap-x-2 gap-y-1"><b className="break-all">{a.account_id}</b><Chip>{a.platform.toUpperCase()}</Chip><Chip tone="ro">READ-ONLY</Chip><span className="ml-auto"><Freshness compact ts={a.ts} source="MT" {...FRESH.account} /></span></div>
                <Stat label="Equity" value={money(a.equity)} />
                <Stat label="Balance" value={money(a.balance)} />
                <Stat label="Đang mở" value={money(fl)} tone={signCls(fl)} sub={`${a.positions?.length || 0} lệnh`} />
              </a>
            );
          })}
        </div>
      )}
    </Async>
  );
}

export default function Overview() {
  const ov = useOverview();
  const allWatch = useWatchSymbols();
  const watch = useMemo(() => allWatch.slice(0, 24), [allWatch]);
  const quotes = useQuotesLatest(watch);
  const accts = useAccounts();
  const alerts = useAlerts({ limit: 6 });
  const sys = useSystem();
  const sparks = useSparks(watch);
  const risk = useRiskAll();
  const riskBy = useMemo(() => Object.fromEntries((risk.data?.symbols || []).map((s) => [s.symbol, s])), [risk.data]);
  const symbols = useMemo(() => {
    const extra = (quotes.data || []).map((x) => x.symbol).filter((s) => !watch.includes(s));
    return [...watch, ...extra].slice(0, 12);
  }, [quotes.data, watch]);
  const upCount = sys.data?.services?.filter((s) => s.up).length ?? 0;
  const total = sys.data?.services?.length ?? 0;

  return (
    <>
      <PageHead title="Tổng quan" sub="Bức tranh toàn hệ thống trong một màn hình. Tất cả giờ hiển thị theo múi giờ Việt Nam (UTC+7)."
        right={sys.data && <Chip tone={upCount === total && total ? "up" : "down"}>{total ? `${upCount}/${total} service hoạt động` : "Chưa rõ trạng thái service"}</Chip>} />
      <RiskSummary data={risk.data} only={symbols} labels={symbolLabel} />
      <div className="ov-grid">
        <Panel title="Bảng giá" icon={ListOrdered} className="ov-price" pad={false} scroll
          right={<span className="text-[11.5px] text-faint hidden sm:inline">Thay đổi: 48 nến H1</span>}>
          <div className="scroll-x">
            <table className="tbl">
              <thead><tr><th>Mã</th><th className="r">Bid</th><th className="r hidden sm:table-cell">Ask</th><th className="r hidden 2xl:table-cell" title="Chênh lệch bid-ask (pip / điểm)">Spread</th><th className="r">%</th><th className="r hidden sm:table-cell">48h</th><th className="r hidden sm:table-cell" title="Nguồn giá và tuổi của tick gần nhất">Cập nhật</th></tr></thead>
              <tbody>{symbols.map((s) => <Row key={s} symbol={s} spark={sparks[s]} risk={riskBy[s]} />)}</tbody>
            </table>
          </div>
          {quotes.isError && <div className="p-3 text-down text-sm" role="alert">{quotes.error.message}</div>}
        </Panel>

        <Panel title="Bản đồ nhiệt" icon={Grid2x2} className="ov-heat" bodyClass="flex flex-col"><Heat sparks={sparks} watch={watch} /></Panel>
        <Panel title="Lịch kinh tế sắp tới" icon={CalendarClock} className="ov-cal" scroll right={<a className="text-[12px] text-muted" href="#/lich">Xem lịch</a>}>
            <Async q={ov} empty="Không có sự kiện vừa/cao trong 48 giờ tới." isEmpty={(d) => !d.upcoming_events.length}>
            {(d) => <Events events={d.upcoming_events} />}
          </Async>
        </Panel>

        <Panel title="Tin nóng" icon={Newspaper} className="ov-news" scroll right={<a className="text-[12px] text-muted" href="#/tin-tuc">Tất cả tin</a>}>
          <Async q={ov} empty="Chưa có tin trong 24 giờ qua." isEmpty={(d) => !d.news.length} rows={6}>
            {(d) => (
              <ul className="m-0 p-0 list-none divide-y divide-line">
                {d.news.map((n) => (
                  <li key={n.url} className="py-2">
                    <a href={n.url} target="_blank" rel="noopener noreferrer" className="no-underline font-medium leading-snug hover:text-accent">{clean(n.title)}</a>
                    <div className="flex flex-wrap items-center gap-2 mt-[2px] text-[11.5px] text-faint">
                      <span>{rel(n.published_at)}</span>
                      {(n.symbols || []).slice(0, 3).map((s) => <Chip key={s}>{symbolLabel(s)}</Chip>)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Async>
        </Panel>

        <Panel title="Tín hiệu chuyên gia mở" icon={Users} className="ov-sig" scroll right={<a className="text-[12px] text-muted" href="#/chuyen-gia">Chi tiết</a>}>
          <Async q={ov} empty="Chưa có tín hiệu đang mở." hint="Expert-collector mặc định tắt (EXPERT_COLLECTOR_ENABLED)." isEmpty={(d) => !d.expert_signals.filter((s) => !isQaId(s.expert_id) && !isQaId(s.symbol)).length}>
            {(d) => (
              <>
                <ul className="m-0 p-0 list-none divide-y divide-line">
                  {d.expert_signals.filter((s) => !isQaId(s.expert_id) && !isQaId(s.symbol)).slice(0, 12).map((s, i) => (
                    <li key={i} className="flex items-center gap-2 py-[6px]">
                      <Chip tone={s.side === "buy" ? "up" : s.side === "sell" ? "down" : ""}>{s.side === "buy" ? "MUA" : s.side === "sell" ? "BÁN" : "ĐỨNG"}</Chip>
                      <b>{symbolLabel(s.symbol)}</b>
                      <span className="num text-muted text-[12px]">{s.entry != null ? price(s.symbol, s.entry) : ""}</span>
                      <span className="ml-auto text-[11.5px] text-faint truncate max-w-[40%]">{expertLabel(s.expert_id)}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 mb-0 text-[11.5px] text-faint">Dữ liệu công khai để tham khảo, không phải khuyến nghị đầu tư.</p>
              </>
            )}
          </Async>
        </Panel>

        <Panel title="Tài khoản MT" icon={Wallet} className="ov-acct" scroll><Accts q={accts} /></Panel>

        <Panel title="Cảnh báo gần nhất" icon={Bell} className="ov-alerts" scroll right={<a className="text-[12px] text-muted" href="#/canh-bao">Tất cả</a>}>
          <Async q={alerts} empty="Không có cảnh báo nào." rows={3}>
            {(d) => (
              <ul className="m-0 p-0 list-none divide-y divide-line">
                {d.items.map((a) => (
                  <li key={a.id} className="flex items-start gap-2 py-[6px]">
                    <Chip tone={a.level === "crit" ? "down" : a.level === "warn" ? "accent" : ""}>{a.level === "crit" ? "Nghiêm trọng" : a.level === "warn" ? "Cảnh báo" : "Thông tin"}</Chip>
                    <span className="flex-1 min-w-0 truncate" title={clean(a.body || "")}>{clean(a.title)}</span>
                    <span className="text-[11.5px] text-faint shrink-0">{dateTime(a.ts)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Async>
        </Panel>

        <Panel title="Trạng thái hệ thống" icon={Activity} className="ov-sys" scroll right={<a className="text-[12px] text-muted" href="#/he-thong">Chi tiết</a>}>
          <Async q={sys} empty="Chưa có dữ liệu trạng thái." rows={3}>
            {(d) => (
              <div className="flex flex-wrap gap-[6px]">
                {d.services.length === 0 && <span className="text-muted">Chưa nhận được trạng thái service (cần Prometheus hoặc sự kiện trên bus).</span>}
                {d.services.map((s) => <Chip key={s.name} tone={s.up ? "up" : "down"}><span className="live-dot" style={{ background: s.up ? "var(--up)" : "var(--down)" }} aria-hidden="true" />{s.name}<span className="sr-only">{s.up ? " hoạt động" : " ngừng"}</span></Chip>)}
              </div>
            )}
          </Async>
        </Panel>
      </div>
      <div><Disclaimer>Trang này chỉ <b>hiển thị dữ liệu</b>. Không có chức năng đặt lệnh; tài khoản MT4/MT5 kết nối ở chế độ investor (chỉ đọc).</Disclaimer></div>
    </>
  );
}
