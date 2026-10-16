// "Hồ sơ kịch bản" (canvas): 16 hàng cố định, cập nhật thời gian thực theo hội thoại. Mỗi hàng: tên | AI hiểu (sửa trực tiếp) | độ chắc chắn | nguồn | Xác nhận / Sửa / Hỏi lại.
// Dữ liệu: GET /class/rooms/{rid}/canvas (nếu máy chủ có) hoặc tính phía client từ /profile. Xác nhận/sửa: POST canvas/{key}/confirm|edit; nếu API chưa có -> lưu cục bộ + (với Sửa) gửi vào chat để AI cập nhật.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleHelp, Pencil, RotateCcw, Undo2, X } from "lucide-react";
import { Chip, cn } from "../ui";
import { cget, cpost } from "./classApi";
import { hhmm, show } from "./ctx";
import { CONF, buildCanvas, wordDiff } from "./canvasModel";

const lsKey = (rid) => `cr-canvas-${rid}`;
const readLocal = (rid) => { try { return JSON.parse(localStorage.getItem(lsKey(rid)) || "{}"); } catch { return {}; } };

/** Hook dùng chung (TopBar + ProfileCanvas + slot): trả {profile, versions, canvas, confirm, edit, revert, loading, error}. */
export function useCanvas(rid, lang = "vi", onSend) {
  const qc = useQueryClient();
  const R = encodeURIComponent(rid || "");
  const pq = useQuery({ queryKey: ["cls", rid, "profile"], enabled: !!rid, queryFn: ({ signal }) => cget(`/rooms/${R}/profile`, {}, signal), refetchInterval: 8000, retry: false });
  const cq = useQuery({ queryKey: ["cls", rid, "canvas"], enabled: !!rid, queryFn: ({ signal }) => cget(`/rooms/${R}/canvas`, {}, signal), refetchInterval: 8000, retry: false });
  const [local, setLocal] = useState(() => readLocal(rid));
  useEffect(() => { setLocal(readLocal(rid)); }, [rid]);
  const save = (n) => { setLocal(n); try { localStorage.setItem(lsKey(rid), JSON.stringify(n)); } catch { /* bỏ */ } };
  const apiCanvas = cq.isSuccess ? cq.data : null;
  const canvas = useMemo(() => buildCanvas({ profile: pq.data?.profile, understanding: pq.data?.understanding, apiCanvas, local, lang }), [pq.data, apiCanvas, local, lang]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["cls", rid, "canvas"] }); qc.invalidateQueries({ queryKey: ["cls", rid, "profile"] }); };
  const confirm = useCallback(async (row, on = true) => {
    save({ ...local, confirmed: { ...local.confirmed, [row.key]: on } });
    try { if (apiCanvas) { await cpost(`/rooms/${R}/canvas/${encodeURIComponent(row.key)}/confirm`, { confirmed: on }); refresh(); } } catch { /* giữ cục bộ */ }
  }, [local, rid, apiCanvas]); // eslint-disable-line react-hooks/exhaustive-deps
  const edit = useCallback(async (row, text) => {
    let viaApi = false;
    try { if (apiCanvas) { await cpost(`/rooms/${R}/canvas/${encodeURIComponent(row.key)}/edit`, { text }); viaApi = true; refresh(); } } catch { /* rơi xuống chat */ }
    save({ ...local, edits: { ...local.edits, ...(viaApi ? {} : { [row.key]: text }) }, confirmed: { ...local.confirmed, [row.key]: true } });
    if (!viaApi && onSend) { try { await onSend(`${lang === "en" ? "Correction for" : "Sửa mục"} «${row.label}»: ${text}`); } catch { /* lỗi hiện ở khung chat */ } }
  }, [local, rid, apiCanvas, onSend, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const revert = useCallback((row) => { const e = { ...local.edits }; delete e[row.key]; save({ ...local, edits: e }); }, [local, rid]); // eslint-disable-line react-hooks/exhaustive-deps
  return { profile: pq.data?.profile, versions: pq.data?.versions || [], canvas, confirm, edit, revert, loading: pq.isPending, error: pq.isError && pq.error?.status !== 404 ? pq.error : null, serverCanvas: !!apiCanvas };
}

function ConfBadge({ c, t, lang }) {
  if (!c) return <span className="cr-conf none" title={t("Chưa có nội dung", "No content yet")}>—</span>;
  const [vi, en, tone, ic] = CONF[c];
  return <span className={cn("cr-conf", tone)} title={t("Độ chắc chắn AI hiểu đúng", "How sure the AI understood")}><span aria-hidden="true">{ic}</span>{lang === "en" ? en : vi}</span>;
}

function Diff({ a, b, t }) {
  const parts = useMemo(() => wordDiff(a, b), [a, b]);
  return <p className="cr-wdiff m-0" aria-label={t("So sánh bản AI hiểu và bản bạn sửa", "AI version vs your edit")}>{parts.map((p, i) => p.t === "=" ? <span key={i}>{p.s}</span> : p.t === "+" ? <ins key={i}>{p.s}</ins> : <del key={i}>{p.s}</del>)}</p>;
}

function Row({ r, t, lang, focus, onConfirm, onEdit, onRevert, onAsk }) {
  const [editing, setEditing] = useState(false), [draft, setDraft] = useState(r.value), [busy, setBusy] = useState(false), [more, setMore] = useState(false);
  const ref = useRef(null), ta = useRef(null);
  useEffect(() => { if (focus) { ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); ref.current?.focus({ preventScroll: true }); } }, [focus]);
  useEffect(() => { if (!editing) setDraft(r.value); }, [r.value, editing]);
  useEffect(() => { if (editing) ta.current?.focus(); }, [editing]);
  const submit = async () => { const v = draft.trim(); if (!v || v === r.value) { setEditing(false); return; } setBusy(true); try { await onEdit(r, v); } finally { setBusy(false); setEditing(false); } };
  const long = r.value.length > 180;
  const sid = `cr-row-${r.key}`;
  return (
    <li ref={ref} tabIndex={-1} className={cn("cr-crow", r.confirmed && "ok", !r.filled && "empty", focus && "focus")} aria-labelledby={`${sid}-n`}>
      <div className="cr-crow-h">
        <span className="cr-crow-i num" aria-hidden="true">{r.i + 1}</span>
        <b id={`${sid}-n`} className="text-[12.5px] min-w-0">{r.label}</b>
        <span className="ml-auto flex items-center gap-1 shrink-0">
          {r.confirmed && <span className="cr-conf up" title={t("Đã xác nhận", "Confirmed")}><Check size={11} aria-hidden="true" />{t("Đã xác nhận", "Confirmed")}</span>}
          <ConfBadge c={r.confidence} t={t} lang={lang} />
        </span>
      </div>
      {editing ? (
        <div className="grid gap-1">
          <textarea ref={ta} className="cr-inp cr-edit" rows={3} value={draft} maxLength={1200} onChange={(e) => setDraft(e.target.value)} aria-label={`${t("Sửa", "Edit")}: ${r.label}`}
            onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setEditing(false); } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); } }} />
          {draft.trim() && draft.trim() !== r.value && r.value && <Diff a={r.value} b={draft.trim()} t={t} />}
          <div className="flex gap-1 flex-wrap items-center">
            <button type="button" className="btn cr-rb" onClick={submit} disabled={busy || !draft.trim()}><Check size={13} aria-hidden="true" />{t("Lưu & xác nhận", "Save & confirm")}</button>
            <button type="button" className="btn ghost cr-rb" onClick={() => setEditing(false)}><X size={13} aria-hidden="true" />{t("Huỷ", "Cancel")}</button>
            <span className="text-[11px] text-muted">Ctrl+Enter {t("lưu", "save")} · Esc {t("huỷ", "cancel")}</span>
          </div>
        </div>
      ) : r.filled ? (
        <>
          <p className={cn("cr-crow-v m-0", !more && long && "clamp")}>{r.value}</p>
          {long && <button type="button" className="cr-link text-[11.5px] justify-self-start" aria-expanded={more} onClick={() => setMore(!more)}>{more ? t("Thu gọn", "Show less") : t("Xem thêm", "Show more")}</button>}
          {r.ai && r.ai !== r.value && <p className="cr-ai m-0 text-[12px] text-muted"><b>{t("AI hiểu", "AI reads it as")}:</b> {r.ai}</p>}
          {r.edited && <div className="cr-edited"><span className="text-[11px] text-muted">{t("Bạn đã sửa — so với bản AI hiểu:", "You edited — vs the AI's version:")}</span>{r.original ? <Diff a={r.original} b={r.value} t={t} /> : null}<button type="button" className="cr-link text-[11.5px]" onClick={() => onRevert(r)}><Undo2 size={11} aria-hidden="true" className="inline mr-1" />{t("Hoàn tác", "Undo")}</button></div>}
        </>
      ) : <p className="cr-crow-v m-0 text-muted">{t("Chưa có. AI sẽ điền khi bạn trả lời, hoặc bấm Sửa để tự viết.", "Nothing yet. The AI fills this as you answer, or click Edit to write it.")}</p>}
      {!editing && (
        <div className="cr-crow-f">
          <span className="cr-src text-[11px] text-muted truncate" title={r.source}>{r.source ? `${t("Nguồn", "Source")}: ${r.source}${r.turn != null ? ` · ${t("lượt", "turn")} ${r.turn}` : ""}` : ""}</span>
          <span className="flex gap-1 ml-auto shrink-0">
            {r.filled && <button type="button" className={cn("btn cr-rb", r.confirmed ? "ghost" : "")} aria-pressed={r.confirmed} onClick={() => onConfirm(r, !r.confirmed)}><Check size={13} aria-hidden="true" /><span>{r.confirmed ? t("Bỏ xác nhận", "Unconfirm") : t("Xác nhận", "Confirm")}</span></button>}
            {!r.readonly && <button type="button" className="btn ghost cr-rb" onClick={() => setEditing(true)} aria-label={`${t("Sửa", "Edit")}: ${r.label}`}><Pencil size={13} aria-hidden="true" /><span>{t("Sửa", "Edit")}</span></button>}
            <button type="button" className="btn ghost cr-rb" onClick={() => onAsk(r)} aria-label={`${t("Hỏi lại", "Ask again")}: ${r.label}`}><CircleHelp size={13} aria-hidden="true" /><span>{t("Hỏi lại", "Ask again")}</span></button>
          </span>
        </div>
      )}
    </li>
  );
}

function Versions({ rid, versions, t }) {
  const [va, setVa] = useState(""), [vb, setVb] = useState("");
  const R = encodeURIComponent(rid);
  const dq = useQuery({ queryKey: ["cls", rid, "diff", va, vb], enabled: !!va && !!vb && va !== vb, queryFn: ({ signal }) => cget(`/rooms/${R}/profile/diff`, { a: va, b: vb }, signal) });
  return (
    <details className="cr-vers">
      <summary>{t("Lịch sử phiên bản & so sánh", "Version history & compare")} ({versions.length})</summary>
      {versions.length ? <ul className="m-0 mt-1 p-0 list-none grid gap-1 text-[12.5px]">{versions.map((v) => <li key={v.version}><b>v{v.version}</b> <span className="text-muted">{hhmm(v.created_at)}{v.by ? ` · ${typeof v.by === "string" ? v.by : v.by.name || ""}` : ""}</span>{v.note ? ` — ${v.note}` : ""}</li>)}</ul> : <p className="m-0 mt-1 text-[12.5px] text-muted">{t("Chưa lưu phiên bản nào. Bấm “Lưu phiên bản” ở thanh trên.", "No saved version yet. Use “Save version” in the top bar.")}</p>}
      {versions.length > 1 && (
        <div className="flex gap-1 items-center flex-wrap mt-2">
          <select className="cr-inp cr-sel" value={va} onChange={(e) => setVa(e.target.value)} aria-label={t("Phiên bản A", "Version A")}><option value="">A</option>{versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
          <span aria-hidden="true">→</span>
          <select className="cr-inp cr-sel" value={vb} onChange={(e) => setVb(e.target.value)} aria-label={t("Phiên bản B", "Version B")}><option value="">B</option>{versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
        </div>
      )}
      {dq.data && ((dq.data.items || []).length
        ? <ul className="m-0 mt-2 p-0 list-none grid gap-2">{dq.data.items.map((d, i) => <li key={i} className="cr-diff"><b className="text-[12px]">{d.title || d.section}</b> <Chip>{d.change}</Chip><Diff a={show(d.before) === "—" ? "" : show(d.before)} b={show(d.after) === "—" ? "" : show(d.after)} t={t} /></li>)}</ul>
        : <p className="m-0 mt-2 text-[12.5px] text-muted">{t("Không có khác biệt.", "No differences.")}</p>)}
    </details>
  );
}

/** Props: {lang, rid, profile, canvas, onClose, onSend(text), model, focusKey, onFill(text)}; model = kết quả useCanvas(). */
export default function ProfileCanvas({ lang = "vi", rid, canvas, model, onSend, onClose, focusKey, onFill, title }) {
  const t = (vi, en) => (lang === "en" ? en : vi);
  const [only, setOnly] = useState(false);
  const rows = (canvas || model?.canvas)?.rows || [];
  const shown = only ? rows.filter((r) => !r.confirmed || r.score < 100) : rows;
  const ask = (r) => onSend?.(lang === "en" ? `Ask me again about «${r.label}» with specific numbers.` : `Hỏi lại tôi về «${r.label}», cần con số cụ thể.`);
  const none = rows.length > 0 && !rows.some((r) => r.filled);
  return (
    <section className="cr-canvas" aria-label={title || t("Hồ sơ kịch bản", "Scenario profile")} data-tour="profile">
      <header className="cr-canvas-h">
        <h3 className="m-0 text-[13px] font-semibold">{title || t("Hồ sơ kịch bản", "Scenario profile")}</h3>
        <span className="text-[11.5px] text-muted">{t("AI hiểu như sau — sửa trực tiếp được", "What the AI understood — editable")}</span>
        <label className="cr-only ml-auto inline-flex items-center gap-1 text-[12px] cursor-pointer"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} />{t("Chỉ hàng chưa rõ", "Unclear rows only")}</label>
        {onClose && <button type="button" className="cr-iconbtn" onClick={onClose} aria-label={t("Đóng hồ sơ", "Close profile")}><X size={14} /></button>}
      </header>
      <p className="cr-legend m-0" aria-label={t("Chú giải độ chắc chắn", "Certainty legend")}>
        {t("Độ chắc chắn", "Certainty")}: <span className="cr-conf up">▲ {t("Cao", "High")}</span> <span className="cr-conf accent">◆ {t("Vừa", "Medium")}</span> <span className="cr-conf down">▼ {t("Thấp", "Low")}</span>
      </p>
      {(canvas || model?.canvas)?.clarity?.next && <p className="cr-next m-0 text-[12.5px]" role="note"><b>{t("Câu AI nên hỏi tiếp", "Next question for the AI")}:</b> {(canvas || model?.canvas).clarity.next}</p>}
      {model?.error && <p role="alert" className="m-0 text-[12.5px] text-down">{model.error.message}</p>}
      {none && (
        <div className="cr-empty-canvas" role="note">
          <b className="text-[13px]">{t("Hãy mô tả kịch bản bằng 3 câu", "Describe the scenario in 3 sentences")}</b>
          <p className="m-0 text-[12.5px] text-muted">{t("Bảng này tự điền khi bạn chat. Ví dụ mở đầu:", "This table fills itself as you chat. Example openers:")}</p>
          <ul className="m-0 p-0 list-none grid gap-1">{EXAMPLES.map(([vi, en], i) => <li key={i}><button type="button" className="cr-chip cr-chip-wide" onClick={() => onFill?.(lang === "en" ? en : vi)}>{lang === "en" ? en : vi}</button></li>)}</ul>
        </div>
      )}
      <ol className="cr-crows m-0 p-0 list-none">
        {shown.map((r) => <Row key={r.key} r={r} t={t} lang={lang} focus={focusKey === r.key} onConfirm={(row, on) => model?.confirm(row, on)} onEdit={(row, v) => model?.edit(row, v)} onRevert={(row) => model?.revert(row)} onAsk={ask} />)}
      </ol>
      {only && !shown.length && <p className="m-0 text-[12.5px] text-up">{t("Mọi hàng đã rõ và được xác nhận.", "Every row is clear and confirmed.")}</p>}
      {rid && <Versions rid={rid} versions={model?.versions || []} t={t} />}
      <p className="m-0 text-[11px] text-muted"><RotateCcw size={10} aria-hidden="true" className="inline mr-1" />{model?.serverCanvas ? t("Đồng bộ với máy chủ.", "Synced with the server.") : t("Xác nhận lưu trên trình duyệt này; Sửa còn được gửi vào chat để AI cập nhật.", "Confirmations are stored in this browser; an Edit is also sent to the chat so the AI updates.")}</p>
    </section>
  );
}

export const EXAMPLES = [
  ["EURUSD H1: giá lập 3 đỉnh thấp dần trong vùng đi ngang, rồi nến thân nhỏ nén lại; vào Sell khi nến đóng cửa dưới đáy nến nén.", "EURUSD H1: price makes 3 lower highs inside a range, then small-body candles compress; Sell when a candle closes below the compression low."],
  ["XAUUSD M15: sau nhịp tăng 2 ATR, hồi không quá 50% rồi phá đáy nhịp hồi thì Sell, SL trên đỉnh 6 nến + 0,25 ATR.", "XAUUSD M15: after a 2 ATR rise, a pullback under 50% then a break of its low is a Sell; SL above the 6-bar high + 0.25 ATR."],
  ["BTCUSDT H4: giá chạm vùng cung đã bị từ chối 2 lần, nến đảo chiều đóng cửa trong vùng thì Sell, TP 2R.", "BTCUSDT H4: price hits a supply zone rejected twice, a reversal candle closes inside it, Sell, TP 2R."],
];
