// Danh sách mã: tab theo loại tài sản, tìm kiếm, yêu thích, giá/%/sparkline; cuộn ảo (chỉ dựng các dòng đang thấy)
// nên mượt với hàng trăm mã. Panel này có chiều cao do cha quyết định và cuộn NỘI BỘ – không bao giờ làm trang dài ra.
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Star, X } from "lucide-react";
import { cn } from "../ui";
import { api } from "../../lib/api";
import { useQuotesLatest } from "../../lib/queries";
import { useQuote } from "../../lib/stream";
import { price, pct, signCls, symbolLabel } from "../../lib/format";
import { CLASSES, CLASS_LABEL, classOf, subLabel } from "../../lib/assetClass";

const ROW = 46;
// Nhãn nhóm con (trường `group` từ /v1/symbols); nhóm lạ giữ nguyên.
const GROUP_LABEL = { Majors: "Major", Minors: "Minor", Exotics: "Exotic" };
const GROUP_ORDER = ["Majors", "Minors", "Exotics"];
const groupLabel = (g) => GROUP_LABEL[g] || g;

function Spark({ data, up }) {
  if (!data || data.length < 2) return <span className="block h-[20px] w-[52px]" aria-hidden="true" />;
  const w = 52, h = 20, min = Math.min(...data), max = Math.max(...data), rg = max - min || 1;
  const pts = data.map((v, i) => `${((i / (data.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((v - min) / rg) * (h - 4)).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className="shrink-0 overflow-visible">
      <polyline points={pts} fill="none" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" className={up ? "stroke-up" : "stroke-down"} />
    </svg>
  );
}

/** 30 nến D1 gần nhất (hoặc khung nhỏ nhất có) làm sparkline + giá tham chiếu cho %; trễ 250ms để cuộn nhanh không bắn hàng loạt request. */
function useSpark(symbol, tfs) {
  const [ready, setReady] = useState(false);
  useEffect(() => { const t = setTimeout(() => setReady(true), 250); return () => clearTimeout(t); }, []);
  const tf = tfs?.includes("D1") ? "D1" : tfs?.[tfs.length - 1] || "D1";
  return useQuery({
    queryKey: ["spark", symbol, tf],
    enabled: ready,
    staleTime: 300_000, gcTime: 900_000, retry: false, refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const d = await api("/bars", { symbol, tf, limit: 30, order: "desc" }, signal);
      return (d.items || []).map((b) => b.c).reverse();
    },
  });
}

const Row = memo(function Row({ s, active, fav, onPick, onFav, top }) {
  const q = useQuote(s.symbol);
  const sp = useSpark(s.symbol, s.tfs);
  const closes = sp.data;
  const lastC = closes?.[closes.length - 1];
  const px = q?.bid ?? q?.ask ?? lastC;
  const ref = closes && closes.length >= 2 ? closes[closes.length - 2] : null;
  const chg = px != null && ref ? ((px - ref) / ref) * 100 : null;
  return (
    <li className="absolute inset-x-0" style={{ top, height: ROW }}>
      <div className={cn("flex h-full items-center border-l-2 pr-2", active ? "bg-panel2 border-l-[var(--accent)]" : "border-l-transparent hover:bg-panel2")}>
        <button type="button" aria-label={fav ? `Bỏ yêu thích ${symbolLabel(s.symbol)}` : `Yêu thích ${symbolLabel(s.symbol)}`} aria-pressed={fav}
          className={cn("grid h-full w-7 shrink-0 place-items-center border-0 bg-transparent cursor-pointer", fav ? "text-accent" : "text-faint hover:text-muted")}
          onClick={() => onFav(s.symbol)}>
          <Star size={13} fill={fav ? "currentColor" : "none"} aria-hidden="true" />
        </button>
        <button type="button" onClick={() => onPick(s.symbol)} aria-pressed={active}
          className="flex h-full min-w-0 flex-1 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 text-left font-[inherit] text-fg">
          <span className="min-w-0 flex-1">
            <b className="block truncate text-[13px] leading-tight">{symbolLabel(s.symbol)}</b>
            <span className="block truncate text-[11px] leading-tight text-faint">{subLabel(s)}</span>
          </span>
          <Spark data={closes} up={(chg ?? 0) >= 0} />
          <span className="flex w-[76px] shrink-0 flex-col items-end leading-tight">
            <span className={cn("num text-[12.5px]", q?.dir > 0 ? "up" : q?.dir < 0 ? "down" : "")}>{price(s.symbol, px)}</span>
            <span className={cn("num text-[11px]", signCls(chg))}>{chg == null ? "—" : pct(chg)}</span>
          </span>
        </button>
      </div>
    </li>
  );
});

export default function SymbolList({ symbols, loading, error, active, onPick, favs, onFav, cls, onCls }) {
  const [filter, setFilter] = useState("");
  const [grp, setGrp] = useState("");
  const box = useRef(null);
  const [vp, setVp] = useState({ top: 0, h: 360 });

  const enriched = useMemo(() => (symbols || []).map((s) => ({ ...s, _cls: classOf(s) })), [symbols]);
  const favSet = useMemo(() => new Set(favs), [favs]);
  const counts = useMemo(() => {
    const c = {};
    for (const s of enriched) c[s._cls] = (c[s._cls] || 0) + 1;
    return c;
  }, [enriched]);

  // nhóm con của loại đang chọn (Forex: Major/Minor/Exotic; Kim loại & hàng hoá; Chỉ số theo khu vực...)
  const groups = useMemo(() => {
    if (cls === "all" || cls === "fav") return [];
    const c = new Map();
    for (const s of enriched) if (s._cls === cls && s.group) c.set(s.group, (c.get(s.group) || 0) + 1);
    if (c.size < 2) return [];
    const rank = (g) => { const i = GROUP_ORDER.indexOf(g); return i < 0 ? 99 : i; };
    return [...c].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0], "vi")).map(([id, n]) => ({ id, n }));
  }, [enriched, cls]);
  const gsel = groups.some((g) => g.id === grp) ? grp : "";

  const list = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const order = Object.fromEntries(CLASSES.map((c, i) => [c.id, i]));
    return enriched
      .filter((s) => (cls === "all" ? true : cls === "fav" ? favSet.has(s.symbol) : s._cls === cls))
      .filter((s) => !gsel || s.group === gsel)
      .filter((s) => !f || s.symbol.toLowerCase().includes(f) || (s.name || "").toLowerCase().includes(f))
      .sort((a, b) => (cls === "all" ? (order[a._cls] ?? 99) - (order[b._cls] ?? 99) : 0) || a.symbol.localeCompare(b.symbol));
  }, [enriched, cls, filter, favSet, gsel]);

  // cuộn ảo
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let raf = 0;
    const read = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => setVp({ top: el.scrollTop, h: el.clientHeight })); };
    read();
    el.addEventListener("scroll", read, { passive: true });
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => { cancelAnimationFrame(raf); el.removeEventListener("scroll", read); ro.disconnect(); };
  }, []);
  useEffect(() => { if (box.current) box.current.scrollTop = 0; }, [cls, filter, gsel]);

  const n = list.length;
  const start = Math.max(0, Math.floor(vp.top / ROW) - 3);
  const end = Math.min(n, Math.ceil((vp.top + vp.h) / ROW) + 3);
  const visible = list.slice(start, end);

  // giá mới nhất cho các dòng đang thấy (debounce theo khoảng cuộn)
  const [qSyms, setQSyms] = useState([]);
  const key = visible.map((s) => s.symbol).join(",");
  useEffect(() => { const t = setTimeout(() => setQSyms(key ? key.split(",").slice(0, 60) : []), 300); return () => clearTimeout(t); }, [key]);
  useQuotesLatest(qSyms.length ? qSyms : undefined);

  const tabs = [{ id: "all", label: "Tất cả", n: enriched.length }, { id: "fav", label: "★", n: favs.length, title: "Yêu thích" },
    ...CLASSES.filter((c) => counts[c.id]).map((c) => ({ ...c, n: counts[c.id] }))];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line p-2">
        <div className="relative">
          <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
          <label className="sr-only" htmlFor="sym-filter">Tìm mã</label>
          <input id="sym-filter" className="field w-full !pl-7 !pr-7" placeholder="Tìm mã hoặc tên…" value={filter} onChange={(e) => setFilter(e.target.value)} autoComplete="off" />
          {filter && <button type="button" aria-label="Xoá tìm kiếm" className="absolute right-1.5 top-1/2 grid h-5 w-5 -translate-y-1/2 place-items-center border-0 bg-transparent text-faint cursor-pointer" onClick={() => setFilter("")}><X size={13} /></button>}
        </div>
      </div>
      <div className="shrink-0 overflow-x-auto border-b border-line px-1.5 py-1.5" role="tablist" aria-label="Loại tài sản">
        <div className="flex w-max gap-1">
          {tabs.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={cls === t.id} title={t.title || CLASS_LABEL[t.id]}
              className={cn("h-7 shrink-0 cursor-pointer rounded-md border px-2 text-[12px] font-medium whitespace-nowrap",
                cls === t.id ? "border-transparent bg-accent text-[var(--accent-fg)]" : "border-line bg-panel2 text-muted hover:text-fg")}
              onClick={() => onCls(t.id)}>
              {t.label} <span className={cn("num text-[10.5px]", cls === t.id ? "opacity-80" : "text-faint")}>{t.n}</span>
            </button>
          ))}
        </div>
      </div>
      {groups.length > 0 && (
        <div className="shrink-0 overflow-x-auto border-b border-line px-1.5 py-1" role="tablist" aria-label="Nhóm">
          <div className="flex w-max gap-1">
            {[{ id: "", n: groups.reduce((a, g) => a + g.n, 0), label: "Tất cả" }, ...groups.map((g) => ({ ...g, label: groupLabel(g.id) }))].map((g) => (
              <button key={g.id || "all"} type="button" role="tab" aria-selected={gsel === g.id}
                className={cn("h-6 shrink-0 cursor-pointer rounded-full border px-2.5 text-[11.5px] whitespace-nowrap",
                  gsel === g.id ? "border-[var(--accent)] bg-panel2 text-fg" : "border-line bg-transparent text-muted hover:text-fg")}
                onClick={() => setGrp(g.id)}>
                {g.label} <span className="num text-[10.5px] text-faint">{g.n}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <div ref={box} className="min-h-0 flex-1 overflow-y-auto overscroll-contain" tabIndex={0} aria-label="Danh sách mã">
        {loading && !enriched.length ? <div className="p-3 text-muted">Đang tải danh sách mã…</div>
          : error && !enriched.length ? <div role="alert" className="p-3 text-down">Không tải được danh sách mã.</div>
          : !n ? <div className="p-3 text-muted">{cls === "fav" ? "Chưa có mã yêu thích. Bấm ★ ở mỗi dòng để thêm." : filter ? `Không có mã khớp “${filter}”.` : "Chưa có mã nào trong nhóm này."}</div>
          : (
            <ul role="list" className="relative m-0 list-none p-0" style={{ height: n * ROW }}>
              {visible.map((s, k) => <Row key={s.symbol} s={s} top={(start + k) * ROW} active={s.symbol === active} fav={favSet.has(s.symbol)} onPick={onPick} onFav={onFav} />)}
            </ul>
          )}
      </div>
      <div className="shrink-0 border-t border-line px-3 py-1 text-[11px] text-faint">{n} mã{filter ? " khớp" : ""} · % so với phiên liền trước</div>
    </div>
  );
}
