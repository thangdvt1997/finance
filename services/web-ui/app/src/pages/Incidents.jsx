import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BellOff, Check, CheckCheck, RefreshCw, Siren, X } from "lucide-react";
import "../fleet.css";
import "../components/fleet/incidents/incidents.css";
import { PageHead, Skeleton, cn } from "../components/ui";
import { Dialog } from "../components/dialog";
import { EmptyState, ErrorState } from "../components/ux/States";
import { Banner, ErrLine, GBtn, RoNote, Unavailable, PRIMARY } from "../components/fleet/bits";
import { isUnavailable } from "../lib/fleetApi";
import { useAssignees, useGroups, useIncidentCounts, usePerm } from "../lib/fleetQueries";
import { useHashQuery } from "../ux/urlstate";
import { toast } from "../ux/bus";
import { useAccountIndex, useIncActions, useIncidentList, useMedia, useNow } from "../components/fleet/incidents/hooks";
import { STATUS, isActive, matchQuery } from "../components/fleet/incidents/model";
import { ClusterCard, IncidentCard } from "../components/fleet/incidents/Card";
import IncidentDetail from "../components/fleet/incidents/Detail";
import Filters, { useIncFilters } from "../components/fleet/incidents/Filters";
import { ResolveDialog, SnoozeDialog } from "../components/fleet/incidents/Dialogs";

export const meta = { path: "su-co", label: "Sự cố", group: "Quản trị đội", icon: Siren, roles: ["master", "support"], perm: "incident.read", order: 20, keywords: "su co incident hop thu canh bao mat ea tuan thu luat nhan giao tam hoan dong" };

const EMPTY_TXT = {
  open: ["Không có sự cố mới — tốt", "Sự cố được sinh tự động từ luật tuân thủ (chạm ngưỡng lỗ/drawdown/margin…), khi EA mất kết nối quá thời gian cho phép của nhóm, hoặc từ các điều kiện ngân sách. Khi điều kiện hết, hệ thống tự đóng."],
  ack: ["Chưa có sự cố nào đang được xử lý", "Sự cố sau khi bấm “Nhận” sẽ nằm ở đây cho đến khi đóng."],
  snoozed: ["Không có sự cố tạm hoãn", "Dùng “Tạm hoãn” để ẩn một sự cố đã biết trong một khoảng thời gian; hết hạn nó tự quay về mục Mới."],
  resolved: ["Chưa có sự cố nào đóng trong 24 giờ qua", "Sự cố được đóng thủ công hoặc tự đóng khi điều kiện không còn."],
};

const typing = (t) => !!t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

/** Trang Sự cố (hộp thư sự cố): #/su-co?st=open|ack|snoozed|resolved&gr=&sv=&as=&kd=&ac=&q=&gop=1&id= */
export default function Incidents() {
  const p = usePerm();
  const allowed = p.loading || p.has("incident.read");
  const canState = p.write("incident.read", { master: true });
  const [st, setSt] = useHashQuery("st", "open");
  const [sel, setSel] = useHashQuery("id", "");
  const f = useIncFilters();
  const status = STATUS.some((s) => s.id === st) ? st : "open";
  const params = useMemo(() => {
    const o = { status };
    if (f.sv) o.severity = f.sv; if (f.as) o.assignee = f.as; if (f.kd) o.kind = f.kd; if (f.gr) o.group = f.gr; if (f.ac) o.account = f.ac; if (f.gop) o.group_by = "cause";
    return o;
  }, [status, f.sv, f.as, f.kd, f.gr, f.ac, f.gop]);

  const q = useIncidentList(params, allowed);
  const countsQ = useIncidentCounts(allowed);
  const accts = useAccountIndex();
  const groups = useGroups({ enabled: allowed });
  const assignees = useAssignees({ enabled: allowed });
  const { act, busy } = useIncActions();
  const now = useNow();
  const wide = useMedia("(min-width: 1100px)");

  const acctMap = accts.data;
  const items = useMemo(() => (q.data?.items || []).filter((i) => matchQuery(i, f.q, acctMap?.get(i.account_id))), [q.data, f.q, acctMap]);
  const total = q.data?.items?.length || 0;
  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);
  const clusters = useMemo(() => {
    if (!f.gop || !q.data?.clusters) return null;
    return q.data.clusters.map((c) => {
      const ids = c.incident_ids.filter((i) => byId.has(i));
      return { ...c, incident_ids: ids, count: ids.length, accounts: ids.map((i) => byId.get(i).account_id) };
    }).filter((c) => c.count > 0);
  }, [f.gop, q.data, byId]);
  const flat = useMemo(() => (clusters ? clusters.flatMap((c) => c.incident_ids.map((i) => byId.get(i))) : items), [clusters, items, byId]);
  const counts = q.data?.counts || countsQ.data || {};

  // chọn nhiều + thẻ đang trỏ tới (phím j/k)
  const [checked, setChecked] = useState(() => new Set());
  const [cur, setCur] = useState("");
  const [snoozeFor, setSnoozeFor] = useState(null);   // {ids}
  const [resolveFor, setResolveFor] = useState(null); // {ids, title}
  const [pageErr, setPageErr] = useState(null);
  useEffect(() => { setChecked(new Set()); }, [status, f.sv, f.as, f.kd, f.gr, f.ac, f.q, f.gop]);
  useEffect(() => { setChecked((s) => { const n = new Set([...s].filter((i) => byId.has(i))); return n.size === s.size ? s : n; }); }, [byId]);
  useEffect(() => { if (wide && cur) setSel(cur); }, [cur, wide]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (cur) document.querySelector(`[data-inc="${cur}"]`)?.scrollIntoView({ block: "nearest" }); }, [cur]);

  const run = useCallback(async (vars, opt) => { const r = await act(vars, opt); setPageErr(r.ok || opt?.dialog ? null : r.error); return r; }, [act]);
  const rowAct = (type, inc) => {
    if (type === "snooze") setSnoozeFor({ ids: [inc.id] });
    else if (type === "resolve") setResolveFor({ ids: [inc.id], title: inc.title });
    else run({ type, id: inc.id });
  };
  const multiAct = (type, list) => {
    const ids = list.filter(isActive).map((i) => i.id);
    if (!ids.length) return;
    if (type === "snooze") setSnoozeFor({ ids });
    else if (type === "resolve") setResolveFor({ ids });
    else run({ type: "bulk", action: "ack", ids });
  };
  const doSnooze = async (minutes) => {
    const ids = snoozeFor.ids;
    const r = await run(ids.length === 1 ? { type: "snooze", id: ids[0], minutes } : { type: "bulk", action: "snooze", ids, minutes }, { dialog: true });
    if (r.ok) setChecked(new Set());
    return r;
  };
  const doResolve = async (text) => {
    const ids = resolveFor.ids;
    const r = await run(ids.length === 1 ? { type: "resolve", id: ids[0], text } : { type: "bulk", action: "resolve", ids }, { dialog: true });
    if (r.ok) setChecked(new Set());
    return r;
  };

  // phím tắt trong trang: j/k chuyển thẻ, a nhận, e đóng (Enter mở chi tiết, x chọn)
  const live = useRef({});
  live.current = { flat, cur, canState, busy, run, sel };
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || document.querySelector('[aria-modal="true"]')) return;
      const L = live.current, k = e.key;
      const idx = L.flat.findIndex((i) => i.id === L.cur);
      if (k === "j" || k === "k") {
        if (!L.flat.length) return;
        e.preventDefault();
        const n = k === "j" ? Math.min(L.flat.length - 1, idx + 1) : Math.max(0, idx < 0 ? 0 : idx - 1);
        setCur(L.flat[n].id);
      } else if (k === "Enter" && L.cur && e.target === document.body) { setSel(L.cur); }
      else if (k === "x" && L.cur && L.canState) { setChecked((s) => { const n = new Set(s); n.has(L.cur) ? n.delete(L.cur) : n.add(L.cur); return n; }); }
      else if ((k === "a" || k === "e") && L.cur) {
        const inc = L.flat[idx];
        if (!inc || !L.canState || L.busy) return;
        e.preventDefault();
        const next = L.flat[idx + 1] || L.flat[idx - 1];
        if (k === "a") {
          if (inc.status !== "open") { toast({ tone: "info", title: "Sự cố này không ở trạng thái Mới", ttl: 2500 }); return; }
          L.run({ type: "ack", id: inc.id }).then((r) => { if (r.ok && next) setCur(next.id); });
        } else {
          if (!isActive(inc)) return;
          L.run({ type: "resolve", id: inc.id }, { undo: { label: "Hoàn tác", run: () => L.run({ type: "reopen", id: inc.id }) } }).then((r) => { if (r.ok && next) setCur(next.id); });
        }
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [setSel]);

  const clearFilters = () => { for (const k of ["gr", "sv", "as", "kd", "ac", "q"]) f.set[k](""); };
  const onCheck = (id, on) => setChecked((s) => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });
  const open = (id) => { setCur(id); setSel(id); };
  const closeDetail = () => { setSel(""); };
  const selInc = sel ? byId.get(sel) || q.data?.items?.find((i) => i.id === sel) : null;
  const chosen = flat.filter((i) => checked.has(i.id));
  const allChecked = flat.length > 0 && chosen.length === flat.length;
  const hasFilters = !!(f.sv || f.as || f.kd || f.gr || f.ac || f.q);
  const updated = q.dataUpdatedAt ? new Date(q.dataUpdatedAt).toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false }) : "";

  const card = (inc) => (
    <IncidentCard key={inc.id} inc={inc} acct={acctMap?.get(inc.account_id)} now={now} current={cur === inc.id} selected={sel === inc.id}
      checked={checked.has(inc.id)} onCheck={onCheck} onOpen={open} onAct={rowAct} canAct={canState} canSelect={canState} busy={busy} />
  );

  if (!allowed) {
    return (
      <div className="inc-page">
        <PageHead title="Sự cố" right={<RoNote />} />
        <Banner tone="warn" title="Vai trò của bạn không có quyền xem sự cố">Liên hệ master để được cấp quyền “xem sự cố”.</Banner>
      </div>
    );
  }

  let body;
  if (q.isPending) body = <Skeleton rows={6} h={64} />;
  else if (q.isError && !q.data) body = isUnavailable(q.error) ? <Unavailable what="Hộp thư sự cố" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /> : <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} what="Danh sách sự cố" compact />;
  else if (!items.length) {
    const [t, h] = EMPTY_TXT[status];
    body = hasFilters || total
      ? <EmptyState compact title="Không có sự cố khớp bộ lọc" hint="Thử nới bộ lọc hoặc xoá ô tìm kiếm." actions={[{ label: "Xoá bộ lọc", onClick: clearFilters }]} />
      : <EmptyState compact title={t} hint={h} />;
  } else {
    body = (
      <ul className="fl-list" aria-label={`Danh sách sự cố: ${STATUS.find((s) => s.id === status).label}`}>
        {clusters
          ? clusters.map((c) => c.count > 1
            ? <ClusterCard key={c.cause_key} cluster={c} byId={byId} accts={acctMap} canAct={canState} busy={busy} forceOpen={c.incident_ids.includes(cur)} onClusterAct={multiAct}>{(list) => list.map(card)}</ClusterCard>
            : card(byId.get(c.incident_ids[0])))
          : items.map(card)}
      </ul>
    );
  }

  const detail = (
    <IncidentDetail id={sel} initial={selInc} assignees={assignees} onClose={wide ? closeDetail : undefined} busy={busy} act={run}
      onAct={rowAct} />
  );

  return (
    <div className="inc-page" data-page="incidents">
      <PageHead title="Sự cố" sub="Hộp thư sự cố của đội tài khoản: nhận, giao, tạm hoãn, ghi chú và đóng. Sự cố tự sinh từ luật tuân thủ, mất kết nối EA và điều kiện ngân sách."
        right={<><RoNote /><button type="button" className="btn" onClick={() => q.refetch()} disabled={q.isFetching} title={updated ? `Cập nhật lúc ${updated}` : undefined}><RefreshCw size={13} className={q.isFetching ? "ux-spin" : ""} aria-hidden="true" />{q.isFetching ? "Đang làm mới…" : `Làm mới${updated ? ` · ${updated}` : ""}`}</button></>} />

      {!canState && !p.loading && <Banner tone="info" title="Chế độ chỉ xem + ghi chú">{p.reason("incident.read", { master: true })} Nhận, giao, tạm hoãn, đóng và mở lại sự cố do master thực hiện; bạn vẫn có thể ghi chú.</Banner>}
      {q.isError && q.data && <Banner tone="warn" title="Dữ liệu có thể đã cũ" actions={<button type="button" className="btn" onClick={() => q.refetch()}>Thử lại</button>}>Không làm mới được lúc này ({q.error?.message}). Đang hiển thị dữ liệu lần tải trước{updated ? ` (${updated})` : ""}.</Banner>}
      <ErrLine error={pageErr} />

      <div className="inc-tabs" role="tablist" aria-label="Trạng thái sự cố">
        {STATUS.map((s) => {
          const n = counts[s.count];
          const hot = s.id === "open" && n > 0 && (counts.critical_active || 0) > 0;
          return (
            <button key={s.id} type="button" role="tab" id={`inc-tab-${s.id}`} aria-selected={status === s.id} aria-controls="inc-panel" onClick={() => { setSt(s.id); setCur(""); setSel(""); }}
              title={s.sub ? `${s.label} (${s.sub})` : undefined}>
              {s.label}<span className={cn("inc-n", hot && "hot")} aria-label={n != null ? `${n} sự cố` : undefined}>{n ?? "—"}</span>
            </button>
          );
        })}
        {counts.critical_active > 0 && <span className="ml-auto self-center pl-3 text-[12px] text-down inline-flex items-center gap-1 whitespace-nowrap"><Siren size={13} aria-hidden="true" /><b className="num">{counts.critical_active}</b> nghiêm trọng đang hoạt động</span>}
      </div>

      <Filters f={f} groups={groups} assignees={assignees} meId={p.me?.user_id} found={items.length} total={total} onClear={clearFilters} />

      {canState && flat.length > 0 && (
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <label className="fl-check !items-center"><input type="checkbox" className="fl-chk" checked={allChecked} onChange={(e) => setChecked(e.target.checked ? new Set(flat.map((i) => i.id)) : new Set())} /><span>Chọn tất cả {flat.length} sự cố đang hiển thị</span></label>
        </div>
      )}

      <div className={cn("inc-layout", wide && "wide")}>
        <div id="inc-panel" role="tabpanel" aria-labelledby={`inc-tab-${status}`} className="min-w-0" aria-busy={q.isFetching && !q.isPending}>{body}</div>
        {wide && <aside className="inc-detail-pane" aria-label="Chi tiết sự cố">{detail}</aside>}
      </div>
      {!wide && (
        <Dialog open={!!sel} onClose={closeDetail} variant="drawer" title="Chi tiết sự cố">
          <div className="p-3">{detail}</div>
        </Dialog>
      )}

      {canState && chosen.length > 0 && (
        <div className="fl-bulkbar" role="region" aria-label="Thao tác hàng loạt">
          <b>{chosen.length} sự cố đã chọn</b>
          <GBtn perm="incident.read" master className={PRIMARY} disabled={busy || !chosen.some((i) => i.status !== "ack" && isActive(i))} onClick={() => run({ type: "bulk", action: "ack", ids: chosen.filter(isActive).map((i) => i.id) }).then((r) => r.ok && setChecked(new Set()))}><Check size={14} aria-hidden="true" />Nhận</GBtn>
          <GBtn perm="incident.read" master disabled={busy || !chosen.some(isActive)} onClick={() => multiAct("snooze", chosen)}><BellOff size={14} aria-hidden="true" />Tạm hoãn</GBtn>
          <GBtn perm="incident.read" master disabled={busy || !chosen.some(isActive)} onClick={() => multiAct("resolve", chosen)}><CheckCheck size={14} aria-hidden="true" />Đóng</GBtn>
          <button type="button" className="btn ml-auto" onClick={() => setChecked(new Set())}><X size={13} aria-hidden="true" />Bỏ chọn</button>
        </div>
      )}

      <div className="inc-keys" aria-label="Phím tắt">
        <span><kbd>j</kbd> / <kbd>k</kbd> thẻ kế / trước</span>
        {canState && <><span><kbd>a</kbd> nhận</span><span><kbd>e</kbd> đóng (có “Hoàn tác”)</span><span><kbd>x</kbd> chọn</span></>}
        <span><kbd>Enter</kbd> mở chi tiết</span><span><kbd>i</kbd> mở trang này từ bất kỳ đâu</span>
      </div>

      <SnoozeDialog open={!!snoozeFor} count={snoozeFor?.ids.length || 1} busy={busy} onClose={() => setSnoozeFor(null)} onPick={doSnooze} />
      <ResolveDialog open={!!resolveFor} count={resolveFor?.ids.length || 1} title={resolveFor?.title} busy={busy} onClose={() => setResolveFor(null)} onConfirm={doResolve} />
    </div>
  );
}
