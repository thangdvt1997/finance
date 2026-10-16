import { ScrollText } from "lucide-react";
import { PageHead } from "../components/ui";
import { usePerm } from "../lib/fleetQueries";
import { Banner, RoNote } from "../components/fleet/bits";
import AuditTable from "../components/fleet/audit/AuditTable";
import VerifyChain from "../components/fleet/audit/VerifyChain";

export const meta = { path: "kiem-toan", label: "Nhật ký kiểm toán", group: "Quản trị đội", icon: ScrollText, roles: ["master", "auditor"], perm: "audit.read", order: 70, keywords: "audit nhật ký log kiểm toán" };

export default function AuditTrail() {
  const p = usePerm();
  return (
    <div className="fl-page">
      <PageHead title="Nhật ký kiểm toán" sub="Mọi thao tác quản trị đều được ghi lại, nối thành chuỗi băm chống chỉnh sửa. Bí mật không bao giờ được hiển thị." right={<RoNote />} />
      {!p.loading && !p.has("audit.read") ? (
        <Banner tone="bad" title="Không có quyền truy cập">Vai trò của bạn không có quyền xem nhật ký kiểm toán.</Banner>
      ) : (
        <>
          <VerifyChain />
          <AuditTable />
        </>
      )}
    </div>
  );
}
