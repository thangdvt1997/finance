import { useState } from "react";
import { BarChart3, Flame, Grid3x3, TrendingDown, TrendingUp, Waves } from "lucide-react";
import { Async, Chip, Panel, Seg, cn } from "../ui";
import { DataTable } from "../table";
import { EChart, css } from "../charts";
import Heatmap from "./Heatmap";
import { BreadthBar, Code, MoversTable, Note, Pct } from "./vnbits";
import { UNIVERSES, bil, pc, tone, useVnHeatmap, useVnLimits, useVnLiquidity, useVnMovers, vnd } from "../../lib/vn";

const UniSelect = ({ value, onChange, list }) => (
  <select className="field" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Nhóm mã">
    {UNIVERSES.filter(([k]) => !list || list.includes(k)).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
  </select>
);

function LiquidityChart({ days }) {
  const build = () => ({
    animation: false, grid: { left: 46, right: 8, top: 10, bottom: 22 },
    tooltip: { trigger: "axis", confine: true, backgroundColor: css("--panel"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
      formatter: (ps) => `${ps[0].axisValue}<br/>Khớp lệnh: <b>${bil(ps[0].value)}</b>` },
    xAxis: { type: "category", data: days.map((d) => String(d.d).slice(5)), axisLabel: { color: css("--muted"), fontSize: 10, interval: "auto" }, axisLine: { lineStyle: { color: css("--line2") } }, axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { color: css("--muted"), fontSize: 10, formatter: (v) => `${Math.round(v / 1e12)}k` }, splitLine: { lineStyle: { color: css("--line") } } },
    series: [{ type: "bar", data: days.map((d, i) => ({ value: d.value, itemStyle: { color: i === days.length - 1 ? css("--accent") : css("--line2"), borderRadius: [3, 3, 0, 0] } })), barMaxWidth: 16 }],
  });
  return <EChart build={build} deps={[days]} height={180} label="GTGD khớp lệnh theo ngày (nghìn tỷ đồng)" />;
}

export function OverviewTab({ ov }) {
  const liq = useVnLiquidity({ n: 30 });
  const movG = useVnMovers({ by: "gainers", universe: "vn100", n: 6, min_value: 5e9 });
  const movL = useVnMovers({ by: "losers", universe: "vn100", n: 6, min_value: 5e9 });
  const b = ov.breadth, l = ov.liquidity, f = ov.foreign;
  const fAll = f.totals?.ALL;
  return (
    <div className="grid gap-3">
      <div className="vn-2">
        <Panel title="Độ rộng thị trường" icon={BarChart3} right={<span className="text-[11.5px] text-muted">đếm từ giá từng mã (cổ phiếu)</span>}>
          <div className="grid gap-4">
            <BreadthBar label="Toàn thị trường" b={b.ALL} />
            <BreadthBar label="HOSE" b={b.HOSE} /><BreadthBar label="HNX" b={b.HNX} /><BreadthBar label="UPCoM" b={b.UPCOM} />
          </div>
        </Panel>
        <Panel title="Thanh khoản" icon={Waves}
          right={l.label && <Chip className={l.ratio >= 1.05 ? "up" : l.ratio < 0.85 ? "down" : ""} title={`So với trung bình ${l.window} phiên trước`}>{l.label} · {(l.ratio * 100).toFixed(0)}% TB{l.window}</Chip>}>
          <div className="grid grid-cols-3 gap-3 mb-2">
            <div><div className="text-[11.5px] text-muted">Khớp lệnh</div><div className="num text-[17px]">{bil(l.last?.value)}</div></div>
            <div><div className="text-[11.5px] text-muted">Thoả thuận</div><div className="num text-[17px]">{bil(l.last?.pt_value)}</div></div>
            <div><div className="text-[11.5px] text-muted">TB {l.window} phiên</div><div className="num text-[17px]">{bil(l.avg_prev)}</div></div>
          </div>
          <Async q={liq} rows={3}>{(d) => <LiquidityChart days={d.days} />}</Async>
        </Panel>
      </div>
      <div className="vn-2">
        <Panel title="Khối ngoại hôm nay" icon={Waves} right={<a className="text-[12px]" href="#/chung-khoan-vn/ngoai">Chi tiết</a>}>
          <div className="grid grid-cols-3 gap-3 mb-2">
            <div><div className="text-[11.5px] text-muted">Mua</div><div className="num text-[16px]">{bil(fAll?.buy)}</div></div>
            <div><div className="text-[11.5px] text-muted">Bán</div><div className="num text-[16px]">{bil(fAll?.sell)}</div></div>
            <div><div className="text-[11.5px] text-muted">Ròng</div><div className={cn("num text-[16px]", tone(fAll?.net))}>{bil(fAll?.net, true)}</div></div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-[12.5px]">
            <div><div className="text-muted mb-1">Mua ròng nhiều</div>{f.top_buy.map((r) => <div key={r.code} className="flex justify-between"><Code code={r.code} /><span className="num up">{bil(r.f_net, true)}</span></div>)}</div>
            <div><div className="text-muted mb-1">Bán ròng nhiều</div>{f.top_sell.map((r) => <div key={r.code} className="flex justify-between"><Code code={r.code} /><span className="num down">{bil(r.f_net, true)}</span></div>)}</div>
          </div>
        </Panel>
        <Panel title="Ngành hôm nay" icon={Grid3x3} right={<a className="text-[12px]" href="#/chung-khoan-vn/heatmap">Bản đồ nhiệt</a>} scroll bodyClass="max-h-[300px]">
          <DataTable data={ov.sectors} getRowId={(r) => r.sector} minWidth={420} initialSort={[{ id: "pct_w", desc: true }]}
            columns={[
              { id: "sector", header: "Ngành", accessorKey: "sector", cell: (c) => <span className="text-[12.5px]">{c.getValue()}</span> },
              { id: "pct_w", header: "% (theo vốn hoá)", accessorKey: "pct_w", meta: { align: "r" }, cell: (c) => <Pct v={c.getValue()} /> },
              { id: "adv", header: "Tăng/Giảm", accessorFn: (r) => r.advances - r.declines, meta: { align: "r" }, cell: (c) => <span className="num text-[12px]"><span className="up">{c.row.original.advances}</span>/<span className="down">{c.row.original.declines}</span></span> },
              { id: "value", header: "GTGD", accessorKey: "value", meta: { align: "r" }, cell: (c) => <span className="num">{bil(c.getValue())}</span> },
            ]} />
        </Panel>
      </div>
      <div className="vn-2">
        <Panel title="Tăng mạnh (VN100)" icon={TrendingUp}><Async q={movG} rows={4}>{(d) => <MoversTable rows={d.rows} />}</Async></Panel>
        <Panel title="Giảm mạnh (VN100)" icon={TrendingDown}><Async q={movL} rows={4}>{(d) => <MoversTable rows={d.rows} />}</Async></Panel>
      </div>
    </div>
  );
}

export function HeatmapTab() {
  const [uni, setUni] = useState("vn100");
  const [size, setSize] = useState("marketcap");
  const q = useVnHeatmap({ universe: uni, size, per_sector: uni === "vn30" ? 30 : 18 });
  return (
    <Panel title="Bản đồ nhiệt theo ngành" icon={Grid3x3} pad={false} bodyClass="flex flex-col"
      right={<><UniSelect value={uni} onChange={setUni} list={["vn30", "vn100", "hose", "hnx", "hnx30"]} />
        <Seg label="Diện tích theo" value={size} onChange={setSize} options={[{ value: "marketcap", label: "Vốn hoá" }, { value: "value", label: "GTGD" }]} /></>}>
      <div className="p-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line">
        <div className="vn-scale"><span className="down num">−5%</span><i /><span className="up num">+5%</span></div>
        <span className="text-[11.5px] text-muted"><span className="px-ceil">▣ viền tím</span> = trần · <span className="px-floor">▣ viền xanh lơ</span> = sàn · diện tích = {size === "value" ? "giá trị giao dịch" : "vốn hoá"} · số % in trong ô</span>
      </div>
      <div className="p-2">
        <Async q={q} rows={8} isEmpty={(d) => !d?.sectors?.length} empty="Chưa có dữ liệu vốn hoá cho nhóm này." hint="Dữ liệu vốn hoá (P/E, P/B) nạp sau phiên; thử lại sau ít phút.">
          {(d) => <><Heatmap data={d} height={560} /><Note>Màu = % thay đổi so với giá tham chiếu; ngành tô theo bình quân gia quyền vốn hoá. Phân ngành theo hệ thống riêng, không phải ICB chính thức. Dữ liệu cuối ngày {d.as_of}.</Note></>}
        </Async>
      </div>
    </Panel>
  );
}

export function MoversTab() {
  const [by, setBy] = useState("gainers");
  const [uni, setUni] = useState("all");
  const q = useVnMovers({ by, universe: uni, n: 30 });
  const lim = useVnLimits({ universe: uni });
  return (
    <div className="grid gap-3">
      <Panel title="Top mã" icon={Flame}
        right={<><UniSelect value={uni} onChange={setUni} />
          <Seg label="Xếp theo" value={by} onChange={setBy} options={[{ value: "gainers", label: "Tăng" }, { value: "losers", label: "Giảm" }, { value: "volume", label: "KL" }, { value: "value", label: "GTGD" }]} /></>}>
        <Async q={q} rows={6}>{(d) => <><MoversTable rows={d.rows} />{(by === "gainers" || by === "losers") && <Note>Chỉ xét mã có GTGD khớp lệnh từ 1 tỷ đồng để loại mã thanh khoản mỏng.</Note>}</>}</Async>
      </Panel>
      <div className="vn-2">
        <Panel title="Chạm trần" icon={TrendingUp} right={<Chip className="ceil">±7% HOSE · ±10% HNX · ±15% UPCoM</Chip>} scroll bodyClass="max-h-[360px]">
          <Async q={lim} rows={3} isEmpty={(d) => !d?.ceiling?.length} empty="Không có mã nào đóng cửa ở giá trần.">{(d) => <MoversTable rows={d.ceiling} />}</Async>
        </Panel>
        <Panel title="Chạm sàn" icon={TrendingDown} scroll bodyClass="max-h-[360px]">
          <Async q={lim} rows={3} isEmpty={(d) => !d?.floor?.length} empty="Không có mã nào đóng cửa ở giá sàn.">{(d) => <MoversTable rows={d.floor} />}</Async>
        </Panel>
      </div>
    </div>
  );
}
