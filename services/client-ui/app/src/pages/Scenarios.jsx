// Trang "Kịch bản" (Scenarios): tín hiệu mẫu hình Sell KB-1..KB-4 dùng CHUNG (không dữ liệu tài khoản), kết quả PAPER.
// Gateway đã lọc cho client: chỉ armed/triggered, không lý do huỷ, không tham số. Chỉ thông tin, hệ thống không đặt lệnh.
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, BookOpen, CircleCheck, CircleDashed, Clock, History, ImageOff, Images, ListChecks, ScanSearch, ShieldCheck, TrendingDown, X, ZoomIn } from "lucide-react";
import { Async, Chip, Kpi, Meter, Notice, PageHead, Panel, Seg, cn } from "../components/ui";
import { EChart, css } from "../components/charts";
import ScCandles from "../components/sccandles";
import { clean, date, dateTime, f1, price, rel, signCls, symbolLabel } from "../lib/format";
import { go } from "../lib/router";
import { t } from "../lib/i18n";
import { imgUrl, itemsOf, setupOf, PAT_MOCK, TF_SEC, usePatBars, usePatExamples, usePatLive, usePatSetup, usePatSpec, usePatStats, usePatTrades } from "../lib/patterns";
import "./scenarios.css";

const PATTERN_IDS = ["KB-1", "KB-2", "KB-3", "KB-4"];
const TFS = ["M15", "H1", "H4"];
const KB_SHORT = () => ({
  "KB-1": t("Hồi vượt đỉnh, 2 đỉnh giảm dần, nhấn chìm"),
  "KB-2": t("Hồi ~50%, nêm thu hẹp, nhấn chìm phá cạnh dưới"),
  "KB-3": t("Đi ngang, vai-đầu-vai, nến nén ở đường cổ"),
  "KB-4": t("Phá hộp, đi ngang mới 3 đỉnh giảm dần, nến nén"),
});
const KB_DESC = () => ({
  "KB-1": t("Sau một sóng giảm mạnh, giá hồi nhẹ, giảm tiếp một đoạn tương đương rồi hồi vượt đỉnh cũ một chút. Giá đi ngang tạo hai đỉnh thấp dần; tín hiệu khi một nến giảm thân dài nhấn chìm xuất hiện ở đỉnh thứ hai."),
  "KB-2": t("Sau một sóng giảm mạnh, giá hồi khoảng một nửa rồi tích luỹ thành hình nêm/tam giác thu hẹp (đỉnh thấp dần, đáy cao dần). Tín hiệu khi nến giảm thân dài nhấn chìm và đóng cửa dưới cạnh dưới của nêm."),
  "KB-3": t("Sau một sóng giảm mạnh, giá đi ngang biên độ đều và hình thành vai-đầu-vai. Khi giá quay về sát đường cổ và xuất hiện cụm 3 nến thân nhỏ nén lại, hệ thống ghi nhận tín hiệu."),
  "KB-4": t("Giá đi ngang trong một hộp rồi một nến thân rất dài phá xuống, tiếp theo là chuỗi nến đỏ. Giá đi ngang ở vùng mới với 3 đỉnh thấp dần; tín hiệu khi cụm nến thân nhỏ nén lại dưới đỉnh thứ ba."),
});
const STATE = () => ({ triggered: [t("Đã kích hoạt"), "down"], armed: [t("Sẵn sàng"), "info"] });
const LEG = () => ({ open: [t("Đang mở"), "info"], tp: [t("Chốt lời"), "up"], sl: [t("Cắt lỗ"), "down"], timeout: [t("Hết hạn"), ""] });
const EX_KIND = () => ({ golden: t("Mẫu chuẩn"), live: t("Đã kích hoạt"), replay: t("Chạy lại lịch sử") });
const fR = (v, dp = 2) => (v == null || !Number.isFinite(+v) ? "—" : `${v > 0 ? "+" : ""}${f1(+v, dp)}R`);
const pctv = (v) => (v == null ? "—" : `${f1(v * 100, 1)}%`);
const px = (sym, v) => price(symbolLabel(sym), v == null ? null : +v);
const setupHref = (s) => `/kich-ban?setup=${encodeURIComponent(s.setup_id)}&symbol=${encodeURIComponent(s.symbol || "")}&tf=${encodeURIComponent(s.tf || "")}`;

function StateChip({ s }) {
  const [l, tone] = STATE()[s] || [s || "—", ""];
  return <Chip tone={tone}>{l}</Chip>;
}

/** Ảnh có trạng thái lỗi; bấm để phóng to. */
function Img({ src, alt, onZoom, className, eager }) {
  const url = imgUrl(src);
  const [bad, setBad] = useState(false);
  if (!url || bad) return <div className={cn("sc-noimg", className)}><ImageOff size={20} aria-hidden="true" /><span>{t("Chưa có ảnh")}</span></div>;
  const img = <img src={url} alt={alt} loading={eager ? "eager" : "lazy"} decoding="async" onError={() => setBad(true)} />;
  if (!onZoom) return <div className={cn("sc-img", className)}>{img}</div>;
  return (
    <button type="button" className={cn("sc-img zoomable", className)} onClick={(e) => { e.preventDefault(); e.stopPropagation(); onZoom({ url, alt }); }} aria-label={t("Phóng to ảnh: {a}", { a: alt })}>
      {img}<span className="sc-zoomhint" aria-hidden="true"><ZoomIn size={14} /></span>
    </button>
  );
}

function Lightbox({ z, onClose }) {
  useEffect(() => {
    const on = (e) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", on);
    document.body.style.overflow = "hidden";
    return () => { removeEventListener("keydown", on); document.body.style.overflow = ""; };
  }, [onClose]);
  return (
    <div className="sc-zoom" role="dialog" aria-modal="true" aria-label={z.alt} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <button className="ibtn sc-zoom-x" onClick={onClose} aria-label={t("Đóng")} autoFocus><X size={20} aria-hidden="true" /></button>
      <img src={z.url} alt={z.alt} />
    </div>
  );
}

function Levels({ s, compact }) {
  const L = s.levels || {};
  const rows = [[t("Entry"), L.entry, "acc"], ["SL", L.sl, "down"], ["TP1", L.tp_1r, "up"], ["TP2", L.tp_2r, "up"], ["TP3", L.tp_3r, "up"]];
  return (
    <dl className={cn("sc-levels", compact && "compact")}>
      {rows.map(([k, v, tone]) => <div key={k}><dt>{k}</dt><dd className={cn("num", tone)}>{px(s.symbol, v)}</dd></div>)}
    </dl>
  );
}

function SetupCard({ s }) {
  const title = `${symbolLabel(s.symbol)} · ${s.tf} · ${s.pattern}`;
  return (
    <li>
      <a className="sc-card" href={`#${setupHref(s)}`} aria-label={t("{x}: xem chi tiết kịch bản", { x: title })}>
        <Img src={s.image} alt={title} className="sc-thumb" />
        <div className="sc-cbody">
          <div className="sc-ctop">
            <StateChip s={s.state} />
            <b className="text-[15px]">{symbolLabel(s.symbol)}</b>
            <span className="text-[12px] text-faint">{s.tf}</span>
            <Chip>{s.pattern}</Chip>
            <span className="sc-score num ml-auto" title={t("Điểm 0–100 chỉ để xếp hạng, không phải xác suất thắng")}>{s.score != null ? Math.round(s.score) : "—"}</span>
          </div>
          <div className="text-[12.5px] text-muted sc-clamp">{KB_SHORT()[s.pattern] || clean(s.name)}</div>
          <Levels s={s} compact />
          <div className="flex items-center gap-1.5 text-[12px] text-faint"><Clock size={12} aria-hidden="true" />{dateTime(s.last_ts || s.bar_ts)} · {rel(s.last_ts || s.bar_ts)}</div>
        </div>
      </a>
    </li>
  );
}

function Filters({ items, f, setF }) {
  const syms = useMemo(() => [...new Set(items.map((x) => x.symbol).filter(Boolean))].sort(), [items]);
  return (
    <div className="sc-filters">
      <select className="field" aria-label={t("Lọc theo mã")} value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })}>
        <option value="">{t("Tất cả mã")}</option>
        {syms.map((x) => <option key={x} value={x}>{symbolLabel(x)}</option>)}
      </select>
      <select className="field" aria-label={t("Lọc theo kịch bản")} value={f.pattern} onChange={(e) => setF({ ...f, pattern: e.target.value })}>
        <option value="">{t("Tất cả kịch bản")}</option>
        {PATTERN_IDS.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      <Seg value={f.tf} onChange={(v) => setF({ ...f, tf: v })} options={[{ value: "", label: t("Mọi khung") }, ...TFS]} label={t("Khung thời gian")} />
    </div>
  );
}
const applyF = (items, f) => items.filter((s) => (!f.symbol || s.symbol === f.symbol) && (!f.tf || s.tf === f.tf) && (!f.pattern || s.pattern === f.pattern));
const notReady = () => t("Tính năng đang được triển khai; dữ liệu sẽ hiện khi dịch vụ quét kịch bản hoạt động.");

function LiveTab() {
  const q = usePatLive({ view: "active", limit: 200 });
  const [f, setF] = useState({ symbol: "", tf: "", pattern: "" });
  const all = itemsOf(q.data);
  const items = applyF(all, f).sort((a, b) => (a.state === b.state ? Date.parse(b.last_ts || 0) - Date.parse(a.last_ts || 0) : a.state === "triggered" ? -1 : 1));
  const nTrig = all.filter((x) => x.state === "triggered").length;
  return (
    <>
      <Filters items={all} f={f} setF={setF} />
      <Panel title={t("Tín hiệu hiện tại")} icon={ScanSearch} right={q.data ? <span className="text-[12px] text-muted">{t("{a} đã kích hoạt · {b} sẵn sàng", { a: nTrig, b: all.length - nTrig })}</span> : null}>
        <Async q={{ ...q, data: q.data ? items : q.data }} rows={5} empty={all.length ? t("Không có tín hiệu khớp bộ lọc.") : t("Hiện chưa có kịch bản nào đang sẵn sàng hoặc vừa kích hoạt.")}
          hint={all.length ? t("Thử bỏ bớt bộ lọc.") : t("Hệ thống chỉ quét trên nến đã đóng; tín hiệu sẽ hiện ở đây khi có.")}>
          {() => <ul className="sc-grid">{items.map((s) => <SetupCard key={s.setup_id} s={s} />)}</ul>}
        </Async>
        {q.isError && <p className="m-0 mt-2 text-[12.5px] text-faint">{notReady()}</p>}
      </Panel>
    </>
  );
}

function Detail({ query, onZoom }) {
  const q = usePatSetup({ setup_id: query.setup, symbol: query.symbol, tf: query.tf });
  const so = setupOf(q.data);
  const s = so?.s;
  const back = () => (history.length > 1 ? history.back() : go("/kich-ban"));
  return (
    <>
      <div className="flex items-center gap-2 flex-wrap">
        <button type="button" className="btn ghost" onClick={back}><ArrowLeft size={16} aria-hidden="true" /> {t("Quay lại")}</button>
        <h1 className="m-0 text-[19px] font-bold min-w-0">{s ? `${symbolLabel(s.symbol)} · ${s.tf} · ${s.pattern}` : t("Chi tiết kịch bản")}</h1>
        {s && <StateChip s={s.state} />}
      </div>
      <Async q={q} rows={8} isEmpty={(d) => !setupOf(d)}>
        {() => <DetailBody s={s} rawMarks={so.marks} win={so.win} onZoom={onZoom} />}
      </Async>
    </>
  );
}

function DetailBody({ s, rawMarks, win, onZoom }) {
  const step = TF_SEC[s.tf] || 3600;
  const hasBars = Array.isArray(s.bars) && s.bars.length > 1;
  const bwin = useMemo(() => (win?.from || win?.to ? { from: win.from, to: win.to }
    : { to: new Date(Date.parse(s.last_ts || s.bar_ts || Date.now()) + step * 40 * 1000).toISOString().slice(0, 19) + "Z" }), [win, s.last_ts, s.bar_ts, step]);
  const bq = usePatBars(s.symbol, s.tf, bwin, !hasBars);
  const bars = hasBars ? s.bars : itemsOf(bq.data);
  const marks = useMemo(() => (Array.isArray(rawMarks) && rawMarks.length ? rawMarks.map((m) => ({ t: m.t ?? m.ts, p: m.p, kind: m.kind, label: clean(String(m.label || "")), tone: m.kind === "trigger" ? "down" : m.tone }))
    : (s.events || []).map((e) => ({ t: e.bar_ts || e.ts, label: STATE()[e.state]?.[0] || e.state, tone: e.state === "triggered" ? "down" : "info" }))), [s, rawMarks]);
  const levels = s.levels;
  const events = [...(s.events || [])].sort((a, b) => Date.parse(a.ts || a.bar_ts) - Date.parse(b.ts || b.bar_ts));
  const steps = s.steps || [];
  const title = `${symbolLabel(s.symbol)} · ${s.tf} · ${s.pattern}`;
  return (
    <div className="sc-detail">
      <div className="grid gap-3 min-w-0">
        <Panel title={t("Ảnh kịch bản")} icon={Images}>
          <Img src={s.image} alt={title} onZoom={onZoom} className="sc-big" eager />
          <p className="m-0 mt-2 text-[12.5px] text-muted">{KB_SHORT()[s.pattern] || clean(s.name)}</p>
        </Panel>
        {(hasBars || bq.isSuccess) && bars.length > 1 && (
          <Panel title={t("Biểu đồ nến")} icon={TrendingDown}>
            <ScCandles bars={bars} symbol={s.symbol} levels={levels} marks={marks} />
          </Panel>
        )}
      </div>
      <div className="grid gap-3 content-start min-w-0">
        <Panel title={t("Mức giá gợi ý")} right={<span className="text-[12px] text-muted">{t("Điểm")} <b className="num">{s.score != null ? Math.round(s.score) : "—"}</b>/100</span>}>
          <Meter value={s.score || 0} label={t("Điểm kịch bản")} color="var(--accent)" />
          <div className="mt-2.5"><Levels s={s} /></div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12.5px] text-muted num">
            {levels?.r != null && <span>R = {px(s.symbol, levels.r)}</span>}
            {levels?.atr != null && <span>ATR = {px(s.symbol, levels.atr)}</span>}
          </div>
          <p className="m-0 mt-2 text-[12px] text-faint">{t("Entry là giá đóng của nến kích hoạt; SL đặt trên đỉnh cấu trúc; TP theo bội số R (1R/2R/3R). Điểm chỉ để xếp hạng, không phải xác suất thắng.")}</p>
        </Panel>
        <Panel title={t("Các bước của kịch bản")} icon={ListChecks}>
          {steps.length ? (
            <ol className="sc-steps">
              {steps.map((x) => (
                <li key={x.id} className={x.ok ? "ok" : ""}>
                  {x.ok ? <CircleCheck size={17} aria-hidden="true" /> : <CircleDashed size={17} aria-hidden="true" />}
                  <span><span className="sr-only">{x.ok ? t("Đã thoả:") : t("Chưa thoả:")} </span>{t(String(x.label || ""))}{x.detail ? <small data-server-text=""> · {clean(String(x.detail))}</small> : null}</span>
                </li>
              ))}
            </ol>
          ) : <p className="m-0 text-muted text-[13px]">{t("Chưa có dữ liệu.")}</p>}
        </Panel>
        <Panel title={t("Dòng thời gian")} icon={Clock}>
          {events.length ? (
            <ol className="sc-tl">
              {events.map((e) => (
                <li key={e.id ?? `${e.state}${e.ts}`} className={e.state}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap"><StateChip s={e.state} /><span className="num text-[12.5px]">{dateTime(e.bar_ts || e.ts)}</span>{e.score != null && <span className="text-[12px] text-faint num">{t("Điểm")} {Math.round(e.score)}</span>}</div>
                  </div>
                  {e.image && <Img src={e.image} alt={t("{x} lúc {t}", { x: STATE()[e.state]?.[0] || e.state, t: dateTime(e.bar_ts || e.ts) })} onZoom={onZoom} className="sc-tlimg" />}
                </li>
              ))}
            </ol>
          ) : <p className="m-0 text-muted text-[13px]">{t("Chưa có sự kiện.")}</p>}
        </Panel>
        {s.trade && <TradePanel tr={s.trade} />}
      </div>
    </div>
  );
}

function TradePanel({ tr }) {
  const st = tr.status === "open" ? [t("Đang mở"), "info"] : [t("Đã đóng"), ""];
  return (
    <Panel title={t("Kết quả mô phỏng (paper)")} right={<Chip tone={st[1]}>{st[0]}</Chip>}>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] num">
        <span>{t("Mở lúc")} {dateTime(tr.opened_at)}</span>
        {tr.closed_at && <span>{t("Đóng lúc")} {dateTime(tr.closed_at)}</span>}
        {tr.result_r != null && <b className={signCls(tr.result_r)}>{fR(tr.result_r)}</b>}
      </div>
      <ul className="sc-legs">
        {(tr.legs || []).map((l, i) => { const [lb, tone] = LEG()[l.status] || [l.status, ""]; return (
          <li key={i}><span className="text-muted">TP{i + 1} <span className="num">{px(tr.symbol, l.tp)}</span></span><Chip tone={tone}>{lb}</Chip><span className={cn("num ml-auto", signCls(l.r))}>{l.r != null ? fR(l.r, 1) : "—"}</span></li>
        ); })}
      </ul>
      <p className="m-0 mt-1 text-[12px] text-faint">{t("Mô phỏng chia 3 phần bằng nhau tại TP1/TP2/TP3, theo dõi trên nến đã đóng. Không có lệnh thật nào được đặt.")}</p>
    </Panel>
  );
}

function EquityR({ pts }) {
  const build = () => {
    const axis = { axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } };
    return {
      animation: false, backgroundColor: "transparent", grid: { left: 44, right: 10, top: 12, bottom: 24 },
      tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
        formatter: (a) => `${dateTime(a[0].value[0])}<br/>${t("R luỹ kế")}: <b>${fR(a[0].value[1])}</b>` },
      xAxis: { type: "time", ...axis, axisLabel: { ...axis.axisLabel, hideOverlap: true, formatter: (v) => date(v) }, splitLine: { show: false } },
      yAxis: { type: "value", ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => `${v}R` } },
      series: [{ type: "line", step: "end", data: pts.map((p) => [Date.parse(p.t), p.cum_r]), showSymbol: false, lineStyle: { width: 2, color: css("--accent") }, itemStyle: { color: css("--accent") }, areaStyle: { color: css("--accent-bg") },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: css("--line2"), type: "dashed" }, label: { show: false } } }],
    };
  };
  return <EChart build={build} deps={[pts]} height={220} label={t("Đường R luỹ kế của các lệnh mô phỏng đã đóng")} />;
}

function StatsBlock() {
  const q = usePatStats();
  return (
    <Panel title={t("Kết quả mô phỏng (paper)")} icon={History} right={q.data?.as_of ? <span className="text-[12px] text-faint">{t("Cập nhật {t}", { t: rel(q.data.as_of) })}</span> : null}>
      <Async q={q} rows={5} isEmpty={(d) => !d?.overall || !((d.overall.n_closed || 0) + (d.overall.n_open || 0))} empty={t("Chưa có kết quả mô phỏng.")}
        hint={q.isError ? notReady() : t("Kết quả sẽ xuất hiện sau khi có kịch bản được kích hoạt và theo dõi trên các nến tiếp theo.")}>
        {(d) => {
          const o = d.overall || {}, n = o.n_closed || 0;
          return (
            <div className="grid gap-3">
              {n < 30 && <Notice tone="warn">{t("Mẫu nhỏ ({n} lệnh đã đóng, dưới 30): số liệu chưa có ý nghĩa thống kê, chỉ để theo dõi.", { n })}</Notice>}
              <div className="kpi-grid c3">
                <Kpi label={t("Lệnh đã đóng")} value={n} sub={t("{n} đang mở", { n: o.n_open ?? 0 })} />
                <Kpi label={t("Tỷ lệ thắng")} value={pctv(o.winrate)} sub={t("{w} thắng · {l} thua", { w: o.wins ?? 0, l: o.losses ?? 0 })} />
                <Kpi label={t("R trung bình")} value={fR(o.avg_r)} tone={signCls(o.avg_r)} />
                <Kpi label={t("Tổng R")} value={fR(o.sum_r, 1)} tone={signCls(o.sum_r)} />
                <Kpi label={t("Profit factor")} value={o.pf != null ? f1(o.pf, 2) : "—"} />
                <Kpi label={t("Sụt giảm tối đa")} value={o.max_dd_r != null ? `${f1(o.max_dd_r, 1)}R` : "—"} tone={o.max_dd_r ? "down" : ""} />
              </div>
              {d.ledger && (
                <div className="flex items-center gap-1.5 text-[12.5px] text-muted">
                  <ShieldCheck size={14} className={d.ledger.ok ? "text-up" : "text-down"} aria-hidden="true" />
                  {d.ledger.ok ? t("Sổ ghi kết quả toàn vẹn ({n} bản ghi, không thể sửa)", { n: d.ledger.n ?? 0 }) : t("Sổ ghi kết quả đang được kiểm tra lại")}
                </div>
              )}
              {(d.equity || []).length > 1 ? <div><div className="text-[12.5px] text-muted mb-1">{t("R luỹ kế")}</div><EquityR pts={d.equity} /></div> : null}
              {(d.by_pattern || []).length > 0 && (
                <div className="overflow-x-auto">
                  <table className="tbl">
                    <thead><tr><th>{t("Kịch bản")}</th><th className="r">{t("Số lệnh")}</th><th className="r">{t("Tỷ lệ thắng")}</th><th className="r">{t("R trung bình")}</th><th className="r">{t("Tổng R")}</th></tr></thead>
                    <tbody>{d.by_pattern.map((r) => (
                      <tr key={r.key ?? r.pattern}><td>{r.key ?? r.pattern}</td><td className="r num">{r.n_closed ?? r.n ?? "—"}</td><td className="r num">{pctv(r.winrate)}</td><td className={cn("r num", signCls(r.avg_r))}>{fR(r.avg_r)}</td><td className={cn("r num", signCls(r.sum_r))}>{fR(r.sum_r, 1)}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </div>
          );
        }}
      </Async>
    </Panel>
  );
}

function TradeStatus({ tr }) {
  if (tr.status === "open") return <Chip tone="info">{t("Đang mở")}</Chip>;
  return <Chip tone={tr.result_r > 0 ? "up" : tr.result_r < 0 ? "down" : ""}>{t("Đã đóng")}</Chip>;
}

function TradesBlock() {
  const [st, setSt] = useState("all");
  const [n, setN] = useState(20);
  const q = usePatTrades({ status: "all", limit: 300 });
  const all = itemsOf(q.data);
  const items = all.filter((x) => st === "all" || x.status === st);
  const shown = items.slice(0, n);
  const link = (tr) => `#${setupHref(tr)}`;
  return (
    <Panel title={t("Lệnh mô phỏng")} right={<Seg value={st} onChange={(v) => { setSt(v); setN(20); }} options={[{ value: "all", label: t("Tất cả") }, { value: "open", label: t("Đang mở") }, { value: "closed", label: t("Đã đóng") }]} label={t("Lọc trạng thái lệnh")} />}>
      <Async q={{ ...q, data: q.data ? items : q.data }} rows={5} empty={t("Chưa có lệnh mô phỏng.")} hint={q.isError ? notReady() : undefined}>
        {() => (
          <>
            <div className="hide-mobile overflow-x-auto">
              <table className="tbl">
                <thead><tr><th>{t("Mở lúc")}</th><th>{t("Mã")}</th><th>{t("Khung")}</th><th>{t("Kịch bản")}</th><th className="r">{t("Entry")}</th><th className="r">SL</th><th>{t("Trạng thái")}</th><th className="r">{t("Kết quả")}</th></tr></thead>
                <tbody>{shown.map((tr) => (
                  <tr key={tr.id}>
                    <td className="num"><a className="underline-offset-2 hover:underline" href={link(tr)}>{dateTime(tr.opened_at)}</a></td>
                    <td><b>{symbolLabel(tr.symbol)}</b></td><td>{tr.tf}</td><td>{tr.pattern}</td>
                    <td className="r num">{px(tr.symbol, tr.entry)}</td><td className="r num">{px(tr.symbol, tr.sl)}</td>
                    <td><TradeStatus tr={tr} /></td>
                    <td className={cn("r num", signCls(tr.result_r))}>{fR(tr.result_r)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <ul className="only-mobile list-none m-0 p-0 grid gap-2">
              {shown.map((tr) => (
                <li key={tr.id}>
                  <a className="pos-card sc-tcard" href={link(tr)}>
                    <div className="flex items-center gap-2"><b className="text-[15px]">{symbolLabel(tr.symbol)}</b><span className="text-[12px] text-faint">{tr.tf} · {tr.pattern}</span><span className="ml-auto"><TradeStatus tr={tr} /></span></div>
                    <div className="row"><span>{t("Mở lúc")}</span><span className="num">{dateTime(tr.opened_at)}</span></div>
                    <div className="row"><span>{t("Entry")} / SL</span><span className="num">{px(tr.symbol, tr.entry)} / {px(tr.symbol, tr.sl)}</span></div>
                    <div className="row"><span>{t("Kết quả")}</span><b className={cn("num", signCls(tr.result_r))}>{fR(tr.result_r)}</b></div>
                  </a>
                </li>
              ))}
            </ul>
            {items.length > n && <button type="button" className="btn mt-3" onClick={() => setN(n + 20)}>{t("Xem thêm ({n})", { n: items.length - n })}</button>}
          </>
        )}
      </Async>
    </Panel>
  );
}

function PastSetups() {
  const q = usePatLive({ view: "history", limit: 100 });
  const [f, setF] = useState({ symbol: "", tf: "", pattern: "" });
  const [n, setN] = useState(8);
  const all = itemsOf(q.data);
  const items = applyF(all, f).sort((a, b) => Date.parse(b.last_ts || 0) - Date.parse(a.last_ts || 0));
  return (
    <Panel title={t("Kịch bản đã qua")} icon={History}>
      {all.length > 0 && <div className="mb-3"><Filters items={all} f={f} setF={setF} /></div>}
      <Async q={{ ...q, data: q.data ? items : q.data }} rows={4} empty={t("Chưa có lịch sử kịch bản.")} hint={q.isError ? notReady() : undefined}>
        {() => (
          <>
            <ul className="sc-grid">{items.slice(0, n).map((s) => <SetupCard key={s.setup_id} s={s} />)}</ul>
            {items.length > n && <button type="button" className="btn mt-3" onClick={() => setN(n + 8)}>{t("Xem thêm ({n})", { n: items.length - n })}</button>}
          </>
        )}
      </Async>
    </Panel>
  );
}

function LibraryTab({ onZoom }) {
  const q = usePatExamples();
  const [kb, setKb] = useState("");
  const all = itemsOf(q.data);
  const items = all.filter((x) => !kb || x.pattern === kb);
  return (
    <Panel title={t("Thư viện ví dụ")} icon={Images}>
      <Seg value={kb} onChange={setKb} options={[{ value: "", label: t("Tất cả") }, ...PATTERN_IDS]} label={t("Lọc theo kịch bản")} scroll className="mb-2 max-w-full" />
      <p className="m-0 mb-3 text-[12.5px] text-muted">{t("Ví dụ minh hoạ mẫu hình (ảnh mẫu và các lần kích hoạt trước đây). Bấm ảnh để phóng to.")}</p>
      <Async q={{ ...q, data: q.data ? items : q.data }} rows={4} empty={t("Chưa có ví dụ.")} hint={q.isError ? notReady() : undefined}>
        {() => (
          <ul className="sc-gallery">
            {items.map((x) => {
              const cap = `${x.pattern || ""}${x.symbol ? ` · ${symbolLabel(x.symbol)}` : ""}${x.tf ? ` · ${x.tf}` : ""}`;
              return (
                <li key={x.id}>
                  <figure>
                    <Img src={x.image || (x.id ? `/v1/patterns/examples/${encodeURIComponent(x.id)}.png` : null)} alt={cap} onZoom={onZoom} className="sc-gimg" />
                    <figcaption>{EX_KIND()[x.kind] && <Chip tone={x.kind === "golden" ? "accent" : ""} className="mr-1.5">{EX_KIND()[x.kind]}</Chip>}<b>{cap}</b>{x.ts && <span className="num"> · {dateTime(x.ts)}</span>}<span className="block text-faint sc-clamp">{KB_SHORT()[x.pattern] || ""}{x.note ? <span data-server-text=""> — {clean(String(x.note))}</span> : null}</span></figcaption>
                  </figure>
                </li>
              );
            })}
          </ul>
        )}
      </Async>
    </Panel>
  );
}

function AboutTab() {
  const q = usePatSpec();
  const spec = Object.fromEntries(itemsOf(q.data).map((x) => [x.id, x]));
  return (
    <>
      <Panel title={t("Cách hệ thống nhận diện")} icon={BookOpen}>
        <ul className="sc-notes">
          <li>{t("Chỉ xét nến đã đóng; tín hiệu đã phát không bị vẽ lại. Nếu kịch bản không còn đúng, nó chỉ đơn giản biến mất khỏi danh sách.")}</li>
          <li>{t("Sẵn sàng: cấu trúc đã đủ, đang chờ nến kích hoạt. Đã kích hoạt: nến kích hoạt vừa đóng.")}</li>
          <li>{t("Entry là giá đóng của nến kích hoạt; SL đặt trên đỉnh cấu trúc; TP theo bội số R (1R/2R/3R). Điểm chỉ để xếp hạng, không phải xác suất thắng.")}</li>
          <li>{t("Mọi kết quả là mô phỏng (paper), có thể khác với giao dịch thật do trượt giá, phí và thời điểm khớp.")}</li>
        </ul>
      </Panel>
      <ul className="sc-spec">
        {PATTERN_IDS.map((id) => {
          const sp = spec[id];
          return (
            <li key={id} className="panel panel-b">
              <div className="flex items-center gap-2 mb-1"><Chip tone="down">{id}</Chip><b className="min-w-0">{KB_SHORT()[id]}</b></div>
              <p className="m-0 text-[13px] text-muted">{KB_DESC()[id]}</p>
              {sp?.steps?.length > 0 && (
                <ol className="sc-steps plain mt-2">{sp.steps.map((x) => <li key={x.id}><CircleDashed size={15} aria-hidden="true" /><span>{t(String(x.label || ""))}</span></li>)}</ol>
              )}
            </li>
          );
        })}
      </ul>
      {q.isError && <p className="m-0 text-[12.5px] text-faint">{t("Chưa tải được danh sách bước chi tiết; mô tả trên vẫn áp dụng.")}</p>}
    </>
  );
}

export default function Scenarios({ query = {} }) {
  const [zoom, setZoom] = useState(null);
  const tab = ["live", "history", "library", "about"].includes(query.tab) ? query.tab : "live";
  const banner = (
    <Notice tone="warn" className="sc-banner">
      <b>{t("Chỉ thông tin, không phải khuyến nghị đầu tư; kết quả là mô phỏng (paper); hệ thống không đặt lệnh.")}</b>
    </Notice>
  );
  return (
    <>
      {query.setup ? (
        <>{banner}<Detail query={query} onZoom={setZoom} /></>
      ) : (
        <>
          <PageHead title={t("Kịch bản")} sub={t("Các mẫu hình giá chiều bán (KB-1 đến KB-4) được nhận diện tự động trên nến đã đóng.")} right={PAT_MOCK ? <Chip tone="accent">{t("Dữ liệu mẫu")}</Chip> : null} />
          {banner}
          <Seg value={tab} onChange={(v) => go(`/kich-ban?tab=${v}`)} label={t("Mục của trang Kịch bản")} scroll className="self-start max-w-full"
            options={[{ value: "live", label: t("Tín hiệu") }, { value: "history", label: t("Lịch sử & kết quả") }, { value: "library", label: t("Thư viện") }, { value: "about", label: t("Giới thiệu") }]} />
          {tab === "live" && <LiveTab />}
          {tab === "history" && <><StatsBlock /><TradesBlock /><PastSetups /></>}
          {tab === "library" && <LibraryTab onZoom={setZoom} />}
          {tab === "about" && <AboutTab />}
        </>
      )}
      {zoom && <Lightbox z={zoom} onClose={() => setZoom(null)} />}
    </>
  );
}
