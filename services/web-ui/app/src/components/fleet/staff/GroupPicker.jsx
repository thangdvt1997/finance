// Chọn nhóm được giao cho nhân sự (GET groups).
import { useGroups } from "../../../lib/fleetQueries";
import { GroupChip } from "../bits";

export default function GroupPicker({ value, onChange, disabled }) {
  const q = useGroups();
  const items = q.data?.items || [];
  const set = new Set(value);
  const toggle = (id) => { const s = new Set(set); if (s.has(id)) s.delete(id); else s.add(id); onChange([...s]); };
  if (q.isPending) return <span className="text-muted text-[12px]">Đang tải nhóm…</span>;
  if (q.isError) return <span className="text-muted text-[12px]">Chưa tải được danh sách nhóm ({q.error?.message}).</span>;
  if (!items.length) return <span className="text-muted text-[12px]">Chưa có nhóm nào. Tạo nhóm ở trang Đội tài khoản, hoặc chọn “Xem toàn bộ tài khoản”.</span>;
  return (
    <div className="grid gap-1 max-h-44 overflow-y-auto rounded-md border border-line p-2" role="group" aria-label="Nhóm được giao">
      {items.map((g) => (
        <label key={g.id} className="fl-check !items-center">
          <input type="checkbox" checked={set.has(g.id)} disabled={disabled} onChange={() => toggle(g.id)} />
          <GroupChip g={g} /><span className="text-muted text-[11.5px]">{g.members ?? 0} tài khoản</span>
        </label>
      ))}
    </div>
  );
}
