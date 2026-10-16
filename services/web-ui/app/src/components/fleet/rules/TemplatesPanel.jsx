import { useState } from "react";
import { Pencil, Plus, Sparkles, Trash2, Link2 } from "lucide-react";
import { Dialog } from "../../dialog";
import { Panel } from "../../ui";
import { EmptyState, ErrorState, TableSkeleton } from "../../ux/States";
import { toast } from "../../../ux/bus";
import { api, useFleetMut, usePerm, KIND_VN } from "../../../lib/fleetQueries";
import { isUnavailable } from "../../../lib/fleetApi";
import { ErrLine, GBtn, PRIMARY, Pill, Unavailable } from "../bits";
import RuleEditor from "./RuleEditor";
import { summarize } from "./schema";

function DeleteDialog({ t, onClose }) {
  const del = useFleetMut(() => api.del(`/rules/templates/${t.id}`), ["tpl", "assign", "compliance"], {
    onSuccess: () => { toast({ tone: "ok", title: "Đã xoá mẫu luật", body: t.name }); onClose(); },
  });
  const n = t.assignments || 0;
  return (
    <Dialog open onClose={onClose} title="Xoá mẫu luật?" className="!min-w-0 !max-w-[460px]"
      footer={<><button type="button" className="btn" onClick={onClose}>Huỷ</button>
        <GBtn master perm="compliance.read" className="!bg-down !text-white !border-transparent" disabled={del.isPending} onClick={() => del.mutate()}><Trash2 size={14} aria-hidden="true" />{del.isPending ? "Đang xoá…" : "Xoá mẫu"}</GBtn></>}>
      <div className="p-3 grid gap-2 text-[13px]">
        <p className="m-0">Bạn sắp xoá mẫu <b>{t.name}</b>. Không thể hoàn tác.</p>
        {n > 0 && <div role="alert" className="fl-banner t-warn"><Link2 size={16} aria-hidden="true" /><div className="fl-banner-b"><b className="block">Mẫu đang được gán {n} lần</b>Xoá mẫu sẽ gỡ các phép gán này và đóng các sự cố luật liên quan.</div></div>}
        <ErrLine error={del.error} />
      </div>
    </Dialog>
  );
}

/** Danh sách mẫu luật + tạo/sửa/xoá. */
export default function TemplatesPanel({ tpl, presets, onAssign }) {
  const p = usePerm();
  const [edit, setEdit] = useState(null); // {t} hoặc {} = tạo mới
  const [del, setDel] = useState(null);
  const items = tpl.data?.items || [];
  const wr = p.reason("compliance.read", { master: true });
  return (
    <Panel title="Mẫu luật" pad={false} right={<>
      <GBtn master perm="compliance.read" onClick={() => setEdit({})}><Sparkles size={14} aria-hidden="true" />Mẫu gợi ý</GBtn>
      <GBtn master perm="compliance.read" className={PRIMARY} onClick={() => setEdit({})}><Plus size={14} aria-hidden="true" />Tạo mẫu luật</GBtn></>}>
      {tpl.isPending ? <div className="p-3"><TableSkeleton rows={3} cols={4} /></div>
        : tpl.isError ? (isUnavailable(tpl.error) ? <Unavailable what="Mẫu luật" error={tpl.error} onRetry={() => tpl.refetch()} retrying={tpl.isFetching} /> : <ErrorState compact error={tpl.error} onRetry={() => tpl.refetch()} retrying={tpl.isFetching} what="mẫu luật" />)
        : !items.length ? <div className="p-3"><EmptyState compact title="Chưa có mẫu luật nào" hint={wr ? "Mẫu luật do master tạo. Bạn chỉ có quyền xem." : "Bấm “Mẫu gợi ý” để chọn mẫu trung tính (lỗ ngày, drawdown, margin level…) rồi chỉnh theo hợp đồng, sau đó gán cho nhóm/tag/tài khoản."} /></div>
        : (
          <div className="fl-tablewrap relative">
            <table className="fl-tbl">
              <caption className="fl-sr">Danh sách mẫu luật</caption>
              <thead><tr><th scope="col">Tên mẫu</th><th scope="col">Loại</th><th scope="col">Tham số</th><th scope="col" className="r">Đang gán</th><th scope="col"><span className="fl-sr">Thao tác</span></th></tr></thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id} style={{ cursor: "default" }}>
                    <td><b>{t.name}</b>{t.description ? <span className="c-sub" title={t.description}>{t.description}</span> : null}</td>
                    <td>{KIND_VN[t.kind] || t.kind}</td>
                    <td className="num text-muted" style={{ maxWidth: "22rem" }}>{summarize(t.kind, t.params)}</td>
                    <td className="r">{t.assignments > 0 ? <Pill tone="ok" icon={Link2}>{t.assignments} phép gán</Pill> : <Pill tone="mute">Chưa gán</Pill>}</td>
                    <td className="r" style={{ whiteSpace: "nowrap" }}>
                      <GBtn master perm="compliance.read" className="!h-7 !px-2" onClick={() => onAssign(t)} aria-label={`Gán mẫu ${t.name}`}><Link2 size={13} aria-hidden="true" />Gán</GBtn>{" "}
                      <GBtn master perm="compliance.read" className="!h-7 !px-2" onClick={() => setEdit({ t })} aria-label={`Sửa mẫu ${t.name}`}><Pencil size={13} aria-hidden="true" />Sửa</GBtn>{" "}
                      <GBtn master perm="compliance.read" className="!h-7 !px-2" onClick={() => setDel(t)} aria-label={`Xoá mẫu ${t.name}`}><Trash2 size={13} aria-hidden="true" /><span className="fl-sr">Xoá</span></GBtn>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>)}
      {edit && <RuleEditor template={edit.t} presets={presets?.presets} kinds={presets?.kinds} onClose={() => setEdit(null)} />}
      {del && <DeleteDialog t={del} onClose={() => setDel(null)} />}
    </Panel>
  );
}
