// Thành phần của terminal tin tức: hàng tin, chip cảm xúc/mức quan trọng, tô sáng từ khoá, panel chi tiết (tin liên quan, mã liên quan).
import { memo, useMemo } from "react";
import { Bookmark, BookmarkCheck, Check, Copy, ExternalLink, EyeOff, LineChart, Tag, X } from "lucide-react";
import { Skeleton, cn } from "../ui";
import { useNewsRelated } from "../../lib/intel";
import { IMPORTANCE_LABEL, TOPIC_LABEL, markRead, toggleSaved, useNewsMarks } from "../../lib/intelNews";
import { useQuote } from "../../lib/stream";
import { chartHref } from "../../lib/intel";
import { dateTime, price, rel, time } from "../../lib/format";
import { copyText } from "../../ux/actions";

export const shortSym = (s) => (s || "").replace(/^[A-Za-z]+:/, "").replace(/USDT$/, "");

/** Tô sáng các từ khoá tìm kiếm trong văn bản (không phân biệt hoa/thường). */
export function Highlight({ text, words }) {
  const parts = useMemo(() => {
    const ws = (words || []).filter((w) => w.length > 1);
    if (!ws.length || !text) return null;
    const re = new RegExp(`(${ws.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig");
    return text.split(re);
  }, [text, words]);
  if (!parts) return text;
  const lw = new Set((words || []).map((w) => w.toLowerCase()));
  return parts.map((p, i) => (lw.has(p.toLowerCase()) ? <mark key={i} className="bg-[var(--accent-bg)] text-accent rounded-[2px] px-[1px]">{p}</mark> : p));
}

export function SentimentChip({ v, label }) {
  if (v == null) return null;
  const tone = v > 0.15 ? "up" : v < -0.15 ? "down" : "";
  const txt = v > 0.15 ? "Tích cực" : v < -0.15 ? "Tiêu cực" : "Trung tính";
  return <span className={cn("chip", tone)} title={`Cảm xúc ${v > 0 ? "+" : ""}${v.toFixed(2)} (−1..+1)${label ? ` · ${label}` : ""}`}>{v > 0.15 ? "▲" : v < -0.15 ? "▼" : "■"} <span className="num">{v > 0 ? "+" : ""}{v.toFixed(2)}</span><span className="sr-only"> {txt}</span></span>;
}

export function ImpTag({ n }) {
  if (n >= 3) return <span className="in-tag hot" title="Tin quan trọng: chủ đề có khả năng tác động thị trường">Quan trọng</span>;
  if (n === 2) return <span className="in-tag warm" title="Tin cần chú ý">Chú ý</span>;
  return null;
}

/** Hàng tin; chiều cao cố định theo `density` để ảo hoá danh sách. */
export const NewsRow = memo(function NewsRow({ it, selected, read, saved, density, onSelect, words, fresh }) {
  const squawk = density === "squawk";
  return (
    <div role="button" tabIndex={0} aria-pressed={selected} aria-label={it.title}
      onClick={() => onSelect(it)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(it); } }}
      className={cn("news-row h-full", read && "read", it.importance >= 3 ? "imp3" : it.importance === 2 ? "imp2" : "", fresh && "news-new", squawk && "!grid-cols-1 content-center")}>
      {squawk ? (
        <div className="flex items-center gap-2 min-w-0">
          <span className="num text-[11px] text-faint shrink-0 w-[38px]">{time(it.ts)}</span>
          {it.importance >= 2 && <span className={cn("shrink-0 w-[7px] h-[7px] rounded-full", it.importance >= 3 ? "bg-[var(--down)]" : "bg-[var(--accent)]")} aria-label={IMPORTANCE_LABEL[it.importance]} />}
          <span className="nt truncate text-[12.5px] flex-1 min-w-0"><Highlight text={it.title} words={words} /></span>
          {it.sentiment != null && <span className={cn("num text-[11px] shrink-0", it.sentiment > 0.15 ? "up" : it.sentiment < -0.15 ? "down" : "flat")}>{it.sentiment > 0 ? "+" : ""}{it.sentiment.toFixed(2)}</span>}
          {saved && <BookmarkCheck size={12} className="text-accent shrink-0" aria-label="Đã lưu" />}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-[6px] min-w-0 text-[11.5px]">
            <span className="num text-faint shrink-0" title={dateTime(it.ts)}>{time(it.ts)}</span>
            <span className="text-faint shrink-0 hidden sm:inline">· {rel(it.ts)}</span>
            <ImpTag n={it.importance} />
            <SentimentChip v={it.sentiment} label={it.sentiment_label} />
            {(it.symbols || []).slice(0, 3).map((s) => <span key={s} className="chip">{shortSym(s)}</span>)}
            {it.topics?.[0] && <span className="in-tag hidden md:inline-flex truncate max-w-[9rem]">{TOPIC_LABEL[it.topics[0]] || it.topics[0]}</span>}
            <span className="ml-auto flex items-center gap-1 shrink-0">
              {it.lang && <span className="uppercase text-[10px] text-faint">{it.lang}</span>}
              {saved && <BookmarkCheck size={12} className="text-accent" aria-label="Đã lưu" />}
            </span>
          </div>
          <div className="nt text-[13px] line-clamp-2"><Highlight text={it.title} words={words} /></div>
        </>
      )}
    </div>
  );
});

function SymBadge({ symbol, onFilter }) {
  const q = useQuote(symbol);
  const px = q ? (q.bid ?? q.ask) : null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-[2px] text-[12px] bg-panel2">
      <button type="button" className="font-semibold bg-transparent border-0 p-0 cursor-pointer text-fg hover:text-accent" onClick={() => onFilter?.(symbol)} title={`Lọc tin về ${shortSym(symbol)}`}>{shortSym(symbol)}</button>
      {px != null && <span className={cn("num text-[11.5px]", q.dir > 0 ? "up" : q.dir < 0 ? "down" : "text-muted")}>{price(symbol, px)}</span>}
      <a href={chartHref(symbol)} className="text-muted hover:text-accent inline-flex" aria-label={`Mở biểu đồ ${shortSym(symbol)}`} title="Mở biểu đồ"><LineChart size={12} aria-hidden="true" /></a>
    </span>
  );
}

/** Panel chi tiết: nội dung, cảm xúc, chủ đề, mã liên quan (giá trực tiếp), tin liên quan, thao tác lưu/đã đọc/sao chép. */
export function NewsDetail({ item, onClose, onTopic, onSymbol, onOpenRelated, words }) {
  const marks = useNewsMarks();
  const rel_ = useNewsRelated(item.url);
  const saved = marks.isSaved(item.url);
  const read = marks.isRead(item.url);
  const s = item.sentiment;
  const pos = s == null ? 50 : Math.round((Math.max(-1, Math.min(1, s)) + 1) * 50);
  const symbols = useMemo(() => [...new Set([...(item.symbols || []), ...((rel_.data?.symbols || []).map((x) => x.symbol))])], [item.symbols, rel_.data]);
  return (
    <article className="flex flex-col min-h-0 h-full" aria-label="Chi tiết tin">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-line shrink-0">
        <ImpTag n={item.importance} />
        <span className="text-[12px] text-muted num" title={dateTime(item.ts)}>{dateTime(item.ts)} · {rel(item.ts)}</span>
        {onClose && <button type="button" className="btn !px-2 ml-auto" onClick={onClose} aria-label="Đóng chi tiết"><X size={14} aria-hidden="true" /></button>}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 grid gap-3 content-start">
        <h2 className="m-0 text-[16px] leading-snug font-semibold"><Highlight text={item.title} words={words} /></h2>
        {item.summary && <p className="m-0 text-[13px] leading-relaxed text-muted whitespace-pre-line"><Highlight text={item.summary} words={words} /></p>}
        <div>
          <div className="text-[11.5px] text-muted mb-1">Cảm xúc tin (mô hình ngôn ngữ, tham khảo)</div>
          <div className="in-meter" role="img" aria-label={s == null ? "Chưa có điểm cảm xúc" : `Cảm xúc ${s.toFixed(2)} trên thang từ −1 đến +1`}>{s != null && <b style={{ left: `${pos}%` }} />}</div>
          <div className="flex justify-between text-[10.5px] text-faint mt-1"><span>Tiêu cực −1</span><span className="num">{s == null ? "chưa gắn nhãn" : `${s > 0 ? "+" : ""}${s.toFixed(2)}`}</span><span>+1 Tích cực</span></div>
        </div>
        {!!item.topics?.length && (
          <div className="flex flex-wrap gap-1" aria-label="Chủ đề">
            {item.topics.map((t) => <button key={t} type="button" className="in-tag cursor-pointer bg-transparent" onClick={() => onTopic?.(t)} title="Lọc theo chủ đề này"><Tag size={10} className="mr-1" aria-hidden="true" />{TOPIC_LABEL[t] || t}</button>)}
          </div>
        )}
        {!!symbols.length && (
          <div>
            <div className="text-[11.5px] text-muted mb-1">Mã liên quan</div>
            <div className="flex flex-wrap gap-1">{symbols.map((sy) => <SymBadge key={sy} symbol={sy} onFilter={onSymbol} />)}</div>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <a className="btn no-underline" href={item.url} target="_blank" rel="noopener noreferrer" onClick={() => markRead(item.url)}><ExternalLink size={13} aria-hidden="true" /> Đọc bài gốc</a>
          <button type="button" className="btn" aria-pressed={saved} onClick={() => toggleSaved(item)}>{saved ? <BookmarkCheck size={13} aria-hidden="true" /> : <Bookmark size={13} aria-hidden="true" />} {saved ? "Đã lưu" : "Lưu tin"}</button>
          <button type="button" className="btn" onClick={() => markRead(item.url, !read)}>{read ? <EyeOff size={13} aria-hidden="true" /> : <Check size={13} aria-hidden="true" />} {read ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}</button>
          <button type="button" className="btn" onClick={() => copyText(item.title)}><Copy size={13} aria-hidden="true" /> Sao chép tiêu đề</button>
        </div>
        <section aria-label="Tin liên quan">
          <h3 className="m-0 mb-1 text-[12.5px] font-semibold">Tin liên quan</h3>
          {rel_.isPending ? <Skeleton rows={3} /> : rel_.isError ? <div className="text-[12px] text-faint">Không tìm được tin liên quan.</div>
            : !rel_.data?.related?.length ? <div className="text-[12px] text-faint">Chưa có tin tương tự trong 14 ngày quanh thời điểm này.</div>
            : (
              <ul className="m-0 p-0 list-none grid">
                {rel_.data.related.map((r) => (
                  <li key={r.url}>
                    <button type="button" className="w-full text-left bg-transparent border-0 border-b border-line py-[6px] px-0 cursor-pointer text-fg hover:text-accent" onClick={() => onOpenRelated?.(r)}>
                      <div className="text-[12.5px] leading-snug line-clamp-2">{r.title}</div>
                      <div className="text-[11px] text-faint flex gap-2 mt-[2px]"><span className="num">{dateTime(r.ts)}</span>{r.sentiment != null && <span className={cn("num", r.sentiment > 0.15 ? "up" : r.sentiment < -0.15 ? "down" : "")}>{r.sentiment > 0 ? "+" : ""}{r.sentiment.toFixed(2)}</span>}</div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
        </section>
        <p className="m-0 text-[11px] text-faint">Điểm cảm xúc, chủ đề và mức quan trọng do mô hình tự động gắn — chỉ mang tính tham khảo, không phải khuyến nghị.</p>
      </div>
    </article>
  );
}
