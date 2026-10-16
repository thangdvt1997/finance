// Nhận ý định tự nhiên (docs/handoff/INTENT_API.md). Mọi lỗi/ quá hạn -> null: KHÔNG bao giờ chặn gửi chat thường.
import { cpost } from "./classApi";

const enc = encodeURIComponent;
export async function understand(rid, text, timeoutMs = 4000) {
  if (!rid) return null;
  let h;
  try {
    return await Promise.race([
      cpost(`/rooms/${enc(rid)}/understand`, { text }),
      new Promise((_, rej) => { h = setTimeout(() => rej(new Error("timeout")), timeoutMs); }),
    ]);
  } catch { return null; } finally { clearTimeout(h); }
}
/** outcome: clicked | ignored | not_this. option_id lấy từ options[].id (hoặc `${und.id}:intent:${key}`). Không báo lỗi. */
export const optFeedback = (rid, option_id, outcome, kind) => { if (rid && option_id) cpost(`/rooms/${enc(rid)}/options/feedback`, { option_id, outcome, ...(kind ? { kind } : {}) }).catch(() => {}); };

const SYM = /^[A-Z][A-Z0-9._]{2,11}$/, TFS = ["m15", "h1", "h4", "d1"];
/** Lệnh nội bộ "thử mã/ khung khác" (quét ví dụ) từ form thẻ xác nhận; sai định dạng -> null. */
export function marketCommand(symbol, tf) {
  const s = String(symbol || "").trim().toUpperCase(), f = String(tf || "").trim().toLowerCase();
  if (s && !SYM.test(s)) return null;
  if (f && !TFS.includes(f)) return null;
  return `/quet${s ? ` symbol=${s}` : ""}${f ? ` tf=${f}` : ""} limit=8`;
}
/** Tách text thành đoạn có/ không tô sáng theo highlights [{start,end}]. */
export function splitHighlights(text, hs) {
  const out = []; let p = 0;
  for (const h of [...(hs || [])].sort((a, b) => a.start - b.start)) {
    if (h.start < p || h.end > text.length || h.start >= h.end) continue;
    if (h.start > p) out.push({ t: text.slice(p, h.start), hl: false });
    out.push({ t: text.slice(h.start, h.end), hl: true }); p = h.end;
  }
  if (p < text.length) out.push({ t: text.slice(p), hl: false });
  return out;
}
