// Trang/mã gần đây + trang đã đánh dấu (bookmark). localStorage theo thiết bị; bọc try/catch.
import { useSyncExternalStore } from "react";
import { lget, lset } from "../lib/lstore";

const RK = "ts-recent", BK = "ts-bookmarks";
let R = lget(RK, []), B = lget(BK, []);
const subs = new Set();
const emit = () => { snap = { recent: R, bookmarks: B }; subs.forEach((f) => f()); };
let snap = { recent: R, bookmarks: B };
export const useRecent = () => useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => snap, () => snap);

/** Ghi lần truy cập: item = {key, label, href, kind: page|symbol}. Giữ 12 mục mới nhất, đưa mục trùng lên đầu. */
export function pushRecent(item) {
  if (!item?.key) return;
  if (R[0]?.key === item.key) return;
  R = [{ ...item, t: Date.now() }, ...R.filter((x) => x.key !== item.key)].slice(0, 12);
  lset(RK, R); emit();
}
export const isBookmarked = (href) => B.some((x) => x.href === href);
export function toggleBookmark(item) {
  B = B.some((x) => x.href === item.href) ? B.filter((x) => x.href !== item.href) : [{ ...item, t: Date.now() }, ...B].slice(0, 30);
  lset(BK, B); emit();
  return B.some((x) => x.href === item.href);
}
export function removeBookmark(href) { B = B.filter((x) => x.href !== href); lset(BK, B); emit(); }
