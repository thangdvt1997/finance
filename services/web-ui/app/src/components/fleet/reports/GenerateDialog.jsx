import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, MinusCircle, XOctagon } from "lucide-react";
import { Dialog } from "../../dialog";
import { Seg } from "../../ui";
import { toast } from "../../../ux/bus";
import { useFleetList } from "../../../lib/fleetQueries";
import { Banner, Field, PRIMARY, RoNote } from "../bits";
import { KIND_VN, KINDS } from "./reportsApi";

const MAX = 50;
/** Tạo báo cáo ngay: 1 tài khoản (account) hoặc cả nhóm (group = {id,name}); chạy TUẦN TỰ từng tài khoản, có tiến độ + huỷ. */
export default function GenerateDialog({ open, onClose, account, group, generate }) {
  const batch = !!group;
  const mem = useFleetList({ group: group?.id, limit: 200 }, { enabled: open && batch });
  const targets = batch ? (mem.data?.items || []).slice(0, MAX).map((a) => ({ id: a.account_id, label: a.label || a.account_id })) : account ? [{ id: account.id, label: account.label || account.id }] : [];
  const over = batch && (mem.data?.total || 0) > MAX;
  const [kind, setKind] = useState("daily");
  const [release, setRelease] = useState(false);
  const [period, setPeriod] = useState("");
  const [run, setRun] = useState(null); // {i, results[], busy}
  const stop = useRef(false);
  useEffect(() => { if (open) { setRun(null); setRelease(false); setPeriod(""); stop.current = false; } }, [open]);

  const start = async () => {
    stop.current = false;
    const results = [];
    setRun({ i: 0, results, busy: true });
    for (let i = 0; i < targets.length; i++) {
      if (stop.current) break;
      setRun({ i, results: [...results], busy: true });
      const t = targets[i];
      try {
        await generate({ account_id: t.id, kind, ...(period ? { period } : {}), ...(release ? { release: true } : {}) });
        results.push({ ...t, ok: true });
      } catch (e) {
        results.push({ ...t, ok: false, skip: e.status === 409, msg: e.status === 409 ? "Chưa có dữ liệu trong kỳ này hoặc đang tạo — bỏ qua." : e.code === "unavailable" ? "Máy chủ chưa mở chức năng tạo báo cáo." : e.message });
        if (e.code === "unavailable" || e.code === "forbidden") break;
      }
    }
    setRun({ i: targets.length, results: [...results], busy: false });
    const ok = results.filter((r) => r.ok).length;
    toast({ tone: ok === results.length && ok > 0 ? "ok" : "warn", title: `Đã tạo ${ok}/${targets.length} báo cáo ${KIND_VN[kind].toLowerCase()}`, body: release ? "Đã phát hành cho khách." : "Ở trạng thái nháp — khách chưa thấy." });
  };
  const busy = !!run?.busy;
  const finished = run && !run.busy;
  const bad = period && !/^\d{4}-\d{2}-\d{2}$/.test(period);
  const results = run?.results || [];

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} title={batch ? `Tạo báo cáo cho nhóm “${group.name}”` : "Tạo báo cáo ngay"}
      description={batch ? "Tạo lần lượt từng tài khoản trong nhóm. Có thể mất vài chục giây mỗi tài khoản." : `Tài khoản ${account?.label ? account.label + " · " : ""}${account?.id || ""}`}
      footer={finished ? <button type="button" className={`btn ${PRIMARY}`} onClick={onClose}>Xong</button> : <>
        <RoNote className="mr-auto" />
        {busy ? <button type="button" className="btn" onClick={() => { stop.current = true; }}>Dừng sau tài khoản này</button> : <button type="button" className="btn" onClick={onClose}>Huỷ</button>}
        <button type="button" className={`btn ${PRIMARY}`} onClick={start} disabled={busy || !targets.length || bad || (batch && mem.isPending)}>
          {busy ? <><Loader2 size={14} className="animate-spin" aria-hidden="true" />Đang tạo {Math.min((run?.i || 0) + 1, targets.length)}/{targets.length}…</> : `Tạo ${targets.length > 1 ? `${targets.length} báo cáo` : "báo cáo"}`}
        </button></>}>
      <div className="grid gap-3 p-3">
        {batch && mem.isPending && <p className="m-0 text-[12.5px] text-muted" role="status">Đang lấy danh sách tài khoản của nhóm…</p>}
        {batch && mem.isError && <Banner tone="bad" title="Không lấy được thành viên nhóm">{mem.error.message}</Banner>}
        {batch && mem.data && !targets.length && <Banner tone="warn" title="Nhóm chưa có tài khoản">Thêm tài khoản vào nhóm trước khi tạo hàng loạt.</Banner>}
        {over && <Banner tone="warn" title={`Giới hạn ${MAX} tài khoản mỗi lần`}>Nhóm có {mem.data.total} tài khoản; chỉ {MAX} tài khoản đầu được tạo. Dùng “Lịch tự động” cho nhóm lớn.</Banner>}
        {!run && <>
          <Field label="Loại báo cáo" htmlFor="gen-kind">
            <Seg label="Loại báo cáo" value={kind} onChange={setKind} options={KINDS.map((k) => ({ value: k, label: KIND_VN[k] }))} />
          </Field>
          <Field label="Kỳ báo cáo (tuỳ chọn)" htmlFor="gen-period" help="Ngày kết thúc kỳ, định dạng YYYY-MM-DD. Để trống = kỳ gần nhất đã đóng." error={bad ? "Nhập đúng dạng YYYY-MM-DD." : null}>
            <input id="gen-period" className="field num" type="date" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
          <label className="fl-check"><input type="checkbox" checked={release} onChange={(e) => setRelease(e.target.checked)} /><span>Phát hành luôn cho khách (khách xem được ngay)</span></label>
          {release ? <Banner tone="warn" title="Khách sẽ thấy báo cáo ngay khi tạo xong">Nên mở xem bản nháp trước khi phát hành. Có thể thu hồi sau.</Banner>
            : <Banner tone="info">Mặc định tạo ở trạng thái <b>nháp</b> — khách chưa thấy. Phát hành sau khi đã kiểm tra.</Banner>}
        </>}
        {run && (
          <div aria-live="polite" className="grid gap-1">
            <div className="h-1.5 rounded bg-line overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={targets.length} aria-valuenow={Math.min(results.length, targets.length)} aria-label="Tiến độ tạo báo cáo">
              <div className="h-full bg-accent transition-all" style={{ width: `${targets.length ? (results.length / targets.length) * 100 : 0}%` }} />
            </div>
            <ul className="m-0 p-0 list-none grid gap-1 max-h-[40vh] overflow-auto">
              {results.map((r) => (
                <li key={r.id} className="flex items-start gap-2 text-[12.5px]">
                  {r.ok ? <CheckCircle2 size={14} className="text-up mt-0.5 shrink-0" aria-hidden="true" /> : r.skip ? <MinusCircle size={14} className="text-accent mt-0.5 shrink-0" aria-hidden="true" /> : <XOctagon size={14} className="text-down mt-0.5 shrink-0" aria-hidden="true" />}
                  <span className="min-w-0"><b className="num">{r.id}</b> {r.ok ? <span className="text-up">Đã tạo{release ? " + phát hành" : " (nháp)"}</span> : <span className={r.skip ? "text-accent" : "text-down"}>{r.msg}</span>}</span>
                </li>))}
              {busy && results.length < targets.length && <li className="text-[12.5px] text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" aria-hidden="true" /><span className="num">{targets[results.length]?.id}</span> đang tạo…</li>}
            </ul>
          </div>)}
      </div>
    </Dialog>
  );
}
