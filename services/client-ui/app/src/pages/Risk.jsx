import { AlertTriangle, BellPlus, BookOpenText, Gauge, Layers, MessageSquareText, ShieldAlert, TrendingDown, Zap } from "lucide-react";
import { Async, Chip, Kpi, Meter, Notice, PageHead, Panel, ReadOnlyChip, cn } from "../components/ui";
import { EChart, css } from "../components/charts";
import MarginGauge from "../components/gauge";
import { marginTone, useActiveAccount } from "../lib/account";
import { accountTitle } from "../lib/auth";
import { useRiskAccount } from "../lib/queries";
import { dateTime, f0, f1, money, pct, signCls, smoney, symbolLabel } from "../lib/format";
import { t, tr } from "../lib/i18n";

const statusMap = () => ({ ok: [t("Trong hạn mức"), "up", t("Các chỉ số rủi ro đang nằm trong ngưỡng đặt trước.")], warn: [t("Gần hạn mức"), "accent", t("Một số chỉ số đang gần ngưỡng, nên cân nhắc giảm khối lượng hoặc đặt SL.")], crit: [t("Vượt hạn mức"), "down", t("Có chỉ số đã vượt ngưỡng đặt trước. Cần xem xét giảm rủi ro.")], na: [t("Chưa đánh giá"), "", t("Chưa đủ dữ liệu để đánh giá.")] });
const barColor = (s) => (s === "crit" ? "var(--down)" : s === "warn" ? "var(--accent)" : "var(--up)");
const budgetStatus = (s) => ({ ok: t("Trong hạn mức"), warn: t("Gần hạn mức"), crit: t("Vượt hạn mức"), na: "—" }[s]);

function Underwater({ dd }) {
  if (!dd?.available || !dd.underwater || dd.underwater.length < 2) return <div className="text-muted">{t("Chưa đủ lịch sử vốn để vẽ đường sụt giảm.")}</div>;
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 44, right: 10, top: 10, bottom: 24 },
    tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
      formatter: (a) => `${dateTime(a[0].value[0])}<br/>${t("Sụt giảm")}: <b>${a[0].value[1].toFixed(2)}%</b>` },
    xAxis: { type: "time", axisLabel: { color: css("--muted"), fontSize: 11, hideOverlap: true }, axisLine: { lineStyle: { color: css("--line2") } }, splitLine: { show: false } },
    yAxis: { type: "value", max: 0, axisLabel: { color: css("--muted"), fontSize: 11, formatter: "{value}%" }, splitLine: { lineStyle: { color: css("--line") } } },
    series: [{ type: "line", data: dd.underwater.map((p) => [p.t * 1000, p.dd]), showSymbol: false, lineStyle: { width: 1.6, color: css("--down") }, areaStyle: { color: css("--down-bg") } }],
  });
  return <EChart build={build} deps={[dd]} height={170} label={t("Đường sụt giảm vốn so với đỉnh gần nhất")} />;
}


function Plain({ r }) {
  const m = r.margin, e = r.exposure || {}, v = r.var, dd = r.drawdown;
  const L = [];
  if (m && m.margin_level_pct != null) {
    L.push(<>{tr("Vốn của bạn đang gấp {x} số tiền broker giữ làm ký quỹ (mức margin {lvl}%).", { x: <b>{t("{n} lần", { n: f1(m.margin_level_pct / 100, 1) })}</b>, lvl: f0(m.margin_level_pct) })} {m.adverse_move_pct_gross != null && m.distance_to_stop_out != null ? tr("Nếu giá đi ngược khoảng {p} (cộng dồn các vị thế), tài khoản có thể chạm mức stop-out {so}% và bị đóng lệnh tự động, tương ứng mất khoảng {amt}.", { p: <b>{f1(m.adverse_move_pct_gross, 2)}%</b>, so: m.stop_out_pct, amt: <b className="down">{money(m.distance_to_stop_out)}</b> }) : null}</>);
  } else if (m) L.push(<>{t("Hiện không có vị thế nào dùng margin, nên chưa có nguy cơ bị đóng lệnh tự động.")}</>);
  if (e.leverage_gross != null) L.push(<>{tr("Đòn bẩy thực tế của bạn khoảng {x}: giá đi ngược 1% có thể làm vốn giảm khoảng {y}.", { x: <b>{f1(e.leverage_gross, 1)}x</b>, y: <b>{f1(e.leverage_gross, 1)}%</b> })}</>);
  if (v?.available) L.push(<>{tr("Trong một ngày bình thường, nhiều khả năng (95%) bạn không lỗ quá {amt}. Đây là ước tính từ lịch sử, ngày có tin lớn có thể tệ hơn.", { amt: <b className="down">{money(v.hist?.["95"]?.var)}</b> })}</>);
  const worst = (r.stress || []).filter((s) => s.pnl < 0).sort((a, b) => a.pnl - b.pnl)[0];
  if (worst) L.push(<>{tr("Kịch bản xấu nhất đã thử: {name} có thể làm bạn lỗ khoảng {amt} ({p}% vốn).", { name: <b>{worst.name}</b>, amt: <b className="down">{money(Math.abs(worst.pnl))}</b>, p: f1(Math.abs(worst.pnl_pct), 1) })}{worst.breach_stop_out ? ` ${t("Kịch bản này có thể chạm stop-out.")}` : ""}</>);
  if (dd?.available && dd.dd_from_peak_pct < -1) L.push(<>{tr("Vốn đang thấp hơn đỉnh gần nhất {p}.", { p: <b className="down">{f1(Math.abs(dd.dd_from_peak_pct), 1)}%</b> })}</>);
  if (!L.length) return null;
  return (
    <Panel title={t("Tóm tắt bằng lời")} icon={MessageSquareText} right={<a className="btn sm" href="#/canh-bao"><BellPlus size={15} aria-hidden="true" /> {t("Đặt cảnh báo margin")}</a>}>
      <div className="grid gap-4 md:grid-cols-[minmax(0,260px)_1fr] items-center">
        <div><MarginGauge level={m?.margin_level_pct ?? null} height={170} /></div>
        <ul className="m-0 pl-5 grid gap-2 text-[14px]">{L.map((x, i) => <li key={i}>{x}</li>)}</ul>
      </div>
    </Panel>
  );
}

function Glossary() {
  const items = [
    [t("Mức margin (margin level)"), t("Vốn (equity) chia cho margin đang bị giữ, tính theo %. Ví dụ 400% nghĩa là vốn gấp 4 lần margin. Khi mức này giảm xuống ngưỡng broker quy định (thường 20% đến 100%), broker có thể tự đóng lệnh (stop-out).")],
    [t("Margin trống (free margin)"), t("Phần vốn còn lại sau khi trừ margin đang giữ. Đây là 'đệm' để chịu lỗ và mở thêm lệnh.")],
    [t("Đòn bẩy hiệu dụng"), t("Tổng giá trị các vị thế chia cho vốn. 10x nghĩa là 1% giá đi ngược có thể làm vốn giảm khoảng 10%.")],
    [t("Sụt giảm (drawdown)"), t("Mức vốn đã giảm so với đỉnh gần nhất. Sụt giảm lớn cần lãi lớn hơn để gỡ lại.")],
    [t("VaR 95% / ES"), t("Ước tính từ dữ liệu quá khứ: trong một ngày bình thường, khả năng 95% bạn không lỗ quá mức VaR. ES là mức lỗ trung bình ở những ngày xấu nhất. Đây là ước tính, ngày bất thường có thể tệ hơn.")],
    [t("Stress test"), t("Giả định lại những biến động lớn trong lịch sử trên các vị thế hiện tại để xem bạn có thể lỗ bao nhiêu. Chưa tính trượt giá và giãn spread.")],
  ];
  return (
    <div className="grid gap-1">
      {items.map(([ttl, d]) => (
        <details key={ttl} className="rounded-lg border border-line bg-panel2 px-3">
          <summary className="min-h-[44px] flex items-center cursor-pointer font-semibold text-[13.5px]">{ttl}</summary>
          <p className="m-0 pb-3 text-[13px] text-muted">{d}</p>
        </details>
      ))}
    </div>
  );
}

function Body({ r }) {
  const m = r.margin, e = r.exposure || {}, dd = r.drawdown, v = r.var;
  const SM = statusMap();
  const st = SM[r.budget?.status] || SM.na;
  const mt = marginTone(m?.margin_level_pct ?? null);
  const ddOk = dd?.available;
  return (
    <>
      <Notice tone={st[1] === "down" ? "down" : st[1] === "accent" ? "warn" : st[1] === "up" ? "up" : "info"} icon={ShieldAlert} title={t("Tổng quan rủi ro: {s}", { s: st[0] })}>{st[2]}</Notice>
      <Plain r={r} />
      {r.warnings?.length > 0 && (
        <Notice tone="info" icon={AlertTriangle} title={t("Lưu ý về dữ liệu")}><ul className="m-0 pl-4">{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul></Notice>
      )}

      <Panel title={t("Margin: bạn còn cách ngưỡng bị đóng lệnh bao xa?")} icon={Gauge}>
        {m ? (
          <div className="grid gap-3">
            <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
              <div><div className="text-[12px] text-muted">{t("Mức margin")}</div><div className={cn("num text-[34px] leading-none", mt.tone === "down" ? "down" : mt.tone === "up" ? "up" : "")} style={mt.tone === "accent" ? { color: "var(--accent)" } : undefined}>{m.margin_level_pct == null ? "—" : `${f0(m.margin_level_pct)}%`}</div></div>
              <Chip tone={mt.tone}>{{ ok: t("An toàn"), warn: t("Thấp, cần chú ý"), margin_call: t("Dưới mức margin call"), stop_out: t("Chạm stop-out"), no_position: t("Không có vị thế") }[m.status] || mt.label}</Chip>
            </div>
            <Meter value={m.margin_level_pct == null ? 100 : Math.min(m.margin_level_pct, 500)} max={500} color={mt.color} label={t("Mức margin trên thang 0 đến 500 phần trăm")} />
            <div className="kpi-grid c3">
              <Kpi label={t("Margin trống")} value={money(m.free_margin)} sub={t("đang dùng {n}% vốn", { n: f1(m.margin_used_pct_equity, 0) })} />
              <Kpi label={t("Còn chịu được lỗ")} value={money(m.distance_to_stop_out)} sub={m.adverse_move_pct_gross != null ? t("≈ giá đi ngược {a}% (gộp) thì chạm stop-out {b}%", { a: f1(m.adverse_move_pct_gross, 2), b: m.stop_out_pct }) : t("tới ngưỡng stop-out")} />
              <Kpi label={t("Đòn bẩy hiệu dụng")} value={e.leverage_gross == null ? "—" : `${f1(e.leverage_gross, 2)}x`} sub={m.nominal_leverage ? t("danh nghĩa 1:{n}", { n: m.nominal_leverage }) : t("ròng {n}x", { n: f1(e.leverage_net, 2) })} />
            </div>
          </div>
        ) : <div className="text-muted">{t("Tài khoản chưa có dữ liệu margin.")}</div>}
      </Panel>

      <div className="kpi-grid c4">
        <Kpi label={t("Lãi/lỗ hôm nay")} value={ddOk ? pct(dd.day?.pnl_pct) : "—"} tone={ddOk ? signCls(dd.day?.pnl_pct) : ""} sub={ddOk ? t("tuần {n}", { n: pct(dd.week?.pnl_pct) }) : t("chưa đủ lịch sử")} />
        <Kpi label={t("Sụt giảm hiện tại")} value={ddOk ? pct(dd.dd_from_peak_pct) : "—"} tone={ddOk ? signCls(dd.dd_from_peak_pct) : ""} sub={ddOk ? t("tối đa {n}", { n: pct(dd.max_dd_pct) }) : ""} />
        <Kpi label={t("Vị thế mở")} value={e.positions ?? "—"} sub={e.mode ? (e.mode === "hedging" ? t("chế độ hedging") : e.mode === "netting" ? t("chế độ netting") : e.mode) : ""} />
        <Kpi label={t("Mức lỗ xấu 1 ngày (ES)")} value={v?.available ? `${f1(v.hist?.es?.es_pct, 2)}%` : "—"} sub={v?.available ? money(v.hist?.es?.es) : t("chưa đủ dữ liệu")} />
      </div>

      {r.budget?.items?.length > 0 && (
        <Panel title={t("Ngân sách rủi ro (hạn mức đặt trước)")} icon={ShieldAlert}>
          <div className="grid gap-3.5 md:grid-cols-2">
            {r.budget.items.map((i) => {
              const used = i.used_pct == null ? 0 : Math.min(i.used_pct, 100);
              return (
                <div key={i.key} className="min-w-0">
                  <div className="flex justify-between gap-2 text-[13px]"><span className="text-muted">{i.label}</span><span className="num shrink-0">{i.value == null ? "—" : f1(i.value, 2)}{i.unit} / {i.direction === "min" ? "≥ " : ""}{i.limit}{i.unit}</span></div>
                  <div className="mt-1.5"><Meter value={used} color={barColor(i.status)} label={i.label} /></div>
                  <div className="mt-1 text-[12px] text-faint">{budgetStatus(i.status)} · {t("đã dùng {n} hạn mức", { n: i.used_pct == null ? "—" : `${i.used_pct.toFixed(0)}%` })}</div>
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      <div className="cols-2">
        <Panel title={t("Sụt giảm so với đỉnh")} icon={TrendingDown}><Underwater dd={dd} /></Panel>
        <Panel title={t("Mức lỗ có thể gặp trong 1 ngày")} icon={Layers}>
          {!v?.available ? <div className="text-muted">{v?.reason || t("Chưa đủ dữ liệu để ước tính.")}</div> : (
            <div className="grid gap-3">
              <p className="m-0 text-[13.5px]">{tr("Trong một ngày bình thường, {a} bạn không lỗ quá {b} ({p}% vốn). Ở những ngày xấu nhất, mức lỗ trung bình có thể khoảng {c} ({q}%).", { a: <b>{t("95% khả năng")}</b>, b: <b className="down num">{money(v.hist?.["95"]?.var)}</b>, p: f1(v.hist?.["95"]?.var_pct, 2), c: <b className="down num">{money(v.hist?.es?.es)}</b>, q: f1(v.hist?.es?.es_pct, 2) })}</p>
              <p className="m-0 text-[12.5px] text-faint">{t("Ước tính từ {d} ngày lịch sử áp lên vị thế hiện tại, phủ {p}% giá trị. Biến động bất thường (gap, tin lớn) có thể vượt mức này.", { d: v.days, p: f0(v.coverage_pct) })}</p>
            </div>
          )}
        </Panel>
      </div>

      <Panel title={t("Mức độ tập trung (exposure)")} icon={Layers}>
        {!e.positions ? <div className="text-muted">{t("Không có vị thế mở.")}</div> : (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="m-0 mb-1.5 text-[13px] text-muted font-semibold">{t("Theo tiền tệ (ròng)")}</h3>
              {(e.by_currency || []).length ? <ul className="list-none m-0 p-0 grid gap-1">{e.by_currency.map((c) => (
                <li key={c.ccy} className="flex justify-between gap-2 text-[13.5px] border-b border-line pb-1"><b>{c.ccy}</b><span className={cn("num", signCls(c.net_value))}>{smoney(c.net_value)} <span className="text-faint">· {c.pct_equity == null ? "—" : t("{n}% vốn", { n: f0(c.pct_equity) })}</span></span></li>))}</ul> : <div className="text-muted text-[13px]">{t("Không có exposure ngoại tệ/kim loại.")}</div>}
            </div>
            <div>
              <h3 className="m-0 mb-1.5 text-[13px] text-muted font-semibold">{t("Theo mã")}</h3>
              <ul className="list-none m-0 p-0 grid gap-1">{(e.by_symbol || []).slice(0, 8).map((s) => (
                <li key={s.symbol} className="flex justify-between gap-2 text-[13.5px] border-b border-line pb-1"><b>{symbolLabel(s.symbol)}</b><span className="num text-muted">{t("mua")} {f1(s.long_lots, 2)} · {t("bán")} {f1(s.short_lots, 2)} · <span className={signCls(s.net_value)}>{smoney(s.net_value)}</span></span></li>))}</ul>
            </div>
          </div>
        )}
      </Panel>

      <Panel title={t("Nếu thị trường biến động mạnh (stress test)")} icon={Zap}>
        {!r.stress?.length ? <div className="text-muted">{t("Không có vị thế để mô phỏng.")}</div> : (
          <ul className="list-none m-0 p-0 grid gap-2.5">
            {r.stress.map((s) => (
              <li key={s.id} className="grid gap-1">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5"><b className="text-[13.5px]">{s.name}</b>
                  {s.breach_stop_out ? <Chip tone="down">{t("chạm stop-out")}</Chip> : s.breach_zero ? <Chip tone="down">{t("vốn về 0")}</Chip> : null}
                  <span className={cn("num ml-auto text-[14px]", signCls(s.pnl))}>{smoney(s.pnl)} <span className="text-faint text-[12.5px]">({pct(s.pnl_pct)})</span></span></div>
                <Meter value={Math.min(100, Math.abs(s.pnl_pct ?? 0))} color={(s.pnl ?? 0) < 0 ? "var(--down)" : "var(--up)"} label={t("Mức ảnh hưởng của kịch bản {name}", { name: s.name })} />
                {s.window && <div className="text-[12px] text-faint">{s.window}</div>}
              </li>
            ))}
          </ul>
        )}
        <p className="m-0 mt-3 text-[12px] text-faint">{t("Dựng lại biến động giá lịch sử trên vị thế hiện tại. Chưa tính trượt giá, gap, giãn spread: thực tế có thể xấu hơn.")}</p>
      </Panel>

      <Panel title={t("Các chỉ số này nghĩa là gì?")} icon={BookOpenText}><Glossary /></Panel>
      <p className="m-0 text-[12px] text-faint">{r.disclaimer || t("Số liệu ước tính, chỉ để tham khảo, không phải khuyến nghị đầu tư.")} {t("Cập nhật {d}.", { d: dateTime(r.generated_at) })}</p>
    </>
  );
}

export default function Risk() {
  const { acc } = useActiveAccount();
  const q = useRiskAccount(acc?.id);
  return (
    <>
      <PageHead title={t("Rủi ro tài khoản")} sub={acc ? `${accountTitle(acc)} · ${t("giải thích bằng ngôn ngữ dễ hiểu, số liệu ước tính")}` : t("Chưa có tài khoản")} right={<ReadOnlyChip />} />
      {acc && q.isError && q.error?.status === 404 && <Notice tone="info" title={t("Chưa có dữ liệu rủi ro")}>{t("Hệ thống cần ít nhất một lần nhận dữ liệu từ EA của tài khoản này để tính rủi ro. Kiểm tra EA đã gắn trên biểu đồ (xem hướng dẫn ở mục Hồ sơ).")}</Notice>}
      {acc && !(q.isError && q.error?.status === 404) && <Async q={q} rows={8} empty={t("Chưa có dữ liệu rủi ro.")} hint={t("Hệ thống cần ít nhất một lần nhận dữ liệu từ EA để tính rủi ro.")}>{(r) => <Body r={r} />}</Async>}
    </>
  );
}
