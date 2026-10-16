// Hộp thoại tạo / sửa nhân sự phụ. Tạo xong hiển thị mật khẩu MỘT lần bằng SecretPanel.
import { useState } from "react";
import { Dialog } from "../../dialog";
import { fpost, fpatch } from "../../../lib/fleetApi";
import { useFleetMut, ROLE_VN } from "../../../lib/fleetQueries";
import { toast } from "../../../ux/bus";
import { Banner, ErrLine, Field, PRIMARY, SecretPanel, useLeaveGuard } from "../bits";
import GroupPicker from "./GroupPicker";

const ROLES = [["support", "Hỗ trợ — xem đội tài khoản, sự cố, ghi chú"], ["analyst", "Phân tích — đội tài khoản, luật & tuân thủ, báo cáo"], ["auditor", "Kiểm toán — chỉ nhật ký kiểm toán"]];
const NAME_RE = /^[a-z0-9][a-z0-9_.-]{1,30}$/;
const gid = (g) => (g && typeof g === "object" ? g.id : g);

function ScopeBox({ role, scopeAll, setScopeAll, groups, setGroups }) {
  if (role === "auditor") return <Banner tone="info">Kiểm toán chỉ đọc nhật ký toàn cục — không có dữ liệu tài khoản nên không cần phạm vi.</Banner>;
  const zero = !scopeAll && groups.length === 0;
  return (
    <div className="grid gap-2">
      <label className="fl-check"><input type="checkbox" checked={scopeAll} onChange={(e) => setScopeAll(e.target.checked)} /><span>Xem toàn bộ tài khoản (bỏ qua nhóm)</span></label>
      {!scopeAll && <Field label="Nhóm được giao"><GroupPicker value={groups} onChange={setGroups} /></Field>}
      <Banner tone={zero ? "warn" : "info"} title={zero ? "Phạm vi hiện tại: 0 tài khoản" : undefined}>
        Nếu <b>không có nhóm nào được giao</b> và <b>không chọn “xem toàn bộ”</b> thì người này sẽ thấy <b>0 tài khoản</b> (mặc định từ chối).
      </Banner>
    </div>
  );
}

const FRESH = { name: "", role: "support", display: "", all: false, groups: [] };

export function CreateStaff({ open, onClose }) {
  const [f, setF] = useState(FRESH);
  const [out, setOut] = useState(null);
  const [ack, setAck] = useState(false);
  const mut = useFleetMut((b) => fpost("/staff", b), ["staff"]);
  useLeaveGuard(!!out && !ack);
  const bad = !NAME_RE.test(f.name);
  const close = () => { if (out && !ack) return; setF(FRESH); setOut(null); setAck(false); mut.reset(); onClose(); };
  const submit = (e) => {
    e.preventDefault();
    if (bad) return;
    mut.mutate(
      { name: f.name, role: f.role, ...(f.display.trim() ? { display_name: f.display.trim() } : {}), scope_all: f.role !== "auditor" && f.all, group_ids: f.role === "auditor" || f.all ? [] : f.groups },
      { onSuccess: (r) => { setOut({ name: (r?.user?.login_key || "").replace(/^master:/, "") || f.name, pw: r?.password }); toast({ tone: "ok", title: "Đã tạo nhân sự", body: f.name }); } },
    );
  };
  return (
    <Dialog open={open} onClose={close} title={out ? "Nhân sự đã tạo" : "Tạo nhân sự"} footer={out
      ? <button type="button" className={`btn ${PRIMARY}`} disabled={!ack} onClick={close}>Xong</button>
      : <><button type="button" className="btn" onClick={close}>Huỷ</button><button type="submit" form="fl-staff-create" className={`btn ${PRIMARY}`} disabled={bad || mut.isPending}>{mut.isPending ? "Đang tạo…" : "Tạo nhân sự"}</button></>}>
      {out ? (
        <div className="p-3 grid gap-2">
          <SecretPanel title="Mật khẩu khởi tạo — chỉ hiển thị MỘT lần" filename={`nhan-su-${out.name}.txt`} onAck={setAck}
            items={[{ k: "Nền tảng đăng nhập", v: "master" }, { k: "Tên đăng nhập", v: out.name }, { k: "Mật khẩu khởi tạo", v: out.pw }]} />
          <Banner tone="warn">Người dùng <b>phải đổi mật khẩu ở lần đăng nhập đầu</b>. Gửi mật khẩu qua kênh riêng, không gửi cùng tên đăng nhập.</Banner>
        </div>
      ) : (
        <form id="fl-staff-create" onSubmit={submit} className="p-3 grid gap-3">
          <div className="fl-formgrid">
            <Field label="Tên đăng nhập" htmlFor="st-name" help="Chữ thường, số, . _ - (2–31 ký tự)." error={f.name && bad ? "Tên không hợp lệ." : null}>
              <input id="st-name" className="field" value={f.name} maxLength={32} autoComplete="off" onChange={(e) => setF({ ...f, name: e.target.value.toLowerCase() })} />
            </Field>
            <Field label="Tên hiển thị" htmlFor="st-disp"><input id="st-disp" className="field" value={f.display} maxLength={80} onChange={(e) => setF({ ...f, display: e.target.value })} /></Field>
          </div>
          <Field label="Vai trò" htmlFor="st-role">
            <select id="st-role" className="field" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </Field>
          <ScopeBox role={f.role} scopeAll={f.all} setScopeAll={(v) => setF({ ...f, all: v })} groups={f.groups} setGroups={(v) => setF({ ...f, groups: v })} />
          <ErrLine error={mut.error} />
        </form>
      )}
    </Dialog>
  );
}

export function EditStaff({ staff, onClose }) {
  const s = staff;
  const [f, setF] = useState(() => ({ role: s.role, display: s.display_name || "", all: !!s.scope_all, groups: (s.groups || []).map(gid) }));
  const mut = useFleetMut((b) => fpatch(`/staff/${s.user_id}`, b), ["staff"], { onSuccess: () => { toast({ tone: "ok", title: "Đã cập nhật nhân sự" }); onClose(); } });
  const submit = (e) => { e.preventDefault(); mut.mutate({ role: f.role, display_name: f.display.trim(), scope_all: f.role !== "auditor" && f.all, group_ids: f.role === "auditor" || f.all ? [] : f.groups }); };
  return (
    <Dialog open onClose={onClose} title={`Sửa nhân sự · ${(s.login_key || "").replace(/^master:/, "")}`} footer={<><button type="button" className="btn" onClick={onClose}>Huỷ</button><button type="submit" form="fl-staff-edit" className={`btn ${PRIMARY}`} disabled={mut.isPending}>{mut.isPending ? "Đang lưu…" : "Lưu thay đổi"}</button></>}>
      <form id="fl-staff-edit" onSubmit={submit} className="p-3 grid gap-3">
        <div className="fl-formgrid">
          <Field label="Vai trò" htmlFor="se-role"><select id="se-role" className="field" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map(([v]) => <option key={v} value={v}>{ROLE_VN[v]}</option>)}</select></Field>
          <Field label="Tên hiển thị" htmlFor="se-disp"><input id="se-disp" className="field" value={f.display} maxLength={80} onChange={(e) => setF({ ...f, display: e.target.value })} /></Field>
        </div>
        <ScopeBox role={f.role} scopeAll={f.all} setScopeAll={(v) => setF({ ...f, all: v })} groups={f.groups} setGroups={(v) => setF({ ...f, groups: v })} />
        <Banner tone="warn">Đổi vai trò/phạm vi sẽ <b>thu hồi mọi phiên</b> của người này — họ phải đăng nhập lại.</Banner>
        <ErrLine error={mut.error} />
      </form>
    </Dialog>
  );
}
