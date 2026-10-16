// Hook React cho SDK realtime (lib/realtime.js). BYTE-GIỐNG ở web-ui và client-ui.
// Quy tắc: hook luôn được gọi vô điều kiện; symbol/topic rỗng => không đăng ký, trả giá trị rỗng. Re-render gộp tối đa theo mỗi khung hình.
import { useCallback, useMemo, useRef, useSyncExternalStore } from "react";
import { subscribe, peek, onStatus, getStatus } from "./realtime.js";

const raf = (fn) => {
  if (typeof requestAnimationFrame === "function" && typeof document !== "undefined" && !document.hidden) requestAnimationFrame(fn);
  else setTimeout(fn, 50);
};

/** subscribe() tương thích useSyncExternalStore: gộp thông báo mỗi khung hình. */
function coalesced(topics, onChange, bump) {
  let queued = false;
  let dead = false;
  const note = () => {
    if (bump) bump();
    if (queued || dead) return;
    queued = true;
    raf(() => {
      queued = false;
      if (!dead) onChange();
    });
  };
  const offs = topics.map((t) => subscribe(t, note));
  return () => {
    dead = true;
    offs.forEach((f) => f());
  };
}

const EMPTY_Q = Object.freeze({ bid: null, ask: null, t: null, stale: true, dir: 0, mid: null });

function toQuote(e) {
  const d = e && e.d;
  if (!d) return EMPTY_Q;
  const bid = typeof d.b === "number" ? d.b : null;
  const ask = typeof d.a === "number" ? d.a : null;
  return { bid, ask, t: d.t ?? null, stale: d.q === 1, dir: e.dir || 0, mid: bid != null && ask != null ? (bid + ask) / 2 : bid ?? ask };
}

/** Trạng thái kết nối: 'connecting' | 'open' | 'closed' | 'sse'. */
export function useRealtimeStatus() {
  return useSyncExternalStore(onStatus, getStatus, () => "closed");
}

/** true khi dữ liệu đang được đẩy (WS 'open' hoặc SSE) -> UI dùng để giảm/tắt polling REST. */
export function useRealtimeLive() {
  const s = useRealtimeStatus();
  return s === "open" || s === "sse";
}

/** Dữ liệu một topic bất kỳ: {data, seq, status}. */
export function useLiveTopic(topic) {
  const sub = useCallback((cb) => (topic ? coalesced([topic], cb) : () => {}), [topic]);
  const entry = useSyncExternalStore(sub, () => (topic ? peek(topic) : undefined), () => undefined);
  const status = useRealtimeStatus();
  return useMemo(() => ({ data: entry && entry.d != null ? entry.d : null, seq: entry ? entry.q : null, status }), [entry, status]);
}

/** Giá một symbol: {bid, ask, t, stale, dir(1|-1|0), mid}. */
export function useLiveQuote(symbol) {
  const topic = symbol ? `q:${symbol}` : "";
  const sub = useCallback((cb) => (topic ? coalesced([topic], cb) : () => {}), [topic]);
  const entry = useSyncExternalStore(sub, () => (topic ? peek(topic) : undefined), () => undefined);
  return useMemo(() => toQuote(entry), [entry]);
}

/** Giá nhiều symbol: Map<symbol, {bid, ask, t, stale, dir, mid}> (chỉ gồm symbol đã có dữ liệu). */
export function useLiveQuotes(symbols) {
  const key = (Array.isArray(symbols) ? symbols : []).filter(Boolean).join(",");
  const ver = useRef(0);
  const sub = useCallback(
    (cb) => (key ? coalesced(key.split(",").map((s) => `q:${s}`), cb, () => { ver.current++; }) : () => {}),
    [key],
  );
  const v = useSyncExternalStore(sub, () => ver.current, () => 0);
  return useMemo(() => {
    const m = new Map();
    if (!key) return m;
    for (const s of key.split(",")) {
      const e = peek(`q:${s}`);
      if (e && e.d) m.set(s, toQuote(e));
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, v]);
}

/** Nến đang hình thành {t,o,h,l,c,v,...} hoặc null. */
export function useLiveCandle(symbol, tf) {
  const topic = symbol && tf ? `c:${symbol}:${tf}` : "";
  const sub = useCallback((cb) => (topic ? coalesced([topic], cb) : () => {}), [topic]);
  const entry = useSyncExternalStore(sub, () => (topic ? peek(topic) : undefined), () => undefined);
  return entry && entry.d ? entry.d : null;
}
