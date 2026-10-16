// Một kết nối WebSocket duy nhất tới /api/v1/stream (nginx chèn X-API-Key khi nâng cấp kết nối).
import { useSyncExternalStore } from "react";

const state = {
  status: "connecting", // connecting | open | closed
  lastMsgAt: 0,
  quotes: new Map(),
  events: [],
  count: 0,
  version: 0,
};
const subs = new Set();
const barSubs = new Set();
const streamSubs = new Set();
let ver = 0;
const emit = () => {
  state.version = ++ver;
  subs.forEach((f) => f());
};

export function seedQuotes(list) {
  let changed = false;
  for (const q of list || []) {
    const cur = state.quotes.get(q.symbol);
    if (!cur || new Date(q.ts) > new Date(cur.ts)) {
      state.quotes.set(q.symbol, { ...q, dir: 0 });
      changed = true;
    }
  }
  if (changed) emit();
}
/** Giá từ kênh rt (lib/rtbridge.js): d = {b,a,t,q}. Ghi vào cùng kho với legacy để mọi useQuote() đều thấy. */
export function pushRtQuote(symbol, d) {
  if (!symbol || !d) return;
  const cur = state.quotes.get(symbol);
  const mid = d.b ?? d.a;
  const pm = cur ? (cur.bid ?? cur.ask) : mid;
  state.quotes.set(symbol, {
    symbol, bid: d.b, ask: d.a, ts: new Date(d.t || Date.now()).toISOString(), stale: d.q === 1, rt: true, rtAt: Date.now(),
    dir: mid > pm ? 1 : mid < pm ? -1 : cur?.dir || 0,
    tickId: (cur?.tickId || 0) + 1,
  });
  scheduleEmit();
}
/** Nhận MỌI sự kiện không phải giá (tin, cảnh báo, lịch...): fn({stream,id,event}). Dùng cho terminal tin tức. */
export const onStreamEvent = (fn) => {
  streamSubs.add(fn);
  return () => streamSubs.delete(fn);
};
export const onBar = (fn) => {
  barSubs.add(fn);
  return () => barSubs.delete(fn);
};
/** Gọi fn(quote) mỗi khi symbol có tick mới (dùng cho biểu đồ nến). */
export const onTick = (symbol, fn) => {
  let last = state.quotes.get(symbol)?.tickId;
  const h = () => {
    const q = state.quotes.get(symbol);
    if (q && q.tickId !== last) {
      last = q.tickId;
      fn(q);
    }
  };
  subs.add(h);
  return () => subs.delete(h);
};

let pending = false;
function scheduleEmit() {
  if (pending) return;
  pending = true;
  setTimeout(() => {
    pending = false;
    emit();
  }, 250);
}

function handle(msg) {
  state.lastMsgAt = Date.now();
  if (msg.type === "ready") {
    state.status = "open";
    emit();
    return;
  }
  if (msg.type !== "event") return;
  state.count++;
  const ev = msg.event;
  const p = ev.payload || {};
  if (msg.stream === "md.quotes" && p.symbol) {
    const cur = state.quotes.get(p.symbol);
    if (cur && cur.rt && Date.now() - cur.rtAt < 5000) return; // kênh rt đang đẩy giá symbol này: bỏ qua bản legacy (tránh nhảy nguồn)
    const mid = p.bid ?? p.ask;
    const pm = cur ? (cur.bid ?? cur.ask) : mid;
    state.quotes.set(p.symbol, {
      symbol: p.symbol, bid: p.bid, ask: p.ask, ts: p.ts || ev.ts, source: p.source,
      dir: mid > pm ? 1 : mid < pm ? -1 : cur?.dir || 0,
      tickId: (cur?.tickId || 0) + 1,
    });
  } else if (msg.stream === "md.bars") {
    barSubs.forEach((f) => f(p));
  } else {
    streamSubs.forEach((f) => f(msg));
    state.events = [{ stream: msg.stream, id: msg.id, ts: ev.ts, payload: p, type: ev.type }, ...state.events].slice(0, 50);
  }
  scheduleEmit();
}

let ws, retry = 0, started = false, timer;
function schedule() {
  retry = Math.min(retry + 1, 6);
  timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** retry));
}
function connect() {
  clearTimeout(timer);
  state.status = "connecting";
  emit();
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const streams = "md.quotes,md.bars,news.items,news.enriched,alerts.out,expert.signals,account.snapshots,calendar.events";
  try {
    ws = new WebSocket(`${proto}//${location.host}/api/v1/stream?streams=${streams}`);
  } catch {
    schedule();
    return;
  }
  ws.onmessage = (e) => {
    try {
      handle(JSON.parse(e.data));
    } catch {
      /* bỏ qua khung hỏng */
    }
  };
  ws.onopen = () => {
    retry = 0;
  };
  ws.onclose = () => {
    state.status = "closed";
    emit();
    schedule();
  };
  ws.onerror = () => ws.close();
}
/** Nối lại ngay (nút "Nối lại ngay" của banner mất kết nối). */
export function reconnectNow() {
  if (ws && ws.readyState <= 1) return;
  retry = 0;
  connect();
}
/** Vai không có quyền stream (chuyên gia): không kết nối, trạng thái "off" -> chỉ báo trực tiếp tự ẩn. */
export function disableStream() {
  state.status = "off";
  emit();
}
export function startStream() {
  if (!started) {
    started = true;
    connect();
  }
}

const subscribe = (fn) => {
  subs.add(fn);
  return () => subs.delete(fn);
};
const snap = () => state.version;
export function useStream() {
  useSyncExternalStore(subscribe, snap);
  return state;
}
export function useQuote(symbol) {
  useSyncExternalStore(subscribe, snap);
  return state.quotes.get(symbol);
}
// Nhắc lịch kinh tế đã đặt: nạp nền để bộ hẹn giờ chạy trên mọi trang (xem lib/calendarPro.js)
import("./calendarPro").catch(() => {});
