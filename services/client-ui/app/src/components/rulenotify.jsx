import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { auth } from "../lib/api";
import { t } from "../lib/i18n";
import { Notice } from "./ui";

/** Khách TỰ chọn nhận thông báo đẩy khi tài khoản sát/vi phạm một luật rủi ro do quản trị cấu hình. Mặc định TẮT; chỉ khách đổi được. Nội dung push chỉ là thông báo chung. */
export default function RuleNotifyCard() {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    let alive = true;
    auth("GET", "/client/notify").then((r) => alive && setSt(r)).catch(() => alive && setSt(false));
    return () => { alive = false; };
  }, []);
  if (!st || !st.accounts?.length) return null;
  const set = async (enabled) => {
    setBusy(true); setMsg("");
    try { setSt(await auth("PUT", "/client/notify", { enabled })); } catch (e) { setMsg(e.message || t("Không thực hiện được.")); } finally { setBusy(false); }
  };
  return (
    <Notice tone={st.enabled ? "up" : "info"} icon={ShieldAlert} title={st.enabled ? t("Đang nhận thông báo khi sát/vi phạm luật rủi ro") : t("Nhận thông báo khi sát/vi phạm luật rủi ro")}
      action={<button className="btn sm" disabled={busy} onClick={() => set(!st.enabled)}>{st.enabled ? t("Tắt") : t("Bật")}</button>}>
      {t("Nếu đội quản trị đặt luật theo dõi cho tài khoản của bạn (ví dụ giới hạn lỗ trong ngày), bạn có thể chọn nhận thông báo đẩy chung khi tài khoản tiến sát hoặc vượt giới hạn. Mặc định tắt, bạn có thể đổi bất cứ lúc nào.")} {msg}
    </Notice>
  );
}
