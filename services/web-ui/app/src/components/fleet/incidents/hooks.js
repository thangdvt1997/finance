// Dữ liệu + thao tác cho trang Sự cố. Khoá truy vấn: ["fl","incidents",params] (danh sách), ["fl","incident",id] (chi tiết),
// ["fl","inc-counts"] (huy hiệu thanh bên, dùng chung với NavBadge) — sau mỗi thao tác đều được làm mới.
import { useCallback, useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fget, fpost } from "../../../lib/fleetApi";
import { toast } from "../../../ux/bus";
import { chunk } from "./model";

const REFRESH_MS = 25_000;

/** Đồng hồ nhẹ để các nhãn "mở 12 phút trước", "còn 3 giờ" tự cập nhật. */
export function useNow(ms = 30_000) {
  const [n, setN] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setN(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return n;
}
export function useMedia(q) {
  const [m, setM] = useState(() => (typeof matchMedia === "function" ? matchMedia(q).matches : false));
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(q), h = () => setM(mq.matches);
    h(); mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [q]);
  return m;
}

/** params: {status, severity, assignee, kind, group, account, group_by}. Tự làm mới 25 giây, tạm dừng khi tab ẩn (mặc định của TanStack). */
export const useIncidentList = (params, enabled = true) => useQuery({
  enabled,
  queryKey: ["fl", "incidents", params], retry: false, staleTime: 10_000, refetchInterval: REFRESH_MS,
  queryFn: ({ signal }) => fget("/incidents", { limit: 500, ...params }, { signal }),
});
export const useIncident = (id, initial) => useQuery({
  queryKey: ["fl", "incident", id], enabled: !!id, retry: false, staleTime: 5_000, refetchInterval: REFRESH_MS,
  queryFn: ({ signal }) => fget(`/incidents/${encodeURIComponent(id)}`, null, { signal }),
  placeholderData: (prev) => (prev && prev.id === id ? prev : initial && initial.id === id ? initial : undefined),
});
/** Chỉ mục tài khoản (nhãn, nhóm) để thẻ sự cố hiện tên khách; lỗi thì thẻ vẫn hiện account_id. */
export const useAccountIndex = () => useQuery({
  queryKey: ["fl", "inc-accounts"], retry: false, staleTime: 60_000, placeholderData: keepPreviousData,
  queryFn: ({ signal }) => fget("/fleet", { limit: 500 }, { signal }),
  select: (r) => { const m = new Map(); for (const a of r?.items || []) m.set(a.account_id, a); return m; },
});

const NEW_STATUS = { ack: "ack", resolve: "resolved", snooze: "snoozed", reopen: "open" };
const OK_MSG = { ack: "Đã nhận sự cố", resolve: "Đã đóng sự cố", snooze: "Đã tạm hoãn sự cố", reopen: "Đã mở lại sự cố", assign: "Đã cập nhật người phụ trách", note: "Đã thêm ghi chú" };

async function run(v) {
  const { type, id, ids } = v;
  if (type === "bulk") {
    const results = [];
    for (const part of chunk(ids, 100)) {
      const r = await fpost("/incidents/bulk", { ids: part, action: v.action, ...(v.action === "snooze" ? { minutes: v.minutes } : {}) });
      results.push(...(r.results || []));
    }
    return { results };
  }
  const base = `/incidents/${encodeURIComponent(id)}`;
  if (type === "resolve") return fpost(`${base}/resolve`, v.text ? { text: v.text } : {});
  if (type === "snooze") return fpost(`${base}/snooze`, { minutes: v.minutes });
  if (type === "assign") return fpost(`${base}/assign`, { user_id: v.user_id || null });
  if (type === "note") return fpost(`${base}/notes`, { text: v.text });
  return fpost(`${base}/${type}`, {});
}

/** act(vars, {dialog}) -> {ok, error, data}. Toast kết quả; dialog:true = lỗi hiện trong hộp thoại gọi (không toast lỗi). */
export function useIncActions() {
  const qc = useQueryClient();
  const m = useMutation({ mutationFn: run });

  const prune = useCallback((type, okIds) => {
    const ns = NEW_STATUS[type];
    if (!ns || !okIds.length) return;
    const set = new Set(okIds);
    for (const [key, data] of qc.getQueriesData({ queryKey: ["fl", "incidents"] })) {
      if (!data?.items) continue;
      const st = key[2]?.status;
      if (st === ns || (st === "active" && ns !== "resolved")) continue;
      qc.setQueryData(key, {
        ...data, items: data.items.filter((i) => !set.has(i.id)),
        ...(data.clusters ? { clusters: data.clusters.map((c) => ({ ...c, incident_ids: c.incident_ids.filter((x) => !set.has(x)) })).filter((c) => c.incident_ids.length) } : {}),
      });
    }
  }, [qc]);

  const act = useCallback(async (v, { dialog = false, quiet = false, undo } = {}) => {
    try {
      const data = await m.mutateAsync(v);
      let okIds = [], failed = 0;
      if (v.type === "bulk") {
        okIds = (data.results || []).filter((r) => r.ok).map((r) => r.id);
        failed = (data.results || []).length - okIds.length;
        prune(v.action, okIds);
      } else {
        okIds = [v.id];
        prune(v.type, okIds);
        if (data?.id) qc.setQueryData(["fl", "incident", v.id], data);
      }
      for (const k of ["incidents", "incident", "inc-counts"]) qc.invalidateQueries({ queryKey: k === "inc-counts" ? ["fl", "inc-counts"] : ["fl", k] });
      if (!quiet) {
        if (v.type === "bulk") {
          const label = OK_MSG[v.action]?.replace("sự cố", "").trim() || "Đã xử lý";
          toast(failed
            ? { tone: okIds.length ? "warn" : "error", title: `${label}: ${okIds.length}/${okIds.length + failed} sự cố`, body: `${failed} sự cố không đổi được (trạng thái đã thay đổi hoặc ngoài phạm vi). Danh sách đã được làm mới.` }
            : { tone: "ok", title: `${label}: ${okIds.length} sự cố` });
        } else toast({ tone: "ok", title: OK_MSG[v.type] || "Đã cập nhật", ttl: undo ? 8000 : 4000, ...(undo ? { actionLabel: undo.label, onAction: undo.run } : {}) });
      }
      return { ok: true, data };
    } catch (e) {
      if (!dialog) toast({ tone: "error", title: "Thao tác không thành công", body: e?.message });
      qc.invalidateQueries({ queryKey: ["fl", "incidents"] });
      return { ok: false, error: e };
    }
  }, [m, qc, prune]);

  return { act, busy: m.isPending };
}
