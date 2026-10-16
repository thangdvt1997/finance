// Cầu nối rt -> kho giá của lib/stream.js (web-ui): mọi component đang dùng useQuote()/onTick() tự nhận giá đẩy từ /api/v1/rt.
// Gọi useRtQuoteFeed(symbols) ở nơi đã biết danh sách mã (useQuotesLatest làm việc này). Legacy /v1/stream vẫn chạy làm dự phòng.
import { useEffect } from "react";
import { subscribe } from "./realtime.js";
import { pushRtQuote } from "./stream";

export function useRtQuoteFeed(symbols) {
  const key = (Array.isArray(symbols) ? symbols : []).filter(Boolean).join(",");
  useEffect(() => {
    if (!key) return undefined;
    const offs = key.split(",").map((s) => subscribe(`q:${s}`, (d) => pushRtQuote(s, d)));
    return () => offs.forEach((f) => f());
  }, [key]);
}
