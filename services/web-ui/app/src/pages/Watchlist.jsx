import { useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, BellPlus, Check, ChevronDown, ChevronUp, GripVertical, ListChecks, Pencil, Plus, RefreshCw, Star, Trash2, X } from "lucide-react";
import { Async, Chip, PageHead, Panel, Seg, cn } from "../components/ui";
import { Dialog } from "../components/dialog";
import { TFS, WATCH } from "../lib/api";
import { useQuotesLatest, useSymbols, useTheme } from "../lib/queries";
import { useQuote } from "../lib/stream";
import { MAX_GROUPS, MAX_SYMBOLS, SYM_RE, activeGroup, flush, mutatePrefs, newGroupId, usePrefsState, watchlistsOf } from "../lib/prefs";
import { price, symbolLabel, symbolMarket, time } from "../lib/format";

// ---------- thao tác trên prefs (đều qua mutatePrefs: lưu trễ + áp lại khi xung đột) ----------
const upd = (fn) => mutatePrefs((p) => ({ ...p, watchlists: fn(watchlistsOf(p)) }));
const mapG = (id, fn) => upd((ws) => ws.map((w) => (w.id === id ? fn(w) : w)));
const moveIn = (arr, from, to) => {
  if (from === to || from < 0 || to < 0 || from >= arr.length || to >= arr.length) return arr;
  const a = arr.slice();
  a.splice(to, 0, a.splice(from, 1)[0]);
  return a;
};
const ops = {
  create(name, symbols = []) {
    const id = newGroupId();
    mutatePrefs((p) => {
      const ws = watchlistsOf(p);
      if (ws.length >= MAX_GROUPS) return p;
      return { ...p, watchlists: [...ws, { id, name, symbols, tf: "H1" }], active_watchlist: ws.length ? p.active_watchlist : id };
    });
    return id;
  },
  rename: (id, name) => mapG(id, (w) => ({ ...w, name })),
  remove: (id) => mutatePrefs((p) => {
    const ws = watchlistsOf(p).filter((w) => w.id !== id);
    return { ...p, watchlists: ws, active_watchlist: ws.some((w) => w.id === p.active_watchlist) ? p.active_watchlist : ws[0]?.id };
  }),
  moveGroup: (from, to) => upd((ws) => moveIn(ws, from, to)),
  setActive: (id) => mutatePrefs((p) => ({ ...p, active_watchlist: id })),
  setTf: (id, tf) => mapG(id, (w) => ({ ...w, tf })),
  addSym: (id, sym) => mapG(id, (w) => (w.symbols.includes(sym) || w.symbols.length >= MAX_SYMBOLS ? w : { ...w, symbols: [...w.symbols, sym] })),
  rmSym: (id, sym) => mapG(id, (w) => ({ ...w, symbols: w.symbols.filter((s) => s !== sym) })),
  moveSym: (id, from, to) => mapG(id, (w) => ({ ...w, symbols: moveIn(w.symbols, from, to) })),
};

/** Kéo-thả HTML5 (chuột). Nút lên/xuống là phương án bàn phím/cảm ứng. */
function useDnd(onMove) {
  const [over, setOver] = useState(null);
  const from = useRef(null);
  return {
    over,
    props: (i) => ({
      draggable: true,
      onDragStart: (e) => { from.current = i; e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", String(i)); } catch { /* bỏ qua */ } },
      onDragOver: (e) => { if (from.current != null) { e.preventDefault(); setOver(i); } },
      onDragLeave: () => setOver((o) => (o === i ? null : o)),
      onDrop: (e) => { e.preventDefault(); if (from.current != null) onMove(from.current, i); from.current = null; setOver(null); },
      onDragEnd: () => { from.current = null; setOver(null); },
    }),
  };
}

// ---------- trạng thái lưu ----------
function SaveStatus({ st }) {
  const map = {
    saving: ["Đang lưu…", "text-muted"], dirty: ["Có thay đổi, sắp lưu…", "text-muted"], saved: ["Đã lưu", "text-up"],
    error: [st.message || "Lưu lỗi", "text-down"], conflict: [st.message || "Đã tải lại bản mới", "text-accent"],
  };
  const [text, cls] = map[st.status] || ["", ""];
  return (
    <div className="flex items-center gap-2 text-[12px]" role="status" aria-live="polite">
      {text && <span className={cn("flex items-center gap-1", cls)}>{st.status === "saved" && <Check size={13} aria-hidden="true" />}{(st.status === "error" || st.status === "conflict") && <AlertTriangle size={13} aria-hidden="true" />}{text}</span>}
      {(st.status === "error" || !st.available) && <button type="button" className="btn" onClick={() => flush()}><RefreshCw size={13} aria-hidden="true" /> Thử lại</button>}
    </div>
  );
}

// ---------- ô thêm mã (combobox) ----------
function SymbolPicker({ onPick, have }) {
  const sy = useSymbols();
  const [v, setV] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const uid = useId();
  const list = useMemo(() => {
    const f = v.trim().toLowerCase();
    const all = sy.data || [];
    const m = all.filter((s) => !have.has(s.symbol) && (!f || s.symbol.toLowerCase().includes(f)));
    m.sort((a, b) => (a.symbol.toLowerCase().startsWith(f) ? 0 : 1) - (b.symbol.toLowerCase().startsWith(f) ? 0 : 1));
    return m.slice(0, 8).map((s) => s.symbol);
  }, [sy.data, v, have]);
  const cv = v.trim().toUpperCase();
  const custom = cv && SYM_RE.test(cv) && !have.has(cv) && !list.includes(cv) ? cv : null;
  const opts = custom ? [...list, custom] : list;
  const pick = (s) => { if (!s) return; onPick(s); setV(""); setIdx(0); };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setIdx((i) => Math.min(i + 1, opts.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(opts[idx] ?? custom); }
    else if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); }
  };
  return (
    <div className="relative min-w-0 w-full sm:w-72">
      <label htmlFor={`${uid}-i`} className="sr-only">Thêm mã vào nhóm</label>
      <input id={`${uid}-i`} role="combobox" aria-expanded={open && opts.length > 0} aria-controls={`${uid}-l`} aria-autocomplete="list"
        aria-activedescendant={open && opts.length ? `${uid}-o${idx}` : undefined}
        className="field w-full" placeholder="Thêm mã… (vd EURUSD, VN:FPT)" autoComplete="off" spellCheck={false}
        value={v} onChange={(e) => { setV(e.target.value); setIdx(0); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)} onKeyDown={onKey} />
      {open && opts.length > 0 && (
        <ul id={`${uid}-l`} role="listbox" aria-label="Gợi ý mã" className="absolute z-20 left-0 right-0 top-full mt-1 m-0 p-1 list-none rounded-md border border-line2 bg-panel shadow-xl max-h-64 overflow-auto">
          {opts.map((s, i) => (
            <li key={s} id={`${uid}-o${i}`} role="option" aria-selected={i === idx} onMouseDown={(e) => { e.preventDefault(); pick(s); }} onMouseEnter={() => setIdx(i)}
              className={cn("flex items-center justify-between gap-2 px-2 py-[6px] rounded cursor-pointer text-[13px]", i === idx && "bg-panel2")}>
              <b>{symbolLabel(s)}</b>
              <span className="text-[11px] text-faint">{s === custom ? "mã tự nhập" : symbolMarket(s)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------- dòng giá ----------
function Row({ sym, i, n, group, dnd }) {
  const q = useQuote(sym);
  const tf = group.tf && TFS.includes(group.tf) ? group.tf : "H1";
  const mv = (d) => ops.moveSym(group.id, i, i + d);
  return (
    <tr {...dnd.props(i)} className={cn(dnd.over === i && "outline outline-1 outline-[var(--accent)]")}>
      <td className="w-6 !pr-0 text-faint cursor-grab" aria-hidden="true"><GripVertical size={14} /></td>
      <td>
        <a href={`#/thi-truong/${encodeURIComponent(sym)}?tf=${tf}`} className="font-semibold no-underline hover:underline" title={`Mở biểu đồ ${sym} (${tf})`}>{symbolLabel(sym)}</a>
        <span className="ml-2 text-[11px] text-faint">{symbolMarket(sym)}</span>
      </td>
      <td className="r"><span className={cn("num", q?.dir > 0 ? "up" : q?.dir < 0 ? "down" : "")}>{price(sym, q?.bid ?? q?.ask)}</span></td>
      <td className="r num text-muted hidden sm:table-cell">{price(sym, q?.ask)}</td>
      <td className="r num text-faint hidden md:table-cell">{q?.ts ? time(q.ts) : "—"}</td>
      <td className="r whitespace-nowrap">
        <a className="btn !px-2 no-underline" href={`#/canh-bao/new?symbol=${encodeURIComponent(sym)}`} aria-label={`Tạo cảnh báo cho ${symbolLabel(sym)}`} title="Tạo cảnh báo"><BellPlus size={14} aria-hidden="true" /></a>{" "}
        <button type="button" className="btn !px-2" onClick={() => mv(-1)} disabled={i === 0} aria-label={`Đưa ${symbolLabel(sym)} lên`}><ChevronUp size={14} aria-hidden="true" /></button>{" "}
        <button type="button" className="btn !px-2" onClick={() => mv(1)} disabled={i === n - 1} aria-label={`Đưa ${symbolLabel(sym)} xuống`}><ChevronDown size={14} aria-hidden="true" /></button>{" "}
        <button type="button" className="btn !px-2" onClick={() => ops.rmSym(group.id, sym)} aria-label={`Bỏ ${symbolLabel(sym)} khỏi nhóm`}><X size={14} aria-hidden="true" /></button>
      </td>
    </tr>
  );
}

function GroupTable({ group }) {
  useQuotesLatest(group.symbols);
  const dnd = useDnd((a, b) => ops.moveSym(group.id, a, b));
  const have = useMemo(() => new Set(group.symbols), [group.symbols]);
  return (
    <>
      <div className="p-3 flex flex-wrap items-center gap-3 border-b border-line">
        <SymbolPicker onPick={(s) => ops.addSym(group.id, s)} have={have} />
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-[12px] text-muted" id={`tf-${group.id}`}>Khung biểu đồ</span>
          <Seg value={group.tf} onChange={(t) => ops.setTf(group.id, t)} label="Khung biểu đồ ưa thích" options={TFS} />
        </div>
      </div>
      <div className="scroll-y scroll-x">
        {group.symbols.length === 0 ? (
          <p className="m-0 p-4 text-muted">Nhóm chưa có mã. Gõ tên mã vào ô phía trên để thêm.</p>
        ) : (
          <table className="tbl">
            <caption className="sr-only">Giá trực tiếp của nhóm {group.name}</caption>
            <thead><tr><th className="w-6"><span className="sr-only">Kéo</span></th><th>Mã</th><th className="r">Bid</th><th className="r hidden sm:table-cell">Ask</th><th className="r hidden md:table-cell">Cập nhật</th><th className="r"><span className="sr-only">Thao tác</span></th></tr></thead>
            <tbody>{group.symbols.map((s, i) => <Row key={s} sym={s} i={i} n={group.symbols.length} group={group} dnd={dnd} />)}</tbody>
          </table>
        )}
      </div>
      <p className="m-0 px-3 py-2 text-[11.5px] text-faint border-t border-line">{group.symbols.length}/{MAX_SYMBOLS} mã · kéo biểu tượng ⋮⋮ hoặc dùng nút ↑ ↓ để sắp xếp · giá chỉ mang tính tham khảo.</p>
    </>
  );
}

// ---------- hộp thoại tên nhóm ----------
function NameDialog({ state, onClose }) {
  const [name, setName] = useState(state?.name || "");
  const [err, setErr] = useState("");
  const uid = useId();
  const submit = (e) => {
    e?.preventDefault();
    const n = name.trim();
    if (!n) return setErr("Nhập tên nhóm.");
    if (n.length > 40) return setErr("Tên tối đa 40 ký tự.");
    state.onOk(n);
    onClose();
  };
  return (
    <Dialog open onClose={onClose} title={state.title} initialFocus="[data-autofocus]"
      footer={<><button type="button" className="btn" onClick={onClose}>Huỷ</button><button type="button" className="btn !bg-accent !text-[var(--accent-fg)] !border-transparent font-semibold" onClick={submit}>{state.cta}</button></>}>
      <form onSubmit={submit} className="p-3 grid gap-1">
        <label htmlFor={uid} className="text-[11.5px] text-muted">Tên nhóm</label>
        <input id={uid} data-autofocus className="field w-full" value={name} maxLength={40} onChange={(e) => { setName(e.target.value); setErr(""); }} aria-invalid={err ? true : undefined} placeholder="VD: Forex chính" />
        {err && <span className="text-[11.5px] text-down" role="alert">{err}</span>}
      </form>
    </Dialog>
  );
}

export default function Watchlist() {
  const st = usePrefsState();
  const [theme, setTheme] = useTheme();
  const ws = watchlistsOf(st.prefs);
  const [sel, setSel] = useState(null);
  const [dlg, setDlg] = useState(null); // {kind:'name'|'del', ...}
  const cur = ws.find((w) => w.id === sel) || activeGroup(st.prefs);
  const dnd = useDnd(ops.moveGroup);
  const loading = !st.loaded;

  const askCreate = (symbols) => setDlg({ kind: "name", title: "Tạo nhóm theo dõi", cta: "Tạo nhóm", name: "", onOk: (n) => setSel(ops.create(n, symbols || [])) });
  const askRename = (g) => setDlg({ kind: "name", title: "Đổi tên nhóm", cta: "Lưu tên", name: g.name, onOk: (n) => ops.rename(g.id, n) });

  return (
    <>
      <PageHead title="Danh sách theo dõi" sub="Gom mã thành nhiều nhóm, xem giá trực tiếp. Nhóm mặc định (có dấu sao) quyết định băng giá trên đầu trang. Lưu trên máy chủ, dùng được ở mọi thiết bị."
        right={<>
          <SaveStatus st={st} />
          <Seg value={theme} onChange={setTheme} label="Giao diện" options={[{ value: "dark", label: "Tối" }, { value: "light", label: "Sáng" }]} />
        </>} />

      {!loading && !st.available && ws.length === 0 && (
        <div role="alert" className="rounded-md border border-line2 bg-panel2 p-3 text-[12.5px] flex gap-2 items-start">
          <AlertTriangle size={15} className="text-accent shrink-0 mt-[2px]" aria-hidden="true" />
          <div>Chưa kết nối được kho tuỳ chọn trên máy chủ ({st.message || "lỗi không rõ"}). Bạn vẫn có thể thao tác, thay đổi sẽ được lưu khi máy chủ sẵn sàng.</div>
        </div>
      )}

      {loading ? <Panel title="Danh sách theo dõi" icon={ListChecks}><Async q={{ isPending: true }} /></Panel> : ws.length === 0 ? (
        <Panel title="Chưa có nhóm nào" icon={ListChecks}>
          <p className="mt-0 text-muted">Băng giá đang dùng danh sách mặc định của hệ thống. Tạo nhóm của riêng bạn để thay thế.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn !bg-accent !text-[var(--accent-fg)] !border-transparent font-semibold" onClick={() => askCreate([...WATCH])}><Plus size={14} aria-hidden="true" /> Tạo từ danh sách mặc định</button>
            <button type="button" className="btn" onClick={() => askCreate([])}>Tạo nhóm trống</button>
          </div>
        </Panel>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[17rem_minmax(0,1fr)] lg:flex-1 lg:min-h-0 items-start lg:items-stretch">
          <Panel title="Nhóm" icon={ListChecks} pad={false} right={<button type="button" className="btn" onClick={() => askCreate([])} disabled={ws.length >= MAX_GROUPS}><Plus size={14} aria-hidden="true" /> Nhóm mới</button>}>
            <ul className="m-0 p-1 list-none grid gap-[2px]" aria-label="Các nhóm theo dõi">
              {ws.map((g, i) => {
                const on = g.id === cur?.id;
                const isDef = g.id === (st.prefs.active_watchlist || ws[0]?.id);
                return (
                  <li key={g.id} {...dnd.props(i)} className={cn("rounded-md", dnd.over === i && "outline outline-1 outline-[var(--accent)]")}>
                    <div className={cn("flex items-center gap-1 rounded-md pr-1", on ? "bg-panel2 shadow-[inset_2px_0_0_var(--accent)]" : "hover:bg-panel2")}>
                      <button type="button" aria-current={on ? "true" : undefined} onClick={() => setSel(g.id)}
                        className="flex-1 min-w-0 text-left bg-transparent border-0 text-fg font-[inherit] cursor-pointer px-2 py-[7px] flex items-center gap-2">
                        {isDef ? <Star size={13} className="text-accent shrink-0" fill="currentColor" aria-label="Nhóm mặc định" /> : <span className="w-[13px] shrink-0" aria-hidden="true" />}
                        <span className="min-w-0 flex-1"><b className="block truncate text-[13px]">{g.name}</b><span className="text-[11px] text-faint">{g.symbols.length} mã · {g.tf}</span></span>
                      </button>
                      <button type="button" className="btn !px-1 !h-7 !border-transparent !bg-transparent" onClick={() => ops.moveGroup(i, i - 1)} disabled={i === 0} aria-label={`Đưa nhóm ${g.name} lên`}><ChevronUp size={14} aria-hidden="true" /></button>
                      <button type="button" className="btn !px-1 !h-7 !border-transparent !bg-transparent" onClick={() => ops.moveGroup(i, i + 1)} disabled={i === ws.length - 1} aria-label={`Đưa nhóm ${g.name} xuống`}><ChevronDown size={14} aria-hidden="true" /></button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Panel>

          {cur && (
            <Panel title={cur.name} icon={ListChecks} pad={false} fill bodyClass="flex flex-col"
              right={<>
                {cur.id === (st.prefs.active_watchlist || ws[0]?.id)
                  ? <Chip tone="accent"><Star size={11} fill="currentColor" aria-hidden="true" /> Mặc định</Chip>
                  : <button type="button" className="btn" onClick={() => ops.setActive(cur.id)}><Star size={13} aria-hidden="true" /> Đặt làm mặc định</button>}
                <button type="button" className="btn !px-2" onClick={() => askRename(cur)} aria-label={`Đổi tên nhóm ${cur.name}`}><Pencil size={14} aria-hidden="true" /></button>
                <button type="button" className="btn !px-2" onClick={() => setDlg({ kind: "del", g: cur })} aria-label={`Xoá nhóm ${cur.name}`}><Trash2 size={14} aria-hidden="true" /></button>
              </>}>
              <GroupTable key={cur.id} group={cur} />
            </Panel>
          )}
        </div>
      )}

      {dlg?.kind === "name" && <NameDialog state={dlg} onClose={() => setDlg(null)} />}
      <Dialog open={dlg?.kind === "del"} onClose={() => setDlg(null)} title="Xoá nhóm?"
        footer={<><button type="button" className="btn" data-autofocus onClick={() => setDlg(null)}>Giữ lại</button>
          <button type="button" className="btn !bg-[var(--down)] !text-white !border-transparent font-semibold" onClick={() => { ops.remove(dlg.g.id); setSel(null); setDlg(null); }}>Xoá nhóm</button></>}>
        <p className="m-0 p-3 text-[13px]">Nhóm <b>{dlg?.g?.name}</b> ({dlg?.g?.symbols.length} mã) sẽ bị xoá khỏi tài khoản của bạn.</p>
      </Dialog>
    </>
  );
}
