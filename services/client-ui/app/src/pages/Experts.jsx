import { useState } from "react";
import { Scale, Trophy } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg } from "../components/ui";
import { pc, sgn, useConsensus, useLeaderboard } from "../lib/trackrecord";
import { symbolLabel } from "../lib/format";
import { t, trData } from "../lib/i18n";
import "./experts.css";

const note = () => t("Chỉ tham khảo, quá khứ không đảm bảo tương lai, đa số ý kiến công khai không vượt ngẫu nhiên.");
const KIND = () => ({ analyst: t("Chuyên gia phân tích"), central_bank: t("Ngân hàng trung ương"), media: t("Luồng tin"), positioning: t("Vị thế đầu cơ"), signal_provider: t("Nhà cung cấp tín hiệu"), other: t("Khác") });
const LV = () => ({ none: t("Chưa rõ"), weak: t("Nghiêng nhẹ"), consensus: t("Đồng thuận") });
const ORDER = { consensus: 0, weak: 1, none: 2 };

function Interval({ lo, hi, v, hollow, up }) {
  if (v == null || lo == null || hi == null) return null;
  const W = 110, x = (a) => 3 + ((Math.max(0.2, Math.min(0.8, a)) - 0.2) / 0.6) * (W - 6);
  const col = up ? "var(--up)" : "var(--muted)";
  return (
    <svg className="xc-iv" width={W} height="16" viewBox={`0 0 ${W} 16`} role="img" aria-label={t("Hit-rate {v}, khoảng tin cậy {lo} đến {hi}, so với 50%", { v: pc(v), lo: pc(lo), hi: pc(hi) })}>
      <line className="ref" x1={x(0.5)} x2={x(0.5)} y1="0" y2="16" />
      <line x1={x(lo)} x2={x(hi)} y1="8" y2="8" stroke={col} strokeWidth="2" strokeLinecap="round" strokeDasharray={hollow ? "3 2" : undefined} opacity={hollow ? 0.6 : 1} />
      <circle cx={x(v)} cy="8" r="4" fill={hollow ? "var(--panel)" : col} stroke={col} strokeWidth="2" />
    </svg>
  );
}

function Card({ r, minN }) {
  const rated = r.status === "rated" && r.rank != null;
  return (
    <li className="xc-card">
      <div className="xc-top">
        <span className={`xc-rank ${rated && r.rank <= 3 ? "top" : ""}`} aria-label={rated ? t("Hạng {n}", { n: r.rank }) : t("Chưa xếp hạng")}>{rated ? r.rank : "—"}</span>
        <b>{trData(String(r.label ?? ""))}</b>
        {r.beats_baseline && rated && <span className="xc-badge ml-auto" title={t("Vượt ngẫu nhiên sau hiệu chỉnh đa kiểm định (q < 0,10)")}>{t("Vượt ngẫu nhiên (q<0,10)")}</span>}
      </div>
      <div className="xc-row"><Chip>{KIND()[r.kind] || r.kind}</Chip>{rated ? <span>{t("{n} quan điểm đã chấm", { n: r.n })}</span> : <span>{t("Chưa đủ mẫu {n}/{m}", { n: r.n, m: minN })}</span>}</div>
      {!rated && <div className="xc-prog" role="progressbar" aria-valuemin={0} aria-valuemax={minN} aria-valuenow={r.n} aria-label={t("Tiến độ mẫu")}><i style={{ width: `${Math.min(100, (r.n / minN) * 100)}%` }} /></div>}
      <div className="xc-row">
        <span className="inline-flex items-center gap-2"><span>{t("Hit-rate")} <b className="num">{pc(r.hit_rate)}</b></span><Interval lo={r.ci_low} hi={r.ci_high} v={r.hit_rate} hollow={!rated} up={r.beats_baseline && rated} /></span>
        <span>{t("Điểm")} <b className="num">{r.score != null ? Math.round(r.score) : "—"}</b>/100</span>
      </div>
    </li>
  );
}

function Board() {
  const [hz, setHz] = useState("1W");
  const q = useLeaderboard({ horizon: hz, scope: "all", limit: 50 });
  return (
    <Panel title={t("Chuyên gia theo điểm uy tín")} icon={Trophy}>
      <Seg value={hz} onChange={setHz} options={["1D", "1W", "1M"]} label={t("Khung đánh giá")} className="mb-3" />
      <Async q={q} rows={4} isEmpty={(d) => !d?.rows?.length} empty={t("Chưa có dữ liệu chuyên gia.")} hint={t("Hệ thống đang thu thập quan điểm; kết quả xuất hiện khi có đủ mẫu.")}>
        {(d) => {
          const rated = d.rows.filter((r) => r.status === "rated").slice(0, 8);
          const rest = d.rows.filter((r) => r.status !== "rated").slice(0, rated.length ? 3 : 5);
          const s = d.summary || {};
          return (
            <>
              {rated.length === 0 && <p className="m-0 mb-2 text-[13px]"><b>{t("Chưa chuyên gia nào đủ mẫu để xếp hạng.")}</b> {t("Đây là kết quả trung thực: khi bằng chứng còn mỏng, hệ thống không xếp hạng.")}</p>}
              <ul className="list-none m-0 p-0 grid gap-2">{rated.map((r) => <Card key={r.entity_id} r={r} minN={d.min_n || 30} />)}</ul>
              {rest.length > 0 && <div className="xc-grp">{t("Chưa đủ mẫu (không xếp hạng)")}</div>}
              <ul className="list-none m-0 p-0 grid gap-2">{rest.map((r) => <Card key={r.entity_id} r={r} minN={d.min_n || 30} />)}</ul>
              <p className="text-[12.5px] text-muted mt-3 mb-0">{t("{a}/{b} chuyên gia đủ mẫu; {c} vượt ngẫu nhiên; kỳ vọng dương tính giả ≈ {d}.", { a: s.rated ?? 0, b: s.entities ?? 0, c: s.beating_baseline ?? 0, d: Number(s.expected_false_positives ?? 0).toFixed(1) })}</p>
            </>
          );
        }}
      </Async>
    </Panel>
  );
}

function Consensus() {
  const q = useConsensus({ window_days: 14, min_experts: 2 });
  return (
    <Panel title={t("Đồng thuận theo mã")} icon={Scale}>
      <Async q={q} rows={4} isEmpty={(d) => !d?.rows?.length} empty={t("Chưa có mã nào đủ nhiều ý kiến.")} hint={t("Cần ít nhất 2 chuyên gia cùng nêu quan điểm trong 14 ngày.")}>
        {(d) => {
          const rows = [...d.rows].sort((a, b) => ORDER[a.level] - ORDER[b.level] || Math.abs(b.net_weighted) - Math.abs(a.net_weighted)).slice(0, 8);
          return (
            <>
              <ul className="list-none m-0 p-0 grid gap-3">
                {rows.map((r) => {
                  const bw = r.bullish?.weight || 0, sw = r.bearish?.weight || 0, tot = bw + sw || 1;
                  const dir = r.level === "consensus" ? (r.net_weighted > 0 ? ` ${t("tăng")}` : ` ${t("giảm")}`) : "";
                  return (
                    <li key={r.symbol}>
                      <div className="flex items-center gap-2"><b>{symbolLabel(r.symbol)}</b><span className="text-[12px] text-faint">{t("{n} chuyên gia", { n: r.n_experts })}</span>
                        <Chip tone={r.level === "consensus" ? (r.net_weighted > 0 ? "up" : "down") : ""} className="ml-auto">{LV()[r.level]}{dir}</Chip></div>
                      <div className="xc-bar mt-1" role="img" aria-label={t("{sym}: {b} tăng, {s} giảm, mức {lv}", { sym: symbolLabel(r.symbol), b: r.bullish?.n ?? 0, s: r.bearish?.n ?? 0, lv: LV()[r.level] })}><div className="b" style={{ width: `${(sw / tot) * 100}%` }} /><div className="s" style={{ width: `${(bw / tot) * 100}%` }} /></div>
                      <div className="flex justify-between text-[12px] text-muted num mt-[2px]"><span className="down">▼ {r.bearish?.n ?? 0}</span><span>{sgn((r.net_weighted ?? 0) * 100)}</span><span className="up">▲ {r.bullish?.n ?? 0}</span></div>
                    </li>
                  );
                })}
              </ul>
              <p className="text-[12.5px] text-muted mt-3 mb-0">{t("Đồng thuận chỉ phản ánh ý kiến đã công bố (có trọng số theo uy tín), không phải dự báo giá.")}</p>
            </>
          );
        }}
      </Async>
    </Panel>
  );
}

export default function Experts() {
  return (
    <>
      <PageHead title={t("Chuyên gia & đồng thuận")} sub={t("Ai nói đúng hướng thật sự, so với ngẫu nhiên? Dữ liệu công khai, không liên quan tài khoản của bạn.")} />
      <Disclaimer><b>{note()}</b> {t("Không phải khuyến nghị đầu tư.")}</Disclaimer>
      <Board />
      <Consensus />
    </>
  );
}
