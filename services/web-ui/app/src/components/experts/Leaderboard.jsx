import { useState } from "react";
import { Async, Seg, cn } from "../ui";
import { HORIZONS, KINDS, LANGS, SCOPES, honestSummary, kindLabel, langLabel, labelOf, qfmt, useLeaderboard, wfmt } from "../../lib/trackrecord";
import { BeatsBadge, HitCell, Progress, Rank, ScoreBar, retCell } from "./bits";
import { rel } from "../../lib/format";

export function Sel({ label, value, onChange, options }) {
  return (
    <label>
      <span>{label}</span>
      <select className="field" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

export default function Leaderboard({ onOpen }) {
  const [horizon, setHorizon] = useState("1W");
  const [scope, setScope] = useState("all");
  const [kind, setKind] = useState("");
  const [lang, setLang] = useState("");
  const [showInsuf, setShowInsuf] = useState(true);
  const q = useLeaderboard({ horizon, scope, kind: kind || undefined, lang: lang || undefined, include_insufficient: showInsuf ? undefined : "false", limit: 200 });
  const minN = q.data?.min_n ?? 30;
  return (
    <div>
      <div className="xp-filters">
        <Seg value={horizon} onChange={setHorizon} label="Khung đánh giá" options={HORIZONS.map(([v]) => ({ value: v, label: v }))} />
        <Sel label="Tài sản" value={scope} onChange={setScope} options={SCOPES} />
        <Sel label="Loại" value={kind} onChange={setKind} options={KINDS} />
        <Sel label="Ngôn ngữ" value={lang} onChange={setLang} options={LANGS} />
        <label className="cursor-pointer"><input type="checkbox" checked={showInsuf} onChange={(e) => setShowInsuf(e.target.checked)} /> <span>Hiện nhóm chưa đủ mẫu</span></label>
      </div>
      <Async q={q} variant="table" rows={6} cols={7} isEmpty={(d) => !d?.rows?.length} empty="Không có chuyên gia nào khớp bộ lọc." hint="Thử bỏ bớt bộ lọc, hoặc bật “Hiện nhóm chưa đủ mẫu”." what="bảng xếp hạng chuyên gia">
        {(d) => {
          const rated = d.rows.filter((r) => r.status === "rated");
          const rest = d.rows.filter((r) => r.status !== "rated");
          const row = (r, dim) => (
            <tr key={r.entity_id} className={cn(dim && "xp-dim")}>
              <td><Rank row={r} /></td>
              <td className="xp-name">
                <button type="button" className="xp-link" onClick={() => onOpen?.(r.entity_id)} aria-label={`Xem chi tiết ${labelOf(r.label)}`}>{labelOf(r.label)}</button>
                <div className="xp-note mt-[2px]">{kindLabel(r.kind)} · {langLabel(r.lang)}</div>
              </td>
              <td><Progress row={r} minN={minN} /></td>
              <td><HitCell row={r} /></td>
              <td className="r">{retCell(r)}</td>
              <td><ScoreBar v={r.score} dim={dim} /></td>
              <td className="r num text-muted" title="q-value (BH-FDR) trên toàn bộ họ kiểm định">{r.status === "rated" ? qfmt(r.q_value) : "—"}</td>
              <td className="r num text-muted">{wfmt(r.weight)}</td>
              <td>{r.status === "rated" ? (<BeatsBadge row={r} />) : <span className="text-faint text-[12px]">—</span>}{r.status === "rated" && !r.beats_baseline && <span className="text-faint text-[12px]">Chưa vượt ngẫu nhiên</span>}</td>
              <td className="text-faint text-[12px]">{r.last_view_at ? rel(r.last_view_at) : "—"}</td>
            </tr>
          );
          return (
            <>
              <div className="scroll-x">
                <table className="tbl xp-tbl" style={{ minWidth: 1020 }}>
                  <caption className="sr-only">Bảng xếp hạng chuyên gia theo khung {d.horizon}, phạm vi {d.scope}</caption>
                  <thead><tr>
                    <th scope="col">Hạng</th><th scope="col" className="xp-name">Chuyên gia</th><th scope="col">Mẫu</th>
                    <th scope="col" title="Tỷ lệ đúng hướng và khoảng tin cậy 95% (Wilson); đường nét đứt là 50% (ngẫu nhiên)">Hit-rate · KTC 95%</th>
                    <th scope="col" className="r" title="Lợi suất trung bình mỗi quan điểm nếu làm theo, chưa trừ phí">Lợi suất TB “nếu theo”</th>
                    <th scope="col">Điểm uy tín</th><th scope="col" className="r">q-value</th><th scope="col" className="r">Trọng số</th><th scope="col">Kết luận</th><th scope="col">Gần nhất</th>
                  </tr></thead>
                  <tbody>
                    {rated.length === 0 && <tr className="xp-sep"><td colSpan={10}><b>Chưa chuyên gia nào đủ mẫu (≥ {minN} quan điểm đã chấm)</b> nên chưa có bảng xếp hạng. Đây là kết quả trung thực, không phải lỗi: hệ thống sẽ không xếp hạng khi bằng chứng còn mỏng.</td></tr>}
                    {rated.map((r) => row(r, false))}
                    {rest.length > 0 && <tr className="xp-sep"><td colSpan={10}><b>Chưa đủ mẫu ({rest.length})</b> · dưới {minN} quan điểm độc lập đã chấm: không xếp hạng, số liệu chỉ để tham khảo, khoảng tin cậy còn rất rộng.</td></tr>}
                    {rest.map((r) => row(r, true))}
                  </tbody>
                </table>
              </div>
              <p className="xp-sum" aria-live="polite"><b>Tóm tắt trung thực:</b> {honestSummary(d.summary)}. Lợi suất “nếu theo” là mô phỏng giả định, không phải kết quả giao dịch thật.</p>
              <p className="xp-note mt-1">{d.baseline?.note ? `Mốc so sánh: 50% — ${d.baseline.note}. ` : ""}Cập nhật {rel(d.as_of)}.</p>
            </>
          );
        }}
      </Async>
    </div>
  );
}
