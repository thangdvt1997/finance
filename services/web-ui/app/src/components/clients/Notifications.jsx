import { useEffect, useMemo, useState } from "react";
import { BellRing, CheckCheck, ShieldAlert, WifiOff, LockKeyhole, UserX, Clock, AlertTriangle } from "lucide-react";
import { Chip, Panel, Seg } from "../ui";
import { rel } from "../../lib/format";
import { deriveNotifications } from "../../lib/clientsQueries";
import { fmtDT } from "./bits";

const KEY = "clients.ack.v1";
const readAck = () => { try { return new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { return new Set(); } };
const ICON = { ea_offline: WifiOff, ea_never: WifiOff, pair_expired: Clock, risk: ShieldAlert, locked: LockKeyhole, unusual_login: UserX, failed_logins: LockKeyhole };

/** Danh sách thông báo (và số chưa xem) cho master. Suy diễn từ fleet + nhật ký kiểm toán; "đã xem" lưu trên trình duyệt này. */
export function useNotices(rows, audit) {
  const [ack, setAck] = useState(readAck);
  const all = useMemo(() => deriveNotifications(rows, audit), [rows, audit]);
  const sig = (n) => `${n.id}@${Math.floor(n.ts / 3600e3)}`; // sự kiện lặp lại sau 1 giờ sẽ hiện lại
  const unread = all.filter((n) => !ack.has(sig(n)));
  const mark = (list) => { const next = new Set([...ack, ...list.map(sig)]); setAck(next); try { localStorage.setItem(KEY, JSON.stringify([...next].slice(-400))); } catch { /* bỏ qua */ } };
  return { all, unread, ack, sig, mark };
}

export default function Notifications({ notices }) {
  const { all, ack, sig, mark } = notices;
  const [lv, setLv] = useState("all");
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(t); }, []);
  const list = all.filter((n) => lv === "all" || (lv === "unread" ? !ack.has(sig(n)) : n.level === lv));
  return (
    <Panel title="Thông báo cho master" icon={BellRing} pad={false}
      right={<><Seg value={lv} onChange={setLv} label="Lọc thông báo" options={[{ value: "all", label: "Tất cả" }, { value: "unread", label: "Chưa xem" }, { value: "crit", label: "Nghiêm trọng" }, { value: "warn", label: "Cảnh báo" }]} />
        <button className="btn" onClick={() => mark(all)} disabled={!all.some((n) => !ack.has(sig(n)))}><CheckCheck size={13} aria-hidden="true" />Đánh dấu đã xem</button></>}>
      {list.length ? (
        <ul className="m-0 p-0 list-none divide-y divide-line" data-now={now}>
          {list.map((n) => {
            const Icon = ICON[n.kind] || AlertTriangle; const seen = ack.has(sig(n));
            return (
              <li key={n.id} className={`flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2.5 ${seen ? "opacity-60" : ""}`}>
                <Icon size={16} className={n.level === "crit" ? "text-down mt-[2px]" : "text-accent mt-[2px]"} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><b className="text-[13px]">{n.title}</b><Chip tone={n.level === "crit" ? "down" : "accent"}>{n.level === "crit" ? "Nghiêm trọng" : "Cảnh báo"}</Chip>{!seen && <Chip tone="up">Mới</Chip>}</div>
                  <p className="m-0 text-[12.5px] text-muted">{n.text}</p>
                </div>
                <div className="ml-auto flex items-center gap-3 text-[11.5px] text-faint"><span title={fmtDT(n.ts)}>{rel(n.ts, now)}</span>
                  {n.account_id && <a href={`#/khach-hang/danh-sach/${n.account_id}`} className="btn !h-7 no-underline">Mở</a>}</div>
              </li>
            );
          })}
        </ul>
      ) : <p className="m-0 p-3 text-muted">Không có thông báo{lv !== "all" ? " trong bộ lọc này" : ""}. EA đều kết nối, không có đăng nhập bất thường.</p>}
      <p className="m-0 px-3 py-2 border-t border-line text-[11.5px] text-faint">Quy tắc: EA mất kết nối &gt; 15 phút · EA chưa từng kết nối · mã ghép cặp hết hạn · vượt ngưỡng rủi ro · ≥ 3 lần đăng nhập sai/24 giờ · đăng nhập IP/quốc gia lạ · khoá tạm.</p>
    </Panel>
  );
}
