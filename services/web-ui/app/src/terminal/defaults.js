// Workspace mặc định / mẫu. Lưới 24 cột; 1 hàng ≈ 36px (28px + khoảng cách 8px).
// `t` có thể là mảng phương án (lấy widget đầu tiên đang tồn tại) để workspace vẫn đẹp khi widget của agent khác chưa có.
import { WIDGETS } from "./registry";

const W = (t, x, y, w, h, c, k) => ({ t, x, y, w, h, c, k });

export const TEMPLATES = [
  {
    id: "overview", name: "Tổng quan", desc: "Bảng giá, biểu đồ, lịch, tin, tài khoản, cảnh báo, hệ thống",
    widgets: [
      W("ticker-tape", 0, 0, 24, 2),
      W("watchlist", 0, 2, 8, 16, { src: "group" }, "red"),
      W(["chart", "quote-card"], 8, 2, 10, 11, undefined, "red"),
      W(["heatmap", "heat-strip"], 8, 13, 10, 5),
      W("calendar-upcoming", 18, 2, 6, 8),
      W(["news", "news-latest"], 18, 10, 6, 8),
      W("account-mini", 0, 18, 7, 8),
      W("alerts-recent", 7, 18, 8, 8),
      W("system-status", 15, 18, 5, 8),
      W("clocks", 20, 18, 4, 8),
    ],
  },
  {
    id: "forex", name: "Forex", desc: "Cặp tiền, kim loại, biểu đồ, lịch kinh tế",
    widgets: [
      W("ticker-tape", 0, 0, 24, 2, { cls: "forex" }),
      W("watchlist", 0, 2, 7, 18, { src: "class", cls: "forex" }, "blue"),
      W(["chart", "quote-card"], 7, 2, 11, 12, undefined, "blue"),
      W(["heatmap", "heat-strip"], 7, 14, 11, 6, { cls: "forex" }),
      W("calendar-upcoming", 18, 2, 6, 10),
      W("clocks", 18, 12, 6, 8),
      W("notes", 0, 20, 8, 7),
      W("account-mini", 8, 20, 8, 7),
      W("alerts-recent", 16, 20, 8, 7),
    ],
  },
  {
    id: "crypto", name: "Crypto", desc: "Tiền ảo 24/7, biểu đồ, biến động",
    widgets: [
      W("ticker-tape", 0, 0, 24, 2, { cls: "crypto" }),
      W("watchlist", 0, 2, 7, 18, { src: "class", cls: "crypto" }, "orange"),
      W(["chart", "quote-card"], 7, 2, 11, 12, undefined, "orange"),
      W(["heatmap", "heat-strip"], 7, 14, 11, 6, { cls: "crypto" }),
      W("top-movers", 18, 2, 6, 10),
      W(["news", "news-latest"], 18, 12, 6, 8),
      W("alerts-recent", 0, 20, 12, 7),
      W("notes", 12, 20, 12, 7),
    ],
  },
  {
    id: "vn", name: "Chứng khoán VN", desc: "Cổ phiếu và chỉ số Việt Nam theo phiên Hà Nội",
    widgets: [
      W("ticker-tape", 0, 0, 24, 2, { cls: "vn" }),
      W("watchlist", 0, 2, 8, 18, { src: "class", cls: "vn" }, "green"),
      W(["chart", "quote-card"], 8, 2, 10, 12, undefined, "green"),
      W(["heatmap", "heat-strip"], 8, 14, 10, 6, { cls: "vn" }),
      W(["news", "news-latest"], 18, 2, 6, 12),
      W("clocks", 18, 14, 6, 6, { zones: ["Asia/Ho_Chi_Minh", "Asia/Tokyo", "America/New_York"] }),
      W("notes", 0, 20, 12, 7),
      W("alerts-recent", 12, 20, 12, 7),
    ],
  },
  {
    id: "news", name: "Tin & Lịch", desc: "Tin tức, lịch kinh tế, cảnh báo, phiên giao dịch",
    widgets: [
      W("ticker-tape", 0, 0, 24, 2),
      W(["news", "news-latest"], 0, 2, 10, 20),
      W("calendar-upcoming", 10, 2, 8, 20),
      W("clocks", 18, 2, 6, 9),
      W("alerts-recent", 18, 11, 6, 11),
      W("watchlist", 0, 22, 12, 8, { src: "group" }),
      W("notes", 12, 22, 12, 8),
    ],
  },
  {
    id: "account", name: "Tài khoản & rủi ro", desc: "Tài khoản MT (chỉ đọc), vị thế đang mở, cửa sổ rủi ro tin, cảnh báo, biểu đồ",
    widgets: [
      W("account-mini", 0, 0, 8, 9),
      W("positions-open", 8, 0, 10, 9, undefined, "yellow"),
      W("risk-windows", 18, 0, 6, 9),
      W(["chart", "quote-card"], 0, 9, 14, 12, undefined, "yellow"),
      W("alerts-recent", 14, 9, 10, 6),
      W("calendar-upcoming", 14, 15, 10, 6),
    ],
  },
  { id: "blank", name: "Trống", desc: "Bắt đầu từ trang trắng", widgets: [] },
];
export const DEFAULT_SET = ["overview", "forex", "crypto", "vn", "news"];

/** Chuyển mẫu thành danh sách widget thật (bỏ widget chưa tồn tại). */
export function buildWidgets(tpl, nid) {
  const out = [];
  for (const w of tpl.widgets) {
    const alts = Array.isArray(w.t) ? w.t : [w.t];
    const t = alts.find((x) => WIDGETS[x]);
    if (!t) continue;
    const o = { i: nid(), t, x: w.x, y: w.y, w: w.w, h: w.h };
    if (w.c) o.c = w.c;
    if (w.k) o.k = w.k;
    out.push(o);
  }
  return out;
}
