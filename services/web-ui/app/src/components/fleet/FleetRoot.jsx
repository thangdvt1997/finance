// Gắn MỘT lần ở App.jsx (nạp lười): banner "đang xem như khách" (đếm ngược, hết hạn tự thoát), banner TOTP bắt buộc cho master (không tắt được), trình hướng dẫn TOTP.
import { Suspense, lazy, useEffect, useState } from "react";
import { Eye, KeyRound, LogOut } from "lucide-react";
import "../../fleet.css";
import { closeTotpWizard, endViewAs, fget, normGrant, openTotpWizard, setViewAs, useTotpWizardOpen, useViewAsGrant } from "../../lib/fleetApi";
import { usePerm } from "../../lib/fleetQueries";
import { useQueryClient } from "@tanstack/react-query";

const TotpWizard = lazy(() => import("./TotpWizard"));

const mmss = (ms) => { const s = Math.max(0, Math.ceil(ms / 1000)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };

function ViewAsBanner({ grant }) {
  const qc = useQueryClient();
  const [now, setNow] = useState(Date.now());
  const left = Date.parse(grant.expires_at) - now;
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { if (Number.isFinite(left) && left <= 0) endViewAs(grant, qc); }, [left]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className={`fl-va ${left < 60_000 ? "urgent" : ""}`} role="status" aria-label="Đang xem như khách hàng">
      <Eye size={16} aria-hidden="true" />
      <span className="min-w-0"><b>ĐANG XEM NHƯ KHÁCH</b> · <span className="num">{grant.account_id}</span> · chỉ đọc — mọi thao tác ghi bị khoá · đã ghi nhật ký kiểm toán{grant.reason ? ` (lý do: ${grant.reason})` : ""}</span>
      <span className="fl-va-cd" aria-label={`Còn ${mmss(left)} phút:giây`}>{Number.isFinite(left) ? mmss(left) : "--:--"}</span>
      <a className="btn no-underline" href={`#/khach-hang/xem/${grant.account_id}`}>Mở màn hình khách</a>
      <button type="button" className="btn" onClick={() => endViewAs(grant, qc)}><LogOut size={13} aria-hidden="true" />Kết thúc</button>
    </div>
  );
}

export default function FleetRoot() {
  const p = usePerm();
  const grant = useViewAsGrant();
  const wizard = useTotpWizardOpen();
  const staff = p.role === "master" || p.role === "support" || p.role === "analyst" || p.role === "auditor";

  // nạp lại phiên xem-như-khách còn hiệu lực sau khi tải lại trang
  useEffect(() => {
    if (!staff || p.loading || !p.isMaster) return;
    let live = true;
    fget("/view-as/active").then((r) => { if (live) setViewAs(normGrant(r)); }).catch(() => {});
    return () => { live = false; };
  }, [staff, p.loading, p.isMaster]);

  return (
    <>
      {grant && <ViewAsBanner grant={grant} />}
      {p.isMaster && p.totpRequired && (
        <div className="fl-banner t-warn fl-sticky-banner" role="alert" style={{ borderRadius: 0, borderLeft: 0, borderRight: 0 }}>
          <KeyRound size={16} aria-hidden="true" />
          <div className="fl-banner-b"><b>Bật xác thực hai bước (TOTP) cho tài khoản master.</b> Thao tác nhạy cảm (hàng loạt, nhập CSV, vai trò, xem như khách) bị chặn đến khi bật.</div>
          <div className="fl-banner-a"><button type="button" className="btn" onClick={openTotpWizard}>Bật TOTP</button></div>
        </div>
      )}
      {wizard && <Suspense fallback={null}><TotpWizard open={wizard} onClose={closeTotpWizard} /></Suspense>}
    </>
  );
}
