import { useEffect, useMemo, useState } from "react";
import { BellRing, LayoutGrid, ListChecks, ScrollText, ShieldAlert, UserPlus } from "lucide-react";
import "../clients.css";
import { Async, Chip, PageHead, Skeleton } from "../components/ui";
import { useAudit, useFleet, useMe } from "../lib/clientsQueries";
import FleetOverview from "../components/clients/FleetOverview";
import AccountList from "../components/clients/AccountList";
import AccountDetail from "../components/clients/AccountDetail";
import AuditLog from "../components/clients/AuditLog";
import Notifications, { useNotices } from "../components/clients/Notifications";
import ViewAs, { markImpersonating } from "../components/clients/ViewAs";
import { CreateDialog } from "../components/clients/ActionDialogs";
import { ModeBanner } from "../components/clients/bits";
import { setModePref } from "../lib/clientsApi";

const TABS = [
  { id: "", label: "Tổng quan", icon: LayoutGrid },
  { id: "danh-sach", label: "Danh sách", icon: ListChecks },
  { id: "nhat-ky", label: "Nhật ký kiểm toán", short: "Kiểm toán", icon: ScrollText },
  { id: "thong-bao", label: "Thông báo", icon: BellRing },
];

/** Trang Khách hàng (master): #/khach-hang[/danh-sach[/<account_id>]|/nhat-ky|/thong-bao|/xem/<account_id>] */
export default function Clients({ arg = "" }) {
  const me = useMe();
  const fleet = useFleet();
  const au = useAudit({}, 200);
  const parts = arg.split("/");
  const tab = ["danh-sach", "nhat-ky", "thong-bao", "xem"].includes(parts[0]) ? parts[0] : "";
  const accId = parts.slice(1).join("/") || "";
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState("");
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(""), 4000); return () => clearTimeout(t); }, [toast]);
  const rows = fleet.rows || [];
  const auditItems = useMemo(() => (au.data?.pages || []).flatMap((p) => p.items || []), [au.data]);
  const notices = useNotices(rows, auditItems);

  if (me.isPending) return <Skeleton rows={6} h={18} />;
  if (me.data?.role !== "master") {
    return (
      <div role="alert" className="panel panel-b max-w-[560px]">
        <b className="text-down">Không có quyền truy cập.</b>
        <p className="text-muted">Trang Khách hàng chỉ dành cho tài khoản master. Khách hàng dùng cổng riêng tại <code>/c/</code>.</p>
      </div>
    );
  }

  const viewing = tab === "xem";
  const needLogin = fleet.isError && [401, 403].includes(fleet.error?.status);
  const open = (id) => { markImpersonating(id); location.hash = `#/khach-hang/xem/${id}`; };

  return (
    <>
      <PageHead title="Khách hàng" sub="Master console: quản lý tài khoản MT4/MT5, sức khoẻ EA, cấp mã và nhật ký kiểm toán. Chỉ đọc — không có chức năng đặt lệnh."
        right={!viewing && <><Chip tone="ro">READ-ONLY · master</Chip><button className="btn !bg-accent !text-[color:var(--accent-fg)] !border-transparent" onClick={() => setCreating(true)}><UserPlus size={14} aria-hidden="true" />Tạo tài khoản MT</button></>} />
      <ModeBanner />
      {!viewing && (
        <nav aria-label="Mục quản trị khách hàng" className="cl-tabs">
          {TABS.map((t) => {
            const on = (t.id === "" && !tab) || t.id === tab;
            const n = t.id === "thong-bao" ? notices.unread.length : 0;
            return (
              <a key={t.id} href={`#/khach-hang${t.id ? "/" + t.id : ""}`} aria-current={on ? "page" : undefined} className={on ? "on" : ""}>
                <t.icon size={14} aria-hidden="true" /><span className="max-sm:hidden">{t.label}</span><span className="sm:hidden">{t.short || t.label}</span>
                {n > 0 && <span className="cl-badge" aria-label={`${n} chưa xem`}>{n}</span>}
              </a>
            );
          })}
        </nav>
      )}
      {toast && <div role="status" className="rounded-md border border-line2 bg-panel2 px-3 py-2 text-[12.5px] text-up">{toast}</div>}

      {needLogin && (
        <div role="alert" className="panel panel-b max-w-[620px] grid gap-2">
          <b className="text-accent">Cần đăng nhập master.</b>
          <p className="m-0 text-muted">Dịch vụ xác thực từ chối yêu cầu ({fleet.error.status}). Đăng nhập bằng tài khoản master (nền tảng “master”) rồi quay lại trang này.</p>
          <div className="flex flex-wrap gap-2"><a className="btn no-underline" href="/auth/login">Đăng nhập master</a><button className="btn" onClick={() => { setModePref("mock"); location.reload(); }}>Xem thử với dữ liệu minh hoạ</button></div>
        </div>)}
      {viewing ? (fleet.isPending ? <Skeleton rows={6} h={18} /> : <ViewAs row={rows.find((r) => r.account_id === accId)} id={accId} />)
        : tab === "nhat-ky" ? <AuditLog />
        : tab === "thong-bao" ? <Notifications notices={notices} />
        : (
          needLogin ? null : <Async q={fleet} rows={6} isEmpty={(d) => !d?.profiles?.length} empty="Chưa có tài khoản MT nào được quản lý." hint="Bấm “Tạo tài khoản MT” để cấp passcode, mã ghép cặp và token EA.">
            {() => (tab === "danh-sach"
              ? <AccountList rows={rows} />
              : <>
                  {notices.unread.some((n) => n.level === "crit") && (
                    <a href="#/khach-hang/thong-bao" className="cl-alert no-underline"><ShieldAlert size={15} aria-hidden="true" /><b>{notices.unread.filter((n) => n.level === "crit").length} thông báo nghiêm trọng chưa xem</b><span className="text-muted">— EA mất kết nối, đăng nhập bất thường hoặc vượt ngưỡng rủi ro. Bấm để xem.</span></a>)}
                  <FleetOverview rows={rows} gwOk={fleet.gwOk} />
                </>)}
          </Async>
        )}

      {tab === "danh-sach" && accId && <AccountDetail id={accId} rows={rows} onClose={() => { location.hash = "#/khach-hang/danh-sach"; }} onView={open} onToast={setToast} />}
      {creating && <CreateDialog onClose={() => setCreating(false)} onCreated={(r) => setToast(`Đã tạo ${r.account?.account_id}.`)} />}
    </>
  );
}
