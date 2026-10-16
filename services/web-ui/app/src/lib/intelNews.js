// Terminal tin tức: nguồn dữ liệu = /v1/intel/news (tìm toàn văn, lọc, phân trang theo thời gian) + sự kiện WebSocket (news.items, news.enriched)
// trộn vào đầu danh sách theo thời gian thực. Trạng thái "đã đọc/đã lưu" lưu localStorage (theo thiết bị). KHÔNG hiển thị tên nguồn.
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "./api";
import { onStreamEvent } from "./stream";
import { lget, lset } from "./lstore";
import "../intel.css";

export const TOPIC_LABEL = {
  monetary_policy: "Chính sách tiền tệ", inflation: "Lạm phát", jobs: "Việc làm", growth: "Tăng trưởng", geopolitics: "Địa chính trị",
  trade_tariffs: "Thương mại & thuế quan", energy: "Năng lượng", precious_metals: "Kim loại quý", corporate: "Doanh nghiệp",
  banking_credit: "Ngân hàng & tín dụng", sovereign_rating: "Xếp hạng tín nhiệm", fx_markets: "Ngoại hối", equities: "Cổ phiếu & chỉ số",
  crypto: "Tiền ảo", real_estate: "Bất động sản", regulation_policy: "Chính sách & quy định", tech_ai: "Công nghệ & AI",
};
export const IMPORTANCE_LABEL = { 3: "Quan trọng", 2: "Chú ý", 1: "Thường", 0: "Thường" };
const IMP = { low: 1, med: 2, high: 3 };

// ---------------------------------------------------------------- đã đọc / đã lưu (localStorage)
const READ_KEY = "ts-news-read";
const SAVED_KEY = "ts-news-saved";
const MAX_READ = 3000;
const MAX_SAVED = 200;
let readArr = lget(READ_KEY, []);
let readSet = new Set(readArr);
let saved = lget(SAVED_KEY, []);
let marksVer = 0;
const marksSubs = new Set();
const marksEmit = () => { marksVer++; marksSubs.forEach((f) => f()); };
const marksSub = (f) => { marksSubs.add(f); return () => marksSubs.delete(f); };

/** Băm URL ngắn để làm khoá (không lưu URL dài vào bộ nhớ). */
export function hashUrl(u) {
  let h = 5381;
  for (let i = 0; i < u.length; i++) h = ((h << 5) + h) ^ u.charCodeAt(i);
  return (h >>> 0).toString(36) + u.length.toString(36);
}
export function markRead(urls, on = true) {
  let ch = false;
  for (const u of [].concat(urls)) {
    const k = hashUrl(u);
    if (on && !readSet.has(k)) { readSet.add(k); readArr.push(k); ch = true; }
    else if (!on && readSet.has(k)) { readSet.delete(k); readArr = readArr.filter((x) => x !== k); ch = true; }
  }
  if (!ch) return;
  if (readArr.length > MAX_READ) { readArr = readArr.slice(-MAX_READ); readSet = new Set(readArr); }
  lset(READ_KEY, readArr);
  marksEmit();
}
export function toggleSaved(item) {
  const k = hashUrl(item.url);
  if (saved.some((s) => s.k === k)) saved = saved.filter((s) => s.k !== k);
  else saved = [{ k, url: item.url, title: item.title, ts: item.ts, symbols: (item.symbols || []).slice(0, 4), sentiment: item.sentiment ?? null, importance: item.importance || 0, topics: (item.topics || []).slice(0, 3), summary: (item.summary || "").slice(0, 400) }, ...saved].slice(0, MAX_SAVED);
  lset(SAVED_KEY, saved);
  marksEmit();
}
/** Đọc trạng thái đánh dấu; tự render lại khi đổi. */
export function useNewsMarks() {
  useSyncExternalStore(marksSub, () => marksVer);
  return { isRead: (u) => readSet.has(hashUrl(u)), isSaved: (u) => saved.some((s) => s.k === hashUrl(u)), saved, readCount: readArr.length };
}

// ---------------------------------------------------------------- tin trực tiếp (WebSocket)
const MAX_LIVE = 300;
let live = [];                       // tin đến trong phiên, mới nhất trước
const enrich = new Map();            // url -> {topics, importance, sentiment, sentiment_label}
let liveVer = 0;
const liveSubs = new Set();
const liveHandlers = new Set();      // (item, kind: "new"|"enriched") => void  (âm báo...)
let liveStarted = false;
const liveEmit = () => { liveVer++; liveSubs.forEach((f) => f()); };

const toItem = (p, ts) => ({
  url: p.url, title: p.title, summary: p.summary || null, ts: p.published_at || ts, lang: p.lang || null, symbols: p.symbols || [],
  sentiment: p.sentiment ?? null, sentiment_label: null, topics: [], importance: 0, live: true, liveAt: Date.now(),
});
function startLive() {
  if (liveStarted) return;
  liveStarted = true;
  onStreamEvent((msg) => {
    const ev = msg.event || {};
    const p = ev.payload || {};
    if (!p.url) return;
    if (msg.stream === "news.items") {
      if (live.some((x) => x.url === p.url)) return;
      const it = applyEnrich(toItem(p, ev.ts));
      live = [it, ...live].slice(0, MAX_LIVE);
      liveEmit();
      liveHandlers.forEach((h) => h(it, "new"));
    } else if (msg.stream === "news.enriched") {
      enrich.set(p.url, { topics: p.topics || [], importance: IMP[p.importance] ?? 0, sentiment: p.sentiment ?? null, sentiment_label: p.label || null });
      if (enrich.size > 1500) enrich.delete(enrich.keys().next().value);
      const i = live.findIndex((x) => x.url === p.url);
      if (i >= 0) {
        live = live.slice();
        live[i] = applyEnrich(live[i]);
        liveHandlers.forEach((h) => h(live[i], "enriched"));
      }
      liveEmit();
    }
  });
}
function applyEnrich(it) {
  const e = enrich.get(it.url);
  return e ? { ...it, topics: e.topics.length ? e.topics : it.topics, importance: e.importance || it.importance, sentiment: e.sentiment ?? it.sentiment, sentiment_label: e.sentiment_label || it.sentiment_label } : it;
}
/** Đăng ký hàm xử lý khi có tin mới/được gắn nhãn (âm báo). Trả hàm huỷ. */
export function onLiveNews(fn) {
  startLive();
  liveHandlers.add(fn);
  return () => liveHandlers.delete(fn);
}

// ---------------------------------------------------------------- lọc phía máy khách cho tin trực tiếp
export function matchesFilters(it, f) {
  if (f.symbol && !(it.symbols || []).includes(f.symbol)) return false;
  if (f.lang && it.lang !== f.lang) return false;
  if (f.hours && Date.parse(it.ts) < Date.now() - f.hours * 3600e3) return false;
  if (f.min_importance && (it.importance || 0) < f.min_importance) return false;
  const tps = f.topic ? f.topic.split(",").filter(Boolean) : [];
  if (tps.length && !tps.some((t) => (it.topics || []).includes(t))) return false;
  const s = it.sentiment;
  if (f.sentiment === "pos" && !(s != null && s > 0.15)) return false;
  if (f.sentiment === "neg" && !(s != null && s < -0.15)) return false;
  if (f.sentiment === "neu" && !(s != null && s >= -0.15 && s <= 0.15)) return false;
  const words = (f.q || "").toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length) { const t = `${it.title} ${it.summary || ""}`.toLowerCase(); if (!words.every((w) => t.includes(w))) return false; }
  return true;
}

/** Danh sách tin (trang đã tải + tin trực tiếp khớp bộ lọc), mới nhất trước, loại trùng URL. */
export function useNewsFeed(filters, { pageSize = 60, live: useLive = true } = {}) {
  startLive();
  useSyncExternalStore((f) => { liveSubs.add(f); return () => liveSubs.delete(f); }, () => liveVer);
  const key = JSON.stringify(filters);
  const q = useInfiniteQuery({
    queryKey: ["intel", "newsfeed", key, pageSize],
    queryFn: ({ pageParam, signal }) => api("/intel/news", { ...filters, before: pageParam, limit: pageSize }, signal),
    initialPageParam: undefined,
    getNextPageParam: (last) => last.next_before || undefined,
    staleTime: 20_000,
  });
  const pages = q.data?.pages;
  const items = useMemo(() => {
    const seen = new Set();
    const out = [];
    const add = (it) => { if (!seen.has(it.url)) { seen.add(it.url); out.push(applyEnrich(it)); } };
    if (useLive) for (const it of live) if (matchesFilters(it, filters)) add(it);
    for (const pg of pages || []) for (const it of pg.items) add(it);
    out.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages, key, useLive, liveVer]);
  useEffect(() => { /* giữ phụ thuộc liveVer để đồng bộ useMemo */ }, [liveVer]);
  return { ...q, items };
}
