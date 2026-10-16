// Ma trận quyền: hàng = quyền, cột = vai trò (GET roles). Mỗi ô có biểu tượng + chữ, không chỉ dùng màu.
import { Check, Minus } from "lucide-react";
import { Panel, Async } from "../../ui";
import { useRoles, ROLE_VN, PERM_VN } from "../../../lib/fleetQueries";
import { Unavailable } from "../bits";

export default function RoleMatrix() {
  const q = useRoles();
  return (
    <Panel title="Ma trận quyền theo vai trò" pad={false}>
      {q.isError && q.error?.code === "unavailable" ? <div className="p-3"><Unavailable what="Ma trận quyền" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /></div> : (
        <Async q={q} rows={5} what="ma trận quyền" isEmpty={(d) => !d?.items?.length} empty="Chưa có dữ liệu vai trò.">
          {(d) => {
            const roles = d.items;
            const perms = roles.find((r) => r.all_perms?.length)?.all_perms || [];
            const has = (r, p) => (r.perms || []).includes("*") || (r.perms || []).includes(p);
            return (
              <div className="fl-tablewrap">
                <table className="fl-tbl [&_tbody_tr]:cursor-default" aria-label="Ma trận quyền">
                  <thead>
                    <tr>
                      <th scope="col">Quyền</th>
                      {roles.map((r) => <th key={r.role} scope="col" title={r.label}>{ROLE_VN[r.role] || r.role}{(r.perms || []).includes("*") ? " *" : ""}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {perms.map((p) => (
                      <tr key={p}>
                        <td><span className="font-medium">{PERM_VN[p] || p}</span><span className="c-sub num">{p}</span></td>
                        {roles.map((r) => {
                          const on = has(r, p);
                          return <td key={r.role}><span className={`inline-flex items-center gap-1 text-[12px] ${on ? "text-up" : "text-muted"}`}>{on ? <Check size={13} aria-hidden="true" /> : <Minus size={13} aria-hidden="true" />}{on ? "Có" : "Không"}</span></td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="m-0 px-3 py-2 text-[11.5px] text-muted">Dấu * = tất cả quyền (kể cả quyền thêm sau). Mặc định TỪ CHỐI: quyền không liệt kê là không có. Phạm vi dữ liệu của hỗ trợ/phân tích tính riêng theo nhóm được giao.</p>
              </div>
            );
          }}
        </Async>
      )}
    </Panel>
  );
}
