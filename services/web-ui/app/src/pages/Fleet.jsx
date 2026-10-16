// Đội tài khoản — Fleet command center (W1/W2). Master: toàn quyền (có TOTP); support/analyst: chỉ-đọc theo phạm vi nhóm được giao.
// Kế thừa tính năng của trang Khách hàng cũ (#/khach-hang: tạo tài khoản, cấp mã ghép cặp, đình chỉ, nhật ký, bảng kỹ thuật): các nút đó nằm trong hồ sơ khách.
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Layers, RefreshCw, Search, Upload, UserPlus, UsersRound, X } from "lucide-react";
import { Panel, PageHead, Skeleton } from "../components/ui";
import { EmptyState, ErrorState } from "../components/ux/States";
import { useFleetFilters, FILTER_KEYS } from "../lib/fleetFilters";
import { useFleetList, useGroups, usePerm, useTags, ACC_STATUS_VN, EA_VN, COMP_VN } from "../lib/fleetQueries";
import { fget } from "../lib/fleetApi";
import { Banner, GBtn, PRIMARY, RoNote, Unavailable, useDebounced, ago } from "../components/fleet/bits";
import FleetKpis from "../components/fleet/FleetKpis";
import FleetTable from "../components/fleet/FleetTable";
import SavedViews from "../components/fleet/SavedViews";
import ProfileDrawer from "../components/fleet/ProfileDrawer";

const BulkDialog = lazy(() => import("../components/fleet/BulkDialog"));
const GroupsManager = lazy(() => import("../components/fleet/GroupsManager"));
const ImportFlow = lazy(() => import("../components/fleet/ImportFlow"));
const CreateDialog = lazy(() => import("../components/clients/ActionDialogs").then((m) => ({ default: m.CreateDialog })));

export const meta = { path: "doi-tai-khoan", label: "Đội tài khoản", short: "Đội TK", group: "Quản trị đội", icon: Layers, roles: ["master", "support", "analyst"], perm: "fleet.read", order: 10,
  keywords: "khách hàng fleet nhóm tag hàng loạt import csv onboarding mt4 mt5 command center" };

const PAGE = 50;
const SELECT_MAX = 200;

export default function Fleet() {
  const perm = usePerm();
  const qc = useQueryClient();
  const { v, set, clear, filters, active } = useFleetFilters();
  const [search, setSearch] = useState(v.q);
  const dSearch = useDebounced(search, 350);
  const [selected, setSelected] = useState(() => new Set());
  const [bulk, setBulk] = useState(false);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const groups = useGroups().data?.items || [];
  const tags = useTags().data?.items || [];
  const page = Math.max(0, Number(v.page) || 0);

  // đồng bộ ô tìm kiếm -> URL (sau debounce). Thay đổi từ bên ngoài (KPI, chip, bộ lọc đã lưu) tự gọi setSearch.
  useEffect(() => { if (dSearch !== v.q) set({ q: dSearch }); }, [dSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const params = { ...filters, sort: v.sort || undefined, dir: v.dir || undefined, limit: PAGE, offset: page * PAGE };
  const q = useFleetList(params);
  const rows = q.data?.items || [];
  const total = q.data?.total ?? 0;
  const counts = q.data?.counts;
  const stale = q.dataUpdatedAt && Date.now() - q.dataUpdatedAt > 90_000;

  const toggle = (id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else if (n.size < SELECT_MAX) n.add(id); return n; });
  const togglePage = () => setSelected((s) => { const n = new Set(s); const all = rows.every((r) => n.has(r.account_id)); for (const r of rows) { if (all) n.delete(r.account_id); else if (n.size < SELECT_MAX) n.add(r.account_id); } return n; });
  const selectAllFiltered = async () => {
    try { const r = await fget("/fleet", { ...filters, limit: SELECT_MAX }); setSelected(new Set((r.items || []).map((x) => x.account_id))); } catch { /* giữ nguyên */ }
  };

  const chips = useMemo(() => {
    const out = [];
    if (v.q) out.push(["q", `Tìm: “${v.q}”`]);
    if (v.group) out.push(["group", `Nhóm: ${groups.find((g) => g.id === v.group)?.name || v.group}`]);
    if (v.tag) out.push(["tag", `Tag: #${v.tag}`]);
    if (v.status) out.push(["status", `Trạng thái: ${ACC_STATUS_VN[v.status] || v.status}`]);
    if (v.ea) out.push(["ea", `EA: ${EA_VN[v.ea] || v.ea}`]);
    if (v.compliance) out.push(["compliance", `Luật: ${COMP_VN[v.compliance] || v.compliance}`]);
    if (v.incident) out.push(["incident", "Có sự cố đang mở"]);
    return out;
  }, [v, groups]);

  const refresh = () => qc.invalidateQueries({ queryKey: ["fl"] });
  const noScope = !q.isPending && !q.isError && total === 0 && !active && (counts?.total ?? 0) === 0;
  const selIds = [...selected];

  return (
    <div className="fl-page">
      <PageHead title="Đội tài khoản"
        sub="Trung tâm giám sát khách hàng: trạng thái EA, tuân thủ luật, sự cố, nhóm/tag và thao tác hàng loạt. Dữ liệu cập nhật tự động."
        right={<>
          <RoNote />
          <GBtn master perm="fleet.read" onClick={() => setGroupsOpen(true)}><UsersRound size={14} aria-hidden="true" />Quản lý nhóm</GBtn>
          <GBtn master perm="fleet.read" onClick={() => setImportOpen(true)}><Upload size={14} aria-hidden="true" />Nhập CSV</GBtn>
          <GBtn master perm="fleet.read" className={PRIMARY} onClick={() => setCreateOpen(true)}><UserPlus size={14} aria-hidden="true" />Tạo tài khoản MT</GBtn>
        </>} />

      {!perm.isMaster && !perm.loading && (
        <Banner tone="info" title={`Bạn đang dùng vai trò ${perm.role === "support" ? "Hỗ trợ" : perm.role === "analyst" ? "Phân tích" : perm.role}`}>
          Chỉ xem tài khoản trong nhóm được giao{perm.me?.scope?.all ? " (toàn bộ)" : ""}. Các nút quản trị bị khoá — chỉ master dùng được. Ghi chú CRM mở cho vai trò Hỗ trợ.
        </Banner>
      )}

      <FleetKpis counts={counts} filters={filters} onFilter={(p) => { setSearch(p.q === "" ? "" : search); set(p); }} loading={q.isPending} />

      <Panel title="Danh sách tài khoản" icon={Layers} pad={false} right={
        <span className="flex items-center gap-2 text-[11.5px] text-muted">
          {stale && <span className="fl-stale" title="Quá 90 giây chưa làm mới được">dữ liệu cũ</span>}
          {q.dataUpdatedAt ? <span className="max-sm:hidden">cập nhật {ago(new Date(q.dataUpdatedAt).toISOString())}</span> : null}
          <button type="button" className="btn !h-7 !px-2" onClick={refresh} aria-label="Làm mới danh sách" title="Làm mới"><RefreshCw size={13} className={q.isFetching ? "ux-spin" : ""} aria-hidden="true" /></button>
        </span>}>
        <div className="p-2.5 grid gap-2 border-b border-line">
          <div className="fl-bar-tools" role="search" aria-label="Lọc danh sách tài khoản">
            <div className="fl-search"><Search size={14} aria-hidden="true" /><input className="field" type="search" aria-label="Tìm theo mã, nhãn, số tài khoản, khách" placeholder="Tìm mã, nhãn, số TK, khách…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
            <select className="field" aria-label="Lọc theo nhóm" value={v.group} onChange={(e) => set({ group: e.target.value })}><option value="">Mọi nhóm</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.members})</option>)}</select>
            <select className="field" aria-label="Lọc theo tag" value={v.tag} onChange={(e) => set({ tag: e.target.value })}><option value="">Mọi tag</option>{tags.map((t) => <option key={t.tag} value={t.tag}>#{t.tag} ({t.count})</option>)}</select>
            <select className="field" aria-label="Lọc theo trạng thái tài khoản" value={v.status} onChange={(e) => set({ status: e.target.value })}><option value="">Mọi trạng thái</option>{Object.entries(ACC_STATUS_VN).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <select className="field" aria-label="Lọc theo kết nối EA" value={v.ea} onChange={(e) => set({ ea: e.target.value })}><option value="">EA: tất cả</option>{["online", "degraded", "offline"].map((k) => <option key={k} value={k}>EA: {EA_VN[k]}</option>)}</select>
            <select className="field" aria-label="Lọc theo tuân thủ luật" value={v.compliance} onChange={(e) => set({ compliance: e.target.value })}><option value="">Luật: tất cả</option>{["green", "yellow", "red"].map((k) => <option key={k} value={k}>Luật: {COMP_VN[k]}</option>)}</select>
            <span className="ml-auto flex items-center gap-2"><SavedViews filters={filters} activeCount={active} onApply={(f) => { setSearch(f.q || ""); set(f); }} /></span>
          </div>
          {chips.length > 0 && (
            <div className="fl-active-filters" aria-label="Bộ lọc đang áp dụng">
              {chips.map(([k, l]) => <span key={k} className="fl-fchip">{l}<button type="button" onClick={() => { if (k === "q") setSearch(""); set({ [k]: "" }); }} aria-label={`Bỏ bộ lọc ${l}`}><X size={11} aria-hidden="true" /></button></span>)}
              <button type="button" className="btn !h-6 !px-2 text-[11.5px]" onClick={() => { setSearch(""); clear(); }}>Xoá hết</button>
              <span className="fl-count ml-auto" aria-live="polite">{q.isFetching && !q.isPending ? "Đang cập nhật…" : `${total} kết quả`}</span>
            </div>
          )}
        </div>

        {q.isPending ? <div className="p-3"><Skeleton rows={8} h={20} /></div>
          : q.isError && !q.data ? <div className="p-3">{q.error?.code === "unavailable" ? <Unavailable what="Danh sách đội tài khoản" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} /> : <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} what="Danh sách đội tài khoản" />}</div>
          : noScope ? <div className="p-3"><EmptyState title="Chưa có tài khoản nào trong phạm vi của bạn"
              hint={perm.isMaster ? "Tạo tài khoản MT đầu tiên hoặc nhập hàng loạt từ CSV; mỗi tài khoản được cấp passcode, mã ghép cặp, token EA và HMAC để cài EA đọc-chỉ." : "Chưa có nhóm nào được giao cho bạn (và không có quyền toàn bộ). Nhờ master giao nhóm ở mục Vai trò & nhân sự."}
              actions={perm.isMaster ? [{ label: "Tạo tài khoản MT", onClick: () => setCreateOpen(true) }, { label: "Nhập CSV", onClick: () => setImportOpen(true) }] : undefined} /></div>
          : !rows.length ? <div className="p-3"><EmptyState title="Không có tài khoản khớp bộ lọc" hint="Thử bỏ bớt bộ lọc hoặc đổi từ khoá." actions={[{ label: "Xoá bộ lọc", onClick: () => { setSearch(""); clear(); } }]} /></div>
          : (
            <>
              {q.isError && <div className="p-2"><Banner tone="warn" title="Không làm mới được — đang hiển thị dữ liệu cũ">{q.error?.message}</Banner></div>}
              <FleetTable rows={rows} sort={v.sort} dir={v.dir || "asc"} onSort={(sort, dir) => set({ sort, dir })} selected={selected} onToggle={toggle} onTogglePage={togglePage}
                onOpen={(id) => set({ acc: id })} activeId={v.acc} />
              <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 border-t border-line text-[12px] text-muted">
                <span>{page * PAGE + 1}–{page * PAGE + rows.length} / {total}</span>
                <span className="flex gap-2">
                  <button className="btn !h-7" disabled={page === 0} onClick={() => set({ page: page - 1 || "" })}>Trang trước</button>
                  <button className="btn !h-7" disabled={(page + 1) * PAGE >= total} onClick={() => set({ page: page + 1 })}>Trang sau</button>
                </span>
              </div>
            </>
          )}
      </Panel>

      {selected.size > 0 && (
        <div className="fl-bulkbar" role="region" aria-label="Thao tác với tài khoản đã chọn">
          <b>Đã chọn {selected.size}</b>
          {total > rows.length && selected.size < Math.min(total, SELECT_MAX) && <button type="button" className="btn !h-7" onClick={selectAllFiltered}>Chọn {Math.min(total, SELECT_MAX)} kết quả đang lọc</button>}
          <button type="button" className="btn !h-7" onClick={() => setSelected(new Set())}>Bỏ chọn</button>
          <span className="ml-auto" />
          <GBtn master perm="fleet.read" className={PRIMARY} onClick={() => setBulk(true)}><Layers size={14} aria-hidden="true" />Thao tác hàng loạt…</GBtn>
        </div>
      )}

      {v.acc && <ProfileDrawer id={v.acc} row={rows.find((r) => r.account_id === v.acc)} onClose={() => set({ acc: "" })} />}
      <Suspense fallback={null}>
        {bulk && <BulkDialog open accountIds={selIds} onClose={() => setBulk(false)} onDone={() => { setSelected(new Set()); }} />}
        {groupsOpen && <GroupsManager open onClose={() => setGroupsOpen(false)} />}
        {importOpen && <ImportFlow open onClose={() => { setImportOpen(false); refresh(); }} />}
        {createOpen && <CreateDialog onClose={() => { setCreateOpen(false); refresh(); }} onCreated={refresh} />}
      </Suspense>
    </div>
  );
}
