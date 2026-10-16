// Màn "Hôm nay": một cái nhìn cho cả ngày giao dịch (giờ VN): lãi/lỗ, vị thế, tin ảnh hưởng vị thế, giới hạn, 3 việc cần chú ý.
// Chỉ theo dõi, không đặt lệnh. Mobile-first.
import { useMemo } from "react";
import { AlertOctagon, AlertTriangle, BellPlus, BellRing, CalendarClock, ChevronRight, Gauge, ListChecks, PartyPopper, PlugZap, ShieldAlert, Target, Wallet } from "lucide-react";
import { Async, Chip, Kpi, PageHead, Panel, cn } from "../components/ui";
import LimitMeter, { limitValue } from "../components/limits/LimitMeter";
import { RiskBanner, riskView } from "../components/riskwin";
import { marginTone, sideOf, useActiveAccount } from "../lib/account";
import { accountTitle, useAuth } from "../lib/auth";
import { useClock } from "../lib/clock";
import { closedFor, currencyOf, eventsForPositions, reminderId, toggleReminder, useCalendarWindow, useReminders } from "../lib/q_today";
import { LIMIT_KEYS, limitMeta, useLimits } from "../lib/q_notif";
import { useEquity, useJnSummary, useRiskAll } from "../lib/queries";
import { connStatus, ageText } from "../lib/freshness";
import { clean, countdown, dateY, f0, f1, money, signCls, smoney, symbolLabel, time, vnDayKey, vnDayStart } from "../lib/format";
import { t } from "../lib/i18n";

const impactLabel = (i) => (i === "high" ? t("Tác động cao") : t("Tác động vừa"));
const noSl = (p) => !(Number(p.sl) > 0);
const minsLeft = (ts, now) => Math.max(0, Math.ceil((ts - now) / 60e3));

/** Xếp hạng việc cần chú ý: điểm cao hơn lên trước, lấy tối đa 3. Mỗi việc: {key, score, tone, icon, title, detail, href}. */
function buildAttention({ view, conn, limits, evs, riskData, held, now }) {
  const out = [];
  const lm = limits?.progress || {};
  for (const k of LIMIT_KEYS) {
    if (k === "monthly_target_pct") continue;
    const p = lm[k], it = (limits?.items || []).find((x) => x.key === k);
    if (!p || it?.value == null) continue;
    const meta = limitMeta(k), cur = limitValue(k, p.current, p.unit), lim = limitValue(k, it.value, p.unit);
    if (p.level === "hit") out.push({ key: `lim-${k}`, score: 100, tone: "down", icon: AlertOctagon, title: t("Đã chạm giới hạn: {name}", { name: meta.label }), detail: t("{cur} trên giới hạn {lim}. Hệ thống chỉ nhắc, không chặn lệnh.", { cur, lim }), href: "#/gioi-han" });
    else if (p.level === "danger") out.push({ key: `lim-${k}`, score: 92, tone: "down", icon: AlertTriangle, title: t("Rất sát giới hạn: {name}", { name: meta.label }), detail: t("{cur} trên giới hạn {lim}.", { cur, lim }), href: "#/gioi-han" });
    else if (p.level === "warn") out.push({ key: `lim-${k}`, score: 60, tone: "accent", icon: Gauge, title: t("Gần giới hạn: {name}", { name: meta.label }), detail: t("{cur} trên giới hạn {lim}.", { cur, lim }), href: "#/gioi-han" });
  }
  // cửa sổ rủi ro tin cho mã đang giữ
  const wins = (riskData?.symbols || []).filter((s) => held.includes(s.symbol)).map((s) => ({ s, v: riskView(s, now) }));
  const act = wins.filter((w) => w.v.kind === "active"), imm = wins.filter((w) => w.v.kind === "imminent");
  if (act.length) out.push({ key: "win-act", score: 96, tone: "down", icon: ShieldAlert, title: t("Đang trong cửa sổ rủi ro tin"), detail: t("Giá có thể biến động mạnh với {syms}. Còn khoảng {n} phút.", { syms: [...new Set(act.map((w) => symbolLabel(w.s.symbol)))].slice(0, 4).join(", "), n: Math.max(1, Math.ceil(Math.max(...act.map((w) => w.v.left)) / 60e3)) }), href: "#/tin-lich" });
  else if (imm.length) out.push({ key: "win-imm", score: 90, tone: "accent", icon: ShieldAlert, title: t("Sắp vào cửa sổ rủi ro tin"), detail: t("Sau khoảng {n} phút, ảnh hưởng {syms}.", { n: Math.max(1, Math.ceil(Math.min(...imm.map((w) => w.v.left)) / 60e3)), syms: [...new Set(imm.map((w) => symbolLabel(w.s.symbol)))].slice(0, 4).join(", ") }), href: "#/tin-lich" });
  // sự kiện sắp tới ảnh hưởng vị thế
  const next = evs[0];
  if (next) {
    const m = minsLeft(next.ts, now), high = next.event.impact === "high";
    const soon = m <= 60;
    out.push({
      key: "evt", score: soon && high ? 94 : soon ? 70 : high ? 55 : 40, tone: soon && high ? "accent" : "info", icon: CalendarClock,
      title: next.ts <= now ? t("Đang có tin: {title}", { title: clean(next.event.title) }) : t("Tin {title} sau {n} phút", { title: clean(next.event.title), n: m }),
      detail: t("Ảnh hưởng vị thế {syms} ({ccy}).{more}", { syms: next.symbols.map(symbolLabel).slice(0, 4).join(", "), ccy: next.ccy, more: evs.length > 1 ? t(" Còn {n} sự kiện khác trong 24 giờ tới.", { n: evs.length - 1 }) : "" }),
      href: "#/tin-lich",
    });
  }
  if (view?.level != null) {
    const mt = marginTone(view.level);
    if (mt.key === "crit" || mt.key === "high") out.push({ key: "margin", score: 88, tone: "down", icon: AlertTriangle, title: t("Margin rất thấp: {n}%", { n: f0(view.level) }), detail: t("Dễ bị broker đóng lệnh tự động. Xem mục Rủi ro."), href: "#/rui-ro" });
    else if (mt.key === "warn") out.push({ key: "margin", score: 55, tone: "accent", icon: Gauge, title: t("Margin thấp: {n}%", { n: f0(view.level) }), detail: t("Cần theo dõi sát khi giá biến động."), href: "#/rui-ro" });
  }
  if (conn.state === "off" || conn.state === "none") out.push({ key: "ea", score: 85, tone: "down", icon: PlugZap, title: conn.label, detail: conn.state === "none" ? t("Chưa có dữ liệu từ tài khoản này. Xem hướng dẫn gắn EA.") : t("Số liệu có thể đã cũ ({a}). Kiểm tra MT và EA.", { a: ageText(conn.ageS) }), href: "#/ho-so" });
  else if (conn.state === "slow") out.push({ key: "ea", score: 50, tone: "accent", icon: PlugZap, title: conn.label, detail: t("Dữ liệu cuối {a}.", { a: ageText(conn.ageS) }), href: "#/ho-so" });
  const nsl = (view?.positions || []).filter(noSl);
  if (nsl.length) out.push({ key: "nosl", score: 45, tone: "accent", icon: AlertTriangle, title: t("{n} vị thế chưa đặt cắt lỗ (SL)", { n: nsl.length }), detail: [...new Set(nsl.map((p) => symbolLabel(p.symbol)))].slice(0, 5).join(", "), href: "#/vi-the" });
  return out.sort((a, b) => b.score - a.score).slice(0, 3);
}

function Attention({ items }) {
  if (!items.length)
    return <div className="flex items-start gap-2.5 text-[13.5px]"><PartyPopper size={18} className="shrink-0 mt-[1px] text-up" aria-hidden="true" /><div><div className="font-semibold">{t("Chưa có gì đáng lo")}</div><div className="text-muted">{t("Giới hạn, margin, kết nối và tin sắp tới đều ổn.")}</div></div></div>;
  return (
    <ol className="list-none m-0 p-0 grid gap-2">
      {items.map((x, i) => {
        const c = x.tone === "down" ? "var(--down)" : x.tone === "accent" ? "var(--accent)" : "var(--info)";
        return (
          <li key={x.key}>
            <a href={x.href} className="flex items-start gap-3 rounded-xl border px-3 py-2.5 no-underline text-fg min-h-[56px]" style={{ borderColor: `color-mix(in srgb, ${c} 45%, transparent)`, background: `color-mix(in srgb, ${c} 9%, transparent)` }}>
              <span className="num grid place-items-center w-6 h-6 rounded-full text-[12px] font-bold shrink-0 mt-[1px]" style={{ background: c, color: "var(--bg)" }} aria-hidden="true">{i + 1}</span>
              <x.icon size={18} className="shrink-0 mt-[3px]" style={{ color: c }} aria-hidden="true" />
              <span className="min-w-0 flex-1"><span className="block font-semibold text-[14px] break-words">{x.title}</span><span className="block text-[12.5px] text-muted break-words">{x.detail}</span></span>
              <ChevronRight size={16} className="shrink-0 mt-[4px] text-muted" aria-hidden="true" />
            </a>
          </li>
        );
      })}
    </ol>
  );
}

function PnlPanel({ acc, view, snap, multi }) {
  const today = vnDayKey(new Date());
  const cur = currencyOf(acc, snap);
  const from = useMemo(() => vnDayStart(0).toISOString().slice(0, 16) + ":00Z", []);
  const eq = useEquity(acc.id, from);
  const jn = useJnSummary(acc.id, { from: today, to: today });
  const pts = eq.data || [];
  const delta = pts.length >= 2 && view.equity != null ? view.equity - pts[0].equity : null;
  const base = pts.length >= 2 ? pts[0].equity : null;
  const realized = jn.data?.calendar ? jn.data.calendar.filter((x) => x.date === today).reduce((s, x) => s + x.net, 0) : null;
  return (
    <Panel title={t("Lãi/lỗ hôm nay (giờ VN)")} icon={Wallet} right={cur ? <Chip>{cur}</Chip> : null}>
      <div className="kpi-grid">
        <div className="col-span-2">
          <Kpi big label={t("Vốn thay đổi hôm nay")} value={delta == null ? "—" : smoney(delta)} tone={delta == null ? undefined : signCls(delta)}
            sub={delta == null ? t("chưa đủ dữ liệu hôm nay") : base ? t("{p}% so với đầu ngày VN. Nạp/rút cũng làm vốn đổi.", { p: `${delta >= 0 ? "+" : ""}${f1((delta / base) * 100, 2)}` }) : undefined} />
        </div>
        <Kpi label={t("Đã chốt hôm nay")} value={jn.isPending ? "…" : realized == null ? "—" : smoney(realized)} tone={realized == null ? undefined : signCls(realized)} sub={jn.isError ? t("chưa có lịch sử lệnh") : t("lệnh đã đóng")} />
        <Kpi label={t("Đang mở (chưa chốt)")} value={smoney(view.floating)} tone={signCls(view.floating)} sub={t("{n} vị thế · {l} lot", { n: view.positions.length, l: f1(view.lots, 2) })} />
      </div>
      <p className="m-0 mt-2.5 text-[12px] text-faint">{t("Vốn {e} · Số dư {b}{c}.", { e: money(view.equity), b: money(view.balance), c: cur ? ` ${cur}` : "" })}{multi ? ` ${t("Chỉ tài khoản đang chọn; tài khoản khác tiền tệ không được cộng gộp.")}` : ""}{multi ? <> <a className="underline" href="#/danh-muc">{t("Xem danh mục")}</a></> : null}</p>
    </Panel>
  );
}

function LimitsPanel({ accId, q }) {
  const d = q.data;
  const set = (d?.items || []).filter((x) => x.value != null);
  return (
    <Panel title={t("Giới hạn của tôi")} icon={Target} right={<a className="btn sm" href="#/gioi-han">{t("Quản lý")} <ChevronRight size={14} aria-hidden="true" /></a>}>
      {q.isPending ? <div className="skel" style={{ height: 70 }} role="status" aria-label={t("Đang tải")} />
        : q.isError ? <p className="m-0 text-[13px] text-muted">{q.error?.status === 404 ? t("Tính năng giới hạn chưa khả dụng trên máy chủ.") : t("Chưa tải được giới hạn.")}</p>
        : set.length === 0 ? <p className="m-0 text-[13px] text-muted">{t("Bạn chưa đặt giới hạn nào. Đặt mức lỗ tối đa trong ngày hay mức margin tối thiểu để được nhắc kịp thời. Hệ thống chỉ nhắc, không chặn lệnh.")}</p>
        : <div className="grid gap-3">{set.slice(0, 4).map((it) => <LimitMeter key={it.key} k={it.key} item={it} progress={d.progress?.[it.key]} compact />)}</div>}
      <span className="sr-only">{accId}</span>
    </Panel>
  );
}

function EventRow({ ev, now, reminders }) {
  const e = ev.event, high = e.impact === "high";
  const left = ev.ts - now;
  const start = ev.ts - 15 * 60e3, end = ev.ts + 30 * 60e3;
  const inWin = high && now >= start && now <= end;
  return (
    <li className="py-3 border-b border-line last:border-0 grid gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone={high ? "down" : "accent"}>{impactLabel(e.impact)}</Chip>
        <span className="num text-[12.5px] text-muted">{time(ev.ts)}</span>
        <span className="num text-[12.5px] font-semibold ml-auto" style={{ color: inWin ? "var(--down)" : undefined }}>{left <= 0 ? t("đang diễn ra") : t("còn {c}", { c: countdown(ev.ts, now) })}</span>
      </div>
      <div className="font-semibold text-[14px] break-words">{clean(e.title)}</div>
      <div className="text-[12.5px] text-muted">{t("Ảnh hưởng: {syms} ({ccy})", { syms: ev.symbols.map(symbolLabel).slice(0, 5).join(", "), ccy: ev.ccy })}</div>
      {high && <div className="text-[12.5px]" style={{ color: inWin ? "var(--down)" : "var(--accent)" }}>{inWin ? t("Đang trong cửa sổ rủi ro tin (đến {t})", { t: time(end) }) : t("Cửa sổ rủi ro tin: {a} - {b}", { a: time(start), b: time(end) })}</div>}
      <div className="flex flex-wrap items-center gap-2 pt-0.5">
        <span className="text-[12px] text-faint">{t("Nhắc trước:")}</span>
        {[15, 60].map((m) => {
          const on = reminders.some((r) => r.id === reminderId(e.event_id || e.title, m));
          const can = ev.ts - m * 60e3 > now;
          return (
            <button key={m} type="button" className="btn sm" aria-pressed={on} disabled={!can && !on} onClick={() => toggleReminder({ eventId: e.event_id || e.title, title: clean(e.title), ts: ev.ts, mins: m })}
              title={can || on ? undefined : t("Đã quá thời điểm này")} style={on ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}>
              {on ? <BellRing size={15} aria-hidden="true" /> : <BellPlus size={15} aria-hidden="true" />}{m === 60 ? t("1 giờ") : t("{n} phút", { n: m })}{on && <span className="sr-only"> {t("(đã đặt)")}</span>}
            </button>
          );
        })}
      </div>
    </li>
  );
}

export default function Today() {
  const { acc, q, snap, view } = useActiveAccount();
  const { accounts } = useAuth();
  const now = useClock();
  const riskQ = useRiskAll();
  const limQ = useLimits(acc?.id);
  const calQ = useCalendarWindow(24);
  const reminders = useReminders();
  const held = useMemo(() => [...new Set((view?.positions || []).map((p) => p.symbol))], [view]);
  const evs = useMemo(() => eventsForPositions(calQ.data?.items, held, now, 24), [calQ.data, held, now]);
  if (!acc) return <PageHead title={t("Hôm nay")} sub={t("Chọn hoặc được gán một tài khoản MT để xem số liệu.")} />;

  const conn = connStatus({ ts: snap?.ts, nowMs: now, closed: closedFor(held, now), latencyMs: snap?.latency_ms ?? null });
  const attention = view ? buildAttention({ view, conn, limits: limQ.data, evs, riskData: riskQ.data, held, now }) : [];
  const top = view ? [...view.positions].sort((a, b) => Math.abs(b.profit || 0) - Math.abs(a.profit || 0)) : [];

  return (
    <>
      <PageHead title={t("Hôm nay")} sub={`${dateY(now)} · ${accountTitle(acc)}${acc.label ? ` · ${acc.label}` : ""}`} />
      <Async q={q} rows={6} isEmpty={() => !snap} empty={t("Chưa nhận được dữ liệu của tài khoản này.")}
        hint={t("Gắn EA lên một biểu đồ trong MT4/MT5 và bật AutoTrading/WebRequest theo hướng dẫn ở mục Cài đặt. Dữ liệu sẽ hiện sau vài chục giây.")}>
        {() => (
          <>
            <Panel title={attention.length === 3 ? t("3 việc cần chú ý") : t("Việc cần chú ý")} icon={ListChecks}><Attention items={attention} /></Panel>
            <RiskBanner data={riskQ.data} only={held} />
            <div className="cols-2">
              <PnlPanel acc={acc} view={view} snap={snap} multi={accounts.length > 1} />
              <LimitsPanel accId={acc.id} q={limQ} />
            </div>
            <Panel title={t("Vị thế đang giữ")} icon={Wallet} right={<a className="btn sm" href="#/vi-the">{t("Tất cả")} <ChevronRight size={14} aria-hidden="true" /></a>}>
              {top.length === 0 ? <div className="text-muted text-[13.5px]">{t("Không có vị thế mở.")}</div> : (
                <ul className="list-none m-0 p-0 grid">
                  {top.slice(0, 8).map((p, i) => {
                    const ccys = evs.filter((e) => e.symbols.includes(p.symbol));
                    return (
                      <li key={p.position_id || p.ticket || i} className="flex items-center gap-3 py-2.5 border-b border-line last:border-0">
                        <Chip tone={sideOf(p) === "buy" ? "up" : "down"}>{sideOf(p) === "buy" ? t("MUA") : t("BÁN")}</Chip>
                        <div className="min-w-0 flex-1">
                          <b>{symbolLabel(p.symbol)}</b> <span className="num text-muted text-[12.5px]">{p.volume ?? p.lots} lot</span>
                          <div className="flex flex-wrap gap-1 pt-0.5">
                            {noSl(p) && <Chip tone="accent">{t("Chưa có SL")}</Chip>}
                            {ccys.length > 0 && <Chip tone="info"><CalendarClock size={11} aria-hidden="true" /> {t("{n} tin trong 24 giờ", { n: ccys.length })}</Chip>}
                          </div>
                        </div>
                        <b className={cn("num", signCls(p.profit))}>{smoney(p.profit)}</b>
                      </li>
                    );
                  })}
                </ul>
              )}
              {view.orders.length > 0 && <p className="m-0 mt-2 text-[12.5px] text-muted">{t("{n} lệnh chờ đang đặt.", { n: view.orders.length })}</p>}
            </Panel>
            <Panel title={t("Tin liên quan vị thế (24 giờ tới)")} icon={CalendarClock} right={<a className="btn sm" href="#/tin-lich">{t("Lịch đầy đủ")} <ChevronRight size={14} aria-hidden="true" /></a>}>
              {held.length === 0 ? <div className="text-muted text-[13.5px]">{t("Không có vị thế nên chưa có tin nào liên quan.")}</div>
                : calQ.isPending ? <div className="skel" style={{ height: 80 }} role="status" aria-label={t("Đang tải")} />
                : calQ.isError ? <div className="text-muted text-[13.5px]">{t("Chưa tải được lịch kinh tế.")}</div>
                : evs.length === 0 ? <div className="text-muted text-[13.5px]">{t("Không có tin tác động cao hoặc vừa nào ảnh hưởng các mã bạn đang giữ trong 24 giờ tới.")}</div>
                : <ul className="list-none m-0 p-0">{evs.slice(0, 8).map((ev) => <EventRow key={`${ev.event.event_id || ev.event.title}:${ev.ts}`} ev={ev} now={now} reminders={reminders} />)}</ul>}
              <p className="m-0 mt-2 text-[12px] text-faint">{t("Nhắc trước chỉ hiện trên thiết bị này khi bạn đang mở ứng dụng. Cửa sổ rủi ro tin là 15 phút trước đến 30 phút sau sự kiện tác động cao. Chỉ để tham khảo.")}</p>
            </Panel>
          </>
        )}
      </Async>
    </>
  );
}
