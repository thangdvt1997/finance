// Danh sách theo dõi cá nhân nhiều nhóm — lưu trong trình duyệt (không có API lưu phía máy chủ; ghi chú ở README).
import { useCallback, useEffect, useState } from "react";
import { lget, lset } from "./lstore";
import { t } from "./i18n";

const KEY = "tc-wl2";
const DEFAULT = { active: "main", groups: [
  { id: "main", name: "Ưu tiên", symbols: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"] },
  { id: "crypto", name: "Tiền ảo", symbols: [] },
] };
// Tên nhóm mặc định được lưu cùng dữ liệu: nhận ra cả bản vi lẫn en rồi hiển thị theo ngôn ngữ hiện tại.
const defName = (n, i) => {
  if (n === "Ưu tiên" || n === "Priority") return t("Ưu tiên");
  if (n === "Tiền ảo" || n === "Crypto") return t("Tiền ảo");
  const m = /^(?:Nhóm|Group) (\d+)$/.exec(n || "");
  return m ? t("Nhóm {n}", { n: m[1] }) : n || t("Nhóm {n}", { n: i + 1 });
};
const clean = (w) => {
  if (!w || !Array.isArray(w.groups) || !w.groups.length) return clean(DEFAULT);
  const groups = w.groups.slice(0, 8).map((g, i) => ({ id: String(g.id || `g${i}`).slice(0, 16), name: defName(String(g.name || ""), i).slice(0, 24), symbols: [...new Set((g.symbols || []).map(String))].slice(0, 40) }));
  return { active: groups.some((g) => g.id === w.active) ? w.active : groups[0].id, groups };
};

export function useWatchlists() {
  const [w, setW] = useState(() => {
    const cur = lget(KEY, null);
    if (cur) return clean(cur);
    const old = lget("tc-watch", null); // bản cũ: một danh sách phẳng
    return Array.isArray(old) && old.length ? clean({ ...DEFAULT, groups: [{ ...DEFAULT.groups[0], symbols: old }, DEFAULT.groups[1]] }) : clean(DEFAULT);
  });
  useEffect(() => { lset(KEY, w); }, [w]);
  const group = w.groups.find((g) => g.id === w.active) || w.groups[0];
  const upd = useCallback((fn) => setW((c) => clean(fn(c))), []);
  return {
    groups: w.groups, group,
    setActive: (id) => upd((c) => ({ ...c, active: id })),
    add: (sym) => upd((c) => ({ ...c, groups: c.groups.map((g) => (g.id === c.active && !g.symbols.includes(sym) ? { ...g, symbols: [...g.symbols, sym] } : g)) })),
    remove: (sym) => upd((c) => ({ ...c, groups: c.groups.map((g) => (g.id === c.active ? { ...g, symbols: g.symbols.filter((s) => s !== sym) } : g)) })),
    move: (sym, dir) => upd((c) => ({ ...c, groups: c.groups.map((g) => { if (g.id !== c.active) return g; const a = [...g.symbols], i = a.indexOf(sym), j = i + dir; if (i < 0 || j < 0 || j >= a.length) return g; [a[i], a[j]] = [a[j], a[i]]; return { ...g, symbols: a }; }) })),
    addGroup: (name) => upd((c) => { const id = `g${Date.now().toString(36)}`; return { active: id, groups: [...c.groups, { id, name: name || t("Nhóm {n}", { n: c.groups.length + 1 }), symbols: [] }] }; }),
    renameGroup: (id, name) => upd((c) => ({ ...c, groups: c.groups.map((g) => (g.id === id ? { ...g, name: name.trim() || g.name } : g)) })),
    removeGroup: (id) => upd((c) => (c.groups.length > 1 ? { ...c, groups: c.groups.filter((g) => g.id !== id) } : c)),
  };
}
