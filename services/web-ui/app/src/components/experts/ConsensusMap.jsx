import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Async, Chip } from "../ui";
import { LEVELS, SCOPES, dirArrow, dirTone, dirWord, labelOf, sgn, useConsensus, wfmt } from "../../lib/trackrecord";
import { Sel } from "./Leaderboard";
import { StatusChip } from "./bits";
import { rel, symbolLabel } from "../../lib/format";

const LV_TONE = { consensus: "accent", weak: "", none: "" };
const WINDOWS = [["7", "7 ngày"], ["14", "14 ngày"], ["30", "30 ngày"], ["90", "90 ngày"]];
const LVF = [["", "Mọi mức"], ["consensus", "Đồng thuận"], ["weak", "Nghiêng nhẹ"]];
const ORDER = { consensus: 0, weak: 1, none: 2 };

function Row({ r, open, onToggle, onOpenExpert, compact }) {
  const bw = r.bullish?.weight || 0, sw = r.bearish?.weight || 0, tot = bw + sw || 1;
  const net = r.net_weighted ?? 0;
  const lean = r.level === "none" ? "" : net > 0 ? "tăng" : net < 0 ? "giảm" : "";
  const aria = `${symbolLabel(r.symbol)}: ${r.bullish?.n ?? 0} dự báo tăng, ${r.bearish?.n ?? 0} dự báo giảm, độ nghiêng có trọng số ${sgn(net * 100, 0, "")} trên thang −100 đến 100, mức ${LEVELS[r.level] || r.level}${lean ? " " + lean : ""}`;
  return (
    <li className="xp-cs-row">
      <button type="button" className="xp-cs-btn" onClick={onToggle} aria-expanded={open} aria-label={`${aria}. Bấm để xem ai đưa ra ý kiến.`}>
        <div className="xp-cs-head">
          <span className="sym flex items-center gap-1">{open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}{symbolLabel(r.symbol)}</span>
          <div>
            {/* trái = giảm (đỏ, lớp .b), phải = tăng (xanh, lớp .s): tỷ trọng theo trọng số */}
            <div className="xp-cs-bar" aria-hidden="true"><div className="b" style={{ width: `${(sw / tot) * 100}%` }} /><div className="s" style={{ width: `${(bw / tot) * 100}%` }} /></div>
            <div className="xp-cs-meta"><span className="down">▼ {r.bearish?.n ?? 0} · {wfmt(sw)}</span><span>{r.n_experts} chuyên gia</span><span className="up">▲ {r.bullish?.n ?? 0} · {wfmt(bw)}</span></div>
          </div>
          <span className="flex items-center gap-1 justify-end">
            <Chip tone={r.level === "consensus" ? (net > 0 ? "up" : "down") : LV_TONE[r.level]}>{LEVELS[r.level] || r.level}{lean && r.level !== "none" ? ` ${lean}` : ""}</Chip>
            {!compact && <span className="num text-[12px] text-muted w-[40px] text-right" title="Độ nghiêng có trọng số, thang −100…+100">{sgn(net * 100, 0, "")}</span>}
          </span>
        </div>
      </button>
      {open && (
        <div className="xp-who">
          <div className="text-muted text-[12px]">Mỗi chuyên gia chỉ tính quan điểm mới nhất trong cửa sổ. Độ nghiêng không có trọng số: <span className="num">{sgn((r.net_unweighted ?? 0) * 100, 0, "")}</span> · đồng thuận {Math.round((r.agreement ?? 0) * 100)}% · cập nhật {rel(r.latest_at)}</div>
          {(r.top || []).map((t) => (
            <div key={t.entity_id}>
              <Chip tone={dirTone(t.direction)}>{dirArrow(t.direction)} {dirWord(t.direction)}</Chip>
              {onOpenExpert ? <button type="button" className="xp-link" onClick={() => onOpenExpert(t.entity_id)}>{labelOf(t.label)}</button> : <b>{labelOf(t.label)}</b>}
              <StatusChip status={t.status} />
              <span className="text-faint text-[12px] num">trọng số {wfmt(t.weight)} · {rel(t.published_at)}</span>
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

/** Bản đồ đồng thuận theo symbol. compact: ẩn bộ lọc (widget/client-ui dùng cấu hình). */
export default function ConsensusMap({ windowDays = "14", scope: scope0 = "all", minExperts = "1", level: level0 = "", symbol, limit, compact, onOpenExpert, hideControls }) {
  const [wd, setWd] = useState(String(windowDays));
  const [scope, setScope] = useState(scope0);
  const [minE, setMinE] = useState(String(minExperts));
  const [level, setLevel] = useState(level0);
  const [openId, setOpenId] = useState(null);
  const w = hideControls ? String(windowDays) : wd, sc = hideControls ? scope0 : scope, me = hideControls ? String(minExperts) : minE, lv = hideControls ? level0 : level;
  const q = useConsensus({ window_days: w, scope: sc, min_experts: me });
  const rows = useMemo(() => {
    let r = [...(q.data?.rows || [])];
    if (lv) r = r.filter((x) => x.level === lv);
    if (symbol) r = r.filter((x) => x.symbol === symbol || symbolLabel(x.symbol) === symbolLabel(symbol));
    r.sort((a, b) => ORDER[a.level] - ORDER[b.level] || Math.abs(b.net_weighted) - Math.abs(a.net_weighted) || b.n_experts - a.n_experts);
    return limit ? r.slice(0, limit) : r;
  }, [q.data, lv, symbol, limit]);
  const view = { ...q, data: q.data && { ...q.data, items: rows } };
  return (
    <div>
      {!hideControls && (
        <div className="xp-filters">
          <Sel label="Cửa sổ" value={wd} onChange={setWd} options={WINDOWS} />
          <Sel label="Tài sản" value={scope} onChange={setScope} options={SCOPES} />
          <Sel label="Tối thiểu" value={minE} onChange={setMinE} options={[["1", "1 chuyên gia"], ["2", "2 chuyên gia"], ["3", "3 chuyên gia"], ["5", "5 chuyên gia"]]} />
          <Sel label="Mức" value={level} onChange={setLevel} options={LVF} />
        </div>
      )}
      <Async q={view} rows={5} isEmpty={(d) => !d?.items?.length} empty="Chưa có mã nào đủ điều kiện." hint="Hạ ngưỡng “Tối thiểu”, nới cửa sổ thời gian hoặc bỏ lọc mức." what="bản đồ đồng thuận">
        {() => (
          <>
            <ul className="list-none m-0 p-0" aria-label="Đồng thuận theo mã">
              {rows.map((r) => <Row key={r.symbol} r={r} compact={compact} open={openId === r.symbol} onToggle={() => setOpenId(openId === r.symbol ? null : r.symbol)} onOpenExpert={onOpenExpert} />)}
            </ul>
            {!compact && <p className="xp-sum">Thanh thể hiện tỷ trọng giảm (đỏ, trái) so với tăng (xanh, phải) theo <b>trọng số</b> uy tín; nhóm chưa đủ mẫu có trọng số 1. “Đồng thuận” khi ≥ 3 chuyên gia và độ nghiêng có trọng số ≥ 60%. Đồng thuận chỉ phản ánh ý kiến đã công bố, <b>không phải dự báo giá</b>.</p>}
          </>
        )}
      </Async>
    </div>
  );
}
