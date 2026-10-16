// Thẻ sự cố (danh sách) + thẻ cụm "N tài khoản cùng lỗi". Mức độ luôn có biểu tượng + chữ + viền trái.
import { useState } from "react";
import { BellOff, Check, CheckCheck, ChevronDown, Layers, RotateCcw, UserRound, Zap } from "lucide-react";
import { cn } from "../../ui";
import { GroupChip, Pill } from "../bits";
import { KIND_LABEL, STATUS, STATUS_TONE, autoClosed, closerLabel, isActive, leftVN, openedVN, sevOf } from "./model";

export const SevPill = ({ severity }) => { const s = sevOf(severity); return <Pill tone={s.tone} icon={s.icon}>{s.label}</Pill>; };
export const StatusPill = ({ status }) => <Pill tone={STATUS_TONE[status] || "mute"}>{STATUS.find((s) => s.id === status)?.label || status}</Pill>;

export function AccountLine({ inc, acct, link = true }) {
  const label = acct?.label || acct?.client_name;
  if (!inc.account_id) return <span className="text-muted">Toàn hệ thống</span>;
  return (
    <span className="inline-flex items-center gap-1.5 min-w-0 flex-wrap">
      {label && <b className="font-medium text-fg truncate max-w-[14rem]">{label}</b>}
      {link
        ? <a className="num text-[11.5px] text-info hover:underline" href={`#/doi-tai-khoan?q=${encodeURIComponent(inc.account_id)}`} onClick={(e) => e.stopPropagation()} title="Mở trong Đội tài khoản">{inc.account_id}</a>
        : <span className="num text-[11.5px]">{inc.account_id}</span>}
    </span>
  );
}

export function IncidentCard({ inc, acct, now, current, selected, checked, onCheck, onOpen, onAct, canAct, canSelect, busy, innerRef }) {
  const sev = sevOf(inc.severity);
  const auto = autoClosed(inc);
  const groups = acct?.groups || [];
  return (
    <li ref={innerRef} className={cn("fl-card inc-card", `t-${sev.tone}`)} aria-current={current ? "true" : undefined} data-inc={inc.id} data-selected={selected ? "1" : undefined}>
      <div className="flex items-start gap-2">
        {canSelect && <input type="checkbox" className="fl-chk mt-[3px]" checked={!!checked} onChange={(e) => onCheck(inc.id, e.target.checked)} aria-label={`Chọn sự cố: ${inc.title}`} />}
        <div className="min-w-0 flex-1 grid gap-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <SevPill severity={inc.severity} />
            <StatusPill status={inc.status} />
            {auto && <Pill tone="ok" icon={Zap} title="Điều kiện đã hết nên hệ thống tự đóng">tự đóng</Pill>}
            {inc.status === "snoozed" && inc.snoozed_until && <Pill tone="mute" icon={BellOff} title={`Tạm hoãn đến ${new Date(inc.snoozed_until).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false })}`}>{leftVN(inc.snoozed_until, now)}</Pill>}
            {inc.occurrences > 1 && <span className="text-[11px] text-muted num" title="Số lần hệ thống ghi nhận lại sự cố này">×{inc.occurrences}</span>}
          </div>
          <button type="button" className="inc-title" onClick={() => onOpen(inc.id)} aria-label={`Mở chi tiết: ${inc.title}`}>{inc.title}</button>
          {inc.detail && <p className="m-0 text-[12px] text-muted inc-detail">{inc.detail}</p>}
          <div className="fl-meta">
            <AccountLine inc={inc} acct={acct} />
            {groups.slice(0, 2).map((g) => <GroupChip key={g.id} g={g} />)}
            {groups.length > 2 && <span className="text-[11px]">+{groups.length - 2} nhóm</span>}
          </div>
          <div className="fl-meta">
            <span title={inc.opened_at ? new Date(inc.opened_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false }) : ""}>{inc.status === "resolved" ? `đóng ${openedVN(inc.resolved_at, now)}` : `mở ${openedVN(inc.opened_at, now)}`}</span>
            {inc.kind && <span>{KIND_LABEL[inc.kind] || inc.kind}</span>}
            <span className="inline-flex items-center gap-1"><UserRound size={11} aria-hidden="true" />{inc.status === "resolved" && inc.resolved_by ? closerLabel(inc).replace(/ \(.*/, "") : inc.assignee_label || "Chưa giao"}</span>
          </div>
        </div>
        {canAct && (
          <div className="inc-quick" role="group" aria-label="Thao tác nhanh">
            {inc.status === "open" && <button type="button" className="btn !h-7 !px-2" disabled={busy} onClick={() => onAct("ack", inc)} title="Nhận sự cố (phím a)"><Check size={13} aria-hidden="true" /><span className="max-sm:sr-only">Nhận</span></button>}
            {isActive(inc) && <button type="button" className="btn !h-7 !px-2" disabled={busy} onClick={() => onAct("resolve", inc)} title="Đóng sự cố (phím e)"><CheckCheck size={13} aria-hidden="true" /><span className="max-sm:sr-only">Đóng</span></button>}
            {inc.status === "resolved" && <button type="button" className="btn !h-7 !px-2" disabled={busy} onClick={() => onAct("reopen", inc)} title="Mở lại sự cố"><RotateCcw size={13} aria-hidden="true" /><span className="max-sm:sr-only">Mở lại</span></button>}
          </div>
        )}
      </div>
    </li>
  );
}

/** Cụm cùng nguyên nhân: tiêu đề + số tài khoản + thao tác hàng loạt cho cả cụm; mở rộng để xem từng tài khoản. */
export function ClusterCard({ cluster, byId, accts, canAct, busy, onClusterAct, forceOpen, children }) {
  const [openS, setOpen] = useState(false);
  const open = openS || !!forceOpen;
  const sev = sevOf(cluster.severity);
  const items = cluster.incident_ids.map((i) => byId.get(i)).filter(Boolean);
  const uniq = [...new Set(cluster.accounts)];
  const names = uniq.slice(0, 4).map((a) => accts?.get(a)?.label || a);
  const rest = uniq.length - names.length;
  const hasOpen = items.some((i) => i.status === "open" || i.status === "snoozed");
  const hasActive = items.some(isActive);
  return (
    <li className={cn("fl-card inc-cluster", `t-${sev.tone}`)} data-cluster={cluster.cause_key}>
      <div className="flex items-start gap-2">
        <Layers size={16} className="mt-[3px] text-muted shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1 grid gap-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <SevPill severity={cluster.severity} />
            <Pill tone="mute"><b className="num">{cluster.count}</b> tài khoản cùng lỗi</Pill>
          </div>
          <button type="button" className="inc-title" aria-expanded={open} onClick={() => setOpen(!openS)}>{cluster.title}</button>
          <div className="fl-meta"><span className="min-w-0 break-words">{names.join(", ")}{rest > 0 ? ` và ${rest} tài khoản khác` : ""}</span></div>
        </div>
        <div className="inc-quick" role="group" aria-label={`Thao tác cho cả cụm ${cluster.count} sự cố`}>
          {canAct && hasOpen && <button type="button" className="btn !h-7 !px-2" disabled={busy} onClick={() => onClusterAct("ack", items)} title="Nhận tất cả sự cố trong cụm"><Check size={13} aria-hidden="true" /><span className="max-sm:sr-only">Nhận tất cả</span></button>}
          {canAct && hasActive && <button type="button" className="btn !h-7 !px-2" disabled={busy} onClick={() => onClusterAct("snooze", items)} title="Tạm hoãn cả cụm"><BellOff size={13} aria-hidden="true" /><span className="max-sm:sr-only">Tạm hoãn</span></button>}
          {canAct && hasActive && <button type="button" className="btn !h-7 !px-2" disabled={busy} onClick={() => onClusterAct("resolve", items)} title="Đóng cả cụm"><CheckCheck size={13} aria-hidden="true" /><span className="max-sm:sr-only">Đóng tất cả</span></button>}
          <button type="button" className="btn !h-7 !px-2" aria-expanded={open} aria-label={open ? "Thu gọn cụm" : "Xem từng tài khoản"} onClick={() => setOpen(!openS)}><ChevronDown size={13} className={cn("transition-transform", open && "rotate-180")} aria-hidden="true" /></button>
        </div>
      </div>
      {open && <ul className="fl-list inc-sub">{children(items)}</ul>}
    </li>
  );
}
