import { useState } from "react";
import { CalendarClock, FileBarChart, FilePlus2, Layers, RefreshCw } from "lucide-react";
import { PageHead, Panel, Seg, Skeleton } from "../components/ui";
import { usePerm, useGroups } from "../lib/fleetQueries";
import { Banner, ErrLine, GBtn, PRIMARY, RoNote, Unavailable } from "../components/fleet/bits";
import AccountPicker from "../components/fleet/reports/AccountPicker";
import GenerateDialog from "../components/fleet/reports/GenerateDialog";
import ReportList from "../components/fleet/reports/ReportList";
import Schedules from "../components/fleet/reports/Schedules";
import { useReportMut, useReports } from "../components/fleet/reports/reportsApi";

export const meta = { path: "bao-cao-khach", label: "Báo cáo khách", group: "Quản trị đội", icon: FileBarChart, roles: ["master", "analyst"], perm: "report.read", order: 40, keywords: "báo cáo khách hàng phát hành lịch pdf" };

/** #/bao-cao-khach[/<account_id>] — báo cáo theo từng tài khoản của khách: tạo, phát hành/thu hồi, xem HTML/PDF, lịch tự động. */
export default function ClientReports({ arg = "" }) {
  const acc = decodeURIComponent(arg || "");
  const [tab, setTab] = useState("reports");
  const [group, setGroup] = useState("");
  const [gen, setGen] = useState(null); // {account} | {group}
  const p = usePerm();
  const groups = useGroups();
  const gl = Array.isArray(groups.data) ? groups.data : groups.data?.items || [];
  const q = useReports(acc);
  const m = useReportMut();
  const pick = (id) => { location.hash = `#/bao-cao-khach/${id}`; };
  const grp = gl.find((g) => g.id === group);
  const writeWhy = p.reason("report.read", { master: true });

  return (
    <div className="fl-page">
      <PageHead title="Báo cáo khách" sub="Tạo, kiểm tra và phát hành báo cáo hiệu suất theo từng tài khoản MT4/MT5. Khách chỉ thấy bản đã phát hành."
        right={<RoNote />} />
      <div className="flex flex-wrap items-center gap-2">
        <Seg label="Mục" value={tab} onChange={setTab} options={[{ value: "reports", label: "Báo cáo" }, { value: "schedules", label: "Lịch tự động" }]} />
        {writeWhy && <span className="text-[12px] text-muted" role="note">Chế độ chỉ xem: {writeWhy}</span>}
      </div>

      {tab === "schedules" ? <Schedules /> : (
        <div className="grid gap-3 grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(17rem,22rem)_minmax(0,1fr)] items-start">
          <div className="grid gap-2 min-w-0">
            <AccountPicker value={acc} onPick={pick} group={group} onGroup={setGroup} />
            <GBtn master perm="report.read" disabled={!group} onClick={() => setGen({ group: grp || { id: group, name: group } })} title={!group ? "Chọn một nhóm ở trên để tạo hàng loạt" : undefined}>
              <Layers size={14} aria-hidden="true" />Tạo hàng loạt cho nhóm{grp ? ` “${grp.name}”` : ""}
            </GBtn>
            {!group && <p className="m-0 text-[11.5px] text-faint">Chọn một nhóm để tạo báo cáo cho cả nhóm (tối đa 50 tài khoản mỗi lần).</p>}
          </div>

          <Panel title={acc ? <span className="num">{acc}</span> : "Báo cáo đã tạo"} icon={FileBarChart} pad={false} className={acc ? "min-w-0 max-lg:order-first" : "min-w-0"}
            right={acc ? <>
              <button type="button" className="btn" onClick={() => q.refetch()} disabled={q.isFetching} aria-label="Làm mới danh sách báo cáo"><RefreshCw size={13} className={q.isFetching ? "animate-spin" : ""} aria-hidden="true" />Làm mới</button>
              <GBtn master perm="report.read" className={PRIMARY} onClick={() => setGen({ account: { id: acc } })}><FilePlus2 size={14} aria-hidden="true" />Tạo báo cáo</GBtn></> : null}>
            {!acc ? (
              <div className="p-3"><div className="fl-empty"><b>Chọn một tài khoản</b><span>Chọn tài khoản ở danh sách bên trái để xem các báo cáo ngày/tuần/tháng đã tạo, hoặc tạo báo cáo mới.</span></div></div>
            ) : q.isPending ? <div className="p-3"><Skeleton rows={4} h={20} /></div>
              : q.isError ? <div className="p-3">{q.error.code === "unavailable" || q.error.code === "network" ? <Unavailable what="Báo cáo theo tài khoản" error={q.error} onRetry={q.refetch} retrying={q.isFetching} /> : <ErrLine error={q.error} />}</div>
              : q.data.length === 0 ? (
                <div className="p-3"><div className="fl-empty"><b>Chưa có báo cáo nào cho tài khoản này</b>
                  <span>Bấm “Tạo báo cáo” để sinh bản ngày/tuần/tháng. Bản mới tạo ở trạng thái nháp (khách chưa thấy) cho đến khi bạn phát hành.</span>
                  <GBtn master perm="report.read" className={PRIMARY} onClick={() => setGen({ account: { id: acc } })}><FilePlus2 size={14} aria-hidden="true" />Tạo báo cáo đầu tiên</GBtn></div></div>
              ) : (
                <>
                  {q.data.some((x) => !x.released) && <div className="p-3 pb-0"><Banner tone="info">Bản “Nháp” chỉ master/phân tích thấy. Mở xem HTML/PDF trước khi phát hành cho khách.</Banner></div>}
                  <ReportList items={q.data} accountId={acc} release={m.release} />
                </>)}
          </Panel>
        </div>)}

      {gen && <GenerateDialog open onClose={() => { setGen(null); m.refresh(); }} account={gen.account ? { id: gen.account.id } : undefined} group={gen.group} generate={m.generate} />}
      <p className="m-0 text-[11.5px] text-faint"><CalendarClock size={11} className="inline mr-1" aria-hidden="true" />Báo cáo chỉ tổng hợp dữ liệu giám sát — không có chức năng đặt lệnh.</p>
    </div>
  );
}
