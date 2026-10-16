// Danh mục: nhiều tài khoản MT của cùng một khách. Tài khoản KHÁC TIỀN TỆ không được cộng gộp: số liệu chia theo nhóm tiền tệ.
import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { ArrowRight, Layers, LineChart as LineIcon, PieChart as PieIcon, Wallet } from "lucide-react";
import { Async, Chip, Kpi, Notice, PageHead, Panel, ReadOnlyChip, Seg, cn } from "../components/ui";
import { EChart, css } from "../components/charts";
import { deriveView, marginTone } from "../lib/account";
import { accountTitle, useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { useAccountSnaps } from "../lib/queries";
import { useClock } from "../lib/clock";
import { ageText, connStatus } from "../lib/freshness";
import { currencyOf } from "../lib/q_today";
import { dateTime, f0, f1, money, signCls, smoney, symbolLabel } from "../lib/format";
import { t } from "../lib/i18n";

const RANGES = [7, 30, 90];
const rangeLabel = (d) => t("{n} ngày", { n: d });

function Combined({ ids, days, cur }) {
  const from = useMemo(() => new Date(Date.now() - days * 86400e3).toISOString().slice(0, 16) + ":00Z", [days]);
  const res = useQueries({ queries: ids.map((id) => ({ queryKey: ["equity", { account_id: id, from, limit: 5000 }], queryFn: ({ signal }) => api("/equity-history", { account_id: id, from, limit: 5000 }, signal), staleTime: 60_000 })) });
  const loading = res.some((r) => r.isPending), err = res.find((r) => r.isError);
  const series = useMemo(() => {
    if (loading) return [];
    const HOUR = days <= 7 ? 3600e3 : 6 * 3600e3;
    const per = res.map((r) => (r.data || []).map((p) => [Math.floor(new Date(p.ts).getTime() / HOUR) * HOUR, p.equity]));
    const buckets = [...new Set(per.flat().map((x) => x[0]))].sort((a, b) => a - b);
    const idx = per.map(() => 0), last = per.map(() => null);
    return buckets.map((tm) => {
      let sum = 0, ok = true;
      per.forEach((arr, k) => { while (idx[k] < arr.length && arr[idx[k]][0] <= tm) { last[k] = arr[idx[k]][1]; idx[k]++; } if (last[k] == null) ok = false; else sum += last[k]; });
      return ok ? [tm, +sum.toFixed(2)] : null;
    }).filter(Boolean);
  }, [res, loading, days]); // eslint-disable-line react-hooks/exhaustive-deps
  if (loading) return <div className="skel" style={{ height: 200 }} role="status" aria-label={t("Đang tải")} />;
  if (err) return <div className="text-down" role="alert">{err.error?.message || t("Không tải được lịch sử vốn.")}</div>;
  if (series.length < 2) return <div className="text-muted">{t("Chưa đủ lịch sử vốn của tất cả tài khoản để vẽ đường tổng.")}</div>;
  const build = () => {
    const vals = series.map((s) => s[1]), lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.15 || Math.max(Math.abs(hi) * 0.002, 1);
    const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
    return { animation: false, backgroundColor: "transparent", grid: { left: 58, right: 10, top: 12, bottom: 24 },
      tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (a) => `${dateTime(a[0].value[0])}<br/>${t("Tổng vốn:")} <b>${money(a[0].value[1], cur)}</b>` },
      xAxis: { type: "time", ...axis, axisLabel: { ...axis.axisLabel, hideOverlap: true }, splitLine: { show: false } },
      yAxis: { type: "value", min: lo - pad, max: hi + pad, ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => v.toLocaleString("en-US", { maximumFractionDigits: 0 }) } },
      series: [{ type: "line", data: series, showSymbol: false, lineStyle: { width: 2, color: css("--accent") }, areaStyle: { color: css("--accent-bg") } }] };
  };
  return <EChart build={build} deps={[series]} height={230} label={t("Đường tổng vốn của các tài khoản cùng tiền tệ")} />;
}

function Allocation({ rows, cur }) {
  const total = rows.reduce((s, r) => s + Math.max(r.equity || 0, 0), 0);
  if (!total) return <div className="text-muted">{t("Chưa có vốn để phân bổ.")}</div>;
  const build = () => ({
    animation: false, backgroundColor: "transparent",
    tooltip: { trigger: "item", confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (p) => `${p.name}<br/><b>${money(p.value, cur)}</b> (${p.percent}%)` },
    color: [css("--accent"), css("--info"), css("--up"), css("--down"), css("--muted")],
    series: [{ type: "pie", radius: ["54%", "78%"], label: { show: false }, itemStyle: { borderColor: css("--panel"), borderWidth: 2 }, data: rows.map((r) => ({ name: r.title, value: Math.max(r.equity || 0, 0) })) }],
  });
  return (
    <div className="grid gap-2 sm:grid-cols-[180px_1fr] items-center">
      <EChart build={build} deps={[rows]} height={180} label={t("Phân bổ vốn theo tài khoản")} />
      <ul className="list-none m-0 p-0 grid gap-1.5 text-[13px]">{rows.map((r, i) => <li key={r.id} className="flex items-center gap-2"><i className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: ["var(--accent)", "var(--info)", "var(--up)", "var(--down)", "var(--muted)"][i % 5] }} aria-hidden="true" /><span className="num truncate">{r.title}</span><b className="num ml-auto">{f1((Math.max(r.equity || 0, 0) / total) * 100, 0)}%</b></li>)}</ul>
    </div>
  );
}

/** Một nhóm tiền tệ: tổng hợp chỉ gồm các tài khoản cùng tiền tệ. */
function Group({ cur, rows, days, setDays, showTitle, total }) {
  const live = rows.filter((r) => r.v);
  const sum = (k) => live.reduce((s, r) => s + (r.v[k] || 0), 0);
  return (
    <section className="grid gap-[.85rem]" aria-label={showTitle ? t("Nhóm tiền tệ {c}", { c: cur || t("không rõ") }) : undefined}>
      {showTitle && <h2 className="m-0 text-[15px] font-bold flex items-center gap-2">{t("Nhóm tiền tệ {c}", { c: cur || t("không rõ") })}<Chip>{t("{n} tài khoản", { n: rows.length })}</Chip></h2>}
      <div className="kpi-grid c4">
        <Kpi big label={t("Tổng vốn (equity)")} value={money(sum("equity"), cur)} sub={t("Số dư {n}", { n: money(sum("balance"), cur) })} />
        <Kpi big label={t("Lãi/lỗ đang mở")} value={smoney(sum("floating"))} tone={signCls(sum("floating"))} sub={t("{n} vị thế · {l} lot", { n: live.reduce((s, r) => s + r.v.positions.length, 0), l: f1(sum("lots"), 2) })} />
        <Kpi label={t("Margin đã dùng")} value={money(sum("margin"), cur)} sub={sum("equity") ? t("{p}% tổng vốn", { p: f1((sum("margin") / sum("equity")) * 100, 1) }) : undefined} />
        <Kpi label={t("Margin còn trống")} value={money(sum("free"), cur)} sub={t("cộng các tài khoản")} />
      </div>
      {live.length < rows.length && <Notice tone="warn" title={t("Một số tài khoản chưa có dữ liệu")}>{t("Tài khoản chưa nhận dữ liệu từ EA không được tính vào tổng.")}</Notice>}
      <div className="cols-2">
        <Panel title={t("Phân bổ vốn")} icon={PieIcon}><Allocation rows={rows} cur={cur} /></Panel>
        <Panel title={t("Đường tổng vốn")} icon={LineIcon} right={<Seg value={days} onChange={setDays} options={RANGES.map((d) => ({ value: d, label: rangeLabel(d) }))} label={t("Khoảng thời gian")} />}>
          {rows.length < 2 && total > 1 ? <div className="text-muted">{t("Nhóm chỉ có một tài khoản: xem đường vốn ở màn Tổng quan.")}</div> : <Combined ids={rows.map((x) => x.id)} days={days} cur={cur} />}
        </Panel>
      </div>
    </section>
  );
}

export default function Portfolio() {
  const a = useAuth();
  const snaps = useAccountSnaps();
  const now = useClock();
  const [days, setDays] = useState(30);
  const rows = useMemo(() => a.accounts.map((acc) => {
    const snap = (snaps.data || []).find((s) => s.account_id === acc.id) || null;
    const v = deriveView(snap);
    return { id: acc.id, acc, title: accountTitle(acc), snap, v, equity: v?.equity ?? null, cur: currencyOf(acc, snap) };
  }), [a.accounts, snaps.data]);
  const groups = useMemo(() => { const m = new Map(); for (const r of rows) { if (!m.has(r.cur)) m.set(r.cur, []); m.get(r.cur).push(r); } return [...m.entries()]; }, [rows]);
  const live = rows.filter((r) => r.v);
  const exposure = useMemo(() => {
    const m = new Map();
    for (const r of live) for (const p of r.v.positions) { const s = symbolLabel(p.symbol), sg = (String(p.side || "").toLowerCase() === "sell" || p.type === 1) ? -1 : 1; const e = m.get(s) || { symbol: s, net: 0, gross: 0, pl: 0 }; const lots = Number(p.volume ?? p.lots) || 0; e.net += sg * lots; e.gross += lots; e.pl += Number(p.profit) || 0; m.set(s, e); }
    return [...m.values()].sort((x, y) => y.gross - x.gross).slice(0, 10);
  }, [live]);
  const expBuild = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 64, right: 12, top: 8, bottom: 24 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 }, formatter: (p) => `${p[0].name}<br/>${t("Ròng:")} <b>${f1(p[0].value, 2)} lot</b>` },
    xAxis: { type: "value", axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } },
    yAxis: { type: "category", inverse: true, data: exposure.map((e) => e.symbol), axisLabel: { color: css("--fg"), fontSize: 11.5 }, axisLine: { lineStyle: { color: css("--line2") } } },
    series: [{ type: "bar", data: exposure.map((e) => ({ value: +e.net.toFixed(2), itemStyle: { color: e.net >= 0 ? css("--up") : css("--down") } })), barMaxWidth: 18 }],
  });

  if (a.accounts.length === 0) return <PageHead title={t("Danh mục")} sub={t("Chưa có tài khoản MT nào được gán.")} />;
  const multiCcy = groups.length > 1;
  return (
    <>
      <PageHead title={t("Danh mục nhiều tài khoản")} sub={multiCcy ? t("{n} tài khoản MT · chia theo {m} nhóm tiền tệ, không cộng gộp khác tiền tệ", { n: a.accounts.length, m: groups.length }) : t("{n} tài khoản MT · cùng một đồng tiền tài khoản", { n: a.accounts.length })} right={<ReadOnlyChip />} />
      <Async q={snaps} rows={5} isEmpty={() => false}>
        {() => (
          <>
            {multiCcy && <Notice tone="info" title={t("Tài khoản khác tiền tệ được tách riêng")}>{t("Số liệu của tài khoản USD, EUR... không được cộng với nhau vì khác đơn vị. Mỗi nhóm tiền tệ có tổng riêng bên dưới.")}</Notice>}
            {groups.map(([cur, g]) => <Group key={cur || "?"} cur={cur} rows={g} days={days} setDays={setDays} showTitle={multiCcy} total={rows.length} />)}
            <Panel title={t("Từng tài khoản")} icon={Wallet} pad={false}>
              <ul className="list-none m-0 p-0">
                {rows.map((r) => {
                  const e = connStatus({ ts: r.snap?.ts, nowMs: now }), mt = r.v ? marginTone(r.v.level) : null;
                  return (
                    <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3.5 py-3 border-b border-line last:border-0">
                      <div className="min-w-0 flex-1 basis-[11rem]"><div className="flex items-center gap-2"><span className={cn("live-dot", e.state === "on" ? "on" : e.state === "slow" ? "warn" : e.state === "off" ? "off" : "")} /><b className="num">{r.title}</b>{r.cur && <Chip>{r.cur}</Chip>}{r.id === a.active?.id && <Chip tone="accent">{t("đang xem")}</Chip>}</div>
                        <div className="text-[12px] text-muted">{r.acc.label || r.acc.server || "—"} · {e.label}{e.ageS != null ? ` (${ageText(e.ageS)})` : ""}</div></div>
                      {r.v ? (
                        <>
                          <div className="text-right"><div className="num font-semibold">{money(r.v.equity, r.cur)}</div><div className={cn("num text-[12.5px]", signCls(r.v.floating))}>{smoney(r.v.floating)}</div></div>
                          <div className="text-right w-[84px]"><div className={cn("num font-semibold", mt.tone === "down" ? "down" : mt.tone === "up" ? "up" : "")} style={mt.tone === "accent" ? { color: "var(--accent)" } : undefined}>{r.v.level == null ? "—" : `${f0(r.v.level)}%`}</div><div className="text-[11.5px] text-faint">margin</div></div>
                        </>
                      ) : <span className="text-muted text-[13px]">{t("chưa có dữ liệu")}</span>}
                      <button className="btn sm" onClick={() => { a.pick(r.id); location.hash = "#/hom-nay"; }} aria-label={t("Xem tài khoản {a}", { a: r.title })}>{t("Xem")} <ArrowRight size={14} aria-hidden="true" /></button>
                    </li>);
                })}
              </ul>
            </Panel>
            <Panel title={t("Tiếp xúc ròng theo mã (lot)")} icon={Layers}>{exposure.length ? <EChart build={expBuild} deps={[exposure]} height={Math.max(150, exposure.length * 26 + 30)} label={t("Vị thế ròng theo mã trên tất cả tài khoản")} /> : <div className="text-muted">{t("Không có vị thế mở.")}</div>}</Panel>
          </>
        )}
      </Async>
    </>
  );
}
