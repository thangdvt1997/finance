import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { apiWrite } from "../lib/api";
import { Notice } from "./ui";
import { t } from "../lib/i18n";

const TAG_RE = /^[a-z0-9_:.\- ]{1,32}$/;

/** Ghi chú/tag/đánh giá cho một lệnh, ngày hoặc tuần. Đây là thao tác GHI duy nhất của nhật ký; không liên quan đặt lệnh. */
export default function NoteEditor({ acc, kind, refId, initial, label = t("Ghi chú"), onSaved }) {
  const qc = useQueryClient();
  const [tags, setTags] = useState(initial?.tags || []);
  const [note, setNote] = useState(initial?.note || "");
  const [rating, setRating] = useState(initial?.rating ?? null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [tagErr, setTagErr] = useState("");
  useEffect(() => { setTags(initial?.tags || []); setNote(initial?.note || ""); setRating(initial?.rating ?? null); setMsg(null); }, [refId, initial?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  const path = `/journal/${encodeURIComponent(acc)}/notes/${kind}/${encodeURIComponent(refId)}`;
  const refresh = () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("journal-") });

  const addTag = (raw) => {
    const tag = raw.trim().toLowerCase().replace(/,+$/, "");
    if (!tag) return;
    if (!TAG_RE.test(tag)) { setTagErr(t("Tag chỉ gồm a-z, 0-9, khoảng trắng và _ : . - (tối đa 32 ký tự).")); return; }
    if (tags.length >= 12) { setTagErr(t("Tối đa 12 tag.")); return; }
    setTagErr("");
    if (!tags.includes(tag)) setTags([...tags, tag]);
    setDraft("");
  };
  const save = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const pend = draft.trim().toLowerCase();
      const finalTags = pend && TAG_RE.test(pend) && !tags.includes(pend) && tags.length < 12 ? [...tags, pend] : tags;
      await apiWrite("PUT", path, { tags: finalTags, note, rating });
      setDraft(""); setTags(finalTags); await refresh(); setMsg({ ok: true, t: t("Đã lưu.") }); onSaved?.();
    } catch (ex) { setMsg({ ok: false, t: ex.message }); } finally { setBusy(false); }
  };
  const del = async () => {
    setBusy(true); setMsg(null);
    try { await apiWrite("DELETE", path); setTags([]); setNote(""); setRating(null); await refresh(); setMsg({ ok: true, t: t("Đã xoá ghi chú.") }); onSaved?.(); }
    catch (ex) { setMsg({ ok: false, t: ex.message }); } finally { setBusy(false); }
  };
  const id = `nt-${kind}-${refId}`;
  return (
    <form className="grid gap-3" onSubmit={save}>
      <div>
        <label htmlFor={`${id}-t`} className="label mb-1.5"><span>{t("Tag (Enter để thêm)")}</span></label>
        {tags.length > 0 && <div className="flex flex-wrap gap-1.5 mb-2">{tags.map((tg) => (
          <span key={tg} className="chip accent">{tg}<button type="button" className="ml-1 -mr-1 w-6 h-6 grid place-items-center bg-transparent border-0 cursor-pointer text-inherit" aria-label={t("Bỏ tag {tag}", { tag: tg })} onClick={() => setTags(tags.filter((x) => x !== tg))}>×</button></span>))}</div>}
        <input id={`${id}-t`} className="field" value={draft} maxLength={32} placeholder={t("vd: fomo, setup-a, ky-luat")} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addTag(draft); } else if (e.key === "Backspace" && !draft && tags.length) setTags(tags.slice(0, -1)); }} />
        {tagErr && <div className="text-[12px] text-down mt-1" role="alert">{tagErr}</div>}
      </div>
      <div className="grid gap-1.5">
        <span className="label"><span>{t("Đánh giá (1 đến 5 sao)")}</span></span>
        <div role="radiogroup" aria-label={t("Đánh giá 1 đến 5 sao")} className="flex">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={t("{n} sao", { n })} className="ibtn" onClick={() => setRating(rating === n ? null : n)}>
              <Star size={22} aria-hidden="true" fill={rating != null && n <= rating ? "var(--accent)" : "none"} style={{ color: rating != null && n <= rating ? "var(--accent)" : "var(--faint)" }} />
            </button>))}
        </div>
      </div>
      <label className="label"><span>{label}</span>
        <textarea className="field" value={note} maxLength={4000} onChange={(e) => setNote(e.target.value)} placeholder={t("Điều gì đã làm đúng? Điều gì cần cải thiện?")} />
      </label>
      {msg && <Notice tone={msg.ok ? "up" : "down"}>{msg.t}</Notice>}
      <div className="flex flex-wrap gap-2">
        <button className="btn primary" type="submit" disabled={busy}>{busy ? t("Đang lưu…") : t("Lưu ghi chú")}</button>
        {(initial || tags.length > 0 || note) && <button className="btn danger" type="button" onClick={del} disabled={busy}>{t("Xoá")}</button>}
      </div>
    </form>
  );
}
