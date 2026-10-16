import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { Async, Chip, Seg, cn } from "../ui";
import { Dialog } from "../dialog";
import { HORIZONS, HZ_BARS, REGIMES, dirArrow, dirTone, dirWord, kindLabel, langLabel, labelOf, pc, scopeLabel, sgn, useTrackRecord, wfmt, FIXED_NOTE } from "../../lib/trackrecord";
import { BandChart, BeatsBadge, HitCell, IntervalBar, MethodButton, Progress, StatusChip } from "./bits";
import { dateTime, date, rel, symbolLabel } from "../../lib/format";

function HCard({ hz, c, cur, onPick }) {
  const rated = c.status === "rated";
  return (
    <button type="button" className={cn("xp-card text-left cursor-pointer text-inherit font-[inherit]", cur && "cur")} onClick={() => onPick(hz)} aria-pressed={cur}>
      <h4><span>Khung {hz}</span><StatusChip status={c.status} /></h4>
      <div className="sub">thoát sau {HZ_BARS[hz]} nến ngày</div>
      <div className="big num">{pc(c.hit_rate)}</div>
      <IntervalBar lo={c.ci_low} hi={c.ci_high} v={c.hit_rate} tone={c.beats_baseline && rated ? "up" : ""} hollow={!rated} width={130} />
      <div className="text-[11.5px] text-muted num">KTC 95%: {pc(c.ci_low)} – {pc(c.ci_high)}</div>
      <div className="text-[12px]"><span className="text-muted">Lợi suất TB: </span><span className={cn("num", c.mean_ret_pct > 0 ? "up" : c.mean_ret_pct < 0 ? "down" : "")}>{sgn(c.mean_ret_pct)}</span></div>
      <div className="text-[12px] text-muted num">Điểm {c.score != null ? Math.round(c.score) : "—"}/100 · trọng số {wfmt(c.weight)}</div>
      {rated ? <BeatsBadge row={c} /> : <Progress row={c} />}
    </button>
  );
}

function Breakdown({ title, rows, nameOf }) {
  if (!rows?.length) return null;
  return (
    <>
      <h3 className="xp-sec">{title}</h3>
      <div className="scroll-x">
        <table className="tbl" style={{ minWidth: 420 }}>
          <thead><tr><th scope="col">Nhóm</th><th scope="col" className="r">Mẫu</th><th scope="col">Hit-rate · KTC</th><th scope="col" className="r">Lợi suất TB</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{nameOf(r)}{r.status === "insufficient" && <span className="text-faint text-[11.5px]"> · chưa đủ mẫu</span>}</td>
                <td className="r num">{r.n}</td>
                <td><HitCell row={{ ...r, status: r.status || (r.n >= 30 ? "rated" : "insufficient") }} width={100} /></td>
                <td className={cn("r num", r.mean_ret_pct > 0 ? "up" : r.mean_ret_pct < 0 ? "down" : "")}>{sgn(r.mean_ret_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Outcome({ hz, o }) {
  if (!o) return <Chip title={`Khung ${hz}: chưa tới hạn`}>{hz} · chờ</Chip>;
  return <Chip tone={o.hit ? "up" : "down"} title={`Khung ${hz}: ${o.hit ? "đúng hướng" : "sai hướng"}, lợi suất ${sgn(o.ret_pct)}`}>{hz} · {o.hit ? "✓" : "✗"} {sgn(o.ret_pct, 2, "")}</Chip>;
}

function Body({ id }) {
  const [horizon, setHorizon] = useState("1W");
  const q = useTrackRecord(id, { horizon });
  return (
    <div className="p-3">
      <Async q={q} rows={8} empty="Không có dữ liệu cho chuyên gia này." what="hồ sơ chuyên gia" isEmpty={(d) => !d?.entity}>
        {(d) => {
          const c = d.card;
          const roll = (d.rolling || []).map((p) => ({ t: p.t, y: p.hit_rate, lo: p.ci_low, hi: p.ci_high, n: p.n }));
          const eq = (d.equity?.points || []).map((p) => ({ t: p.t, y: p.cum_ret_pct, lo: p.rand_p05, hi: p.rand_p95, mid: p.rand_p50 }));
          return (
            <>
              <h3 className="m-0 mb-2 text-[18px] font-semibold">{labelOf(d.entity.label)}</h3>
              <div className="flex flex-wrap gap-1 items-center">
                <Chip>{kindLabel(d.entity.kind)}</Chip><Chip>{langLabel(d.entity.lang)}</Chip><StatusChip status={c.status} /><BeatsBadge row={c} />
              </div>
              <p className="xp-note mt-2">{d.entity.n_total} quan điểm có hướng · từ {date(d.entity.first_view_at)} · gần nhất {rel(d.entity.last_view_at)}</p>
              <div className="flex flex-wrap items-center gap-2 mt-2"><Seg value={horizon} onChange={setHorizon} label="Khung đánh giá" options={HORIZONS.map(([v]) => ({ value: v, label: v }))} /><MethodButton /></div>

              <h3 className="xp-sec">Ba khung đánh giá</h3>
              <div className="xp-cards">
                {HORIZONS.map(([hz]) => d.horizons?.[hz] && <HCard key={hz} hz={hz} c={d.horizons[hz].card} cur={hz === horizon} onPick={setHorizon} />)}
              </div>
              {c.status !== "rated" && <p className="xp-note mt-2">Chưa đủ mẫu ở khung {horizon}: cần thêm {c.n_needed ?? "…"} quan điểm đã chấm. Thứ hạng và huy hiệu chỉ xuất hiện sau ngưỡng này; số liệu bên dưới chỉ để tham khảo.</p>}

              <h3 className="xp-sec">Hit-rate tích luỹ theo thời gian (khung {horizon})</h3>
              <BandChart pts={roll} ref0={0.5} yFmt={(v) => pc(v, 0)} label="Hit-rate tích luỹ với khoảng tin cậy" lineLabel="Hit-rate tích luỹ" bandLabel="KTC 95% (Wilson)" yMin={0} yMax={1}
                tip={(p) => [`${date(p.t)} · n=${p.n}`, `Hit-rate ${pc(p.y)}`, `KTC ${pc(p.lo)} – ${pc(p.hi)}`]} />
              <details className="mt-1 text-[12px] text-muted"><summary className="cursor-pointer">Xem dạng bảng số</summary>
                <div className="scroll-x"><table className="tbl"><thead><tr><th>Ngày</th><th className="r">n</th><th className="r">Hit-rate</th><th className="r">KTC thấp</th><th className="r">KTC cao</th></tr></thead>
                  <tbody>{roll.slice(-12).map((p, i) => <tr key={i}><td>{date(p.t)}</td><td className="r num">{p.n}</td><td className="r num">{pc(p.y)}</td><td className="r num">{pc(p.lo)}</td><td className="r num">{pc(p.hi)}</td></tr>)}</tbody></table></div>
              </details>

              <h3 className="xp-sec">Lợi suất “nếu làm theo” so với ngẫu nhiên</h3>
              <BandChart pts={eq} ref0={0} yFmt={(v) => sgn(v, 1)} label="Tổng lợi suất nếu làm theo và dải ngẫu nhiên" tone="var(--accent)" lineLabel="Nếu làm theo chuyên gia" bandLabel="Ngẫu nhiên p05–p95 (hoán vị hướng)"
                tip={(p) => [date(p.t), `Nếu theo: ${sgn(p.y)}`, `Ngẫu nhiên: ${sgn(p.lo)} … ${sgn(p.hi)}`]} />
              <p className="xp-note mt-1">{d.equity?.note || "Tổng lợi suất log %, chưa tính phí/trượt giá. Đường nằm trong dải ngẫu nhiên nghĩa là chưa phân biệt được với may rủi."}</p>
              <details className="mt-1 text-[12px] text-muted"><summary className="cursor-pointer">Xem dạng bảng số</summary>
                <div className="scroll-x"><table className="tbl"><thead><tr><th>Ngày</th><th className="r">Nếu theo</th><th className="r">p05</th><th className="r">p95</th></tr></thead>
                  <tbody>{eq.slice(-12).map((p, i) => <tr key={i}><td>{date(p.t)}</td><td className="r num">{sgn(p.y)}</td><td className="r num">{sgn(p.lo)}</td><td className="r num">{sgn(p.hi)}</td></tr>)}</tbody></table></div>
              </details>

              <Breakdown title="Theo loại tài sản / mã" rows={d.by_scope} nameOf={(r) => scopeLabel(r.scope)} />
              <Breakdown title="Theo chế độ thị trường lúc công bố" rows={d.by_regime} nameOf={(r) => REGIMES[r.regime] || r.regime} />

              <h3 className="xp-sec">Quan điểm gần đây</h3>
              {!d.recent?.length ? <div className="xp-empty">Chưa có quan điểm nào được ghi nhận.</div> : (
                <ol className="xp-tl">
                  {d.recent.map((v) => (
                    <li key={v.view_id} className={cn(dirTone(v.direction), v.state)}>
                      <div className="flex flex-wrap items-center gap-2">
                        <b>{symbolLabel(v.symbol)}</b>
                        <Chip tone={dirTone(v.direction)}>{dirArrow(v.direction)} {dirWord(v.direction)}</Chip>
                        <Chip tone={v.state === "pending" ? "accent" : ""}>{v.state === "pending" ? "Đang chờ chấm" : "Đã chấm"}</Chip>
                        <span className="text-faint text-[12px] num">{dateTime(v.published_at)}</span>
                      </div>
                      <div className="xp-oc mt-1">{HORIZONS.map(([hz]) => <Outcome key={hz} hz={hz} o={v.outcome?.[hz]} />)}</div>
                      {v.invalidation != null && <div className="xp-note mt-1">Mức vô hiệu: <span className="num">{v.invalidation}</span></div>}
                    </li>
                  ))}
                </ol>
              )}
              <p className="xp-note mt-3 flex items-center gap-1"><ShieldCheck size={13} aria-hidden="true" />{d.chain?.verified ? "Nhật ký quan điểm không thể sửa (chuỗi băm đã được xác minh)." : "Chuỗi băm chưa xác minh được ở lần kiểm tra gần nhất."}</p>
              <p className="xp-note mt-2">{FIXED_NOTE}</p>
            </>
          );
        }}
      </Async>
    </div>
  );
}

export default function ExpertDetail({ id, onClose }) {
  return (
    <Dialog open={!!id} onClose={onClose} variant="drawer" title="Hồ sơ chuyên gia" className="xp-drawer">
      {id && <Body id={id} key={id} />}
    </Dialog>
  );
}
export { labelOf };
