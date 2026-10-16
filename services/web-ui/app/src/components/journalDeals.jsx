// Nhật ký: bảng lệnh (sắp xếp/phân trang phía server), chi tiết + ghi chú, kỷ luật, MAE/MFE, review tuần.
// Đường GHI duy nhất: ghi chú/tag (PUT/DELETE /journal/{acc}/notes/{deal|week|day}/{ref}). Không có thao tác đặt/sửa/đóng lệnh.
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, ChevronDown, ChevronRight as ChevronR, Flag, Star, X } from "lucide-react";
import { Async, Chip, Panel, Seg, Skeleton, Stat, cn } from "./ui";
import { DataTable } from "./table";
import { Dialog } from "./dialog";
import { EChart, css } from "./charts";
import { apiWrite } from "../lib/api";
import { useJnDeals, useJnDiscipline, useJnExcursions, useJnNotes, useJnReview } from "../lib/queries";
import { dateTime, dur, price, signCls, vnDayKey } from "../lib/format";
import { RULE_LABEL, SESSION, SIDE, fN, fP, fPF, fR, fS, fWR, ruleLabel } from "./journal";

export const invalidateJournal = (qc) => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("journal-") });
const errText = (e) => e?.message || "Không lưu được.";

// ---------- trình sửa ghi chú / tag / rating ----------
const TAG_RE = /^[a-z0-9 _:.-]{1,32}$/;
export function NoteEditor({ acc, kind, refId, initial, tagHints = [], onSaved, placeholder, rows = 4 }) {
  const qc = useQueryClient();
  const [tags, setTags] = useState(initial?.tags || []);
  const [note, setNote] = useState(initial?.note || "");
  const [rating, setRating] = useState(initial?.rating ?? null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [tagErr, setTagErr] = useState("");
  const noteRef = useRef(null);
  useEffect(() => { setTags(initial?.tags || []); setNote(initial?.note || ""); setRating(initial?.rating ?? null); setMsg(null); }, [refId, initial?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  const addTag = (raw) => {
    const t = raw.trim().toLowerCase().replace(/,+$/, "");
    if (!t) return;
    if (!TAG_RE.test(t)) { setTagErr("Tag chỉ gồm a-z, 0-9, khoảng trắng và _ : . - (tối đa 32 ký tự)."); return; }
    if (tags.length >= 12) { setTagErr("Tối đa 12 tag."); return; }
    setTagErr("");
    if (!tags.includes(t)) setTags([...tags, t]);
    setDraft("");
  };
  const path = `/journal/${encodeURIComponent(acc)}/notes/${kind}/${encodeURIComponent(refId)}`;
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const pending = draft.trim().toLowerCase();
      const finalTags = pending && TAG_RE.test(pending) && !tags.includes(pending) && tags.length < 12 ? [...tags, pending] : tags;
      await apiWrite("PUT", path, { tags: finalTags, note, rating });
      setDraft(""); setTags(finalTags);
      await invalidateJournal(qc);
      setMsg({ ok: true, t: "Đã lưu." }); noteRef.current?.focus(); onSaved?.();
    } catch (e) { setMsg({ ok: false, t: errText(e) }); } finally { setBusy(false); }
  };
  const del = async () => {
    setBusy(true); setMsg(null);
    try {
      await apiWrite("DELETE", path);
      setTags([]); setNote(""); setRating(null);
      await invalidateJournal(qc);
      setMsg({ ok: true, t: "Đã xoá ghi chú." }); noteRef.current?.focus(); onSaved?.();
    } catch (e) { setMsg({ ok: false, t: errText(e) }); } finally { setBusy(false); }
  };
  const lid = `tg-${kind}-${refId}`;
  const sugg = tagHints.filter((t) => !tags.includes(t)).slice(0, 12);
  return (
    <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); save(); }}>
      <div>
        <label className="text-[11.5px] text-muted block mb-1" htmlFor={`${lid}-in`}>Tag (Enter để thêm)</label>
        <div className="flex flex-wrap gap-1 mb-1">
          {tags.map((t) => (
            <span key={t} className="chip accent">{t}<button type="button" className="ml-1 bg-transparent border-0 p-0 cursor-pointer text-inherit" aria-label={`Bỏ tag ${t}`} onClick={() => setTags(tags.filter((x) => x !== t))}><X size={11} aria-hidden="true" /></button></span>
          ))}
        </div>
        <input id={`${lid}-in`} className="field w-full" value={draft} maxLength={32} placeholder="vd: fomo, setup-a, ky-luat" list={`${lid}-l`} aria-describedby={tagErr ? `${lid}-e` : undefined}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addTag(draft); } else if (e.key === "Backspace" && !draft && tags.length) setTags(tags.slice(0, -1)); }} />
        <datalist id={`${lid}-l`}>{tagHints.map((t) => <option key={t} value={t} />)}</datalist>
        {tagErr && <div id={`${lid}-e`} role="alert" className="text-[11.5px] text-down mt-1">{tagErr}</div>}
        {sugg.length > 0 && <div className="flex flex-wrap gap-1 mt-1" aria-label="Gợi ý tag">{sugg.map((t) => <button key={t} type="button" className="chip cursor-pointer bg-transparent" onClick={() => addTag(t)}>+ {t}</button>)}</div>}
      </div>
      <div>
        <label className="text-[11.5px] text-muted block mb-1" htmlFor={`${lid}-n`}>Ghi chú ({note.length}/4000)</label>
        <textarea ref={noteRef} id={`${lid}-n`} className="field w-full !h-auto py-2 leading-relaxed" rows={rows} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} placeholder={placeholder || "Lý do vào lệnh, cảm xúc, bài học…"} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div role="radiogroup" aria-label="Đánh giá 1 đến 5 sao" className="flex items-center gap-[2px]">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} sao`} title={`${n} sao (bấm lại để bỏ)`} className="bg-transparent border-0 p-[3px] cursor-pointer" onClick={() => setRating(rating === n ? null : n)}>
              <Star size={17} aria-hidden="true" fill={rating != null && n <= rating ? "var(--accent)" : "none"} stroke={rating != null && n <= rating ? "var(--accent)" : "var(--faint)"} />
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {initial && <button type="button" className="btn" onClick={del} disabled={busy}>Xoá ghi chú</button>}
          <button type="submit" className="btn !bg-[var(--accent)] !text-[var(--accent-fg)] !border-transparent" disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </div>
      </div>
      {msg && <div role={msg.ok ? "status" : "alert"} className={cn("text-[12px]", msg.ok ? "up" : "down")}>{msg.t}</div>}
    </form>
  );
}

// ---------- chi tiết lệnh ----------
function Field({ k, v, cls }) {
  return <div className="min-w-0"><div className="text-[11px] text-muted">{k}</div><div className={cn("num text-[13px] break-words", cls)}>{v ?? "—"}</div></div>;
}
export function DealDialog({ acc, deal, onClose, tagHints, cur }) {
  const notes = useJnNotes(acc, "deal");
  const found = deal ? (notes.data?.items || []).find((n) => String(n.ref) === String(deal.ticket)) : null;
  const initial = deal?.note || found || null;
  if (!deal) return null;
  const sym = deal.symbol;
  const partial = deal.price_open === undefined;
  return (
    <Dialog open onClose={onClose} variant="drawer" title={`Lệnh #${deal.ticket} · ${sym || ""} ${SIDE[deal.side] || ""}`}>
      <div className="p-3 grid gap-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Field k="Net" v={`${fS(deal.net)}${cur ? " " + cur : ""}`} cls={signCls(deal.net)} />
          <Field k="R" v={deal.r == null ? "—" : fR(deal.r)} />
          <Field k="Thời gian giữ" v={deal.hold_s != null ? dur(deal.hold_s) : "—"} />
          <Field k="Vào" v={dateTime(deal.time_open)} />
          <Field k="Ra" v={deal.time_close ? dateTime(deal.time_close) : "—"} />
          <Field k="Khối lượng" v={deal.volume != null ? fN(deal.volume, 2) : "—"} />
          {!partial && <>
            <Field k="Giá vào" v={price(sym, deal.price_open)} /><Field k="Giá ra" v={price(sym, deal.price_close)} /><Field k="Lý do đóng" v={deal.reason} />
            <Field k="SL" v={deal.sl ? price(sym, deal.sl) : "—"} /><Field k="TP" v={deal.tp ? price(sym, deal.tp) : "—"} /><Field k="EA / magic" v={deal.group ?? deal.magic} />
            <Field k="Profit" v={fS(deal.profit)} /><Field k="Swap" v={fS(deal.swap)} /><Field k="Commission" v={fS(deal.commission)} />
          </>}
        </div>
        {partial && <div className="text-[12px] text-faint">Hiển thị rút gọn (lệnh này lấy từ danh sách kỷ luật). Mở từ bảng lệnh để xem đầy đủ giá/SL/TP.</div>}
        {deal.comment && <div className="text-[12.5px] text-muted">Comment: {deal.comment}</div>}
        {deal.flags?.length > 0 && (
          <div>
            <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold flex items-center gap-1"><Flag size={12} aria-hidden="true" /> Vi phạm kỷ luật</h3>
            <div className="flex flex-wrap gap-1">
              {deal.flags.map((f, i) => { const id = typeof f === "string" ? f : f.rule; return <Chip key={i} tone="down" title={ruleLabel(id)}>{ruleLabel(id)}</Chip>; })}
            </div>
          </div>
        )}
        <section aria-label="Ghi chú lệnh">
          <h3 className="m-0 mb-2 text-[12px] text-muted font-semibold">Ghi chú &amp; tag của tôi</h3>
          {notes.isPending && !deal.note ? <Skeleton rows={3} /> : <NoteEditor acc={acc} kind="deal" refId={deal.ticket} initial={initial} tagHints={tagHints} />}
          <p className="text-[11.5px] text-faint mt-2 mb-0">Chỉ lưu ghi chú; hệ thống không đặt, sửa hay đóng lệnh.</p>
        </section>
      </div>
    </Dialog>
  );
}

// ---------- bảng lệnh ----------
const SORTABLE = new Set(["time_close", "time_open", "net", "volume", "symbol", "hold_s", "r"]);
const PAGE = 50;
export function DealsPanel({ acc, filters, day, onClearDay, onOpen, tagHints, cur }) {
  const [sorting, setSorting] = useState([{ id: "time_close", desc: true }]);
  const [offset, setOffset] = useState(0);
  const [outcome, setOutcome] = useState("");
  const [tag, setTag] = useState("");
  const [flagged, setFlagged] = useState(false);
  const f = useMemo(() => {
    const o = { ...filters, outcome: outcome || undefined, tag: tag || undefined, flagged: flagged ? "true" : undefined,
      sort: sorting[0]?.id || "time_close", order: sorting[0]?.desc === false ? "asc" : "desc", limit: PAGE, offset };
    if (day) { o.from = day; o.to = day; }
    return o;
  }, [filters, outcome, tag, flagged, sorting, offset, day]);
  useEffect(() => { setOffset(0); }, [filters, day, outcome, tag, flagged]);
  const q = useJnDeals(acc, f);
  const data = q.data?.items || [];
  const total = q.data?.total ?? 0;
  const columns = useMemo(() => [
    { id: "ticket", header: "Ticket", accessorKey: "ticket", enableSorting: false, cell: (c) => <button type="button" className="num underline decoration-dotted bg-transparent border-0 p-0 cursor-pointer text-inherit" onClick={() => onOpen(c.row.original)} aria-label={`Mở chi tiết lệnh ${c.getValue()}`}>{c.getValue()}</button> },
    { id: "time_open", header: "Vào", accessorKey: "time_open", cell: (c) => <span className="num text-[12px] whitespace-nowrap">{dateTime(c.getValue())}</span> },
    { id: "time_close", header: "Ra", accessorKey: "time_close", cell: (c) => <span className="num text-[12px] whitespace-nowrap">{dateTime(c.getValue())}</span> },
    { id: "symbol", header: "Symbol", accessorKey: "symbol", cell: (c) => <b>{c.getValue()}</b> },
    { id: "side", header: "Hướng", accessorKey: "side", enableSorting: false, cell: (c) => <Chip tone={c.getValue() === "buy" ? "up" : "down"}>{SIDE[c.getValue()] || c.getValue()}</Chip> },
    { id: "volume", header: "KL", accessorKey: "volume", meta: { align: "r" }, cell: (c) => <span className="num">{fN(c.getValue(), 2)}</span> },
    { id: "px", header: "Giá vào → ra", enableSorting: false, meta: { align: "r" }, cell: (c) => { const d = c.row.original; return <span className="num whitespace-nowrap text-[12px]">{price(d.symbol, d.price_open)} → {price(d.symbol, d.price_close)}</span>; } },
    { id: "sltp", header: "SL / TP", enableSorting: false, meta: { align: "r" }, cell: (c) => { const d = c.row.original; return <span className="num whitespace-nowrap text-[12px] text-muted">{d.sl ? price(d.symbol, d.sl) : "—"} / {d.tp ? price(d.symbol, d.tp) : "—"}</span>; } },
    { id: "hold_s", header: "Giữ", accessorKey: "hold_s", meta: { align: "r" }, cell: (c) => <span className="num whitespace-nowrap">{dur(c.getValue())}</span> },
    { id: "net", header: "Net", accessorKey: "net", meta: { align: "r" }, cell: (c) => <b className={cn("num", signCls(c.getValue()))}>{fS(c.getValue())}</b> },
    { id: "r", header: "R", accessorKey: "r", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : fR(c.getValue())}</span> },
    { id: "group", header: "EA", accessorKey: "group", enableSorting: false, cell: (c) => <span className="text-muted text-[12px]">{c.getValue() === "manual" ? "Thủ công" : c.getValue() || "—"}</span> },
    { id: "reason", header: "Lý do đóng", accessorKey: "reason", enableSorting: false, cell: (c) => <span className="text-muted text-[12px]">{c.getValue() || "—"}</span> },
    { id: "note", header: "Tag / ghi chú", enableSorting: false, cell: (c) => { const n = c.row.original.note; return n ? <span className="flex flex-wrap gap-1 max-w-[220px]">{(n.tags || []).map((t) => <Chip key={t} tone="accent">{t}</Chip>)}{n.note && <span className="text-[11.5px] text-muted truncate max-w-[200px]" title={n.note}>{n.note}</span>}</span> : <span className="text-faint">—</span>; } },
    { id: "flags", header: "Kỷ luật", enableSorting: false, cell: (c) => { const fl = c.row.original.flags || []; return fl.length ? <span className="flex flex-wrap gap-1 max-w-[240px]">{fl.map((x) => <Chip key={x} tone="down" title={ruleLabel(x)}>{ruleLabel(x)}</Chip>)}</span> : <span className="text-faint">—</span>; } },
  ], [onOpen]);
  const table = useReactTable({
    data, columns, state: { sorting }, manualSorting: true, enableSortingRemoval: false, getRowId: (r) => r.ticket,
    onSortingChange: (u) => setSorting((p) => { const n = typeof u === "function" ? u(p) : u; return n.length ? n : p; }),
    getCoreRowModel: getCoreRowModel(),
  });
  const from = total ? offset + 1 : 0;
  const to = Math.min(total, offset + PAGE);
  return (
    <Panel title="Danh sách lệnh đã đóng" className="min-w-0"
      right={<span className="text-[11.5px] text-faint num" aria-live="polite">{from}–{to} / {total}</span>}>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Seg value={outcome} onChange={setOutcome} label="Kết quả" options={[{ value: "", label: "Tất cả" }, { value: "win", label: "Thắng" }, { value: "loss", label: "Thua" }, { value: "be", label: "Hoà" }]} />
        <label className="flex items-center gap-1 text-[12px] text-muted">Tag
          <select className="field" value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Lọc theo tag">
            <option value="">Tất cả</option>{(q.data?.tags || []).map((t) => <option key={t.tag} value={t.tag}>{t.tag} ({t.n})</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1 text-[12px] cursor-pointer"><input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} /> Chỉ lệnh vi phạm kỷ luật</label>
        {day && <button className="chip accent cursor-pointer" onClick={onClearDay} aria-label={`Bỏ lọc ngày ${day}`}>Ngày {day} <X size={11} aria-hidden="true" /></button>}
        {q.data?.totals && <span className="ml-auto text-[12px] text-muted">Tổng net bộ lọc <b className={cn("num", signCls(q.data.totals.net))}>{fS(q.data.totals.net)}{cur ? " " + cur : ""}</b></span>}
      </div>
      {q.isPending ? <Skeleton rows={6} /> : q.isError ? (
        <div role="alert" className="text-down flex items-center gap-2">{q.error?.message}<button className="btn" onClick={() => q.refetch()}>Thử lại</button></div>
      ) : (
        <div className={cn("scroll-x", q.isPlaceholderData && "opacity-60")}>
          <table className="tbl" style={{ minWidth: 1280 }}>
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => {
                    const id = h.column.id, can = SORTABLE.has(id), s = h.column.getIsSorted();
                    return (
                      <th key={h.id} className={h.column.columnDef.meta?.align === "r" ? "r" : ""} aria-sort={s === "asc" ? "ascending" : s === "desc" ? "descending" : "none"}>
                        {can ? <button type="button" onClick={h.column.getToggleSortingHandler()} title="Sắp xếp (phía máy chủ)">{flexRender(h.column.columnDef.header, h.getContext())}{s === "asc" ? <ArrowUp size={12} /> : s === "desc" ? <ArrowDown size={12} /> : <ChevronsUpDown size={12} className="opacity-40" />}</button> : flexRender(h.column.columnDef.header, h.getContext())}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((r) => (
                <tr key={r.id} className="cursor-pointer" onClick={(e) => { if (!e.target.closest("button")) onOpen(r.original); }}>
                  {r.getVisibleCells().map((c) => <td key={c.id} className={c.column.columnDef.meta?.align === "r" ? "r" : ""}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
                </tr>
              ))}
              {!data.length && <tr><td colSpan={columns.length} className="text-muted">Không có lệnh nào khớp bộ lọc.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex items-center gap-2 pt-3">
        <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} aria-label="Trang trước"><ChevronLeft size={14} aria-hidden="true" /> Trước</button>
        <span className="text-[12px] text-muted num">Trang {Math.floor(offset / PAGE) + 1} / {Math.max(1, Math.ceil(total / PAGE))}</span>
        <button className="btn" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)} aria-label="Trang sau">Sau <ChevronRight size={14} aria-hidden="true" /></button>
      </div>
    </Panel>
  );
}

// ---------- kỷ luật ----------
function Gauge({ score }) {
  const v = score == null ? 0 : Math.max(0, Math.min(100, score));
  const col = score == null ? "var(--faint)" : v >= 80 ? "var(--up)" : v >= 60 ? "var(--accent)" : "var(--down)";
  const R = 52, C = 2 * Math.PI * R;
  return (
    <div className="relative w-[132px] h-[132px] shrink-0" role="img" aria-label={score == null ? "Chưa có điểm kỷ luật" : `Điểm kỷ luật ${v.toFixed(0)} trên 100`}>
      <svg viewBox="0 0 132 132" width="132" height="132" aria-hidden="true">
        <circle cx="66" cy="66" r={R} fill="none" stroke="var(--line2)" strokeWidth="10" />
        <circle cx="66" cy="66" r={R} fill="none" stroke={col} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(v / 100) * C} ${C}`} transform="rotate(-90 66 66)" />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center"><div><div className="num text-[30px] leading-none" style={{ color: col }}>{score == null ? "—" : v.toFixed(0)}</div><div className="text-[10.5px] text-faint">/ 100</div></div></div>
    </div>
  );
}
const PARAMS = [
  { k: "revenge_gap_min", l: "Vào lại sau thua (phút)", min: 1, max: 1440, step: 1 },
  { k: "size_up_ratio", l: "Tăng KL (x lệnh thua trước)", min: 1, max: 10, step: 0.1 },
  { k: "max_trades_day", l: "Tối đa lệnh / ngày", min: 1, max: 200, step: 1 },
  { k: "max_trades_hour", l: "Tối đa lệnh / giờ", min: 1, max: 100, step: 1 },
  { k: "daily_loss_limit_pct", l: "Hạn mức lỗ ngày (%)", min: 0.1, max: 100, step: 0.1 },
];
export function DisciplinePanel({ acc, filters, onOpen, params, setParams, cur }) {
  const [draft, setDraft] = useState(params);
  const f = useMemo(() => ({ from: filters.from, to: filters.to, symbol: filters.symbol, group: filters.group, ...params }), [filters, params]);
  const q = useJnDiscipline(acc, f);
  useEffect(() => { setDraft(params); }, [params]);
  const apply = (e) => { e.preventDefault(); const o = {}; for (const p of PARAMS) { const n = Number(draft[p.k]); if (Number.isFinite(n) && n >= p.min && n <= p.max) o[p.k] = n; } setParams(o); };
  return (
    <Panel title="Kỷ luật giao dịch" right={<span className="text-[11.5px] text-faint">phát hiện SAU khi lệnh xảy ra, không chặn lệnh</span>}>
      <Async q={q} rows={5} isEmpty={(d) => !d} empty="Chưa có dữ liệu kỷ luật.">
        {(d) => (
          <div className="grid gap-4">
            <div className="flex flex-wrap items-center gap-5">
              <Gauge score={d.score} />
              <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                <Stat label="Lệnh vi phạm" value={`${d.n_flagged} / ${d.n_trades}`} />
                <Stat label="P/L lệnh vi phạm" value={<span className={signCls(d.net_flagged)}>{fS(d.net_flagged)}</span>} sub={cur} />
                <Stat label="P/L lệnh sạch" value={<span className={signCls(d.net_clean)}>{fS(d.net_clean)}</span>} sub={cur} />
                <Stat label="Chênh lệch" value={<span className={signCls((d.net_clean || 0) - (d.net_flagged || 0))}>{fS((d.net_clean || 0) - (d.net_flagged || 0))}</span>} sub="sạch trừ vi phạm" />
              </div>
              <Compare a={d.net_clean} b={d.net_flagged} />
            </div>
            {d.note && <div className="text-[12px] text-faint">{d.note}</div>}
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold">Quy tắc</h3>
                <table className="tbl" style={{ minWidth: 320 }}>
                  <thead><tr><th>Quy tắc</th><th className="r">Lệnh</th><th className="r">P/L</th></tr></thead>
                  <tbody>{(d.rules || []).map((r) => <tr key={r.rule}><td title={r.rule}>{r.label || ruleLabel(r.rule)}</td><td className="r num">{r.count}</td><td className={cn("r num", signCls(r.net))}>{r.count ? fS(r.net) : "—"}</td></tr>)}</tbody>
                </table>
                {d.day_breaches?.length > 0 && (
                  <div className="mt-3">
                    <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold">Ngày vượt hạn mức lỗ ({d.params?.daily_loss_limit_pct ?? params.daily_loss_limit_pct}%)</h3>
                    <ul className="m-0 p-0 list-none text-[12.5px] grid gap-1">{d.day_breaches.map((b) => <li key={b.date} className="flex gap-3"><span className="num">{b.date}</span><span className="num down">{fS(b.net)}</span>{b.limit != null && <span className="text-faint num">hạn mức {fN(b.limit)}</span>}</li>)}</ul>
                  </div>
                )}
              </div>
              <div>
                <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold">Lệnh bị gắn cờ ({d.flagged?.length || 0})</h3>
                {!d.flagged?.length ? <div className="text-muted text-[12.5px]">Không có lệnh nào vi phạm trong khoảng này.</div> : (
                  <ul className="m-0 p-0 list-none grid gap-1 max-h-[300px] overflow-y-auto" aria-label="Lệnh vi phạm kỷ luật">
                    {d.flagged.map((x) => (
                      <li key={x.ticket}>
                        <button type="button" className="w-full text-left bg-transparent border border-line rounded-md px-2 py-1.5 cursor-pointer hover:bg-panel2 text-[12.5px] text-inherit" onClick={() => onOpen(x)}>
                          <span className="flex items-center gap-2"><b>{x.symbol}</b><Chip tone={x.side === "buy" ? "up" : "down"}>{SIDE[x.side] || x.side}</Chip><span className="num text-faint text-[11.5px]">#{x.ticket} · {dateTime(x.time_open)}</span><b className={cn("num ml-auto", signCls(x.net))}>{fS(x.net)}</b></span>
                          <span className="flex flex-wrap gap-1 mt-1">{(x.flags || []).map((fl, i) => <Chip key={i} tone="down">{ruleLabel(fl.rule)}</Chip>)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <form onSubmit={apply} className="border-t border-line pt-3">
              <h3 className="m-0 mb-2 text-[12px] text-muted font-semibold">Ngưỡng kiểm tra</h3>
              <div className="flex flex-wrap items-end gap-3">
                {PARAMS.map((p) => (
                  <label key={p.k} className="text-[11.5px] text-muted grid gap-1">{p.l}
                    <input className="field w-[120px] num" type="number" inputMode="decimal" min={p.min} max={p.max} step={p.step} value={draft[p.k] ?? d.params?.[p.k] ?? ""} onChange={(e) => setDraft({ ...draft, [p.k]: e.target.value })} />
                  </label>
                ))}
                <button className="btn" type="submit">Áp dụng</button>
                <button className="btn" type="button" onClick={() => setParams({})}>Mặc định</button>
              </div>
            </form>
          </div>
        )}
      </Async>
    </Panel>
  );
}
function Compare({ a, b }) {
  const mx = Math.max(1, Math.abs(a || 0), Math.abs(b || 0));
  const bar = (label, v) => (
    <div className="grid grid-cols-[4.5rem_1fr_4.5rem] items-center gap-2 text-[12px]">
      <span className="text-muted">{label}</span>
      <span className="h-3 rounded bg-panel2 overflow-hidden"><span className="block h-full" style={{ width: `${(Math.abs(v || 0) / mx) * 100}%`, background: (v || 0) >= 0 ? "var(--up)" : "var(--down)", opacity: 0.85 }} /></span>
      <span className={cn("num r", signCls(v))}>{fS(v, 0)}</span>
    </div>
  );
  return <div className="grid gap-1 min-w-[240px] flex-1 max-w-[360px]" role="img" aria-label={`So sánh P/L lệnh sạch ${fS(a)} và lệnh vi phạm ${fS(b)}`}>{bar("Lệnh sạch", a)}{bar("Vi phạm", b)}</div>;
}

// ---------- MAE / MFE ----------
export function ExcursionPanel({ acc, filters }) {
  const [open, setOpen] = useState(false);
  const q = useJnExcursions(acc, { from: filters.from, to: filters.to, symbol: filters.symbol, limit: 100 }, open);
  const d = q.data;
  const items = d?.items || [];
  const build = () => ({
    animation: false, backgroundColor: "transparent", grid: { left: 52, right: 14, top: 14, bottom: 40 },
    tooltip: { trigger: "item", backgroundColor: css("--panel2"), borderColor: css("--line2"), textStyle: { color: css("--fg"), fontSize: 12 },
      formatter: (p) => { const t = items[p.dataIndex]; return `#${t.ticket} ${t.symbol} ${SIDE[t.side] || ""}<br/>MAE ${fP(t.mae_pct, 2)} · MFE ${fP(t.mfe_pct, 2)}<br/>Net <b>${fS(t.net)}</b>${t.capture != null ? ` · capture ${fP(t.capture * 100, 0)}` : ""}`; } },
    xAxis: { type: "value", name: "MAE % (bất lợi tối đa)", nameLocation: "middle", nameGap: 24, nameTextStyle: { color: css("--muted"), fontSize: 11 }, axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } },
    yAxis: { type: "value", name: "MFE %", nameTextStyle: { color: css("--muted"), fontSize: 11 }, axisLine: { lineStyle: { color: css("--line2") } }, axisLabel: { color: css("--muted"), fontSize: 11 }, splitLine: { lineStyle: { color: css("--line") } } },
    series: [{ type: "scatter", symbolSize: 9, data: items.map((t) => ({ value: [Math.abs(t.mae_pct ?? 0), t.mfe_pct ?? 0], itemStyle: { color: t.net >= 0 ? css("--up") : css("--down"), opacity: 0.8 } })) }],
  });
  const cols = useMemo(() => [
    { id: "ticket", header: "Ticket", accessorKey: "ticket", cell: (c) => <span className="num">{c.getValue()}</span> },
    { id: "symbol", header: "Symbol", accessorKey: "symbol" },
    { id: "mae", header: "MAE %", accessorKey: "mae_pct", meta: { align: "r" }, cell: (c) => <span className="num">{fP(c.getValue(), 2)}</span> },
    { id: "mfe", header: "MFE %", accessorKey: "mfe_pct", meta: { align: "r" }, cell: (c) => <span className="num">{fP(c.getValue(), 2)}</span> },
    { id: "cap", header: "Capture", accessorKey: "capture", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : fP(c.getValue() * 100, 0)}</span> },
    { id: "left", header: "Bỏ lại", accessorKey: "left_on_table_pct", meta: { align: "r" }, cell: (c) => <span className="num">{c.getValue() == null ? "—" : fP(c.getValue(), 2)}</span> },
    { id: "net", header: "Net", accessorKey: "net", meta: { align: "r" }, cell: (c) => <span className={cn("num", signCls(c.getValue()))}>{fS(c.getValue())}</span> },
  ], []);
  return (
    <section className="panel" aria-labelledby="jn-exc-h">
      <div className="panel-h">
        <button type="button" className="bg-transparent border-0 p-0 flex items-center gap-2 cursor-pointer text-inherit" aria-expanded={open} aria-controls="jn-exc-b" onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronR size={14} aria-hidden="true" />}<h2 id="jn-exc-h">MAE / MFE (xấp xỉ từ nến)</h2>
        </button>
        <span className="ml-auto text-[11.5px] text-faint">tải khi mở</span>
      </div>
      {open && (
        <div id="jn-exc-b" className="panel-b grid gap-3">
          <Async q={q} rows={4} isEmpty={(x) => !x?.items?.length} empty="Chưa tính được MAE/MFE (thiếu nến phủ khoảng giữ lệnh).">
            {() => (
              <>
                <div className="flex flex-wrap gap-x-6 gap-y-2">
                  <Stat label="Lệnh tính được" value={`${d.covered ?? d.summary?.n ?? 0} / ${d.requested ?? "—"}`} />
                  <Stat label="MAE TB" value={fP(d.summary?.avg_mae_pct, 2)} /><Stat label="MFE TB" value={fP(d.summary?.avg_mfe_pct, 2)} />
                  <Stat label="Capture TB" value={d.summary?.avg_capture == null ? "—" : fP(d.summary.avg_capture * 100, 0)} sub="phần MFE thực sự chốt" />
                  <Stat label="MAE lệnh thắng" value={fP(d.summary?.winners_avg_mae_pct, 2)} sub="gợi ý độ rộng SL" />
                  <Stat label="MFE lệnh thua" value={fP(d.summary?.losers_avg_mfe_pct, 2)} sub="lệnh thua từng có lãi" />
                  <Stat label="Spread TB" value={d.summary?.avg_spread_bps == null ? "—" : `${fN(d.summary.avg_spread_bps, 1)} bps`} />
                </div>
                <div className="flex flex-col"><EChart build={build} deps={[d]} height={240} label="Scatter MAE so với MFE từng lệnh" /></div>
                <DataTable data={items.slice(0, 50)} columns={cols} minWidth={520} initialSort={[{ id: "mae", desc: true }]} />
              </>
            )}
          </Async>
          <div className="text-[12px] text-faint" role="note">{d?.note ? `${d.note} ` : ""}Lưu ý: MAE/MFE chỉ là xấp xỉ từ dữ liệu nến, không phải tick; với tài khoản mô phỏng (giá không khớp thị trường) giá trị này không có ý nghĩa.</div>
        </div>
      )}
    </section>
  );
}

// ---------- review tuần ----------
const DAY = 86400000;
const parseKey = (k) => Date.UTC(+k.slice(0, 4), +k.slice(5, 7) - 1, +k.slice(8, 10));
const monBased = (ms) => (new Date(ms).getUTCDay() + 6) % 7;
export function isoWeekOf(ms) {
  const th = ms - monBased(ms) * DAY + 3 * DAY;
  const y = new Date(th).getUTCFullYear();
  const jan4 = Date.UTC(y, 0, 4);
  const w = 1 + Math.round(((th - jan4) / DAY - 3 + monBased(jan4)) / 7);
  return `${y}-W${String(w).padStart(2, "0")}`;
}
export const curWeek = () => isoWeekOf(parseKey(vnDayKey(new Date())));
function weekMonday(label) {
  const [y, w] = label.split("-W").map(Number);
  const jan4 = Date.UTC(y, 0, 4);
  return jan4 - monBased(jan4) * DAY + (w - 1) * 7 * DAY;
}
export const shiftWeek = (label, n) => isoWeekOf(weekMonday(label) + n * 7 * DAY);
const dk = (ms) => new Date(ms).toISOString().slice(0, 10);

function Delta({ v, fmt, goodUp = true }) {
  if (v == null || Number.isNaN(v)) return <span className="text-faint">so với tuần trước —</span>;
  const good = v === 0 ? null : goodUp ? v > 0 : v < 0;
  return <span className={cn("num text-[11.5px]", good == null ? "text-muted" : good ? "up" : "down")}>{v > 0 ? "▲" : v < 0 ? "▼" : "="} {fmt(v)} so với tuần trước</span>;
}
function DealList({ title, items, onOpen }) {
  return (
    <div>
      <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold">{title}</h3>
      {!items?.length ? <div className="text-muted text-[12.5px]">—</div> : (
        <ul className="m-0 p-0 list-none grid gap-1">
          {items.map((t) => (
            <li key={t.ticket}><button type="button" className="w-full flex items-center gap-2 text-left bg-transparent border border-line rounded-md px-2 py-1 cursor-pointer hover:bg-panel2 text-[12.5px] text-inherit" onClick={() => onOpen(t)}>
              <b>{t.symbol}</b><Chip tone={t.side === "buy" ? "up" : "down"}>{SIDE[t.side] || t.side}</Chip><span className="num text-faint text-[11.5px]">#{t.ticket}</span><b className={cn("num ml-auto", signCls(t.net))}>{fS(t.net)}</b>
            </button></li>
          ))}
        </ul>
      )}
    </div>
  );
}
export function ReviewPanel({ acc, onOpen, tagHints, cur }) {
  const now = useMemo(() => curWeek(), []);
  const [week, setWeek] = useState(now);
  const q = useJnReview(acc, week);
  const d = q.data;
  const start = weekMonday(week);
  const s = d?.summary, dl = d?.delta || {};
  const maxAbs = Math.max(1, ...(d?.days || []).map((x) => Math.abs(x.net)));
  return (
    <Panel title="Review hàng tuần" right={
      <div className="flex items-center gap-1">
        <button className="btn !px-2" onClick={() => setWeek(shiftWeek(week, -1))} aria-label="Tuần trước"><ChevronLeft size={15} aria-hidden="true" /></button>
        <span className="num text-[12.5px] px-1 min-w-[10.5rem] text-center" aria-live="polite">{week} · {dk(start).slice(5)} → {dk(start + 6 * DAY).slice(5)}</span>
        <button className="btn !px-2" onClick={() => setWeek(shiftWeek(week, 1))} disabled={week >= now} aria-label="Tuần sau"><ChevronRight size={15} aria-hidden="true" /></button>
        {week !== now && <button className="btn" onClick={() => setWeek(now)}>Tuần này</button>}
      </div>}>
      <Async q={q} rows={6} isEmpty={(x) => !x} empty="Không có dữ liệu cho tuần này.">
        {() => (
          <div className="grid gap-4">
            {s?.n === 0 && <div className="text-muted text-[12.5px]">Tuần này chưa có lệnh đã đóng. Dùng nút mũi tên để chọn tuần khác.</div>}
            <div className="grid gap-3 grid-cols-2 md:grid-cols-5">
              <div><Stat label="Net P/L" value={<span className={signCls(s?.net)}>{fS(s?.net)}</span>} sub={cur} big /><Delta v={dl.net} fmt={(v) => fS(v)} /></div>
              <div><Stat label="Số lệnh" value={s?.n ?? "—"} big /><Delta v={dl.n} fmt={(v) => fS(v, 0)} goodUp={true} /></div>
              <div><Stat label="Win rate" value={fWR(s?.win_rate)} big /><Delta v={dl.win_rate} fmt={(v) => `${(v * 100).toFixed(1)} đ.%`} /></div>
              <div><Stat label="Profit factor" value={fPF(s?.profit_factor)} big /><Delta v={dl.profit_factor} fmt={(v) => fS(v)} /></div>
              <div><Stat label="Expectancy" value={fS(s?.expectancy)} big /><Delta v={dl.expectancy} fmt={(v) => fS(v)} /></div>
            </div>
            {d?.insights?.length > 0 && (
              <ul className="m-0 pl-5 grid gap-1 text-[12.5px]" aria-label="Nhận xét tự động">{d.insights.map((x, i) => <li key={i}>{x}</li>)}</ul>
            )}
            <div className="grid grid-cols-7 gap-1" role="list" aria-label="P/L từng ngày trong tuần">
              {(d?.days || []).map((x) => (
                <div key={x.date} role="listitem" className="rounded-md border border-line p-1.5 text-center" style={{ background: x.n ? `color-mix(in srgb, ${x.net >= 0 ? "var(--up)" : "var(--down)"} ${Math.round(15 + 55 * Math.abs(x.net) / maxAbs)}%, var(--panel))` : undefined }}>
                  <div className="text-[10.5px] text-muted">{x.date.slice(5)}</div>
                  <div className={cn("num text-[12.5px]", x.n ? signCls(x.net) : "text-faint")}>{x.n ? fS(x.net, 0) : "—"}</div>
                  <div className="text-[10.5px] text-faint">{x.n} lệnh</div>
                </div>
              ))}
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <DealList title="Lệnh tốt nhất" items={d?.best} onOpen={onOpen} />
              <DealList title="Lệnh xấu nhất" items={d?.worst} onOpen={onOpen} />
              <div className="grid gap-3 content-start">
                <div>
                  <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold">Kỷ luật tuần</h3>
                  <div className="text-[12.5px]">Điểm <b className="num">{d?.discipline?.score == null ? "—" : Number(d.discipline.score).toFixed(0)}</b> · {d?.discipline?.n_flagged ?? 0} lệnh vi phạm (P/L <span className={signCls(d?.discipline?.net_flagged)}>{fS(d?.discipline?.net_flagged)}</span>)</div>
                  {(d?.discipline?.rules || []).filter((r) => r.count).map((r) => <div key={r.rule} className="text-[12px] text-muted">{r.label || ruleLabel(r.rule)}: {r.count}</div>)}
                </div>
                <div>
                  <h3 className="m-0 mb-1 text-[12px] text-muted font-semibold">Tag đã dùng</h3>
                  <div className="flex flex-wrap gap-1">{d?.tags?.length ? d.tags.map((t) => <Chip key={t.tag} tone="accent">{t.tag} · {t.n}</Chip>) : <span className="text-muted text-[12.5px]">—</span>}</div>
                </div>
              </div>
            </div>
            {d?.by_symbol?.length > 0 && (
              <div className="text-[12.5px] flex flex-wrap gap-x-4 gap-y-1"><span className="text-muted">Theo symbol:</span>{d.by_symbol.map((r) => <span key={r.key ?? r.symbol}><b>{r.key ?? r.symbol}</b> <span className={cn("num", signCls(r.net))}>{fS(r.net, 0)}</span> <span className="text-faint">({r.n})</span></span>)}</div>
            )}
            <section aria-label="Ghi chú review tuần" className="border-t border-line pt-3">
              <h3 className="m-0 mb-2 text-[12px] text-muted font-semibold">Ghi chú review {week} · việc cần làm tuần tới</h3>
              <NoteEditor key={week} acc={acc} kind="week" refId={week} initial={d?.review} tagHints={tagHints} rows={6}
                placeholder={"Tuần này làm tốt gì?\nSai ở đâu (xem lệnh xấu nhất, lệnh vi phạm)?\nTuần tới sẽ làm: 1) … 2) …"} />
            </section>
          </div>
        )}
      </Async>
    </Panel>
  );
}
