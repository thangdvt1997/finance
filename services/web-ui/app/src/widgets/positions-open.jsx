import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ListChecks } from "lucide-react";
import { Async, Chip, cn } from "../components/ui";
import { useAccounts } from "../lib/queries";
import { money, price, signCls, symbolLabel } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "positions-open", title: "Vị thế đang mở", icon: ListChecks, group: "Tài khoản", linkable: true,
  desc: "Mọi lệnh đang mở của các tài khoản MT (chỉ đọc): mã, hướng, khối lượng, giá vào, lãi/lỗ; bấm dòng để đổi mã cho kênh màu.",
  defaultSize: { w: 10, h: 9 }, minSize: { w: 5, h: 4 },
  configSchema: [{ key: "only", label: "Chỉ tài khoản (để trống = tất cả)", type: "text", default: "", placeholder: "vd: mt5:12345678" }],
};

const COLS = [["symbol", "Mã"], ["side", "Hướng"], ["volume", "KL"], ["price_open", "Giá vào"], ["profit", "Lãi/lỗ"]];

export default function PositionsOpen() {
  const { config, symbol, setSymbol } = useWidget();
  const q = useAccounts();
  const [sort, setSort] = useState({ k: "profit", d: -1 });
  const rows = useMemo(() => {
    const out = [];
    for (const a of q.data || []) {
      if (config.only && a.account_id !== config.only) continue;
      for (const p of a.positions || []) out.push({ ...p, account: a.account_id });
    }
    out.sort((x, y) => { const a = x[sort.k], b = y[sort.k]; return (typeof a === "string" ? String(a).localeCompare(b) : (a ?? 0) - (b ?? 0)) * sort.d; });
    return out;
  }, [q.data, config.only, sort]);
  const total = rows.reduce((s, p) => s + (p.profit || 0), 0);
  return (
    <div className="tm-fill">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-line shrink-0">
        <span className="tm-sub">{rows.length} lệnh</span>
        <span className="ml-auto text-[12px] text-muted">Tổng lãi/lỗ <b className={cn("num", signCls(total))}>{money(total)}</b></span>
      </div>
      <div className="tm-scroll">
        <Async q={q} rows={4} empty="Chưa có tài khoản MT nào gửi dữ liệu." isEmpty={(d) => !d.length}>
          {() => rows.length === 0 ? <div className="tm-pad text-muted text-[12.5px]">Không có lệnh đang mở.</div> : (
            <table className="tm-tbl">
              <thead>
                <tr>{COLS.map(([k, l]) => (
                  <th key={k} className={k === "symbol" || k === "side" ? "" : "r"} aria-sort={sort.k === k ? (sort.d > 0 ? "ascending" : "descending") : undefined}>
                    <button type="button" onClick={() => setSort((s) => ({ k, d: s.k === k ? -s.d : -1 }))}>{l}{sort.k === k && (sort.d > 0 ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}</button>
                  </th>))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={`${p.account}-${p.position_id}`} aria-selected={symbol === p.symbol} onClick={() => setSymbol(p.symbol)} title={p.account}>
                    <td className="font-semibold">{symbolLabel(p.symbol)}</td>
                    <td><Chip tone={p.side === "buy" ? "up" : "down"}>{p.side === "buy" ? "MUA" : "BÁN"}</Chip></td>
                    <td className="r num">{p.volume}</td>
                    <td className="r num text-muted">{price(p.symbol, p.price_open)}</td>
                    <td className={cn("r num", signCls(p.profit))}>{money(p.profit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </div>
    </div>
  );
}
