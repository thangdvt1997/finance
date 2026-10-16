// Hộp thoại xác nhận 2 bước dùng chung cho thao tác nhạy cảm (đình chỉ, thu hồi phiên, đăng xuất mọi nơi...).
import { Dialog } from "../../dialog";
import { Banner, ErrLine } from "../bits";

export default function Confirm({ open = true, title, body, warn, confirmLabel = "Xác nhận", danger, busy, error, onConfirm, onClose }) {
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} title={title} footer={<>
      <button type="button" className="btn" onClick={onClose} disabled={busy} data-autofocus>Huỷ</button>
      <button type="button" className={`btn ${danger ? "!bg-down !text-white !border-transparent" : "!bg-accent !text-[color:var(--accent-fg)] !border-transparent"}`} onClick={onConfirm} disabled={busy}>{busy ? "Đang thực hiện…" : confirmLabel}</button>
    </>}>
      <div className="p-3 grid gap-2 text-[13px]">
        <div>{body}</div>
        {warn && <Banner tone="warn">{warn}</Banner>}
        <ErrLine error={error} />
      </div>
    </Dialog>
  );
}
