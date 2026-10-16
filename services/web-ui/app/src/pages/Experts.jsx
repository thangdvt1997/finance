import { useMemo, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { Users } from "lucide-react";
import { Async, Chip, LatestFresh, PageHead, Panel, Seg, cn } from "../components/ui";
import { FRESH } from "../lib/freshness";
import { DataTable } from "../components/table";
import { consensus, useExperts, usePositions, useSignals } from "../lib/queries";
import { dateTime, pct, price, rel, symbolLabel, clean, expertLabel } from "../lib/format";
import TrackRecordTab from "../components/experts/TrackRecordTab";
import { FixedNote } from "../components/experts/bits";

const SIDE = { buy: ["MUA", "up"], sell: ["BÁN", "down"], flat: ["ĐỨNG NGOÀI", ""] };

function ScoreBar({ v }) {
  const n = v ?? 0;
  const col = n >= 70 ? "var(--up)" : n >= 50 ? "var(--accent)" : "var(--down)";
  return (
    <div className="flex items-center gap-2 min-w-[96px]" title={`Điểm uy tín ${n}/100`}>
      <div className="flex-1 h-[6px] rounded bg-line"><div className="h-full rounded" style={{ width: `${Math.max(2, Math.min(100, n))}%`, background: col }} /></div>
      <span className="num text-[12px] w-[28px] text-right">{v == null ? "—" : Math.round(n)}</span>
    </div>
  );
}

const expertCols = [
  { id: "name", header: "Chuyên gia", accessorFn: (e) => e.display_name || e.expert_id,
    cell: ({ row: { original: e } }) => (
      <div>
        {e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer" className="font-semibold no-underline hover:text-accent">{expertLabel(e.display_name || e.expert_id)}</a> : <b>{expertLabel(e.display_name || e.expert_id)}</b>}
      </div>) },
  { id: "score", header: "Điểm uy tín", accessorFn: (e) => e.reputation?.score ?? -1, cell: ({ row: { original: e } }) => <ScoreBar v={e.reputation?.score} /> },
  { id: "gain", header: "Lãi", accessorFn: (e) => e.reputation?.gain_pct ?? -999, meta: { align: "r" }, cell: ({ row: { original: e } }) => <span className={cn("num", (e.reputation?.gain_pct ?? 0) >= 0 ? "up" : "down")}>{pct(e.reputation?.gain_pct, 1)}</span> },
  { id: "dd", header: "Sụt vốn tối đa", accessorFn: (e) => e.reputation?.max_drawdown_pct ?? 999, meta: { align: "r" }, cell: ({ row: { original: e } }) => <span className="num">{e.reputation?.max_drawdown_pct != null ? `${e.reputation.max_drawdown_pct.toFixed(1)}%` : "—"}</span> },
  { id: "months", header: "Số tháng", accessorFn: (e) => e.reputation?.months_active ?? 0, meta: { align: "r" }, cell: ({ getValue }) => <span className="num">{getValue() || "—"}</span> },
  { id: "followers", header: "Người theo dõi", accessorFn: (e) => e.reputation?.followers ?? 0, meta: { align: "r" }, cell: ({ getValue }) => <span className="num">{getValue() ? getValue().toLocaleString("en-US") : "—"}</span> },
  { id: "flags", header: "Cờ rủi ro", enableSorting: false,
    cell: ({ row: { original: e } }) => {
      const r = e.reputation || {};
      const f = [r.martingale && "Martingale", r.grid && "Grid", r.history_wiped && "Xoá lịch sử"].filter(Boolean);
      return <div className="flex flex-wrap gap-1">{f.length ? f.map((x) => <Chip key={x} tone="down">{x}</Chip>) : <Chip tone={r.qualified ? "up" : ""}>{r.qualified ? "Đạt chuẩn" : e.tracked ? "Theo dõi" : "Không đạt"}</Chip>}</div>;
    } },
];

function Experts_() {
  const q = useExperts();
  return (
    <Async q={q} empty="Chưa theo dõi chuyên gia nào." hint="expert-collector mặc định tắt: đặt EXPERT_COLLECTOR_ENABLED=true sau khi đọc README về ToS nguồn." rows={5}>
      {(d) => <DataTable data={d.items} columns={expertCols} initialSort={[{ id: "score", desc: true }]} getRowId={(e) => e.expert_id + e.source} minWidth={680} />}
    </Async>
  );
}

function Signals_({ experts }) {
  const [status, setStatus] = useState("open");
  const q = useSignals({ status: status === "all" ? undefined : status });
  const name = useMemo(() => new Map((experts || []).map((e) => [e.expert_id, e.display_name || e.expert_id])), [experts]);
  return (
    <>
      <div className="mb-3"><Seg value={status} onChange={setStatus} label="Trạng thái" options={[{ value: "open", label: "Đang mở" }, { value: "closed", label: "Đã đóng" }, { value: "all", label: "Tất cả" }]} /></div>
      <Async q={q} empty="Không có tín hiệu nào." rows={5}>
        {(d) => (
          <div className="scroll-x">
            <table className="tbl" style={{ minWidth: 640 }}>
              <thead><tr><th>Mở lúc</th><th>Chuyên gia</th><th>Mã</th><th>Hướng</th><th className="r">Vào</th><th className="r">SL</th><th className="r">TP</th><th>Trạng thái</th></tr></thead>
              <tbody>
                {d.items.map((s, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap text-muted">{dateTime(s.opened_at)}</td>
                    <td>{s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="no-underline hover:text-accent">{name.get(s.expert_id) || s.expert_id}</a> : name.get(s.expert_id) || s.expert_id}</td>
                    <td><b>{symbolLabel(s.symbol)}</b></td>
                    <td><Chip tone={SIDE[s.side]?.[1]}>{SIDE[s.side]?.[0] || s.side}</Chip></td>
                    <td className="r num">{s.entry != null ? price(s.symbol, s.entry) : "—"}</td>
                    <td className="r num text-muted">{s.sl ? price(s.symbol, s.sl) : "—"}</td>
                    <td className="r num text-muted">{s.tp ? price(s.symbol, s.tp) : "—"}</td>
                    <td><Chip tone={s.status === "open" ? "accent" : ""}>{s.status === "open" ? "Đang mở" : "Đã đóng"}</Chip></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="pt-2"><LatestFresh items={d.items} tsKey="opened_at" label="Tín hiệu mới nhất" {...FRESH.experts} /></div>
          </div>
        )}
      </Async>
    </>
  );
}

function Positions_({ experts }) {
  const q = usePositions({});
  const name = useMemo(() => new Map((experts || []).map((e) => [e.expert_id, e.display_name || e.expert_id])), [experts]);
  return (
    <Async q={q} empty="Chưa có vị thế công khai." hint="Vị thế công khai của chuyên gia và tổ chức." rows={5}>
      {(d) => (
        <div className="scroll-x">
          <table className="tbl" style={{ minWidth: 560 }}>
            <thead><tr><th>Cập nhật</th><th>Chuyên gia / quỹ</th><th>Mã</th><th className="r">Vị thế ròng</th><th className="r">Giá vốn TB</th></tr></thead>
            <tbody>
              {d.items.map((p, i) => (
                <tr key={i}>
                  <td className="whitespace-nowrap text-muted">{dateTime(p.as_of)}</td>
                  <td>{expertLabel(name.get(p.expert_id) || p.expert_id)}</td>
                  <td><b>{symbolLabel(p.symbol)}</b></td>
                  <td className={cn("r num", p.net_volume > 0 ? "up" : p.net_volume < 0 ? "down" : "")}>{p.net_volume == null ? "—" : `${p.net_volume > 0 ? "+" : ""}${p.net_volume.toLocaleString("en-US")}`}</td>
                  <td className="r num text-muted">{p.avg_price != null ? price(p.symbol, p.avg_price) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pt-2"><LatestFresh items={d.items} tsKey="as_of" label="Vị thế cập nhật mới nhất" {...FRESH.experts} /></div>
        </div>
      )}
    </Async>
  );
}

function Consensus_({ experts }) {
  const s = useSignals({ status: "open" });
  const p = usePositions({});
  const rows = useMemo(() => consensus(s.data?.items, p.data?.items, experts), [s.data, p.data, experts]);
  const q = { isPending: s.isPending || p.isPending, isError: s.isError || p.isError, error: s.error || p.error, refetch: () => { s.refetch(); p.refetch(); }, data: rows };
  return (
    <Async q={q} empty="Chưa đủ dữ liệu để tính đồng thuận." hint="Cần ít nhất một tín hiệu đang mở hoặc vị thế công khai." rows={4}>
      {(list) => (
        <>
          <p className="mt-0 text-muted text-[12.5px] max-w-[80ch]">Điểm nghiêng = (tổng trọng số MUA − BÁN) / tổng, trọng số là điểm uy tín của từng chuyên gia. Chỉ phản ánh <b>những gì các chuyên gia công khai</b>, không dự báo giá.</p>
          <div className="scroll-x">
            <table className="tbl" style={{ minWidth: 560 }}>
              <thead><tr><th>Mã</th><th className="r">Mua</th><th className="r">Bán</th><th>Nghiêng</th><th className="r" title="Số vị thế ròng dương − âm trong COT/13F…">Vị thế ròng</th></tr></thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.symbol}>
                    <td><b>{symbolLabel(r.symbol)}</b></td>
                    <td className="r num up">{r.buy}</td>
                    <td className="r num down">{r.sell}</td>
                    <td style={{ minWidth: 170 }}>
                      <div className="relative h-[8px] rounded bg-line" role="img" aria-label={`Điểm nghiêng ${(r.score * 100).toFixed(0)} phần trăm, ${r.score > 0 ? "nghiêng mua" : r.score < 0 ? "nghiêng bán" : "trung tính"}`}>
                        <div className="absolute inset-y-0 left-1/2 w-px bg-line2" />
                        <div className="absolute inset-y-0 rounded" style={{ background: r.score >= 0 ? "var(--up)" : "var(--down)", left: r.score >= 0 ? "50%" : `${50 + r.score * 50}%`, width: `${Math.abs(r.score) * 50}%` }} />
                      </div>
                    </td>
                    <td className={cn("r num", r.posNet > 0 ? "up" : r.posNet < 0 ? "down" : "text-muted")}>{r.posN ? (r.posNet > 0 ? "+" : "") + r.posNet : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Async>
  );
}

export default function Experts() {
  const ex = useExperts();
  const experts = ex.data?.items;
  const tabs = [["tr", "Xếp hạng & track record"], ["cg", "Danh sách theo dõi"], ["tin", "Tín hiệu"], ["vt", "Vị thế"], ["dt", "Đồng thuận"]];
  return (
    <>
      <PageHead title="Chuyên gia uy tín" sub="Theo dõi lệnh và ý kiến công khai của chuyên gia đủ chuẩn. Chỉ tổng hợp dữ liệu, không đặt lệnh." />
      <FixedNote />
      <Panel icon={Users} pad={false} fill bodyClass="flex flex-col">
        <Tabs.Root defaultValue="tr" className="flex flex-col flex-1 min-h-0">
          <Tabs.List className="flex gap-1 p-2 border-b border-line overflow-x-auto shrink-0" aria-label="Nhóm dữ liệu chuyên gia">
            <div className="seg">{tabs.map(([v, l]) => <Tabs.Trigger key={v} value={v}>{l}</Tabs.Trigger>)}</div>
          </Tabs.List>
          <>
            <Tabs.Content value="tr" className="p-3 scroll-y scroll-x outline-none"><TrackRecordTab /></Tabs.Content>
            <Tabs.Content value="cg" className="p-3 scroll-y scroll-x outline-none"><Experts_ /></Tabs.Content>
            <Tabs.Content value="tin" className="p-3 scroll-y scroll-x outline-none"><Signals_ experts={experts} /></Tabs.Content>
            <Tabs.Content value="vt" className="p-3 scroll-y scroll-x outline-none"><Positions_ experts={experts} /></Tabs.Content>
            <Tabs.Content value="dt" className="p-3 scroll-y scroll-x outline-none"><Consensus_ experts={experts} /></Tabs.Content>
          </>
        </Tabs.Root>
      </Panel>
    </>
  );
}
