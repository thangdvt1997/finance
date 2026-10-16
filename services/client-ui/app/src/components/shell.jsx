import { useState } from "react";
import { BarChart3, Bot, Bell, BellRing, BookOpen, CalendarCheck, Check, ChevronDown, Eye, FileBarChart, HelpCircle, Layers, LayoutGrid, LineChart, Moon, Newspaper, Radar, Settings, ShieldAlert, Sparkles, Sun, Target, TrendingDown, Users, Wallet } from "lucide-react";
import { useAuth, accountTitle } from "../lib/auth";
import { useTheme, useAccountSnaps } from "../lib/queries";
import { MOCK } from "../lib/api";
import { useClock } from "../lib/clock";
import { ageText, connStatus } from "../lib/freshness";
import { cn, Sheet } from "./ui";
import { AlertEngine, BellButton, OfflineBar, ToastHost } from "./notify";
import Onboarding from "./onboarding";
import { preload } from "../lib/preload";
import { t } from "../lib/i18n";
import { useReminderEngine } from "../lib/q_today";
import StatusBanner from "./statusbanner";

export const NAV = [
  { to: "/hom-nay", get label() { return t("Hôm nay"); }, get short() { return t("Hôm nay"); }, icon: CalendarCheck, main: true },
  { to: "/vi-the", get label() { return t("Vị thế & lệnh chờ"); }, get short() { return t("Vị thế"); }, icon: Wallet, main: true },
  { to: "/thi-truong", get label() { return t("Thị trường"); }, get short() { return t("Thị trường"); }, icon: LineChart, main: true },
  { to: "/nhat-ky", get label() { return t("Nhật ký giao dịch"); }, get short() { return t("Nhật ký"); }, icon: BookOpen, main: true },
  { to: "/tong-quan", get label() { return t("Tổng quan tài khoản"); }, get short() { return t("Tổng quan"); }, icon: LayoutGrid },
  { to: "/gioi-han", get label() { return t("Giới hạn & mục tiêu"); }, get short() { return t("Giới hạn"); }, icon: Target },
  { to: "/rui-ro", get label() { return t("Rủi ro"); }, get short() { return t("Rủi ro"); }, icon: ShieldAlert },
  { to: "/danh-muc", get label() { return t("Danh mục nhiều tài khoản"); }, get short() { return t("Danh mục"); }, icon: Layers, multi: true },
  { to: "/tin-lich", get label() { return t("Tin & Lịch kinh tế"); }, get short() { return t("Tin & Lịch"); }, icon: Newspaper },
  { to: "/ban-tin", get label() { return t("Bản tin AI"); }, get short() { return t("Bản tin"); }, icon: Sparkles },
  { to: "/tin-hieu", get label() { return t("Phân tích kỹ thuật"); }, get short() { return t("Phân tích"); }, icon: Radar },
  { to: "/kich-ban", get label() { return t("Kịch bản"); }, get short() { return t("Kịch bản"); }, icon: TrendingDown },
  { to: "/ai-trading", get label() { return t("AI Trading"); }, get short() { return t("AI Trading"); }, icon: Bot },
  { to: "/chuyen-gia", get label() { return t("Chuyên gia & đồng thuận"); }, get short() { return t("Chuyên gia"); }, icon: Users },
  { to: "/bao-cao", get label() { return t("Báo cáo của tôi"); }, get short() { return t("Báo cáo"); }, icon: FileBarChart },
  { to: "/canh-bao", get label() { return t("Cảnh báo của tôi"); }, get short() { return t("Cảnh báo"); }, icon: BellRing },
  { to: "/thong-bao", get label() { return t("Thông báo"); }, get short() { return t("Thông báo"); }, icon: Bell },
  { to: "/ho-so", get label() { return t("Cài đặt & hồ sơ"); }, get short() { return t("Cài đặt"); }, icon: Settings },
  { to: "/tro-giup", get label() { return t("Trợ giúp & thuật ngữ"); }, get short() { return t("Trợ giúp"); }, icon: HelpCircle },
];

export function Brand({ size = 44 }) {
  return (
    <span className="brandmark" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 32 32" width={size * 0.64} height={size * 0.64}><path d="M6 21l6-7 5 4 9-11" fill="none" stroke="#E8B04B" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /><circle cx="26" cy="7" r="2.2" fill="#22C38E" /></svg>
    </span>
  );
}

function EaDot({ ts }) {
  const now = useClock();
  const s = connStatus({ ts, nowMs: now });
  const cls = s.state === "on" ? "on" : s.state === "slow" ? "warn" : s.state === "off" ? "off" : "";
  return <span className={cn("live-dot", cls)} role="img" aria-label={s.label} title={s.label} />;
}

function AccountSwitcher() {
  const a = useAuth();
  const snaps = useAccountSnaps();
  const [open, setOpen] = useState(false);
  const now = useClock();
  const tsOf = (id) => (snaps.data || []).find((x) => x.account_id === id)?.ts;
  const act = a.active;
  return (
    <>
      <button type="button" className="btn ghost !px-2.5 min-w-0 flex-1 sm:flex-none justify-start" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label={t("Tài khoản đang xem: {a}. Bấm để đổi tài khoản", { a: accountTitle(act) })}>
        <EaDot ts={tsOf(act?.id)} />
        <span className="num truncate text-[14px]">{accountTitle(act)}</span>
        {a.accounts.length > 1 && <ChevronDown size={16} className="shrink-0 text-muted" aria-hidden="true" />}
      </button>
      {open && (
        <Sheet title={t("Tài khoản MT của bạn")} onClose={() => setOpen(false)}>
          {a.accounts.length === 0 ? <p className="text-muted">{t("Chưa có tài khoản nào được gán cho hồ sơ này.")}</p> : (
            <ul className="list-none m-0 p-0 grid gap-1">
              {a.accounts.map((x) => {
                const s = connStatus({ ts: tsOf(x.id), nowMs: now });
                return (
                  <li key={x.id}>
                    <button className="row" onClick={() => { a.pick(x.id); setOpen(false); }} aria-current={x.id === act?.id ? "true" : undefined}>
                      <EaDot ts={tsOf(x.id)} />
                      <span className="min-w-0 flex-1">
                        <span className="num block truncate">{accountTitle(x)}</span>
                        <span className="block text-[12.5px] text-muted truncate">{x.label || x.server || "—"} · {s.label}{s.ageS != null ? ` (${ageText(s.ageS)})` : ""}</span>
                      </span>
                      {x.id === act?.id && <Check size={18} className="text-accent shrink-0" aria-hidden="true" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-3 mb-0 text-[12.5px] text-faint">{t("Bạn chỉ thấy các tài khoản được gán cho hồ sơ của mình.")}</p>
        </Sheet>
      )}
    </>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button className="ibtn" onClick={() => setTheme(next)} aria-label={next === "dark" ? t("Đổi sang giao diện tối") : t("Đổi sang giao diện sáng")} title={t("Đổi giao diện sáng/tối")}>
      {theme === "dark" ? <Sun size={19} aria-hidden="true" /> : <Moon size={19} aria-hidden="true" />}
    </button>
  );
}

function ReminderEngine() { useReminderEngine(); return null; }

export function Shell({ path, children }) {
  const [more, setMore] = useState(false);
  const { accounts } = useAuth();
  const nav = NAV.filter((n) => !n.multi || accounts.length > 1);
  const mainNav = nav.filter((n) => n.main);
  const moreNav = nav.filter((n) => !n.main);
  const inMore = moreNav.some((n) => n.to === path);
  return (
    <div className="app">
      <a className="skip" href="#main-content">{t("Bỏ qua điều hướng")}</a>
      <header className="app-head">
        <Brand size={36} />
        <AccountSwitcher />
        <span className="hide-mobile ml-auto" />
        <span className="hide-mobile chip info" title={t("Hệ thống chỉ theo dõi và phân tích. Không thể đặt, sửa hay đóng lệnh.")}><Eye size={12} aria-hidden="true" /> {t("Chỉ theo dõi, không đặt lệnh")}</span>
        <BellButton active={path === "/thong-bao"} />
        <ThemeToggle />
      </header>
      <OfflineBar />
      <AlertEngine />
      <ReminderEngine />
      <div className="app-body">
        <nav className="side-nav" aria-label={t("Điều hướng chính")}>
          {nav.map((n) => <a key={n.to} href={`#${n.to}`} onPointerEnter={() => preload(n.to)} onFocus={() => preload(n.to)} aria-current={path === n.to ? "page" : undefined}><n.icon size={18} aria-hidden="true" />{n.label}</a>)}
        </nav>
        <main className="app-main" id="main-content" tabIndex={-1}>
          <div className="page">
            <div className="only-mobile flex items-center gap-1.5 text-[12px] text-muted -mb-1" role="note"><Eye size={13} className="shrink-0" aria-hidden="true" />{t("Chỉ theo dõi, không đặt lệnh. Số liệu tham khảo, không phải khuyến nghị.")}</div>
            {MOCK && <div role="status" className="chip accent self-start">{t("Dữ liệu mẫu (chế độ thử giao diện)")}</div>}
            <StatusBanner />
            {children}
            <p className="text-[12px] text-faint m-0 pt-2 hide-mobile">{t("Số liệu và phân tích chỉ để tham khảo, không phải khuyến nghị đầu tư. Hệ thống không đặt, sửa hay đóng lệnh.")}</p>
          </div>
        </main>
      </div>
      <nav className="bottom-nav" aria-label={t("Điều hướng chính (di động)")}>
        {mainNav.map((n) => <a key={n.to} href={`#${n.to}`} onPointerDown={() => preload(n.to)} aria-current={path === n.to ? "page" : undefined}><n.icon size={22} aria-hidden="true" />{n.short}</a>)}
        <button onClick={() => setMore(true)} aria-haspopup="dialog" aria-current={inMore ? "page" : undefined}><BarChart3 size={22} aria-hidden="true" />{t("Thêm")}</button>
      </nav>
      <ToastHost />
      <Onboarding />
      {more && (
        <Sheet title={t("Thêm")} onClose={() => setMore(false)}>
          <ul className="list-none m-0 p-0 grid gap-1">
            {moreNav.map((n) => <li key={n.to}><a className="row" href={`#${n.to}`} onClick={() => setMore(false)} aria-current={path === n.to ? "page" : undefined}><n.icon size={20} className="text-muted" aria-hidden="true" />{n.label}</a></li>)}
          </ul>
        </Sheet>
      )}
    </div>
  );
}
