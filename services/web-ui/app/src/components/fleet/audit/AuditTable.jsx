// Bảng nhật ký kiểm toán: lọc hành động/đối tượng (máy chủ) + người thực hiện/khoảng ngày (trên các dòng đã tải), tải thêm, xuất CSV, xem chi tiết.
import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Download, Search, X, ShieldAlert, Eye } from "lucide-react";
import { Panel, Async } from "../../ui";
import { Dialog } from "../../dialog";
import { fget, downloadText, csvCell, csvSafe } from "../../../lib/fleetApi";
import { Pill, Unavailable, useDebounced, fmtDTfull, ago } from "../bits";
import { actionLabel, actionOptions, actionTone, redact, detailText } from "./labels";

const PAGE = 100;
const vnDay = (t) => new Date(t).toLocaleDateString("sv-SE", { timeZone: "Asia/Ho_Chi_Minh" }); // YYYY-MM-DD

export default function AuditTable() {
  const [f, setF] = useState({ action: "", actor: "", target: "", from: "", to: "" });
  const tgt = useDebounced(f.target.trim(), 400);
  const q = useInfiniteQuery({
    queryKey: ["fl", "audit-trail", f.action, tgt],
    queryFn: ({ pageParam, signal }) => fget("/audit", { limit: PAGE, action: f.action, target: tgt, before_id: pageParam }, { signal }),
    initialPageParam: undefined,
    getNextPageParam: (last) => (last?.items?.length >= PAGE ? last.items[last.items.length - 1].id : undefined),
    retry: false, staleTime: 10_000,
  });
  const all = useMemo(() => (q.data?.pages || []).flatMap((p) => p.items || []), [q.data]);
  const actor = f.actor.trim().toLowerCase();
  const rows = useMemo(() => all.filter((r) => (!actor || (r.actor_label || "").toLowerCase().includes(actor)) && (!f.from || vnDay(r.ts) >= f.from) && (!f.to || vnDay(r.ts) <= f.to)), [all, actor, f.from, f.to]);
  const [sel, setSel] = useState(null);
  const filtered = !!(f.action || f.actor || f.target || f.from || f.to);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const exportCsv = () => {
    const head = ["Thời gian (UTC+7)", "Người thực hiện", "Hành động", "Mã hành động", "Đối tượng", "IP", "Chi tiết"];
    const lines = [head.map(csvCell).join(",")].concat(rows.map((r) => [fmtDTfull(r.ts), r.actor_label, actionLabel(r.action), r.action, r.target, r.ip, detailText(r.detail)].map((v) => csvCell(csvSafe(v))).join(",")));
    downloadText(`nhat-ky-kiem-toan-${new Date().toISOString().slice(0, 10)}.csv`, lines.join("\r\n"));
  };

  return (
    <Panel title="Sự kiện" pad={false} right={<button type="button" className="btn" onClick={exportCsv} disabled={!rows.length}><Download size={13} aria-hidden="true" />Xuất CSV ({rows.length})</button>}>
      <div className="fl-bar-tools p-3 border-b border-line">
        <div className="fl-search"><Search size={14} aria-hidden="true" /><input className="field" aria-label="Lọc theo đối tượng" placeholder="Đối tượng (chính xác, vd tài khoản)" value={f.target} onChange={set("target")} /></div>
        <select className="field !w-auto" aria-label="Lọc theo hành động" value={f.action} onChange={set("action")}>
          <option value="">Mọi hành động</option>
          {actionOptions().map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <input className="field !w-40" aria-label="Lọc theo người thực hiện" placeholder="Người thực hiện" value={f.actor} onChange={set("actor")} />
        <label className="inline-flex items-center gap-1 text-[12px] text-muted">Từ<input type="date" className="field !w-auto" value={f.from} max={f.to || undefined} onChange={set("from")} /></label>
        <label className="inline-flex items-center gap-1 text-[12px] text-muted">đến<input type="date" className="field !w-auto" value={f.to} min={f.from || undefined} onChange={set("to")} /></label>
        {filtered && <button type="button" className="btn" onClick={() => setF({ action: "", actor: "", target: "", from: "", to: "" })}><X size={13} aria-hidden="true" />Xoá lọc</button>}
      </div>
      {q.isError && q.error?.code === "unavailable" ? <div className="p-3"><Unavailable what="Nhật ký kiểm toán" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /></div> : (
        <Async q={q} variant="table" cols={5} what="nhật ký kiểm toán" isEmpty={() => !all.length} empty="Chưa có sự kiện nào khớp bộ lọc.">
          {() => (
            <div className="fl-tablewrap">
              <table className="fl-tbl [&_tbody_tr]:cursor-default" aria-label="Nhật ký kiểm toán">
                <thead><tr><th scope="col">Thời gian</th><th scope="col">Người thực hiện</th><th scope="col">Hành động</th><th scope="col">Đối tượng</th><th scope="col">IP</th><th scope="col"><span className="fl-sr">Chi tiết</span></th></tr></thead>
                <tbody>
                  {rows.map((r) => {
                    const tone = actionTone(r.action);
                    return (
                      <tr key={r.id}>
                        <td className="whitespace-nowrap" title={ago(r.ts)}>{fmtDTfull(r.ts)}</td>
                        <td className="c-id">{r.actor_label || "—"}</td>
                        <td><Pill tone={tone} icon={tone === "bad" ? ShieldAlert : undefined}>{actionLabel(r.action)}</Pill></td>
                        <td className="c-id"><span className="block max-w-[16rem] truncate" title={r.target}>{r.target || "—"}</span></td>
                        <td className="c-id">{r.ip || "—"}</td>
                        <td className="r"><button type="button" className="btn !h-7 !px-2 text-[11.5px]" onClick={() => setSel(r)} aria-label={`Chi tiết sự kiện ${actionLabel(r.action)} lúc ${fmtDTfull(r.ts)}`}><Eye size={12} aria-hidden="true" />Chi tiết</button></td>
                      </tr>
                    );
                  })}
                  {!rows.length && <tr><td colSpan={6} className="text-muted text-center !py-6">Không có dòng nào khớp trong {all.length} sự kiện đã tải — bấm “Tải thêm” để xem sự kiện cũ hơn.</td></tr>}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center gap-2 p-3">
                <span className="fl-count">Hiển thị {rows.length}/{all.length} sự kiện đã tải. Lọc người thực hiện và ngày áp dụng trên các dòng đã tải.</span>
                {q.hasNextPage && <button type="button" className="btn" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>{q.isFetchingNextPage ? "Đang tải…" : "Tải thêm"}</button>}
              </div>
            </div>
          )}
        </Async>
      )}
      {sel && (
        <Dialog open onClose={() => setSel(null)} title="Chi tiết sự kiện" footer={<button type="button" className="btn" onClick={() => setSel(null)}>Đóng</button>}>
          <dl className="p-3 m-0">
            {[["Thời gian", fmtDTfull(sel.ts)], ["Người thực hiện", sel.actor_label || "—"], ["Hành động", `${actionLabel(sel.action)} (${sel.action})`], ["Đối tượng", sel.target || "—"], ["IP", sel.ip || "—"], ["Mã sự kiện", `#${sel.id}`]].map(([k, v]) => <div key={k} className="fl-kv"><dt>{k}</dt><dd className="num">{v}</dd></div>)}
          </dl>
          <div className="px-3 pb-3">
            <b className="text-[12px]">Dữ liệu kèm theo</b>
            <pre className="m-0 mt-1 p-2 rounded-md border border-line bg-panel2 text-[11.5px] overflow-auto max-h-64 whitespace-pre-wrap break-words num">{JSON.stringify(redact(sel.detail ?? {}), null, 2)}</pre>
            <p className="m-0 mt-1 text-[11.5px] text-muted">Giá trị bí mật (mật khẩu, token, mã) luôn được ẩn.</p>
          </div>
        </Dialog>
      )}
    </Panel>
  );
}
