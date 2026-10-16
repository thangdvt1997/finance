import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Bot, Database, FileText, History, RefreshCw, Search } from "lucide-react";
import "../dulieu.css";
import { Async, Chip, PageHead, Panel, Seg, Stat, cn } from "../components/ui";
import { EmptyState } from "../components/ux/States";
import { api, apiWrite } from "../lib/api";
import { clean, dateTime, rel } from "../lib/format";
import { toast } from "../ux/bus";

export const meta = {
  path: "du-lieu", label: "Dữ liệu", group: "Vận hành", icon: Database, order: 30, roles: ["master"],
  keywords: "du lieu phu ma khung gap backfill im lang thi truong dong feed kiem tra lai data keeper",
};

const ST = {
  OK: { sym: "✓", label: "Đủ & mới", cls: "dk-OK" },
  CLOSED: { sym: "◐", label: "Thị trường đóng", cls: "dk-CLOSED" },
  SLOW: { sym: "▲", label: "Chậm", cls: "dk-SLOW" },
  BROKEN: { sym: "✕", label: "Hỏng", cls: "dk-BROKEN" },
};
const KIND = { ok: ["up", "Bình thường"], warn: ["accent", "Cần chú ý"], bad: ["down", "Có lỗi"] };
const useDk = (path, opts = {}) =>
  useQuery({ queryKey: ["dk", path], queryFn: ({ signal }) => api(`/data${path}`, {}, signal), staleTime: 30_000, refetchInterval: (qy) => (qy.state.status === "error" ? false : 60_000), refetchIntervalInBackground: false, retry: 0, placeholderData: keepPreviousData, ...opts });

function Cell({ c, tf, sym }) {
  if (!c) return <div className="dk-cell text-faint" aria-label={`${sym} ${tf}: không có`}>·</div>;
  const s = ST[c.s] || ST.OK;
  const tip = `${sym} ${tf} — ${s.label}\nNến cuối: ${c.bar ? dateTime(c.bar) : "—"}\nTick cuối: ${c.tick ? dateTime(c.tick) : "—"}${c.g ? `\nKhoảng thiếu: ${c.g}` : ""}`;
  return <div className={cn("dk-cell", s.cls)} title={tip} role="img" aria-label={`${sym} ${tf}: ${s.label}${c.g ? `, ${c.g} khoảng thiếu` : ""}`}>{s.sym}{c.g > 0 && <span className="dk-gap">{c.g}</span>}</div>;
}

function Matrix({ data }) {
  const [group, setGroup] = useState("all");
  const [stat, setStat] = useState("all");
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    return data.symbols.filter((s) => (group === "all" || s.group === group) && (stat === "all" || (stat === "issue" ? s.status === "SLOW" || s.status === "BROKEN" : s.status === stat)) && (!t || s.symbol.includes(t)));
  }, [data, group, stat, q]);
  const groups = [{ value: "all", label: "Tất cả" }, ...data.groups.filter((g) => data.symbols.some((s) => s.group === g)).map((g) => ({ value: g, label: g }))];
  return (
    <>
      <div className="dk-filters">
        <div className="max-w-full overflow-x-auto"><Seg value={group} onChange={setGroup} options={groups} label="Lọc theo nhóm mã" /></div>
        <div className="max-w-full overflow-x-auto"><Seg value={stat} onChange={setStat} label="Lọc theo trạng thái"
          options={[{ value: "all", label: "Mọi trạng thái" }, { value: "issue", label: "Chậm / hỏng" }, { value: "CLOSED", label: "Đóng cửa" }, { value: "OK", label: "Đủ" }]} /></div>
        <label className="relative ml-auto">
          <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
          <input className="field w-[10rem]" style={{ paddingLeft: "1.8rem" }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm mã…" aria-label="Tìm mã" />
        </label>
      </div>
      {rows.length === 0 ? <EmptyState compact title="Không có mã khớp bộ lọc" hint="Bỏ bớt bộ lọc hoặc xoá ô tìm kiếm." /> : (
        <div className="dk-wrap" role="region" aria-label="Bảng phủ dữ liệu mã theo khung thời gian" tabIndex={0}>
          <table className="dk-tbl">
            <thead>
              <tr><th className="dk-sym" scope="col">Mã ({rows.length})</th><th className="dk-st" scope="col" style={{ textAlign: "left" }}>Trạng thái</th>{data.tfs.map((tf) => <th key={tf} scope="col">{tf}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const st = ST[s.status] || ST.OK;
                return (
                  <tr key={s.symbol}>
                    <th className="dk-sym" scope="row">{s.symbol}</th>
                    <td className="dk-st"><span className={cn("chip", s.status === "OK" ? "up" : s.status === "BROKEN" ? "down" : s.status === "SLOW" ? "accent" : "")}>{st.sym} {st.label}</span></td>
                    {data.tfs.map((tf) => <td key={tf}><Cell c={s.tf[tf]} tf={tf} sym={s.symbol} /></td>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="dk-legend mt-2" aria-label="Chú giải">
        {Object.entries(ST).map(([k, v]) => <span key={k}><i className={v.cls}>{v.sym}</i>{v.label}</span>)}
        <span className="text-faint">Số nhỏ cạnh ô = số khoảng thiếu nến. “Thị trường đóng” là bình thường, không phải lỗi.</span>
      </div>
    </>
  );
}

function Diagnosis({ d }) {
  if (!d) return null;
  return (
    <div className="grid gap-2 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={d.mode === "llm" ? "ro" : ""} title={d.mode === "llm" ? "Do mô hình AI chạy cục bộ tóm tắt từ số liệu đã đo" : "Bản mẫu tất định từ số liệu đã đo"}><Bot size={11} aria-hidden="true" /> {d.mode === "llm" ? "AI cục bộ" : "Tóm tắt tự động"}</Chip>
      </div>
      <p className="m-0">{clean(d.summary)}</p>
      {d.causes?.length > 0 && <div><div className="text-[11.5px] text-muted">Nguyên nhân có khả năng</div><ul className="dk-diag m-0 pl-4">{d.causes.map((c, i) => <li key={i}>{clean(c)}</li>)}</ul></div>}
      {d.suggestions?.length > 0 && <div><div className="text-[11.5px] text-muted">Gợi ý</div><ul className="dk-diag m-0 pl-4">{d.suggestions.map((c, i) => <li key={i}>{clean(c)}</li>)}</ul></div>}
    </div>
  );
}

function Decisions() {
  const q = useDk("/decisions", { queryFn: ({ signal }) => api("/data/decisions", { limit: 30 }, signal) });
  return (
    <Async q={q} empty="Chưa có quyết định nào" hint="Nhật ký ghi lại mỗi lần hệ thống tự kiểm tra, lấp khoảng thiếu hoặc xử lý mã im lặng." rows={4}>
      {(d) => (
        <ul className="dk-log" aria-label="Nhật ký quyết định">
          {d.items.map((a, i) => <li key={`${a.ts}-${i}`}><span className="text-muted num text-[11.5px]" title={a.ts ? dateTime(a.ts) : ""}>{a.ts ? rel(a.ts) : "—"}</span><span>{clean(a.explain)}</span></li>)}
        </ul>
      )}
    </Async>
  );
}

export default function DuLieu() {
  const qc = useQueryClient();
  const h = useDk("/health");
  const rep = useDk("/report/daily", { refetchInterval: 300_000 });
  const re = useMutation({
    mutationFn: () => apiWrite("POST", "/data/recheck", {}),
    onSuccess: () => { toast({ tone: "ok", title: "Đã kiểm tra lại", body: "Bảng phủ dữ liệu đã được cập nhật.", ttl: 2500 }); qc.invalidateQueries({ queryKey: ["dk"] }); },
    onError: (e) => toast({ tone: e.status === 429 ? "info" : "error", title: e.status === 429 ? "Vừa kiểm tra xong" : "Không kiểm tra lại được", body: e.status === 429 ? "Đợi vài chục giây rồi thử lại." : e.message, ttl: 4000 }),
  });
  const d = h.data, sm = d?.summary;
  const health = !sm ? null : sm.broken > 0 ? "bad" : sm.slow > 0 ? "warn" : "ok";
  return (
    <>
      <PageHead title="Dữ liệu" sub="Độ phủ dữ liệu giá theo từng mã và khung thời gian: mã nào đủ, mã nào im lặng vì thị trường đóng, mã nào chậm hoặc hỏng thật."
        right={<>
          {d?.updated_at && <span className="text-[11.5px] text-muted" title={dateTime(d.updated_at)}>Cập nhật {rel(d.updated_at)}</span>}
          <button type="button" className="btn" onClick={() => re.mutate()} disabled={re.isPending} aria-label="Kiểm tra lại dữ liệu">
            <RefreshCw size={13} className={re.isPending ? "dk-spin" : ""} aria-hidden="true" /> {re.isPending ? "Đang kiểm tra…" : "Kiểm tra lại"}
          </button>
        </>} />
      {d?.mock && <div role="note" className="rounded-md border border-line2 bg-panel2 px-3 py-2 text-[12.5px] text-muted mb-3">Đang hiển thị dữ liệu mẫu (dịch vụ giám sát dữ liệu chưa kết nối).</div>}
      {d && d.enabled === false && <div role="note" className="rounded-md border border-line2 bg-panel2 px-3 py-2 text-[12.5px] text-muted mb-3">Tự động giám sát đang tắt (kill-switch). Bảng bên dưới là số liệu lần kiểm kê cuối.</div>}
      <div className="grid gap-3">
        <Panel title="Tổng quan" icon={Database} right={health && <Chip tone={KIND[health][0]}>{KIND[health][1]}</Chip>}>
          <Async q={h} rows={2} what="Tình trạng dữ liệu">
            {() => (
              <div className="dk-stats">
                <Stat label="Mã đủ dữ liệu" value={`${sm.complete}/${sm.total}`} big tone={health === "ok" ? "text-up" : undefined} term={false} />
                <Stat label="Thị trường đóng" value={sm.closed} sub="im lặng bình thường" term={false} />
                <Stat label="Chậm" value={sm.slow} tone={sm.slow ? "text-accent" : undefined} term={false} />
                <Stat label="Hỏng" value={sm.broken} tone={sm.broken ? "text-down" : undefined} term={false} />
                <Stat label="Khoảng thiếu còn" value={sm.gaps_open} term={false} />
                <Stat label="Đã lấp 24 giờ" value={sm.gaps_filled_24h} sub={sm.backfill_queue ? `${sm.backfill_queue} việc đang chờ` : undefined} term={false} />
                <Stat label="Tự chữa 24 giờ" value={sm.heal_actions_24h} term={false} />
              </div>
            )}
          </Async>
        </Panel>
        <div className="grid gap-3 lg:grid-cols-2 items-start">
          <Panel title="Chẩn đoán" icon={Bot}><Async q={h} rows={3}>{(x) => <Diagnosis d={x.diagnosis} />}</Async></Panel>
          <Panel title="Báo cáo hằng ngày" icon={FileText}>
            <Async q={rep} rows={3} what="Báo cáo hằng ngày">
              {(r) => (
                <div className="grid gap-2 text-[13px]">
                  <div className="text-[11.5px] text-muted">Ngày {r.date}</div>
                  <p className="m-0 font-medium">{clean(r.headline)}</p>
                  <p className="m-0 text-muted text-[12px]">Chi tiết nguyên nhân xem ở mục Chẩn đoán.</p>
                </div>
              )}
            </Async>
          </Panel>
        </div>
        <Panel title="Phủ dữ liệu theo mã và khung" icon={Database}>
          <Async q={h} variant="table" rows={8} cols={8} isEmpty={(x) => !x?.symbols?.length} empty="Chưa có số liệu kiểm kê" hint="Dịch vụ giám sát chưa hoàn tất lần kiểm kê đầu tiên. Bấm “Kiểm tra lại” sau ít phút.">
            {(x) => <Matrix data={x} />}
          </Async>
        </Panel>
        <Panel title="Nhật ký quyết định" icon={History}><Decisions /></Panel>
      </div>
    </>
  );
}
