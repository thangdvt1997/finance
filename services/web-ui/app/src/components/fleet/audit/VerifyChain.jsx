// Kiểm tra toàn vẹn chuỗi băm của nhật ký (GET audit/verify).
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { fget } from "../../../lib/fleetApi";
import { useFleetMut } from "../../../lib/fleetQueries";
import { Banner, ErrLine } from "../bits";

export default function VerifyChain() {
  const [res, setRes] = useState(null);
  const m = useFleetMut(() => fget("/audit/verify"), [], { onSuccess: (r) => setRes(r) });
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn" onClick={() => { setRes(null); m.mutate(); }} disabled={m.isPending}><ShieldCheck size={13} aria-hidden="true" />{m.isPending ? "Đang kiểm tra…" : "Kiểm tra toàn vẹn chuỗi băm"}</button>
        <span className="text-[12px] text-muted">Tính lại chuỗi băm của toàn bộ nhật ký để phát hiện chỉnh sửa/xoá.</span>
      </div>
      {res && (res.ok
        ? <Banner tone="ok" title="Chuỗi băm nguyên vẹn">Đã kiểm tra <b className="num">{res.rows?.toLocaleString("vi-VN")}</b> bản ghi — không phát hiện chỉnh sửa.</Banner>
        : <Banner tone="bad" title="Phát hiện bất thường trong chuỗi băm">Bản ghi đầu tiên sai: <b className="num">#{res.first_bad_id}</b> (đã duyệt {res.rows} bản ghi trước đó). Báo ngay cho quản trị hệ thống.</Banner>)}
      <ErrLine error={m.error} />
    </div>
  );
}
