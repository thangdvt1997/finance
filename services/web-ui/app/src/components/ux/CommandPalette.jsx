// Command palette (Ctrl/Cmd-K) v2: trang, mã (mở chart / thêm danh sách theo dõi / tạo cảnh báo), tin, thuật ngữ, lệnh nhanh, lịch sử gần đây,
// cú pháp lệnh ("cảnh báo eurusd 1.0850", "eurusd h4", tiền tố > $ # ?). Mẫu a11y combobox + listbox. Không có lệnh giao dịch.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellPlus, BookOpen, Bookmark, CandlestickChart, Clock, CornerDownLeft, ListPlus, Newspaper, Search, Terminal, Zap, LayoutDashboard } from "lucide-react";
import { Dialog } from "../dialog";
import { cn } from "../ui";
import { useSymbols } from "../../lib/queries";
import { api } from "../../lib/api";
import { clean, symbolLabel, symbolMarket } from "../../lib/format";
import { buildCommands, fold as foldText, parseIntents, runProviders, score } from "../../ux/commands";
import { useRecent } from "../../ux/recent";
import { addToWatchlistToast } from "../../ux/actions";

const ICONS = { bell: Bell, chart: CandlestickChart, cmd: Terminal };
const PREFIX = { ">": "cmd", "$": "sym", "#": "news", "?": "help" };
const GROUP_ORDER = ["Gợi ý", "Gần đây", "Đã đánh dấu", "Trang", "Mã", "Lệnh", "Tin", "Thuật ngữ", "Khác"];

export function CommandPalette({ open, onClose, routes, label }) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const uid = useId();
  const listRef = useRef(null);
  const qc = useQueryClient();
  const sy = useSymbols();
  const { recent, bookmarks } = useRecent();

  useEffect(() => { if (open) { setQ(""); setIdx(0); } }, [open]);

  const mode = PREFIX[q.trim()[0]] || "all";
  const term = mode === "all" ? q.trim() : q.trim().slice(1).trim();
  const wantNews = open && (mode === "news" || (mode === "all" && term.length >= 3));
  const news = useQuery({ queryKey: ["palette-news"], queryFn: () => api("/news", { limit: 80 }), enabled: wantNews, staleTime: 60_000 });

  // thuật ngữ/FAQ (~9KB) chỉ tải khi cần tra cứu
  const [gl, setGl] = useState(null);
  useEffect(() => { if (open && !gl && (mode === "help" || term.length >= 2)) import("../../ux/glossary").then(setGl); }, [open, gl, mode, term]);
  const GLOSSARY = gl?.GLOSSARY || [], FAQ = gl?.FAQ || [];

  const symbols = useMemo(() => (sy.data || []).map((s) => ({ symbol: s.symbol, label: symbolLabel(s.symbol) })), [sy.data]);

  const results = useMemo(() => {
    const go = (h) => () => { location.hash = h; };
    const pages = routes.map((r) => ({ id: `r-${r.id}`, group: "Trang", label: r.label, hint: r.group || "", icon: r.icon, kw: `${r.id} ${r.group || ""} ${r.keywords || ""}`, run: go(`#/${r.id}`) }));
    const cmds = buildCommands({ qc, label });
    const items = [];
    const rank = (list, t) => list.map((i) => ({ i, s: score(`${i.label} ${i.kw || ""}`, t) })).filter((x) => x.s >= 0).sort((a, b) => b.s - a.s).map((x) => x.i);

    if (!term) {
      if (mode === "cmd") return cmds.slice(0, 40);
      if (mode === "help") return [{ id: "h-open", group: "Thuật ngữ", label: "Mở trang Trợ giúp & thuật ngữ", hint: "#/tro-giup", icon: BookOpen, run: go("#/tro-giup") }, ...GLOSSARY.slice(0, 12).map((g) => ({ id: `g-${g.id}`, group: "Thuật ngữ", label: g.term, hint: g.short.slice(0, 48), icon: BookOpen, run: go(`#/tro-giup?term=${g.id}`) }))];
      if (mode === "sym" || mode === "news") return [];
      const rec = recent.slice(0, 6).map((r) => ({ id: `rec-${r.key}`, group: "Gần đây", label: r.label, hint: r.kind === "symbol" ? "mã" : "trang", icon: Clock, run: go(r.href) }));
      const bm = bookmarks.slice(0, 6).map((b) => ({ id: `bm-${b.href}`, group: "Đã đánh dấu", label: b.label, hint: "đã đánh dấu", icon: Bookmark, run: go(b.href) }));
      return [...rec, ...bm, ...pages, ...cmds.filter((c) => /theme-toggle|bell|help|refresh|tour/.test(c.id))].slice(0, 36);
    }

    if (mode === "all") items.push(...parseIntents(term, symbols).map((x) => ({ ...x, icon: ICONS[x.icon] || Zap })));
    if (mode === "all" || mode === "cmd") items.push(...rank(cmds, term).slice(0, mode === "cmd" ? 30 : 6));
    if (mode === "all") items.push(...rank(pages, term).slice(0, 8));
    if (mode === "all") items.push(...recent.filter((r) => score(r.label, term) >= 0).slice(0, 3).map((r) => ({ id: `rec-${r.key}`, group: "Gần đây", label: r.label, hint: "đã mở", icon: Clock, run: go(r.href) })));
    if (mode === "all" || mode === "sym") {
      const hits = symbols.map((s) => ({ s, sc: score(`${s.label} ${s.symbol}`, term) })).filter((x) => x.sc >= 0).sort((a, b) => b.sc - a.sc).slice(0, mode === "sym" ? 10 : 4);
      for (const { s } of hits) {
        const l = s.label;
        items.push({ id: `s-${s.symbol}`, group: "Mã", label: `Mở biểu đồ ${l}`, hint: symbolMarket(s.symbol), icon: CandlestickChart, run: go(`#/thi-truong/${encodeURIComponent(s.symbol)}`) });
        items.push({ id: `w-${s.symbol}`, group: "Mã", label: `Thêm ${l} vào danh sách theo dõi`, hint: "nhóm đang chọn", icon: ListPlus, run: () => addToWatchlistToast(s.symbol) });
        items.push({ id: `a-${s.symbol}`, group: "Mã", label: `Tạo cảnh báo giá ${l}`, hint: "biểu mẫu", icon: BellPlus, run: go(`#/canh-bao/new?symbol=${encodeURIComponent(s.symbol)}`) });
      }
    }
    if (mode === "all" || mode === "news") {
      const t = foldText(term);
      const list = (news.data?.items || []).filter((n) => foldText(`${n.title} ${n.summary || ""}`).includes(t)).slice(0, mode === "news" ? 15 : 4);
      items.push(...list.map((n) => ({ id: `n-${n.url}`, group: "Tin", label: clean(n.title), hint: "mở bài", icon: Newspaper, run: () => window.open(n.url, "_blank", "noopener,noreferrer") })));
      if (mode === "news" && news.isPending) items.push({ id: "n-load", group: "Tin", label: "Đang tải tin…", hint: "", icon: Newspaper, run: () => {} });
    }
    if (mode === "all" || mode === "help") {
      const gl = GLOSSARY.map((g) => ({ g, sc: score(`${g.term} ${(g.aka || []).join(" ")}`, term) })).filter((x) => x.sc >= 0).sort((a, b) => b.sc - a.sc).slice(0, mode === "help" ? 10 : 3);
      items.push(...gl.map(({ g }) => ({ id: `g-${g.id}`, group: "Thuật ngữ", label: g.term, hint: "giải thích", icon: BookOpen, run: go(`#/tro-giup?term=${g.id}`) })));
      if (mode === "help") {
        const fq = FAQ.map((f, i) => ({ f, i, sc: score(f.q, term) })).filter((x) => x.sc >= 0).slice(0, 5);
        items.push(...fq.map(({ f, i }) => ({ id: `f-${i}`, group: "Thuật ngữ", label: f.q, hint: "câu hỏi thường gặp", icon: BookOpen, run: go(`#/tro-giup?faq=${i}`) })));
      }
    }
    if (mode === "all") items.push(...runProviders(term, { go }).map((x) => ({ group: "Khác", icon: Zap, ...x })));
    // sắp theo nhóm cố định, giữ thứ tự điểm trong nhóm
    return items.map((it, i) => ({ it, i })).sort((a, b) => (GROUP_ORDER.indexOf(a.it.group) - GROUP_ORDER.indexOf(b.it.group)) || a.i - b.i).map((x) => x.it).slice(0, 40);
  }, [routes, term, mode, symbols, recent, bookmarks, news.data, news.isPending, qc, label, gl]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setIdx(0); }, [q]);
  useEffect(() => { listRef.current?.querySelector(`[data-i="${idx}"]`)?.scrollIntoView({ block: "nearest" }); }, [idx]);

  const choose = (it) => { if (!it) return; onClose(); setTimeout(() => it.run(), 0); };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Home" && e.ctrlKey) { e.preventDefault(); setIdx(0); }
    else if (e.key === "End" && e.ctrlKey) { e.preventDefault(); setIdx(results.length - 1); }
    else if (e.key === "Enter") { e.preventDefault(); choose(results[idx]); }
    else if (e.key === "Tab" && !e.shiftKey && !q) { e.preventDefault(); setQ(">"); }
  };

  return (
    <Dialog open={open} onClose={onClose} labelledBy={`${uid}-t`} initialFocus="[data-autofocus]">
      <h2 id={`${uid}-t`} className="sr-only">Tìm nhanh và lệnh</h2>
      <div className="flex items-center gap-2 px-3 border-b border-line">
        <Search size={16} className="text-muted shrink-0" aria-hidden="true" />
        <input data-autofocus role="combobox" aria-expanded="true" aria-controls={`${uid}-l`} aria-autocomplete="list" aria-label="Tìm trang, mã, tin, thuật ngữ hoặc gõ lệnh"
          aria-activedescendant={results.length ? `${uid}-o${idx}` : undefined}
          className="ux-pal-in flex-1 min-w-0 h-12 bg-transparent border-0 text-fg text-[14px] outline-none" placeholder="Tìm trang, mã, tin… hoặc gõ lệnh (vd: cảnh báo eurusd 1.0850)"
          value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} autoComplete="off" spellCheck={false} />
        <kbd className="ux-kbd">Esc</kbd>
      </div>
      <div className="flex flex-wrap gap-1 px-3 py-[6px] border-b border-line text-[11.5px] text-muted" aria-label="Cú pháp">
        {[[">", "lệnh"], ["$", "mã"], ["#", "tin"], ["?", "thuật ngữ"]].map(([k, l]) => (
          <button key={k} type="button" className={cn("ux-chip", mode !== "all" && PREFIX[k] === mode && "on")} onClick={() => { setQ(k); document.querySelector("[data-autofocus]")?.focus(); }} aria-label={`Chỉ tìm ${l} (gõ ${k})`}><kbd>{k}</kbd> {l}</button>
        ))}
      </div>
      <ul id={`${uid}-l`} ref={listRef} role="listbox" aria-label="Kết quả" className="m-0 p-1 list-none max-h-[55dvh] overflow-auto">
        {results.length === 0 && <li className="px-3 py-6 text-center text-muted" role="presentation">{mode === "sym" || mode === "news" ? (term ? `Không có kết quả cho “${term}”.` : mode === "sym" ? "Gõ mã, ví dụ: eurusd, vcb" : "Gõ từ khoá để tìm trong tin mới.") : `Không có kết quả cho “${q}”. Thử “>” để xem lệnh hoặc “?” để xem thuật ngữ.`}</li>}
        {results.map((it, i) => {
          const Ic = it.icon || LayoutDashboard;
          const newGroup = i === 0 || results[i - 1].group !== it.group;
          return (
            <li key={it.id} role="presentation">
              {newGroup && <div className="px-2 pt-2 pb-1 text-[10.5px] uppercase tracking-wide text-faint" aria-hidden="true">{it.group}</div>}
              <div id={`${uid}-o${i}`} data-i={i} role="option" aria-selected={i === idx} onMouseEnter={() => setIdx(i)} onClick={() => choose(it)}
                className={cn("flex items-center gap-3 px-2 py-2 rounded-md cursor-pointer", i === idx && "bg-panel2 shadow-[inset_2px_0_0_var(--accent)]")}>
                <Ic size={16} className="text-muted shrink-0" aria-hidden="true" />
                <span className="flex-1 min-w-0 truncate text-[13px]"><span className="sr-only">{it.group}: </span>{it.label}</span>
                {it.hint && <span className="text-[11px] text-faint shrink-0 max-w-[40%] truncate">{it.hint}</span>}
                {i === idx && <CornerDownLeft size={13} className="text-faint shrink-0" aria-hidden="true" />}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="px-3 py-2 border-t border-line text-[11px] text-faint flex gap-3 flex-wrap">
        <span>↑↓ chọn</span><span>Enter mở</span><span>Tab = lệnh</span><span>Esc đóng</span><span className="ml-auto">Nhấn <kbd>?</kbd> ngoài hộp tìm để xem phím tắt</span>
      </div>
    </Dialog>
  );
}
