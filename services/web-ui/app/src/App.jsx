import { Component, Fragment, Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sun, Moon, PanelLeftClose, PanelLeftOpen, Search, Menu, LayoutDashboard, SlidersHorizontal, LifeBuoy } from "lucide-react";
import { cn, Skeleton } from "./components/ui";
import { TickerTape, SessionClocks, LiveStatus } from "./components/topbar";
import { useTheme } from "./lib/queries";
import { InstallButton, UpdateToast } from "./components/install";
import { startPrefs, usePrefsState, savePref } from "./lib/prefs";
import { startStream, disableStream } from "./lib/stream";
const CommandPalette = lazy(() => import("./components/ux/CommandPalette").then((m) => ({ default: m.CommandPalette })));
const Cheatsheet = lazy(() => import("./components/ux/Cheatsheet").then((m) => ({ default: m.Cheatsheet })));
const NotificationCenter = lazy(() => import("./components/ux/NotificationCenter").then((m) => ({ default: m.NotificationCenter })));
import { UxRoot } from "./components/ux/UxRoot";
import { BellButton } from "./components/ux/BellButton";
import { PageTools } from "./components/ux/PageTools";
import { ConnectionBanner } from "./components/ux/States";
import { useFmtVersion } from "./ux/settings";
import { Dialog } from "./components/dialog";
import { GPending, useShortcuts } from "./components/shortcuts";
import { routesFor, groupsOf, DEFAULT_PATH } from "./shell/registry";
import { fetchMe } from "./lib/clientsApi";
import { NavBadge } from "./components/fleet/NavBadge";
const FleetRoot = lazy(() => import("./components/fleet/FleetRoot")); // banner xem-như-khách + TOTP bắt buộc (quản trị đội tài khoản)

function useRail() {
  const [rail, setRail] = useState(() => { try { return localStorage.getItem("rail") === "1"; } catch { return false; } });
  const set = (v) => { setRail(v); try { localStorage.setItem("rail", v ? "1" : "0"); } catch { /* bỏ qua */ } };
  return [rail, set];
}

function useRoute(routes) {
  const parse = () => {
    const [idq, ...rest] = (location.hash.replace(/^#\/?/, "") || DEFAULT_PATH).split("/");
    const id = idq.split("?")[0]; // "#/tro-giup?term=x": phần sau ? là trạng thái trong địa chỉ (ux/urlstate.js)
    const hit = routes.find((r) => r.id === id) || routes.find((r) => r.id === DEFAULT_PATH) || routes[0];
    return { id: hit?.id, arg: rest.join("/") };
  };
  const [r, setR] = useState(parse);
  useEffect(() => {
    const h = () => setR(parse());
    h();
    addEventListener("hashchange", h);
    return () => removeEventListener("hashchange", h);
  }, [routes]); // eslint-disable-line react-hooks/exhaustive-deps
  return r;
}

class Boundary extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidUpdate(prev) { if (prev.k !== this.props.k && this.state.err) this.setState({ err: null }); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div role="alert" className="panel panel-b max-w-[560px]">
        <b>Mục này tạm thời chưa hiển thị được.</b>
        <p className="text-muted">Dữ liệu có thể đang khởi tạo hoặc giao diện vừa được cập nhật.</p>
        <button className="btn" onClick={() => this.setState({ err: null })}>Thử lại</button>{" "}
        <button className="btn" onClick={() => location.reload()}>Tải lại trang</button>
      </div>
    );
  }
}

export default function App() {
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 300_000, retry: false });
  const role = me.data?.role || "master";
  const ROUTES = useMemo(() => routesFor(role, me.data?.perms), [role, me.data?.perms]);
  const PRIMARY = useMemo(() => { const p = ROUTES.filter((r) => r.primary); return (p.length ? p : ROUTES.slice(0, 4)).slice(0, 4).map((r) => r.id); }, [ROUTES]);
  const GROUPS = useMemo(() => groupsOf(ROUTES), [ROUTES]);
  const route = useRoute(ROUTES);
  const [theme, setTheme] = useTheme();
  const [rail, setRailLocal] = useRail();
  const prefs = usePrefsState();
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [bell, setBell] = useState(false);
  const fmtVer = useFmtVersion();
  const [more, setMore] = useState(false);
  const setRail = (v) => { setRailLocal(v); savePref("nav_rail", v); };
  // vai chuyên gia không có quyền stream/prefs/alerts (403) -> không mở kết nối để khỏi lỗi console + banner mất kết nối giả (UX-X1)
  useEffect(() => { if (me.isLoading) return; if (role === "expert") { disableStream(); return; } startPrefs(); startStream(); }, [me.isLoading, role]);
  // nạp sẵn các hộp thoại dùng nhiều (Ctrl-K, phím tắt, thông báo) lúc rảnh để lần mở đầu không bị trễ/mất phím gõ; không ảnh hưởng LCP
  useEffect(() => {
    const warm = () => { import("./components/ux/CommandPalette"); import("./components/ux/Cheatsheet"); import("./components/ux/NotificationCenter"); };
    const t = setTimeout(() => (window.requestIdleCallback ? requestIdleCallback(warm, { timeout: 1500 }) : warm()), 600);
    return () => clearTimeout(t);
  }, []);
  // Vùng cuộn không có phần tử focus được -> cho phép focus bằng bàn phím để cuộn được (WCAG 2.1.1; axe: scrollable-region-focusable)
  useEffect(() => {
    const fix = () => {
      for (const el of document.querySelectorAll(".tm-scroll, .scroll-x, .scroll-y, .fl-tablewrap, #main, [role=\"region\"]")) {
        if (el.hasAttribute("tabindex") && el.getAttribute("tabindex") !== "-1") continue;
        if (el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1) continue;
        if (el.querySelector("a[href],button,input,select,textarea,[tabindex]:not([tabindex=\"-1\"])")) continue;
        el.setAttribute("tabindex", "0");
      }
    };
    // chạy ngay sau mỗi lần DOM đổi (gộp 200ms) + dự phòng định kỳ (kích thước vùng cuộn đổi khi resize)
    let t = 0;
    const mo = new MutationObserver(() => { clearTimeout(t); t = setTimeout(fix, 200); });
    mo.observe(document.body, { childList: true, subtree: true });
    const id = setInterval(fix, 2500);
    return () => { mo.disconnect(); clearTimeout(t); clearInterval(id); };
  }, []);
  // áp thanh nav từ máy chủ một lần khi tải prefs
  useEffect(() => { if (prefs.loaded && typeof prefs.prefs.nav_rail === "boolean") setRailLocal(prefs.prefs.nav_rail); }, [prefs.loaded]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");
  const gArmed = useShortcuts({ onPalette: () => setPalette((v) => !v), onHelp: () => setHelp(true), onTheme: toggleTheme, onRail: () => setRail(!rail) });
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");
  const cur = ROUTES.find((r) => r.id === route.id) || ROUTES[0];
  const Page = cur?.el;

  useEffect(() => { setMore(false); }, [route.id]);
  useEffect(() => {
    if (cur) document.title = `${cur.label} · Trạm theo dõi thị trường`;
    document.getElementById("main")?.focus({ preventScroll: true });
    scrollTo(0, 0);
    document.getElementById("main")?.scrollTo(0, 0);
  }, [cur?.label]);

  return (
    <div className={cn("flex flex-col min-h-dvh lg:h-dvh lg:overflow-hidden app-pad", rail ? "lg:pl-[60px]" : "lg:pl-[208px]")}>
      <a href="#main" className="sr-only-skip" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Bỏ qua điều hướng</a>
      <UpdateToast />

      {/* Thanh trên: thương hiệu · băng giá · phiên · trạng thái */}
      <header className="sticky top-0 z-30 shrink-0 border-b border-line bg-bg/95 backdrop-blur">
        <div className="flex items-center gap-1.5 sm:gap-3 px-3 h-[44px]">
          <a href={`#/${DEFAULT_PATH}`} className="lg:hidden flex items-center justify-center gap-2 font-semibold no-underline shrink-0 min-w-[44px] h-[44px]" aria-label="Trang tổng quan">
            <Logo />
          </a>
          <div className="min-w-0 flex-1"><TickerTape /></div>
          <div className="hidden xl:block"><SessionClocks /></div>
          <div data-tour="status"><LiveStatus /></div>
          <button className="btn !px-2 sm:!px-3" data-tour="search" onClick={() => setPalette(true)} aria-label={`Tìm… ${isMac ? "⌘K" : "Ctrl K"} — tìm nhanh trang, mã và lệnh`} aria-keyshortcuts="Control+K Meta+K">
            <Search size={14} aria-hidden="true" /><span className="hidden sm:inline text-muted">Tìm…</span><kbd className="hidden md:inline num text-[10.5px] text-faint border border-line2 rounded px-1">{isMac ? "⌘K" : "Ctrl K"}</kbd>
          </button>
          <InstallButton />
          <BellButton open={bell} onOpen={() => setBell(true)} />
          <PageTools route={route} label={cur?.label || ""} />
          <span className="hidden md:inline-flex"><a href="#/tro-giup" className="btn !px-2 no-underline" aria-label="Trợ giúp và thuật ngữ" title="Trợ giúp (g h)"><LifeBuoy size={15} aria-hidden="true" /></a></span>
          <a href="#/cai-dat" className="btn !px-2 no-underline" data-tour="settings" aria-label="Cài đặt" title="Cài đặt (g k)" aria-current={route.id === "cai-dat" ? "page" : undefined}><SlidersHorizontal size={15} aria-hidden="true" /></a>
          <span className="hidden sm:inline-flex"><button className="btn !px-2" aria-label={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button></span>
        </div>
        <div className="xl:hidden border-t border-line px-3 py-1 overflow-x-auto" tabIndex={0} role="group" aria-label="Phiên giao dịch"><SessionClocks /></div>
      </header>

      <ConnectionBanner />
      {role !== "client" && <Suspense fallback={null}><FleetRoot /></Suspense>}
      <nav aria-label="Điều hướng chính" data-tour="nav"
        className={cn("bottom-nav fixed z-40 bottom-0 inset-x-0 border-t border-line bg-panel flex lg:inset-y-0 lg:left-0 lg:right-auto lg:flex-col lg:border-t-0 lg:border-r lg:pt-3", rail ? "lg:w-[60px]" : "lg:w-[208px]")}>
        <a href={`#/${DEFAULT_PATH}`} className="hidden lg:flex items-center gap-2 px-4 pb-4 pt-1 no-underline text-fg shrink-0"><Logo full={!rail} /></a>
        <ul className="flex lg:flex-col flex-1 lg:min-h-0 m-0 p-0 list-none overflow-x-auto lg:overflow-y-auto lg:overflow-x-hidden lg:px-2 lg:gap-[2px]">
          {ROUTES.map((r, i) => {
            const on = r.id === route.id;
            const prim = PRIMARY.includes(r.id);
            const head = i === 0 || ROUTES[i - 1].group !== r.group;
            return (
              <Fragment key={r.id}>
                {head && (rail
                  ? <li role="presentation" aria-hidden="true" className={cn("hidden lg:block mx-2 border-t border-line", i === 0 ? "mt-0 border-t-0" : "mt-2 mb-1")} />
                  : <li role="presentation" aria-hidden="true" className={cn("hidden lg:block px-3 text-[10.5px] font-semibold uppercase tracking-wider text-faint", i === 0 ? "pt-0 pb-1" : "pt-2 pb-0.5")}>{r.group}</li>)}
                <li className={cn("flex-1 min-w-0 lg:flex-none", !prim && "max-lg:hidden")}>
                  <a href={`#/${r.id}`} aria-current={on ? "page" : undefined} title={rail ? r.label : undefined}
                    className={cn("relative flex flex-col lg:flex-row items-center justify-center lg:justify-start gap-[2px] lg:gap-3 h-[58px] lg:h-8 lg:px-3 rounded-md",
                      rail && "lg:justify-center lg:px-0",
                      " no-underline text-[10.5px] lg:text-[13px] font-medium",
                      on ? "text-accent lg:bg-[var(--accent-bg)]" : "text-muted hover:text-fg")}>
                    <r.icon size={18} aria-hidden="true" />
                    <span className={cn("truncate max-lg:max-w-full", rail && "lg:sr-only")}><span className="lg:hidden">{r.short || r.label}</span><span className="max-lg:hidden">{r.label}</span></span>
                    <NavBadge id={r.id} />
                  </a>
                </li>
              </Fragment>
            );
          })}
          <li className="flex-1 min-w-0 lg:hidden">
            <button type="button" onClick={() => setMore(true)} aria-haspopup="dialog" aria-expanded={more}
              className={cn("w-full flex flex-col items-center justify-center gap-[2px] h-[58px] bg-transparent border-0 font-medium text-[10.5px] cursor-pointer", PRIMARY.includes(route.id) ? "text-muted" : "text-accent")}>
              <Menu size={18} aria-hidden="true" /><span>Thêm</span>
            </button>
          </li>
        </ul>
        {!rail && <div className="hidden lg:block mt-auto px-4 py-2 text-[11px] text-faint leading-snug">
          Dữ liệu tham khảo, không phải khuyến nghị đầu tư. Mọi tài khoản MT ở chế độ chỉ đọc.
        </div>}
        <div className={cn("hidden lg:flex p-2 shrink-0", rail ? "mt-auto justify-center" : "justify-end")}>
          <button className="btn !px-2" onClick={() => setRail(!rail)} aria-pressed={rail} aria-label={rail ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"} title={rail ? "Mở rộng" : "Thu gọn"}>
            {rail ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
          </button>
        </div>
      </nav>

      <Dialog open={more} onClose={() => setMore(false)} title="Tất cả trang">
        <nav aria-label="Tất cả trang" className="p-3 grid gap-3">
          {GROUPS.map((g) => (
            <section key={g} aria-label={g}>
              <div className="px-1 pb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">{g}</div>
              <div className="grid grid-cols-2 gap-2">
                {ROUTES.filter((r) => r.group === g).map((r) => (
                  <a key={r.id} href={`#/${r.id}`} aria-current={r.id === route.id ? "page" : undefined} onClick={() => setMore(false)}
                    className={cn("flex items-center gap-2 min-h-[44px] px-3 rounded-md border no-underline text-[13px]", r.id === route.id ? "border-accent text-accent bg-[var(--accent-bg)]" : "border-line text-fg bg-panel2")}>
                    <r.icon size={16} aria-hidden="true" /><span className="min-w-0">{r.label}</span><NavBadge id={r.id} />
                  </a>
                ))}
              </div>
            </section>
          ))}
        </nav>
      </Dialog>
      <Once on={palette}><CommandPalette open={palette} onClose={() => setPalette(false)} routes={ROUTES} label={cur?.label || ""} /></Once>
      <Once on={help}><Cheatsheet open={help} onClose={() => setHelp(false)} /></Once>
      <Once on={bell}><NotificationCenter open={bell} onClose={() => setBell(false)} /></Once>
      <UxRoot route={route} label={cur?.label || ""} onBell={() => setBell(true)} onHelp={() => setHelp(true)} onRail={() => setRail(!rail)} onPalette={() => setPalette(true)} />
      {gArmed && <GPending />}
      <main id="main" tabIndex={-1} className="flex-1 min-h-0 lg:overflow-y-auto p-3 lg:p-4 outline-none">
        <div className={cn("page", route.id === "thi-truong" && "page-fixed", route.id === "terminal" && "page-terminal")}>
          <Boundary k={route.id}>
            <Suspense fallback={<Skeleton rows={8} h={18} />}>
              {Page && <Page key={route.id === "cai-dat" ? "ux" : fmtVer} arg={route.arg} />}
            </Suspense>
          </Boundary>
        </div>
      </main>
    </div>
  );
}

/** Nạp lười một lần: chỉ dựng (và tải chunk) khi `on` lần đầu bằng true, sau đó giữ nguyên để hộp thoại tự điều khiển open/close. */
function Once({ on, children }) {
  const [seen, setSeen] = useState(false);
  if (on && !seen) setSeen(true);
  return seen ? <Suspense fallback={null}>{children}</Suspense> : null;
}

function Logo({ full }) {
  return (
    <span className="flex items-center gap-2">
      <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="var(--panel2)" stroke="var(--line2)" /><path d="M6 21l6-7 5 4 9-11" fill="none" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /><circle cx="26" cy="7" r="2.2" fill="var(--up)" /></svg>
      {full && <span className="leading-tight"><b className="block text-[13.5px]">Trạm thị trường</b><span className="text-[11px] text-muted">chỉ-đọc · giờ Việt Nam</span></span>}
    </span>
  );
}
