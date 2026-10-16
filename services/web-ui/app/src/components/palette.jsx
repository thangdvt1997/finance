// Command palette (Ctrl/Cmd-K): tìm trang, mã, lệnh. Mẫu a11y combobox + listbox. Chỉ điều hướng, không có lệnh giao dịch.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { BellPlus, CandlestickChart, CornerDownLeft, Moon, Search, Sun, LayoutDashboard } from "lucide-react";
import { Dialog } from "./dialog";
import { cn } from "./ui";
import { useSymbols } from "../lib/queries";
import { symbolLabel, symbolMarket } from "../lib/format";

const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();

/** Khớp mờ đơn giản: mọi từ phải xuất hiện (chuỗi con) hoặc là dãy con; điểm cao hơn = khớp tốt hơn. */
function score(text, query) {
  const t = fold(text);
  let total = 0;
  for (const w of fold(query).split(/\s+/).filter(Boolean)) {
    const i = t.indexOf(w);
    if (i >= 0) { total += 100 - Math.min(i, 60) + (i === 0 ? 30 : 0); continue; }
    let k = 0, gaps = 0;
    for (const ch of t) { if (ch === w[k]) k++; else if (k) gaps++; if (k === w.length) break; }
    if (k < w.length) return -1;
    total += 20 - Math.min(gaps, 18);
  }
  return total;
}

export function CommandPalette({ open, onClose, routes, theme, onToggleTheme }) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const uid = useId();
  const listRef = useRef(null);
  const sy = useSymbols();

  useEffect(() => { if (open) { setQ(""); setIdx(0); } }, [open]);

  const all = useMemo(() => {
    const go = (h) => () => { location.hash = h; };
    const items = routes.map((r) => ({ id: `r-${r.id}`, group: "Trang", label: r.label, hint: `#/${r.id}`, icon: r.icon, kw: r.id, run: go(`#/${r.id}`) }));
    items.push({ id: "c-theme", group: "Lệnh", label: theme === "dark" ? "Đổi sang giao diện sáng" : "Đổi sang giao diện tối", hint: "T", icon: theme === "dark" ? Sun : Moon, kw: "doi giao dien theme sang toi dark light", run: onToggleTheme });
    items.push({ id: "c-newalert", group: "Lệnh", label: "Tạo quy tắc cảnh báo mới", hint: "", icon: BellPlus, kw: "tao canh bao alert rule", run: go("#/canh-bao/new") });
    for (const s of sy.data || []) {
      const l = symbolLabel(s.symbol);
      items.push({ id: `s-${s.symbol}`, group: "Mã", label: l, hint: symbolMarket(s.symbol), icon: CandlestickChart, kw: s.symbol, run: go(`#/thi-truong/${encodeURIComponent(s.symbol)}`) });
      items.push({ id: `a-${s.symbol}`, group: "Cảnh báo", label: `Tạo cảnh báo cho ${l}`, hint: symbolLabel(s.symbol), icon: BellPlus, kw: `tao canh bao alert ${s.symbol}`, run: go(`#/canh-bao/new?symbol=${encodeURIComponent(s.symbol)}`) });
    }
    return items;
  }, [routes, sy.data, theme, onToggleTheme]);

  const results = useMemo(() => {
    const t = q.trim();
    if (!t) return all.filter((i) => i.group === "Trang" || i.group === "Lệnh").slice(0, 24);
    return all.map((i) => ({ i, s: score(`${i.label} ${i.kw}`, t) })).filter((x) => x.s >= 0).sort((a, b) => b.s - a.s).slice(0, 30).map((x) => x.i);
  }, [all, q]);

  useEffect(() => { setIdx(0); }, [q]);
  useEffect(() => { listRef.current?.querySelector(`[data-i="${idx}"]`)?.scrollIntoView({ block: "nearest" }); }, [idx]);

  const choose = (it) => { if (!it) return; onClose(); setTimeout(() => it.run(), 0); };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Home") { e.preventDefault(); setIdx(0); }
    else if (e.key === "End") { e.preventDefault(); setIdx(results.length - 1); }
    else if (e.key === "Enter") { e.preventDefault(); choose(results[idx]); }
  };

  return (
    <Dialog open={open} onClose={onClose} labelledBy={`${uid}-t`} initialFocus="[data-autofocus]">
      <h2 id={`${uid}-t`} className="sr-only">Tìm nhanh và lệnh</h2>
      <div className="flex items-center gap-2 px-3 border-b border-line">
        <Search size={16} className="text-muted shrink-0" aria-hidden="true" />
        <input data-autofocus role="combobox" aria-expanded="true" aria-controls={`${uid}-l`} aria-autocomplete="list" aria-label="Tìm trang, mã hoặc lệnh"
          aria-activedescendant={results.length ? `${uid}-o${idx}` : undefined}
          className="flex-1 min-w-0 h-12 bg-transparent border-0 text-fg text-[14px] outline-none" placeholder="Tìm trang, mã, lệnh… (vd: eurusd, cảnh báo)"
          value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} autoComplete="off" spellCheck={false} />
        <kbd className="text-[10.5px] text-faint border border-line2 rounded px-1">Esc</kbd>
      </div>
      <ul id={`${uid}-l`} ref={listRef} role="listbox" aria-label="Kết quả" className="m-0 p-1 list-none max-h-[55dvh] overflow-auto">
        {results.length === 0 && <li className="px-3 py-6 text-center text-muted" role="presentation">Không có kết quả cho “{q}”.</li>}
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
                <span className="text-[11px] text-faint shrink-0">{it.hint}</span>
                {i === idx && <CornerDownLeft size={13} className="text-faint shrink-0" aria-hidden="true" />}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="px-3 py-2 border-t border-line text-[11px] text-faint flex gap-3 flex-wrap">
        <span>↑↓ chọn</span><span>Enter mở</span><span>Esc đóng</span><span className="ml-auto">Nhấn <kbd>?</kbd> để xem phím tắt</span>
      </div>
    </Dialog>
  );
}
