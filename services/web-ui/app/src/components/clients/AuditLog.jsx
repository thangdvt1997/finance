import { useEffect, useState } from "react";
import { ScrollText } from "lucide-react";
import { Async, Chip, Panel } from "../ui";
import { AUDIT_TONE, AUDIT_VN, isMasterActor, useAudit } from "../../lib/clientsQueries";
import { fmtDT } from "./bits";

function useDebounced(v, ms = 350) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}
const brief = (d) => {
  if (!d) return "";
  const parts = [];
  if (d.reason) parts.push(`lý do: ${d.reason}`);
  for (const [k, v] of Object.entries(d)) if (k !== "reason" && v !== "" && v != null) parts.push(`${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  return parts.join(" · ");
};

export default function AuditLog() {
  const [f, setF] = useState({ q: "", action: "", target: "", actor: "", from: "", to: "" });
  const dq = useDebounced(f);
  const filters = Object.fromEntries(Object.entries(dq).filter(([, v]) => v));
  const q = useAudit(filters);
  const items = (q.data?.pages || []).flatMap((p) => p.items || []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Panel title="Nhật ký kiểm toán" icon={ScrollText} pad={false} right={<Chip>{items.length}{q.hasNextPage ? "+" : ""} bản ghi</Chip>}>
      <form className="flex flex-wrap items-end gap-2 p-3 border-b border-line" onSubmit={(e) => e.preventDefault()} aria-label="Bộ lọc nhật ký">
        <label className="grid gap-1 text-[11.5px] text-muted flex-1 min-w-[10rem]">Tìm nhanh<input className="field" type="search" value={f.q} onChange={set("q")} placeholder="IP, lý do, tài khoản…" /></label>
        <label className="grid gap-1 text-[11.5px] text-muted">Hành động
          <select className="field" value={f.action} onChange={set("action")}><option value="">Tất cả</option>{Object.entries(AUDIT_VN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="grid gap-1 text-[11.5px] text-muted">Đối tượng<input className="field num w-[9.5rem]" value={f.target} onChange={set("target")} placeholder="mt5:123…" /></label>
        <label className="grid gap-1 text-[11.5px] text-muted">Người thực hiện<input className="field w-[8rem]" value={f.actor} onChange={set("actor")} placeholder="master / ID MT" /></label>
        <label className="grid gap-1 text-[11.5px] text-muted">Từ ngày<input className="field" type="date" value={f.from} onChange={set("from")} /></label>
        <label className="grid gap-1 text-[11.5px] text-muted">Đến ngày<input className="field" type="date" value={f.to} onChange={set("to")} /></label>
        {Object.values(f).some(Boolean) && <button type="button" className="btn" onClick={() => setF({ q: "", action: "", target: "", actor: "", from: "", to: "" })}>Xoá lọc</button>}
      </form>
      <div className="p-3 pt-2">
        <Async q={q} rows={6} isEmpty={() => !items.length} empty="Không có bản ghi khớp bộ lọc.">
          {() => (
            <>
              <div className="scroll-x -mx-3"><table className="tbl" style={{ minWidth: 760 }}>
                <thead><tr><th>Thời gian (VN)</th><th>Người thực hiện</th><th>Hành động</th><th>Đối tượng</th><th>IP</th><th>Chi tiết</th></tr></thead>
                <tbody>{items.map((e) => (
                  <tr key={e.id}>
                    <td className="num whitespace-nowrap">{fmtDT(e.ts)}</td>
                    <td>{isMasterActor(e.actor_label) ? <b>{e.actor_label}</b> : <span className="num">{e.actor_label || "—"}</span>}</td>
                    <td><Chip tone={AUDIT_TONE[e.action]}>{AUDIT_VN[e.action] || e.action}</Chip></td>
                    <td className="num"><a href={`#/khach-hang/danh-sach/${e.target}`} className="no-underline hover:underline">{e.target}</a></td>
                    <td className="num">{e.ip}</td>
                    <td className="text-muted max-w-[22rem] truncate" title={brief(e.detail)}>{brief(e.detail) || "—"}</td>
                  </tr>))}</tbody></table></div>
              {q.hasNextPage && <div className="pt-3"><button className="btn" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>{q.isFetchingNextPage ? "Đang tải…" : "Tải thêm"}</button></div>}
            </>
          )}
        </Async>
      </div>
    </Panel>
  );
}
