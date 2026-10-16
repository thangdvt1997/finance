import { useState } from "react";
import { Radar } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg, Sheet, cn } from "../components/ui";
import { TASummary, taNote } from "../components/ta";
import { useScreener } from "../lib/queries";
import { signCls, symbolLabel } from "../lib/format";
import { t } from "../lib/i18n";

const TREND = () => ({ up: [t("Xu hướng tăng"), "up"], down: [t("Xu hướng giảm"), "down"], side: [t("Đi ngang"), ""] });
const MOM = () => ({ overbought: [t("Quá mua"), "accent"], oversold: [t("Quá bán"), "accent"], bullish: [t("Nghiêng tăng"), "up"], bearish: [t("Nghiêng giảm"), "down"], neutral: [t("Trung tính"), ""] });
const VOL = () => ({ squeeze: [t("Nén biến động"), "accent"], high: [t("Biến động cao"), "accent"], normal: [t("Biến động vừa"), ""], low: [t("Biến động thấp"), ""] });
const PRESETS = {
  hot: { get label() { return t("Đáng chú ý"); }, p: { heat_min: 60 } },
  ob: { get label() { return t("Quá mua"); }, p: { momentum: "overbought" } },
  os: { get label() { return t("Quá bán"); }, p: { momentum: "oversold" } },
  up: { get label() { return t("Xu hướng tăng"); }, p: { trend: "up", adx_min: 25 } },
  down: { get label() { return t("Xu hướng giảm"); }, p: { trend: "down", adx_min: 25 } },
  sq: { get label() { return t("Nén biến động"); }, p: { volatility: "squeeze" } },
};
const TFS = ["M15", "H1", "H4", "D1"];
const num = (v, dp = 1) => (v == null ? "—" : Number(v).toFixed(dp));

const Tag = ({ map, v }) => { const [l, tone] = map()[v] || [v, ""]; return <Chip tone={tone}>{l}</Chip>; };

export default function Signals() {
  const [tf, setTf] = useState("H1");
  const [preset, setPreset] = useState("hot");
  const [pick, setPick] = useState(null);
  const q = useScreener({ tf, limit: 40, ...PRESETS[preset].p });
  const items = q.data?.items || [];
  return (
    <>
      <PageHead title={t("Phân tích kỹ thuật")} sub={t("Lọc nhanh các mã theo trạng thái chỉ báo. Đây là mô tả trạng thái, không phải tín hiệu mua/bán.")} />
      <Disclaimer><b>{taNote()}</b> {t("Hệ thống không đưa ra khuyến nghị, không đặt lệnh.")}</Disclaimer>
      <div className="grid gap-2">
        <Seg value={preset} onChange={setPreset} options={Object.entries(PRESETS).map(([value, x]) => ({ value, label: x.label }))} label={t("Bộ lọc nhanh")} scroll />
        <Seg value={tf} onChange={setTf} options={TFS} label={t("Khung thời gian")} className="self-start" />
      </div>
      <Panel title={q.data ? t("Kết quả · {n} mã", { n: q.data.total ?? items.length }) : t("Kết quả")} icon={Radar} pad={false}>
        <div className="p-3">
          <Async q={q} rows={6} isEmpty={(d) => !d?.items?.length} empty={t("Không có mã nào khớp bộ lọc này.")} hint={t("Thử bộ lọc khác hoặc đổi khung thời gian.")}>
            {() => (
              <ul className="list-none m-0 p-0 grid gap-2">
                {items.map((r) => (
                  <li key={`${r.symbol}:${r.tf}`}>
                    <button type="button" className="pos-card w-full text-left cursor-pointer text-inherit font-[inherit]" onClick={() => setPick(r)} aria-label={t("{sym}: xem tóm tắt kỹ thuật", { sym: symbolLabel(r.symbol) })}>
                      <div className="flex items-center gap-2"><b className="text-[15px]">{symbolLabel(r.symbol)}</b><span className="text-[12px] text-faint">{r.tf}</span>
                        <span className={cn("num ml-auto text-[13px]", r.bias > 0 ? "up" : r.bias < 0 ? "down" : "flat")} title={t("Độ nghiêng chỉ báo −100…+100")}>{r.bias > 0 ? "+" : ""}{num(r.bias, 0)}</span></div>
                      <div className="flex flex-wrap gap-1.5"><Tag map={TREND} v={r.trend} /><Tag map={MOM} v={r.momentum} /><Tag map={VOL} v={r.volatility} /></div>
                      <div className="flex gap-4 text-[12.5px] text-muted num"><span>RSI {num(r.rsi)}</span><span>ADX {num(r.adx)}</span><span>Heat {num(r.heat, 0)}</span></div>
                    </button>
                  </li>))}
              </ul>
            )}
          </Async>
        </div>
      </Panel>
      {pick && (
        <Sheet title={t("{sym} · tóm tắt kỹ thuật", { sym: symbolLabel(pick.symbol) })} onClose={() => setPick(null)}>
          <TASummary symbol={pick.symbol} tf={pick.tf} />
          <a className="btn mt-3" href="#/thi-truong" onClick={() => { try { const w = JSON.parse(localStorage.getItem("tc-watch") || "[]"); if (!w.includes(pick.symbol)) localStorage.setItem("tc-watch", JSON.stringify([pick.symbol, ...w].slice(0, 20))); } catch { /* bỏ qua */ } }}>{t("Xem biểu đồ")}</a>
        </Sheet>
      )}
    </>
  );
}
