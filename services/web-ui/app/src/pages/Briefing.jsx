import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Bot, CalendarClock, ExternalLink, Gauge, History, ListOrdered, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg, cn } from "../components/ui";
import { clean, dateTime, rel } from "../lib/format";
import "../briefing.css";

const SCOPES = [{ value: "vn", label: "Việt Nam" }, { value: "intl", label: "Quốc tế" }];
const EDITIONS = [{ value: "morning", label: "Bản tin sáng" }, { value: "close", label: "Cuối phiên" }];
const KIND = { news: "Tin", calendar: "Lịch", market: "Số liệu", sentiment: "Tâm lý" };

const useBriefingList = (scope, edition) =>
  useQuery({ queryKey: ["briefing-list", scope, edition], queryFn: ({ signal }) => api("/briefing/list", { scope, edition, limit: 30 }, signal), staleTime: 30_000, refetchInterval: 120_000, placeholderData: keepPreviousData });
const useBriefing = (id) =>
  useQuery({ queryKey: ["briefing", id], queryFn: ({ signal }) => api(`/briefing/${id}`, {}, signal), enabled: !!id, staleTime: 60_000, placeholderData: keepPreviousData });

/** Chip trích dẫn [n]: tin -> mở bài gốc (tab mới); mục khác -> nhảy tới mục trong danh sách trích dẫn. */
function Cite({ n, item, onJump }) {
  const title = item ? `${KIND[item.kind] || ""}: ${clean(item.title)}` : `Mục ${n}`;
  const cls = "cite num";
  if (item?.url) return <a className={cls} href={item.url} target="_blank" rel="noopener noreferrer" title={`${title} (mở bài gốc)`} aria-label={`Trích dẫn ${n}: ${title}. Mở bài gốc trong tab mới`}>{n}</a>;
  return <button type="button" className={cls} title={title} aria-label={`Trích dẫn ${n}: ${title}`} onClick={() => onJump(n)}>{n}</button>;
}

function MoodBar({ mood }) {
  const v = Math.max(-1, Math.min(1, mood.avg ?? 0));
  const tone = mood.avg > 0.15 ? "up" : mood.avg < -0.15 ? "down" : "";
  const total = Math.max(1, mood.pos + mood.neg + mood.neu);
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={tone}>{mood.label}</Chip>
        <span className="num text-[12px] text-muted">điểm TB {mood.avg > 0 ? "+" : ""}{Number(mood.avg).toFixed(2)} · {mood.n} tin có điểm</span>
      </div>
      <div className="relative h-[8px] rounded-full bg-panel2 border border-line" role="img" aria-label={`Điểm tâm lý ${Number(mood.avg).toFixed(2)} trên thang -1 đến +1`}>
        <span className="absolute top-[-3px] bottom-[-3px] w-[2px] bg-line2 left-1/2" aria-hidden="true" />
        <span className="absolute top-[-3px] w-[10px] h-[14px] rounded-[3px] -translate-x-1/2" style={{ left: `${(v + 1) * 50}%`, background: tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--muted)" }} aria-hidden="true" />
      </div>
      <div className="flex h-[6px] rounded-full overflow-hidden" aria-hidden="true">
        <span style={{ width: `${(mood.neg / total) * 100}%`, background: "var(--down)" }} />
        <span style={{ width: `${(mood.neu / total) * 100}%`, background: "var(--line2)" }} />
        <span style={{ width: `${(mood.pos / total) * 100}%`, background: "var(--up)" }} />
      </div>
      <div className="flex justify-between text-[11.5px] text-muted num"><span>{mood.neg} tiêu cực</span><span>{mood.neu} trung tính</span><span>{mood.pos} tích cực</span></div>
      {mood.top?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 text-[11.5px]">
          {mood.top.map((t) => <span key={t.symbol} className="chip" title={`${t.count} tin`}>{String(t.symbol).replace(/^[A-Za-z]+:/, "")} <span className={cn("num", t.avg > 0.15 ? "text-up" : t.avg < -0.15 ? "text-down" : "text-muted")}>{t.avg > 0 ? "+" : ""}{Number(t.avg).toFixed(2)}</span></span>)}
        </div>
      )}
    </div>
  );
}

function Article({ b }) {
  const body = b.body || {};
  const items = b.context?.items || [];
  const by = useMemo(() => Object.fromEntries(items.map((i) => [i.n, i])), [items]);
  const [hot, setHot] = useState(null);
  const refs = useRef({});
  const jump = (n) => { setHot(n); refs.current[n]?.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); };
  useEffect(() => { if (hot == null) return undefined; const t = setTimeout(() => setHot(null), 2500); return () => clearTimeout(t); }, [hot]);
  const q = b.quality || {};
  const isAi = b.status === "llm";
  const when = body.watch || [];

  return (
    <article className="grid gap-3" aria-labelledby="bt-title">
      <header className="rounded-lg border border-line bg-panel p-4 grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={isAi ? "accent" : ""} title={isAi ? "Nội dung do mô hình AI chạy cục bộ tóm tắt, đã qua hậu kiểm tự động" : "Mô hình AI không dùng được hoặc không qua hậu kiểm: đây là bản mẫu ghép từ dữ liệu, không có AI"}>
            {isAi ? <><Sparkles size={11} aria-hidden="true" /> Tạo bởi AI</> : <><ListOrdered size={11} aria-hidden="true" /> Bản mẫu, không AI</>}
          </Chip>
          <Chip title="Không phải lời khuyên đầu tư, không có lệnh giao dịch">Tham khảo · không phải khuyến nghị</Chip>
        </div>
        <h2 id="bt-title" className="m-0 text-[20px] leading-tight font-semibold tracking-tight">{clean(b.headline)}</h2>
        <div className="text-[12px] text-muted flex flex-wrap gap-x-3 gap-y-1">
          <span>{b.title}</span>
          <span title={dateTime(b.generated_at)}>Sinh lúc {dateTime(b.generated_at)} ({rel(b.generated_at)})</span>
          <span className="inline-flex items-center gap-1"><Bot size={12} aria-hidden="true" />{isAi ? b.model : "bản mẫu"}{b.latency_ms ? ` · ${Math.round(b.latency_ms / 1000)} giây` : ""}</span>
        </div>
      </header>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] items-start">
        <div className="grid gap-3 min-w-0">
          <Panel title="Ý chính" icon={ListOrdered}>
            <ol className="m-0 p-0 list-none grid gap-3">
              {(body.points || []).map((p, i) => (
                <li key={i} className="grid grid-cols-[1.6rem_1fr] gap-2">
                  <span className="num text-faint text-[12px] pt-[3px] text-right" aria-hidden="true">{i + 1}.</span>
                  <p className="m-0 leading-relaxed">
                    {clean(p.text)}{" "}
                    <span className="inline-flex flex-wrap gap-1 align-baseline" aria-label="Căn cứ">{(p.cites || []).map((n) => <Cite key={n} n={n} item={by[n]} onJump={jump} />)}</span>
                  </p>
                </li>
              ))}
              {(body.points || []).length === 0 && <li className="text-muted">Không có ý chính nào qua hậu kiểm.</li>}
            </ol>
          </Panel>

          <Panel title="Cần theo dõi hôm nay" icon={CalendarClock}>
            {when.length === 0 ? (
              <p className="m-0 text-muted">Không có sự kiện lịch tác động cao trong khoảng từ 3 giờ trước đến 36 giờ tới.</p>
            ) : (
              <ul className="m-0 p-0 list-none grid gap-2">
                {when.map((w, i) => (
                  <li key={i} className="rounded-md border border-line bg-panel2 p-2.5 grid gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Chip tone={w.status === "sắp tới" ? "accent" : ""}>{w.status}</Chip>
                      <span className="num text-[12px] text-muted" title={dateTime(w.ts)}>{rel(w.ts)}</span>
                      <span className="inline-flex gap-1 ml-auto">{(w.cites || []).map((n) => <Cite key={n} n={n} item={by[n]} onJump={jump} />)}</span>
                    </div>
                    <div>{clean(w.text)}</div>
                  </li>
                ))}
              </ul>
            )}
            <p className="m-0 mt-2 text-[11.5px] text-faint">Cửa sổ rủi ro tin = khoảng thời gian quanh sự kiện mà biến động có thể bất thường (theo cấu hình hệ thống).</p>
          </Panel>
        </div>

        <div className="grid gap-3 min-w-0">
          <Panel title="Tâm lý chung (từ số liệu)" icon={Gauge}>
            {body.mood ? (
              <div className="grid gap-2">
                <MoodBar mood={body.mood} />
                <p className="m-0 text-[12.5px] text-muted">{clean(body.mood.text)} <span className="inline-flex gap-1">{(body.mood.cites || []).map((n) => <Cite key={n} n={n} item={by[n]} onJump={jump} />)}</span></p>
              </div>
            ) : <p className="m-0 text-muted">Chưa có tin có điểm tâm lý trong 24 giờ qua.</p>}
          </Panel>

          <Panel title={`Căn cứ trích dẫn (${items.length})`} icon={ShieldCheck} bodyClass="!p-0">
            <ol className="m-0 p-0 list-none max-h-[560px] overflow-y-auto" aria-label="Danh sách mục được trích dẫn">
              {items.map((it) => (
                <li key={it.n} ref={(el) => { refs.current[it.n] = el; }} className={cn("grid grid-cols-[1.9rem_1fr] gap-1.5 px-3 py-2 border-b border-line last:border-b-0", hot === it.n && "cite-hot")}>
                  <span className="num text-[11.5px] text-faint text-right pt-[2px]">[{it.n}]</span>
                  <div className="min-w-0 grid gap-0.5">
                    {it.url ? (
                      <a href={it.url} target="_blank" rel="noopener noreferrer" className="no-underline hover:text-accent leading-snug">{clean(it.title)} <ExternalLink size={11} className="inline text-faint" aria-hidden="true" /><span className="sr-only"> (mở bài gốc)</span></a>
                    ) : <span className="leading-snug">{clean(it.title)}</span>}
                    <div className="flex flex-wrap gap-2 text-[11px] text-faint"><span>{KIND[it.kind] || it.kind}</span>{it.ts && <span title={dateTime(it.ts)}>{rel(it.ts)}</span>}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>

          <Panel title="Hậu kiểm tự động" icon={History}>
            <ul className="m-0 pl-4 grid gap-1 text-[12.5px] text-muted">
              <li>Giữ <b className="text-fg num">{q.n_points ?? (body.points || []).length}</b>{q.raw_points ? <> / {q.raw_points} ý do AI viết</> : null}; mọi số và mã đều phải có trong mục được trích dẫn.</li>
              {(q.dropped || []).length > 0 && <li>Đã loại {q.dropped.length} ý: {[...new Set(q.dropped.map((d) => String(d.reason).split(":")[0]))].join("; ")}.</li>}
              {q.blocked_injection > 0 && <li>Đã chặn {q.blocked_injection} tin có dấu hiệu chèn chỉ thị vào AI (không dùng làm căn cứ).</li>}
              {!isAi && q.fallback_reason && <li>Lý do dùng bản mẫu: {clean(q.fallback_reason)}.</li>}
            </ul>
          </Panel>
        </div>
      </div>
    </article>
  );
}

export default function Briefing() {
  const [scope, setScope] = useState("vn");
  const [edition, setEdition] = useState("morning");
  const [sel, setSel] = useState(null);
  const list = useBriefingList(scope, edition);
  const items = list.data?.items || [];
  const id = sel && items.some((x) => x.id === sel) ? sel : items[0]?.id;
  const one = useBriefing(id);

  return (
    <>
      <PageHead title="Bản tin" sub="Bản tin thị trường tiếng Việt do mô hình AI chạy cục bộ tóm tắt từ dữ liệu của hệ thống. Mỗi nhận định đều kèm số trích dẫn bấm được tới tin gốc."
        right={<>
          <Seg value={scope} onChange={(v) => { setScope(v); setSel(null); }} options={SCOPES} label="Phạm vi" />
          <Seg value={edition} onChange={(v) => { setEdition(v); setSel(null); }} options={EDITIONS} label="Kỳ bản tin" />
        </>} />
      <Disclaimer>Bản tin do AI tạo, chỉ để tham khảo, <b>không phải khuyến nghị đầu tư</b>. AI chỉ tóm tắt dữ liệu có sẵn; hệ thống không đặt hoặc gửi lệnh nào. Bản tin tự động tạo lúc 06:15 và 16:30 (giờ Việt Nam).</Disclaimer>
      <div className="grid gap-3 mt-3 lg:grid-cols-[13rem_minmax(0,1fr)] items-start">
        <Panel title="Các bản tin" icon={History} bodyClass="!p-0">
          <Async q={list} rows={5} empty="Chưa có bản tin nào cho lựa chọn này." hint="Bản tin được tạo tự động theo lịch; có thể chạy tay bằng endpoint nội bộ của service.">
            {() => (
              <ul className="m-0 p-0 list-none max-h-[70vh] overflow-y-auto" aria-label="Danh sách bản tin">
                {items.map((x) => (
                  <li key={x.id}>
                    <button type="button" aria-pressed={x.id === id} onClick={() => setSel(x.id)}
                      className={cn("w-full text-left px-3 py-2 border-0 border-b border-line bg-transparent cursor-pointer text-fg grid gap-0.5 hover:bg-panel2", x.id === id && "bg-panel2 shadow-[inset_2px_0_0_var(--accent)]")}>
                      <span className="num text-[12px]">{dateTime(x.generated_at)}</span>
                      <span className="text-[11.5px] text-muted flex items-center gap-1.5">{x.status === "llm" ? "AI" : "Bản mẫu"}{x.latency_ms ? ` · ${Math.round(x.latency_ms / 1000)}s` : ""}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Async>
        </Panel>
        <div className="min-w-0">
          {id && <Async q={one} rows={8} isEmpty={(d) => !d}>{(b) => <Article b={b} />}</Async>}
        </div>
      </div>
    </>
  );
}
