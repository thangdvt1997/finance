// Chi tiết một sự cố: tóm tắt, thao tác (Nhận/Giao/Tạm hoãn/Đóng/Mở lại), ghi chú và dòng thời gian sự kiện.
import { useId, useState } from "react";
import { BellOff, Check, CheckCheck, ExternalLink, MessageSquarePlus, RotateCcw, UserCheck, X } from "lucide-react";
import { ErrLine, Field, GBtn, GroupChip, Pill, PRIMARY, Unavailable, fmtDTfull } from "../bits";
import { isUnavailable } from "../../../lib/fleetApi";
import { usePerm } from "../../../lib/fleetQueries";
import { EmptyState, ErrorState } from "../../ux/States";
import { Skeleton } from "../../ui";
import { useAccountIndex, useIncident, useNow } from "./hooks";
import { EVENT_TONE, EVENT_VN, KIND_LABEL, autoClosed, closerLabel, isActive, leftVN, openedVN } from "./model";
import { AccountLine, SevPill, StatusPill } from "./Card";

const TONE_VAR = { bad: "var(--down)", ok: "var(--up)", warn: "var(--accent)", info: "var(--info)", mute: "var(--muted)" };

function Timeline({ events }) {
  if (!events?.length) return <p className="m-0 text-muted text-[12.5px]">Chưa có sự kiện.</p>;
  return (
    <ol className="fl-timeline" aria-label="Dòng thời gian sự kiện">
      {[...events].reverse().map((e) => {
        const auto = e.type === "auto_resolve";
        return (
          <li key={e.id} style={{ "--ec": TONE_VAR[EVENT_TONE[e.type] || "mute"] }} className="inc-ev">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <b className="text-[12.5px]">{EVENT_VN[e.type] || e.type}</b>
              {auto && <Pill tone="ok">tự động</Pill>}
              <span className="text-muted text-[11.5px]">bởi {e.actor || "hệ thống"}</span>
            </div>
            {e.text && <p className="m-0 mt-0.5 text-[12.5px] whitespace-pre-wrap break-words">{e.text}</p>}
            <time dateTime={e.ts} title={fmtDTfull(e.ts)}>{fmtDTfull(e.ts)} · {openedVN(e.ts)}</time>
          </li>
        );
      })}
    </ol>
  );
}

function NoteForm({ onSubmit, busy }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState(null);
  const id = useId();
  const submit = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setErr(null);
    const r = await onSubmit(text.trim());
    if (r.ok) setText(""); else setErr(r.error);
  };
  return (
    <form onSubmit={submit} className="grid gap-2">
      <Field label="Thêm ghi chú" htmlFor={id} help={`${text.length}/1000 ký tự · ghi chú lưu vĩnh viễn trong dòng thời gian`}>
        <textarea id={id} className="field" rows={2} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Đã liên hệ khách, chờ EA khởi động lại…" />
      </Field>
      <ErrLine error={err} />
      <div><GBtn perm="incident.note" type="submit" disabled={busy || !text.trim()}><MessageSquarePlus size={14} aria-hidden="true" />Lưu ghi chú</GBtn></div>
    </form>
  );
}

function AssignBox({ inc, assignees, meId, busy, onAssign }) {
  const [val, setVal] = useState(inc.assignee_user_id || "");
  const [err, setErr] = useState(null);
  const id = useId();
  const items = assignees.data?.items || [];
  const go = async (uid) => { setErr(null); const r = await onAssign(uid); if (!r.ok) setErr(r.error); };
  const mine = meId && items.some((u) => u.user_id === meId);
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="fl-lab text-[12px] font-semibold">Giao cho</label>
      <div className="flex flex-wrap gap-2">
        <select id={id} className="field flex-1 min-w-[10rem]" value={val} onChange={(e) => setVal(e.target.value)} disabled={assignees.isPending}>
          <option value="">Chưa giao</option>
          {items.map((u) => <option key={u.user_id} value={u.user_id}>{u.name} · {u.role === "master" ? "Master" : "Hỗ trợ"}{u.user_id === meId ? " (tôi)" : ""}</option>)}
          {val && !items.some((u) => u.user_id === val) && <option value={val}>{inc.assignee_label || val}</option>}
        </select>
        <GBtn perm="incident.read" master disabled={busy || val === (inc.assignee_user_id || "")} onClick={() => go(val || null)}><UserCheck size={14} aria-hidden="true" />Áp dụng</GBtn>
        {mine && inc.assignee_user_id !== meId && <GBtn perm="incident.read" master disabled={busy} onClick={() => { setVal(meId); go(meId); }}>Giao cho tôi</GBtn>}
      </div>
      {assignees.isError && <span className="text-[11.5px] text-muted">Không tải được danh sách người phụ trách.</span>}
      <ErrLine error={err} />
    </div>
  );
}

export default function IncidentDetail({ id, initial, assignees, onClose, onAct, act, busy }) {
  const p = usePerm();
  const q = useIncident(id, initial);
  const accts = useAccountIndex();
  const now = useNow();
  const inc = q.data;
  if (!id) return <EmptyState compact title="Chọn một sự cố để xem chi tiết" hint="Dùng phím j / k để chuyển giữa các sự cố, a để nhận, e để đóng." />;
  if (!inc && q.isPending) return <Skeleton rows={6} />;
  if (!inc) return isUnavailable(q.error) ? <Unavailable what="Chi tiết sự cố" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /> : <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} what="Chi tiết sự cố" compact />;
  const acct = accts.data?.get(inc.account_id);
  const active = isActive(inc);
  const stateAct = (type) => onAct(type, inc);
  const kv = (k, v) => (v == null || v === "" ? null : <div className="fl-kv"><dt>{k}</dt><dd>{v}</dd></div>);
  const reasonState = p.reason("incident.read", { master: true });
  return (
    <article className="grid gap-3 min-w-0" aria-labelledby={`inc-h-${inc.id}`} data-detail={inc.id}>
      <header className="grid gap-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <SevPill severity={inc.severity} /><StatusPill status={inc.status} />
          {autoClosed(inc) && <Pill tone="ok">tự đóng</Pill>}
          {inc.status === "snoozed" && <Pill tone="mute" icon={BellOff}>{leftVN(inc.snoozed_until, now)}</Pill>}
          {onClose && <button type="button" className="btn !h-7 !px-2 ml-auto" onClick={onClose} aria-label="Bỏ chọn sự cố"><X size={13} aria-hidden="true" /></button>}
        </div>
        <h2 id={`inc-h-${inc.id}`} className="m-0 text-[15px] font-semibold leading-snug break-words">{inc.title}</h2>
        {inc.detail && <p className="m-0 text-[12.5px] text-muted whitespace-pre-wrap break-words">{inc.detail}</p>}
      </header>

      {q.isError && <ErrLine error={q.error} />}

      <section aria-label="Thao tác" className="grid gap-2 p-2.5 rounded-lg border border-line bg-panel2">
        {reasonState && <p className="m-0 text-[12px] text-muted" role="note">{reasonState} Bạn vẫn có thể ghi chú bên dưới.</p>}
        <div className="flex flex-wrap gap-2">
          {inc.status === "open" && <GBtn perm="incident.read" master className={PRIMARY} disabled={busy} onClick={() => stateAct("ack")}><Check size={14} aria-hidden="true" />Nhận (a)</GBtn>}
          {active && <GBtn perm="incident.read" master disabled={busy} onClick={() => stateAct("snooze")}><BellOff size={14} aria-hidden="true" />Tạm hoãn</GBtn>}
          {active && <GBtn perm="incident.read" master disabled={busy} onClick={() => stateAct("resolve")}><CheckCheck size={14} aria-hidden="true" />Đóng (e)</GBtn>}
          {!active && <GBtn perm="incident.read" master className={PRIMARY} disabled={busy} onClick={() => stateAct("reopen")}><RotateCcw size={14} aria-hidden="true" />Mở lại</GBtn>}
          <a className="btn no-underline" href={`#/doi-tai-khoan?q=${encodeURIComponent(inc.account_id)}`}><ExternalLink size={13} aria-hidden="true" />Xem tài khoản</a>
        </div>
        {active && <AssignBox key={`${inc.id}:${inc.assignee_user_id || ""}`} inc={inc} assignees={assignees} meId={p.me?.user_id} busy={busy} onAssign={(uid) => act({ type: "assign", id: inc.id, user_id: uid }, { dialog: true })} />}
      </section>

      <dl className="m-0">
        {kv("Tài khoản", <AccountLine inc={inc} acct={acct} />)}
        {kv("Nhóm", acct?.groups?.length ? <span className="flex flex-wrap gap-1">{acct.groups.map((g) => <GroupChip key={g.id} g={g} />)}</span> : null)}
        {kv("Loại", KIND_LABEL[inc.kind] || inc.kind)}
        {kv("Mở lúc", `${fmtDTfull(inc.opened_at)} (${openedVN(inc.opened_at, now)})`)}
        {kv("Nhận lúc", inc.acked_at ? fmtDTfull(inc.acked_at) : null)}
        {kv("Người phụ trách", inc.assignee_label || "Chưa giao")}
        {kv("Tạm hoãn đến", inc.status === "snoozed" && inc.snoozed_until ? `${fmtDTfull(inc.snoozed_until)} (${leftVN(inc.snoozed_until, now)})` : null)}
        {kv("Đóng lúc", inc.status === "resolved" ? `${fmtDTfull(inc.resolved_at)} · ${closerLabel(inc)}` : null)}
        {kv("Ghi nhận lại", inc.occurrences > 1 ? <span className="num">{inc.occurrences} lần · gần nhất {openedVN(inc.last_seen_at, now)}</span> : null)}
      </dl>

      <section aria-label="Ghi chú" className="grid gap-1.5">
        <NoteForm busy={busy} onSubmit={(text) => act({ type: "note", id: inc.id, text }, { dialog: true })} />
      </section>

      <section aria-label="Dòng thời gian" className="grid gap-2">
        <h3 className="m-0 text-[12.5px] font-semibold">Dòng thời gian</h3>
        <Timeline events={inc.events} />
      </section>
    </article>
  );
}
