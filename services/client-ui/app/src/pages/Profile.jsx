import { useEffect, useState } from "react";
import { Bell, Cloud, CloudOff, Download, HelpCircle, KeyRound, LogOut, MonitorSmartphone, Palette, Plug, RefreshCw, ShieldCheck, Wallet } from "lucide-react";
import { auth } from "../lib/api";
import { accountTitle, useAuth } from "../lib/auth";
import { eaState, useAccountSnaps } from "../lib/queries";
import { TZ_OPTIONS, usePrefs } from "../lib/prefs";
import { LANGS, t, tr } from "../lib/i18n";
import { syncNow, useSyncStatus } from "../lib/prefsync";
import { PermissionCard } from "./Notifications";
import { useClock } from "../lib/clock";
import { ageText } from "../lib/freshness";
import { dateTime, rel } from "../lib/format";
import { Async, Chip, Notice, PageHead, Panel, Seg, Sheet } from "../components/ui";
import ChangePasswordForm from "../components/changepw";
import { useQuery } from "@tanstack/react-query";
import { clearSwCaches } from "../lib/pwa";

function Sessions() {
  const a = useAuth();
  const q = useQuery({ queryKey: ["auth-sessions"], queryFn: () => auth("GET", "/sessions"), retry: false, staleTime: 15_000 });
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState("");
  const items = Array.isArray(q.data) ? q.data : q.data?.items || [];
  const revoke = async (id) => {
    setBusy(id); setMsg("");
    try { await auth("POST", `/sessions/${encodeURIComponent(id)}/revoke`, {}); await q.refetch(); } catch (e) { setMsg(e.message); } finally { setBusy(null); }
  };
  const unsupported = q.isError && (q.error?.status === 404 || q.error?.status === 405);
  return (
    <div className="grid gap-3">
      {unsupported ? <p className="m-0 text-muted text-[13.5px]">{t("Máy chủ chưa hỗ trợ xem danh sách thiết bị. Bạn vẫn có thể đăng xuất ngay bên dưới.")}</p> : (
        <Async q={q} rows={3} isEmpty={() => items.length === 0} empty={t("Không có thông tin phiên.")}>
          {() => (
            <ul className="list-none m-0 p-0 grid gap-2">
              {items.map((s) => (
                <li key={s.id} className="rounded-xl border border-line bg-panel2 p-3 flex flex-wrap items-center gap-3 min-w-0">
                  <MonitorSmartphone size={20} className="text-muted shrink-0" aria-hidden="true" />
                  <div className="min-w-0 flex-1 basis-[10rem]">
                    <div className="text-[13.5px] font-semibold truncate">{(s.user_agent || t("Thiết bị không rõ")).slice(0, 60)}</div>
                    {s.current && <Chip tone="up">{t("thiết bị này")}</Chip>}
                    <div className="text-[12px] text-faint">{t("Đăng nhập {at} · hoạt động {ago}", { at: dateTime(s.created_at), ago: s.last_seen_at ? ageText((Date.now() - new Date(s.last_seen_at)) / 1000) : "—" })}{s.ip ? ` · ${s.ip}` : ""}</div>
                  </div>
                  {!s.current && <button className="btn sm danger" onClick={() => revoke(s.id)} disabled={busy === (s.id)} aria-label={t("Đăng xuất thiết bị này")}>{t("Đăng xuất")}</button>}
                </li>))}
            </ul>
          )}
        </Async>
      )}
      {msg && <Notice tone="down">{msg}</Notice>}
      <div className="flex flex-wrap gap-2">
        <button className="btn" onClick={() => { clearSwCaches(); a.logout(); }}><LogOut size={16} aria-hidden="true" /> {t("Đăng xuất thiết bị này")}</button>
        <button className="btn danger" onClick={() => { clearSwCaches(); a.logout(true); }}>{t("Đăng xuất mọi thiết bị")}</button>
      </div>
    </div>
  );
}

function Accounts() {
  const a = useAuth();
  const snaps = useAccountSnaps();
  const now = useClock();
  const statusLabel = { active: t("Đang hoạt động"), pending: t("Chờ ghép cặp"), suspended: t("Đang tạm dừng") };
  return (
    <ul className="list-none m-0 p-0 grid gap-2">
      {a.accounts.length === 0 && <li className="text-muted">{t("Chưa có tài khoản MT nào được gán.")}</li>}
      {a.accounts.map((x) => {
        const ts = (snaps.data || []).find((s) => s.account_id === x.id)?.ts;
        const s = eaState(ts, now);
        return (
          <li key={x.id} className="rounded-xl border border-line bg-panel2 p-3 grid gap-1">
            <div className="flex items-center gap-2 flex-wrap"><b className="num text-[15px]">{accountTitle(x)}</b>{x.id === a.active?.id && <Chip tone="accent">{t("đang xem")}</Chip>}
              <Chip tone={x.status === "active" ? "up" : "down"}>{statusLabel[x.status] || x.status}</Chip></div>
            <div className="text-[13px] text-muted">{x.label || "—"}{x.server ? ` · ${t("Máy chủ {name}", { name: x.server })}` : ""}</div>
            <div className="text-[12.5px] flex items-center gap-2"><span className={`live-dot ${s.level === "on" ? "on" : s.level === "warn" ? "warn" : s.level === "off" ? "off" : ""}`} />{s.label}{s.ageS != null ? ` · ${ageText(s.ageS)}` : ""}</div>
          </li>);
      })}
    </ul>
  );
}

export function EaGuide() {
  const origin = typeof location !== "undefined" ? location.origin : "";
  const steps = [
    [t("Lấy tệp EA"), t("Nhận tệp EA (.ex4 cho MT4 hoặc .ex5 cho MT5) từ quản trị viên của bạn.")],
    [t("Chép vào MT"), t("Trong MT chọn Tệp (File) → Mở thư mục dữ liệu → thư mục MQL của nền tảng → Experts, chép tệp EA vào đó rồi khởi động lại MT hoặc bấm Làm mới ở cửa sổ Navigator.")],
    [t("Cho phép kết nối"), tr("Công cụ (Tools) → Tùy chọn (Options) → Expert Advisors: bật {opt} và thêm địa chỉ {url}. Không cần bật giao dịch tự động.", { opt: <b>Allow WebRequest for listed URL</b>, url: <span className="num break-all">{origin}</span> })],
    [t("Gắn EA vào biểu đồ"), t("Kéo EA từ Navigator vào một biểu đồ bất kỳ. Tab Experts sẽ in mã ghép cặp trong lần đầu.")],
    [t("Ghép cặp"), t("Quay lại màn hình đăng nhập, chọn \"Ghép cặp lần đầu\", nhập số tài khoản, mã ghép cặp và tự đặt mật khẩu cổng.")],
  ];
  return (
    <div className="grid gap-3">
      <Notice tone="info" icon={ShieldCheck}>{tr("EA chỉ {b} tài khoản về hệ thống. Nó không đặt, sửa hay đóng lệnh. Bạn không cần đưa mật khẩu giao dịch cho bất kỳ ai.", { b: <b>{t("đọc và gửi dữ liệu")}</b> })}</Notice>
      <ol className="m-0 pl-0 list-none grid gap-2.5">
        {steps.map(([title, d], i) => (
          <li key={i} className="flex gap-3"><span className="grid place-items-center w-7 h-7 rounded-full bg-[var(--accent-bg)] text-accent font-bold text-[13px] shrink-0">{i + 1}</span>
            <div className="min-w-0"><div className="font-semibold text-[14px]">{title}</div><div className="text-[13px] text-muted">{d}</div></div></li>))}
      </ol>
    </div>
  );
}

function Install() {
  const [ev, setEv] = useState(null);
  const standalone = typeof matchMedia !== "undefined" && matchMedia("(display-mode: standalone)").matches;
  useEffect(() => {
    const h = (e) => { e.preventDefault(); setEv(e); };
    addEventListener("beforeinstallprompt", h);
    return () => removeEventListener("beforeinstallprompt", h);
  }, []);
  if (standalone) return <p className="m-0 text-muted text-[13.5px]">{t("Bạn đang dùng ứng dụng đã cài trên thiết bị.")}</p>;
  return (
    <div className="grid gap-2 text-[13.5px]">
      {ev && <button className="btn primary self-start" onClick={async () => { ev.prompt(); await ev.userChoice; setEv(null); }}><Download size={16} aria-hidden="true" /> {t("Cài ứng dụng")}</button>}
      <p className="m-0 text-muted"><b className="text-fg">iPhone/iPad (Safari):</b> {t("bấm biểu tượng Chia sẻ → Thêm vào Màn hình chính.")}<br /><b className="text-fg">Android (Chrome):</b> {t("menu ⋮ → Cài đặt ứng dụng / Thêm vào màn hình chính.")}</p>
      {!window.isSecureContext && <p className="m-0 text-faint text-[12.5px]">{t("Cài đặt cần kết nối HTTPS.")}</p>}
    </div>
  );
}

function Row({ label, hint, children }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-4 py-2.5 border-b border-line last:border-0">
      <div className="min-w-0"><div className="font-semibold text-[13.5px]">{label}</div>{hint && <div className="text-[12.5px] text-muted">{hint}</div>}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** Trạng thái đồng bộ cài đặt giữa các thiết bị (lib/prefsync.jsx). */
function SyncLine() {
  const s = useSyncStatus();
  if (s.status === "idle") return null;
  const off = s.status === "unavailable" || s.status === "offline";
  const text = s.status === "synced" ? t("Cài đặt được đồng bộ giữa các thiết bị của bạn.") + (s.at ? ` ${t("Cập nhật {ago}.", { ago: rel(s.at) })}` : "")
    : s.status === "syncing" ? t("Đang đồng bộ cài đặt…")
    : s.status === "offline" ? t("Chưa đồng bộ được (mất kết nối). Cài đặt vẫn được lưu trên thiết bị này và sẽ đồng bộ lại sau.")
    : t("Đồng bộ giữa thiết bị chưa khả dụng. Cài đặt chỉ lưu trên thiết bị này.");
  const Icon = off ? CloudOff : Cloud;
  return (
    <div className="flex items-start gap-2 pt-2.5 text-[12.5px] text-muted" role="status">
      <Icon size={15} className="shrink-0 mt-0.5" aria-hidden="true" />
      <span className="min-w-0 flex-1">{text}</span>
      {s.status !== "unavailable" && s.status !== "syncing" && <button className="btn sm ghost shrink-0" onClick={() => syncNow()} aria-label={t("Đồng bộ lại ngay")}><RefreshCw size={14} aria-hidden="true" /> {t("Đồng bộ")}</button>}
    </div>
  );
}

function Prefs() {
  const { prefs, set } = usePrefs();
  return (
    <div>
      <Row label={t("Ngôn ngữ")} hint={t("Ngôn ngữ giao diện. Bản tin và tin tức giữ nguyên ngôn ngữ gốc.")}>
        <Seg value={prefs.lang} onChange={(v) => set({ lang: v })} options={LANGS} label={t("Chọn ngôn ngữ")} />
      </Row>
      <Row label={t("Giao diện")} hint={t("Tự động theo chế độ của thiết bị hoặc chọn cố định.")}>
        <Seg value={prefs.theme} onChange={(v) => set({ theme: v })} options={[{ value: "auto", label: t("Tự động") }, { value: "dark", label: t("Tối") }, { value: "light", label: t("Sáng") }]} label={t("Chọn giao diện")} />
      </Row>
      <Row label={t("Mật độ hiển thị")} hint={t("Gọn: hiện được nhiều số liệu hơn trên một màn hình.")}>
        <Seg value={prefs.density} onChange={(v) => set({ density: v })} options={[{ value: "comfortable", label: t("Thoải mái") }, { value: "compact", label: t("Gọn") }]} label={t("Mật độ hiển thị")} />
      </Row>
      <Row label={t("Múi giờ hiển thị")} hint={t("Chỉ đổi cách hiển thị giờ; thống kê theo ngày vẫn tính theo giờ Việt Nam.")}>
        <select className="field" value={prefs.tz} onChange={(e) => set({ tz: e.target.value })} aria-label={t("Múi giờ hiển thị")}>{TZ_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
      </Row>
      <Row label={t("Định dạng số")} hint={t("Ví dụ 12,345.67 hoặc 12.345,67.")}>
        <Seg value={prefs.num} onChange={(v) => set({ num: v })} options={[{ value: "en", label: "12,345.67" }, { value: "vi", label: "12.345,67" }]} label={t("Định dạng số")} />
      </Row>
      <Row label={t("Thông báo hệ thống tự động")} hint={t("Tự báo khi EA mất kết nối hoặc margin xuống mức nguy hiểm.")}>
        <Seg value={prefs.toasts === false ? "off" : "on"} onChange={(v) => set({ toasts: v === "on" })} options={[{ value: "on", label: t("Bật") }, { value: "off", label: t("Tắt") }]} label={t("Thông báo hệ thống")} />
      </Row>
      <SyncLine />
    </div>
  );
}

export default function Profile() {
  const a = useAuth();
  const { set } = usePrefs();
  const [pw, setPw] = useState(false);
  return (
    <>
      <PageHead title={t("Cài đặt & hồ sơ")} sub={`${a.me.name || t("Khách hàng")}${a.me.role === "master" ? ` · ${t("quản trị")}` : ""}`}
        right={<><a className="btn sm" href="#/tro-giup"><HelpCircle size={16} aria-hidden="true" /> {t("Trợ giúp & thuật ngữ")}</a><button className="btn sm" onClick={() => set({ onboarded: false })}>{t("Xem lại hướng dẫn đầu tiên")}</button></>} />
      <Panel title={t("Tài khoản MT của bạn")} icon={Wallet}><Accounts /></Panel>
      <Panel title={t("Giao diện & hiển thị")} icon={Palette}><Prefs /></Panel>
      <Panel title={t("Thông báo")} icon={Bell}><PermissionCard /></Panel>
      <Panel title={t("Mật khẩu cổng")} icon={KeyRound}>
        <p className="m-0 mb-3 text-[13px] text-muted">{t("Mật khẩu cổng chỉ dùng để đăng nhập ứng dụng này. Không phải mật khẩu giao dịch MT.")}</p>
        <button className="btn" onClick={() => setPw(true)}>{t("Đổi mật khẩu cổng")}</button>
      </Panel>
      <Panel title={t("Thiết bị & phiên đăng nhập")} icon={MonitorSmartphone}><Sessions /></Panel>
      <Panel title={t("Hướng dẫn cài EA trên MT4/MT5")} icon={Plug}><EaGuide /></Panel>
      <Panel title={t("Cài ứng dụng lên điện thoại")} icon={Download}><Install /></Panel>
      {pw && <Sheet title={t("Đổi mật khẩu cổng")} onClose={() => setPw(false)}><ChangePasswordForm onDone={() => setTimeout(() => setPw(false), 1200)} /></Sheet>}
    </>
  );
}
