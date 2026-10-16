import { useMemo, useState } from "react";
import { AlertTriangle, Clock4, ListOrdered, Search, Wallet } from "lucide-react";
import { Async, Chip, Kpi, Notice, PageHead, Panel, ReadOnlyChip, Seg, cn } from "../components/ui";
import { ORDER_KINDS, marginTone, sideOf, useActiveAccount } from "../lib/account";
import { accountTitle } from "../lib/auth";
import { dateTime, f0, f1, money, price, signCls, smoney, symbolLabel } from "../lib/format";
import { t, tn } from "../lib/i18n";

const filters = () => [{ value: "all", label: t("Tất cả") }, { value: "buy", label: t("Mua") }, { value: "sell", label: t("Bán") }, { value: "win", label: t("Đang lãi") }, { value: "loss", label: t("Đang lỗ") }, { value: "nosl", label: t("Chưa có SL") }];
const sorts = () => [{ value: "pl", label: t("Lãi/lỗ") }, { value: "sym", label: t("Mã") }, { value: "time", label: t("Mới nhất") }];

function Sl({ p }) {
  const open = Number(p.price_open ?? p.open_price), sl = Number(p.sl), cur = Number(p.price_current ?? p.price);
  if (!sl) return <Chip tone="accent" title={t("Vị thế chưa đặt Stop Loss: lỗ không bị chặn tự động")}>{t("Chưa có SL")}</Chip>;
  const d = open ? (Math.abs(cur - sl) / cur) * 100 : null;
  return <span className="num">{price(p.symbol, sl)}{d != null && <span className="text-faint text-[12px]"> · {t("cách {n}%", { n: f1(d, 2) })}</span>}</span>;
}

function PositionCards({ rows }) {
  return (
    <div className="grid gap-2 lg:hidden">
      {rows.map((p, i) => (
        <article key={p.position_id || p.ticket || i} className="pos-card" aria-label={`${symbolLabel(p.symbol)} ${sideOf(p) === "buy" ? t("mua") : t("bán")}`}>
          <div className="flex items-center gap-2">
            <b className="text-[15px]">{symbolLabel(p.symbol)}</b>
            <Chip tone={sideOf(p) === "buy" ? "up" : "down"}>{sideOf(p) === "buy" ? t("MUA") : t("BÁN")}</Chip>
            <span className="num text-muted text-[13px]">{p.volume ?? p.lots} {t("lot")}</span>
            <b className={cn("num ml-auto text-[16px]", signCls(p.profit))}>{smoney(p.profit)}</b>
          </div>
          <div className="row"><span>{t("Giá vào → hiện tại")}</span><span className="num">{price(p.symbol, p.price_open ?? p.open_price)} → {price(p.symbol, p.price_current ?? p.price)}</span></div>
          <div className="row"><span>{t("Stop Loss")}</span><Sl p={p} /></div>
          <div className="row"><span>{t("Take Profit")}</span><span className="num">{p.tp ? price(p.symbol, p.tp) : "—"}</span></div>
          <div className="row"><span>{t("Swap · Mở lúc")}</span><span className="num text-[12.5px]">{money(p.swap ?? 0)} · {dateTime(p.time_open)}</span></div>
        </article>
      ))}
    </div>
  );
}

function PositionTable({ rows }) {
  return (
    <div className="scroll-x hidden lg:block">
      <table className="tbl" style={{ minWidth: 780 }}>
        <thead><tr><th>{t("Mã")}</th><th>{t("Hướng")}</th><th className="r">{t("Lot")}</th><th className="r">{t("Giá vào")}</th><th className="r">{t("Giá hiện tại")}</th><th>{t("Stop Loss")}</th><th className="r">{t("Take Profit")}</th><th className="r">{t("Swap")}</th><th>{t("Mở lúc")}</th><th className="r">{t("Lãi/lỗ")}</th></tr></thead>
        <tbody>
          {rows.map((p, i) => (
            <tr key={p.position_id || p.ticket || i}>
              <td><b>{symbolLabel(p.symbol)}</b></td>
              <td><Chip tone={sideOf(p) === "buy" ? "up" : "down"}>{sideOf(p) === "buy" ? t("MUA") : t("BÁN")}</Chip></td>
              <td className="r num">{p.volume ?? p.lots}</td>
              <td className="r num">{price(p.symbol, p.price_open ?? p.open_price)}</td>
              <td className="r num">{price(p.symbol, p.price_current ?? p.price)}</td>
              <td><Sl p={p} /></td>
              <td className="r num text-muted">{p.tp ? price(p.symbol, p.tp) : "—"}</td>
              <td className="r num text-muted">{money(p.swap ?? 0)}</td>
              <td className="num text-[12.5px] text-muted whitespace-nowrap">{dateTime(p.time_open)}</td>
              <td className={cn("r num font-semibold", signCls(p.profit))}>{smoney(p.profit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Orders({ view }) {
  const o = view.orders;
  if (!view.hasOrdersFeed)
    return <div className="text-muted text-[13px]">{t("Máy chủ chưa gửi dữ liệu lệnh chờ cho tài khoản này. Khi có, các lệnh Buy/Sell Limit và Buy/Sell Stop sẽ hiện tại đây.")}</div>;
  if (!o.length) return <div className="text-muted">{t("Không có lệnh chờ nào.")}</div>;
  return (
    <div className="grid gap-2">
      {o.map((x, i) => {
        const buy = String(x.kind || "").startsWith("buy");
        return (
          <article key={x.order_id || i} className="pos-card">
            <div className="flex items-center gap-2 flex-wrap">
              <b className="text-[15px]">{symbolLabel(x.symbol)}</b>
              <Chip tone={buy ? "up" : "down"}>{ORDER_KINDS[x.kind] || ORDER_KINDS.other}</Chip>
              <span className="num text-muted text-[13px]">{x.volume} {t("lot")}</span>
              <span className="num ml-auto font-semibold">@ {price(x.symbol, x.price)}</span>
            </div>
            <div className="row"><span>SL / TP</span><span className="num">{x.sl ? price(x.symbol, x.sl) : "—"} / {x.tp ? price(x.symbol, x.tp) : "—"}</span></div>
            <div className="row"><span>{t("Đặt lúc")}</span><span className="num text-[12.5px]">{dateTime(x.time_setup)}</span></div>
          </article>
        );
      })}
    </div>
  );
}

export default function Positions() {
  const { acc, q, view } = useActiveAccount();
  const [sort, setSort] = useState("pl");
  const [flt, setFlt] = useState("all");
  const [txt, setTxt] = useState("");
  const rows = useMemo(() => {
    const needle = txt.trim().toLowerCase();
    const r = (view?.positions || []).filter((p) => (flt === "all" || (flt === "buy" && sideOf(p) === "buy") || (flt === "sell" && sideOf(p) === "sell") || (flt === "loss" && (p.profit || 0) < 0) || (flt === "win" && (p.profit || 0) > 0) || (flt === "nosl" && !Number(p.sl)))
      && (!needle || String(p.symbol).toLowerCase().includes(needle)));
    if (sort === "pl") r.sort((a, b) => (a.profit || 0) - (b.profit || 0));
    if (sort === "sym") r.sort((a, b) => String(a.symbol).localeCompare(String(b.symbol)));
    if (sort === "time") r.sort((a, b) => new Date(b.time_open || 0) - new Date(a.time_open || 0));
    return r;
  }, [view, sort, flt, txt]);
  const noSl = rows.filter((p) => !Number(p.sl));
  const mt = view ? marginTone(view.level) : null;

  return (
    <>
      <PageHead title={t("Vị thế & lệnh chờ")} sub={acc ? `${accountTitle(acc)} · ${t("cập nhật theo dữ liệu EA gửi lên")}` : t("Chưa có tài khoản")} right={<ReadOnlyChip />} />
      {acc && (
        <Async q={q} rows={6} isEmpty={() => !view} empty={t("Chưa nhận được dữ liệu của tài khoản này.")} hint={t("Kiểm tra EA đã gắn trên biểu đồ và đang chạy.")}>
          {() => (
            <>
              {view.level != null && mt.key !== "safe" && <Notice tone={mt.key === "warn" ? "warn" : "down"} icon={AlertTriangle} title={t("Cảnh báo margin: mức {n}%", { n: f0(view.level) })}>{mt.label}. {t("Còn {n} margin trống.", { n: money(view.free) })} {t("Nếu thị trường đi ngược, broker có thể tự đóng lệnh khi mức margin chạm ngưỡng stop-out của họ.")}</Notice>}
              {noSl.length > 0 && <Notice tone="warn" icon={AlertTriangle} title={tn("{n} vị thế chưa đặt Stop Loss", noSl.length)}>{t("Không có SL nghĩa là khoản lỗ không bị giới hạn tự động. Đây chỉ là nhắc nhở tham khảo, hệ thống không thể đặt hay sửa SL giúp bạn.")}</Notice>}
              <div className="kpi-grid c4">
                <Kpi label={t("Vị thế mở")} value={view.positions.length} sub={`${f1(view.lots, 2)} ${t("lot")}`} />
                <Kpi label={t("Lãi/lỗ đang mở")} value={smoney(view.floating)} tone={signCls(view.floating)} />
                <Kpi label={t("Lệnh chờ")} value={view.hasOrdersFeed ? view.orders.length : "—"} sub={view.hasOrdersFeed ? undefined : t("chưa có dữ liệu")} />
                <Kpi label={t("Mức margin")} value={view.level == null ? "—" : `${f0(view.level)}%`} tone={mt.tone === "down" ? "down" : mt.tone === "up" ? "up" : ""} sub={t("Trống {n}", { n: money(view.free) })} />
              </div>
              {view.positions.length > 3 && (
                <div className="grid gap-2">
                  <label className="relative block"><span className="sr-only">{t("Tìm theo mã")}</span><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" /><input className="field !pl-9" placeholder={t("Tìm theo mã, ví dụ EURUSD")} value={txt} onChange={(e) => setTxt(e.target.value)} /></label>
                  <Seg value={flt} onChange={setFlt} options={filters()} label={t("Lọc vị thế")} scroll />
                </div>
              )}
              <Panel title={`${t("Vị thế đang mở")}${rows.length !== view.positions.length ? ` (${rows.length}/${view.positions.length})` : ""}`} icon={Wallet} right={rows.length > 1 ? <Seg value={sort} onChange={setSort} options={sorts()} label={t("Sắp xếp vị thế")} scroll /> : null} pad={rows.length === 0}>
                {rows.length === 0 ? <div className="text-muted flex items-center gap-2"><Clock4 size={16} aria-hidden="true" /> {view.positions.length ? t("Không có vị thế nào khớp bộ lọc.") : t("Tài khoản không có vị thế đang mở.")}</div> : (
                  <div className="p-2 lg:p-0"><PositionCards rows={rows} /><PositionTable rows={rows} /></div>
                )}
              </Panel>
              <Panel title={t("Lệnh chờ")} icon={ListOrdered}><Orders view={view} /></Panel>
            </>
          )}
        </Async>
      )}
    </>
  );
}
