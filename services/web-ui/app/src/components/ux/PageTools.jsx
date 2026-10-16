// Nút "Công cụ trang" trên thanh trên: xuất/in/chia sẻ/đánh dấu cho trang hiện tại. Quét bảng thật trong <main> khi mở menu.
import { useEffect, useMemo, useRef, useState } from "react";
import { Bookmark, BookmarkCheck, Clock, Copy, FileSpreadsheet, FileText, Image as ImageIcon, Link2, Printer, Share2, Table2 } from "lucide-react";
import { cn } from "../ui";
import { copyText } from "../../ux/actions";
import { removeBookmark, toggleBookmark, useRecent } from "../../ux/recent";
import { toast } from "../../ux/bus";

function Item({ icon: Ic, children, onClick, disabled, hint }) {
  return (
    <button type="button" role="menuitem" className="ux-menuitem" onClick={onClick} disabled={disabled}>
      <Ic size={15} className="shrink-0 text-muted" aria-hidden="true" />
      <span className="flex-1 min-w-0 truncate text-left">{children}</span>
      {hint && <span className="text-[11px] text-faint shrink-0">{hint}</span>}
    </button>
  );
}

export function PageTools({ route, label }) {
  const [open, setOpen] = useState(false);
  const [tables, setTables] = useState([]);
  const [sel, setSel] = useState(0);
  const [ex, setEx] = useState(null); // ux/exporters nạp lười khi mở menu lần đầu (không nằm trong bundle chính)
  const { bookmarks, recent } = useRecent();
  const btn = useRef(null);
  const menu = useRef(null);
  const href = `#/${route.id}${route.arg ? `/${route.arg}` : ""}`;
  const bm = useMemo(() => bookmarks.some((b) => b.href === href), [bookmarks, href]);

  useEffect(() => { setOpen(false); }, [href]);
  useEffect(() => {
    if (!open) return;
    let live = true;
    import("../../ux/exporters").then((m) => { if (!live) return; setEx(m); const t = m.findTables(); setTables(t); setSel((s) => Math.min(s, Math.max(0, t.length - 1))); });
    menu.current?.querySelector("[role=menuitem]:not(:disabled)")?.focus();
    const away = (e) => { if (!menu.current?.contains(e.target) && !btn.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => { live = false; document.removeEventListener("pointerdown", away); };
  }, [open]);

  const onKey = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); setOpen(false); btn.current?.focus(); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Home" && e.key !== "End") return;
    const items = [...menu.current.querySelectorAll("[role=menuitem]:not(:disabled)")];
    const i = items.indexOf(document.activeElement);
    e.preventDefault();
    const n = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
    items[n]?.focus();
  };

  const cur = tables[sel];
  const run = async (fn, ok) => { setOpen(false); try { await fn(); if (ok) toast({ tone: "ok", title: ok, ttl: 2800 }); } catch (e) { toast({ tone: "error", title: "Không thực hiện được", body: e?.message || "Thử lại sau.", ttl: 5000 }); } };
  const matrix = () => ex.tableToMatrix(cur.el);
  const target = () => document.getElementById("main")?.querySelector(".page") || document.getElementById("main");
  const panelOf = () => cur?.el.closest(".panel");

  return (
    <div className="relative no-print">
      <button ref={btn} type="button" className="btn !px-2" aria-haspopup="menu" aria-expanded={open} aria-label="Công cụ trang: xuất, in, chia sẻ, đánh dấu" title="Công cụ trang" onClick={() => setOpen((v) => !v)} data-tour="tools">
        <Share2 size={15} aria-hidden="true" />
      </button>
      {open && (
        <div ref={menu} role="menu" aria-label="Công cụ trang" className="ux-menu" onKeyDown={onKey}>
          <div className="ux-menu-h">Trang: {label}</div>
          {tables.length > 1 && (
            <div className="px-2 pb-1">
              <label className="text-[11px] text-faint block mb-1" htmlFor="ux-tbl">Bảng cần xuất ({tables.length})</label>
              <select id="ux-tbl" className="field w-full !h-8" value={sel} onChange={(e) => setSel(+e.target.value)}>
                {tables.map((t, i) => <option key={i} value={i}>{t.title} ({t.rows} dòng)</option>)}
              </select>
            </div>
          )}
          <Item icon={Table2} disabled={!cur || !ex} onClick={() => run(() => ex.downloadCSV(matrix(), cur.title), "Đã tải CSV")} hint={cur ? "CSV" : "không có bảng"}>Xuất bảng ra CSV</Item>
          <Item icon={FileSpreadsheet} disabled={!cur || !ex} onClick={() => run(() => ex.downloadXLSX(matrix(), cur.title), "Đã tải Excel")} hint=".xlsx">Xuất bảng ra Excel</Item>
          <Item icon={Copy} disabled={!cur || !ex} onClick={() => run(async () => { if (!(await ex.copyMatrix(matrix()))) throw new Error("Trình duyệt chặn sao chép."); }, "Đã sao chép bảng, dán vào Excel/Sheets")}>Sao chép bảng (dán vào Excel)</Item>
          <div className="ux-menu-sep" role="separator" />
          <Item icon={ImageIcon} disabled={!panelOf() || !ex} onClick={() => run(() => ex.downloadPNG(panelOf(), cur.title), "Đã lưu ảnh PNG")}>Lưu ảnh khung chứa bảng</Item>
          <Item icon={ImageIcon} disabled={!ex} onClick={() => run(() => ex.downloadPNG(target(), label), "Đã lưu ảnh PNG")}>Lưu ảnh cả trang</Item>
          <Item icon={Printer} disabled={!ex} onClick={() => { setOpen(false); ex.printPage(); }} hint="PDF">In / lưu PDF</Item>
          <div className="ux-menu-sep" role="separator" />
          <Item icon={Link2} onClick={() => run(async () => { if (!(await copyText(location.href))) throw new Error("Trình duyệt chặn sao chép."); }, "Đã sao chép liên kết (giữ nguyên mã/khung/bộ lọc trong địa chỉ)")}>Sao chép liên kết trang</Item>
          <Item icon={bm ? BookmarkCheck : Bookmark} onClick={() => run(() => { const on = toggleBookmark({ href, label: `${label}${route.arg ? ` · ${decodeURIComponent(route.arg.split("?")[0])}` : ""}`, kind: "page" }); toast({ tone: "ok", title: on ? "Đã đánh dấu trang" : "Đã bỏ đánh dấu", ttl: 2200 }); })}>{bm ? "Bỏ đánh dấu trang này" : "Đánh dấu trang này"}</Item>
          {bookmarks.length > 0 && (
            <>
              <div className="ux-menu-h">Đã đánh dấu</div>
              {bookmarks.slice(0, 6).map((b) => (
                <a key={b.href} role="menuitem" href={b.href} className="ux-menuitem no-underline" onClick={() => setOpen(false)}>
                  <BookmarkCheck size={15} className="shrink-0 text-accent" aria-hidden="true" /><span className="truncate">{b.label}</span>
                </a>
              ))}
            </>
          )}
          {recent.length > 0 && (
            <>
              <div className="ux-menu-h">Gần đây</div>
              {recent.slice(0, 5).map((b) => (
                <a key={b.key} role="menuitem" href={b.href} className={cn("ux-menuitem no-underline", b.href === href && "opacity-60")} onClick={() => setOpen(false)}>
                  <Clock size={15} className="shrink-0 text-muted" aria-hidden="true" /><span className="truncate">{b.label}</span>
                </a>
              ))}
            </>
          )}
          <div className="ux-menu-foot"><FileText size={12} aria-hidden="true" /> Bảng được xuất đúng như hiển thị. {bookmarks.length > 0 && <button type="button" className="ux-link" onClick={() => { bookmarks.forEach((b) => removeBookmark(b.href)); }}>Xoá đánh dấu</button>}</div>
        </div>
      )}
    </div>
  );
}
