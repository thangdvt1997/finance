import { MonitorSmartphone } from "lucide-react";
import { PageHead } from "../components/ui";
import { RoNote } from "../components/fleet/bits";
import MySessions from "../components/fleet/security/MySessions";
import TotpCard from "../components/fleet/security/TotpCard";
import AllSessions from "../components/fleet/security/AllSessions";

export const meta = { path: "phien-thiet-bi", label: "Phiên & thiết bị", group: "Quản trị đội", icon: MonitorSmartphone, roles: ["master", "support", "analyst", "auditor"], order: 60, keywords: "đăng xuất totp bảo mật thiết bị" };

export default function SessionsDevices() {
  return (
    <div className="fl-page">
      <PageHead title="Phiên & thiết bị" sub="Xem các thiết bị đang đăng nhập tài khoản của bạn, thu hồi phiên lạ và bật xác thực hai bước." right={<RoNote />} />
      <TotpCard />
      <MySessions />
      <AllSessions />
    </div>
  );
}
