// Bảng bên của AI Training Class: gắn nhãn ví dụ (active learning), Sổ tay phương pháp (hồ sơ + phiên bản + diff + xuất YAML), tin đã ghim.
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, FileText, HelpCircle, X } from "lucide-react";
import { Chip, Stat, cn } from "../ui";
import { cget, cpost, mediaUrl } from "./classApi";
import SafeImg from "./SafeImg";
import { hhmm, num, pct, show, useCls } from "./ctx";
import { ResultCard } from "./MessageView";
import Markdown from "./Markdown";

const VERD = [["dung", "ĐÚNG", "RIGHT", "up", Check], ["gan_dung", "GẦN ĐÚNG", "CLOSE", "accent", HelpCircle], ["sai", "SAI", "WRONG", "down", X]];

function Zoom({ src, onClose }) {
  useEffect(() => { const h = (e) => e.key === "Escape" && onClose(); addEventListener("keydown", h); return () => removeEventListener("keydown", h); }, [onClose]);
  return <div className="cr-zoom" role="dialog" aria-modal="true" aria-label="Zoom" onClick={onClose}><img src={src} alt="" /><button type="button" className="btn cr-zoom-x" onClick={onClose} aria-label="Close"><X size={16} /></button></div>;
}

export function LabelPanel({ scans }) {
  const { t, rid, lang } = useCls();
  const qc = useQueryClient();
  const lq = useQuery({ queryKey: ["cls", rid, "labels"], queryFn: ({ signal }) => cget(`/rooms/${encodeURIComponent(rid)}/labels`, {}, signal), refetchInterval: 8000 });
  const items = lq.data?.items || [], sum = lq.data?.summary || {};
  const byEx = useMemo(() => { const m = {}; for (const l of items) m[l.example_id] = l; return m; }, [items]);
  const examples = useMemo(() => scans.flatMap((s) => (s.data?.examples || []).map((e) => ({ ...e, round: s.data?.round }))).reverse(), [scans]);
  const [reason, setReason] = useState({}), [zoom, setZoom] = useState(null), [err, setErr] = useState(null), [pendingId, setPendingId] = useState(null);
  const mut = useMutation({
    mutationFn: ({ example_id, verdict }) => cpost(`/rooms/${encodeURIComponent(rid)}/labels`, { example_id, verdict, ...(reason[example_id]?.trim() ? { reason: reason[example_id].trim().slice(0, 300) } : {}) }),
    onMutate: ({ example_id }) => { setPendingId(example_id); setErr(null); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cls", rid, "labels"] }),
    onError: (e) => setErr(e.message), onSettled: () => setPendingId(null),
  });
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-3 gap-2">
        <Stat label={t("Độ chính xác", "Precision")} value={sum.precision == null ? "—" : pct(sum.precision)} sub={sum.precision_strict == null ? undefined : `${t("chặt", "strict")} ${pct(sum.precision_strict)}`} term={false} />
        <Stat label={t("Độ phủ", "Coverage")} value={sum.coverage == null ? "—" : pct(sum.coverage)} sub={`${sum.n_labeled ?? 0}/${sum.n_examples ?? examples.length}`} term={false} />
        <Stat label={t("Vòng", "Rounds")} value={sum.rounds ?? "—"} term={false} />
      </div>
      {Array.isArray(sum.by_round) && sum.by_round.length > 0 && <p className="m-0 text-[12px] text-muted">{sum.by_round.map((r) => `${t("Vòng", "R")}${r.round}: ${r.precision == null ? "—" : pct(r.precision)} (${r.n})`).join(" · ")}</p>}
      {sum.advice && <p className="m-0 text-[12.5px]" role="note">{show(sum.advice)}</p>}
      <p className="m-0 text-[12px] text-muted">{t("Độ chính xác = (ĐÚNG + ½·GẦN ĐÚNG) / đã gắn nhãn. Chưa có nhãn thì để trống, không ước lượng. Nhãn SAI kèm lý do thành phản ví dụ.", "Precision = (RIGHT + ½·CLOSE) / labeled. Empty until labeled; never estimated. WRONG labels with a reason become counter-examples.")}</p>
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
      {!examples.length && <p className="m-0 text-[13px] text-muted">{t("Chưa có ví dụ. Nhờ AI tìm trong lịch sử và đưa 6-10 ảnh nến để bạn gắn nhãn.", "No examples yet. Ask the AI to search history and show 6-10 candle images to label.")}</p>}
      <ul className="cr-exlist m-0 p-0 list-none grid gap-3">
        {examples.map((e) => {
          const cur = byEx[e.id], u = mediaUrl(e.image_url), busy = pendingId === e.id;
          return (
            <li key={e.id} className="cr-ex">
              {u && <button type="button" className="cr-eximg" onClick={() => setZoom(u)} aria-label={t("Phóng to ảnh", "Zoom image")}><SafeImg src={u} alt={`${e.symbol || ""} ${e.tf || ""} ${e.ts || ""}`} loading="lazy" lang={lang} /></button>}
              <div className="text-[12px] flex flex-wrap gap-x-2 gap-y-0.5 mt-1"><b>{e.symbol} {e.tf}</b><span className="text-muted">{hhmm(e.ts)}</span>{e.entry != null && <span>{t("Vào", "Entry")} {show(e.entry)}</span>}{e.sl != null && <span>SL {show(e.sl)}</span>}</div>
              {e.note && <p className="m-0 text-[12px] text-muted">{e.note}</p>}
              <input className="cr-inp mt-1" value={reason[e.id] ?? cur?.reason ?? ""} maxLength={300} onChange={(ev) => setReason((r) => ({ ...r, [e.id]: ev.target.value }))} placeholder={t("Lý do (đặc biệt khi SAI/GẦN ĐÚNG)", "Reason (esp. for WRONG/CLOSE)")} aria-label={t("Lý do", "Reason")} />
              <div className="flex gap-1 mt-1 flex-wrap" role="group" aria-label={t("Nhãn", "Label")}>
                {VERD.map(([v, vi, en, tone, Ic]) => <button key={v} type="button" disabled={busy} aria-pressed={cur?.verdict === v} className={cn("btn cr-sm", cur?.verdict === v ? `cr-on-${tone}` : "ghost")} onClick={() => mut.mutate({ example_id: e.id, verdict: v })}><Ic size={13} aria-hidden="true" />{lang === "en" ? en : vi}</button>)}
              </div>
            </li>
          );
        })}
      </ul>
      {zoom && <Zoom src={zoom} onClose={() => setZoom(null)} />}
    </div>
  );
}

function KV({ obj }) {
  const { t } = useCls();
  if (obj == null) return null;
  const CF = { cao: ["Cao", "up"], high: ["Cao", "up"], "vừa": ["Vừa", ""], vua: ["Vừa", ""], medium: ["Vừa", ""], "thấp": ["Thấp", "down"], thap: ["Thấp", "down"], low: ["Thấp", "down"] };
  const rows = Array.isArray(obj) ? obj.map((v, i) => [i + 1, v]) : typeof obj === "object" ? Object.entries(obj) : [["", obj]];
  const val = (v) => {
    if (Array.isArray(v)) return v.map(show).join("; ");
    if (v && typeof v === "object") {
      const c = v.confidence ?? v.certainty, [cl, ct] = CF[String(c).toLowerCase()] || [];
      const rest = Object.entries(v).filter(([a]) => !/^(confidence|certainty|value|text)$/.test(a));
      const main = v.value ?? v.text;
      return <>{main != null ? show(main) : ""}{rest.length > 0 && <span className="text-muted">{main != null ? " · " : ""}{rest.map(([a, b]) => `${a.replace(/_/g, " ")}: ${show(b)}`).join(" · ")}</span>}{cl && <Chip tone={ct} className="ml-2">{t("Chắc chắn", "Certainty")}: {cl}</Chip>}</>;
    }
    return show(v);
  };
  return <dl className="m-0 grid gap-1">{rows.map(([k, v]) => <div key={k} className="cr-und-row"><dt>{String(k).replace(/_/g, " ")}</dt><dd>{val(v)}</dd></div>)}</dl>;
}

export function Notebook() {
  const { t, rid } = useCls();
  const R = encodeURIComponent(rid);
  const pq = useQuery({ queryKey: ["cls", rid, "profile"], queryFn: ({ signal }) => cget(`/rooms/${R}/profile`, {}, signal), refetchInterval: 10000 });
  const p = pq.data?.profile || {}, versions = pq.data?.versions || [];
  const [va, setVa] = useState(""), [vb, setVb] = useState("");
  const dq = useQuery({ queryKey: ["cls", rid, "diff", va, vb], enabled: !!va && !!vb && va !== vb, queryFn: ({ signal }) => cget(`/rooms/${R}/profile/diff`, { a: va, b: vb }, signal) });
  const [ex, setEx] = useState(null), [busy, setBusy] = useState(false), [err, setErr] = useState(null);
  const doExport = async (register) => {
    setBusy(true); setErr(null);
    try { setEx(await cpost(`/rooms/${R}/profile/export`, { ...(va && !vb ? { version: +va } : {}), register: !!register })); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const dl = () => { const b = new Blob([ex.yaml || ""], { type: "text/yaml" }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `${p.name || "kich-ban"}.yaml`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); };
  if (pq.isError) return <p className="m-0 text-[13px] text-muted">{pq.error?.status === 404 ? t("Chưa có hồ sơ cho phòng này.", "No profile for this room yet.") : pq.error?.message}</p>;
  const sec = (title, node) => node && <section className="grid gap-1"><h3 className="m-0 text-[12.5px] font-semibold">{title}</h3>{node}</section>;
  const list = (a) => Array.isArray(a) && a.length ? <ul className="m-0 pl-4 text-[12.5px] grid gap-1">{a.map((x, i) => <li key={i}>{show(x)}</li>)}</ul> : null;
  const labels = p.labels;
  const lw = Array.isArray(labels) ? labels : labels?.items;
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap"><b className="text-[14px]">{p.name || t("(chưa đặt tên)", "(unnamed)")}</b>{p.version != null && <Chip tone="accent">v{p.version}</Chip>}<span className="text-[12px] text-muted">{versions.length} {t("phiên bản", "versions")}</span></div>
      {sec(t("Luật & câu trả lời của chuyên gia", "Rules & expert answers"), p.answers && Object.keys(p.answers).length ? <KV obj={p.answers} /> : <p className="m-0 text-[12.5px] text-muted">{t("Chưa có. AI sẽ hỏi từng cụm nhỏ.", "Empty. The AI asks small groups of questions.")}</p>)}
      {sec(t("AI hiểu như sau", "What the AI understood"), pq.data?.understanding ? <KV obj={pq.data.understanding} /> : null)}
      {sec(t("Giả định", "Assumptions"), list(p.assumptions))}
      {sec(t("Câu hỏi còn mở", "Open questions"), list(p.open_questions))}
      {sec(t("Ví dụ đúng/sai (nhãn)", "Right/wrong examples (labels)"), Array.isArray(lw) && lw.length ? <ul className="m-0 pl-4 text-[12.5px] grid gap-1">{lw.slice(0, 20).map((l, i) => <li key={i}><Chip tone={l.verdict === "dung" ? "up" : l.verdict === "sai" ? "down" : "accent"}>{l.verdict}</Chip> {l.reason || l.example_id}</li>)}</ul> : null)}
      {sec(t("Người đóng góp", "Contributors"), Array.isArray(p.contributors) && p.contributors.length ? <p className="m-0 text-[12.5px]">{p.contributors.map((c) => (typeof c === "string" ? c : c.name || c.user_id)).join(", ")}</p> : null)}
      <section className="grid gap-2">
        <h3 className="m-0 text-[12.5px] font-semibold">{t("Phiên bản & so sánh (diff)", "Versions & diff")}</h3>
        {versions.length ? <ul className="m-0 p-0 list-none grid gap-1 text-[12.5px]">{versions.map((v) => <li key={v.version}><b>v{v.version}</b> <span className="text-muted">{hhmm(v.created_at)}{v.by ? ` · ${typeof v.by === "string" ? v.by : v.by.name || ""}` : ""}</span>{v.note ? ` — ${v.note}` : ""}</li>)}</ul> : <p className="m-0 text-[12.5px] text-muted">{t("Chưa lưu phiên bản nào. Bấm “Lưu phiên bản” hoặc nói “lưu lại”.", "No saved version yet. Press “Save version” or say “save it”.")}</p>}
        {versions.length > 1 && (
          <div className="flex gap-1 items-center flex-wrap">
            <select className="cr-inp cr-sel" value={va} onChange={(e) => setVa(e.target.value)} aria-label={t("Phiên bản A", "Version A")}><option value="">A</option>{versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
            <span aria-hidden="true">→</span>
            <select className="cr-inp cr-sel" value={vb} onChange={(e) => setVb(e.target.value)} aria-label={t("Phiên bản B", "Version B")}><option value="">B</option>{versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
          </div>
        )}
        {dq.data && ((dq.data.items || []).length ? <ul className="m-0 p-0 list-none grid gap-2">{dq.data.items.map((d, i) => <li key={i} className="cr-diff"><b className="text-[12px]">{d.title || d.section}</b> <Chip>{d.change}</Chip><div className="text-[12px] text-down">− {show(d.before)}</div><div className="text-[12px] text-up">+ {show(d.after)}</div></li>)}</ul> : <p className="m-0 text-[12.5px] text-muted">{t("Không có khác biệt.", "No differences.")}</p>)}
      </section>
      <section className="grid gap-2">
        <h3 className="m-0 text-[12.5px] font-semibold">{t("Xuất YAML kịch bản", "Export scenario YAML")}</h3>
        <div className="flex gap-1 flex-wrap">
          <button type="button" className="btn cr-sm" disabled={busy} onClick={() => doExport(false)}><FileText size={13} aria-hidden="true" />{t("Xuất & kiểm tra", "Export & validate")}</button>
          <button type="button" className="btn ghost cr-sm" disabled={busy || !ex?.ok} onClick={() => doExport(true)} title={t("Lưu vào Dạy kịch bản (chỉ khi hợp lệ)", "Save to Teach scenario (only if valid)")}>{t("Đăng ký vào Dạy kịch bản", "Register in Teach scenario")}</button>
          <a className="btn ghost cr-sm" href={`/api/v1/ai-trading/class/rooms/${R}/minutes.md`} download><Download size={13} aria-hidden="true" />{t("Biên bản (.md)", "Minutes (.md)")}</a>
          <button type="button" className="btn ghost cr-sm" onClick={() => window.print()}>{t("In / PDF", "Print / PDF")}</button>
        </div>
        {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
        {ex && (
          <div className="grid gap-1">
            <div className="flex gap-1 flex-wrap items-center"><Chip tone={ex.ok ? "up" : "down"}>{ex.ok ? t("Hợp lệ", "Valid") : t("Chưa hợp lệ", "Invalid")}</Chip>{ex.registered && <Chip tone="accent">{t("Đã đăng ký", "Registered")} {ex.scenario_id}</Chip>}{ex.yaml && <button type="button" className="btn ghost cr-sm" onClick={dl}>{t("Tải YAML", "Download YAML")}</button>}</div>
            {(ex.errors || []).map((e, i) => <p key={i} className="m-0 text-[12px] text-down">{show(e)}</p>)}
            {(ex.warnings || []).map((e, i) => <p key={i} className="m-0 text-[12px] text-muted">{show(e)}</p>)}
            {ex.yaml && <pre className="cr-pre"><code>{ex.yaml}</code></pre>}
          </div>
        )}
      </section>
    </div>
  );
}

export function PinsPanel({ pinned, onUnpin }) {
  const { t } = useCls();
  if (!pinned.length) return <p className="m-0 text-[13px] text-muted">{t("Chưa ghim tin nào. Dùng biểu tượng ghim trên mỗi tin.", "Nothing pinned. Use the pin icon on any message.")}</p>;
  return <ul className="m-0 p-0 list-none grid gap-2">{pinned.map((m) => <li key={m.id} className="cr-card"><div className="text-[11.5px] text-muted flex gap-2"><b>{m.author?.name}</b><span>{hhmm(m.created_at)}</span><button type="button" className="cr-link ml-auto" onClick={() => onUnpin(m)}>{t("Bỏ ghim", "Unpin")}</button></div><Markdown text={String(m.text || "").slice(0, 600)} /></li>)}</ul>;
}

/** Dự phòng cho tab Test khi <TestResultCard/> chưa có: hiện thẻ kết quả test gần nhất trong phòng (nếu có) + nút chạy test. */
export function TestFallback({ onSend, messages = [] }) {
  const { t } = useCls();
  const res = [...messages].reverse().filter((m) => m.kind === "result_card").slice(0, 3);
  return (
    <div className="grid gap-3">
      <div className="flex gap-2 items-center flex-wrap"><button type="button" className="btn" onClick={() => onSend("/test").catch(() => {})}>{t("Chạy test", "Run test")}</button><span className="text-[12px] text-muted">{t("Test paper trung thực (walk-forward). Cần xác nhận; không mở test khoá.", "Honest paper test (walk-forward). Needs confirmation; no locked test.")}</span></div>
      {!res.length && <p className="m-0 text-[13px] text-muted">{t("Chưa có kết quả test. Không có edge là kết quả bình thường; hãy làm rõ kịch bản và gắn nhãn ví dụ trước khi test.", "No test result yet. No edge is a normal outcome; clarify the scenario and label examples before testing.")}</p>}
      {res.map((m) => <ResultCard key={m.id} data={m.data} />)}
    </div>
  );
}
