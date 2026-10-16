// Danh sách nhân sự phụ + thao tác (sửa, đình chỉ/kích hoạt, thu hồi phiên). Mọi thao tác ghi cần master đã bật TOTP.
import { useState } from "react";
import { CheckCircle2, ShieldCheck, ShieldOff, UserPlus, XOctagon, Pencil, Ban, Play, LogOut } from "lucide-react";
import { Panel, Async } from "../../ui";
import { fpost } from "../../../lib/fleetApi";
import { useStaff, useFleetMut, usePerm, ROLE_VN } from "../../../lib/fleetQueries";
import { toast } from "../../../ux/bus";
import { Pill, Unavailable, GBtn, PRIMARY, ErrLine, ago, fmtDTfull } from "../bits";
import { CreateStaff, EditStaff } from "./StaffForm";
import Confirm from "./Confirm";

const ACT = {
  suspend: { label: "Đình chỉ", icon: Ban, title: "Đình chỉ nhân sự", danger: true, done: "Đã đình chỉ", body: (n) => <>Đình chỉ <b>{n}</b>? Người này sẽ bị đăng xuất và không đăng nhập được cho đến khi bạn kích hoạt lại.</> },
  activate: { label: "Kích hoạt", icon: Play, title: "Kích hoạt lại nhân sự", done: "Đã kích hoạt", body: (n) => <>Cho phép <b>{n}</b> đăng nhập lại?</> },
  "revoke-sessions": { label: "Thu hồi phiên", icon: LogOut, title: "Thu hồi mọi phiên", done: "Đã thu hồi phiên", body: (n) => <>Đăng xuất <b>{n}</b> khỏi mọi thiết bị? Họ vẫn có thể đăng nhập lại bằng mật khẩu.</> },
};

const nameOf = (s) => (s.login_key || "").replace(/^master:/, "");
const gname = (g) => (g && typeof g === "object" ? g.name || g.id : g);

function ScopeCell({ s }) {
  if (s.role === "master") return <Pill tone="info">Toàn bộ tài khoản</Pill>;
  if (s.role === "auditor") return <span className="text-muted">Nhật ký toàn cục</span>;
  if (s.scope_all) return <Pill tone="info">Toàn bộ tài khoản</Pill>;
  const g = s.groups || [];
  if (!g.length) return <Pill tone="warn" icon={XOctagon} title="Không có nhóm nào được giao và không có phạm vi toàn bộ nên người này thấy 0 tài khoản">0 tài khoản (chưa giao nhóm)</Pill>;
  return <span className="fl-cell-chips">{g.map((x, i) => <span key={i} className="fl-tchip">{gname(x)}</span>)}</span>;
}

export default function StaffList() {
  const q = useStaff();
  const p = usePerm();
  const [creating, setCreating] = useState(false);
  const [edit, setEdit] = useState(null);
  const [act, setAct] = useState(null); // {kind, s}
  const mut = useFleetMut(({ kind, s }) => fpost(`/users/${s.user_id}/${kind}`, {}), ["staff"], {
    onSuccess: (_r, v) => { toast({ tone: "ok", title: ACT[v.kind].done, body: nameOf(v.s) }); setAct(null); },
  });
  const why = p.reason(undefined, { master: true });
  const rows = q.data?.items || [];
  return (
    <Panel title="Nhân sự & quản trị viên" pad={false} right={<GBtn master className={PRIMARY} onClick={() => setCreating(true)}><UserPlus size={13} aria-hidden="true" />Tạo nhân sự</GBtn>}>
      {q.isError && q.error?.code === "totp_required" ? <div className="p-3"><ErrLine error={q.error} /></div>
        : q.isError && q.error?.code === "unavailable" ? <div className="p-3"><Unavailable what="Danh sách nhân sự" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /></div>
        : (
          <Async q={q} variant="table" cols={6} what="danh sách nhân sự" isEmpty={() => !rows.length} empty="Chưa có nhân sự phụ nào." hint="Bấm “Tạo nhân sự” để thêm người hỗ trợ, phân tích hoặc kiểm toán — mỗi người chỉ thấy đúng phần được giao.">
            {() => (
              <div className="fl-tablewrap">
                <table className="fl-tbl [&_tbody_tr]:cursor-default" aria-label="Nhân sự phụ">
                  <thead><tr><th scope="col">Nhân sự</th><th scope="col">Vai trò</th><th scope="col">Trạng thái</th><th scope="col">TOTP</th><th scope="col">Phạm vi</th><th scope="col">Đăng nhập cuối</th><th scope="col"><span className="fl-sr">Thao tác</span></th></tr></thead>
                  <tbody>
                    {rows.map((s) => {
                      const on = s.status === "active";
                      const isMaster = s.role === "master";
                      const self = s.user_id === p.me?.user_id;
                      return (
                        <tr key={s.user_id}>
                          <td><span className="font-medium">{s.display_name || nameOf(s)}</span><span className="c-sub num">{nameOf(s)}</span></td>
                          <td>{ROLE_VN[s.role] || s.role}</td>
                          <td>{on ? <Pill tone="ok" icon={CheckCircle2}>Hoạt động</Pill> : <Pill tone="bad" icon={Ban}>Đình chỉ</Pill>}</td>
                          <td>{s.totp_enabled ? <Pill tone="ok" icon={ShieldCheck}>Đã bật</Pill> : <Pill tone="mute" icon={ShieldOff}>Chưa bật</Pill>}</td>
                          <td><ScopeCell s={s} /></td>
                          <td title={fmtDTfull(s.last_login_at)}>{s.last_login_at ? ago(s.last_login_at) : <span className="text-muted">Chưa đăng nhập</span>}</td>
                          <td>
                            <div className="flex flex-wrap gap-1 justify-end">
                              <GBtn master disabled={isMaster} title={isMaster ? "Không sửa vai trò master tại đây" : undefined} className="!h-7 !px-2 text-[11.5px]" onClick={() => setEdit(s)} aria-label={`Sửa ${nameOf(s)}`}><Pencil size={12} aria-hidden="true" />Sửa</GBtn>
                              <GBtn master disabled={self} title={self ? "Không thể đình chỉ chính mình" : undefined} className="!h-7 !px-2 text-[11.5px]" onClick={() => setAct({ kind: on ? "suspend" : "activate", s })} aria-label={`${on ? "Đình chỉ" : "Kích hoạt"} ${nameOf(s)}`}>{on ? <Ban size={12} aria-hidden="true" /> : <Play size={12} aria-hidden="true" />}{on ? "Đình chỉ" : "Kích hoạt"}</GBtn>
                              <GBtn master disabled={self} title={self ? "Dùng “Đăng xuất mọi nơi” ở trang Phiên & thiết bị" : undefined} className="!h-7 !px-2 text-[11.5px]" onClick={() => setAct({ kind: "revoke-sessions", s })} aria-label={`Thu hồi phiên của ${nameOf(s)}`}><LogOut size={12} aria-hidden="true" />Thu hồi phiên</GBtn>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {why && <p className="m-0 px-3 py-2 text-[11.5px] text-muted">Thao tác ghi bị khoá: {why}</p>}
              </div>
            )}
          </Async>
        )}
      <CreateStaff open={creating} onClose={() => setCreating(false)} />
      {edit && <EditStaff staff={edit} onClose={() => setEdit(null)} />}
      {act && <Confirm title={ACT[act.kind].title} body={ACT[act.kind].body(nameOf(act.s))} danger={ACT[act.kind].danger} confirmLabel={ACT[act.kind].label} busy={mut.isPending} error={mut.error}
        onConfirm={() => mut.mutate(act)} onClose={() => { setAct(null); mut.reset(); }} />}
    </Panel>
  );
}
