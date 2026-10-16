// Hành động dùng chung cho Ctrl-K, phím tắt, công cụ trang. Mọi thao tác chỉ ảnh hưởng UI/prefs của người dùng (không có lệnh giao dịch).
import { MAX_SYMBOLS, SYM_RE, activeGroup, getPrefsState, mutatePrefs, newGroupId, watchlistsOf } from "../lib/prefs";
import { toast } from "./bus";

/** Thêm mã vào nhóm theo dõi đang dùng (tạo nhóm "Của tôi" nếu chưa có). Trả {ok, msg}. */
export function addToWatchlist(symbol) {
  const sym = String(symbol || "").trim();
  if (!SYM_RE.test(sym)) return { ok: false, msg: "Mã không hợp lệ." };
  const st = getPrefsState();
  if (!st.loaded || !st.available) return { ok: false, msg: "Chưa lưu được tuỳ chọn (máy chủ chưa sẵn sàng). Thử lại sau." };
  const g = activeGroup(st.prefs);
  if (g?.symbols?.includes(sym)) return { ok: true, msg: `${sym} đã có trong “${g.name}”.`, dup: true };
  if (g && g.symbols.length >= MAX_SYMBOLS) return { ok: false, msg: `Nhóm “${g.name}” đã đủ ${MAX_SYMBOLS} mã.` };
  let name = g?.name || "Của tôi";
  const ok = mutatePrefs((p) => {
    const ws = watchlistsOf(p);
    const cur = activeGroup(p);
    if (!cur) { const id = newGroupId(); return { ...p, watchlists: [{ id, name: "Của tôi", symbols: [sym], tf: "H1" }], active_watchlist: id }; }
    name = cur.name;
    return { ...p, watchlists: ws.map((w) => (w.id === cur.id ? { ...w, symbols: [...w.symbols, sym] } : w)) };
  });
  return ok ? { ok: true, msg: `Đã thêm ${sym} vào “${name}”.` } : { ok: false, msg: "Không thêm được (vượt giới hạn dung lượng)." };
}
export function addToWatchlistToast(symbol) {
  const r = addToWatchlist(symbol);
  toast({ tone: r.ok ? "ok" : "error", title: r.msg, ttl: 4000, href: r.ok ? "#/danh-sach" : undefined, actionLabel: "Mở danh sách" });
  return r;
}

/** Sao chép văn bản; trả true nếu thành công. */
export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {
    try {
      const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); ta.remove(); return ok;
    } catch { return false; }
  }
}

/** Sự kiện điều khiển giao diện cấp ứng dụng (App lắng nghe). name: palette|help|bell|rail|tour|theme */
export const appCmd = (name, detail) => dispatchEvent(new CustomEvent("ts-cmd", { detail: { name, ...detail } }));
