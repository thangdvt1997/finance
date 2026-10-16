import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { Notice } from "./ui";
import { currentSubscription, disableWebPush, enableWebPush, testWebPush, webPushInfo, webPushSupported } from "../lib/webpush";

/** Thông báo đẩy khi ứng dụng đóng (Web Push tự host). Ẩn nếu máy chủ chưa bật hoặc thiết bị không hỗ trợ. */
export default function WebPushCard() {
  const [info, setInfo] = useState(null);
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (!webPushSupported()) return undefined;
    const ac = new AbortController();
    webPushInfo(ac.signal).then(setInfo);
    currentSubscription().then((s) => setOn(!!s && Notification.permission === "granted"));
    return () => ac.abort();
  }, []);
  if (!info) return null;
  const run = async (fn, ok) => { setBusy(true); setMsg(""); try { await fn(); setMsg(ok); } catch (e) { setMsg(e.message || "Không thực hiện được."); } finally { setBusy(false); } };
  if (on) {
    return (
      <Notice tone="up" icon={BellRing} title="Thông báo đẩy đã bật"
        action={<span className="flex gap-2"><button className="btn sm" disabled={busy} onClick={() => run(testWebPush, "Đã gửi thông báo thử.")}>Gửi thử</button><button className="btn sm" disabled={busy} onClick={() => run(async () => { await disableWebPush(); setOn(false); }, "Đã tắt thông báo đẩy.")}>Tắt</button></span>}>
        Cảnh báo bạn đặt trên máy chủ sẽ gửi tới thiết bị này kể cả khi đã đóng ứng dụng. Nội dung chỉ là thông báo chung, không có số dư. {msg}
      </Notice>
    );
  }
  return (
    <Notice tone="info" title="Bật thông báo đẩy khi đã đóng ứng dụng"
      action={<button className="btn sm" disabled={busy} onClick={() => run(async () => { await enableWebPush(info.public_key); setOn(true); }, "Đã bật thông báo đẩy.")}>Bật thông báo đẩy</button>}>
      Nhận cảnh báo của bạn ngay trên thiết bị, không cần mở ứng dụng. Miễn phí, không quảng cáo. {msg}
    </Notice>
  );
}
