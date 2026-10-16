// SDK realtime rt.v1 (docs/REALTIME.md). ES module, KHÔNG phụ thuộc thư viện. File này BYTE-GIỐNG ở web-ui và client-ui (kiểm: cmp).
// Một kết nối / tab (WebSocket, rơi sang SSE khi WS liên tục lỗi). Topic: q:SYM | c:SYM:TF | a:ACC | e:ACC | n | sys.
//   const off = subscribe("q:EURUSD", (d, meta) => ..., {replay:true});  off();
// cb(d, meta): meta = {topic, seq, snap, reset, replay}. reset=true: mất đồng bộ -> nên tải lại bằng REST (topic reliable e:/n/sys).
// Suy giảm êm: không mở được => getStatus() != "open"/"sse" và UI tự dùng polling REST như trước.

const BASE = (() => {
  try {
    return location.pathname.startsWith("/c/") ? "/c/api/v1/rt" : "/api/v1/rt";
  } catch {
    return "/api/v1/rt";
  }
})();

const RELIABLE = (t) => t === "n" || t === "sys" || t.startsWith("e:");
const kindOf = (t) => (t === "n" || t === "sys" ? t : t.slice(0, t.indexOf(":")));
const DEBOUNCE_MS = 20;
const IDLE_HIDDEN_MS = 30_000;
const LAT_EVERY_MS = 30_000;
const LAT_MAX = 20;
const WS_FAILS_TO_SSE = 3;
const SSE_RETRY_WS_MS = 300_000;
const KICK_PAUSE_MS = 30_000;

// ---- trạng thái module (singleton) ----
const subs = new Map(); // topic -> Set<cb>
const store = new Map(); // topic -> {d, q, prev, dir, at, snap}
const lastSeq = new Map(); // topic reliable -> seq cuối đã nhận liên tục
const active = new Set(); // topic đã gửi sub trên kết nối hiện tại
const rejected = new Set(); // topic bị từ chối vĩnh viễn (forbidden/bad_topic)
const resync = new Set();
const idleSince = new Map();
const statusSubs = new Set();

let status = "closed"; // connecting | open | closed | sse
let ws = null;
let es = null;
let esKey = "";
let mode = "ws"; // ws | sse
let helloed = false;
let epoch = null;
let hbSec = 15;
let attempt = 0;
let fails = 0;
let openedAt = 0;
let byeReason = "";
let reconnectTimer = null;
let flushTimer = null;
let pingTimer = null;
let latTimer = null;
let watchTimer = null;
let hiddenTimer = null;
let sseRetryTimer = null;
let idleClosed = false;
let pauseUntil = 0;
let lastRecv = 0;
let lastRtt = null;
let rttWin = []; // [{rtt, off}] tối đa 8
let offset = null;
let hasPong = false;
let latSamples = [];
let latRing = [];
let msgCount = 0;
let frameCount = 0;
let started = false;

const safe = (fn) => {
  try {
    return fn();
  } catch {
    return undefined;
  }
};

function setStatus(s) {
  if (s === status) return;
  status = s;
  statusSubs.forEach((f) => safe(() => f(s)));
}
export const getStatus = () => status;
export function onStatus(fn) {
  statusSubs.add(fn);
  return () => statusSubs.delete(fn);
}
/** true khi dữ liệu đang được đẩy (WS mở hoặc SSE). UI dùng để giảm polling. */
export const isLive = () => status === "open" || status === "sse";

// ---- thống kê ----
function pct(arr, p) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))];
}
export function stats() {
  return {
    status,
    mode,
    msgs: msgCount,
    frames: frameCount,
    p50: pct(latRing, 50),
    p95: pct(latRing, 95),
    rtt: lastRtt,
    offset,
    lastRecv,
    topics: subs.size,
  };
}

// ---- API đọc store ----
export const peek = (topic) => store.get(topic);

// ---- đăng ký ----
export function subscribe(topic, cb, opts) {
  if (typeof topic !== "string" || !topic || typeof cb !== "function") return () => {};
  let set = subs.get(topic);
  if (!set) {
    set = new Set();
    subs.set(topic, set);
    idleSince.delete(topic);
  }
  set.add(cb);
  if (set.size === 1) scheduleFlush();
  ensureStarted();
  if (!opts || opts.replay !== false) {
    const e = store.get(topic);
    if (e && e.d != null) safe(() => cb(e.d, { topic, seq: e.q, snap: true, replay: true }));
  }
  let done = false;
  return () => {
    if (done) return;
    done = true;
    const s = subs.get(topic);
    if (!s) return;
    s.delete(cb);
    if (!s.size) {
      subs.delete(topic);
      rejected.delete(topic);
      idleSince.set(topic, Date.now());
      scheduleFlush();
    }
  };
}

function scheduleFlush() {
  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flush();
  }, DEBOUNCE_MS);
}

function sendJson(o) {
  if (ws && ws.readyState === 1) {
    try {
      ws.send(JSON.stringify(o));
      return true;
    } catch {
      /* ignore */
    }
  }
  return false;
}

function flush() {
  if (mode === "sse") {
    syncSse();
    return;
  }
  if (!ws || ws.readyState !== 1 || !helloed) return;
  const unsub = [];
  for (const t of [...active]) {
    if (!subs.has(t) || resync.has(t)) {
      unsub.push(t);
      active.delete(t);
    }
  }
  resync.clear();
  const sub = [];
  for (const t of subs.keys()) if (!active.has(t) && !rejected.has(t)) sub.push(t);
  for (let i = 0; i < unsub.length; i += 50) sendJson({ op: "unsub", topics: unsub.slice(i, i + 50) });
  for (let i = 0; i < sub.length; i += 50) {
    const chunk = sub.slice(i, i + 50);
    const resume = {};
    for (const t of chunk) if (RELIABLE(t) && lastSeq.has(t)) resume[t] = lastSeq.get(t);
    const m = { op: "sub", topics: chunk };
    if (Object.keys(resume).length) {
      m.resume = resume;
      m.ep = epoch;
    }
    if (sendJson(m)) chunk.forEach((t) => active.add(t));
  }
}

// ---- xử lý tin ----
function emitTopic(topic, d, meta) {
  const set = subs.get(topic);
  if (!set) return;
  for (const cb of [...set]) safe(() => cb(d, meta));
}

function put(topic, d, q, snap) {
  const old = store.get(topic);
  const e = { d, q, prev: old ? old.d : null, dir: old ? old.dir : 0, at: Date.now(), snap: !!snap };
  if (kindOf(topic) === "q" && d && old && old.d && typeof d.b === "number" && typeof old.d.b === "number") {
    if (d.b > old.d.b) e.dir = 1;
    else if (d.b < old.d.b) e.dir = -1;
  }
  store.set(topic, e);
  return e;
}

function gap(topic) {
  if (mode === "sse") {
    esKey = "";
    syncSse(true);
    return;
  }
  resync.add(topic);
  scheduleFlush();
}

function onMsg(m, recvMs) {
  const k = m.k;
  switch (m.t) {
    case "snap": {
      if (typeof k !== "string") return;
      msgCount++;
      if (m.ep != null && epoch != null && m.ep !== epoch) epoch = m.ep;
      if (RELIABLE(k)) {
        if (typeof m.q === "number") lastSeq.set(k, m.q);
        resync.delete(k);
        if (m.reset) {
          put(k, m.d ?? null, m.q, true);
          emitTopic(k, m.d ?? null, { topic: k, seq: m.q, snap: true, reset: true });
        } else if (m.d != null) {
          put(k, m.d, m.q, true);
          emitTopic(k, m.d, { topic: k, seq: m.q, snap: true });
        }
        return;
      }
      if (m.d == null) {
        const old = store.get(k);
        if (!old) store.set(k, { d: null, q: m.q, prev: null, dir: 0, at: Date.now(), snap: true });
        return;
      }
      put(k, m.d, m.q, true);
      emitTopic(k, m.d, { topic: k, seq: m.q, snap: true });
      return;
    }
    case "d": {
      if (typeof k !== "string") return;
      msgCount++;
      if (RELIABLE(k)) {
        const last = lastSeq.get(k);
        if (typeof m.q === "number" && last != null) {
          if (m.q <= last) return; // trùng (phát lại chồng lấp)
          if (m.q !== last + 1) {
            if (!resync.has(k)) gap(k);
            return;
          }
        }
        if (typeof m.q === "number") lastSeq.set(k, m.q);
        put(k, m.d, m.q, false);
        emitTopic(k, m.d, { topic: k, seq: m.q, snap: false });
        return;
      }
      put(k, m.d, m.q, false);
      emitTopic(k, m.d, { topic: k, seq: m.q, snap: false });
      return;
    }
    case "ok": {
      if (Array.isArray(m.e)) {
        for (const x of m.e) {
          if (!Array.isArray(x)) continue;
          const [t, code] = x;
          active.delete(t);
          if (code === "forbidden" || code === "bad_topic") rejected.add(t);
        }
      }
      return;
    }
    case "pong": {
      const rtt = recvMs - Number(m.c);
      if (!(rtt >= 0 && rtt < 60_000) || typeof m.s !== "number") return;
      lastRtt = rtt;
      hasPong = true;
      rttWin.push({ rtt, off: m.s - (Number(m.c) + rtt / 2) });
      if (rttWin.length > 8) rttWin.shift();
      let best = rttWin[0];
      for (const x of rttWin) if (x.rtt < best.rtt) best = x;
      offset = best.off;
      return;
    }
    default:
  }
}

function onFrame(obj) {
  const recv = Date.now();
  lastRecv = recv;
  const t = obj && obj.t;
  if (t === "b") {
    frameCount++;
    if (offset != null && typeof obj.st === "number") {
      const lat = recv + offset - obj.st;
      if (lat >= 0 && lat < 30_000) {
        latSamples.push(lat);
        if (latSamples.length > LAT_MAX) latSamples.shift();
        latRing.push(lat);
        if (latRing.length > 200) latRing.shift();
      }
    }
    if (Array.isArray(obj.m)) for (const m of obj.m) safe(() => onMsg(m, recv));
  } else if (t === "hello") {
    onHello(obj, recv);
  } else if (t === "bye") {
    byeReason = String(obj.c || "bye");
  }
}

function onHello(h, recv) {
  helloed = true;
  fails = 0;
  hbSec = Number(h.hb) > 0 ? Number(h.hb) : 15;
  if (typeof h.now === "number" && !hasPong) offset = h.now - recv; // ước lượng thô tới khi có pong
  if (epoch != null && h.ep !== epoch) {
    lastSeq.clear();
    for (const t of [...store.keys()]) if (RELIABLE(t)) store.delete(t);
  }
  epoch = h.ep ?? epoch;
  active.clear();
  resync.clear();
  setStatus(mode === "sse" ? "sse" : "open");
  if (mode === "ws") {
    startPing();
    scheduleFlush();
  }
  startLat();
}

// ---- ping / độ trễ / watchdog ----
function startPing() {
  stopPing();
  const send = () => sendJson({ op: "ping", t: Date.now(), r: lastRtt == null ? undefined : Math.round(lastRtt) });
  send();
  pingTimer = setInterval(send, hbSec * 1000);
}
function stopPing() {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = null;
}
function startLat() {
  if (latTimer) return;
  latTimer = setInterval(() => {
    if (mode !== "ws" || !latSamples.length) return;
    if (sendJson({ op: "lat", s: latSamples.slice(-LAT_MAX).map((x) => Math.round(x)) })) latSamples = [];
  }, LAT_EVERY_MS);
}
function stopLat() {
  if (latTimer) clearInterval(latTimer);
  latTimer = null;
}
function startWatch() {
  if (watchTimer) return;
  watchTimer = setInterval(() => {
    const now = Date.now();
    if (helloed && lastRecv && now - lastRecv > 2.5 * hbSec * 1000) {
      byeReason = "silent";
      closeTransport();
    }
    for (const [t, at] of idleSince) {
      if (now - at > 60_000) {
        idleSince.delete(t);
        if (!subs.has(t)) {
          store.delete(t);
          lastSeq.delete(t);
        }
      }
    }
  }, 5000);
}

// ---- kết nối ----
function closeTransport() {
  if (ws) {
    const w = ws;
    try {
      w.close();
    } catch {
      /* ignore */
    }
    // onclose có thể không tới nếu socket treo -> tự xử lý
    setTimeout(() => {
      if (ws === w) handleClosed();
    }, 1500);
  } else if (es) {
    handleClosed();
  }
}

function wsUrl() {
  return (location.protocol === "https:" ? "wss://" : "ws://") + location.host + BASE;
}

function connect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws || es || idleClosed) return;
  if (typeof window === "undefined") return;
  const wait = pauseUntil - Date.now();
  if (wait > 0) {
    reconnectTimer = setTimeout(connect, wait);
    return;
  }
  if (!subs.size) {
    setStatus("closed");
    return;
  }
  setStatus("connecting");
  helloed = false;
  byeReason = "";
  hasPong = false;
  rttWin = [];
  if (mode === "sse") {
    syncSse(true);
    return;
  }
  if (typeof WebSocket === "undefined") {
    mode = "sse";
    connect();
    return;
  }
  let w;
  try {
    w = new WebSocket(wsUrl());
  } catch {
    handleClosed();
    return;
  }
  ws = w;
  openedAt = Date.now();
  lastRecv = Date.now();
  w.onmessage = (ev) => {
    if (ws !== w) return;
    let obj;
    try {
      obj = JSON.parse(ev.data);
    } catch {
      return;
    }
    safe(() => onFrame(obj));
  };
  w.onclose = () => {
    if (ws === w) handleClosed();
  };
  w.onerror = () => {};
}

function handleClosed() {
  const lived = openedAt ? Date.now() - openedAt : 0;
  const hadHello = helloed;
  if (ws) {
    const w = ws;
    ws = null;
    w.onmessage = w.onclose = w.onerror = null;
    try {
      w.close();
    } catch {
      /* ignore */
    }
  }
  if (es) {
    try {
      es.close();
    } catch {
      /* ignore */
    }
    es = null;
    esKey = "";
  }
  helloed = false;
  active.clear();
  stopPing();
  stopLat();
  setStatus("closed");
  if (idleClosed) return;
  let delay;
  if (byeReason === "reauth") {
    attempt = 0;
    delay = 100 + Math.random() * 200;
  } else if (byeReason === "kicked") {
    pauseUntil = Date.now() + KICK_PAUSE_MS;
    delay = KICK_PAUSE_MS + Math.random() * 1000;
  } else {
    if (!hadHello && mode === "ws") {
      fails++;
      if (fails >= WS_FAILS_TO_SSE && typeof EventSource !== "undefined") {
        mode = "sse";
        fails = 0;
        attempt = 0;
        if (sseRetryTimer) clearTimeout(sseRetryTimer);
        sseRetryTimer = setTimeout(() => {
          sseRetryTimer = null;
          if (mode === "sse") {
            mode = "ws";
            fails = WS_FAILS_TO_SSE - 1; // một lần lỗi nữa -> quay lại SSE
          }
        }, SSE_RETRY_WS_MS);
      }
    }
    if (lived > 5000 && hadHello) attempt = 0;
    else attempt++;
    const base = Math.min(30_000, 500 * 2 ** Math.max(0, attempt - 1));
    delay = base * (0.5 + Math.random() * 0.5);
  }
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, delay);
}

// ---- SSE (chỉ nhận; đăng ký cố định trong URL) ----
function syncSse(force) {
  if (mode !== "sse" || idleClosed) return;
  const topics = [...subs.keys()].filter((t) => !rejected.has(t)).sort();
  const key = topics.join(",");
  if (!force && key === esKey && es) return;
  if (es) {
    es.onmessage = es.onerror = null;
    try {
      es.close();
    } catch {
      /* ignore */
    }
    es = null;
  }
  if (!topics.length) {
    esKey = "";
    setStatus("closed");
    return;
  }
  esKey = key;
  helloed = false;
  openedAt = Date.now();
  let src;
  try {
    src = new EventSource(BASE + "/sse?topics=" + encodeURIComponent(key));
  } catch {
    handleClosed();
    return;
  }
  es = src;
  src.onmessage = (ev) => {
    if (es !== src) return;
    let obj;
    try {
      obj = JSON.parse(ev.data);
    } catch {
      return;
    }
    safe(() => onFrame(obj));
    if (obj && obj.t === "bye") {
      try {
        src.close();
      } catch {
        /* ignore */
      }
      handleClosed();
    }
  };
  src.onerror = () => {
    if (es !== src) return;
    if (src.readyState === 2) handleClosed(); // CLOSED (vd 401): tự backoff
    else setStatus("connecting"); // EventSource tự nối lại
  };
}

// ---- tab ẩn / mạng ----
function onVisibility() {
  const hidden = safe(() => document.hidden);
  if (hidden) {
    if (!hiddenTimer)
      hiddenTimer = setTimeout(() => {
        hiddenTimer = null;
        idleClosed = true;
        byeReason = "idle";
        if (ws || es) handleClosed();
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
      }, IDLE_HIDDEN_MS);
  } else {
    if (hiddenTimer) {
      clearTimeout(hiddenTimer);
      hiddenTimer = null;
    }
    if (idleClosed) {
      idleClosed = false;
      attempt = 0;
      connect();
    }
  }
}

function ensureStarted() {
  if (started) {
    if (!ws && !es && !reconnectTimer && !idleClosed) connect();
    return;
  }
  if (typeof window === "undefined") return;
  started = true;
  safe(() => document.addEventListener("visibilitychange", onVisibility));
  safe(() =>
    window.addEventListener("online", () => {
      if (!ws && !es && !idleClosed) {
        attempt = 0;
        connect();
      }
    }),
  );
  safe(() => window.addEventListener("pagehide", () => {
    if (ws) safe(() => ws.close(1000));
  }));
  startWatch();
  connect();
}

// phần thuần cho kiểm thử
export const _internals = { pct, kindOf, RELIABLE, BASE };
