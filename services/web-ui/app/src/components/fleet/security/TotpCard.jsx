// Trạng thái xác thực hai bước (TOTP) từ /auth/me + nút mở trình hướng dẫn.
import { KeyRound, ShieldCheck, ShieldAlert } from "lucide-react";
import { Panel } from "../../ui";
import { openTotpWizard } from "../../../lib/fleetApi";
import { useAuthMe } from "../../../lib/fleetQueries";
import { Banner, Pill } from "../bits";

export default function TotpCard() {
  const me = useAuthMe();
  const d = me.data;
  return (
    <Panel title="Xác thực hai bước (TOTP)">
      {me.isPending ? <span className="text-muted text-[12.5px]">Đang kiểm tra…</span> : me.isError ? <Banner tone="bad">Chưa lấy được trạng thái TOTP. Tải lại trang để thử lại.</Banner> : (
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {d?.totp_enabled ? <Pill tone="ok" icon={ShieldCheck}>Đã bật</Pill> : <Pill tone={d?.totp_setup_required ? "bad" : "mute"} icon={ShieldAlert}>Chưa bật</Pill>}
            {!d?.totp_enabled && <button type="button" className="btn !bg-accent !text-[color:var(--accent-fg)] !border-transparent" onClick={openTotpWizard}><KeyRound size={13} aria-hidden="true" />Bật TOTP</button>}
          </div>
          {d?.totp_setup_required && <Banner tone="warn">Tài khoản master cần bật TOTP: thao tác nhạy cảm (hàng loạt, nhập CSV, quản lý vai trò) sẽ bị từ chối cho đến khi bật.</Banner>}
          {d?.totp_enabled && <p className="m-0 text-[12.5px] text-muted">Mỗi lần đăng nhập cần thêm mã 6 số từ ứng dụng xác thực. Mất thiết bị: nhờ master khác đặt lại.</p>}
          {!d?.totp_enabled && !d?.totp_setup_required && <p className="m-0 text-[12.5px] text-muted">Nên bật TOTP để bảo vệ tài khoản ngay cả khi lộ mật khẩu.</p>}
        </div>
      )}
    </Panel>
  );
}
