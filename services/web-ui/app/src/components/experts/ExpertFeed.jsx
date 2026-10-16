import { useState } from "react";
import { Async, Chip, Seg } from "../ui";
import { dirArrow, dirTone, dirWord, kindLabel, labelOf, useFeed, wfmt } from "../../lib/trackrecord";
import { StatusChip } from "./bits";
import { rel, symbolLabel, dateTime } from "../../lib/format";

const DIRS = [{ value: "", label: "Tất cả" }, { value: "bullish", label: "Tăng" }, { value: "bearish", label: "Giảm" }];

/** Dòng thời gian quan điểm gần đây. symbol/direction có thể cố định từ ngoài (widget) hoặc người dùng chọn. */
export default function ExpertFeed({ symbol: symbol0 = "", direction: dir0 = "", limit: limit0 = 30, entityId, onOpenExpert, hideControls, compact }) {
  const [sym, setSym] = useState("");
  const [dir, setDir] = useState("");
  const [limit, setLimit] = useState(limit0);
  const symbol = hideControls ? symbol0 : sym.trim().toUpperCase();
  const direction = hideControls ? dir0 : dir;
  const q = useFeed({ limit, symbol: symbol || undefined, direction: direction || undefined, entity_id: entityId || undefined });
  const items = q.data?.items || [];
  return (
    <div>
      {!hideControls && (
        <div className="xp-filters">
          <label><span>Mã</span><input className="field" style={{ width: 120 }} value={sym} onChange={(e) => setSym(e.target.value)} placeholder="vd: EURUSD" aria-label="Lọc theo mã" /></label>
          <Seg value={dir} onChange={setDir} options={DIRS} label="Hướng" />
        </div>
      )}
      <Async q={q} rows={5} isEmpty={(d) => !d?.items?.length} empty="Chưa có quan điểm phù hợp." hint="Bỏ bớt bộ lọc mã/hướng, hoặc quay lại sau khi có ý kiến mới." what="dòng quan điểm">
        {() => (
          <>
            <ul className="xp-feed" aria-label="Quan điểm gần đây">
              {items.map((it) => (
                <li key={it.view_id}>
                  <div className="l1">
                    <Chip tone={dirTone(it.direction)}>{dirArrow(it.direction)} {dirWord(it.direction)}</Chip>
                    <b>{symbolLabel(it.symbol)}</b>
                    {onOpenExpert ? <button type="button" className="xp-link" onClick={() => onOpenExpert(it.entity_id)}>{labelOf(it.label)}</button> : <span>{labelOf(it.label)}</span>}
                  </div>
                  <div className="l2">
                    <span title={dateTime(it.published_at)}>{rel(it.published_at)}</span>
                    {!compact && <span>{kindLabel(it.kind)}</span>}
                    <StatusChip status={it.status} />
                    <span>trọng số {wfmt(it.weight)}</span>
                    {it.horizon_hint && <span>khung nêu: {it.horizon_hint}</span>}
                    {it.invalidation != null && <span>vô hiệu: <span className="num">{it.invalidation}</span></span>}
                  </div>
                </li>
              ))}
            </ul>
            {q.data?.next_before && limit < 200 && <div className="pt-2"><button type="button" className="btn" onClick={() => setLimit((l) => Math.min(200, l + 50))} disabled={q.isFetching}>{q.isFetching ? "Đang tải…" : "Tải thêm"}</button></div>}
          </>
        )}
      </Async>
    </div>
  );
}
