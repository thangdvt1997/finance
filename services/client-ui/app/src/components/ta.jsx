import { Async, Chip, Kpi, Seg } from "./ui";
import { useAnSymbol } from "../lib/queries";
import { price, symbolLabel } from "../lib/format";
import { t } from "../lib/i18n";

export const taNote = () => t("Chỉ báo kỹ thuật tham khảo, không phải khuyến nghị đầu tư.");
const TONE = { up: "up", down: "down", accent: "accent", warn: "accent", neutral: "" };
const num = (v, dp = 1) => (v == null ? "—" : Number(v).toFixed(dp));
const signed = (v, dp = 0) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(dp)}`);
export const lineData = (ts, v) => ts.map((x, i) => ({ time: x, value: v[i] })).filter((p) => p.value != null);

/** Tóm tắt kỹ thuật rút gọn của một symbol cho khung `tf` (nếu không có khung đó, lấy khung đầu tiên). */
export function TASummary({ symbol, tf, onTf, d: dProp }) {
  const q = useAnSymbol(symbol);
  const tfs = q.data ? Object.keys(q.data.tfs || {}) : [];
  const cur = tfs.includes(tf) ? tf : tfs[0];
  const d = dProp || q.data?.tfs?.[cur];
  return (
    <Async q={q} rows={5} isEmpty={() => !d} empty={t("Chưa có phân tích cho {sym}.", { sym: symbolLabel(symbol) })} hint={t("Cần đủ nến lịch sử để tính chỉ báo.")}>
      {() => (
        <div className="grid gap-3">
          {onTf && tfs.length > 1 && <Seg value={cur} onChange={onTf} options={tfs} label={t("Khung phân tích")} scroll />}
          <div className="flex flex-wrap gap-1.5" aria-label={t("Trạng thái kỹ thuật")}>
            {(d.states || []).map((s) => <Chip key={s.code} tone={TONE[s.tone]} title={t("Quy tắc: {rule}", { rule: s.rule })}>{s.label}</Chip>)}
          </div>
          <div className="kpi-grid c4">
            <Kpi label={t("Độ nghiêng chỉ báo")} value={signed(d.bias)} tone={d.bias > 0 ? "up" : d.bias < 0 ? "down" : ""} sub="−100 … +100" />
            <Kpi label="RSI(14)" value={num(d.rsi)} sub={d.rsi >= 70 ? t("vùng quá mua") : d.rsi <= 30 ? t("vùng quá bán") : t("trung tính")} />
            <Kpi label="ADX(14)" value={num(d.adx)} sub={d.adx >= 25 ? t("xu hướng rõ") : t("xu hướng yếu")} />
            <Kpi label={t("Cách EMA200")} value={d.ema200_dist_pct == null ? "—" : `${signed(d.ema200_dist_pct, 2)}%`} tone={d.ema200_dist_pct > 0 ? "up" : d.ema200_dist_pct < 0 ? "down" : ""} />
          </div>
          {d.pivot && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
              {["r2", "r1", "p", "s1", "s2"].map((k) => <span key={k}><span className="text-muted uppercase">{k}</span> <b className="num">{price(symbol, d.pivot[k])}</b></span>)}
            </div>
          )}
          <p className="m-0 text-[12px] text-faint">{taNote()} {t("Hệ thống chỉ mô tả trạng thái, không đưa ra tín hiệu mua/bán.")}</p>
        </div>
      )}
    </Async>
  );
}
