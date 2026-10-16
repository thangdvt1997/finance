// Hiển thị tin nhắn AI Training Class: bong bóng, markdown, thẻ kết quả test (số thật + cảnh báo trung thực), thẻ quét ví dụ, chú thích, nhận định AI (Chấp nhận/Sửa/Phản bác).
import { useState } from "react";
import { AlertTriangle, Check, Lock, MapPin, MessageSquareWarning, Pencil, Pin, PinOff, X } from "lucide-react";
import { Chip, Stat, cn } from "../ui";
import Markdown from "./Markdown";
import { cpost, mediaUrl, cmdLabel } from "./classApi";
import SafeImg from "./SafeImg";
import { hhmm, num, pct, rr, show, useCls } from "./ctx";
import { kindLabel } from "./ExampleChart";
import TestResultCard from "./TestResultCard";
const ACT_NAME = { test: ["Chạy thử kịch bản", "Test the scenario"], quet: ["Tìm ví dụ trong lịch sử", "Find examples in history"], ve: ["Vẽ lên biểu đồ", "Draw on chart"], "bien-the": ["Tạo biến thể", "Create variants"], "doi-xung": ["Phiên bản phía mua", "Buy-side version"], "so-sanh": ["So sánh", "Compare"] };

const ROLE = { master: ["Master", "accent"], expert: ["Chuyên gia", "info"], ai: ["AI", ""] };
const VERDICT = { no_edge: ["Không có edge", "down"], unproven: ["Chưa chứng minh", ""], edge: ["Có edge (cần kiểm chứng)", "up"] };
const CONF = { cao: ["Cao", "up"], vua: ["Vừa", ""], "vừa": ["Vừa", ""], thap: ["Thấp", "down"], "thấp": ["Thấp", "down"], high: ["Cao", "up"], medium: ["Vừa", ""], low: ["Thấp", "down"] };
const toneT = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");

/** "AI hiểu như sau": khoá -> giá trị (+ độ chắc chắn nếu có). Hiển thị tổng quát, không giả định tên trường. */
export function Understanding({ data }) {
  const { t } = useCls();
  if (!data || typeof data !== "object") return null;
  const rows = Array.isArray(data) ? data.map((v, i) => [String(i + 1), v]) : Object.entries(data);
  if (!rows.length) return null;
  return (
    <div className="cr-und" role="group" aria-label={t("AI hiểu như sau", "AI understanding")}>
      <div className="text-[11.5px] font-semibold text-muted mb-1">{t("AI hiểu như sau", "What the AI understood")}</div>
      <dl className="m-0 grid gap-1">
        {rows.map(([k, v]) => {
          const conf = v && typeof v === "object" ? (v.confidence ?? v.certainty ?? v.do_chac_chan) : null;
          const val = v && typeof v === "object" && !Array.isArray(v) ? (v.value ?? v.text ?? v.summary ?? Object.fromEntries(Object.entries(v).filter(([a]) => !/confidence|certainty|do_chac_chan/.test(a)))) : v;
          const [cl, ct] = CONF[String(conf).toLowerCase()] || [];
          return <div key={k} className="cr-und-row"><dt>{k.replace(/_/g, " ")}</dt><dd>{Array.isArray(val) ? val.map(show).join("; ") : show(val)}{cl && <Chip tone={ct} className="ml-2">{t("Chắc chắn", "Certainty")}: {cl}</Chip>}</dd></div>;
        })}
      </dl>
    </div>
  );
}

function ReviewBar({ msg, onChanged }) {
  const { t, rid } = useCls();
  const [mode, setMode] = useState(null), [txt, setTxt] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState(null);
  const done = msg.review;
  const send = async (verdict, note, edit_text) => {
    setBusy(true); setErr(null);
    try { await cpost(`/rooms/${encodeURIComponent(rid)}/messages/${encodeURIComponent(msg.id)}/review`, { verdict, ...(note ? { note } : {}), ...(edit_text ? { edit_text } : {}) }); setMode(null); setTxt(""); onChanged?.(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const VL = { accept: t("Đã chấp nhận", "Accepted"), edit: t("Đã sửa", "Edited"), reject: t("Đã phản bác", "Rejected") };
  if (done?.verdict && !mode) return <div className="cr-review text-[12px] text-muted"><Chip tone={done.verdict === "accept" ? "up" : done.verdict === "reject" ? "down" : "accent"}>{VL[done.verdict] || done.verdict}</Chip>{done.by ? ` ${done.by}` : ""}{done.note ? ` — ${done.note}` : ""} <button type="button" className="cr-link" onClick={() => setMode("edit")}>{t("Đổi", "Change")}</button></div>;
  return (
    <div className="cr-review">
      <div className="flex gap-1 flex-wrap">
        <button type="button" className="btn ghost cr-sm" disabled={busy} onClick={() => send("accept")}><Check size={13} aria-hidden="true" />{t("Chấp nhận", "Accept")}</button>
        <button type="button" className={cn("btn cr-sm", mode !== "edit" && "ghost")} disabled={busy} onClick={() => setMode(mode === "edit" ? null : "edit")}><Pencil size={13} aria-hidden="true" />{t("Sửa", "Edit")}</button>
        <button type="button" className={cn("btn cr-sm", mode !== "reject" && "ghost")} disabled={busy} onClick={() => setMode(mode === "reject" ? null : "reject")}><MessageSquareWarning size={13} aria-hidden="true" />{t("Phản bác", "Dispute")}</button>
      </div>
      {mode && (
        <form className="grid gap-1 mt-2" onSubmit={(e) => { e.preventDefault(); if (mode === "edit" ? txt.trim() : true) send(mode === "edit" ? "edit" : "reject", mode === "reject" ? txt.trim() : undefined, mode === "edit" ? txt.trim() : undefined); }}>
          <textarea className="cr-inp" rows={2} maxLength={500} value={txt} onChange={(e) => setTxt(e.target.value)} aria-label={mode === "edit" ? t("Nội dung sửa", "Corrected text") : t("Lý do phản bác", "Reason")} placeholder={mode === "edit" ? t("Sửa lại cho đúng (≤500 ký tự)…", "Write the correction (≤500 chars)…") : t("Vì sao AI sai? (tuỳ chọn)", "Why is the AI wrong? (optional)")} />
          <div className="flex gap-1"><button type="submit" className="btn cr-sm" disabled={busy || (mode === "edit" && !txt.trim())}>{t("Gửi", "Send")}</button><button type="button" className="btn ghost cr-sm" onClick={() => setMode(null)}>{t("Huỷ", "Cancel")}</button></div>
        </form>
      )}
      {err && <p role="alert" className="m-0 mt-1 text-[12px] text-down">{err}</p>}
    </div>
  );
}

export function ResultCard({ data }) {
  const { t, rid, isMaster } = useCls();
  const m = data?.metrics || {}, [vl, vt] = VERDICT[data?.verdict] || [t("Chưa chứng minh", "Unproven"), ""];
  const [open, setOpen] = useState(false), [cf, setCf] = useState(""), [busy, setBusy] = useState(false), [res, setRes] = useState(null);
  const lock = async () => {
    setBusy(true); setRes(null);
    try { await cpost(`/rooms/${encodeURIComponent(rid)}/final-test`, { scenario_id: data.scenario_id, confirm: cf }); setRes({ ok: true }); }
    catch (e) { setRes({ err: e.message }); } finally { setBusy(false); }
  };
  const extra = Object.entries(m).filter(([k]) => !["expectancy_r", "p_vs_random", "trades"].includes(k) && (typeof m[k] === "number" || typeof m[k] === "string"));
  return (
    <section className="cr-card" aria-label={t("Kết quả test", "Test result")}>
      <div className="flex items-center gap-2 flex-wrap"><b className="text-[13px]">{t("Kết quả test (walk-forward dev, ngoài mẫu)", "Test result (walk-forward dev, out-of-sample)")}</b><Chip tone={vt}>{t(vl, vl)}</Chip>{data?.scenario_id && <code className="text-[11.5px] text-muted">{data.scenario_id}</code>}</div>
      <div className="grid grid-cols-3 gap-2 mt-2">
        <Stat label={t("Kỳ vọng", "Expectancy")} value={rr(m.expectancy_r)} tone={toneT(m.expectancy_r)} term={false} />
        <Stat label={t("p so với ngẫu nhiên", "p vs random")} value={m.p_vs_random == null ? "—" : num(m.p_vs_random, 3)} term={false} />
        <Stat label={t("Số lệnh", "Trades")} value={m.trades ?? "—"} term={false} />
      </div>
      {extra.length > 0 && <p className="m-0 mt-2 text-[12px] text-muted">{extra.slice(0, 8).map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "number" ? num(v, 3) : v}`).join(" · ")}</p>}
      {Array.isArray(data?.honesty) && data.honesty.length > 0 && <ul className="cr-honest m-0 mt-2 pl-4 grid gap-1 text-[12.5px]">{data.honesty.map((h, i) => <li key={i}><AlertTriangle size={12} className="inline mr-1 text-down" aria-hidden="true" />{show(h)}</li>)}</ul>}
      <p className="m-0 mt-2 text-[12px] text-muted">{data?.disclaimer || t("Kết quả không có edge hoặc chưa chứng minh là kết quả bình thường: đừng chỉnh luật theo test. Chỉ nghiên cứu/paper.", "No-edge or unproven is a normal outcome: do not tune rules on the test. Research/paper only.")}</p>
      {isMaster && data?.scenario_id && (
        <div className="mt-2">
          <button type="button" className="btn ghost cr-sm" onClick={() => setOpen(!open)} aria-expanded={open}><Lock size={13} aria-hidden="true" />{t("Mở test khoá (một lần)", "Open locked test (once)")}</button>
          {open && (
            <div className="grid gap-1 mt-2 cr-warnbox">
              <p className="m-0 text-[12px]">{t("Test khoá chỉ mở MỘT lần cho id này, không lặp lại, có ghi nhật ký; sau đó không được chỉnh luật theo kết quả. Gõ đúng id để xác nhận:", "The locked test opens ONLY ONCE for this id, is logged, and the rules must not be tuned afterwards. Type the exact id to confirm:")} <code>{data.scenario_id}</code></p>
              <div className="flex gap-1 flex-wrap"><input className="cr-inp" value={cf} onChange={(e) => setCf(e.target.value)} aria-label={t("Xác nhận id", "Confirm id")} /><button type="button" className="btn cr-sm" disabled={busy || cf !== data.scenario_id} onClick={lock}>{t("Mở test khoá", "Open locked test")}</button></div>
              {res?.ok && <p className="m-0 text-[12px] text-up">{t("Đã yêu cầu mở test khoá. Kết quả sẽ hiện trong phòng.", "Locked test requested. The result appears in the room.")}</p>}
              {res?.err && <p role="alert" className="m-0 text-[12px] text-down">{res.err}</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function ScanCard({ data, onLabel }) {
  const { t } = useCls();
  const ex = data?.examples || [];
  return (
    <section className="cr-card" aria-label={t("Ví dụ quét lịch sử", "Scanned examples")}>
      <div className="flex items-center gap-2 flex-wrap"><b className="text-[13px]">{t("Ví dụ quét lịch sử", "Scanned examples")}{data?.round != null ? ` — ${t("vòng", "round")} ${data.round}` : ""}</b><Chip>{ex.length} {t("ảnh", "images")}</Chip></div>
      <div className="cr-thumbs mt-2">{ex.slice(0, 10).map((e) => { const u = mediaUrl(e.image_url); return u ? <SafeImg key={e.id} src={u} alt={`${e.symbol || ""} ${e.tf || ""} ${e.ts || ""}`} loading="lazy" /> : null; })}</div>
      {data?.precision_hint != null && <p className="m-0 mt-2 text-[12px] text-muted">{show(data.precision_hint)}</p>}
      <button type="button" className="btn cr-sm mt-2" onClick={onLabel}>{t("Gắn nhãn ĐÚNG/SAI/GẦN ĐÚNG", "Label RIGHT/WRONG/CLOSE")}</button>
    </section>
  );
}

export function AnnotationCard({ data, text, onOpen }) {
  const { t, lang } = useCls();
  const d = data || {};
  return (
    <section className="cr-card" aria-label={t("Chú thích biểu đồ", "Chart annotation")}>
      <div className="flex items-center gap-2 flex-wrap"><MapPin size={14} aria-hidden="true" /><b className="text-[13px]">{kindLabel(d.kind, lang === "en") || t("Chú thích", "Annotation")}</b>{d.symbol && <Chip>{d.symbol}{d.tf ? ` ${d.tf}` : ""}</Chip>}</div>
      {d.note && <p className="m-0 mt-1 text-[12.5px]">{d.note}</p>}
      {!d.note && text && <div className="mt-1"><Markdown text={text} /></div>}
      {d.symbol && d.tf && <button type="button" className="btn ghost cr-sm mt-2" onClick={() => onOpen?.(d)}>{t("Mở trên biểu đồ", "Open on chart")}</button>}
    </section>
  );
}

export function ActionCard({ a, onConfirm, busy }) {
  const { t } = useCls();
  const ST = { needs_confirm: [t("Chờ xác nhận", "Needs confirmation"), "accent"], queued: [t("Xếp hàng", "Queued"), ""], running: [t("Đang chạy", "Running"), "info"], done: [t("Xong", "Done"), "up"], failed: [t("Lỗi", "Failed"), "down"], cancelled: [t("Đã huỷ", "Cancelled"), ""] };
  const [l, tn] = ST[a.status] || [a.status, ""];
  return (
    <div className="cr-act" role="status">
      <div className="flex items-center gap-2 flex-wrap"><b className="text-[12.5px]">{t(...(ACT_NAME[a.command] || [a.command, a.command]))}</b><Chip tone={tn}>{l}</Chip>{a.progress != null && a.status === "running" && <span className="text-[12px] text-muted">{typeof a.progress === "number" ? pct(a.progress) : show(a.progress)}</span>}</div>
      {a.summary && <p className="m-0 mt-1 text-[12px] text-muted">{show(a.summary)}</p>}
      {a.message && a.status !== "done" && <p className="m-0 mt-1 text-[12px] text-muted">{a.message}</p>}
      {a.status === "needs_confirm" && <button type="button" className="btn cr-sm mt-1" disabled={busy} onClick={() => onConfirm(a)}>{t("Xác nhận chạy (chỉ nghiên cứu/paper)", "Confirm run (research/paper only)")}</button>}
    </div>
  );
}

export default function Bubble({ msg, onSend, onFill, onPin, onChanged, goLabel, openChart, mine }) {
  const { t, lang, me, rid } = useCls();
  const a = msg.author || {}, isAi = a.role === "ai" || a.user_id === "ai";
  const [rl, rt] = ROLE[a.role] || [a.role || "", ""];
  if (msg.kind === "system") return <div className="cr-sys" role="note"><Markdown text={msg.text} /></div>;
  const atts = msg.attachments || [];
  return (
    <article className={cn("cr-msg", mine && "mine", isAi && "ai")} aria-label={`${a.name || ""}, ${hhmm(msg.created_at)}`} data-seq={msg.seq}>
      <header className="cr-msg-h">
        <b>{a.name || (isAi ? t("AI học trò", "AI student") : "?")}</b>{rl && <Chip tone={rt}>{lang === "en" ? ({ Master: "Master", "Chuyên gia": "Expert", AI: "AI" })[rl] : rl}</Chip>}
        <span className="text-faint text-[11px]">{hhmm(msg.created_at)}</span>
        {msg.id && !String(msg.id).startsWith("local-") && <button type="button" className="cr-iconbtn ml-auto" onClick={() => onPin?.(msg)} aria-label={msg.pinned ? t("Bỏ ghim", "Unpin") : t("Ghim", "Pin")} title={msg.pinned ? t("Bỏ ghim", "Unpin") : t("Ghim", "Pin")}>{msg.pinned ? <PinOff size={13} /> : <Pin size={13} />}</button>}
      </header>
      {msg.kind === "result_card" ? <><TestResultCard lang={lang} result={msg.data} role={me?.role} rid={rid} onSend={onSend} onEdit={() => onFill?.(t("Tôi muốn sửa kịch bản: ", "I want to change the scenario: "))} />{msg.text && <Markdown text={msg.text} />}</>
        : msg.kind === "scan" ? <><ScanCard data={msg.data} onLabel={goLabel} />{msg.text && <Markdown text={msg.text} />}</>
        : msg.kind === "annotation" ? <AnnotationCard data={msg.data} text={msg.text} onOpen={openChart} />
        : <Markdown text={(!isAi && cmdLabel(msg.text, lang === "en")) || msg.text} />}
      {atts.length > 0 && (
        <div className="cr-atts">
          {atts.map((x) => x.kind === "image" && mediaUrl(x.url)
            ? <figure key={x.id} className="m-0"><SafeImg src={mediaUrl(x.url)} alt={x.note || x.name} loading="lazy" className="cr-img" /><figcaption className="text-[11.5px] text-muted">{x.name}{x.note ? ` — ${x.note}` : ""}</figcaption></figure>
            : <a key={x.id} className="cr-file" href={mediaUrl(x.url) || undefined} target="_blank" rel="noopener noreferrer" download={x.name}>{x.kind.toUpperCase()} · {x.name} {x.size ? `(${Math.ceil(x.size / 1024)} KB)` : ""}</a>)}
        </div>
      )}
      {msg.understanding && <Understanding data={msg.understanding} />}
      {isAi && msg.id && (msg.kind === "text" || msg.kind === "review") && !String(msg.id).startsWith("local-") && <ReviewBar msg={msg} onChanged={onChanged} />}
    </article>
  );
}
