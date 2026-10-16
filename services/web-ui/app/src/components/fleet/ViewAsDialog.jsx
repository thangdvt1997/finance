// "Xem như khách": BẮT BUỘC nhập lý do (>= 8 ký tự) -> POST view-as -> banner cố định trên mọi trang (đếm ngược), mọi thao tác ghi bị khoá ở UI.
import { useEffect, useState } from "react";
import { Eye } from "lucide-react";
import { Dialog } from "../dialog";
import { fpost, setViewAs } from "../../lib/fleetApi";
import { markImpersonating } from "../clients/ViewAs";
import { Banner, ErrLine, Field, PRIMARY } from "./bits";

export default function ViewAsDialog({ open, accountId, label, onClose }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  useEffect(() => { if (open) { setReason(""); setErr(null); } }, [open]);
  const ok = reason.trim().length >= 8;
  const go = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await fpost("/view-as", { account_id: accountId, reason: reason.trim() });
      setViewAs({ grant_id: r.grant_id, account_id: accountId, expires_at: r.expires_at, reason: reason.trim() });
      markImpersonating(accountId);
      onClose?.();
      location.hash = `#/khach-hang/xem/${accountId}`;
    } catch (e2) { setErr(e2); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={onClose} title="Xem như khách hàng" description={`${label ? `${label} · ` : ""}${accountId}`}>
      <form onSubmit={go} className="p-3 grid gap-3 text-[13px]">
        <Banner tone="info" icon={Eye} title="Chế độ chỉ-đọc, có thời hạn">
          Bạn sẽ thấy đúng dữ liệu khách nhìn thấy, trong 30 phút (có đếm ngược). Mọi thao tác ghi bị khoá; việc xem được ghi vào nhật ký kiểm toán kèm lý do bên dưới.
        </Banner>
        <Field label="Lý do xem (bắt buộc, tối thiểu 8 ký tự)" htmlFor="va-reason" help={`${reason.trim().length}/8 ký tự tối thiểu`}>
          <textarea id="va-reason" className="field" rows={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ví dụ: khách báo không thấy lệnh đang mở, kiểm tra hiển thị" data-autofocus required />
        </Field>
        <ErrLine error={err} />
        <div className="flex justify-end gap-2"><button type="button" className="btn" onClick={onClose}>Huỷ</button>
          <button type="submit" className={`btn ${PRIMARY}`} disabled={!ok || busy}>{busy ? "Đang mở…" : "Bắt đầu xem"}</button></div>
      </form>
    </Dialog>
  );
}
