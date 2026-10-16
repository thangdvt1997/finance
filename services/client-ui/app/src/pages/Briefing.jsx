// Bản tin AI: tóm tắt thị trường tiếng Việt (do dịch vụ briefing tạo, đã hậu kiểm). Mỗi ý có số trích dẫn [n] trỏ tới mục căn cứ.
// Không hiển thị tên nguồn: mọi chuỗi đi qua clean(). Chỉ đọc.
import { useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Bot, CalendarClock, ExternalLink, Gauge, ListOrdered, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg } from "../components/ui";
import { clean, dateTime, rel } from "../lib/format";
import { t } from "../lib/i18n";

const scopes = () => [{ value: "vn", label: t("Việt Nam") }, { value: "intl", label: t("Quốc tế") }];
const editions = () => [{ value: "morning", label: t("Bản tin sáng") }, { value: "close", label: t("Cuối phiên") }];
const KIND = { get news() { return t("Tin"); }, get calendar() { return t("Lịch"); }, get market() { return t("Số liệu"); }, get sentiment() { return t("Tâm lý"); } };

export const useBriefingLatest = (scope, edition) =>
  useQuery({ queryKey: ["briefing-latest", scope, edition], queryFn: ({ signal }) => api("/briefing/latest", { scope, edition }, signal), staleTime: 60_000, refetchInterval: 300_000, retry: false, placeholderData: keepPreviousData });

function Cites({ list }) {
  if (!list?.length) return null;
  return <span className="whitespace-nowrap">{list.map((n) => <a key={n} href={`#/ban-tin?ref=${n}`} className="num text-[11.5px] text-accent no-underline mr-1" aria-label={t("Căn cứ {n}", { n })} onClick={(e) => { e.preventDefault(); document.getElementById(`cite-${n}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); }}>[{n}]</a>)}</span>;
}

function Mood({ mood }) {
  const v = Math.max(-1, Math.min(1, mood.avg ?? 0));
  const tone = mood.avg > 0.15 ? "up" : mood.avg < -0.15 ? "down" : "";
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2"><Chip tone={tone}>{clean(mood.label)}</Chip><span className="num text-[12px] text-muted">{t("điểm TB {avg} · {n} tin", { avg: `${mood.avg > 0 ? "+" : ""}${Number(mood.avg).toFixed(2)}`, n: mood.n })}</span></div>
      <div className="relative h-[8px] rounded-full bg-panel2 border border-line" role="img" aria-label={t("Điểm tâm lý {v} trên thang -1 đến +1", { v: Number(mood.avg).toFixed(2) })}>
        <span className="absolute top-[-3px] bottom-[-3px] w-[2px] bg-line2 left-1/2" aria-hidden="true" />
        <span className="absolute top-[-3px] w-[10px] h-[14px] rounded-[3px] -translate-x-1/2" style={{ left: `${(v + 1) * 50}%`, background: tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--muted)" }} aria-hidden="true" />
      </div>
      <div className="flex justify-between text-[11.5px] text-muted num"><span>{t("{n} tiêu cực", { n: mood.neg })}</span><span>{t("{n} trung tính", { n: mood.neu })}</span><span>{t("{n} tích cực", { n: mood.pos })}</span></div>
    </div>
  );
}

function Article({ b }) {
  const body = b.body || {};
  const items = b.context?.items || [];
  const isAi = b.status === "llm";
  const when = body.watch || [];
  return (
    <article className="grid gap-3" aria-labelledby="bt-title">
      <header className="panel panel-b grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={isAi ? "accent" : ""} title={isAi ? t("Do mô hình AI chạy cục bộ tóm tắt, đã qua hậu kiểm tự động") : t("Bản mẫu ghép từ dữ liệu, không có AI")}>
            {isAi ? <><Sparkles size={11} aria-hidden="true" /> {t("Tạo bởi AI")}</> : <><ListOrdered size={11} aria-hidden="true" /> {t("Bản mẫu, không AI")}</>}
          </Chip>
          <Chip>{t("Tham khảo, không phải khuyến nghị")}</Chip>
        </div>
        <h2 id="bt-title" className="m-0 text-[19px] leading-tight font-semibold tracking-tight">{clean(b.headline)}</h2>
        <div className="text-[12px] text-muted flex flex-wrap gap-x-3 gap-y-1">
          <span>{clean(b.title)}</span>
          <span title={dateTime(b.generated_at)}>{t("Sinh lúc {when} ({ago})", { when: dateTime(b.generated_at), ago: rel(b.generated_at) })}</span>
          <span className="inline-flex items-center gap-1"><Bot size={12} aria-hidden="true" />{isAi ? t("AI cục bộ") : t("bản mẫu")}</span>
        </div>
      </header>
      <Panel title={t("Ý chính")} icon={ListOrdered}>
        <ol className="m-0 p-0 list-none grid gap-3">
          {(body.points || []).map((p, i) => (
            <li key={i} className="grid grid-cols-[1.6rem_1fr] gap-2"><span className="num text-faint text-[12px] pt-[3px] text-right" aria-hidden="true">{i + 1}.</span><p className="m-0 leading-relaxed">{clean(p.text)} <Cites list={p.cites} /></p></li>
          ))}
          {(body.points || []).length === 0 && <li className="text-muted">{t("Không có ý chính nào qua hậu kiểm.")}</li>}
        </ol>
      </Panel>
      <div className="cols-2">
        <Panel title={t("Cần theo dõi")} icon={CalendarClock}>
          {when.length === 0 ? <p className="m-0 text-muted">{t("Không có sự kiện lịch tác động cao trong khoảng từ 3 giờ trước đến 36 giờ tới.")}</p> : (
            <ul className="m-0 p-0 list-none grid gap-2">{when.map((w, i) => (
              <li key={i} className="rounded-lg border border-line bg-panel2 p-2.5 grid gap-1">
                <div className="flex flex-wrap items-center gap-2"><Chip tone={w.status === "sắp tới" ? "accent" : ""}>{w.status}</Chip><span className="num text-[12px] text-muted" title={dateTime(w.ts)}>{rel(w.ts)}</span><span className="ml-auto"><Cites list={w.cites} /></span></div>
                <div>{clean(w.text)}</div>
              </li>))}</ul>
          )}
        </Panel>
        <Panel title={t("Tâm lý chung")} icon={Gauge}>
          {body.mood ? <div className="grid gap-2"><Mood mood={body.mood} /><p className="m-0 text-[12.5px] text-muted">{clean(body.mood.text)} <Cites list={body.mood.cites} /></p></div> : <p className="m-0 text-muted">{t("Chưa có tin có điểm tâm lý trong 24 giờ qua.")}</p>}
        </Panel>
      </div>
      <Panel title={t("Căn cứ trích dẫn ({n})", { n: items.length })} icon={ShieldCheck} pad={false}>
        <ol className="m-0 p-0 list-none max-h-[480px] overflow-y-auto" aria-label={t("Danh sách mục được trích dẫn")}>
          {items.map((it) => (
            <li key={it.n} id={`cite-${it.n}`} className="grid grid-cols-[2rem_1fr] gap-1.5 px-3 border-b border-line last:border-b-0 scroll-mt-24">
              <span className="num text-[11.5px] text-faint text-right pt-3">[{it.n}]</span>
              {it.url ? (
                <a href={it.url} target="_blank" rel="noopener noreferrer" className="no-underline py-2.5 min-h-[44px] block leading-snug">{clean(it.title)} <ExternalLink size={11} className="inline text-faint" aria-hidden="true" /><span className="sr-only"> {t("(mở bài gốc)")}</span>
                  <span className="block text-[11px] text-faint">{KIND[it.kind] || it.kind}{it.ts ? ` · ${rel(it.ts)}` : ""}</span></a>
              ) : <div className="py-2.5 min-h-[44px] leading-snug">{clean(it.title)}<span className="block text-[11px] text-faint">{KIND[it.kind] || it.kind}{it.ts ? ` · ${rel(it.ts)}` : ""}</span></div>}
            </li>))}
        </ol>
      </Panel>
    </article>
  );
}

export default function Briefing() {
  const [scope, setScope] = useState("vn");
  const [edition, setEdition] = useState("morning");
  const q = useBriefingLatest(scope, edition);
  const empty = useMemo(() => q.isError && q.error?.status === 404, [q.isError, q.error]);
  return (
    <>
      <PageHead title={t("Bản tin AI")} sub={t("Tóm tắt thị trường tiếng Việt từ tin tức, lịch và số liệu của hệ thống. Mỗi nhận định đều kèm số trích dẫn tới mục căn cứ.")}
        right={<><Seg value={scope} onChange={setScope} options={scopes()} label={t("Phạm vi")} /><Seg value={edition} onChange={setEdition} options={editions()} label={t("Kỳ bản tin")} /></>} />
      <Disclaimer>{t("Bản tin do AI tạo, chỉ để tham khảo,")} <b>{t("không phải khuyến nghị đầu tư")}</b>{t(". AI chỉ tóm tắt dữ liệu có sẵn. Tự động cập nhật lúc 06:15 và 16:30 (giờ Việt Nam).")}</Disclaimer>
      {empty ? <div className="panel panel-b text-muted">{t("Chưa có bản tin cho lựa chọn này.")}</div> : (
        <Async q={q} rows={8} isEmpty={(d) => !d} empty={t("Chưa có bản tin cho lựa chọn này.")}>{(b) => <Article b={b} />}</Async>
      )}
    </>
  );
}
