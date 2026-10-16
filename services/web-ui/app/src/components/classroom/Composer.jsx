// Ô nhập của AI Training Class: nhận ý định tự nhiên (AI hiểu ý + thẻ xác nhận + option gợi ý bấm được; không có lệnh "/"), chip dự phòng, dán/kéo ảnh, đính kèm YAML/CSV/PDF/ghi chú, lưu nháp, phím tắt.
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ChartCandlestick, Paperclip, Send, Square, X } from "lucide-react";
import { cn } from "../ui";
import { KIND_BY_EXT, LIMIT } from "./classApi";
import { optFeedback, understand } from "./intentApi";
import IntentPanel from "./IntentPanel";
import { useCls } from "./ctx";

const dkey = (rid) => `cr-draft-${rid}`;
const readDraft = (rid) => { try { return localStorage.getItem(dkey(rid)) || ""; } catch { return ""; } };

const Composer = forwardRef(function Composer({ chips, streaming, onSend, onStop, onUpload, onChart, onUi, ask, disabled }, ref) {
  const { t, rid } = useCls();
  const [text, setText] = useState(() => readDraft(rid)), [files, setFiles] = useState([]), [err, setErr] = useState(null), [busy, setBusy] = useState(false), [drag, setDrag] = useState(false);
  const ta = useRef(null), fi = useRef(null);
  useImperativeHandle(ref, () => ({ focus: () => ta.current?.focus(), insert: (s) => { setText(s); ta.current?.focus(); } }));
  useEffect(() => { setText(readDraft(rid)); setFiles([]); setErr(null); }, [rid]);
  useEffect(() => { const h = setTimeout(() => { try { text ? localStorage.setItem(dkey(rid), text) : localStorage.removeItem(dkey(rid)); } catch { /* bỏ */ } }, 400); return () => clearTimeout(h); }, [text, rid]);
  useEffect(() => { const el = ta.current; if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 180)}px`; } }, [text]);

  // --- nhận ý định tự nhiên: option gợi ý sau mỗi lượt AI, "AI hiểu ý bạn là", thẻ xác nhận (việc nặng không tự chạy) ---
  const [und, setUnd] = useState(null), [opts, setOpts] = useState([]), [card, setCard] = useState(null), [tick, setTick] = useState(0);
  const plain = useRef(false);
  useEffect(() => { setUnd(null); setCard(null); setOpts([]); }, [rid]);
  useEffect(() => {
    if (!rid || String(rid).startsWith("m:") || streaming) return undefined;   // phòng phương pháp (rid ảo "m:<id>") không có route understand
    let dead = false;
    understand(rid, "").then((r) => { if (!dead && r?.options) setOpts(r.options); });
    return () => { dead = true; };
  }, [rid, streaming, tick]);
  const goUi = (u) => { if (u === "chart") onChart?.(); else onUi?.(u); };
  const runCmd = async (cmd, clear = true) => {
    if (!cmd || busy || streaming || disabled) return;
    setCard(null); setErr(null);
    try { setBusy(true); if (clear) { setText(""); try { localStorage.removeItem(dkey(rid)); } catch { /* bỏ */ } } await onSend(cmd); setTick((n) => n + 1); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const pickOpt = (o) => {
    optFeedback(rid, o.id, "clicked", o.kind);
    if (o.confirm_card) { setCard(o.confirm_card); return; }
    if (o.ui) { goUi(o.ui); return; }
    if (o.command_text && o.send) { runCmd(o.command_text, false); return; }
    if (o.fill != null) { if (o.fill) setText(o.fill); ta.current?.focus(); }
  };
  const pickAlt = (a) => {                       // chọn lại ý định (không phải ý này / ý yếu): việc nặng vẫn qua thẻ xác nhận
    if (und?.id) optFeedback(rid, `${und.id}:intent:${a.key}`, "clicked");
    if (a.ui) { goUi(a.ui); return; }
    if (!a.command_text) return;
    if (a.heavy) { const l = (a.label_vi || "").toLowerCase(), e = (a.label_en || "").toLowerCase(); setCard({ id: `alt-${a.key}`, question_vi: `Bạn muốn mình ${l} chứ?`, question_en: `Do you want me to ${e}?`, buttons: [{ id: "run", label_vi: "Làm luôn", label_en: "Do it", command_text: a.command_text }, { id: "no", label_vi: "Không", label_en: "No" }] }); return; }
    runCmd(a.command_text);
  };
  const cardNo = () => { if (und?.intent && und?.id) optFeedback(rid, `${und.id}:intent:${und.intent.key}`, "not_this"); setCard(null); ta.current?.focus(); };
  const sendPlain = () => { setCard(null); plain.current = true; submit().finally(() => { plain.current = false; }); };

  const addFiles = (list) => {
    setErr(null); const out = [];
    for (const f of Array.from(list)) {
      const ext = (f.name.split(".").pop() || (f.type.startsWith("image/") ? "png" : "")).toLowerCase(); const kind = KIND_BY_EXT[ext] || (f.type.startsWith("image/") ? "image" : null);
      if (!kind || kind === "note" && f.size > 20000) { setErr(t(`Không hỗ trợ tệp ${f.name} (nhận ảnh png/jpg/webp, YAML, CSV, PDF, ghi chú .txt/.md).`, `Unsupported file ${f.name} (png/jpg/webp, YAML, CSV, PDF, .txt/.md notes).`)); continue; }
      if (kind !== "note" && f.size > LIMIT[kind]) { setErr(t(`${f.name} quá lớn (tối đa ${Math.round(LIMIT[kind] / 1024)} KB).`, `${f.name} is too large (max ${Math.round(LIMIT[kind] / 1024)} KB).`)); continue; }
      out.push({ file: f, kind, caption: "", url: null });
      if (kind === "image") { const fr = new FileReader(); fr.onload = () => setFiles((a) => a.map((y) => (y.file === f ? { ...y, url: String(fr.result) } : y))); fr.readAsDataURL(f); }   // data: URL (CSP img-src chỉ cho 'self' data:, không cho blob:)
    }
    setFiles((a) => [...a, ...out].slice(0, 5));
  };
  const rm = (i) => setFiles((a) => { const x = a[i]; if (x?.url) URL.revokeObjectURL(x.url); return a.filter((_, j) => j !== i); });

  const submit = async (override) => {
    const msg = (override ?? text).trim();
    if (busy || streaming || disabled || (!msg && !files.length)) return;
    setErr(null);
    try {
      setBusy(true);
      if (msg && override == null && !files.length && !plain.current && !msg.startsWith("/") && !String(rid || "").startsWith("m:")) {
        const u = await understand(rid, msg);      // lỗi/ quá hạn -> null: vẫn gửi như chat thường
        const it = u?.intent;
        setUnd(u && (it || u.injected) ? u : null); setCard(null);
        if (it?.level === "strong" && it.heavy && u.confirm_card) { setCard(u.confirm_card); return; }     // việc nặng: hỏi xác nhận, KHÔNG tự chạy
        if (it?.level === "strong" && it.auto_run) {
          setText(""); try { localStorage.removeItem(dkey(rid)); } catch { /* bỏ */ }
          optFeedback(rid, `${u.id}:intent:${it.key}`, "clicked");
          if (it.command_text) await onSend(it.command_text); else goUi(it.ui);
          setTick((n) => n + 1); return;
        }
        for (const o of opts.slice(0, 4)) optFeedback(rid, o.id, "ignored", o.kind);      // gõ tự do: các gợi ý trước đó coi như bỏ qua
      }
      if (files.length) { await onUpload(files); files.forEach((x) => x.url && URL.revokeObjectURL(x.url)); setFiles([]); }
      if (msg) { if (override == null) { setText(""); try { localStorage.removeItem(dkey(rid)); } catch { /* bỏ */ } } await onSend(msg); setTick((n) => n + 1); }
    } catch (e) { if (override == null && msg) setText((x) => x || msg); setErr(e.message); } finally { setBusy(false); }
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
    else if (e.key === "Escape" && streaming) onStop();
  };
  const onPaste = (e) => { const fs = Array.from(e.clipboardData?.files || []).filter((f) => f.type.startsWith("image/")); if (fs.length) { e.preventDefault(); addFiles(fs); } };
  const chipClick = (c) => { const cmd = c.command || c.text || c.label; if (!cmd) return; if (c.command) submit(String(c.command).startsWith("/") ? c.command : `/${c.command}`); else submit(c.text); };

  return (
    <div className={cn("cr-composer", drag && "drag")} onDragOver={(e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); setDrag(true); } }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}>
      <IntentPanel und={und} opts={opts} card={card} busy={busy || streaming || disabled} onOption={pickOpt} onRun={(c) => runCmd(c)} onNo={cardNo} onPlain={sendPlain} onAlt={pickAlt}
        onNotThis={() => { if (und?.id && und?.intent) optFeedback(rid, `${und.id}:intent:${und.intent.key}`, "not_this"); }} />
      {!opts.length && !card && chips?.length > 0 && <div className="cr-chips" role="group" aria-label={t("Gợi ý nhanh", "Quick suggestions")}>{chips.slice(0, 8).map((c, i) => <button key={`${c.label}${i}`} type="button" className="cr-chip" disabled={streaming || busy || disabled} onClick={() => chipClick(c)}>{c.label}</button>)}</div>}
      {files.length > 0 && (
        <ul className="cr-tray m-0 p-0 list-none">
          {files.map((x, i) => (
            <li key={i} className="cr-tray-i">
              {x.url ? <img src={x.url} alt="" /> : <span className="cr-fileico">{x.kind.toUpperCase()}</span>}
              <div className="min-w-0 flex-1 grid gap-1"><span className="text-[12px] truncate">{x.file.name}</span><input className="cr-inp" maxLength={300} value={x.caption} onChange={(e) => setFiles((a) => a.map((y, j) => (j === i ? { ...y, caption: e.target.value } : y)))} placeholder={x.kind === "image" ? t("Chú thích ảnh (bắt buộc để AI hiểu)", "Image caption (needed for the AI)") : t("Ghi chú (tuỳ chọn)", "Note (optional)")} aria-label={t("Chú thích", "Caption")} /></div>
              <button type="button" className="cr-iconbtn" onClick={() => rm(i)} aria-label={t("Bỏ tệp", "Remove file")}><X size={14} /></button>
            </li>
          ))}
        </ul>
      )}
      <div className="cr-row">
        <button type="button" className="cr-iconbtn big" onClick={() => fi.current?.click()} aria-label={t("Đính kèm tệp", "Attach file")} title={t("Đính kèm: ảnh, YAML, CSV, PDF, ghi chú", "Attach: image, YAML, CSV, PDF, note")}><Paperclip size={17} /></button>
        <button type="button" className="cr-iconbtn big" onClick={onChart} aria-label={t("Chọn ví dụ trên biểu đồ", "Pick example on chart")} title={t("Chọn ví dụ trên biểu đồ", "Pick example on chart")}><ChartCandlestick size={17} /></button>
        <input ref={fi} type="file" hidden multiple accept="image/png,image/jpeg,image/webp,.yaml,.yml,.csv,.pdf,.txt,.md" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
        <textarea ref={ta} className="cr-ta" rows={1} value={text} maxLength={1500} disabled={disabled} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste}
          placeholder={ask ? t("Trả lời AI bằng lời bình thường, càng cụ thể (có số) càng tốt…", "Answer the AI in plain words, the more specific (numbers) the better…") : t("Nói điều bạn muốn: chạy thử, tìm ví dụ, tóm tắt…", "Say what you want: test it, find examples, sum up…")} aria-label={t("Tin nhắn", "Message")} />
        {streaming
          ? <button type="button" className="btn cr-send" onClick={onStop} aria-label={t("Dừng", "Stop")}><Square size={15} /></button>
          : <button type="button" className="btn cr-send" onClick={() => submit()} disabled={busy || disabled || (!text.trim() && !files.length)} aria-label={t("Gửi", "Send")}><Send size={15} /></button>}
      </div>
      <div className="cr-foot"><span>{text.length}/1500</span><span className="hidden sm:inline">Enter {t("gửi", "send")} · Shift+Enter {t("xuống dòng", "newline")} · Ctrl+K {t("tìm", "search")}</span></div>
      {err && <p role="alert" className="m-0 text-[12.5px] text-down">{err}</p>}
    </div>
  );
});
export default Composer;
