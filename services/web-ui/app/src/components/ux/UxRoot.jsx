// Gốc hệ thống UX xuyên suốt: áp cài đặt, đồng bộ prefs máy chủ, toast, cầu thông báo, tour, ghi trang gần đây, điều hướng bàn phím trong bảng,
// vùng thông báo cho trình đọc màn hình, tiêu đề in. Một component, gắn một lần trong App.
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import "../../ux/ux.css";
import { adoptServer, startUx, useSettings } from "../../ux/settings";
import { usePrefsState } from "../../lib/prefs";
import { pushRecent } from "../../ux/recent";
import { tzOffsetLabel, isVnTz } from "../../ux/fmtconfig";
import { dateTime } from "../../lib/format";
import { Toaster } from "./Toaster";
import { NotifyBridge } from "./NotifyBridge";
const Onboarding = lazy(() => import("./Onboarding").then((m) => ({ default: m.Onboarding })));
const TOUR_VERSION = 1; // giữ khớp Onboarding.TOUR_VERSION

startUx();
const typing = (t) => !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

/** Mũi tên trong bảng: khi đang ở nút/liên kết/ô của bảng, ↑↓ nhảy cùng cột dòng kế, Home/End về đầu/cuối dòng. */
function tableKeys(e) {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
  if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
  const t = e.target;
  if (!(t instanceof Element) || typing(t) || t.closest("[role=listbox],[role=menu],[role=dialog],[role=tablist],[role=combobox]")) return;
  const cell = t.closest("td,th");
  const table = cell?.closest("table");
  if (!cell || !table || (t !== cell && !t.matches("a,button,[tabindex]"))) return;
  const row = cell.parentElement;
  const col = [...row.children].indexOf(cell);
  const focusables = (c) => (c ? [...c.querySelectorAll("a[href],button:not([disabled]),[tabindex='0']")].filter((x) => x.getClientRects().length) : []);
  const go = (c) => { const f = focusables(c)[0] || c; if (f && !f.matches("a,button,[tabindex]")) f.tabIndex = -1; f?.focus({ preventScroll: false }); return !!f; };
  if (e.key === "Home" || e.key === "End") {
    const cells = [...row.children].filter((c) => focusables(c).length || c === cell);
    const dest = e.key === "Home" ? cells[0] : cells[cells.length - 1];
    if (dest && dest !== cell) { e.preventDefault(); go(dest); }
    return;
  }
  let r = row;
  for (let n = 0; n < 200; n++) {
    r = e.key === "ArrowDown" ? r.nextElementSibling || (r.parentElement.tagName === "THEAD" ? r.parentElement.nextElementSibling?.firstElementChild : null) : r.previousElementSibling;
    if (!r) return;
    const c = r.children[col];
    if (c && (focusables(c).length || t === cell)) { e.preventDefault(); go(c); return; }
  }
}

export function UxRoot({ route, label, onBell, onHelp, onRail, onPalette }) {
  const [s] = useSettings();
  const prefs = usePrefsState();
  const [announce, setAnnounce] = useState("");
  const [tourReq, setTourReq] = useState(0);
  const tourOn = tourReq > 0 || s.onboarded < TOUR_VERSION;
  const fn = useRef({});
  fn.current = { onBell, onHelp, onRail, onPalette };

  useEffect(() => { if (prefs.loaded) adoptServer(prefs.prefs?.ux); }, [prefs.loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // lệnh cấp ứng dụng từ Ctrl-K / menu (ts-cmd)
  useEffect(() => {
    const h = (e) => { const n = e.detail?.name; const f = fn.current; if (n === "tour") setTourReq((x) => x + 1); else if (n === "bell") f.onBell?.(); else if (n === "help") f.onHelp?.(); else if (n === "rail") f.onRail?.(); else if (n === "palette") f.onPalette?.(); };
    addEventListener("ts-cmd", h);
    return () => removeEventListener("ts-cmd", h);
  }, []);

  // phím: Alt+N mở thông báo; điều hướng mũi tên trong bảng
  useEffect(() => {
    const k = (e) => {
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.toLowerCase() === "n" && !e.isComposing) { e.preventDefault(); fn.current.onBell?.(); return; }
      tableKeys(e);
    };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, []);

  // ghi lịch sử + thông báo chuyển trang cho trình đọc màn hình
  useEffect(() => {
    const href = `#/${route.id}${route.arg ? `/${route.arg}` : ""}`;
    const arg = route.arg ? decodeURIComponent(route.arg.split("?")[0]) : "";
    pushRecent({ key: href, href, label: `${label}${arg ? ` · ${arg.replace(/^[A-Za-z]+:/, "")}` : ""}`, kind: arg && route.id === "thi-truong" ? "symbol" : "page" });
    setAnnounce(`Đã mở trang ${label}`);
  }, [route.id, route.arg, label]);

  // vùng cuộn phải truy cập được bằng bàn phím (WCAG 2.1.1) + có tên cho trình đọc màn hình
  useEffect(() => {
    let raf = 0;
    const fix = () => {
      raf = 0;
      document.querySelectorAll("#main .scroll-y, #main .scroll-x, #main [class*='overflow-auto'], #main [class*='overflow-y-auto'], #main [class*='overflow-x-auto']").forEach((el) => {
        if (el.dataset.uxScroll) return;
        el.dataset.uxScroll = "1";
        if (el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1) { delete el.dataset.uxScroll; return; }
        if (!el.querySelector("a[href],button,input,select,textarea,[tabindex='0']") && !el.hasAttribute("tabindex")) {
          el.tabIndex = 0; el.setAttribute("role", "region");
          if (!el.getAttribute("aria-label") && !el.getAttribute("aria-labelledby")) el.setAttribute("aria-label", (el.closest("section")?.querySelector("h2")?.textContent || "Vùng cuộn") + " (cuộn được)");
        }
      });
    };
    const mo = new MutationObserver(() => { if (!raf) raf = setTimeout(fix, 1200); });
    mo.observe(document.getElementById("main") || document.body, { childList: true, subtree: true });
    const t = setTimeout(fix, 600);
    return () => { mo.disconnect(); clearTimeout(t); clearTimeout(raf); };
  }, [route.id]);

  return (
    <>
      <Toaster />
      <NotifyBridge />
      {tourOn && <Suspense fallback={null}><Onboarding seq={tourReq} /></Suspense>}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announce}</div>
      <div className="print-head" aria-hidden="true">
        <b>Trạm thị trường</b> · {label}{route.arg ? ` · ${decodeURIComponent(route.arg.split("?")[0])}` : ""} · {dateTime(Date.now())} {isVnTz() ? "(giờ VN)" : `(${tzOffsetLabel()})`}
        <div>{location.href}</div>
        <div>Dữ liệu tham khảo, không phải khuyến nghị đầu tư.</div>
      </div>
      {!isVnTz() && s.tz !== "vn" && <span className="sr-only">Múi giờ hiển thị {tzOffsetLabel()}</span>}
    </>
  );
}
