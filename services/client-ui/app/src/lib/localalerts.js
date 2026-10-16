// Cảnh báo cá nhân CHẠY TRÊN THIẾT BỊ (trình duyệt này): giá chạm ngưỡng, margin thấp, lãi/lỗ đang mở, EA mất kết nối.
// Lý do: dịch vụ alert-rules chưa có "chủ sở hữu theo tài khoản" nên khách chưa tạo được cảnh báo chạy nền trên máy chủ.
// Giới hạn trung thực: chỉ kiểm tra khi ứng dụng đang mở (kể cả tab nền); đóng hẳn ứng dụng thì không có cảnh báo. Báo khi VỪA chạm ngưỡng (không báo lặp khi vẫn ở trạng thái đó).
import { useCallback, useEffect, useRef, useState } from "react";
import { lget, lset } from "./lstore";
import { deriveView, marginTone } from "./account";
import { eaState } from "./queries";
import { pushNotification } from "./notifstore";
import { f0, f1, price, symbolLabel } from "./format";
import { t } from "./i18n";

let curUid = "";
const keyOf = () => `tc-lrules:${curUid}`;
export const KINDS = {
  price: { get label() { return t("Giá chạm ngưỡng"); }, get sub() { return t("Báo khi giá một mã vượt lên hoặc xuống một mức"); } },
  margin: { get label() { return t("Margin thấp"); }, get sub() { return t("Báo khi mức margin giảm xuống dưới ngưỡng"); } },
  pl: { get label() { return t("Lỗ đang mở lớn"); }, get sub() { return t("Báo khi lãi/lỗ đang mở xuống dưới −X% số dư"); } },
  ea: { get label() { return t("EA mất kết nối"); }, get sub() { return t("Báo khi không nhận dữ liệu từ MT quá N phút"); } },
};
let rules = [];
const subs = new Set();
const emit = () => subs.forEach((f) => f());
const save = (r) => { rules = r.slice(0, 40); if (curUid) lset(keyOf(), rules); emit(); };
/** Cảnh báo cục bộ lưu theo từng người dùng (tránh lộ giữa hai tài khoản dùng chung trình duyệt). */
export function bindRulesUser(uid) { if (uid === curUid) return; curUid = uid || ""; rules = curUid ? lget(keyOf(), []) : []; emit(); }
const uid = () => Math.random().toString(36).slice(2, 10);

export function useLocalRules() {
  const [, tick] = useState(0);
  useEffect(() => { const f = () => tick((n) => n + 1); subs.add(f); return () => subs.delete(f); }, []);
  return {
    rules,
    add: (r) => { const id = uid(); save([{ ...r, id, enabled: true, createdAt: Date.now() }, ...rules]); return id; },
    update: (id, patch) => save(rules.map((r) => (r.id === id ? { ...r, ...patch } : r))),
    remove: (id) => save(rules.filter((r) => r.id !== id)),
  };
}

export const OPS = { get gte() { return t("≥ (lên trên)"); }, get lte() { return t("≤ (xuống dưới)"); } };
export function describeRule(r) {
  const sym = symbolLabel(r.symbol || "");
  switch (r.kind) {
    case "price": return t("Giá {s} {op} {v}", { s: sym, op: r.op === "gte" ? "≥" : "≤", v: r.value });
    case "margin": return t("Mức margin ≤ {v}%", { v: r.value });
    case "pl": return t("Lãi/lỗ đang mở ≤ −{v}% số dư", { v: r.value });
    case "ea": return t("EA im lặng quá {v} phút", { v: r.value });
    default: return r.name || r.kind;
  }
}

/** Đánh giá các quy tắc với dữ liệu hiện có. Trả về [{rule, hit, text}] — hit = điều kiện đang đúng. */
export function evaluate(rule, { quotes, snaps, now }) {
  if (rule.kind === "price") {
    const q = quotes.get(rule.symbol);
    const px = q?.bid ?? q?.ask;
    if (px == null) return null;
    const hit = rule.op === "gte" ? px >= rule.value : px <= rule.value;
    return { hit, title: t("{s} chạm {v}", { s: symbolLabel(rule.symbol), v: price(rule.symbol, rule.value) }), body: t("Giá hiện tại {p} ({d} ngưỡng bạn đặt).", { p: price(rule.symbol, px), d: rule.op === "gte" ? t("vượt lên trên") : t("xuống dưới") }), level: "warn" };
  }
  const snap = snaps.find((s) => s.account_id === rule.account_id);
  if (!snap) return null;
  const v = deriveView(snap);
  if (rule.kind === "margin") {
    if (v.level == null) return { hit: false };
    return { hit: v.level <= rule.value, title: t("Margin thấp: {v}%", { v: f0(v.level) }), body: t("Tài khoản {a} còn {v}% (ngưỡng {th}%). {m}.", { a: rule.account_id.replace(":", " ").toUpperCase(), v: f0(v.level), th: rule.value, m: marginTone(v.level).label }), level: "crit" };
  }
  if (rule.kind === "pl") {
    if (!v.balance) return { hit: false };
    const p = (v.floating / v.balance) * 100;
    return { hit: p <= -rule.value, title: t("Lỗ đang mở {v}% số dư", { v: f1(p, 2) }), body: t("Tài khoản {a}: lãi/lỗ đang mở {v}% (ngưỡng −{th}%).", { a: rule.account_id.replace(":", " ").toUpperCase(), v: f1(p, 2), th: rule.value }), level: "warn" };
  }
  if (rule.kind === "ea") {
    const s = eaState(snap.ts, now);
    const min = s.ageS == null ? Infinity : s.ageS / 60;
    return { hit: min >= rule.value, title: t("EA mất kết nối"), body: t("Không nhận dữ liệu từ {a} hơn {m} phút. Kiểm tra MT còn mở và EA còn gắn.", { a: rule.account_id.replace(":", " ").toUpperCase(), m: f0(rule.value) }), level: "crit" };
  }
  return null;
}

/** Chạy trong Shell: mỗi khi dữ liệu mới về thì đối chiếu quy tắc + kiểm tra hệ thống (EA, margin). */
export function useAlertEngine({ snaps, quotes, sys = true }) {
  const { rules: rs, update } = useLocalRules();
  const prev = useRef(new Map());
  const last = useRef(new Map());
  const run = useCallback(() => {
    const now = Date.now();
    const qm = new Map((quotes || []).map((q) => [q.symbol, q]));
    const sn = snaps || [];
    for (const r of rs) {
      if (!r.enabled) continue;
      const res = evaluate(r, { quotes: qm, snaps: sn, now });
      if (!res) continue;
      const was = prev.current.get(r.id);
      prev.current.set(r.id, res.hit);
      if (was === undefined || was === true || !res.hit) continue; // chỉ báo khi chuyển từ sai -> đúng
      const cool = (r.cooldownMin ?? 30) * 60_000;
      if (now - (last.current.get(r.id) || 0) < cool) continue;
      last.current.set(r.id, now);
      pushNotification({ id: `rule:${r.id}:${now}`, kind: "alert", level: res.level, title: res.title, body: res.body });
      if (r.mode === "once") update(r.id, { enabled: false, lastFired: now });
    }
    if (sys) for (const s of sn) { // thông báo hệ thống tự động: EA mất kết nối, margin xuống dải nguy hiểm
      const name = s.account_id.replace(":", " ").toUpperCase();
      const ea = eaState(s.ts, now).level === "off";
      const kEa = `sys-ea:${s.account_id}`;
      if (prev.current.get(kEa) === false && ea) pushNotification({ id: `${kEa}:${now}`, kind: "system", level: "crit", title: t("Mất kết nối EA"), body: t("{name}: chưa nhận dữ liệu mới hơn 10 phút. Số liệu có thể đã cũ.", { name }) });
      prev.current.set(kEa, ea);
      const v = deriveView(s), band = v.level == null ? 0 : v.level < 100 ? 3 : v.level < 150 ? 2 : v.level < 300 ? 1 : 0;
      const kM = `sys-margin:${s.account_id}`, pb = prev.current.get(kM);
      if (pb !== undefined && band > pb && band >= 2) pushNotification({ id: `${kM}:${now}`, kind: "system", level: "crit", title: t("Margin xuống {v}%", { v: f0(v.level) }), body: t("{name}: {m}. Xem mục Rủi ro.", { name, m: marginTone(v.level).label }) });
      prev.current.set(kM, band);
    }
  }, [rs, quotes, snaps, sys, update]);
  useEffect(() => { run(); }, [run]);
}
