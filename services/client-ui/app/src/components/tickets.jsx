// Sheet "Báo quản trị": chọn loại sự cố + ghi chú, tự đính kèm ngữ cảnh kết nối, gửi POST /user/tickets; xem yêu cầu của tôi và phản hồi.
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Inbox, Send } from "lucide-react";
import { Chip, Notice, Sheet, Skeleton, cn } from "./ui";
import { TICKET_CATS, sendTicket, ticketItems, useInvalidateTickets, useTickets } from "../lib/q_today";
import { ageText } from "../lib/freshness";
import { clean, dateTime } from "../lib/format";
import { t } from "../lib/i18n";

const MAX = 1000;
const statusInfo = (s) => {
  const k = String(s || "open").toLowerCase();
  if (["answered", "replied"].includes(k)) return { label: t("Đã phản hồi"), tone: "up" };
  if (["in_progress", "processing", "pending"].includes(k)) return { label: t("Đang xử lý"), tone: "accent" };
  if (["closed", "resolved", "done"].includes(k)) return { label: t("Đã đóng"), tone: "" };
  return { label: t("Đã gửi, chờ xử lý"), tone: "info" };
};
const catLabel = (v) => TICKET_CATS.find((c) => c.value === v)?.label || t("Khác");

function MyTickets({ enabled }) {
  const q = useTickets(enabled);
  if (q.isPending) return <Skeleton rows={2} />;
  if (q.isError) return <p className="m-0 text-[13px] text-muted" role="status">{q.error?.status === 404 ? t("Tính năng gửi yêu cầu chưa khả dụng trên máy chủ. Hãy liên hệ quản trị viên trực tiếp.") : t("Chưa tải được danh sách yêu cầu của bạn.")}</p>;
  const items = ticketItems(q.data).slice(0, 12);
  if (!items.length) return <p className="m-0 flex items-start gap-2 text-[13px] text-muted"><Inbox size={15} className="mt-[2px] shrink-0" aria-hidden="true" />{t("Bạn chưa gửi yêu cầu nào.")}</p>;
  return (
    <ul className="list-none m-0 p-0 grid gap-2">
      {items.map((x) => {
        const st = statusInfo(x.status);
        return (
          <li key={x.id} className="rounded-xl border border-line bg-panel2 p-2.5 text-[13px]">
            <div className="flex flex-wrap items-center gap-1.5">
              <Chip>{catLabel(x.category)}</Chip><Chip tone={st.tone}>{st.label}</Chip>
              <span className="ml-auto text-[12px] text-faint num">{dateTime(x.created_at)}</span>
            </div>
            <p className="m-0 mt-1.5 whitespace-pre-wrap break-words">{clean(x.message)}</p>
            {x.reply ? (
              <div className="mt-2 border-l-2 pl-2.5" style={{ borderColor: "var(--accent)" }}>
                <div className="text-[12px] font-semibold text-accent">{t("Phản hồi của quản trị")}</div>
                <p className="m-0 whitespace-pre-wrap break-words text-muted">{clean(x.reply)}</p>
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

/** ctx = { ea_state, age_s, latency_ms, label }. onClose phải là hàm ỔN ĐỊNH (useCallback) vì Sheet gắn lại focus khi onClose đổi. */
export default function TicketSheet({ accountId, ctx, initialCat = "other", onClose }) {
  const [cat, setCat] = useState(initialCat);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const [err, setErr] = useState("");
  const [until, setUntil] = useState(0);
  const [, tick] = useState(0);
  const lock = useRef(false);
  const inval = useInvalidateTickets();
  const left = Math.max(0, Math.ceil((until - Date.now()) / 1000));
  useEffect(() => {
    if (!until) return undefined;
    const h = setInterval(() => { tick((n) => n + 1); if (Date.now() >= until) setUntil(0); }, 1000);
    return () => clearInterval(h);
  }, [until]);

  const submit = async (e) => {
    e.preventDefault();
    if (lock.current || busy || left > 0) return; // chống bấm đúp
    const message = msg.trim();
    if (!message) { setErr(t("Hãy mô tả ngắn vấn đề bạn gặp.")); return; }
    lock.current = true; setBusy(true); setErr(""); setSent(null);
    try {
      const body = { account_id: accountId || undefined, category: cat, message: message.slice(0, MAX), context: { ea_state: ctx?.ea_state ?? null, age_s: ctx?.age_s == null ? null : Math.round(ctx.age_s), latency_ms: ctx?.latency_ms ?? null } };
      const r = await sendTicket(body);
      setSent(r?.id || true); setMsg(""); inval();
    } catch (x) {
      if (x?.status === 429) { const s = Number(x.retryAfter) || 30; setUntil(Date.now() + s * 1000); setErr(t("Bạn gửi quá nhiều yêu cầu trong thời gian ngắn. Hãy thử lại sau {n} giây.", { n: s })); }
      else setErr(x?.message || t("Chưa gửi được. Hãy thử lại."));
    } finally { lock.current = false; setBusy(false); }
  };

  return (
    <Sheet title={t("Báo quản trị")} onClose={onClose}>
      <form onSubmit={submit} className="grid gap-3" noValidate>
        <div className="grid gap-1.5">
          <span className="text-[12.5px] text-muted font-semibold">{t("Loại vấn đề")}</span>
          <div role="group" aria-label={t("Loại vấn đề")} className="grid grid-cols-2 gap-2">{TICKET_CATS.map((c) => <button key={c.value} type="button" className="btn sm" aria-pressed={cat === c.value} onClick={() => setCat(c.value)} style={cat === c.value ? { background: "var(--accent)", color: "var(--accent-fg)", borderColor: "transparent" } : undefined}>{c.label}</button>)}</div>
        </div>
        <label className="label">
          <span>{t("Mô tả (tối đa {n} ký tự)", { n: MAX })}</span>
          <textarea className="field" value={msg} maxLength={MAX} rows={4} onChange={(e) => setMsg(e.target.value)} placeholder={t("Ví dụ: EA báo mất kết nối từ 9 giờ dù MT vẫn mở.")} aria-describedby="tk-count" />
          <span id="tk-count" className={cn("text-[12px] text-right num", msg.length > MAX - 50 ? "text-accent" : "text-faint")}>{msg.length}/{MAX}</span>
        </label>
        <p className="m-0 text-[12.5px] text-faint">
          {t("Tự đính kèm: trạng thái {s}, dữ liệu {a}{l}.", { s: ctx?.label || "—", a: ctx?.age_s == null ? t("chưa có") : ageText(ctx.age_s), l: ctx?.latency_ms != null ? t(", độ trễ {n} ms", { n: Math.round(ctx.latency_ms) }) : "" })}
        </p>
        {err ? <div role="alert" className="text-[13px] text-down">{err}</div> : null}
        {sent ? <Notice tone="up" icon={CheckCircle2} title={t("Đã gửi cho quản trị")}>{typeof sent === "string" ? t("Mã yêu cầu {id}. ", { id: sent }) : ""}{t("Phản hồi sẽ hiện ở danh sách bên dưới.")}</Notice> : null}
        <button type="submit" className="btn primary" disabled={busy || left > 0 || !msg.trim()} aria-busy={busy}>
          <Send size={16} aria-hidden="true" /> {busy ? t("Đang gửi...") : left > 0 ? t("Thử lại sau {n} giây", { n: left }) : t("Gửi cho quản trị")}
        </button>
      </form>
      <h3 className="mt-4 mb-2 text-[13.5px] font-semibold">{t("Yêu cầu của tôi")}</h3>
      <MyTickets enabled />
    </Sheet>
  );
}
