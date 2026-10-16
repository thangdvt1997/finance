// Trang "AI Trading" (client): bản rút gọn CHỈ ĐỌC — thẻ chiến lược + cảnh báo trung thực. Không có thao tác đặt lệnh.
// API: GET /v1/ai-trading/overview (hợp đồng docs/handoff/AI_TRADING_status.md). 404/403 -> trạng thái rỗng, không lỗi đỏ.
import { useQuery } from "@tanstack/react-query";
import { Bot, TriangleAlert } from "lucide-react";
import { Async, Chip, Notice, PageHead, Panel, cn } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, f1 } from "../lib/format";
import { go } from "../lib/router";
import { t } from "../lib/i18n";

const STATUS = () => ({ research: [t("Nghiên cứu"), "info"], paper: [t("Paper"), "accent"], paused: [t("Tạm dừng"), ""] });
const VERDICT = () => ({ no_edge: [t("Không có edge"), "down"], unproven: [t("Chưa chứng minh"), ""], edge: [t("Có edge (cần kiểm chứng)"), "up"] });
const rr = (v) => (v == null || !Number.isFinite(+v) ? "—" : `${+v > 0 ? "+" : ""}${f1(+v, 2)}R`);
const list = (d, k) => (Array.isArray(d) ? d : d?.[k] || []);

function Card({ s }) {
  const [sl, st] = STATUS()[s.status] || [s.status || "—", ""];
  const [vl, vt] = VERDICT()[s.verdict] || [t("Chưa chứng minh"), ""];
  const m = s.metrics || {};
  return (
    <article className={cn("panel panel-b grid gap-2 content-start", s.verdict === "no_edge" && "border-l-2 border-l-[var(--down)]")} aria-label={s.name}>
      <div className="flex items-start gap-2 flex-wrap"><h3 className="m-0 text-[15px] font-semibold flex-1 min-w-0">{s.name}</h3><Chip tone={st}>{sl}</Chip><Chip tone={vt}>{vl}</Chip></div>
      {s.summary && <p className="m-0 text-[13px] text-muted">{s.summary}</p>}
      <dl className="m-0 grid grid-cols-3 gap-2 text-[13px]">
        <div><dt className="text-muted text-[11.5px]">{t("Kỳ vọng")}</dt><dd className="m-0 num">{rr(m.expectancy_r)}</dd></div>
        <div><dt className="text-muted text-[11.5px]">{t("p so với ngẫu nhiên")}</dt><dd className="m-0 num">{m.p_vs_random == null ? "—" : f1(+m.p_vs_random, 3)}</dd></div>
        <div><dt className="text-muted text-[11.5px]">{t("Số lệnh")}</dt><dd className="m-0 num">{m.trades ?? "—"}</dd></div>
      </dl>
      {s.warning && <div role="note" className="flex gap-2 items-start text-[12.5px] text-down"><TriangleAlert size={14} className="shrink-0 mt-[2px]" aria-hidden="true" /><span>{s.warning}</span></div>}
    </article>
  );
}

function RegimeBrief() {
  const q = useQuery({ queryKey: ["ai-trading", "regime"], queryFn: ({ signal }) => api("/ai-trading/regime", {}, signal), staleTime: 60_000, refetchInterval: 300_000,
    retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500) });
  const rows = q.data?.symbols || [];
  if (q.isError || !rows.length) return null;
  return (
    <Panel title={t("Regime thị trường")}>
      <div className="grid gap-2">
        <p className="m-0 text-[12.5px] text-muted">{q.data.note}</p>
        <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(min(100%,180px),1fr))]">
          {rows.map((r) => (
            <div key={r.symbol} className="grid gap-1 text-[13px]">
              <b>{r.symbol}</b><span>{r.current.label} · {r.current.days_in_state} {t("ngày")}</span>
              <span className="text-muted text-[12px]">{r.current.trend}</span>
            </div>
          ))}
        </div>
        <p className="m-0 text-[12px] text-faint">{q.data.verdict?.summary}</p>
      </div>
    </Panel>
  );
}

export default function AiTrading() {
  const q = useQuery({
    queryKey: ["ai-trading", "overview"], queryFn: ({ signal }) => api("/ai-trading/overview", {}, signal), staleTime: 30_000, refetchInterval: 60_000,
    retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500),
  });
  const na = q.isError && [403, 404, 502, 503].includes(q.error?.status);
  return (
    <div className="grid gap-3">
      <PageHead title={t("AI Trading")} sub={t("Chỉ nghiên cứu và mô phỏng (paper). Không phải khuyến nghị đầu tư; hệ thống không đặt lệnh.")} />
      <Notice tone="warn" icon={TriangleAlert}>{t("Kết quả trung thực: kịch bản Sell KB-1..KB-4 không có edge sau chi phí (walk-forward âm, test khoá âm, không hơn ngẫu nhiên).")}</Notice>
      {na ? <Notice tone="info" title={t("Dịch vụ chưa sẵn sàng")}>{t("Mục này chưa được bật hoặc đang khởi động. Thử lại sau.")}</Notice> : (
        <Async q={q} empty={t("Chưa có dữ liệu AI Trading.")} isEmpty={(d) => !list(d, "strategies").length && !list(d, "warnings").length}>
          {(d) => (
            <>
              {list(d, "warnings").length > 0 && (
                <Panel title={t("Cảnh báo")} icon={TriangleAlert}><ul className="m-0 pl-4 grid gap-1 text-[13px]">{list(d, "warnings").map((w, i) => <li key={i}>{w}</li>)}</ul></Panel>
              )}
              {list(d, "strategies").length === 0 ? <Notice tone="info">{t("Chưa có chiến lược nào.")}</Notice> : (
                <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))]">{list(d, "strategies").map((s) => <Card key={s.id} s={s} />)}</div>
              )}
              <RegimeBrief />
              <div className="flex items-center gap-3 text-[12px] text-faint">
                <span>{t("Cập nhật")}: {d.updated_at ? dateTime(d.updated_at) : "—"}</span>
                <button type="button" className="btn ghost" onClick={() => go("/kich-ban")}>{t("Xem kịch bản")}</button>
              </div>
            </>
          )}
        </Async>
      )}
    </div>
  );
}
