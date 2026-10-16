// Ma trận tỷ giá chéo 8x8 + máy tính quy đổi. Tỷ giá tham khảo, không dùng để giao dịch.
import { useMemo, useState } from "react";
import { cn } from "../ui";
import { AsOf, QState } from "./bits";
import { CCY_COLOR, CCY_NAME, ccyInk, useFxMatrix } from "../../lib/intel";

const dpFor = (v, quote) => (quote === "JPY" || v >= 100 ? 3 : v >= 10 ? 4 : v >= 0.1 ? 5 : 6);
const fmt = (v, quote) => (v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: dpFor(v, quote), maximumFractionDigits: dpFor(v, quote) }));

export function CrossRatesView({ compact }) {
  const q = useFxMatrix();
  const d = q.data;
  const ccys = useMemo(() => d?.cross?.ccys || [], [d]);
  const mat = useMemo(() => d?.cross?.matrix || [], [d]);
  const [hov, setHov] = useState(null);
  const [amt, setAmt] = useState("1");
  const [from, setFrom] = useState("EUR");
  const [to, setTo] = useState("USD");

  const conv = useMemo(() => {
    const i = ccys.indexOf(from), j = ccys.indexOf(to), n = parseFloat(String(amt).replace(/,/g, "."));
    if (i < 0 || j < 0 || !Number.isFinite(n)) return null;
    const r = i === j ? 1 : mat[i]?.[j];
    return r == null ? null : { rate: r, out: n * r };
  }, [ccys, mat, amt, from, to]);

  const hv = hov && mat[hov.i]?.[hov.j] != null ? { a: ccys[hov.i], b: ccys[hov.j], r: mat[hov.i][hov.j], inv: mat[hov.j]?.[hov.i] } : null;

  return (
    <div className={cn("flex flex-col gap-3", compact && "tm-pad")}>
      <QState q={q} compact={compact} rows={7} empty="Chưa có tỷ giá chéo." isEmpty={(x) => !x || !(x.cross?.matrix || []).length} />
      {d && ccys.length > 0 && (
        <>
          <div className="flex items-center gap-2 flex-wrap text-[12px] text-muted">
            <span>Hàng = tiền tệ cơ sở; cột = đồng yết giá (1 cơ sở = x yết giá).</span>
            <span className="ml-auto"><AsOf ts={d.as_of} /></span>
          </div>
          <div className="overflow-auto" role="region" aria-label="Ma trận tỷ giá chéo" tabIndex={0}>
            <table className="tbl" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  <th scope="col" className="text-left">Cơ sở / Yết</th>
                  {ccys.map((c) => <th key={c} scope="col" style={{ color: ccyInk(c) }}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {ccys.map((a, i) => (
                  <tr key={a}>
                    <th scope="row" className="text-left" style={{ color: ccyInk(a) }} title={CCY_NAME[a]}>{a}</th>
                    {ccys.map((b, j) => (
                      i === j
                        ? <td key={b} className="num text-center" style={{ background: "var(--panel2)", color: "var(--faint)" }} aria-label={`${a}/${b} không áp dụng`}>—</td>
                        : (
                          <td key={b} className="num text-right" tabIndex={0}
                            onMouseEnter={() => setHov({ i, j })} onFocus={() => setHov({ i, j })} onMouseLeave={() => setHov(null)} onBlur={() => setHov(null)}
                            title={`1 ${a} = ${fmt(mat[i][j], b)} ${b}${mat[j]?.[i] != null ? ` · 1 ${b} = ${fmt(mat[j][i], a)} ${a}` : ""}`}
                            style={hov && hov.i === i && hov.j === j ? { outline: "2px solid var(--accent)", outlineOffset: -2 } : undefined}>
                            {fmt(mat[i][j], b)}
                          </td>
                        )
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[12px] num min-h-[18px]" aria-live="polite">
            {hv
              ? <>1 <b>{hv.a}</b> = {fmt(hv.r, hv.b)} <b>{hv.b}</b> · nghịch đảo: 1 <b>{hv.b}</b> = {fmt(hv.inv, hv.a)} <b>{hv.a}</b></>
              : <span className="text-faint">Rê chuột hoặc focus vào một ô để xem nghịch đảo.</span>}
          </div>
          <div className="rounded-md border border-line p-2 grid gap-2">
            <div className="text-[12px] font-semibold">Quy đổi nhanh (tham khảo)</div>
            <div className="flex flex-wrap items-center gap-2">
              <input className="field w-[7.5rem] num" inputMode="decimal" aria-label="Số lượng" value={amt} onChange={(e) => setAmt(e.target.value)} />
              <select className="field" aria-label="Từ tiền tệ" value={from} onChange={(e) => setFrom(e.target.value)}>{ccys.map((c) => <option key={c} value={c}>{c}</option>)}</select>
              <span aria-hidden="true">→</span>
              <select className="field" aria-label="Sang tiền tệ" value={to} onChange={(e) => setTo(e.target.value)}>{ccys.map((c) => <option key={c} value={c}>{c}</option>)}</select>
            </div>
            <div className="num text-[14px]" aria-live="polite">
              {conv
                ? <><b>{Number(conv.out).toLocaleString("en-US", { maximumFractionDigits: dpFor(conv.out, to) })}</b> {to} <span className="text-faint text-[11.5px]">(tỷ giá {fmt(conv.rate, to)})</span></>
                : <span className="text-faint">Nhập số hợp lệ để quy đổi.</span>}
            </div>
          </div>
          <p className="m-0 text-[11px] text-faint">Tỷ giá chéo tính từ các cặp quy về USD, chỉ để tham khảo, không phải giá giao dịch.</p>
        </>
      )}
    </div>
  );
}

export default CrossRatesView;
