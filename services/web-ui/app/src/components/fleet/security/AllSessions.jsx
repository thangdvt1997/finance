// Master: phiên của mọi người. Thu hồi theo NGƯỜI (users/{id}/revoke-sessions) vì nginx chưa mở sessions/{id}/revoke.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { Panel, Async } from "../../ui";
import { fget, fpost } from "../../../lib/fleetApi";
import { useFleetMut, usePerm, ROLE_VN } from "../../../lib/fleetQueries";
import { toast } from "../../../ux/bus";
import { Unavailable, ago, fmtDTfull } from "../bits";
import Confirm from "../staff/Confirm";

export default function AllSessions() {
  const p = usePerm();
  const q = useQuery({ queryKey: ["fl", "all-sessions"], queryFn: ({ signal }) => fget("/sessions", null, { signal }), retry: false, staleTime: 10_000, enabled: p.isMaster });
  const [tgt, setTgt] = useState(null);
  const m = useFleetMut((s) => fpost(`/users/${s.user_id}/revoke-sessions`, {}), ["all-sessions", "my-sessions"], { onSuccess: () => { toast({ tone: "ok", title: "Đã thu hồi phiên của người dùng" }); setTgt(null); } });
  if (!p.isMaster) return null;
  const items = (q.data?.items || []).filter((s) => !s.revoked);
  return (
    <Panel title="Phiên của mọi người dùng" pad={false}>
      {q.isError && q.error?.code === "unavailable" ? <div className="p-3"><Unavailable what="Danh sách phiên toàn hệ thống" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /></div> : (
        <Async q={q} variant="table" cols={5} what="danh sách phiên" isEmpty={() => !items.length} empty="Không có phiên nào đang hoạt động.">
          {() => (
            <div className="fl-tablewrap">
              <table className="fl-tbl [&_tbody_tr]:cursor-default" aria-label="Phiên của mọi người dùng">
                <thead><tr><th scope="col">Người dùng</th><th scope="col">Vai trò</th><th scope="col">Thiết bị</th><th scope="col">IP</th><th scope="col">Hoạt động cuối</th><th scope="col"><span className="fl-sr">Thao tác</span></th></tr></thead>
                <tbody>
                  {items.map((s) => {
                    const mine = s.user_id === p.me?.user_id;
                    return (
                      <tr key={s.id}>
                        <td className="c-id">{s.login}{mine && <span className="text-accent"> · bạn</span>}</td>
                        <td>{ROLE_VN[s.role] || s.role}</td>
                        <td>{s.device || "—"}</td>
                        <td className="c-id">{s.ip || "—"}</td>
                        <td title={fmtDTfull(s.last_seen_at)}>{ago(s.last_seen_at)}</td>
                        <td className="r"><button type="button" className="btn !h-7 !px-2 text-[11.5px]" disabled={mine} title={mine ? "Dùng “Đăng xuất mọi nơi” ở phần phiên của tôi" : "Thu hồi mọi phiên của người này"} onClick={() => setTgt(s)} aria-label={`Thu hồi mọi phiên của ${s.login}`}><LogOut size={12} aria-hidden="true" />Thu hồi</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="m-0 px-3 py-2 text-[11.5px] text-muted">Thu hồi áp dụng cho mọi phiên của người đó (không tách từng phiên).</p>
            </div>
          )}
        </Async>
      )}
      {tgt && <Confirm title="Thu hồi mọi phiên" body={<>Đăng xuất <b>{tgt.login}</b> khỏi mọi thiết bị?</>} confirmLabel="Thu hồi" danger busy={m.isPending} error={m.error} onConfirm={() => m.mutate(tgt)} onClose={() => { setTgt(null); m.reset(); }} />}
    </Panel>
  );
}
