import { useEffect, useState } from "react";
import { CalendarClock, CheckCircle2, EyeOff, Loader2, MinusCircle, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { Dialog } from "../../dialog";
import { Panel, Skeleton } from "../../ui";
import { toast } from "../../../ux/bus";
import { useGroups, usePerm } from "../../../lib/fleetQueries";
import { Banner, ErrLine, Field, GBtn, Pill, PRIMARY, RoNote, Unavailable } from "../bits";
import { ACC_RE, KIND_VN, KINDS, useSchedules, useScheduleMut } from "./reportsApi";

const SCOPE_VN = { group: "Nhóm", tag: "Tag", account: "Tài khoản", all: "Tất cả tài khoản" };
const MAX = 200;
const blank = { scope: { type: "group", ref: "" }, kind: "daily", hour: 7, enabled: true, auto_release: false };

function Form({ init, groups, onSave, onClose, busy, error }) {
  const [f, setF] = useState(init);
  const [touched, setTouched] = useState(false);
  useEffect(() => { setF(init); setTouched(false); }, [init]);
  const t = f.scope.type, ref = (f.scope.ref || "").trim();
  const refErr = t === "all" ? null : !ref ? "Cần chọn/nhập phạm vi." : t === "account" && !ACC_RE.test(ref) ? "ID tài khoản không hợp lệ (chữ, số, : . _ -)." : t === "tag" && ref.length > 64 ? "Tối đa 64 ký tự." : null;
  const set = (p) => setF((x) => ({ ...x, ...p }));
  const submit = () => { setTouched(true); if (refErr) return; onSave({ ...f, scope: { type: t, ref: t === "all" ? null : ref } }); };
  return (
    <Dialog open onClose={busy ? undefined : onClose} title={f.schedule_id ? "Sửa lịch báo cáo" : "Thêm lịch báo cáo"}
      footer={<><RoNote className="mr-auto" /><button type="button" className="btn" onClick={onClose} disabled={busy}>Huỷ</button>
        <button type="button" className={`btn ${PRIMARY}`} onClick={submit} disabled={busy}>{busy && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}Lưu lịch</button></>}>
      <div className="grid gap-3 p-3">
        <div className="fl-formgrid">
          <Field label="Phạm vi" htmlFor="sc-type">
            <select id="sc-type" className="field" value={t} onChange={(e) => set({ scope: { type: e.target.value, ref: "" } })}>{Object.entries(SCOPE_VN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </Field>
          {t !== "all" && (
            <Field label={t === "group" ? "Nhóm" : t === "tag" ? "Tên tag" : "ID tài khoản"} htmlFor="sc-ref" error={touched ? refErr : null}>
              {t === "group"
                ? <select id="sc-ref" className="field" value={f.scope.ref || ""} onChange={(e) => set({ scope: { type: t, ref: e.target.value } })}><option value="">— chọn nhóm —</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select>
                : <input id="sc-ref" className="field num" value={f.scope.ref || ""} onChange={(e) => set({ scope: { type: t, ref: e.target.value } })} placeholder={t === "tag" ? "vd: vip" : "vd: mt5:99000001"} autoComplete="off" />}
            </Field>)}
          <Field label="Loại báo cáo" htmlFor="sc-kind">
            <select id="sc-kind" className="field" value={f.kind} onChange={(e) => set({ kind: e.target.value })}>{KINDS.map((k) => <option key={k} value={k}>{KIND_VN[k]}</option>)}</select>
          </Field>
          <Field label="Giờ chạy" htmlFor="sc-hour" help="Theo múi giờ cấu hình của dịch vụ báo cáo.">
            <select id="sc-hour" className="field num" value={f.hour} onChange={(e) => set({ hour: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select>
          </Field>
        </div>
        <label className="fl-check"><input type="checkbox" checked={f.enabled} onChange={(e) => set({ enabled: e.target.checked })} /><span>Đang bật (tự tạo báo cáo theo lịch)</span></label>
        <label className="fl-check"><input type="checkbox" checked={f.auto_release} onChange={(e) => set({ auto_release: e.target.checked })} /><span>Tự phát hành cho khách ngay khi tạo xong</span></label>
        {f.auto_release && <Banner tone="warn" title="Khách sẽ thấy báo cáo mà không qua kiểm tra của bạn">{t === "all" ? "Phạm vi “Tất cả tài khoản” — mọi khách đều nhận báo cáo tự động. " : ""}Nên để tắt cho đến khi bạn đã kiểm tra chất lượng vài bản nháp.</Banner>}
        <ErrLine error={error} />
      </div>
    </Dialog>
  );
}

export default function Schedules() {
  const p = usePerm();
  const q = useSchedules(p.isMaster);
  const groups = useGroups();
  const gl = Array.isArray(groups.data) ? groups.data : groups.data?.items || [];
  const gname = (id) => gl.find((g) => g.id === id)?.name;
  const mut = useScheduleMut();
  const [edit, setEdit] = useState(null);
  const [del, setDel] = useState(null);
  const [err, setErr] = useState(null);
  const list = q.data || [];
  const save = async (next, ok) => {
    setErr(null);
    try {
      await mut.mutateAsync(next.map(({ schedule_id, scope, kind, hour, enabled, auto_release }) => ({ ...(schedule_id ? { schedule_id } : {}), scope, kind, hour, enabled, auto_release })));
      toast({ tone: "ok", title: ok }); setEdit(null); setDel(null);
    } catch (e) { setErr(e.code === "unavailable" ? Object.assign(new Error("Máy chủ chưa mở thao tác ghi lịch (chưa khả dụng)."), { code: "unavailable" }) : e); }
  };
  const upsert = (s) => save(s.schedule_id ? list.map((x) => (x.schedule_id === s.schedule_id ? s : x)) : [...list, s], "Đã lưu lịch báo cáo");
  const toggle = (s) => save(list.map((x) => (x.schedule_id === s.schedule_id ? { ...x, enabled: !x.enabled } : x)), s.enabled ? "Đã tạm dừng lịch" : "Đã bật lịch");

  if (!p.isMaster) return <Panel title="Lịch tự động" icon={CalendarClock}><Banner tone="info" title="Chỉ master xem và chỉnh lịch tự động">Vai trò của bạn xem được danh sách báo cáo đã tạo ở thẻ “Báo cáo”.</Banner></Panel>;
  return (
    <Panel title="Lịch tạo báo cáo tự động" icon={CalendarClock} pad={false}
      right={<><span className="fl-count num">{q.data ? `${list.length}/${MAX}` : ""}</span>
        <GBtn master perm="report.read" className={PRIMARY} disabled={q.isError || list.length >= MAX} onClick={() => { setErr(null); setEdit({ ...blank }); }}><Plus size={14} aria-hidden="true" />Thêm lịch</GBtn></>}>
      {q.isPending ? <div className="p-3"><Skeleton rows={4} h={18} /></div>
        : q.isError ? <div className="p-3">{q.error.code === "unavailable" || q.error.code === "network" ? <Unavailable what="Lịch báo cáo" error={q.error} onRetry={q.refetch} retrying={q.isFetching} /> : <ErrLine error={q.error} />}</div>
        : list.length === 0 ? (
          <div className="p-3"><div className="fl-empty"><b>Chưa có lịch nào</b><span>Thêm lịch để hệ thống tự tạo báo cáo ngày/tuần/tháng cho một nhóm, tag hoặc tài khoản. Mặc định tạo ở dạng nháp — bạn kiểm tra rồi mới phát hành.</span>
            <GBtn master perm="report.read" className={PRIMARY} onClick={() => setEdit({ ...blank })}><Plus size={14} aria-hidden="true" />Thêm lịch đầu tiên</GBtn></div></div>)
        : (
          <div className="fl-tablewrap relative">
            <table className="fl-tbl">
              <caption className="fl-sr">Lịch tạo báo cáo tự động</caption>
              <thead><tr><th scope="col">Phạm vi</th><th scope="col">Loại</th><th scope="col">Giờ</th><th scope="col">Trạng thái</th><th scope="col">Với khách</th><th scope="col"><span className="fl-sr">Thao tác</span></th></tr></thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.schedule_id} style={{ cursor: "default" }}>
                    <td><b>{SCOPE_VN[s.scope?.type] || s.scope?.type}</b>{s.scope?.ref ? <span className="num text-muted"> · {s.scope.type === "group" ? gname(s.scope.ref) || s.scope.ref : s.scope.ref}</span> : null}</td>
                    <td>{KIND_VN[s.kind] || s.kind}</td>
                    <td className="num">{String(s.hour).padStart(2, "0")}:00</td>
                    <td>{s.enabled ? <Pill tone="ok" icon={CheckCircle2}>Đang bật</Pill> : <Pill tone="mute" icon={MinusCircle}>Tạm dừng</Pill>}</td>
                    <td>{s.auto_release ? <Pill tone="warn" icon={Send} title="Khách thấy ngay khi tạo xong">Tự phát hành</Pill> : <Pill tone="mute" icon={EyeOff}>Tạo nháp</Pill>}</td>
                    <td><div className="flex flex-wrap gap-1.5 justify-end">
                      <GBtn master perm="report.read" onClick={() => toggle(s)} disabled={mut.isPending}>{s.enabled ? "Tạm dừng" : "Bật"}</GBtn>
                      <GBtn master perm="report.read" onClick={() => { setErr(null); setEdit(s); }} aria-label={`Sửa lịch ${SCOPE_VN[s.scope?.type]} ${KIND_VN[s.kind]}`}><Pencil size={13} aria-hidden="true" />Sửa</GBtn>
                      <GBtn master perm="report.read" onClick={() => { setErr(null); setDel(s); }} aria-label={`Xoá lịch ${SCOPE_VN[s.scope?.type]} ${KIND_VN[s.kind]}`}><Trash2 size={13} aria-hidden="true" />Xoá</GBtn>
                    </div></td>
                  </tr>))}
              </tbody>
            </table>
          </div>)}
      {err && !edit && !del && <div className="p-3"><ErrLine error={err} /></div>}
      {edit && <Form init={edit} groups={gl} onSave={upsert} onClose={() => setEdit(null)} busy={mut.isPending} error={err} />}
      <Dialog open={!!del} onClose={mut.isPending ? undefined : () => setDel(null)} title="Xoá lịch này?"
        footer={<><button type="button" className="btn" onClick={() => setDel(null)} disabled={mut.isPending}>Huỷ</button>
          <button type="button" className="btn" onClick={() => save(list.filter((x) => x.schedule_id !== del.schedule_id), "Đã xoá lịch")} disabled={mut.isPending}>{mut.isPending && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}Xoá lịch</button></>}>
        <div className="grid gap-2 p-3 text-[12.5px]"><p className="m-0">Báo cáo đã tạo trước đó không bị xoá; chỉ dừng việc tự tạo từ nay.</p><ErrLine error={err} /></div>
      </Dialog>
    </Panel>
  );
}
