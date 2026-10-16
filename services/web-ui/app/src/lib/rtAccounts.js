// Đồng bộ tài khoản qua rt vào cache react-query (BYTE-GIỐNG ở web-ui và client-ui). KHÔNG tự bịa id: nhận id từ danh sách /accounts.
//  - a:<id> -> gộp snapshot mới vào query ["accounts", {}] (giữ trường REST không có trong push, vd currency/orders khi push thiếu).
//  - e:<id> (events:true) -> deal mới / reset => làm mới các query journal-* + equity của đúng tài khoản đó (thay vì poll).
// Dùng bộ đếm tham chiếu mức module: nhiều component gọi cùng id chỉ tạo MỘT đăng ký.
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { subscribe } from "./realtime.js";

const MAX_IDS = 100;
const watchers = new Map(); // key -> {refs, off}
const tsMs = (v) => {
  const n = typeof v === "number" ? v : Date.parse(v);
  return Number.isFinite(n) ? n : 0;
};

function mergeAcct(qc, id, d) {
  if (!d || typeof d !== "object") return;
  qc.setQueryData(["accounts", {}], (old) => {
    if (!Array.isArray(old)) return old;
    let hit = false;
    const next = old.map((r) => {
      if (!r || r.account_id !== id) return r;
      hit = true;
      if (tsMs(d.ts) && tsMs(r.ts) && tsMs(d.ts) < tsMs(r.ts)) return r; // gói cũ hơn REST
      const m = { ...r };
      for (const k of ["platform", "ts", "balance", "equity", "margin", "positions", "currency"]) if (d[k] !== undefined && d[k] !== null) m[k] = d[k];
      if (Array.isArray(d.orders)) m.orders = d.orders;
      return m;
    });
    return hit ? next : old;
  });
}

function refreshJournal(qc, id) {
  qc.invalidateQueries({ predicate: (q) => {
    const k = q.queryKey;
    return Array.isArray(k) && ((typeof k[0] === "string" && k[0].startsWith("journal-") && k[1] === id) || (k[0] === "equity" && k[1]?.account_id === id));
  } });
}

function watch(qc, kind, id) {
  const key = kind + id;
  let w = watchers.get(key);
  if (!w) {
    const topic = `${kind}:${id}`;
    const off = subscribe(topic, (d, meta) => {
      if (kind === "a") mergeAcct(qc, id, d);
      else if (meta && meta.reset) refreshJournal(qc, id);
      else if (d && d.k === "deals") refreshJournal(qc, id);
    }, { replay: false });
    w = { refs: 0, off };
    watchers.set(key, w);
  }
  w.refs++;
  return () => {
    if (--w.refs <= 0) {
      w.off();
      watchers.delete(key);
    }
  };
}

/** ids: chuỗi "id1,id2" (ổn định để làm dependency). events: true => theo dõi e:<id> (deal). */
export function useRtAccounts(ids, events) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!ids) return undefined;
    const list = String(ids).split(",").filter(Boolean).slice(0, MAX_IDS);
    const offs = [];
    for (const id of list) {
      offs.push(watch(qc, "a", id));
      if (events) offs.push(watch(qc, "e", id));
    }
    return () => offs.forEach((f) => f());
  }, [qc, ids, events]);
}
