// D1 (tab AI Trading): arena paper + guardrail rủi ro (kill-switch master, CSRF) + toàn vẹn hash-chain sổ paper.
// CHỈ nghiên cứu/paper — không có thao tác đặt lệnh. API: GET /v1/ai-trading/arena | /guardrail | /ledger/verify; POST /guardrail/killswitch.
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, OctagonX, ShieldAlert, ShieldCheck, Trophy, XCircle } from "lucide-react";
import { Chip, Panel, Stat, cn } from "../ui";
import { DataTable } from "../table";
import { EmptyState } from "../ux/States";
import { api, apiWrite } from "../../lib/api";

export const EN_D1 = {
  "Bảng xếp hạng paper (arena)": "Paper leaderboard (arena)", "Chiến lược": "Strategy", "Loại": "Type", "Kịch bản": "Scenario", "Danh mục (đối chứng)": "Portfolio (benchmark)",
  "Tổng R": "Total R", "Kỳ vọng ± CI95": "Expectancy ± CI95", "Sụt vốn tối đa": "Max drawdown", "chưa đủ mẫu": "not enough sample", "Đã xếp hạng": "Ranked",
  "Chưa có lệnh paper live nào đã đóng": "No closed live paper trades yet", "Dịch vụ quét chưa sẵn sàng": "Scanner not ready",
  "Quản trị rủi ro": "Risk management", "Kill-switch": "Kill-switch", "ĐANG BẬT — chặn mọi tín hiệu paper mới": "ON — blocking all new paper signals", "Đang tắt": "Off",
  "Bật kill-switch": "Turn kill-switch on", "Tắt kill-switch": "Turn kill-switch off", "Xác nhận bật": "Confirm", "Huỷ": "Cancel", "Chỉ master bật/tắt được.": "Only master can toggle.",
  "Lỗ ngày (UTC)": "Daily loss (UTC)", "Giới hạn lỗ ngày": "Daily loss limit", "Rủi ro mỗi lệnh": "Risk per trade", "Vốn paper danh nghĩa": "Notional paper equity",
  "Cửa sổ tin": "News window", "Đang áp dụng": "Applied", "Tắt": "Off", "Đã chặn": "Blocked", "Cho qua": "Allowed", "Lý do": "Reason", "Thời điểm": "Time",
  "Chưa chặn tín hiệu nào.": "No signal blocked yet.", "Bảng thử cỡ vị thế": "Position-size trial table", "Khoảng dừng": "Stop distance", "Cỡ (đơn vị)": "Size (units)", "Rủi ro thực": "Actual risk",
  "Toàn vẹn sổ lệnh paper": "Paper ledger integrity", "chuỗi toàn vẹn": "chain intact", "chuỗi BỊ ĐỨT": "chain BROKEN", "Số bản ghi": "Records", "Đầu chuỗi": "Chain head",
  "Có neo ngoài cơ sở dữ liệu": "Anchored outside the database", "Chưa có neo": "No anchor yet", "Nguồn phụ suy giảm": "Degraded inputs", "Chưa đọc được": "Unavailable",
  "Lý do bật/tắt (tuỳ chọn)": "Reason (optional)", "Đã lưu": "Saved",
};

const rr = (v, dp = 2) => (v == null || !Number.isFinite(+v) ? "—" : `${+v > 0 ? "+" : ""}${(+v).toFixed(dp).replace(".", ",")}`);
const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const dt = (v) => { if (!v) return "—"; const d = new Date(v); return Number.isNaN(+d) ? String(v).slice(0, 16) : d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }); };
const useGet = (key, path, opts = {}) => useQuery({ queryKey: ["ai-trading", key], queryFn: ({ signal }) => api(`/ai-trading${path}`, {}, signal), staleTime: 15_000, refetchInterval: 30_000, retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500), ...opts });

export function ArenaPanel({ T, fallback }) {
  const q = useGet("arena", "/arena");
  const d = q.data || (fallback?.length ? { items: fallback, available: true } : null);
  const items = d?.items || [];
  const cols = useMemo(() => [
    { header: "#", id: "rank", enableSorting: false, accessorFn: (r) => r.rank ?? "", cell: (c) => (c.getValue() === "" ? "—" : c.getValue()) },
    { header: T("Chiến lược"), accessorKey: "name" },
    { header: T("Loại"), id: "kind", accessorFn: (r) => r.kind, cell: (c) => <Chip tone="">{T(c.getValue() === "portfolio" ? "Danh mục (đối chứng)" : "Kịch bản")}</Chip> },
    { header: T("Tổng R"), id: "pnl", accessorFn: (r) => (r.unit === "%" ? r.pnl_pct : r.pnl_r), meta: { align: "r" }, cell: (c) => <span className={cn("num", tone(c.getValue()))}>{rr(c.getValue())}{c.row.original.unit === "%" ? "%" : "R"}</span> },
    { header: T("Số lệnh"), accessorKey: "trades", meta: { align: "r" }, cell: (c) => (c.getValue() ?? "—") },
    { header: T("Kỳ vọng ± CI95"), id: "exp", accessorFn: (r) => r.expectancy_r, meta: { align: "r" },
      cell: (c) => { const r = c.row.original; return r.expectancy_r == null ? "—" : <span className={cn("num", tone(r.expectancy_r))}>{rr(r.expectancy_r)}R{r.ci95 ? <span className="text-faint"> [{rr(r.ci95[0])}; {rr(r.ci95[1])}]</span> : null}</span>; } },
    { header: T("p so với ngẫu nhiên"), accessorKey: "p_vs_random", meta: { align: "r" }, cell: (c) => (c.getValue() == null ? "—" : (+c.getValue()).toFixed(3).replace(".", ",")) },
    { header: T("Sụt vốn tối đa"), id: "dd", accessorFn: (r) => (r.unit === "%" ? r.max_dd_pct : r.max_dd_r), meta: { align: "r" }, cell: (c) => (c.getValue() == null ? "—" : `-${(+c.getValue()).toFixed(2).replace(".", ",")}${c.row.original.unit === "%" ? "%" : "R"}`) },
    { header: "", id: "lbl", enableSorting: false, accessorFn: (r) => r.label || "", cell: (c) => (c.getValue() ? <Chip tone="">{T(c.getValue())}</Chip> : <Chip tone="accent">{T("Đã xếp hạng")}</Chip>) },
  ], [T]);
  return (
    <Panel title={T("Bảng xếp hạng paper (arena)")} icon={Trophy}>
      {q.isPending && !d ? null : !d || d.available === false ? (
        <EmptyState compact title={T("Dịch vụ quét chưa sẵn sàng")} hint={d?.note} />
      ) : (
        <div className="grid gap-2">
          {d.note && <p role="note" className="m-0 text-[12.5px] text-muted">{d.note}</p>}
          {d.total_trades === 0 && <EmptyState compact title={T("Chưa có lệnh paper live nào đã đóng")} />}
          <DataTable data={items} columns={cols} minWidth={720} getRowId={(r) => r.id} />
        </div>
      )}
    </Panel>
  );
}

function Integrity({ T, v }) {
  if (!v || v.available === false) return <Chip tone="">{T("Chưa đọc được")}</Chip>;
  const ok = v.ok === true;
  return (
    <div className="grid gap-1" aria-label={T("Toàn vẹn sổ lệnh paper")}>
      <div className="flex items-center gap-2 flex-wrap">
        {ok ? <CheckCircle2 size={16} className="text-up" aria-hidden="true" /> : <XCircle size={16} className="text-down" aria-hidden="true" />}
        <b className={ok ? "text-up" : "text-down"} data-testid="chain-status">{ok ? `✓ ${T("chuỗi toàn vẹn")}` : `✗ ${T("chuỗi BỊ ĐỨT")}`}</b>
        <Chip tone="">{v.anchored ? T("Có neo ngoài cơ sở dữ liệu") : T("Chưa có neo")}</Chip>
      </div>
      <div className="text-[12.5px] text-muted">{T("Số bản ghi")}: <span className="num">{v.n ?? 0}</span>{v.head ? <> · {T("Đầu chuỗi")}: <code className="text-[11.5px]">{String(v.head).slice(0, 12)}…</code></> : null}</div>
      {!ok && v.reason && <div className="text-[12.5px] text-down">{v.reason}{v.broken_at ? ` (#${v.broken_at})` : ""}</div>}
    </div>
  );
}

export function RiskPanel({ T }) {
  const qc = useQueryClient();
  const q = useGet("guardrail", "/guardrail");
  const [confirm, setConfirm] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const d = q.data;
  const ks = d?.kill_switch || {};
  const lim = d?.limits || {};
  const toggle = async (on) => {
    setBusy(true); setErr("");
    try {
      await apiWrite("POST", "/ai-trading/guardrail/killswitch", { on, ...(reason.trim() ? { reason: reason.trim().slice(0, 200) } : {}) });
      setConfirm(null); setReason("");
      await qc.invalidateQueries({ queryKey: ["ai-trading", "guardrail"] });
    } catch (e) { setErr(e?.message || "Lỗi"); } finally { setBusy(false); }
  };
  const blockCols = useMemo(() => [
    { header: T("Thời điểm"), accessorKey: "at", cell: (c) => dt(c.getValue()) },
    { header: "Mã", accessorKey: "symbol" }, { header: "KB", accessorKey: "pattern" },
    { header: T("Lý do"), accessorKey: "reason" },
  ], [T]);
  const szCols = useMemo(() => [
    { header: "ATR", accessorKey: "atr", meta: { align: "r" } },
    { header: "% " + T("Rủi ro mỗi lệnh"), accessorKey: "risk_pct", meta: { align: "r" } },
    { header: T("Khoảng dừng"), accessorKey: "stop_distance", meta: { align: "r" }, cell: (c) => (c.getValue() == null ? "—" : (+c.getValue()).toPrecision(4)) },
    { header: T("Cỡ (đơn vị)"), accessorKey: "units", meta: { align: "r" } },
    { header: T("Rủi ro thực"), accessorKey: "risk_amount", meta: { align: "r" } },
  ], [T]);
  if (q.isError) return <EmptyState compact title={T("Dịch vụ quét chưa sẵn sàng")} hint={q.error?.message} />;
  if (!d) return null;
  if (d.available === false) return <EmptyState compact title={T("Dịch vụ quét chưa sẵn sàng")} hint={d.reason} />;
  return (
    <div className="grid gap-3">
      <Panel title={T("Kill-switch")} icon={OctagonX}>
        <div className="grid gap-2">
          <div className="flex items-center gap-2 flex-wrap" role="status" aria-live="polite">
            <Chip tone={ks.on ? "down" : "up"}>{ks.on ? T("ĐANG BẬT — chặn mọi tín hiệu paper mới") : T("Đang tắt")}</Chip>
            {ks.on && ks.at && <span className="text-[12.5px] text-muted">{dt(ks.at)}{ks.reason ? ` · ${ks.reason}` : ""}</span>}
          </div>
          {confirm == null ? (
            <button type="button" className={cn("btn self-start", ks.on ? "ghost" : "")} onClick={() => setConfirm(!ks.on)}>{ks.on ? T("Tắt kill-switch") : T("Bật kill-switch")}</button>
          ) : (
            <div className="flex gap-2 flex-wrap items-center">
              <input className="input min-w-[200px] flex-1" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={T("Lý do bật/tắt (tuỳ chọn)")} aria-label={T("Lý do bật/tắt (tuỳ chọn)")} />
              <button type="button" className="btn" disabled={busy} onClick={() => toggle(confirm)}>{T("Xác nhận bật")}{confirm ? "" : ` (${T("Tắt")})`}</button>
              <button type="button" className="btn ghost" disabled={busy} onClick={() => { setConfirm(null); setErr(""); }}>{T("Huỷ")}</button>
            </div>
          )}
          {err && <div role="alert" className="text-[12.5px] text-down">{err}</div>}
          <p className="m-0 text-[12px] text-faint">{T("Chỉ master bật/tắt được.")}</p>
        </div>
      </Panel>
      <Panel title={T("Quản trị rủi ro")} icon={ShieldAlert}>
        <div className="grid gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Stat label={T("Lỗ ngày (UTC)")} value={d.daily_loss_r == null ? "—" : `${rr(d.daily_loss_r)}R`} tone={d.daily_blocked ? "down" : tone(d.daily_loss_r)} term={false} />
            <Stat label={T("Giới hạn lỗ ngày")} value={lim.max_daily_loss_r != null ? `-${String(lim.max_daily_loss_r).replace(".", ",")}R` : "—"} term={false} />
            <Stat label={T("Rủi ro mỗi lệnh")} value={lim.risk_pct != null ? `${String(lim.risk_pct).replace(".", ",")}%` : "—"} term={false} />
            <Stat label={T("Vốn paper danh nghĩa")} value={lim.equity ?? "—"} term={false} />
          </div>
          <div className="flex gap-2 flex-wrap text-[12.5px]">
            <Chip tone={d.enabled ? "accent" : ""}>{T("Đang áp dụng")}: {d.enabled ? "✓" : T("Tắt")}</Chip>
            <Chip tone="">{T("Cửa sổ tin")}: {lim.news_window ? "✓" : T("Tắt")}</Chip>
            <Chip tone="">{T("Đã chặn")}: {(d.counts?.kill_switch || 0) + (d.counts?.daily_loss || 0) + (d.counts?.news_window || 0)}</Chip>
            <Chip tone="">{T("Cho qua")}: {d.counts?.allowed || 0}</Chip>
          </div>
          {d.degraded?.length > 0 && <div role="note" className="text-[12.5px] text-down">{T("Nguồn phụ suy giảm")}: {d.degraded.join(", ")}</div>}
          {(d.notes || []).map((n) => <p key={n} className="m-0 text-[12.5px] text-muted">{n}</p>)}
        </div>
      </Panel>
      <Panel title={T("Đã chặn")} icon={ShieldAlert}>
        {d.recent_blocks?.length ? <DataTable data={d.recent_blocks} columns={blockCols} minWidth={520} getRowId={(r) => `${r.at}${r.symbol}${r.pattern}${r.reason}`} /> : <EmptyState compact title={T("Chưa chặn tín hiệu nào.")} />}
      </Panel>
      <Panel title={T("Bảng thử cỡ vị thế")} icon={ShieldCheck}>
        <DataTable data={d.sizing_table || []} columns={szCols} minWidth={420} getRowId={(r) => `${r.atr}-${r.risk_pct}`} />
      </Panel>
      <Panel title={T("Toàn vẹn sổ lệnh paper")} icon={ShieldCheck}><Integrity T={T} v={d.ledger} /></Panel>
    </div>
  );
}
