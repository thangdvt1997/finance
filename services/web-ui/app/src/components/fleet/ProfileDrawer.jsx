// Hồ sơ khách (W2): drawer 4 tab — Tổng quan · Rủi ro & luật · Ghi chú CRM · Kiểm toán. Mọi thao tác ghi đi qua API /auth/admin (server kiểm quyền thật).
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, FileText, KeyRound, LogOut, MessageSquarePlus, Pause, Play, Plus, QrCode, RefreshCcw, ScrollText, ShieldAlert, SlidersHorizontal, UserCog, Wrench } from "lucide-react";
import { Dialog } from "../dialog";
import { Skeleton } from "../ui";
import { toast } from "../../ux/bus";
import { fget, fpost, fput } from "../../lib/fleetApi";
import { ACC_STATUS_VN, EA_VN, KIND_VN, SEV_VN, useAccountNotes, useAuditTarget, useCompliance, useFleetList, useFleetMut, useGroups, usePerm, useTags } from "../../lib/fleetQueries";
import { AUDIT_VN } from "../../lib/clientsQueries";
import { ConfirmDialog, ACTIONS } from "../clients/ActionDialogs";
import { Banner, CompStatus, ErrLine, Field, GBtn, GroupChip, Pill, TagChip, UsageBar, Unavailable, ago, fmtDT, fmtDTfull, PRIMARY } from "./bits";
import { StatePills } from "./FleetTable";
import ViewAsDialog from "./ViewAsDialog";

const EquitySpark = lazy(() => import("../clients/AccountDetail").then((m) => ({ default: m.EquitySpark })));
const TAG_RE = /^[a-z0-9][a-z0-9_.-]{0,23}$/;

const KV = ({ k, children, mono }) => (<div className="fl-kv"><dt>{k}</dt><dd className={mono ? "num" : undefined}>{children ?? "—"}</dd></div>);

function useAccount(id) {
  return useQuery({ queryKey: ["fl", "account", id], enabled: !!id, retry: false, staleTime: 10_000, queryFn: ({ signal }) => fget(`/accounts/${encodeURIComponent(id)}`, null, { signal }) });
}

function GroupsTags({ row, canEdit }) {
  const groups = useGroups().data?.items || [];
  const tags = useTags().data?.items || [];
  const [tag, setTag] = useState("");
  const [grp, setGrp] = useState("");
  const setGroups = useFleetMut((ids) => fput(`/accounts/${encodeURIComponent(row.account_id)}/groups`, { group_ids: ids }), ["fleet", "groups", "account"]);
  const setTags = useFleetMut((t) => fput(`/accounts/${encodeURIComponent(row.account_id)}/tags`, { tags: t }), ["fleet", "tags"]);
  const gids = (row.groups || []).map((g) => g.id);
  const addTag = (e) => {
    e.preventDefault();
    const t = tag.trim().toLowerCase();
    if (!TAG_RE.test(t) || (row.tags || []).includes(t)) return;
    setTags.mutate([...(row.tags || []), t], { onSuccess: () => setTag("") });
  };
  return (
    <div className="grid gap-3">
      <div className="grid gap-1.5">
        <span className="fl-lab text-[12px] font-semibold">Nhóm</span>
        <div className="flex flex-wrap items-center gap-1.5">
          {(row.groups || []).map((g) => <GroupChip key={g.id} g={g} onRemove={canEdit ? () => setGroups.mutate(gids.filter((x) => x !== g.id)) : undefined} />)}
          {!(row.groups || []).length && <span className="text-faint text-[12px]">Chưa thuộc nhóm nào</span>}
          {canEdit && (
            <select aria-label="Thêm vào nhóm" className="field !h-7 !text-[11.5px]" value={grp} onChange={(e) => { const v = e.target.value; setGrp(""); if (v) setGroups.mutate([...gids, v]); }}>
              <option value="">+ Thêm vào nhóm…</option>
              {groups.filter((g) => !gids.includes(g.id)).map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          )}
        </div>
      </div>
      <div className="grid gap-1.5">
        <span className="fl-lab text-[12px] font-semibold">Tag</span>
        <div className="flex flex-wrap items-center gap-1.5">
          {(row.tags || []).map((t) => <TagChip key={t} t={t} onRemove={canEdit ? () => setTags.mutate((row.tags || []).filter((x) => x !== t)) : undefined} />)}
          {!(row.tags || []).length && <span className="text-faint text-[12px]">Chưa có tag</span>}
          {canEdit && (
            <form onSubmit={addTag} className="inline-flex items-center gap-1">
              <input list="pd-tags" aria-label="Thêm tag" className="field !h-7 !text-[11.5px] !w-28" placeholder="+ tag" value={tag} maxLength={24} onChange={(e) => setTag(e.target.value)} aria-invalid={tag !== "" && !TAG_RE.test(tag.trim().toLowerCase())} />
              <datalist id="pd-tags">{tags.map((t) => <option key={t.tag} value={t.tag} />)}</datalist>
              <button type="submit" className="btn !h-7 !px-2" aria-label="Thêm tag" disabled={!TAG_RE.test(tag.trim().toLowerCase())}><Plus size={13} aria-hidden="true" /></button>
            </form>
          )}
        </div>
      </div>
      <ErrLine error={setGroups.error || setTags.error} />
    </div>
  );
}

function Overview({ row, acc, can, onAct, onViewAs }) {
  const inc = useQuery({ queryKey: ["fl", "acc-inc", row.account_id], retry: false, staleTime: 15_000, queryFn: ({ signal }) => fget("/incidents", { account: row.account_id, status: "active", limit: 10 }, { signal }) });
  const a = acc.data || {};
  const items = inc.data?.items || [];
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Hành động quản trị tài khoản">
        <GBtn master perm="fleet.read" onClick={onViewAs} disabled={row.status === "pending"} title={row.status === "pending" ? "Tài khoản chưa được duyệt" : "Xem đúng dữ liệu khách thấy (chỉ đọc, có lý do + hạn 30 phút)"}><Eye size={13} aria-hidden="true" />Xem như khách</GBtn>
        <GBtn master perm="fleet.read" onClick={() => onAct("pairing")}><QrCode size={13} aria-hidden="true" />Cấp mã ghép cặp</GBtn>
        <GBtn master perm="fleet.read" onClick={() => onAct("rotate")}><RefreshCcw size={13} aria-hidden="true" />Xoay token EA</GBtn>
        <GBtn master perm="fleet.read" onClick={() => onAct("passcode")}><KeyRound size={13} aria-hidden="true" />Cấp lại passcode</GBtn>
        {row.status === "suspended"
          ? <GBtn master perm="fleet.read" onClick={() => onAct("activate")}><Play size={13} aria-hidden="true" />Kích hoạt</GBtn>
          : <GBtn master perm="fleet.read" onClick={() => onAct("suspend")} disabled={row.status === "pending"}><Pause size={13} aria-hidden="true" />Đình chỉ</GBtn>}
        <GBtn master perm="fleet.read" onClick={() => onAct("logout")} disabled={!a.client_id}><LogOut size={13} aria-hidden="true" />Ép đăng xuất</GBtn>
        <a className="btn no-underline" href={`#/khach-hang/danh-sach/${row.account_id}`} title="Bảng kỹ thuật cũ: vị thế, equity, nhật ký đăng nhập, xoá tài khoản…"><Wrench size={13} aria-hidden="true" />Bảng kỹ thuật</a>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <section aria-label="Hồ sơ" className="rounded-lg border border-line p-3">
          <h3 className="m-0 mb-1 text-[12.5px] font-semibold">Hồ sơ</h3>
          <dl className="m-0">
            <KV k="Khách hàng">{row.client_name || a.client_name}</KV>
            <KV k="Nền tảng" mono>{row.platform?.toUpperCase()} · {row.login}</KV>
            <KV k="Server">{row.server}</KV>
            <KV k="Trạng thái">{ACC_STATUS_VN[row.status] || row.status}</KV>
            <KV k="Tạo lúc">{fmtDT(a.created_at)}</KV>
            <KV k="Ghi chú đầu">{a.notes}</KV>
            <KV k="Thông báo khách">{row.client_notify ? "Khách đã bật nhận thông báo khi sát/vi phạm luật" : "Khách chưa bật (opt-in)"}</KV>
          </dl>
        </section>
        <section aria-label="Kết nối EA" className="rounded-lg border border-line p-3">
          <h3 className="m-0 mb-1 text-[12.5px] font-semibold">Kết nối EA</h3>
          <dl className="m-0">
            <KV k="Trạng thái"><StatePills r={row} /></KV>
            <KV k="Phiên bản EA" mono>{row.ea_version}</KV>
            <KV k="Độ trễ" mono>{row.ea_latency_ms != null ? `${row.ea_latency_ms} ms` : null}</KV>
            <KV k="Dữ liệu cuối">{row.last_seen_at ? `${fmtDTfull(row.last_seen_at)} · ${ago(row.last_seen_at)}` : "Chưa có"}</KV>
            <KV k="Tuân thủ"><CompStatus status={row.compliance?.status || "na"} /></KV>
          </dl>
        </section>
      </div>
      <section aria-label="Nhóm và tag" className="rounded-lg border border-line p-3"><GroupsTags row={row} canEdit={can.edit} /></section>
      <section aria-label="Sự cố đang mở" className="rounded-lg border border-line p-3">
        <h3 className="m-0 mb-2 text-[12.5px] font-semibold flex items-center gap-1.5"><ShieldAlert size={14} aria-hidden="true" />Sự cố đang mở {items.length ? <span className="fl-badge">{items.length}</span> : null}</h3>
        {inc.isPending ? <Skeleton rows={2} /> : inc.isError ? <p className="m-0 text-[12.5px] text-muted">{inc.error?.code === "forbidden" ? "Vai trò của bạn không xem được sự cố." : "Chưa tải được sự cố."}</p>
          : !items.length ? <p className="m-0 text-[12.5px] text-muted">Không có sự cố đang mở.</p>
          : <ul className="fl-list">{items.map((i) => (
              <li key={i.id} className={`fl-card ${i.severity === "critical" ? "t-bad" : "t-warn"}`}>
                <b className="text-[12.5px]">{i.title || i.condition || i.cause_key}</b>
                <span className="fl-meta"><Pill tone={i.severity === "critical" ? "bad" : "warn"}>{SEV_VN[i.severity] || i.severity}</Pill><span>mở {ago(i.opened_at || i.created_at)}</span>{i.assignee_name || i.assignee ? <span>phụ trách: {i.assignee_name || i.assignee}</span> : null}</span>
              </li>))}
            </ul>}
        <a className="btn no-underline mt-2 inline-flex" href="#/su-co"><ScrollText size={13} aria-hidden="true" />Mở hộp sự cố</a>
      </section>
      {row.status !== "pending" && (
        <section aria-label="Equity 7 ngày" className="rounded-lg border border-line p-3"><h3 className="m-0 mb-1 text-[12.5px] font-semibold">Equity 7 ngày</h3>
          <Suspense fallback={<Skeleton rows={3} />}><EquitySpark id={row.account_id} /></Suspense></section>
      )}
    </div>
  );
}

function RulesTab({ id }) {
  const q = useCompliance({ account: id, limit: 500 });
  if (q.isPending) return <Skeleton rows={4} />;
  if (q.isError) return <Unavailable what="Tuân thủ luật" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  const items = (q.data?.items || []).filter((x) => x.account_id === id);
  if (!items.length) return (
    <div className="fl-empty"><b>Chưa có luật nào áp cho tài khoản này</b><span>Gán mẫu luật theo nhóm/tag/tài khoản ở trang Luật & tuân thủ; kết quả xuất hiện sau chu kỳ đánh giá kế tiếp.</span><a className="btn no-underline mt-1" href="#/luat"><SlidersHorizontal size={13} aria-hidden="true" />Mở Luật & tuân thủ</a></div>);
  return (
    <ul className="fl-list">
      {items.map((x) => (
        <li key={`${x.assignment_id}`} className={`fl-card ${x.status === "red" ? "t-bad" : x.status === "yellow" ? "t-warn" : x.status === "green" ? "t-ok" : ""}`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><b className="text-[12.5px]">{x.rule_name}</b><CompStatus status={x.status} stale={x.stale} /></div>
          <span className="text-[11.5px] text-muted">{KIND_VN[x.kind] || x.kind}</span>
          <UsageBar pct={x.usage_pct} status={x.status} headroom={x.headroom} unit={x.unit} label={x.value != null && x.limit != null ? `${x.value} / ${x.limit}${x.unit ? ` ${x.unit}` : ""}` : undefined} />
          <span className="fl-meta">{x.reset_at && <span>Reset: {fmtDT(x.reset_at)}</span>}{x.evaluated_at && <span>Đánh giá {ago(x.evaluated_at)}</span>}</span>
        </li>
      ))}
    </ul>
  );
}

function NotesTab({ id, canWrite }) {
  const q = useAccountNotes(id);
  const [text, setText] = useState("");
  const add = useFleetMut((t) => fpost(`/accounts/${encodeURIComponent(id)}/notes`, { text: t }), ["notes"], { onSuccess: () => { setText(""); toast({ tone: "ok", title: "Đã thêm ghi chú" }); } });
  const items = q.data?.items || [];
  return (
    <div className="grid gap-3">
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate(text.trim()); }} className="grid gap-2">
        <Field label="Thêm ghi chú CRM" htmlFor="pd-note" help={`${text.length}/1000 — ghi nhận liên hệ, cam kết, nhắc việc. Khách KHÔNG thấy ghi chú này.`}>
          <textarea id="pd-note" className="field" rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} disabled={!canWrite} placeholder={canWrite ? "Ví dụ: đã gọi khách 14:05, hẹn cập nhật EA tối nay" : "Vai trò của bạn không có quyền ghi chú"} />
        </Field>
        <ErrLine error={add.error} />
        <div><GBtn perm="note.write" type="submit" className={PRIMARY} disabled={!text.trim() || add.isPending}><MessageSquarePlus size={13} aria-hidden="true" />{add.isPending ? "Đang lưu…" : "Lưu ghi chú"}</GBtn></div>
      </form>
      {q.isPending ? <Skeleton rows={3} /> : q.isError ? <Unavailable what="Ghi chú CRM" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
        : !items.length ? <p className="m-0 text-[12.5px] text-muted">Chưa có ghi chú nào.</p>
        : <ul className="fl-list">{items.map((n, i) => (
            <li key={n.id ?? i} className="fl-card t-info"><p className="m-0 whitespace-pre-wrap text-[12.5px]">{n.text}</p>
              <span className="fl-meta"><span>{n.author || n.actor_label || n.author_name || "—"}</span><span title={fmtDTfull(n.created_at || n.ts)}>{ago(n.created_at || n.ts)}</span></span></li>))}</ul>}
    </div>
  );
}

function AuditTab({ id }) {
  const q = useAuditTarget(id, 60);
  if (q.isPending) return <Skeleton rows={5} />;
  if (q.isError) return <Unavailable what="Nhật ký kiểm toán" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  const items = q.data?.items || [];
  if (!items.length) return <p className="m-0 text-[12.5px] text-muted">Chưa có hành động nào được ghi cho tài khoản này.</p>;
  return (
    <ol className="fl-timeline" aria-label="Nhật ký hành động theo tài khoản">
      {items.map((e) => (
        <li key={e.id}><b>{AUDIT_VN[e.action] || e.action}</b> <span className="text-muted">· {e.actor_label || "hệ thống"}</span>
          <time dateTime={e.ts} title={fmtDTfull(e.ts)}>{fmtDT(e.ts)} · {ago(e.ts)}{e.ip ? ` · ${e.ip}` : ""}</time></li>))}
    </ol>
  );
}

const TABS = [
  { id: "tong-quan", label: "Tổng quan", icon: UserCog },
  { id: "luat", label: "Rủi ro & luật", icon: ShieldAlert },
  { id: "ghi-chu", label: "Ghi chú CRM", icon: FileText },
  { id: "kiem-toan", label: "Kiểm toán", icon: ScrollText, perm: "audit.read" },
];

export default function ProfileDrawer({ id, row: given, onClose }) {
  const perm = usePerm();
  const qc = useQueryClient();
  const [tab, setTab] = useState("tong-quan");
  const [act, setAct] = useState(null);
  const [va, setVa] = useState(false);
  const lookup = useFleetList({ q: id, limit: 5 }, { enabled: !!id && !given });
  const row = useMemo(() => given || (lookup.data?.items || []).find((r) => r.account_id === id), [given, lookup.data, id]);
  const acc = useAccount(id);
  const can = { edit: perm.write("fleet.read", { master: true }), note: perm.write("note.write") };
  const tabs = TABS.filter((t) => !t.perm || perm.has(t.perm));
  useEffect(() => { setTab("tong-quan"); }, [id]);
  // hàng cho ConfirmDialog cũ cần client_id/has_hmac (lấy từ GET accounts/{id})
  const techRow = row ? { ...row, ...(acc.data || {}), client_name: row.client_name || acc.data?.client_name } : null;

  return (
    <>
      <Dialog open onClose={onClose} variant="drawer" className="sm:max-w-[780px]" title={row ? `${row.label || row.login} · ${row.account_id}` : id}>
        <div className="flex flex-col min-h-0">
          <div role="tablist" aria-label="Mục hồ sơ" className="fl-tabs px-2">
            {tabs.map((t) => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} id={`pd-t-${t.id}`} aria-controls={`pd-p-${t.id}`} onClick={() => setTab(t.id)}
                onKeyDown={(e) => { const i = tabs.findIndex((x) => x.id === tab); if (e.key === "ArrowRight") setTab(tabs[(i + 1) % tabs.length].id); if (e.key === "ArrowLeft") setTab(tabs[(i + tabs.length - 1) % tabs.length].id); }}>
                <t.icon size={13} aria-hidden="true" />{t.label}
              </button>
            ))}
          </div>
          <div className="p-3 grid gap-3" role="tabpanel" id={`pd-p-${tab}`} aria-labelledby={`pd-t-${tab}`} tabIndex={0}>
            {!row ? (
              lookup.isPending ? <Skeleton rows={6} /> : lookup.isError ? <ErrLine error={lookup.error} /> : <p className="m-0 text-muted">Không tìm thấy tài khoản <span className="num">{id}</span> trong phạm vi của bạn (có thể đã bị xoá hoặc ngoài nhóm được giao).</p>
            ) : (
              <>
                {tab === "tong-quan" && <Overview row={row} acc={acc} can={can} onAct={setAct} onViewAs={() => setVa(true)} />}
                {tab === "luat" && <RulesTab id={row.account_id} />}
                {tab === "ghi-chu" && <NotesTab id={row.account_id} canWrite={can.note} />}
                {tab === "kiem-toan" && <AuditTab id={row.account_id} />}
                {perm.viewAs && <Banner tone="info">Đang xem như khách: các nút ghi bị khoá.</Banner>}
              </>
            )}
          </div>
        </div>
      </Dialog>
      {act && techRow && <ConfirmDialog kind={act} row={techRow} onClose={() => { setAct(null); qc.invalidateQueries({ queryKey: ["fl"] }); }} onDone={(k) => { toast({ tone: "ok", title: `${ACTIONS[k]?.label || k}: đã thực hiện`, body: techRow.account_id }); }} />}
      {va && row && <ViewAsDialog open accountId={row.account_id} label={row.label} onClose={() => setVa(false)} />}
    </>
  );
}
