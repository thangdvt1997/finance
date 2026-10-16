import { Sparkline, Chip, cn } from "../ui";
import { DataTable } from "../table";
import { n0, pc, vnd, bil, vol, priceCls, tone, goSymbol, FLOOR_NAME } from "../../lib/vn";

export const Code = ({ code, name }) => (
  <a href={`#/chung-khoan-vn/ma/${code}`} className="no-underline hover:underline" title={name || code}>
    <b className="num">{code}</b>
  </a>
);

export const Pct = ({ v, dp = 2 }) => <span className={cn("num", tone(v))}>{pc(v, dp)}</span>;

export function IndexCard({ ix }) {
  const t = ix.pct > 0 ? "up" : ix.pct < 0 ? "down" : "";
  const adv = ix.advances, dec = ix.declines;
  return (
    <div className={cn("vn-idx-card", t)}>
      <div className="nm"><b className="text-fg">{ix.code === "UPCOM" ? "UPCoM" : ix.code}</b><span className="num">{bil(ix.value)}</span></div>
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div className={cn("num text-[19px] leading-tight", tone(ix.pct))}>{ix.close?.toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          <div className={cn("num text-[12px] whitespace-nowrap", tone(ix.pct))}>{ix.chg > 0 ? "+" : ix.chg < 0 ? "−" : ""}{Math.abs(ix.chg ?? 0).toFixed(2).replace(".", ",")} · {pc(ix.pct)}</div>
        </div>
        <Sparkline values={ix.spark} width={56} height={30} />
      </div>
      {adv != null && (
        <div className="num text-[11px] text-muted flex flex-wrap gap-x-2" title="Số mã tăng / đứng / giảm theo sở (không giao dịch không tính)">
          <span className="whitespace-nowrap"><span className="up">▲{adv}</span> <span className="px-ref">■{ix.no_change}</span> <span className="down">▼{dec}</span></span>
          {(ix.ceiling_n > 0 || ix.floor_n > 0) && <span className="whitespace-nowrap"><span className="px-ceil">trần {ix.ceiling_n}</span> <span className="px-floor">sàn {ix.floor_n}</span></span>}
        </div>
      )}
    </div>
  );
}

/** Thanh độ rộng một sàn: tăng | đứng | giảm | không GD, mỗi đoạn ghi số mã. */
export function BreadthBar({ label, b }) {
  const tr = b.advances + b.unchanged + b.declines + b.no_trade || 1;
  const seg = (n, cls, name) => n > 0 && <span className={cls} style={{ flex: n / tr }} title={`${name}: ${n}`}>{n / tr > 0.06 ? n : ""}</span>;
  return (
    <div className="grid gap-1">
      <div className="flex items-baseline justify-between gap-2 text-[12px]">
        <b>{label}</b>
        <span className="text-muted num">{b.total} mã · GTGD {bil(b.value)}{b.pt_value ? ` (+${bil(b.pt_value)} thoả thuận)` : ""}</span>
      </div>
      <div className="vn-bar" role="img" aria-label={`${label}: ${b.advances} tăng, ${b.unchanged} đứng, ${b.declines} giảm, ${b.no_trade} không giao dịch`}>
        {seg(b.advances, "a", "Tăng")}{seg(b.unchanged, "u", "Đứng giá")}{seg(b.declines, "d", "Giảm")}{seg(b.no_trade, "n", "Không giao dịch")}
      </div>
      <div className="num text-[11.5px] text-muted flex flex-wrap gap-x-3">
        <span className="up">▲ {b.advances} tăng</span><span className="px-ref">■ {b.unchanged} đứng</span><span className="down">▼ {b.declines} giảm</span>
        <span>{b.no_trade} không GD</span>
        {b.ceiling > 0 && <span className="px-ceil">{b.ceiling} trần</span>}{b.floor > 0 && <span className="px-floor">{b.floor} sàn</span>}
      </div>
    </div>
  );
}

const col = (key, header, cell, right) => ({ accessorKey: key, header, cell, meta: right ? { align: "r" } : undefined, sortUndefined: "last" });

/** Bảng top mã (gainers/losers/volume/value/foreign). */
export function MoversTable({ rows, showFlow }) {
  const columns = [
    { id: "code", header: "Mã", accessorKey: "code", cell: (c) => <Code code={c.getValue()} name={c.row.original.name} /> },
    { id: "floor", header: "Sàn", accessorKey: "floor", cell: (c) => <span className="text-muted text-[11.5px]">{FLOOR_NAME[c.getValue()] || c.getValue()}</span> },
    col("close", "Giá", (c) => { const r = c.row.original; return <span className={cn("num", priceCls(r.close, r.basic, r.ceil, r.flr))}>{vnd(r.close)}</span>; }, true),
    col("pct", "%", (c) => <Pct v={c.getValue()} />, true),
    col("volume", "KL", (c) => <span className="num">{vol(c.getValue())}</span>, true),
    col("value", "GTGD", (c) => <span className="num">{bil(c.getValue())}</span>, true),
    ...(showFlow ? [col("f_net", "NN ròng", (c) => <span className={cn("num", tone(c.getValue()))}>{bil(c.getValue(), true)}</span>, true)] : []),
    { id: "lim", header: "", accessorKey: "limit", enableSorting: false, cell: (c) => c.getValue() === "ceiling" ? <Chip className="ceil">Trần</Chip> : c.getValue() === "floor" ? <Chip className="floorc">Sàn</Chip> : null },
  ];
  return <DataTable data={rows || []} columns={columns} getRowId={(r) => r.code} minWidth={showFlow ? 520 : 460} empty="Không có mã phù hợp." />;
}

export function Note({ children }) {
  return <p className="m-0 text-[12px] text-muted max-w-[90ch]">{children}</p>;
}

export function ErrorNote({ q }) {
  return q.isError ? <div role="alert" className="text-down text-[12.5px]">{q.error?.message}</div> : null;
}

export { goSymbol, n0 };
