// C2 (tab "Mô hình AI"): regime, đồng thuận chuyên gia, AI analyst (LLM cục bộ). CHỈ ĐỌC — không có thao tác đặt lệnh.
// API: GET /v1/ai-trading/regime | /consensus | /analyst?symbol= (master). Dịch (T) do trang cha truyền vào.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Bot, Users } from "lucide-react";
import { Chip, Panel } from "../ui";
import { DataTable } from "../table";
import { EmptyState } from "../ux/States";
import { api } from "../../lib/api";

export const EN_C2 = {
  "Regime thị trường": "Market regime", "Đồng thuận chuyên gia": "Expert consensus", "AI analyst (LLM cục bộ)": "AI analyst (local LLM)",
  "AI tạo, không phải lời khuyên": "AI-generated, not advice", "Mã": "Symbol", "Trạng thái": "State", "Số ngày": "Days", "Biến động năm (%)": "Annual vol (%)", "Phân vị biến động": "Vol percentile",
  "Xu hướng 20 ngày": "20-day trend", "Dữ liệu đến": "Data as of", "Báo cáo trung thực": "Honest report", "Đánh giá ngoài mẫu (master)": "Out-of-sample evaluation (master)",
  "Holdout dài": "Long holdout", "Val ngắn": "Short val", "p dự báo biến động": "p vol forecast", "Hơn đường cơ sở": "Beats baseline", "Có": "Yes", "Không": "No",
  "Chưa có dữ liệu regime.": "No regime data yet.", "Chưa có dữ liệu đồng thuận.": "No consensus data yet.", "Số nguồn": "Experts", "Nghiêng tăng": "Bullish", "Nghiêng giảm": "Bearish",
  "Net có trọng số": "Weighted net", "Đồng thuận": "Agreement", "Mức": "Level", "Tin cậy": "Confidence", "Độ tin cậy toàn hệ thống": "System-wide reliability",
  "Nguồn đủ mẫu (xếp hạng)": "Rated sources", "Mã (ví dụ EURUSD)": "Symbol (e.g. EURUSD)", "Phân tích": "Analyze", "Đang tạo bản AI…": "Generating the AI version…",
  "Bản mẫu tất định (chưa có bản AI)": "Deterministic template (no AI version)", "Do AI tạo, đã hậu kiểm tất định": "AI-written, deterministically verified", "Ý bị hậu kiểm loại": "Points rejected by checks",
  "Căn cứ (dữ liệu đầu vào)": "Evidence (inputs)", "Giải thích kịch bản": "Scenario explanation", "Bối cảnh": "Context", "Chưa tải được phân tích": "Could not load the analysis",
};

const base = "/ai-trading";
const num = (v, d = 2) => (v == null || !Number.isFinite(+v) ? "—" : (+v).toFixed(d).replace(".", ","));
const LCOL = { "Biến động thấp": "up", "Biến động vừa": "info", "Biến động cao": "down" };
const LEVEL = { consensus: ["Đồng thuận", "accent"], weak: ["Yếu", "info"], none: ["Không", ""] };

function useGet(key, path, params, opts = {}) {
  return useQuery({ queryKey: ["ai-trading", key, params], queryFn: ({ signal }) => api(`${base}${path}`, params, signal), staleTime: 30_000, retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500), ...opts });
}
const Note = ({ children }) => <p className="m-0 text-[12.5px] text-muted">{children}</p>;

export function RegimePanel({ T, master }) {
  const q = useGet("regime", "/regime", {}, { refetchInterval: 300_000 });
  const d = q.data;
  const rows = d?.symbols || [];
  const cols = useMemo(() => [
    { header: T("Mã"), accessorKey: "symbol", cell: (c) => <b>{c.getValue()}</b> },
    { header: T("Trạng thái"), id: "st", accessorFn: (r) => r.current.label, cell: (c) => <Chip tone={LCOL[c.getValue()] || ""}>{c.getValue()}</Chip> },
    { header: T("Số ngày"), id: "dd", accessorFn: (r) => r.current.days_in_state, cell: (c) => <span className="num">{c.getValue()}</span> },
    { header: T("Biến động năm (%)"), id: "av", accessorFn: (r) => r.current.ann_vol_pct, cell: (c) => <span className="num">{num(c.getValue(), 1)}</span> },
    { header: T("Phân vị biến động"), id: "vp", accessorFn: (r) => r.current.vol_percentile, cell: (c) => <span className="num">{num(c.getValue(), 0)}</span> },
    { header: T("Xu hướng 20 ngày"), id: "tr", accessorFn: (r) => r.current.trend, cell: (c) => <span className="text-[12.5px]">{c.getValue()}</span> },
    { header: T("Dữ liệu đến"), id: "as", accessorFn: (r) => r.current.as_of, cell: (c) => <span className="num text-[12px]">{c.getValue()}</span> },
  ], [T]);
  const evCols = useMemo(() => [
    { header: T("Mã"), accessorKey: "symbol" },
    { header: `${T("Holdout dài")} · ${T("p dự báo biến động")}`, id: "h", accessorFn: (r) => r.eval?.holdout?.hmm?.vol_p_vs_shifted, cell: (c) => <span className="num">{num(c.getValue(), 3)}</span> },
    { header: `${T("Holdout dài")} · ${T("Hơn đường cơ sở")}`, id: "hb", accessorFn: (r) => r.eval?.holdout && r.eval.holdout.hmm.vol_eta2 > r.eval.holdout.baseline_vol20_tercile.vol_eta2, cell: (c) => T(c.getValue() ? "Có" : "Không") },
    { header: `${T("Val ngắn")} · ${T("p dự báo biến động")}`, id: "v", accessorFn: (r) => r.eval?.val?.hmm?.vol_p_vs_shifted, cell: (c) => <span className="num">{num(c.getValue(), 3)}</span> },
    { header: `${T("Val ngắn")} · ${T("Hơn đường cơ sở")}`, id: "vb", accessorFn: (r) => r.eval?.val && r.eval.val.hmm.vol_eta2 > r.eval.val.baseline_vol20_tercile.vol_eta2, cell: (c) => T(c.getValue() ? "Có" : "Không") },
  ], [T]);
  return (
    <Panel title={T("Regime thị trường")} icon={Activity} right={<Chip tone="info">HMM · k-means</Chip>}>
      {q.isError ? <EmptyState compact title={T("Chưa tải được phân tích")} hint={q.error?.message} /> : !d ? null : !d.available || !rows.length ? <EmptyState compact title={T("Chưa có dữ liệu regime.")} /> : (
        <div className="grid gap-3">
          <Note>{d.note}</Note>
          <DataTable data={rows} columns={cols} minWidth={640} getRowId={(r) => r.symbol} />
          <div className="grid gap-1 border-t border-line2 pt-2">
            <b className="text-[13px]">{T("Báo cáo trung thực")}</b>
            <Note>{d.verdict?.summary}</Note>
            {d.missing?.length ? <Note>{d.missing.join("; ")}</Note> : null}
          </div>
          {master && rows[0]?.eval ? (
            <div className="grid gap-1 border-t border-line2 pt-2">
              <b className="text-[13px]">{T("Đánh giá ngoài mẫu (master)")}</b>
              <DataTable data={rows} columns={evCols} minWidth={640} getRowId={(r) => r.symbol} />
              <Note>{d.locks}</Note>
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  );
}

export function ConsensusPanel({ T, master }) {
  const q = useGet("consensus", "/consensus", {}, { refetchInterval: 120_000 });
  const d = q.data;
  const rows = (d?.rows || []).slice().sort((a, b) => b.n_experts - a.n_experts).slice(0, 14);
  const cols = useMemo(() => [
    { header: T("Mã"), accessorKey: "symbol", cell: (c) => <b>{c.getValue()}</b> },
    { header: T("Số nguồn"), accessorKey: "n_experts", cell: (c) => <span className="num">{c.getValue()}</span> },
    { header: T("Nghiêng tăng"), accessorKey: "bullish", cell: (c) => <span className="num up">{c.getValue()}</span> },
    { header: T("Nghiêng giảm"), accessorKey: "bearish", cell: (c) => <span className="num down">{c.getValue()}</span> },
    { header: T("Net có trọng số"), accessorKey: "net_weighted", cell: (c) => <span className="num">{num(c.getValue(), 2)}</span> },
    { header: T("Mức"), accessorKey: "level", cell: (c) => { const [l, t] = LEVEL[c.getValue()] || [c.getValue(), ""]; return <Chip tone={t}>{T(l)}</Chip>; } },
    { header: T("Tin cậy"), accessorKey: "confidence", cell: (c) => <span className="text-[12.5px]">{c.getValue()}</span> },
  ], [T]);
  return (
    <Panel title={T("Đồng thuận chuyên gia")} icon={Users}>
      {q.isError ? <EmptyState compact title={T("Chưa tải được phân tích")} hint={q.error?.message} /> : !d ? null : !rows.length ? <EmptyState compact title={T("Chưa có dữ liệu đồng thuận.")} /> : (
        <div className="grid gap-3">
          <Note>{d.note}</Note>
          <div className="flex gap-2 flex-wrap items-center"><b className="text-[13px]">{T("Độ tin cậy toàn hệ thống")}:</b><Chip tone={d.reliability?.beating_baseline ? "up" : ""}>{d.reliability?.tier}</Chip><span className="text-[12.5px] text-muted">{d.reliability?.text}</span></div>
          <DataTable data={rows} columns={cols} minWidth={560} getRowId={(r) => r.symbol} />
          {master && d.rated_experts?.length ? (
            <div className="grid gap-1 border-t border-line2 pt-2">
              <b className="text-[13px]">{T("Nguồn đủ mẫu (xếp hạng)")}</b>
              <ul className="m-0 pl-4 grid gap-1 text-[12.5px]">{d.rated_experts.map((e) => <li key={e.label}>{e.label} · n={e.n} · hit {num(e.hit_rate * 100, 1)}% · q={num(e.q_value, 2)}</li>)}</ul>
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  );
}

export function AnalystPanel({ T, symbols = [] }) {
  const [input, setInput] = useState("EURUSD");
  const [sym, setSym] = useState("EURUSD");
  const ok = /^[A-Za-z0-9][A-Za-z0-9:_.-]{0,23}$/.test(input.trim());
  const q = useGet("analyst", "/analyst", { symbol: sym }, { refetchInterval: (qq) => (qq.state.data?.llm_pending ? 8_000 : false), staleTime: 60_000 });
  const d = q.data;
  const byN = new Map((d?.context || []).map((c) => [c.n, c]));
  return (
    <Panel title={T("AI analyst (LLM cục bộ)")} icon={Bot} right={<Chip tone="accent">{T("AI tạo, không phải lời khuyên")}</Chip>}>
      <div className="grid gap-3">
        <form className="flex gap-2 flex-wrap items-center" onSubmit={(e) => { e.preventDefault(); if (ok) setSym(input.trim().toUpperCase()); }}>
          <input className="field" list="ai-an-syms" value={input} onChange={(e) => setInput(e.target.value)} placeholder={T("Mã (ví dụ EURUSD)")} aria-label={T("Mã (ví dụ EURUSD)")} maxLength={24} />
          <datalist id="ai-an-syms">{symbols.map((s) => <option key={s} value={s} />)}</datalist>
          <button type="submit" className="btn" disabled={!ok}>{T("Phân tích")}</button>
          {d && <Chip tone={d.status === "llm" ? "up" : ""}>{d.status === "llm" ? T("Do AI tạo, đã hậu kiểm tất định") : T("Bản mẫu tất định (chưa có bản AI)")}</Chip>}
          {d?.llm_pending && <span className="text-[12px] text-muted" role="status">{T("Đang tạo bản AI…")}</span>}
        </form>
        {q.isError ? <EmptyState compact title={T("Chưa tải được phân tích")} hint={q.error?.message} /> : !d ? null : (
          <div className="grid gap-3">
            <div className="text-[14px] font-semibold">{d.headline}</div>
            <ul className="m-0 pl-0 list-none grid gap-2">
              {d.points.map((p, i) => (
                <li key={i} className="grid gap-1 text-[13px]">
                  <span>{p.topic === "scenario" && <Chip tone="info" className="mr-1">{T("Giải thích kịch bản")}</Chip>}{p.text}{" "}
                    {p.cites.map((n) => <sup key={n} className="text-muted mr-0.5" title={byN.get(n)?.title}>[{n}]</sup>)}</span>
                </li>
              ))}
            </ul>
            <details>
              <summary className="cursor-pointer text-[12.5px] text-muted">{T("Căn cứ (dữ liệu đầu vào)")} · {d.context.length}</summary>
              <ol className="m-0 pl-0 list-none grid gap-1 text-[12.5px] mt-1">{d.context.map((c) => <li key={c.n}><span className="text-muted">[{c.n}]</span> {c.title}</li>)}</ol>
            </details>
            <Note>{d.disclaimer}</Note>
            {d.quality?.dropped?.length ? <Note>{T("Ý bị hậu kiểm loại")}: {d.quality.dropped.length}</Note> : null}
          </div>
        )}
      </div>
    </Panel>
  );
}
