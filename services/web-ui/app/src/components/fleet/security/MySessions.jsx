// Phiên đăng nhập của tôi: thiết bị, IP, mốc thời gian, thu hồi từng phiên, đăng xuất mọi nơi.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Laptop, LogOut, Smartphone, XCircle } from "lucide-react";
import { Panel, Async } from "../../ui";
import { authGet, authPost } from "../../../lib/fleetApi";
import { useFleetMut } from "../../../lib/fleetQueries";
import { toast } from "../../../ux/bus";
import { Pill, Unavailable, ago, fmtDTfull } from "../bits";
import Confirm from "../staff/Confirm";

export const useMySessions = () => useQuery({ queryKey: ["fl", "my-sessions"], queryFn: () => authGet("/sessions"), retry: false, staleTime: 10_000, refetchInterval: 30_000 });
const mobile = (d) => /android|iphone|ipad|mobile/i.test(d || "");

export default function MySessions() {
  const q = useMySessions();
  const [one, setOne] = useState(null);
  const [all, setAll] = useState(false);
  const rev = useFleetMut((s) => authPost(`/sessions/${s.id}/revoke`, {}), ["my-sessions"], { onSuccess: () => { toast({ tone: "ok", title: "Đã thu hồi phiên" }); setOne(null); } });
  const out = useFleetMut(() => authPost("/logout-all", {}), ["my-sessions"], { onSuccess: () => { location.assign("/auth/login"); } });
  const items = (q.data?.items || []).filter((s) => !s.revoked);
  return (
    <Panel title="Phiên đăng nhập của tôi" pad={false} right={<button type="button" className="btn" onClick={() => setAll(true)} disabled={!items.length}><LogOut size={13} aria-hidden="true" />Đăng xuất mọi nơi</button>}>
      {q.isError && q.error?.code === "unavailable" ? <div className="p-3"><Unavailable what="Danh sách phiên" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /></div> : (
        <Async q={q} rows={3} what="danh sách phiên" isEmpty={() => !items.length} empty="Không có phiên đang hoạt động.">
          {() => (
            <ul className="fl-list p-3" aria-label="Phiên đăng nhập của tôi">
              {items.map((s) => {
                const Ic = mobile(s.device) ? Smartphone : Laptop;
                return (
                  <li key={s.id} className="fl-card" style={s.current ? { "--c": "var(--accent)" } : undefined}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Ic size={15} className="text-muted" aria-hidden="true" />
                      <b className="text-[13px]">{s.device || "Thiết bị không xác định"}</b>
                      {s.current && <Pill tone="warn">Phiên hiện tại</Pill>}
                      <button type="button" className="btn !h-7 !px-2 text-[11.5px] ml-auto" disabled={s.current} title={s.current ? "Dùng “Đăng xuất mọi nơi” để thoát phiên này" : undefined} onClick={() => setOne(s)} aria-label={`Thu hồi phiên ${s.device || ""} IP ${s.ip || ""}`}><XCircle size={12} aria-hidden="true" />Thu hồi</button>
                    </div>
                    <div className="fl-meta">
                      <span>IP <span className="num">{s.ip || "—"}</span></span>
                      <span title={fmtDTfull(s.created_at)}>Tạo {ago(s.created_at)}</span>
                      <span title={fmtDTfull(s.last_seen_at)}>Hoạt động cuối {ago(s.last_seen_at)}</span>
                      <span title={fmtDTfull(s.expires_at)}>Hết hạn {fmtDTfull(s.expires_at)}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Async>
      )}
      {one && <Confirm title="Thu hồi phiên" body={<>Thu hồi phiên trên <b>{one.device || "thiết bị này"}</b> (IP <span className="num">{one.ip || "—"}</span>)? Thiết bị đó sẽ bị đăng xuất ngay.</>} confirmLabel="Thu hồi" danger busy={rev.isPending} error={rev.error} onConfirm={() => rev.mutate(one)} onClose={() => { setOne(null); rev.reset(); }} />}
      {all && <Confirm title="Đăng xuất mọi nơi" body="Đăng xuất khỏi TẤT CẢ thiết bị, kể cả phiên bạn đang dùng." warn="Bạn sẽ bị đăng xuất ngay sau khi xác nhận và được chuyển tới trang đăng nhập." confirmLabel="Đăng xuất mọi nơi" danger busy={out.isPending} error={out.error} onConfirm={() => out.mutate()} onClose={() => { setAll(false); out.reset(); }} />}
    </Panel>
  );
}
