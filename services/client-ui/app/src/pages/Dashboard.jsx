import { useMemo, useState } from "react";
import { Activity, ArrowRight, Gauge, Layers, LineChart as LineIcon, Plug, Wallet } from "lucide-react";
import { Async, Chip, Kpi, Notice, PageHead, Panel, ReadOnlyChip, Seg, cn } from "../components/ui";
import EquityChart, { RANGES } from "../components/equitychart";
import MarginGauge from "../components/gauge";
import { EChart, css } from "../components/charts";
import { RiskBanner } from "../components/riskwin";
import ShareButton from "../components/share";
import { marginTone, sideOf, useActiveAccount } from "../lib/account";
import { useEquity, useJnSummary, useRiskAccount, useRiskAll } from "../lib/queries";
import { useClock } from "../lib/clock";
import { ageText, connStatus } from "../lib/freshness";
import { f0, f1, money, price, signCls, smoney, symbolLabel, vnDayKey, vnDayStart } from "../lib/format";
import { accountTitle } from "../lib/auth";
import { t } from "../lib/i18n";

function EaStatus({ ts }) {
  const now = useClock();
  const s = connStatus({ ts, nowMs: now });
  const tone = s.state === "on" ? "up" : s.state === "slow" ? "accent" : "down";
  return <Chip tone={tone} title={s.ageS != null ? t("Dữ liệu cuối {a}", { a: ageText(s.ageS) }) : undefined}><span className={cn("live-dot", s.state === "on" ? "on" : s.state === "slow" ? "warn" : "off")} /> {s.label}{s.ageS != null ? ` · ${ageText(s.ageS)}` : ""}</Chip>;
}

/** Thay đổi vốn từ đầu ngày VN (ảnh chụp equity). Nạp/rút trong ngày cũng làm vốn đổi — ghi chú ở phụ đề. */
function TodayPnl({ id, equity }) {
  const from = useMemo(() => vnDayStart(0).toISOString().slice(0, 16) + ":00Z", []);
  const q = useEquity(id, from);
  const pts = q.data || [];
  if (q.isPending) return <Kpi label={t("Vốn thay đổi hôm nay")} value="…" />;
  if (pts.length < 2 || equity == null) return <Kpi label={t("Vốn thay đổi hôm nay")} value="—" sub={t("chưa đủ dữ liệu hôm nay")} />;
  const start = pts[0].equity, d = equity - start;
  return <Kpi label={t("Vốn thay đổi hôm nay")} value={smoney(d)} tone={signCls(d)} sub={start ? t("{p}% so với đầu ngày VN", { p: `${d >= 0 ? "+" : ""}${f1((d / start) * 100, 2)}` }) : undefined} />;
}

/** Lãi/lỗ ĐÃ CHỐT hôm nay / tuần / tháng (giờ VN) từ lịch lãi-lỗ của nhật ký, cộng lãi/lỗ đang mở. */
function PeriodPnl({ id, floating }) {
  const today = vnDayKey(new Date());
  const monthStart = today.slice(0, 8) + "01";
  const q = useJnSummary(id, { from: monthStart, to: today });
  const cal = q.data?.calendar || [];
  const weekStart = useMemo(() => { const d = vnDayStart(0); const wd = (new Date(d.getTime() + 7 * 3600e3).getUTCDay() + 6) % 7; return vnDayKey(new Date(d.getTime() - wd * 86400e3)); }, []);
  const sum = (pred) => cal.filter((x) => pred(x.date)).reduce((s, x) => s + x.net, 0);
  const rows = [[t("Hôm nay"), sum((d) => d === today)], [t("Tuần này"), sum((d) => d >= weekStart)], [t("Tháng này"), sum((d) => d >= monthStart)]];
  if (q.isPending) return <Kpi label={t("Lãi/lỗ đã chốt")} value="…" />;
  if (q.isError) return <Kpi label={t("Lãi/lỗ đã chốt")} value="—" sub={t("chưa có lịch sử lệnh")} />;
  return (
    <div className="kpi col-span-2">
      <div className="k">{t("Lãi/lỗ đã chốt (giờ VN)")}</div>
      <div className="grid grid-cols-3 gap-2 pt-1">
        {rows.map(([l, v]) => <div key={l}><div className="text-[11.5px] text-faint">{l}</div><div className={cn("num text-[16px] font-semibold", signCls(v))}>{smoney(v)}</div></div>)}
      </div>
      <div className="s pt-1">{t("Đang mở:")} <span className={cn("num", signCls(floating))}>{smoney(floating)}</span></div>
    </div>
  );
}

function ExposureBars({ risk, view }) {
  const rows = useMemo(() => {
    const bs = risk?.exposure?.by_symbol;
    if (bs?.length) return bs.slice(0, 8).map((s) => ({ name: symbolLabel(s.symbol), v: s.net_value ?? 0, lots: s.net_lots }));
    const m = new Map();
    for (const p of view?.positions || []) { const k = symbolLabel(p.symbol); m.set(k, (m.get(k) || 0) + (sideOf(p) === "sell" ? -1 : 1) * (Number(p.volume ?? p.lots) || 0)); }
    return [...m.entries()].map(([name, v]) => ({ name, v, lots: v, lot: true }));
  }, [risk, view]);
  if (!rows.length) return <div className="text-muted">{t("Không có vị thế mở.")}</div>;
  const lot = rows[0].lot;
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 62, right: 14, top: 6, bottom: 22 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (p) => `${p[0].name}<br/><b>${lot ? `${f1(p[0].value, 2)} lot` : money(p[0].value)}</b>` },
    xAxis: { type: "value", axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } },
    yAxis: { type: "category", inverse: true, data: rows.map((r) => r.name), axisLabel: { color: css("--fg"), fontSize: 11.5 }, axisLine: { lineStyle: { color: css("--line2") } } },
    series: [{ type: "bar", barMaxWidth: 18, data: rows.map((r) => ({ value: +r.v.toFixed(2), itemStyle: { color: r.v >= 0 ? css("--up") : css("--down") } })) }],
  });
  return (
    <>
      <EChart build={build} deps={[rows]} height={Math.max(140, rows.length * 26 + 28)} label={t("Tiếp xúc ròng theo mã")} />
      <p className="m-0 text-[12px] text-faint">{lot ? t("Khối lượng ròng (lot)") : t("Giá trị ròng")}: {t("xanh = nghiêng mua, đỏ = nghiêng bán.")}</p>
    </>
  );
}

function CcyBars({ risk }) {
  const rows = (risk?.exposure?.by_currency || []).filter((c) => c.pct_equity != null).slice(0, 8);
  if (!rows.length) return <div className="text-muted text-[13px]">{t("Chưa có dữ liệu tiếp xúc theo tiền tệ.")}</div>;
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 50, right: 14, top: 6, bottom: 22 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (p) => t("{n}<br/><b>{v}% vốn</b>", { n: p[0].name, v: f0(p[0].value) }) },
    xAxis: { type: "value", axisLabel: { color: css("--muted"), fontSize: 11, formatter: "{value}%" }, splitLine: { lineStyle: { color: css("--line") } } },
    yAxis: { type: "category", inverse: true, data: rows.map((r) => r.ccy), axisLabel: { color: css("--fg"), fontSize: 11.5 }, axisLine: { lineStyle: { color: css("--line2") } } },
    series: [{ type: "bar", barMaxWidth: 18, data: rows.map((r) => ({ value: +r.pct_equity.toFixed(1), itemStyle: { color: r.pct_equity >= 0 ? css("--up") : css("--down") } })) }],
  });
  return <EChart build={build} deps={[rows]} height={Math.max(140, rows.length * 26 + 28)} label={t("Tiếp xúc ròng theo tiền tệ, phần trăm vốn")} />;
}

export default function Dashboard() {
  const { acc, q, snap, view } = useActiveAccount();
  const [range, setRange] = useState("1W");
  const riskQ = useRiskAll();
  const acctRisk = useRiskAccount(acc?.id);
  const held = useMemo(() => [...new Set((view?.positions || []).map((p) => p.symbol))], [view]);

  if (!acc) return <PageHead title={t("Tổng quan tài khoản")} sub={t("Chọn hoặc được gán một tài khoản MT để xem số liệu.")} />;
  const mt = view ? marginTone(view.level) : null;
  const top = [...(view?.positions || [])].sort((a, b) => Math.abs(b.profit || 0) - Math.abs(a.profit || 0)).slice(0, 5);
  const r = acctRisk.data;
  const lev = r?.exposure?.leverage_gross;

  return (
    <>
      <PageHead title={t("Tổng quan tài khoản")} sub={`${accountTitle(acc)}${acc.label ? ` · ${acc.label}` : ""}${acc.server ? ` · ${acc.server}` : ""}`}
        right={<><EaStatus ts={snap?.ts} /><ReadOnlyChip /><ShareButton /></>} />

      <Async q={q} rows={6} isEmpty={() => !snap} empty={t("Chưa nhận được dữ liệu của tài khoản này.")}
        hint={t("Gắn EA lên một biểu đồ trong MT4/MT5 và bật AutoTrading/WebRequest theo hướng dẫn ở mục Cài đặt. Dữ liệu sẽ hiện sau vài chục giây.")}>
        {() => (
          <>
            {connStatus({ ts: snap.ts }).state === "off" && <Notice tone="down" icon={Plug} title={t("Mất kết nối EA")}>{t("Chưa nhận dữ liệu mới từ MT trong hơn 10 phút. Số liệu bên dưới có thể đã cũ. Kiểm tra MT còn mở, EA còn gắn trên biểu đồ và mạng ổn định.")}</Notice>}
            {view.level != null && mt.key !== "safe" && (
              <Notice tone={mt.key === "warn" ? "warn" : "down"} title={t("Mức margin {n}%: {l}", { n: f0(view.level), l: mt.label })}>
                {t("Margin level là tỷ lệ vốn so với margin đang dùng. Càng thấp càng gần bị broker đóng lệnh tự động. Xem chi tiết ở mục")} <a className="underline" href="#/rui-ro">{t("Rủi ro")}</a>.
              </Notice>
            )}
            <RiskBanner data={riskQ.data} only={held} />

            <div id="share-area" className="grid gap-[.85rem]">
              <div className="kpi-grid c4">
                <Kpi big label={t("Vốn (equity)")} value={money(view.equity)} sub={t("Số dư {n}", { n: money(view.balance) })} />
                <Kpi big label={t("Lãi/lỗ đang mở")} value={smoney(view.floating)} tone={signCls(view.floating)} sub={t("{n} vị thế · {l} lot", { n: view.positions.length, l: f1(view.lots, 2) })} />
                <TodayPnl id={acc.id} equity={view.equity} />
                <PeriodPnl id={acc.id} floating={view.floating} />
              </div>

              <div className="cols-2">
                <Panel title={t("Sức khoẻ margin")} icon={Gauge}>
                  <MarginGauge level={view.level} />
                  <p className="m-0 text-center text-[13px]" style={{ color: mt.color }}>{mt.label}</p>
                  <div className="kpi-grid mt-3">
                    <Kpi label={t("Margin đã dùng")} value={money(view.margin)} sub={t("vốn đang bị giữ")} />
                    <Kpi label={t("Margin còn trống")} value={money(view.free)} sub={t("dùng để mở thêm lệnh")} />
                    <Kpi label={t("Đòn bẩy hiệu dụng")} value={lev == null ? "—" : `${f1(lev, 2)}x`} sub={lev == null ? t("chưa tính được") : t("giá trị vị thế ÷ vốn")} />
                    <Kpi label={t("Cách stop-out")} value={r?.margin?.distance_to_stop_out != null ? money(r.margin.distance_to_stop_out) : "—"} sub={t("mức lỗ còn chịu được")} />
                  </div>
                </Panel>
                <Panel title={t("Đường vốn")} icon={LineIcon} right={<Seg value={range} onChange={setRange} options={Object.keys(RANGES)} label={t("Khoảng thời gian")} scroll />}>
                  <EquityChart id={acc.id} range={range} />
                </Panel>
              </div>
            </div>

            <div className="cols-2">
              <Panel title={t("Tiếp xúc theo mã")} icon={Layers}><ExposureBars risk={r} view={view} /></Panel>
              <Panel title={t("Tiếp xúc theo tiền tệ")} icon={Layers}><CcyBars risk={r} /></Panel>
            </div>

            <Panel title={t("Vị thế nổi bật")} icon={Wallet} right={<a className="btn sm" href="#/vi-the">{t("Tất cả")} <ArrowRight size={14} aria-hidden="true" /></a>}>
              {top.length === 0 ? <div className="text-muted">{t("Không có vị thế mở.")}</div> : (
                <ul className="list-none m-0 p-0 grid">
                  {top.map((p, i) => (
                    <li key={p.position_id || p.ticket || i} className="flex items-center gap-3 py-2.5 border-b border-line last:border-0">
                      <Chip tone={sideOf(p) === "buy" ? "up" : "down"}>{sideOf(p) === "buy" ? t("MUA") : t("BÁN")}</Chip>
                      <div className="min-w-0 flex-1"><b>{symbolLabel(p.symbol)}</b> <span className="num text-muted text-[12.5px]">{p.volume ?? p.lots} lot</span>
                        <div className="text-[12px] text-faint num truncate">{t("vào {a} → {b}", { a: price(p.symbol, p.price_open ?? p.open_price), b: price(p.symbol, p.price_current ?? p.price) })}</div></div>
                      <b className={cn("num", signCls(p.profit))}>{smoney(p.profit)}</b>
                    </li>
                  ))}
                </ul>
              )}
              {view.orders.length > 0 && <p className="m-0 mt-2 text-[12.5px] text-muted"><Activity size={13} className="inline mr-1" aria-hidden="true" />{t("{n} lệnh chờ đang đặt.", { n: view.orders.length })}</p>}
            </Panel>
          </>
        )}
      </Async>
    </>
  );
}
