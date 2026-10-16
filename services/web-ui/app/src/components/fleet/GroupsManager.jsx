// Quản lý nhóm: tạo / đổi tên + màu / xoá, thành viên (thêm-gỡ), chính sách cảnh báo của nhóm. API: groups, groups/{id}, groups/{id}/members, groups/{id}/policy.
import { useEffect, useState } from "react";
import { Check, Plus, Trash2, Users } from "lucide-react";
import { Dialog } from "../dialog";
import { toast } from "../../ux/bus";
import { fdel, fpatch, fpost, fput } from "../../lib/fleetApi";
import { SEV_VN, useAssignees, useFleetList, useFleetMut, useGroupPolicy, useGroups, usePerm } from "../../lib/fleetQueries";
import { Banner, ErrLine, Field, GBtn, GroupChip, PRIMARY, Unavailable, useDebounced } from "./bits";

const COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#ec4899", "#94a3b8"];

function Swatches({ value, onChange }) {
  return (
    <div role="radiogroup" aria-label="Màu nhóm" className="flex flex-wrap gap-1.5">
      {COLORS.map((c) => (
        <button key={c} type="button" role="radio" aria-checked={value === c} aria-label={`Màu ${c}`} onClick={() => onChange(c)}
          style={{ background: c, width: 24, height: 24, borderRadius: 6, border: value === c ? "2px solid var(--fg)" : "1px solid var(--line2)", display: "grid", placeItems: "center", cursor: "pointer" }}>
          {value === c && <Check size={13} color="#fff" aria-hidden="true" />}
        </button>
      ))}
    </div>
  );
}

function PolicyForm({ g, canEdit }) {
  const q = useGroupPolicy(g.id);
  const as = useAssignees().data?.items || [];
  const [p, setP] = useState(null);
  useEffect(() => { if (q.data) { const d = q.data.policy || q.data; setP({ ea_offline_grace_min: d.ea_offline_grace_min ?? 5, min_severity: d.min_severity || "warning", auto_assign_user_id: d.auto_assign_user_id || "", client_notify: !!d.client_notify }); } }, [q.data]);
  const save = useFleetMut((v) => fput(`/groups/${g.id}/policy`, v), ["policy", "groups"], { onSuccess: () => toast({ tone: "ok", title: "Đã lưu chính sách cảnh báo", body: g.name }) });
  if (q.isPending) return <p className="m-0 text-muted text-[12.5px]">Đang tải chính sách…</p>;
  if (q.isError) return <Unavailable what="Chính sách cảnh báo nhóm" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  if (!p) return null;
  const submit = (e) => { e.preventDefault(); const body = { ea_offline_grace_min: Number(p.ea_offline_grace_min), min_severity: p.min_severity, client_notify: p.client_notify }; if (p.auto_assign_user_id) body.auto_assign_user_id = p.auto_assign_user_id; save.mutate(body); };
  return (
    <form onSubmit={submit} className="grid gap-3">
      <div className="fl-formgrid">
        <Field label="Chờ trước khi báo mất kết nối EA (phút)" htmlFor="pol-grace" hint="EA im lặng quá số phút này mới mở sự cố 'mất kết nối' cho tài khoản trong nhóm. Tránh báo giả khi MT khởi động lại.">
          <input id="pol-grace" type="number" min={1} max={1440} className="field num" value={p.ea_offline_grace_min} disabled={!canEdit} onChange={(e) => setP({ ...p, ea_offline_grace_min: e.target.value })} /></Field>
        <Field label="Mức tối thiểu mở sự cố" htmlFor="pol-sev" hint="Chỉ tạo sự cố cho điều kiện từ mức này trở lên.">
          <select id="pol-sev" className="field" value={p.min_severity} disabled={!canEdit} onChange={(e) => setP({ ...p, min_severity: e.target.value })}>{Object.entries(SEV_VN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Tự giao cho" htmlFor="pol-as" hint="Sự cố mới của nhóm tự được giao cho người này.">
          <select id="pol-as" className="field" value={p.auto_assign_user_id} disabled={!canEdit} onChange={(e) => setP({ ...p, auto_assign_user_id: e.target.value })}><option value="">— không tự giao —</option>{as.map((u) => <option key={u.user_id} value={u.user_id}>{u.name} ({u.role})</option>)}</select></Field>
      </div>
      <label className="fl-check"><input type="checkbox" checked={p.client_notify} disabled={!canEdit} onChange={(e) => setP({ ...p, client_notify: e.target.checked })} /><span>Thông báo cho khách của nhóm này (chỉ khách đã tự bật opt-in nhận thông báo)</span></label>
      <ErrLine error={save.error} />
      <div><GBtn master perm="fleet.read" type="submit" className={PRIMARY} disabled={save.isPending}>{save.isPending ? "Đang lưu…" : "Lưu chính sách"}</GBtn></div>
    </form>
  );
}

function Members({ g, canEdit }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const list = useFleetList({ group: g.id, limit: 200 });
  const found = useFleetList({ q: dq, limit: 8 }, { enabled: dq.trim().length >= 2 });
  const memberIds = new Set((list.data?.items || []).map((r) => r.account_id));
  const add = useFleetMut((ids) => fpost(`/groups/${g.id}/members`, { account_ids: ids }), ["fleet", "groups"]);
  const rm = useFleetMut((id) => fdel(`/groups/${g.id}/members/${encodeURIComponent(id)}`), ["fleet", "groups"]);
  return (
    <div className="grid gap-3">
      {canEdit && (
        <div className="grid gap-1">
          <Field label="Thêm tài khoản vào nhóm" htmlFor="gm-q" help="Gõ ≥ 2 ký tự: mã, nhãn hoặc số tài khoản.">
            <input id="gm-q" className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm tài khoản…" /></Field>
          {dq.trim().length >= 2 && (
            <ul className="m-0 p-0 list-none rounded-md border border-line max-h-40 overflow-auto">
              {found.isPending && <li className="p-2 text-[12px] text-muted">Đang tìm…</li>}
              {(found.data?.items || []).map((r) => (
                <li key={r.account_id} className="flex items-center gap-2 px-2 py-1 border-b border-line last:border-0 text-[12.5px]">
                  <span className="min-w-0 flex-1 truncate"><b>{r.label || r.login}</b> <span className="num text-muted">{r.account_id}</span></span>
                  {memberIds.has(r.account_id) ? <span className="text-[11.5px] text-muted">đã trong nhóm</span> : <button type="button" className="btn !h-7" onClick={() => add.mutate([r.account_id], { onSuccess: () => setQ("") })}><Plus size={13} aria-hidden="true" />Thêm</button>}
                </li>))}
              {found.data && !(found.data.items || []).length && <li className="p-2 text-[12px] text-muted">Không tìm thấy.</li>}
            </ul>
          )}
        </div>
      )}
      <ErrLine error={add.error || rm.error} />
      {list.isPending ? <p className="m-0 text-[12.5px] text-muted">Đang tải thành viên…</p> : list.isError ? <ErrLine error={list.error} />
        : !(list.data?.items || []).length ? <p className="m-0 text-[12.5px] text-muted">Nhóm chưa có tài khoản nào.</p>
        : <ul className="fl-list">{list.data.items.map((r) => (
            <li key={r.account_id} className="fl-card flex-row" style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
              <span className="min-w-0 flex-1 truncate text-[12.5px]"><b>{r.label || r.login}</b> <span className="num text-muted">{r.account_id}</span></span>
              {canEdit && <button type="button" className="btn !h-7 !px-2" onClick={() => rm.mutate(r.account_id)} aria-label={`Gỡ ${r.account_id} khỏi nhóm`}><Trash2 size={13} aria-hidden="true" /></button>}
            </li>))}</ul>}
    </div>
  );
}

function Editor({ g, canEdit, onDeleted }) {
  const [name, setName] = useState(g.name);
  const [desc, setDesc] = useState(g.description || "");
  const [color, setColor] = useState(g.color || COLORS[0]);
  const [sub, setSub] = useState("thanh-vien");
  const [del, setDel] = useState(false);
  useEffect(() => { setName(g.name); setDesc(g.description || ""); setColor(g.color || COLORS[0]); setSub("thanh-vien"); setDel(false); }, [g.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useFleetMut(() => fpatch(`/groups/${g.id}`, { name: name.trim(), description: desc.trim(), color }), ["groups", "fleet"], { onSuccess: () => toast({ tone: "ok", title: "Đã lưu nhóm", body: name }) });
  const rm = useFleetMut(() => fdel(`/groups/${g.id}`), ["groups", "fleet"], { onSuccess: () => { toast({ tone: "info", title: "Đã xoá nhóm", body: g.name }); onDeleted(); } });
  const dirty = name.trim() !== g.name || desc.trim() !== (g.description || "") || color !== (g.color || COLORS[0]);
  return (
    <div className="grid gap-3 min-w-0">
      <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="grid gap-3">
        <div className="fl-formgrid">
          <Field label="Tên nhóm" htmlFor="ge-name"><input id="ge-name" className="field" maxLength={60} required value={name} disabled={!canEdit} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Mô tả" htmlFor="ge-desc"><input id="ge-desc" className="field" maxLength={200} value={desc} disabled={!canEdit} onChange={(e) => setDesc(e.target.value)} /></Field>
        </div>
        <Field label="Màu"><Swatches value={color} onChange={canEdit ? setColor : () => {}} /></Field>
        <ErrLine error={save.error || rm.error} />
        <div className="flex flex-wrap gap-2">
          <GBtn master perm="fleet.read" type="submit" className={PRIMARY} disabled={!dirty || !name.trim() || save.isPending}>{save.isPending ? "Đang lưu…" : "Lưu thay đổi"}</GBtn>
          {!del ? <GBtn master perm="fleet.read" onClick={() => setDel(true)}><Trash2 size={13} aria-hidden="true" />Xoá nhóm</GBtn>
            : <span className="inline-flex items-center gap-2 text-[12.5px]">Xoá nhóm “{g.name}”? Tài khoản không bị xoá.<button type="button" className="btn !bg-down !text-white !border-transparent" onClick={() => rm.mutate()} disabled={rm.isPending}>Xác nhận xoá</button><button type="button" className="btn" onClick={() => setDel(false)}>Huỷ</button></span>}
        </div>
      </form>
      <div role="tablist" aria-label="Thành viên và chính sách" className="fl-tabs">
        {[["thanh-vien", "Thành viên"], ["chinh-sach", "Chính sách cảnh báo"]].map(([id, l]) => <button key={id} role="tab" aria-selected={sub === id} onClick={() => setSub(id)}>{l}</button>)}
      </div>
      {sub === "thanh-vien" ? <Members g={g} canEdit={canEdit} /> : <PolicyForm g={g} canEdit={canEdit} />}
    </div>
  );
}

export default function GroupsManager({ open, onClose }) {
  const perm = usePerm();
  const q = useGroups();
  const [sel, setSel] = useState(null);
  const [name, setName] = useState("");
  const [color, setColor] = useState(COLORS[0]);
  const items = q.data?.items || [];
  const g = items.find((x) => x.id === sel);
  const canEdit = perm.write("fleet.read", { master: true });
  const create = useFleetMut(() => fpost("/groups", { name: name.trim(), color }), ["groups"], { onSuccess: (r) => { setName(""); setSel(r.id); toast({ tone: "ok", title: "Đã tạo nhóm", body: r.name }); } });
  useEffect(() => { if (open && !sel && items.length) setSel(items[0].id); }, [open, items.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Dialog open={open} onClose={onClose} title="Quản lý nhóm" description="Nhóm là đơn vị để lọc, gán luật, giao nhân sự và đặt chính sách cảnh báo." className="sm:max-w-[960px]">
      <div className="p-3 grid gap-3 md:grid-cols-[15rem_minmax(0,1fr)] items-start">
        <div className="grid gap-3">
          {q.isPending ? <p className="m-0 text-[12.5px] text-muted">Đang tải…</p> : q.isError ? <Unavailable what="Nhóm" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
            : (
              <ul className="fl-list" aria-label="Danh sách nhóm">
                {items.map((x) => (
                  <li key={x.id}><button type="button" className="fl-card w-full text-left cursor-pointer" aria-current={sel === x.id ? "true" : undefined} onClick={() => setSel(x.id)} style={{ font: "inherit", color: "inherit" }}>
                    <span className="flex items-center justify-between gap-2"><GroupChip g={x} /><span className="text-[11.5px] text-muted num"><Users size={11} className="inline mr-0.5" aria-hidden="true" />{x.members}</span></span>
                    {x.description && <span className="text-[11.5px] text-muted truncate">{x.description}</span>}
                  </button></li>))}
                {!items.length && <li className="text-[12.5px] text-muted">Chưa có nhóm. Tạo nhóm đầu tiên bên dưới.</li>}
              </ul>)}
          <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="grid gap-2 rounded-lg border border-line p-2">
            <Field label="Nhóm mới" htmlFor="gn-name"><input id="gn-name" className="field" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} disabled={!canEdit} placeholder={canEdit ? "Ví dụ: Khách VIP" : "Chỉ master tạo nhóm"} /></Field>
            <Swatches value={color} onChange={setColor} />
            <ErrLine error={create.error} />
            <GBtn master perm="fleet.read" type="submit" className={PRIMARY} disabled={!name.trim() || create.isPending}><Plus size={13} aria-hidden="true" />Tạo nhóm</GBtn>
          </form>
        </div>
        <div className="min-w-0">
          {g ? <Editor g={g} canEdit={canEdit} onDeleted={() => setSel(null)} /> : <Banner tone="info">Chọn một nhóm để sửa, quản lý thành viên và chính sách cảnh báo.</Banner>}
        </div>
      </div>
    </Dialog>
  );
}
