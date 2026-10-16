// Trang "AI Trading" (master): nền gom mọi chiến lược/mô hình giao dịch AI. CHỈ ĐỌC + PAPER — không có thao tác đặt lệnh.
// API (gateway, GET): /v1/ai-trading/overview, /strategies/{id}, /lab, /arena, /ledger.csv?strategy=<id>. Hợp đồng: docs/handoff/AI_TRADING_status.md.
// Trung thực: kịch bản KB-1..4 backtest KHÔNG có edge — hiển thị kết quả thật, không làm đẹp.
import { useMemo, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { Bot, Brain, Download, FlaskConical, Gauge, Gavel, LineChart, ShieldAlert, Trophy, TriangleAlert } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg, Stat, cn } from "../components/ui";
import { DataTable } from "../components/table";
import { EmptyState } from "../components/ux/States";
import { api } from "../lib/api";
import Classroom from "../components/classroom/Classroom";
import MethodsPage from "../components/classroom/MethodsPage";
import { ScenarioFlow, TeachPanel } from "../components/ai/TeachScenario";
import { ArenaPanel, EN_D1, RiskPanel } from "../components/aitrading/D1Panels";
import { AnalystPanel, ConsensusPanel, EN_C2, RegimePanel } from "../components/aitrading/C2Panels";

export const meta = {
  path: "ai-trading", label: "AI Trading", group: "Thị trường", icon: Bot, order: 64, roles: ["master"],
  keywords: "ai trading chien luoc mo hinh meta labeling regime llm rl arena paper lab backtest edge phap ly",
};

// ---------- i18n gọn (vi mặc định, en tuỳ chọn; nhớ trong localStorage) ----------
const LKEY = "ts-aitrading-lang";
const readLang = () => { try { return localStorage.getItem(LKEY) === "en" ? "en" : "vi"; } catch { return "vi"; } };
const EN = {
  "Tổng quan": "Overview", "AI Training Class": "AI Training Class", "Phương pháp": "Methods", "Kịch bản nến & sóng": "Candle & wave scenarios", "Mô hình AI": "AI models", "Rủi ro & guardrail": "Risk & guardrails", "Lab": "Lab", "Pháp lý": "Legal",
  "Nghiên cứu": "Research", "Paper": "Paper", "Tạm dừng": "Paused",
  "Không có edge": "No edge", "Chưa chứng minh": "Unproven", "Có edge (cần kiểm chứng)": "Edge (needs verification)",
  "Kỳ vọng": "Expectancy", "p so với ngẫu nhiên": "p vs random", "Số lệnh": "Trades", "Chưa có": "n/a",
  "Cảnh báo": "Warnings", "Bảng xếp hạng paper (arena)": "Paper leaderboard (arena)", "Chưa có dữ liệu arena.": "No arena data yet.",
  "Chưa có chiến lược nào.": "No strategies yet.", "Dịch vụ AI Trading chưa sẵn sàng": "AI Trading service is not ready",
  "Phần phụ trợ chưa được bật hoặc đang khởi động. Trang sẽ tự tải lại.": "The backend is not enabled or is starting. The page reloads automatically.",
  "Chiến lược": "Strategy", "Tổng R": "Total R", "Từ": "Since", "Cập nhật": "Updated",
  "Chỉ nghiên cứu và mô phỏng (paper). Không phải khuyến nghị đầu tư; hệ thống KHÔNG đặt lệnh thật.": "Research and simulation (paper) only. Not investment advice; the system places NO real orders.",
  "Kết quả trung thực: kịch bản Sell KB-1..KB-4 không có edge sau chi phí (walk-forward âm, test khoá âm, không hơn ngẫu nhiên). Trang này hiển thị kết quả thật, không làm đẹp.": "Honest result: Sell scenarios KB-1..KB-4 show no edge after costs (negative walk-forward, negative locked test, not better than random). This page shows real results without embellishment.",
  "Chọn chiến lược": "Pick a strategy", "Kết quả backtest": "Backtest result", "Forward paper": "Forward paper", "Đồ thị": "Charts", "Ví dụ thắng/thua": "Win/loss examples",
  "Tải sổ lệnh CSV": "Download ledger CSV", "Mở trang Kịch bản (tín hiệu live)": "Open Scenarios page (live signals)", "Khoảng tin cậy 95%": "95% CI", "Sụt vốn tối đa": "Max drawdown",
  "Chia dữ liệu": "Splits", "Phát triển": "Dev", "Kiểm định": "Validation", "Test khoá": "Locked test", "Ghi chú trung thực": "Honesty note",
  "Chưa có chi tiết.": "No details yet.", "Chưa có ảnh/đồ thị.": "No charts yet.", "Chưa có ví dụ.": "No examples yet.", "Thắng": "Win", "Thua": "Loss",
  "Học máy (meta-labeling)": "Machine learning (meta-labeling)", "Phát hiện regime": "Regime detection", "LLM phân tích": "LLM analyst", "Đồng thuận & chuyên gia": "Consensus & experts", "Học tăng cường (nghiên cứu)": "Reinforcement learning (research)",
  "Lọc tín hiệu pattern bằng mô hình nhỏ (GBM/logistic), walk-forward + purged CV; báo cáo trung thực dù âm.": "Filter pattern signals with a small model (GBM/logistic), walk-forward + purged CV; honest report even if negative.",
  "Phân loại trạng thái thị trường (HMM/clustering) làm đặc trưng và bộ lọc.": "Classify market state (HMM/clustering) as features and filters.",
  "Tóm tắt bối cảnh từ tin/lịch/vị thế/kỹ thuật, có trích dẫn và hậu kiểm tất định; chạy cục bộ, không có công cụ/URL, không ra lệnh.": "Summarises context from news/calendar/positioning/technicals with citations and deterministic post-checks; local, no tools/URLs, never issues orders.",
  "Đồng thuận chuyên gia + track-record làm bộ lọc/đặc trưng; xếp hạng độ tin cậy.": "Expert consensus + track-record as filter/feature; reliability ranking.",
  "Chỉ trong môi trường mô phỏng paper với chi phí thật; khảo sát + prototype nhỏ.": "Only in a paper simulation with real costs; survey + small prototype.",
  "Kế hoạch (chưa triển khai)": "Planned (not built)", "Mô hình": "Model", "Trạng thái": "Status", "Không có chiến lược liên kết": "No linked strategy",
  "Quản trị rủi ro": "Risk management", "Kích thước vị thế theo ATR và % rủi ro mỗi lệnh.": "Position size by ATR and risk % per trade.", "Giới hạn lỗ ngày; vượt thì dừng paper đến hết ngày.": "Daily loss limit; once hit, paper trading stops for the day.",
  "Kill-switch: một công tắc dừng toàn bộ tín hiệu/paper.": "Kill-switch: one switch halts all signals/paper.", "Cửa sổ tin: không mở paper mới quanh tin mạnh.": "News window: no new paper entries around major releases.",
  "Sổ lệnh paper có hash-chain (track-record) để chứng minh không bị sửa.": "Paper ledger is hash-chained (track-record) to prove it was not altered.",
  "Không có đường đặt lệnh thật trong hệ thống; kiểm tĩnh trong CI.": "There is no real-order path in the system; checked statically in CI.",
  "Thí nghiệm đã chạy": "Experiments run", "Backlog ý tưởng": "Idea backlog", "Chưa có thí nghiệm.": "No experiments yet.", "Chưa có ý tưởng.": "No ideas yet.",
  "Tham số": "Params", "Snapshot": "Snapshot", "Kết quả": "Result", "Ngày": "Date", "Ý tưởng": "Idea", "Module": "Module", "Tài liệu": "Doc",
  "Ghi chú pháp lý": "Legal notes", "Hệ thống chỉ phục vụ nghiên cứu và giao dịch mô phỏng (paper), chỉ đọc (READ-ONLY).": "The system is for research and simulated (paper) trading only, read-only.",
  "Giao dịch thật chỉ được cân nhắc sau các cổng pháp lý G1-G3, có duyệt của chủ hệ thống và một control plane riêng (docs/CONTROL_PLANE_DESIGN.md).": "Real trading is considered only after legal gates G1-G3, owner approval and a dedicated control plane (docs/CONTROL_PLANE_DESIGN.md).",
  "Kết quả quá khứ/mô phỏng không đảm bảo kết quả tương lai; không phải lời khuyên đầu tư.": "Past/simulated results do not guarantee future results; not investment advice.",
  "Hiện G1-G3 CHƯA mở. Không có nút hay API đặt lệnh.": "G1-G3 are NOT open. There is no order button or API.",
  "Chưa tải được": "Could not load", "Chi tiết": "Details",
};
Object.assign(EN, EN_C2, EN_D1);
const mk = (lang) => (s) => (lang === "en" ? EN[s] ?? s : s);

const STATUS = { research: ["Nghiên cứu", "info"], paper: ["Paper", "accent"], paused: ["Tạm dừng", ""] };
const VERDICT = { no_edge: ["Không có edge", "down"], unproven: ["Chưa chứng minh", ""], edge: ["Có edge (cần kiểm chứng)", "up"] };
const MODULES = [
  ["ml", "Học máy (meta-labeling)", "Lọc tín hiệu pattern bằng mô hình nhỏ (GBM/logistic), walk-forward + purged CV; báo cáo trung thực dù âm."],
  ["regime", "Phát hiện regime", "Phân loại trạng thái thị trường (HMM/clustering) làm đặc trưng và bộ lọc."],
  ["llm", "LLM phân tích", "Tóm tắt bối cảnh từ tin/lịch/vị thế/kỹ thuật, có trích dẫn và hậu kiểm tất định; chạy cục bộ, không có công cụ/URL, không ra lệnh."],
  ["consensus", "Đồng thuận & chuyên gia", "Đồng thuận chuyên gia + track-record làm bộ lọc/đặc trưng; xếp hạng độ tin cậy."],
  ["rl", "Học tăng cường (nghiên cứu)", "Chỉ trong môi trường mô phỏng paper với chi phí thật; khảo sát + prototype nhỏ."],
];

const base = "/ai-trading";
const useAi = (key, path, params, opts = {}) => useQuery({
  queryKey: ["ai-trading", key, params], queryFn: ({ signal }) => api(`${base}${path}`, params, signal), staleTime: 30_000, refetchInterval: 60_000,
  retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500), ...opts,
});
const list = (d, k) => (Array.isArray(d) ? d : d?.[k] || []);
const rr = (v, dp = 2) => (v == null || !Number.isFinite(+v) ? "—" : `${+v > 0 ? "+" : ""}${(+v).toFixed(dp).replace(".", ",")}R`);
const pv = (v) => (v == null || !Number.isFinite(+v) ? "—" : (+v).toFixed(3).replace(".", ","));
const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const img = (u) => (u ? (/^https?:/.test(u) ? u : `/api${u.startsWith("/") ? "" : "/"}${u}`) : null);
const dt = (v) => { if (!v) return "—"; const d = new Date(v); return Number.isNaN(+d) ? String(v).slice(0, 16) : d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }); };

function Unavailable({ q, T }) {
  if (!q.isError) return null;
  const nf = q.error?.status === 404 || q.error?.status === 502 || q.error?.status === 503;
  return <EmptyState compact title={T(nf ? "Dịch vụ AI Trading chưa sẵn sàng" : "Chưa tải được")} hint={nf ? T("Phần phụ trợ chưa được bật hoặc đang khởi động. Trang sẽ tự tải lại.") : q.error?.message} />;
}

function StatusChips({ s, T }) {
  const [sl, st] = STATUS[s.status] || [s.status || "—", ""];
  const [vl, vt] = VERDICT[s.verdict] || [T("Chưa chứng minh"), ""];
  return <span className="inline-flex flex-wrap gap-1"><Chip tone={st}>{T(sl)}</Chip><Chip tone={vt}>{T(vl)}</Chip></span>;
}

function StrategyCard({ s, T, onOpen }) {
  const m = s.metrics || {};
  return (
    <article className={cn("panel panel-b grid gap-2 content-start", s.verdict === "no_edge" && "border-l-2 border-l-[var(--down)]")} aria-label={s.name}>
      <div className="flex items-start gap-2 flex-wrap">
        <h3 className="m-0 text-[14px] font-semibold min-w-0 flex-1">{s.name}</h3>
        <StatusChips s={s} T={T} />
      </div>
      {s.summary && <p className="m-0 text-[12.5px] text-muted">{s.summary}</p>}
      <div className="grid grid-cols-3 gap-2">
        <Stat label={T("Kỳ vọng")} value={rr(m.expectancy_r)} tone={tone(m.expectancy_r)} term={false} />
        <Stat label={T("p so với ngẫu nhiên")} value={pv(m.p_vs_random)} term={false} />
        <Stat label={T("Số lệnh")} value={m.trades ?? "—"} term={false} />
      </div>
      {s.warning && <div role="note" className="flex gap-2 items-start text-[12.5px] text-down"><TriangleAlert size={14} className="shrink-0 mt-[2px]" aria-hidden="true" /><span>{s.warning}</span></div>}
      {onOpen && <button type="button" className="btn ghost self-start" onClick={() => onOpen(s.id)}>{T("Chi tiết")}</button>}
    </article>
  );
}

// ---------- Tab 1: Tổng quan ----------
function OverviewTab({ T, ov, onOpen }) {
  return (
    <div className="grid gap-3">
      <Async q={ov} empty={T("Chưa có chiến lược nào.")} what="ai-trading/overview" isEmpty={(d) => !list(d, "strategies").length && !list(d, "warnings").length}>
        {(d) => (
          <>
            {list(d, "warnings").length > 0 && (
              <Panel title={T("Cảnh báo")} icon={TriangleAlert}>
                <ul className="m-0 pl-4 grid gap-1 text-[13px]">{list(d, "warnings").map((w, i) => <li key={i}>{w}</li>)}</ul>
              </Panel>
            )}
            {list(d, "strategies").length === 0 ? <EmptyState compact title={T("Chưa có chiến lược nào.")} /> : (
              <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))]">
                {list(d, "strategies").map((s) => <StrategyCard key={s.id} s={s} T={T} onOpen={onOpen} />)}
              </div>
            )}
            <div className="text-[11.5px] text-faint">{T("Cập nhật")}: {dt(d.updated_at)}</div>
          </>
        )}
      </Async>
      <ArenaPanel T={T} fallback={list(ov.data, "arena")} />
    </div>
  );
}

// ---------- Tab 2: Kịch bản nến & sóng ----------
function PatternTab({ T, ov, sel, setSel }) {
  const cards = list(ov.data, "strategies").filter((s) => /pattern|kb|scenario/i.test(`${s.module} ${s.id}`));
  const id = sel && cards.some((c) => c.id === sel) ? sel : cards[0]?.id;
  const dq = useAi(`strategy:${id}`, `/strategies/${encodeURIComponent(id || "")}`, {}, { enabled: !!id });
  const d = dq.data;
  const b = d?.backtest;
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {cards.length > 1 && <Seg label={T("Chọn chiến lược")} value={id} onChange={setSel} options={cards.map((c) => ({ value: c.id, label: c.name }))} />}
        <a className="btn ghost ml-auto" href="#/kich-ban"><LineChart size={15} aria-hidden="true" /> {T("Mở trang Kịch bản (tín hiệu live)")}</a>
      </div>
      <Unavailable q={ov} T={T} />
      {!ov.isError && !cards.length && !ov.isPending && <EmptyState compact title={T("Chưa có chiến lược nào.")} />}
      {id && (
        <Async q={dq} empty={T("Chưa có chi tiết.")} what="ai-trading/strategies" isEmpty={(x) => !x}>
          {(x) => (
            <>
              <StrategyCard s={x} T={T} />
              {x.origin === "user" && <ScenarioFlow x={x} T={T} />}
              <Panel title={T("Kết quả backtest")} icon={Gauge}>
                {b ? (
                  <div className="grid gap-3">
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                      <Stat label={T("Kỳ vọng")} value={rr(b.expectancy_r)} tone={tone(b.expectancy_r)} term={false} />
                      <Stat label={T("Khoảng tin cậy 95%")} value={Array.isArray(b.ci95) ? `${rr(b.ci95[0])} … ${rr(b.ci95[1])}` : "—"} term={false} />
                      <Stat label={T("p so với ngẫu nhiên")} value={pv(b.p_vs_random)} term={false} />
                      <Stat label={T("Sụt vốn tối đa")} value={b.max_dd_r == null ? "—" : `-${Math.abs(+b.max_dd_r).toFixed(1).replace(".", ",")}R`} tone="down" term={false} />
                      <Stat label={T("Số lệnh")} value={b.trades ?? "—"} term={false} />
                    </div>
                    {b.splits && (
                      <div>
                        <div className="text-[11.5px] text-muted mb-1">{T("Chia dữ liệu")} (R/{T("Số lệnh").toLowerCase()})</div>
                        <div className="grid grid-cols-3 gap-3">
                          {[["dev", "Phát triển"], ["val", "Kiểm định"], ["test", "Test khoá"]].map(([k, l]) => {
                            const v = b.splits[k]; const e = v && typeof v === "object" ? v.expectancy_r : v;
                            return <Stat key={k} label={T(l)} value={rr(e)} tone={tone(e)} sub={v && v.trades != null ? `${v.trades}` : undefined} term={false} />;
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                ) : <EmptyState compact title={T("Chưa có chi tiết.")} />}
              </Panel>
              {x.forward_paper && (
                <Panel title={T("Forward paper")} icon={Trophy}>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {Object.entries(x.forward_paper).filter(([, v]) => typeof v !== "object").map(([k, v]) => (
                      <Stat key={k} label={k.replace(/_/g, " ")} value={typeof v === "number" ? (/_r$|^r$|pnl/.test(k) ? rr(v) : String(v)) : String(v)} term={false} />
                    ))}
                  </div>
                </Panel>
              )}
              {x.origin !== "user" && <Panel title={T("Đồ thị")} icon={LineChart}>
                {list(x, "charts").length ? (
                  <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,360px),1fr))]">
                    {list(x, "charts").map((u, i) => <a key={i} href={img(u)} target="_blank" rel="noreferrer"><img src={img(u)} alt={`${x.name} #${i + 1}`} loading="lazy" className="w-full rounded border border-line2 bg-panel2" /></a>)}
                  </div>
                ) : <EmptyState compact title={T("Chưa có ảnh/đồ thị.")} />}
              </Panel>}
              {x.origin !== "user" && <Panel title={T("Ví dụ thắng/thua")} icon={Gavel}>
                {list(x, "examples").length ? (
                  <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr))]">
                    {list(x, "examples").map((e) => (
                      <figure key={e.id} className="m-0 grid gap-1">
                        <img src={img(e.image_url)} alt={`${e.id} ${e.result}`} loading="lazy" className="w-full rounded border border-line2 bg-panel2" />
                        <figcaption className="text-[12px]"><Chip tone={/win|tp|thang|thắng/i.test(e.result) ? "up" : "down"}>{/win|tp|thang|thắng/i.test(e.result) ? T("Thắng") : T("Thua")}</Chip> <span className="text-muted">{e.id}</span></figcaption>
                      </figure>
                    ))}
                  </div>
                ) : <EmptyState compact title={T("Chưa có ví dụ.")} />}
              </Panel>}
              {x.honesty_note && <Disclaimer><b>{T("Ghi chú trung thực")}: </b>{x.honesty_note}</Disclaimer>}
              {x.origin !== "user" && <a className="btn self-start" href={`/api/v1/ai-trading/ledger.csv?strategy=${encodeURIComponent(x.id)}`} download><Download size={15} aria-hidden="true" /> {T("Tải sổ lệnh CSV")}</a>}
            </>
          )}
        </Async>
      )}
      <TeachPanel T={T} onCreated={setSel} />
    </div>
  );
}

// ---------- Tab 3: Mô hình AI ----------
function ModelsTab({ T, ov }) {
  const cards = list(ov.data, "strategies");
  return (
    <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))]">
      {MODULES.map(([mod, name, desc]) => {
        const lk = cards.filter((s) => (s.module || "").toLowerCase() === mod);
        return (
          <article key={mod} className="panel panel-b grid gap-2 content-start" aria-label={T(name)}>
            <div className="flex items-start gap-2 flex-wrap"><h3 className="m-0 text-[14px] font-semibold flex-1 min-w-0">{T(name)}</h3>{!lk.length && <Chip>{T("Kế hoạch (chưa triển khai)")}</Chip>}</div>
            <p className="m-0 text-[12.5px] text-muted">{T(desc)}</p>
            {lk.map((s) => (
              <div key={s.id} className="grid gap-1 border-t border-line2 pt-2">
                <div className="flex gap-2 flex-wrap items-center"><b className="text-[13px]">{s.name}</b><StatusChips s={s} T={T} /></div>
                <div className="text-[12px] num">{T("Kỳ vọng")}: {rr(s.metrics?.expectancy_r)} · p {pv(s.metrics?.p_vs_random)} · {s.metrics?.trades ?? "—"}</div>
                {s.warning && <div className="text-[12px] text-down">{s.warning}</div>}
              </div>
            ))}
          </article>
        );
      })}
      <div className="grid gap-3 [grid-column:1/-1]">
        <RegimePanel T={T} master />
        <ConsensusPanel T={T} master />
        <AnalystPanel T={T} symbols={["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40"]} />
      </div>
    </div>
  );
}

// ---------- Tab 4: Rủi ro & guardrail ----------
function RiskTab({ T }) {
  const rows = ["Không có đường đặt lệnh thật trong hệ thống; kiểm tĩnh trong CI.", "Guardrail áp dụng cho sổ paper: cỡ vị thế theo % rủi ro/khoảng dừng, giới hạn lỗ ngày, cửa sổ tin, kill-switch."];
  return (
    <div className="grid gap-3">
      <RiskPanel T={T} />
      <Panel title={T("Quản trị rủi ro")} icon={ShieldAlert}><ul className="m-0 pl-4 grid gap-2 text-[13px]">{rows.map((r) => <li key={r}>{T(r)}</li>)}</ul></Panel>
    </div>
  );
}

// ---------- Tab 5: Lab ----------
function LabTab({ T }) {
  const q = useAi("lab", "/lab", {});
  const ex = list(q.data, "experiments"), bl = list(q.data, "backlog");
  const exCols = useMemo(() => [
    { header: "ID", accessorKey: "id" },
    { header: T("Tham số"), accessorKey: "params", enableSorting: false, cell: (c) => <code className="text-[11.5px] break-all">{typeof c.getValue() === "object" ? JSON.stringify(c.getValue()) : String(c.getValue() ?? "—")}</code> },
    { header: T("Snapshot"), accessorKey: "snapshot_sha", cell: (c) => <code className="text-[11.5px]">{String(c.getValue() || "—").slice(0, 10)}</code> },
    { header: T("Kết quả"), accessorKey: "result", cell: (c) => <span className="text-[12.5px]">{typeof c.getValue() === "object" ? JSON.stringify(c.getValue()) : String(c.getValue() ?? "—")}</span> },
    { header: T("Ngày"), accessorKey: "date", cell: (c) => dt(c.getValue()) },
  ], [T]);
  const blCols = useMemo(() => [
    { header: T("Ý tưởng"), accessorKey: "idea" },
    { header: T("Module"), accessorKey: "module" },
    { header: T("Trạng thái"), accessorKey: "status", cell: (c) => <Chip>{String(c.getValue() ?? "—")}</Chip> },
    { header: T("Tài liệu"), accessorKey: "doc", enableSorting: false, cell: (c) => <span className="text-[12px] text-muted break-all">{c.getValue() || "—"}</span> },
  ], [T]);
  if (q.isError) return <Unavailable q={q} T={T} />;
  return (
    <div className="grid gap-3">
      <Panel title={T("Thí nghiệm đã chạy")} icon={FlaskConical}>
        <Async q={q} variant="table" empty={T("Chưa có thí nghiệm.")} isEmpty={() => !ex.length}>{() => <DataTable data={ex} columns={exCols} minWidth={640} getRowId={(r) => String(r.id)} />}</Async>
      </Panel>
      <Panel title={T("Backlog ý tưởng")} icon={Brain}>
        {q.isPending ? null : bl.length ? <DataTable data={bl} columns={blCols} minWidth={560} getRowId={(r) => String(r.id)} /> : <EmptyState compact title={T("Chưa có ý tưởng.")} />}
      </Panel>
    </div>
  );
}

// ---------- Tab 6: Pháp lý ----------
function LegalTab({ T }) {
  const rows = ["Hệ thống chỉ phục vụ nghiên cứu và giao dịch mô phỏng (paper), chỉ đọc (READ-ONLY).", "Giao dịch thật chỉ được cân nhắc sau các cổng pháp lý G1-G3, có duyệt của chủ hệ thống và một control plane riêng (docs/CONTROL_PLANE_DESIGN.md).", "Kết quả quá khứ/mô phỏng không đảm bảo kết quả tương lai; không phải lời khuyên đầu tư.", "Hiện G1-G3 CHƯA mở. Không có nút hay API đặt lệnh."];
  return <Panel title={T("Ghi chú pháp lý")} icon={Gavel}><ul className="m-0 pl-4 grid gap-2 text-[13px]">{rows.map((r) => <li key={r}>{T(r)}</li>)}</ul></Panel>;
}

const TABS = [["overview", "Tổng quan"], ["pattern", "Kịch bản nến & sóng"], ["class", "AI Training Class"], ["methods", "Phương pháp"], ["models", "Mô hình AI"], ["risk", "Rủi ro & guardrail"], ["lab", "Lab"], ["legal", "Pháp lý"]];

export default function AiTrading() {
  const [lang, setLang] = useState(readLang);
  const T = useMemo(() => mk(lang), [lang]);
  const [tab, setTab] = useState(() => { try { return sessionStorage.getItem("ai.tab") || "overview"; } catch { return "overview"; } });
  const [sel, setSel] = useState(null);
  const ov = useAi("overview", "/overview", {});
  const go = (t) => { setTab(t); try { sessionStorage.setItem("ai.tab", t); } catch { /* bỏ */ } };
  const open = (id) => { setSel(id); go("pattern"); };
  const chLang = (l) => { setLang(l); try { localStorage.setItem(LKEY, l); } catch { /* bỏ */ } };
  return (
    <div className="grid gap-3 ai-trading">
      <PageHead title="AI Trading" sub={T("Chỉ nghiên cứu và mô phỏng (paper). Không phải khuyến nghị đầu tư; hệ thống KHÔNG đặt lệnh thật.")}
        right={<Seg label="Language" value={lang} onChange={chLang} options={[{ value: "vi", label: "VI" }, { value: "en", label: "EN" }]} />} />
      {tab !== "class" && tab !== "methods" && <Disclaimer>{T("Kết quả trung thực: kịch bản Sell KB-1..KB-4 không có edge sau chi phí (walk-forward âm, test khoá âm, không hơn ngẫu nhiên). Trang này hiển thị kết quả thật, không làm đẹp.")}</Disclaimer>}
      <Tabs.Root value={tab} onValueChange={go} className="grid gap-3">
        <Tabs.List className="flex gap-1 overflow-x-auto border-b border-line2" aria-label="AI Trading">
          {TABS.map(([v, l]) => (
            <Tabs.Trigger key={v} value={v} className={cn("px-3 py-2 text-[13px] whitespace-nowrap shrink-0 border-b-2 border-transparent text-muted", "data-[state=active]:text-text data-[state=active]:border-[var(--accent)] data-[state=active]:font-semibold")}>{T(l)}</Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="overview">{ov.isError ? <Unavailable q={ov} T={T} /> : <OverviewTab T={T} ov={ov} onOpen={open} />}</Tabs.Content>
        <Tabs.Content value="pattern"><PatternTab T={T} ov={ov} sel={sel} setSel={setSel} /></Tabs.Content>
        <Tabs.Content value="class">{tab === "class" && <Classroom lang={lang} />}</Tabs.Content>
        <Tabs.Content value="methods">{tab === "methods" && <MethodsPage lang={lang} onGoRooms={() => go("class")} />}</Tabs.Content>
        <Tabs.Content value="models"><ModelsTab T={T} ov={ov} /></Tabs.Content>
        <Tabs.Content value="risk"><RiskTab T={T} /></Tabs.Content>
        <Tabs.Content value="lab"><LabTab T={T} /></Tabs.Content>
        <Tabs.Content value="legal"><LegalTab T={T} /></Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
