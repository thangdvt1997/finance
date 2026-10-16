// Nút chuông (nhẹ, nằm trong bundle chính); ngăn kéo thông báo NotificationCenter nạp lười khi mở lần đầu.
import { Bell } from "lucide-react";
import { useNotifications } from "../../ux/bus";

export function BellButton({ open, onOpen }) {
  const { unread } = useNotifications();
  return (
    <button type="button" className="btn !px-2 relative" onClick={onOpen} aria-haspopup="dialog" aria-expanded={open}
      aria-label={unread ? `Thông báo, ${unread} chưa đọc` : "Thông báo"} data-tour="bell">
      <Bell size={15} aria-hidden="true" />
      {unread > 0 && <span className="ux-badge" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
    </button>
  );
}
