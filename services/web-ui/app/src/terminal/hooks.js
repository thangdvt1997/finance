// Hook dữ liệu dùng chung cho widget (cùng queryKey ["spark", mã] với trang Tổng quan/Bảng giá để chia sẻ cache).
import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { api } from "../lib/api";
import { classOf } from "../lib/assetClass";
import { useWatchSymbols } from "../lib/prefs";
import { useSymbols } from "../lib/queries";

// nginx giới hạn ~15 yêu cầu/giây/IP: nhiều widget cùng nạp nến cho hàng chục mã sẽ bị 429 nếu bắn đồng loạt -> xếp hàng, tối đa 4 đồng thời, cách nhau >= 75ms.
let active = 0, lastStart = 0;
const waiting = [];
function pump() {
  while (active < 4 && waiting.length) {
    const wait = Math.max(0, lastStart + 75 - Date.now());
    if (wait > 0) { setTimeout(pump, wait); return; }
    const job = waiting.shift();
    active++; lastStart = Date.now();
    job().finally(() => { active--; pump(); });
  }
}
/** Chạy fn() theo hàng đợi có nhịp; trả Promise như fn(). Dùng cho các truy vấn N+1 theo từng mã. */
export function paced(fn) {
  return new Promise((resolve, reject) => { waiting.push(() => fn().then(resolve, reject)); pump(); });
}

/** { [mã]: { closes[], change% (48 nến H1), loading } } */
export function useSparkChanges(symbols, enabled = true) {
  const res = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ["spark", s], enabled,
      queryFn: ({ signal }) => paced(() => api("/bars", { symbol: s, tf: "H1", limit: 48, order: "desc" }, signal)),
      staleTime: 60_000, refetchInterval: 120_000,
    })),
  });
  const key = res.map((r) => r.dataUpdatedAt).join(",");
  return useMemo(() => Object.fromEntries(symbols.map((s, i) => {
    const closes = [...(res[i].data?.items || [])].reverse().map((b) => b.c);
    const change = closes.length > 1 ? ((closes[closes.length - 1] - closes[0]) / closes[0]) * 100 : null;
    return [s, { closes, change, loading: res[i].isPending && enabled }];
  })), [key, symbols.join(","), enabled]); // eslint-disable-line react-hooks/exhaustive-deps
}

/** Danh sách mã theo nguồn: "watch" (nhóm theo dõi chung), "all", hoặc id loại tài sản (forex, crypto, vn, us, commodity, index, bond). */
export function useSymbolsBy(cls, limit = 60) {
  const watch = useWatchSymbols();
  const all = useSymbols();
  return useMemo(() => {
    if (!cls || cls === "watch") return { symbols: watch.slice(0, limit), pending: false };
    const list = (all.data || []).filter((s) => cls === "all" || classOf(s) === cls).map((s) => s.symbol);
    return { symbols: list.slice(0, limit), pending: all.isPending };
  }, [cls, watch, all.data, all.isPending, limit]);
}
