import { createContext, useContext } from "react";
export const ClassCtx = createContext({ lang: "vi", t: (vi) => vi, me: {}, rid: null, isMaster: false });
export const useCls = () => useContext(ClassCtx);
export const hhmm = (v) => { if (!v) return ""; const d = new Date(v); return Number.isNaN(+d) ? "" : d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }); };
export const num = (v, dp = 2) => (v == null || !Number.isFinite(+v) ? "—" : (+v).toFixed(dp).replace(".", ","));
export const pct = (v) => (v == null || !Number.isFinite(+v) ? "—" : `${(+v * 100).toFixed(0)}%`);
export const rr = (v) => (v == null || !Number.isFinite(+v) ? "—" : `${+v > 0 ? "+" : ""}${(+v).toFixed(2).replace(".", ",")}R`);
export const show = (v) => (v == null ? "—" : typeof v === "string" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : JSON.stringify(v));
