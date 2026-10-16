// Ma trận 28 cặp x 5 kỳ (% thay đổi). Thống kê tham khảo.
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Seg, cn } from "../ui";
import { AsOf, HeatCell, QState } from "./bits";
import { CCY_NAME, chartHref, fpct, useFxMatrix } from "../../lib/intel";

const PERIODS = [
  { k: "1h", label: "1 giờ", cap: 0.3 },
  { k: "4h", label: "4 giờ", cap: 0.3 },
  { k: "1d", label: "1 ngày", cap: 0.8 },
  { k: "1w", label: "1 tuần", cap: 2 },
  { k: "1m", label: "1 tháng", cap: 4 },
];
const GROUPS = [{ value: "all", label: "Tất cả" }, { value: "major", label: "Majors" }, { value: "cross", label: "Chéo" }];

export function FxHeatmapView({ compact }) {
  const q = useFxMatrix();
  const [grp, setGrp] = useState("all");
  const [ccy, setCcy] = useState("");
  const [sort, setSort] = useState({ key: null, dir: -1 });
  const d = q.data;
  const rows = useMemo(() => d?.rows || [], [d]);
  const linkable = useMemo(() => new Set(d?.coverage?.["1d"] || []), [d]);

  const view = useMemo(() => {
    let r = rows.filter((x) => {
      if (ccy) return x.base === ccy || x.quote === ccy;
      if (grp === "major") return x.base === "USD" || x.quote === "USD";
      if (grp === "cross") return x.base !== "USD" && x.quote !== "USD";
      return true;
    });
    if (sort.key) {
      r = [...r].sort((a, b) => {
        const va = a[sort.key], vb = b[sort.key];
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        return (va - vb) * sort.dir;
      });
    }
    return r;
  }, [rows, grp, ccy, sort]);

  const onSort = (k) => setSort((s) => (s.key === k ? (s.dir === -1 ? { key: k, dir: 1 } : { key: null, dir: -1 }) : { key: k, dir: -1 }));
  const ccys = useMemo(() => [...new Set(rows.flatMap((x) => [x.base, x.quote]))].sort(), [rows]);
  const th = { position: "sticky", top: 0, background: "var(--panel)", zIndex: 1 };
  const cov = (k) => (d?.coverage?.[k] || []).length;

  return (
    <div className={cn("flex flex-col gap-2 min-h-0", compact && "tm-fill")}>
      <div className={cn("flex flex-wrap items-center gap-2", compact && "tm-pad pb-0")}>
        <Seg label="Nhóm cặp" value={ccy ? "" : grp} onChange={(v) => { setCcy(""); setGrp(v); }} options={GROUPS} />
        <label className="flex items-center gap-1 text-[12px] text-muted">Theo tiền tệ
          <select className="field" aria-label="Lọc theo tiền tệ" value={ccy} onChange={(e) => setCcy(e.target.value)}>
            <option value="">—</option>
            {ccys.map((c) => <option key={c} value={c}>{c} · {CCY_NAME[c] || ""}</option>)}
          </select>
        </label>
        <span className="ml-auto"><AsOf ts={d?.as_of} /></span>
      </div>
      <QState q={q} compact={compact} rows={8} empty="Chưa có dữ liệu cặp tiền." isEmpty={(x) => !x || !(x.rows || []).length} />
      {d && rows.length > 0 && (
        <>
          <div className={cn("overflow-auto min-h-0 flex-1", compact ? "tm-scroll" : "max-h-[560px]")} tabIndex={0} role="region" aria-label="Bảng biến động cặp tiền">
            <table className="tbl" style={{ minWidth: 460 }}>
              <thead>
                <tr>
                  <th style={th} scope="col">Cặp</th>
                  {PERIODS.map((p) => (
                    <th key={p.k} style={th} scope="col" aria-sort={sort.key === p.k ? (sort.dir === -1 ? "descending" : "ascending") : "none"}>
                      <button type="button" className="inline-flex items-center gap-1 bg-transparent border-0 text-inherit font-inherit cursor-pointer p-0" onClick={() => onSort(p.k)} title={`Sắp xếp theo ${p.label}`}>
                        {p.label}{sort.key === p.k && (sort.dir === -1 ? <ArrowDown size={11} aria-hidden="true" /> : <ArrowUp size={11} aria-hidden="true" />)}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {view.map((r) => {
                  const link = linkable.has(r.pair);
                  return (
                    <tr key={r.pair}>
                      <th scope="row" className="text-left whitespace-nowrap font-semibold">
                        {link
                          ? <a href={chartHref(r.pair)} className="no-underline hover:text-accent" title={`Mở biểu đồ ${r.pair}`}>{r.base}/{r.quote}</a>
                          : <span title="Cặp chéo, tính từ các cặp quy về USD">{r.base}/{r.quote}</span>}
                      </th>
                      {PERIODS.map((p) => (
                        <td key={p.k} className="p-[1px]">
                          {r[p.k] == null
                            ? <HeatCell v={null} title="Chưa có dữ liệu khung này">—</HeatCell>
                            : <HeatCell v={r[p.k]} cap={p.cap} title={`${r.pair} ${p.label}: ${fpct(r[p.k], 3)}`} />}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {view.length === 0 && <div className="p-3 text-[12.5px] text-muted">Không có cặp phù hợp bộ lọc.</div>}
          </div>
          <p className={cn("m-0 text-[11px] text-faint", compact && "tm-pad pt-0")}>
            "—" = chưa có dữ liệu khung này (khung 1 giờ: {cov("1h")} cặp gốc USD, 4 giờ: {cov("4h")}, 1 ngày: {cov("1d")}). Khi nến ngắn chưa đủ, các khung có thể trùng giá trị. Màu bão hoà theo từng kỳ. Thống kê tham khảo.
          </p>
        </>
      )}
    </div>
  );
}

export default FxHeatmapView;
