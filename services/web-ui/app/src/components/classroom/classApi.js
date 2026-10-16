// Lớp API "AI Training Class" (hợp đồng: docs/handoff/AI_CLASSROOM_API.md). Chỉ nghiên cứu/paper — không có lệnh đặt lệnh.
import { api, apiWrite, ApiError, getCsrf } from "../../lib/api";
import { readSSE } from "./sse";

const B = "/ai-trading/class";
export const cget = (path, params, signal) => api(`${B}${path}`, params || {}, signal);
export const cpost = (path, body, opts) => apiWrite("POST", `${B}${path}`, body ?? {}, { maxBytes: 3_000_000, ...opts });
export const mediaUrl = (u) => (u ? (/^https?:/.test(u) ? null : u.startsWith("/api/") ? u : `/api${u.startsWith("/") ? "" : "/"}${u}`) : null);

/** Gửi tin nhắn, đọc SSE. handlers: {user, meta, delta, turn, action, done, error}. Trả Promise (hết luồng). */
export async function streamMessage(rid, text, handlers, signal, client_id) {
  const token = await getCsrf();
  let res;
  try {
    res = await fetch(`/api/v1${B}/rooms/${encodeURIComponent(rid)}/messages`, {
      method: "POST", credentials: "same-origin", signal,
      headers: { Accept: "text/event-stream", "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ text, client_id }),
    });
  } catch (e) { if (e.name === "AbortError") return; throw new ApiError(0, "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại."); }
  if (!res.ok) {
    let d = ""; try { d = (await res.json()).detail; } catch { /* bỏ */ }
    throw new ApiError(res.status, res.status === 429 ? "AI đang nhận quá nhiều tin, đợi vài giây rồi gửi lại." : (typeof d === "string" && d) || `Lỗi ${res.status} từ máy chủ.`);
  }
  await readSSE(res, ({ data }) => { const h = handlers[data?.type]; if (h) h(data); }, signal);
}

/** File -> base64 (không tiền tố). */
export const fileB64 = (file) => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(",")[1] || ""); fr.onerror = () => rej(new Error("Không đọc được tệp")); fr.readAsDataURL(file); });
export const KIND_BY_EXT = { png: "image", jpg: "image", jpeg: "image", webp: "image", yaml: "yaml", yml: "yaml", csv: "csv", pdf: "pdf", txt: "note", md: "note" };
export const LIMIT = { image: 700 * 1024, yaml: 64 * 1024, csv: 256 * 1024, pdf: 1.5 * 1024 * 1024, note: 4000 };

// Hành động gợi ý (nội bộ dùng mã /; người dùng chỉ thấy mô tả tự nhiên) (khớp docs/AI_CLASSROOM.md): [lệnh, gợi ý tham số, mô tả vi, mô tả en]
export const COMMANDS = [
  ["/test", "[mode=dev|walkforward]", "Backtest trung thực (cần xác nhận)", "Honest backtest (needs confirmation)"],
  ["/quet", "[limit=8] [symbol=] [tf=]", "Quét lịch sử, ảnh nến để gắn nhãn", "Scan history, candle images to label"],
  ["/bien-the", "", "Biến thể, đối lập, phản ví dụ", "Variants, opposites, counter-examples"],
  ["/doi-xung", "", "Phiên bản mua đối xứng", "Mirrored (buy) version"],
  ["/so-sanh", "[vs=buy_hold|random]", "So với mua-giữ/ngẫu nhiên", "Compare to buy-hold/random"],
  ["/giai-thich", "<phần>", "AI giải thích một phần", "AI explains a part"],
  ["/tom-tat", "", "AI hiểu như sau (độ chắc chắn)", "What the AI understood (confidence)"],
  ["/luu", "[ghi chú]", "Lưu phiên bản hồ sơ", "Save profile version"],
  ["/hoi-them", "", "Giả định ngầm, biên, phản ví dụ", "Hidden assumptions, edges, counter-examples"],
  ["/ve", "kind=dinh|day|vung|diem-vao|song", "Vẽ chú thích lên biểu đồ", "Draw annotation on chart"],
  ["/dat-lai", "xacnhan=co", "Đặt lại hồ sơ phiên này", "Reset this profile"],
];
export const LOCAL_CMDS = new Set(["bien-the", "doi-xung", "giai-thich", "tom-tat", "hoi-them", "dat-lai"]);

/** Tin người dùng dạng mã nội bộ ("/test"...) -> câu tự nhiên để hiển thị; tin thường giữ nguyên. */
export const cmdLabel = (text, en) => { const m = /^\/([a-z-]+)(?:\s|$)/.exec(String(text || "").trim()); if (!m) return null; const c = COMMANDS.find((x) => x[0] === `/${m[1]}`); return c ? (en ? c[3] : c[2]) : null; };
