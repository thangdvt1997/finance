import { useId, useState } from "react";
import { Link2, Plus, Trash2 } from "lucide-react";
import { Dialog } from "../../dialog";
import { Panel, Seg } from "../../ui";
import { EmptyState, ErrorState, TableSkeleton } from "../../ux/States";
import { toast } from "../../../ux/bus";
import { api, useFleetMut, useFleetList, useGroups, useTags, usePerm, KIND_VN } from "../../../lib/fleetQueries";
import { isUnavailable } from "../../../lib/fleetApi";
import { ErrLine, Field, GBtn, GroupChip, PRIMARY, TagChip, Unavailable, useDebounced } from "../bits";
import { SCOPE_VN } from "./schema";

const KINDS_SCOPE = ["all", "group", "tag", "account"];
const INV = ["assign", "tpl", "compliance"];

function ScopeCell({ a, groups }) {
  const g = a.scope_type === "group" ? (groups || []).find((x) => x.id === a.scope_ref) : null;
  if (a.scope_type === "all") return <span>Tất cả tài khoản</span>;
  if (a.scope_type === "group") return <span className="inline-flex items-center gap-1 flex-wrap">Nhóm {g ? <GroupChip g={g} /> : <b>{a.scope_label || "(đã xoá)"}</b>}</span>;
  if (a.scope_type === "tag") return <span className="inline-flex items-center gap-1">Tag <TagChip t={a.scope_ref} /></span>;
  return <span>Tài khoản <b className="num">{a.scope_label || a.scope_ref}</b></span>;
}

function AssignDialog({ templates, groups, tags, preset, onClose }) {
  const uid = useId();
  const [tid, setTid] = useState(preset?.id || templates[0]?.id || "");
  const [st, setSt] = useState("group");
  const [ref, setRef] = useState("");
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const [enabled, setEnabled] = useState(true);
  const [notify, setNotify] = useState(false);
  const [touched, setTouched] = useState(false);
  const acc = useFleetList({ q: dq.trim(), limit: 8 }, { enabled: st === "account" && dq.trim().length >= 2 });
  const save = useFleetMut((b) => api.post("/rules/assignments", b), INV, { onSuccess: () => { toast({ tone: "ok", title: "Đã gán luật" }); onClose(); } });
  const needRef = st !== "all";
  const err = !tid ? "Chọn mẫu luật." : needRef && !ref ? (st === "group" ? "Chọn một nhóm." : st === "tag" ? "Chọn một tag." : "Chọn một tài khoản.") : "";
  const submit = (e) => { e.preventDefault(); setTouched(true); if (err) return; save.mutate({ template_id: tid, scope: { type: st, ref: needRef ? ref : "" }, enabled, notify_client: notify }); };
  const accounts = acc.data?.items || [];
  return (
    <Dialog open onClose={onClose} title="Gán luật cho phạm vi" className="!min-w-0 !max-w-[560px]"
      footer={<><button type="button" className="btn" onClick={onClose}>Huỷ</button>
        <GBtn type="submit" form={`${uid}-f`} master perm="compliance.read" className={PRIMARY} disabled={save.isPending}><Link2 size={14} aria-hidden="true" />{save.isPending ? "Đang gán…" : "Gán luật"}</GBtn></>}>
      <form id={`${uid}-f`} onSubmit={submit} noValidate className="p-3 grid gap-3 grid-cols-[minmax(0,1fr)]">
        <Field label="Mẫu luật" htmlFor={`${uid}-t`} hint="Mẫu luật sẽ được đánh giá liên tục cho mọi tài khoản trong phạm vi.">
          <select id={`${uid}-t`} className="field" value={tid} onChange={(e) => setTid(e.target.value)} data-autofocus>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.name} — {KIND_VN[t.kind] || t.kind}</option>)}
          </select>
        </Field>
        <div className="fl-field">
          <span className="fl-lab">Phạm vi</span>
          <Seg label="Loại phạm vi" value={st} onChange={(v) => { setSt(v); setRef(""); setQ(""); }} options={KINDS_SCOPE.map((k) => ({ value: k, label: SCOPE_VN[k] }))} />
        </div>
        {st === "group" && (
          <Field label="Nhóm" htmlFor={`${uid}-g`} hint="Áp cho mọi tài khoản thuộc nhóm này." error={touched ? err : ""}>
            <select id={`${uid}-g`} className="field" value={ref} onChange={(e) => setRef(e.target.value)}>
              <option value="">— Chọn nhóm —</option>
              {groups.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.members ?? 0} TK)</option>)}
            </select>
          </Field>)}
        {st === "tag" && (
          <Field label="Tag" htmlFor={`${uid}-tg`} hint="Áp cho mọi tài khoản có tag này." error={touched ? err : ""}>
            <select id={`${uid}-tg`} className="field" value={ref} onChange={(e) => setRef(e.target.value)}>
              <option value="">— Chọn tag —</option>
              {tags.map((t) => { const n = typeof t === "string" ? t : t.tag; return <option key={n} value={n}>#{n}{t.count != null ? ` (${t.count} TK)` : ""}</option>; })}
            </select>
          </Field>)}
        {st === "account" && (
          <Field label="Tài khoản" htmlFor={`${uid}-a`} hint="Gõ ít nhất 2 ký tự của số tài khoản hoặc nhãn rồi chọn." error={touched ? err : ""}>
            <input id={`${uid}-a`} className="field" value={q} onChange={(e) => { setQ(e.target.value); setRef(""); }} placeholder="vd mt5:1005…" autoComplete="off" />
            {ref && <span className="fl-help">Đã chọn: <b className="num">{ref}</b></span>}
            {dq.trim().length >= 2 && (
              <ul aria-label="Kết quả tìm tài khoản" className="m-0 p-0 list-none grid gap-1 mt-1">
                {acc.isFetching && !accounts.length && <li className="text-muted text-[12px]">Đang tìm…</li>}
                {!acc.isFetching && !accounts.length && <li className="text-muted text-[12px]">Không thấy tài khoản phù hợp.</li>}
                {accounts.map((a) => (
                  <li key={a.account_id}>
                    <button type="button" className="btn w-full !justify-start" aria-pressed={ref === a.account_id} onClick={() => setRef(a.account_id)}><span className="num">{a.account_id}</span><span className="text-muted truncate">{a.label}</span></button>
                  </li>))}
              </ul>)}
          </Field>)}
        <label className="fl-check"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /><span>Bật ngay sau khi gán</span></label>
        <label className="fl-check"><input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /><span>Thông báo cho khách đã opt-in khi sát/vi phạm luật<span className="block text-muted text-[11.5px]">Chỉ gửi cho khách tự bật nhận thông báo trong cổng của họ.</span></span></label>
        {touched && err && st === "all" && <div role="alert" className="text-down text-[12px]">{err}</div>}
        <ErrLine error={save.error} />
      </form>
    </Dialog>
  );
}

function DelDialog({ a, onClose }) {
  const del = useFleetMut(() => api.del(`/rules/assignments/${a.id}`), INV, { onSuccess: () => { toast({ tone: "ok", title: "Đã gỡ phép gán" }); onClose(); } });
  return (
    <Dialog open onClose={onClose} title="Gỡ phép gán luật?" className="!min-w-0 !max-w-[440px]"
      footer={<><button type="button" className="btn" onClick={onClose}>Huỷ</button>
        <GBtn master perm="compliance.read" className="!bg-down !text-white !border-transparent" disabled={del.isPending} onClick={() => del.mutate()}><Trash2 size={14} aria-hidden="true" />{del.isPending ? "Đang gỡ…" : "Gỡ phép gán"}</GBtn></>}>
      <div className="p-3 grid gap-2 text-[13px]">
        <p className="m-0">Gỡ luật <b>{a.template_name}</b> khỏi phạm vi này. Các sự cố luật liên quan sẽ được đóng.</p>
        <ErrLine error={del.error} />
      </div>
    </Dialog>
  );
}

/** Danh sách phép gán luật + bật/tắt + thông báo khách + xoá + tạo mới. presetTpl: mẫu được chọn từ danh sách mẫu (mở sẵn hộp thoại). */
export default function AssignmentsPanel({ asg, tpl, presetTpl, onCloseAssign }) {
  const p = usePerm();
  const gq = useGroups(); const tq = useTags();
  const [open, setOpen] = useState(false);
  const [del, setDel] = useState(null);
  const groups = gq.data?.items || [];
  const tags = tq.data?.items || [];
  const templates = tpl.data?.items || [];
  const rows = asg.data?.items || [];
  const tog = useFleetMut(({ id, ...b }) => api.patch(`/rules/assignments/${id}`, b), INV);
  const reason = p.reason("compliance.read", { master: true });
  const members = (a) => (a.scope_type === "group" ? groups.find((g) => g.id === a.scope_ref)?.members : a.scope_type === "account" ? 1 : null);
  const noTpl = !templates.length;
  const close = () => { setOpen(false); onCloseAssign?.(); };
  return (
    <Panel title="Gán luật" pad={false} right={<GBtn master perm="compliance.read" className={PRIMARY} disabled={noTpl} title={noTpl ? "Cần tạo mẫu luật trước" : undefined} onClick={() => setOpen(true)}><Plus size={14} aria-hidden="true" />Gán luật mới</GBtn>}>
      {asg.isPending ? <div className="p-3"><TableSkeleton rows={3} cols={5} /></div>
        : asg.isError ? (isUnavailable(asg.error) ? <Unavailable what="Gán luật" error={asg.error} onRetry={() => asg.refetch()} retrying={asg.isFetching} /> : <ErrorState compact error={asg.error} onRetry={() => asg.refetch()} retrying={asg.isFetching} what="phép gán luật" />)
        : !rows.length ? <div className="p-3"><EmptyState compact title="Chưa gán luật nào" hint={noTpl ? "Tạo mẫu luật trước, sau đó gán cho nhóm, tag, tài khoản hoặc toàn đội." : "Bấm “Gán luật mới” để áp một mẫu cho nhóm/tag/tài khoản. Bảng tuân thủ sẽ có dữ liệu sau vài phút."} /></div>
        : (
          <div className="fl-tablewrap relative">
            <table className="fl-tbl">
              <caption className="fl-sr">Các phép gán luật</caption>
              <thead><tr><th scope="col">Luật</th><th scope="col">Phạm vi</th><th scope="col" className="r">TK ảnh hưởng</th><th scope="col">Bật</th><th scope="col">Báo khách</th><th scope="col"><span className="fl-sr">Thao tác</span></th></tr></thead>
              <tbody>
                {rows.map((a) => {
                  const n = members(a);
                  return (
                    <tr key={a.id} style={{ cursor: "default" }}>
                      <td><b>{a.template_name}</b><span className="c-sub">{KIND_VN[a.kind] || a.kind}</span></td>
                      <td><ScopeCell a={a} groups={groups} /></td>
                      <td className="r num">{n != null ? n : <span className="text-muted" title="Không suy ra được số tài khoản từ phạm vi này">—</span>}</td>
                      <td><label className="fl-check !items-center"><input type="checkbox" checked={!!a.enabled} disabled={!!reason || tog.isPending} onChange={(e) => tog.mutate({ id: a.id, enabled: e.target.checked })} aria-label={`Bật luật ${a.template_name}`} title={reason || undefined} /><span>{a.enabled ? "Bật" : "Tắt"}</span></label></td>
                      <td><label className="fl-check !items-center"><input type="checkbox" checked={!!a.notify_client} disabled={!!reason || tog.isPending} onChange={(e) => tog.mutate({ id: a.id, notify_client: e.target.checked })} aria-label={`Thông báo cho khách đã opt-in — ${a.template_name}`} title={reason || "Thông báo cho khách đã opt-in"} /><span className="max-sm:hidden">{a.notify_client ? "Có" : "Không"}</span></label></td>
                      <td className="r"><GBtn master perm="compliance.read" className="!h-7 !px-2" onClick={() => setDel(a)} aria-label={`Gỡ phép gán ${a.template_name}`}><Trash2 size={13} aria-hidden="true" /><span className="fl-sr">Gỡ</span></GBtn></td>
                    </tr>);
                })}
              </tbody>
            </table>
          </div>)}
      {tog.error && <div className="p-3 pt-0"><ErrLine error={tog.error} /></div>}
      {reason && rows.length > 0 && <p className="m-0 px-3 pb-2 text-[11.5px] text-muted">{reason}</p>}
      {(open || presetTpl) && <AssignDialog templates={templates} groups={groups} tags={tags} preset={presetTpl} onClose={close} />}
      {del && <DelDialog a={del} onClose={() => setDel(null)} />}
    </Panel>
  );
}
