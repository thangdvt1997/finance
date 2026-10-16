import { ShieldCheck, KeyRound } from "lucide-react";
import { PageHead } from "../components/ui";
import { usePerm } from "../lib/fleetQueries";
import { openTotpWizard } from "../lib/fleetApi";
import { Banner, RoNote } from "../components/fleet/bits";
import RoleMatrix from "../components/fleet/staff/RoleMatrix";
import StaffList from "../components/fleet/staff/StaffList";

export const meta = { path: "vai-tro", label: "Vai trò & nhân sự", group: "Quản trị đội", icon: ShieldCheck, roles: ["master"], order: 50, keywords: "nhân sự hỗ trợ phân tích kiểm toán quyền" };

export default function Roles() {
  const p = usePerm();
  return (
    <div className="fl-page">
      <PageHead title="Vai trò & nhân sự" sub="Giao quyền theo nguyên tắc tối thiểu: mỗi nhân sự chỉ thấy đúng nhóm tài khoản được giao. Không vai trò nào có quyền đặt lệnh." right={<RoNote />} />
      {p.me?.totp_setup_required && (
        <Banner tone="warn" title="Cần bật xác thực hai bước (TOTP) để quản lý nhân sự"
          actions={<button type="button" className="btn" onClick={openTotpWizard}><KeyRound size={13} aria-hidden="true" />Bật TOTP ngay</button>}>
          Tạo/sửa/đình chỉ nhân sự là thao tác nhạy cảm — máy chủ sẽ từ chối cho đến khi tài khoản master bật TOTP.
        </Banner>
      )}
      {!p.loading && !p.isMaster ? (
        <Banner tone="bad" title="Không có quyền truy cập">Trang này chỉ dành cho tài khoản master.</Banner>
      ) : (
        <>
          <StaffList />
          <RoleMatrix />
        </>
      )}
    </div>
  );
}
