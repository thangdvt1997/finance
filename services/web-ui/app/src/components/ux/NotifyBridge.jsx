// Cầu nối: gom sự kiện realtime + cảnh báo máy chủ + trạng thái kết nối + lỗi tải dữ liệu -> Trung tâm thông báo. Không vẽ gì.
import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe } from "../../lib/clientsApi";
import { useStream } from "../../lib/stream";
import { useAlerts } from "../../lib/queries";
import { clean, expertLabel } from "../../lib/format";
import { notify, lastOpen } from "../../ux/bus";

const LEVEL = { crit: "crit", critical: "crit", error: "crit", warn: "warn", warning: "warn", info: "info" };
const sevOf = (l) => LEVEL[String(l || "").toLowerCase()] || "info";
const alertKey = (a) => `alert:${a.dedupe_key || `${a.title}|${Math.floor((Date.parse(a.ts) || 0) / 60000)}`}`;

function fromEvent(stream, ev) {
  const p = ev.payload || {};
  const ts = Date.parse(ev.ts) || Date.now();
  if (stream === "alerts.out") {
    return { key: alertKey({ ...p, ts: ev.ts }), cat: "alert", sev: sevOf(p.level), title: clean(p.title) || "Cảnh báo", body: clean(p.body), href: "#/canh-bao", ts };
  }
  if (stream === "news.items") {
    const imp = p.importance ?? p.impact;
    const high = imp === "high" || (typeof imp === "number" && imp >= 0.7);
    if (!high) return null;
    return { key: `news:${p.url || p.id || ev.id}`, cat: "news", sev: "info", title: clean(p.title) || "Tin quan trọng", body: clean(p.summary), href: "#/tin-tuc", ts };
  }
  if (stream === "calendar.events") {
    if (p.impact !== "high") return null;
    return { key: `cal:${p.event_id || p.id || ev.id}`, cat: "news", sev: "info", title: clean(p.title || p.event) || "Sự kiện lịch tác động cao", body: [p.country || p.currency, p.actual != null ? `Thực tế ${p.actual}` : p.forecast != null ? `Dự báo ${p.forecast}` : ""].filter(Boolean).join(" · "), href: "#/lich", ts };
  }
  if (stream === "expert.signals") {
    const who = expertLabel(p.expert_name || p.expert || p.name || "");
    const what = [p.symbol, p.direction || p.side || p.bias].filter(Boolean).join(" ");
    return { key: `exp:${p.signal_id || p.id || ev.id}`, cat: "expert", sev: "info", title: clean(p.title) || `Tín hiệu chuyên gia${what ? `: ${what}` : ""}`, body: who, href: "#/chuyen-gia", ts };
  }
  return null;
}

export function NotifyBridge() {
  const st = useStream();
  const qc = useQueryClient();
  const seen = useRef(null);
  const first = useRef(true);

  // 1) sự kiện realtime
  useEffect(() => {
    if (!seen.current) seen.current = new Set();
    for (const ev of st.events) {
      const id = `${ev.stream}:${ev.id}`;
      if (seen.current.has(id)) continue;
      seen.current.add(id);
      const n = fromEvent(ev.stream, ev);
      if (n) notify(n);
    }
    if (seen.current.size > 400) seen.current = new Set([...seen.current].slice(-200));
  }, [st.version]); // eslint-disable-line react-hooks/exhaustive-deps

  // 2) cảnh báo từ máy chủ (khởi tạo lịch sử + bù khi WebSocket rớt). Chỉ master; client nhận 403 -> bỏ qua.
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 300_000, retry: false });
  const al = useAlerts({ limit: 30 }, { enabled: !!me.data?.role && me.data.role !== "expert" });
  useEffect(() => {
    const items = al.data?.items;
    if (!items) return;
    const lo = lastOpen();
    const seed = first.current;
    first.current = false;
    for (const a of [...items].reverse()) {
      const ts = Date.parse(a.ts) || Date.now();
      const old = seed && (ts < lo || Date.now() - ts > 6 * 3600e3 || sevOf(a.level) === "info");
      notify({ key: alertKey(a), cat: "alert", sev: sevOf(a.level), title: clean(a.title) || "Cảnh báo", body: clean(a.body), href: "#/canh-bao", ts, read: old, quiet: seed || old });
    }
  }, [al.data]);

  // 3) trạng thái kết nối realtime
  const prev = useRef({ everOpen: false, downTimer: null, wasDown: false });
  useEffect(() => {
    const r = prev.current;
    if (st.status === "open") {
      clearTimeout(r.downTimer); r.downTimer = null;
      if (r.wasDown) { notify({ key: `sys:up:${Date.now()}`, cat: "system", sev: "info", title: "Đã nối lại dữ liệu thời gian thực", body: "Giá và tin đang cập nhật trở lại." }); r.wasDown = false; }
      r.everOpen = true;
    } else if (st.status === "closed" && r.everOpen && !r.downTimer) {
      r.downTimer = setTimeout(() => {
        r.downTimer = null; r.wasDown = true;
        notify({ key: `sys:down:${Date.now()}`, cat: "system", sev: "warn", title: "Mất kết nối dữ liệu thời gian thực", body: "Giao diện đang tự nối lại. Số liệu hiển thị có thể cũ.", quiet: true });
      }, 6000);
    }
  }, [st.status]);

  // 4) lỗi tải dữ liệu (gộp theo nhóm truy vấn, tối đa 1 thông báo / 10 phút / nhóm; bỏ 401/403/404 vì là quyền hạn)
  useEffect(() => {
    const last = new Map();
    return qc.getQueryCache().subscribe((ev) => {
      if (ev?.type !== "updated" || ev.action?.type !== "error") return;
      const err = ev.action.error; const key = String(ev.query.queryKey?.[0] || "");
      if ([401, 403, 404].includes(err?.status) || err?.name === "AbortError") return;
      if (Date.now() - (last.get(key) || 0) < 600e3) return;
      last.set(key, Date.now());
      notify({ key: `sys:q:${key}:${Math.floor(Date.now() / 600e3)}`, cat: "system", sev: "warn", title: "Không tải được một phần dữ liệu", body: `${err?.message || "Lỗi không xác định"} (mục: ${key})`, quiet: true, href: "#/he-thong" });
    });
  }, [qc]);
  return null;
}
