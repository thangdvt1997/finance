import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bell, Info, X } from "lucide-react";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { mergeLiveQuotes, useAccountSnaps } from "../lib/queries";
import { useLiveQuotes, useRealtimeLive } from "../lib/useLiveQuote";
import { useClientPrefs, useServerUnread } from "../lib/q_notif";
import { clean } from "../lib/format";
import { t } from "../lib/i18n";
import { bindRulesUser, useAlertEngine, useLocalRules } from "../lib/localalerts";
import { bindUser, dismissToast, pushNotification, useToasts, useUnread } from "../lib/notifstore";
import { usePrefs } from "../lib/prefs";
import { cn } from "./ui";

/** Chạy ngầm trong Shell: cảnh báo trên thiết bị + thông báo hệ thống + sự kiện cảnh báo từ máy chủ (nếu có). Không vẽ gì. */
export function AlertEngine() {
  const { me } = useAuth();
  const { prefs } = usePrefs();
  const snaps = useAccountSnaps();
  const { rules } = useLocalRules();
  const syms = useMemo(() => [...new Set(rules.filter((r) => r.enabled && r.kind === "price").map((r) => r.symbol))], [rules]);
  const rtLive = useRealtimeLive();
  const quotesQ = useQuery({
    queryKey: ["quotes-engine", syms.join(",")], enabled: syms.length > 0, refetchInterval: rtLive ? 90_000 : 15_000, staleTime: 5_000, retry: false,
    queryFn: ({ signal }) => api("/quotes/latest", { symbols: syms.join(",") }, signal),
  });
  const liveQ = useLiveQuotes(syms.length ? syms.slice(0, 100) : undefined);
  const quotes = useMemo(() => { const d = mergeLiveQuotes(quotesQ.data, liveQ, syms); return d === quotesQ.data ? quotesQ : { data: d }; }, [quotesQ, liveQ, syms]);
  useEffect(() => { bindUser(me?.userId); bindRulesUser(me?.userId); }, [me?.userId]);
  useAlertEngine({ snaps: snaps.data, quotes: quotes.data, sys: prefs.toasts !== false });

  // thông báo từ máy chủ: toast cho mục chưa đọc MỚI hơn lúc mở ứng dụng (tôn trọng cài đặt "trong ứng dụng" từng loại); nội dung nằm trên máy chủ nên không lưu cục bộ
  const born = useRef(Date.now());
  const srv = useQuery({ queryKey: ["user-notifs-latest"], queryFn: ({ signal }) => api("/user/notifications", { limit: 10 }, signal), refetchInterval: 30_000, retry: false, staleTime: 15_000 });
  const cp = useClientPrefs();
  const appOn = (kind) => cp.data?.data?.notif?.[kind]?.app !== false;
  useEffect(() => {
    for (const n of srv.data?.items || []) {
      const ts = new Date(n.ts).getTime();
      if (n.read || !Number.isFinite(ts) || ts <= born.current || !appOn(n.kind)) continue;
      pushNotification({ id: `srv:${n.id}`, kind: "server", level: n.severity === "danger" ? "crit" : n.severity === "warn" ? "warn" : "info", title: clean(n.title || t("Thông báo mới")), body: clean(n.body || ""), ts, toast: prefs.toasts !== false, persist: false });
    }
  }, [srv.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // dự phòng khi máy chủ chưa có trung tâm thông báo: dùng sự kiện quy tắc (nếu dịch vụ cho phép với tài khoản khách)
  const ev = useQuery({ queryKey: ["user-rule-events", "", 15], enabled: srv.isError, queryFn: ({ signal }) => api("/user/rule-events", { limit: 15 }, signal), refetchInterval: 45_000, retry: false, staleTime: 20_000 });
  useEffect(() => {
    for (const e of ev.data?.items || []) {
      const ts = new Date(e.ts).getTime();
      if (Number.isFinite(ts)) pushNotification({ id: `srv:${e.id ?? ts}`, kind: "server", level: e.level === "crit" ? "crit" : e.level === "warn" ? "warn" : "info", title: clean(e.title || e.rule_name || t("Cảnh báo")), body: clean(e.body || ""), ts, toast: ts > born.current });
    }
  }, [ev.data]);
  return null;
}

const ICON = { crit: AlertTriangle, warn: AlertTriangle, info: Info };
export function ToastHost() {
  const list = useToasts();
  return (
    <div className="toast-host" aria-live="polite" aria-atomic="false">
      {list.map((x) => {
        const I = ICON[x.level] || Info;
        return (
          <div key={x.id} className="toast" role={x.level === "crit" ? "alert" : "status"}>
            <I size={18} className="shrink-0 mt-[2px]" style={{ color: x.level === "crit" ? "var(--down)" : x.level === "warn" ? "var(--accent)" : "var(--info)" }} aria-hidden="true" />
            <div className="min-w-0 flex-1"><div className="font-semibold text-[13.5px]">{x.title}</div>{x.body && <div className="text-[12.5px] text-muted">{x.body}</div>}
              <a href="#/thong-bao" className="text-[12px] text-accent inline-block min-h-[24px] pt-1">{t("Xem trung tâm thông báo")}</a></div>
            <button className="ibtn !w-11 !h-11 -mr-1 -mt-1" onClick={() => dismissToast(x.id)} aria-label={t("Đóng thông báo")}><X size={16} aria-hidden="true" /></button>
          </div>);
      })}
    </div>
  );
}

export function BellButton({ active }) {
  const local = useUnread();
  const server = useServerUnread();
  const n = local + (server.data || 0);   // chưa đọc trên máy chủ + sự kiện cục bộ của thiết bị này
  return (
    <a href="#/thong-bao" className={cn("ibtn relative", active && "!text-accent")} aria-label={n ? t("Thông báo, {n} chưa đọc", { n }) : t("Thông báo")} title={t("Trung tâm thông báo")}>
      <Bell size={20} aria-hidden="true" />{n > 0 && <span className="badge-dot" aria-hidden="true">{n > 9 ? "9+" : n}</span>}
    </a>
  );
}

export function OfflineBar() {
  const [off] = useOnline();
  if (!off) return null;
  return <div className="offline-bar" role="status">{t("Đang ngoại tuyến: số liệu hiển thị là lần cập nhật gần nhất, có thể đã cũ.")}</div>;
}
function useOnline() {
  const [off, setOff] = useState(typeof navigator !== "undefined" && navigator.onLine === false);
  useEffect(() => {
    const a = () => setOff(true), b = () => setOff(false);
    addEventListener("offline", a); addEventListener("online", b);
    return () => { removeEventListener("offline", a); removeEventListener("online", b); };
  }, []);
  return [off, setOff];
}
