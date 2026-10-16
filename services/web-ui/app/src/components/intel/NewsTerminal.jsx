// Terminal tin tức: dòng tin thời gian thực (WebSocket) kiểu squawk, tìm toàn văn, lọc mã/chủ đề/mức quan trọng/cảm xúc, nhóm theo chủ đề,
// panel chi tiết + tin liên quan + mã liên quan, đã đọc/đã lưu, âm báo tin quan trọng. Không hiển thị tên nguồn.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bell, BellOff, Bookmark, ChevronDown, Layers, ListFilter, Mic, MicOff, Newspaper, RefreshCw, Rows3, Search, X } from "lucide-react";
import { Dialog } from "../dialog";
import { Panel, Seg, cn } from "../ui";
import { QState, VirtualList, useLocal } from "./bits";
import { NewsDetail, NewsRow, shortSym } from "./NewsParts";
import { useNewsTopics } from "../../lib/intel";
import { TOPIC_LABEL, markRead, matchesFilters, onLiveNews, toggleSaved, useNewsFeed, useNewsMarks } from "../../lib/intelNews";
import { useStream } from "../../lib/stream";
import { beep } from "../../ux/sound";

const HOURS = [{ value: "6", label: "6 giờ" }, { value: "24", label: "24 giờ" }, { value: "72", label: "3 ngày" }, { value: "168", label: "7 ngày" }, { value: "720", label: "30 ngày" }];
const DEFAULT_F = { topic: "", min_importance: 0, sentiment: "", lang: "", symbol: "", hours: 72 };
const ROW_H = { normal: 76, squawk: 36 };

function useDebounced(v, ms) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}
function useDesktop() {
  const get = () => typeof matchMedia === "function" && matchMedia("(min-width: 1024px)").matches;
  const [d, setD] = useState(get);
  useEffect(() => {
    if (typeof matchMedia !== "function") return undefined;
    const m = matchMedia("(min-width: 1024px)");
    const h = () => setD(m.matches);
    m.addEventListener("change", h);
    return () => m.removeEventListener("change", h);
  }, []);
  return d;
}
const say = (t) => { try { if ("speechSynthesis" in window) { const u = new SpeechSynthesisUtterance(t); u.lang = /[ạảãàáâấầẩẫậăắằẳẵặđêếềểễệôốồổỗộơớờởỡợưứừửữự]/i.test(t) ? "vi-VN" : "en-US"; u.rate = 1.05; speechSynthesis.speak(u); } } catch { /* trình duyệt không hỗ trợ */ } };

function FilterSide({ f, setF, topics, hours, onClear, unread, setUnread, activeCount }) {
  const set = (patch) => setF({ ...f, ...patch });
  const picked = new Set((f.topic || "").split(",").filter(Boolean));
  const toggleTopic = (id) => { const n = new Set(picked); if (n.has(id)) n.delete(id); else n.add(id); set({ topic: [...n].join(",") }); };
  const maxN = Math.max(1, ...(topics.data?.topics || []).map((t) => t.n));
  return (
    <div className="grid gap-3 content-start p-3 text-[12.5px]">
      <div className="flex items-center justify-between">
        <b className="text-[12.5px]">Bộ lọc</b>
        <button type="button" className="btn !h-7" onClick={onClear} disabled={!activeCount}>Xoá lọc{activeCount ? ` (${activeCount})` : ""}</button>
      </div>
      <div><div className="text-muted mb-1">Khoảng thời gian</div><Seg label="Khoảng thời gian" value={String(f.hours)} onChange={(v) => set({ hours: Number(v) })} options={HOURS} /></div>
      <div><div className="text-muted mb-1">Mức quan trọng</div>
        <Seg label="Mức quan trọng" value={String(f.min_importance)} onChange={(v) => set({ min_importance: Number(v) })} options={[{ value: "0", label: "Tất cả" }, { value: "2", label: "Chú ý+" }, { value: "3", label: "Quan trọng" }]} /></div>
      <div><div className="text-muted mb-1">Cảm xúc</div>
        <Seg label="Cảm xúc" value={f.sentiment || "all"} onChange={(v) => set({ sentiment: v === "all" ? "" : v })} options={[{ value: "all", label: "Tất cả" }, { value: "pos", label: "Tích cực" }, { value: "neu", label: "Trung tính" }, { value: "neg", label: "Tiêu cực" }]} /></div>
      <div><div className="text-muted mb-1">Ngôn ngữ</div>
        <Seg label="Ngôn ngữ" value={f.lang || "all"} onChange={(v) => set({ lang: v === "all" ? "" : v })} options={[{ value: "all", label: "Tất cả" }, { value: "vi", label: "Tiếng Việt" }, { value: "en", label: "English" }]} /></div>
      <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={unread} onChange={(e) => setUnread(e.target.checked)} style={{ accentColor: "var(--accent)" }} /> Chỉ tin chưa đọc</label>
      <div>
        <div className="text-muted mb-1">Chủ đề ({hours}h gần nhất)</div>
        {topics.isPending ? <div className="text-faint">Đang tải…</div> : !topics.data?.topics?.length ? <div className="text-faint">Chưa có chủ đề.</div> : (
          <ul className="m-0 p-0 list-none grid gap-[2px]">
            {topics.data.topics.map((t) => (
              <li key={t.id}>
                <label className="flex items-center gap-2 cursor-pointer py-[2px]">
                  <input type="checkbox" checked={picked.has(t.id)} onChange={() => toggleTopic(t.id)} style={{ accentColor: "var(--accent)" }} />
                  <span className="flex-1 min-w-0 truncate">{TOPIC_LABEL[t.id] || t.name}</span>
                  <span className={cn("num text-[11px]", t.sentiment > 0.1 ? "up" : t.sentiment < -0.1 ? "down" : "text-faint")} title={t.sentiment == null ? "" : `Cảm xúc TB ${t.sentiment.toFixed(2)}`}>{t.sentiment == null ? "" : t.sentiment > 0 ? "▲" : "▼"}</span>
                  <span className="num text-[11px] text-faint w-[28px] text-right">{t.n}</span>
                </label>
                <div className="in-bar !h-[3px] ml-6"><i style={{ left: 0, width: `${(t.n / maxN) * 100}%`, background: "var(--line2)" }} /></div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="text-muted mb-1">Mã được nhắc nhiều</div>
        <div className="flex flex-wrap gap-1">
          {(topics.data?.symbols || []).slice(0, 14).map((s) => (
            <button key={s.symbol} type="button" aria-pressed={f.symbol === s.symbol} className={cn("chip cursor-pointer bg-transparent", f.symbol === s.symbol && "accent")} onClick={() => set({ symbol: f.symbol === s.symbol ? "" : s.symbol })}>{s.label} <span className="num text-faint">{s.n}</span></button>
          ))}
          {f.symbol && !(topics.data?.symbols || []).some((s) => s.symbol === f.symbol) && <button type="button" className="chip accent cursor-pointer bg-transparent" onClick={() => set({ symbol: "" })}>{shortSym(f.symbol)} <X size={10} aria-hidden="true" /></button>}
        </div>
      </div>
    </div>
  );
}

function GroupedFeed({ items, marks, selUrl, onSelect, words }) {
  const [open, setOpen] = useState({});
  const groups = useMemo(() => {
    const m = new Map();
    for (const it of items) { const g = it.topics?.[0] || "_none"; if (!m.has(g)) m.set(g, []); m.get(g).push(it); }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [items]);
  return (
    <div className="flex-1 min-h-0 overflow-auto">
      {groups.map(([g, arr]) => {
        const sent = arr.filter((x) => x.sentiment != null);
        const avg = sent.length ? sent.reduce((a, b) => a + b.sentiment, 0) / sent.length : null;
        const all = open[g];
        const shown = all ? arr : arr.slice(0, 6);
        return (
          <section key={g} aria-label={TOPIC_LABEL[g] || "Khác"}>
            <div className="sticky top-0 z-[1] flex items-center gap-2 px-3 py-[5px] bg-panel2 border-b border-line text-[11.5px] font-semibold uppercase tracking-wide text-muted">
              <span className="flex-1">{TOPIC_LABEL[g] || "Chưa phân loại"}</span>
              {avg != null && <span className={cn("num normal-case", avg > 0.1 ? "up" : avg < -0.1 ? "down" : "")}>{avg > 0 ? "+" : ""}{avg.toFixed(2)}</span>}
              <span className="num normal-case">{arr.length}</span>
            </div>
            {shown.map((it) => (
              <div key={it.url} style={{ height: ROW_H.normal }}>
                <NewsRow it={it} selected={selUrl === it.url} read={marks.isRead(it.url)} saved={marks.isSaved(it.url)} density="normal" onSelect={onSelect} words={words} />
              </div>
            ))}
            {arr.length > 6 && <button type="button" className="w-full text-left text-[12px] px-3 py-[6px] bg-transparent border-0 border-b border-line text-accent cursor-pointer" onClick={() => setOpen({ ...open, [g]: !all })}>{all ? "Thu gọn" : `Xem thêm ${arr.length - 6} tin`} <ChevronDown size={12} className={cn("inline", all && "rotate-180")} aria-hidden="true" /></button>}
          </section>
        );
      })}
    </div>
  );
}

export default function NewsTerminalView() {
  const [f, setF] = useLocal("ts-news-f", DEFAULT_F);
  const flt = { ...DEFAULT_F, ...f };
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 350);
  const [view, setView] = useLocal("ts-news-view", "feed");
  const [density, setDensity] = useLocal("ts-news-dens", "normal");
  const [sound, setSound] = useLocal("ts-news-snd", false);
  const [speak, setSpeak] = useLocal("ts-news-spk", false);
  const [unread, setUnread] = useState(false);
  const [showF, setShowF] = useState(false);
  const [sel, setSel] = useState(null);
  const [pending, setPending] = useState(0);
  const desktop = useDesktop();
  const marks = useNewsMarks();
  const st = useStream();
  const scrollRef = useRef(null);
  const words = useMemo(() => q.split(/\s+/).filter(Boolean), [q]);

  const filters = useMemo(() => ({ q: q || undefined, symbol: flt.symbol || undefined, topic: flt.topic || undefined, min_importance: flt.min_importance || undefined, sentiment: flt.sentiment || undefined, lang: flt.lang || undefined, hours: flt.hours }),
    [q, flt.symbol, flt.topic, flt.min_importance, flt.sentiment, flt.lang, flt.hours]);
  const feed = useNewsFeed(filters);
  const topics = useNewsTopics(Math.min(720, flt.hours));
  const activeCount = (flt.topic ? 1 : 0) + (flt.min_importance ? 1 : 0) + (flt.sentiment ? 1 : 0) + (flt.lang ? 1 : 0) + (flt.symbol ? 1 : 0) + (flt.hours !== 72 ? 1 : 0) + (unread ? 1 : 0);
  const list = useMemo(() => {
    if (view === "saved") return marks.saved.map((s) => ({ ...s, id: s.k, live: false })).filter((it) => !q || `${it.title} ${it.summary || ""}`.toLowerCase().includes(q.toLowerCase()));
    return unread ? feed.items.filter((it) => !marks.isRead(it.url)) : feed.items;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, feed.items, unread, marks.saved, marks.readCount, q]);

  // âm báo / đọc to tin quan trọng đến theo thời gian thực (chỉ khi khớp bộ lọc hiện tại)
  const fref = useRef(filters); fref.current = filters;
  const flags = useRef({ sound, speak }); flags.current = { sound, speak };
  useEffect(() => {
    const done = new Set();
    return onLiveNews((it) => {
      const { sound: s, speak: sp } = flags.current;
      if ((!s && !sp) || it.importance < 3 || done.has(it.url) || !matchesFilters(it, { ...fref.current, hours: undefined })) return;
      done.add(it.url);
      if (s) beep("warn");
      if (sp) say(it.title);
    });
  }, []);

  // giữ vị trí cuộn khi có tin mới chèn lên đầu; hiện nút "N tin mới" nếu đang cuộn xuống
  const prevFirst = useRef(null);
  useEffect(() => {
    const first = list[0]?.url;
    const sc = scrollRef.current;
    if (view === "feed" && sc && prevFirst.current && first && first !== prevFirst.current) {
      const added = list.findIndex((x) => x.url === prevFirst.current);
      if (added > 0 && sc.scrollTop > 40) { sc.scrollTop += added * ROW_H[density]; setPending((p) => p + added); }
    }
    prevFirst.current = first || null;
  }, [list, view, density]);
  useEffect(() => {
    const sc = scrollRef.current;
    if (!sc) return undefined;
    const h = () => { if (sc.scrollTop < 40) setPending(0); };
    sc.addEventListener("scroll", h, { passive: true });
    return () => sc.removeEventListener("scroll", h);
  }, [view, list.length > 0]);

  const select = useCallback((it) => { setSel(it); markRead(it.url); }, []);
  const move = (d) => {
    const i = list.findIndex((x) => x.url === sel?.url);
    const n = list[Math.max(0, Math.min(list.length - 1, (i < 0 ? (d > 0 ? -1 : list.length) : i) + d))];
    if (n) { select(n); const sc = scrollRef.current; const idx = list.indexOf(n); if (sc) { const top = idx * ROW_H[density]; if (top < sc.scrollTop) sc.scrollTop = top; else if (top + ROW_H[density] > sc.scrollTop + sc.clientHeight) sc.scrollTop = top + ROW_H[density] - sc.clientHeight; } }
  };
  const onKey = (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "s" && sel) { toggleSaved(sel); }
    else if (e.key === "u" && sel) { markRead(sel.url, !marks.isRead(sel.url)); }
  };
  const clear = () => { setF(DEFAULT_F); setUnread(false); setText(""); };
  const connected = st.status === "open";
  const rowH = ROW_H[density];

  const feedBody = view === "topics"
    ? <><GroupedFeed items={list} marks={marks} selUrl={sel?.url} onSelect={select} words={words} />{feed.hasNextPage && <button type="button" className="btn m-2 self-start" disabled={feed.isFetchingNextPage} onClick={() => feed.fetchNextPage()}>{feed.isFetchingNextPage ? "Đang tải…" : "Tải thêm tin"}</button>}</>
    : (
      <VirtualList count={list.length} rowHeight={rowH} ariaLabel="Dòng tin" scrollRef={scrollRef} className="outline-none"
        onNearEnd={view === "feed" && feed.hasNextPage && !feed.isFetchingNextPage ? () => feed.fetchNextPage() : undefined}
        render={(i) => { const it = list[i]; return <NewsRow it={it} selected={sel?.url === it.url} read={marks.isRead(it.url)} saved={marks.isSaved(it.url)} density={density} onSelect={select} words={words} fresh={it.live && Date.now() - (it.liveAt || 0) < 4000} />; }} />
    );

  return (
    <div className="grid gap-3 lg:grid-cols-[236px_minmax(0,1fr)_minmax(320px,410px)] lg:h-[calc(100dvh-190px)] lg:min-h-[480px]" onKeyDown={onKey}>
      <div className={cn("lg:block min-h-0", showF ? "block" : "hidden")}>
        <Panel title="Lọc tin" icon={ListFilter} pad={false} className="h-full" bodyClass="overflow-auto">
          <FilterSide f={flt} setF={setF} topics={topics} hours={Math.min(720, flt.hours)} onClear={clear} unread={unread} setUnread={setUnread} activeCount={activeCount} />
        </Panel>
      </div>
      <Panel title="Dòng tin" icon={Newspaper} pad={false} className="h-[74dvh] min-h-[420px] lg:min-h-0 lg:h-full" bodyClass="flex flex-col"
        right={<span className="flex items-center gap-2 text-[11.5px] text-muted"><span className={cn("live-dot", connected && "on")} aria-hidden="true" />{connected ? "Trực tiếp" : st.status === "connecting" ? "Đang nối…" : "Mất kết nối"}</span>}>
        <div className="flex flex-wrap items-center gap-2 p-2 border-b border-line shrink-0">
          <div className="relative flex-1 min-w-[160px]">
            <Search size={14} className="absolute left-2 top-[9px] text-faint" aria-hidden="true" />
            <label className="sr-only" htmlFor="nt-q">Tìm toàn văn trong tin</label>
            <input id="nt-q" type="search" className="field w-full !pl-7" placeholder="Tìm toàn văn (vd: lãi suất Fed)…" value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          <button type="button" className="btn lg:!hidden" aria-expanded={showF} onClick={() => setShowF(!showF)}><ListFilter size={14} aria-hidden="true" /> Lọc{activeCount ? ` (${activeCount})` : ""}</button>
          <Seg label="Kiểu xem" value={view} onChange={(v) => { setView(v); setPending(0); }} options={[{ value: "feed", label: "Dòng tin" }, { value: "topics", label: "Theo chủ đề" }, { value: "saved", label: `Đã lưu (${marks.saved.length})` }]} />
          {view !== "topics" && <Seg label="Mật độ" value={density} onChange={setDensity} options={[{ value: "normal", label: "Chuẩn" }, { value: "squawk", label: "Squawk" }]} />}
          <button type="button" className="btn !px-2" aria-pressed={sound} onClick={() => { setSound(!sound); if (!sound) beep("info"); }} title="Âm báo khi có tin quan trọng" aria-label="Âm báo tin quan trọng">{sound ? <Bell size={14} /> : <BellOff size={14} />}</button>
          <button type="button" className="btn !px-2" aria-pressed={speak} onClick={() => setSpeak(!speak)} title="Đọc to tiêu đề tin quan trọng" aria-label="Đọc to tin quan trọng">{speak ? <Mic size={14} /> : <MicOff size={14} />}</button>
          <button type="button" className="btn !px-2" onClick={() => feed.refetch()} aria-label="Làm mới" title="Làm mới"><RefreshCw size={14} className={feed.isFetching ? "animate-spin" : ""} aria-hidden="true" /></button>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 text-[11.5px] text-faint border-b border-line shrink-0">
          <span className="num">{list.length}{feed.hasNextPage && view === "feed" ? "+" : ""} tin</span>
          {q && <span>· khớp “{q}”</span>}
          <span className="ml-auto hidden md:inline">Phím tắt: j/k duyệt · s lưu · u đã đọc</span>
        </div>
        <div className="relative flex-1 min-h-0 flex flex-col">
          {pending > 0 && view === "feed" && <button type="button" className="absolute z-[2] top-2 left-1/2 -translate-x-1/2 btn !bg-accent !text-[var(--accent-fg)] !border-transparent shadow-lg" onClick={() => { if (scrollRef.current) scrollRef.current.scrollTop = 0; setPending(0); }}>↑ {pending} tin mới</button>}
          {view === "saved" && !list.length
            ? <div className="p-4 text-muted text-[12.5px] flex items-center gap-2"><Bookmark size={15} aria-hidden="true" /> Chưa lưu tin nào. Mở một tin rồi bấm “Lưu tin” (hoặc phím s).</div>
            : view !== "saved" && feed.isPending && !list.length ? <QState q={feed} rows={7} />
              : view !== "saved" && feed.isError && !list.length ? <QState q={feed} />
                : !list.length ? <div className="p-4 text-muted text-[12.5px]">Không có tin khớp bộ lọc.{activeCount || q ? <button type="button" className="btn ml-2" onClick={clear}>Xoá bộ lọc</button> : null}</div>
                  : feedBody}
          {view === "feed" && feed.isFetchingNextPage && <div className="text-center text-[11.5px] text-faint py-1 border-t border-line">Đang tải thêm…</div>}
        </div>
      </Panel>
      <div className="hidden lg:block min-h-0">
        <Panel title="Chi tiết" icon={Layers} pad={false} className="h-full" bodyClass="min-h-0 flex flex-col">
          {sel ? <NewsDetail key={sel.url} item={sel} words={words} onTopic={(t) => setF({ ...flt, topic: t })} onSymbol={(s) => setF({ ...flt, symbol: s })} onOpenRelated={(r) => select(r)} />
            : <div className="p-4 text-muted text-[12.5px] grid gap-2"><Rows3 size={18} aria-hidden="true" /><span>Chọn một tin để xem nội dung, cảm xúc, mã liên quan và tin tương tự.</span><span className="text-faint">Mẹo: bật chuông để nghe âm báo khi có tin quan trọng; chế độ Squawk hiển thị mỗi tin một dòng.</span></div>}
        </Panel>
      </div>
      {!desktop && (
        <Dialog open={!!sel} onClose={() => setSel(null)} title="Chi tiết tin" variant="drawer">
          {sel && <div className="h-[calc(100dvh-52px)]"><NewsDetail key={sel.url} item={sel} words={words} onTopic={(t) => { setF({ ...flt, topic: t }); setSel(null); }} onSymbol={(s) => { setF({ ...flt, symbol: s }); setSel(null); }} onOpenRelated={(r) => select(r)} /></div>}
        </Dialog>
      )}
    </div>
  );
}
