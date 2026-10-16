import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, BookOpen, Inbox } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel, Seg, Skeleton } from "../components/ui";
import { useJnAccounts, useJnDeals, useJnSummary } from "../lib/queries";
import { lget, lset } from "../lib/lstore";
import { vnDayKey, vnDayStart } from "../lib/format";
import { AccountBadges, CalendarHeat, ContributionPanel, EquityPanel, GroupPanel, KpiRow, MiscPanel, RPanel, accountFlags, fN } from "../components/journal";
import { DealDialog, DealsPanel, DisciplinePanel, ExcursionPanel, ReviewPanel } from "../components/journalDeals";

const KEY = "journal.v1";
const RANGES = [{ value: "7", label: "7 ngày" }, { value: "30", label: "30 ngày" }, { value: "90", label: "90 ngày" }, { value: "all", label: "Tất cả" }, { value: "custom", label: "Tuỳ chọn" }];
const TABS = [{ value: "overview", label: "Tổng quan" }, { value: "deals", label: "Lệnh" }, { value: "discipline", label: "Kỷ luật" }, { value: "review", label: "Review tuần" }];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function useStored() {
  const [s, setS] = useState(() => lget(KEY, {}));
  const upd = (patch) => setS((p) => { const n = { ...p, ...patch }; lset(KEY, n); return n; });
  return [s, upd];
}

export default function Journal() {
  const [st, upd] = useStored();
  const accQ = useJnAccounts();
  const accounts = accQ.data?.items || [];
  const acc = accounts.find((a) => a.account_id === st.acc) || accounts.find((a) => a.n_trades > 0) || accounts[0];
  const accId = acc?.account_id;
  const range = st.range || "30";
  const tab = st.tab || "overview";
  const [day, setDay] = useState(null);
  const [open, setOpen] = useState(null);
  const [dim, setDim] = useState("hour");
  const [seen, setSeen] = useState({ acc: null, symbols: [], groups: [] });

  const today = vnDayKey(new Date());
  const dates = useMemo(() => {
    if (range === "all") return {};
    if (range === "custom") return { from: DATE_RE.test(st.from || "") ? st.from : undefined, to: DATE_RE.test(st.to || "") ? st.to : undefined };
    return { from: vnDayKey(vnDayStart(-(Number(range) - 1))), to: today };
  }, [range, st.from, st.to, today]);
  const filters = useMemo(() => ({ ...dates, symbol: st.symbol || undefined, group: st.group || undefined, side: st.side || undefined }), [dates, st.symbol, st.group, st.side]);

  const sumQ = useJnSummary(accId, filters);
  const sd = sumQ.data;

  // gom danh sách symbol/EA đã thấy (để dropdown không biến mất khi đang lọc)
  useEffect(() => {
    if (!sd || !accId) return;
    setSeen((p) => {
      const base = p.acc === accId ? p : { acc: accId, symbols: [], groups: [] };
      const symbols = [...new Set([...base.symbols, ...(sd.groups?.symbol || []).map((r) => r.key)])].sort();
      const groups = [...new Set([...base.groups, ...(sd.groups?.magic || []).map((r) => r.key)])].sort();
      return symbols.length === base.symbols.length && groups.length === base.groups.length && base === p ? p : { acc: accId, symbols, groups };
    });
  }, [sd, accId]);
  const symbols = seen.acc === accId ? seen.symbols : [];
  const groups = seen.acc === accId ? seen.groups : [];

  // gợi ý tag (từ danh sách lệnh, không lọc)
  const tagQ = useJnDeals(accId, { limit: 1 });
  const tagHints = useMemo(() => (tagQ.data?.tags || []).map((t) => t.tag), [tagQ.data]);

  const params = st.disc || {};
  const setParams = (o) => upd({ disc: o });
  const cur = acc?.currency || "";
  const openDeal = (d) => setOpen(d);
  const pickDay = (k) => { setDay(k); if (k) upd({ tab: "deals" }); };
  const changeAcc = (id) => { upd({ acc: id }); setDay(null); setSeen({ acc: null, symbols: [], groups: [] }); };

  const sel = "field";
  const noTrades = acc && acc.n_trades === 0;
  const emptyWindow = sd && sd.summary?.n === 0 && !noTrades;

  return (
    <>
      <PageHead title="Nhật ký giao dịch" sub="Thống kê, kỷ luật và review từ lịch sử lệnh ĐÃ ĐÓNG của tài khoản MT (EA gửi deal) và paper. Chỉ đọc: chỉ ghi chú/tag được lưu."
        right={acc ? <><AccountBadges a={acc} />{sd?.base_source && <Chip title="Số dư gốc dùng cho % drawdown">có số dư gốc</Chip>}</> : null} />

      <Panel pad={false}>
        <form className="flex flex-wrap items-end gap-x-3 gap-y-2 p-3" aria-label="Bộ lọc nhật ký" onSubmit={(e) => e.preventDefault()}>
          <label className="grid gap-1 text-[11.5px] text-muted">Tài khoản
            <select className={sel + " min-w-[220px]"} value={accId || ""} onChange={(e) => changeAcc(e.target.value)} disabled={!accounts.length}>
              {!accounts.length && <option value="">{accQ.isPending ? "Đang tải…" : "Chưa có tài khoản"}</option>}
              {accounts.map((a) => {
                const f = accountFlags(a);
                return <option key={a.account_id} value={a.account_id}>{`${a.name || a.account_id} · ${a.kind === "mt" ? "MT" : "Paper"}${f.sim ? " · MÔ PHỎNG" : f.fixture ? " · FIXTURE" : ""} · ${a.n_trades} lượt khớp lệnh`}</option>;
              })}
            </select>
          </label>
          <div className="grid gap-1 text-[11.5px] text-muted">Khoảng thời gian
            <Seg value={range} onChange={(v) => { upd({ range: v }); setDay(null); }} options={RANGES} label="Khoảng thời gian" />
          </div>
          {range === "custom" && (
            <>
              <label className="grid gap-1 text-[11.5px] text-muted">Từ ngày<input type="date" className={sel} value={st.from || ""} max={st.to || today} onChange={(e) => upd({ from: e.target.value })} /></label>
              <label className="grid gap-1 text-[11.5px] text-muted">Đến ngày<input type="date" className={sel} value={st.to || ""} min={st.from || undefined} max={today} onChange={(e) => upd({ to: e.target.value })} /></label>
            </>
          )}
          <label className="grid gap-1 text-[11.5px] text-muted">Symbol
            <select className={sel} value={st.symbol || ""} onChange={(e) => upd({ symbol: e.target.value })}>
              <option value="">Tất cả</option>{[...new Set([...(st.symbol ? [st.symbol] : []), ...symbols])].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-[11.5px] text-muted">EA / chiến lược
            <select className={sel} value={st.group || ""} onChange={(e) => upd({ group: e.target.value })}>
              <option value="">Tất cả</option>{[...new Set([...(st.group ? [st.group] : []), ...groups])].map((g) => <option key={g} value={g}>{g === "manual" ? "Thủ công" : g}</option>)}
            </select>
          </label>
          <div className="grid gap-1 text-[11.5px] text-muted">Hướng
            <Seg value={st.side || ""} onChange={(v) => upd({ side: v })} label="Hướng lệnh" options={[{ value: "", label: "Cả hai" }, { value: "buy", label: "Mua" }, { value: "sell", label: "Bán" }]} />
          </div>
          {(st.symbol || st.group || st.side) && <button type="button" className="btn" onClick={() => upd({ symbol: "", group: "", side: "" })}>Xoá lọc</button>}
          <span className="ml-auto text-[11.5px] text-faint num">{acc?.first ? `dữ liệu ${String(acc.first).slice(0, 10).split("-").reverse().join("/")} → ${String(acc.last).slice(0, 10).split("-").reverse().join("/")}` : ""}</span>
        </form>
      </Panel>

      <Disclaimer>Các chỉ số tính trên lệnh <b>đã đóng</b> trong khoảng chọn, <b>không gồm lệnh đang mở (floating P/L)</b>. Dữ liệu tham khảo để tự soi lại giao dịch, không phải khuyến nghị đầu tư.{acc && accountFlags(acc).sim ? " Tài khoản này là MÔ PHỎNG để thử giao diện." : ""}</Disclaimer>

      {accQ.isPending ? <Skeleton rows={6} /> : accQ.isError ? <Async q={accQ}>{() => null}</Async> : !accounts.length ? (
        <EmptyAccounts />
      ) : noTrades ? (
        <EmptyAccount acc={acc} />
      ) : sumQ.isPending ? <Skeleton rows={8} h={18} /> : sumQ.isError ? (
        <Panel title="Không tải được thống kê"><Async q={sumQ}>{() => null}</Async></Panel>
      ) : (
        <>
          {emptyWindow && (
            <div role="status" className="panel panel-b flex flex-wrap items-center gap-3 text-muted">
              <Inbox size={16} aria-hidden="true" /> Không có lệnh nào trong bộ lọc này.
              {acc?.n_trades > 0 && <button className="btn" onClick={() => upd({ range: "all", symbol: "", group: "", side: "" })}>Xem tất cả thời gian và bỏ lọc</button>}
            </div>
          )}
          <KpiRow s={sd.summary} eq={sd.equity} cur={cur} />
          {sd.notes?.length > 0 && <div className="text-[11.5px] text-faint" role="note">{sd.notes.join(" · ")}</div>}

          <Seg value={tab} onChange={(v) => upd({ tab: v })} options={TABS} label="Mục nhật ký" className="self-start" />

          {tab === "overview" && !emptyWindow && (
            <div className="grid gap-3">
              <EquityPanel eq={sd.equity} cur={cur} />
              <CalendarHeat calendar={sd.calendar} picked={day} onPick={pickDay} cur={cur} />
              <div className="grid gap-3 xl:grid-cols-2">
                <RPanel r={sd.r} />
                <GroupPanel groups={sd.groups} dim={dim} setDim={setDim} />
              </div>
              <ContributionPanel rows={sd.contribution} />
              <MiscPanel s={sd.summary} streaks={sd.streaks} hold={sd.hold} costs={sd.costs} cur={cur} />
            </div>
          )}
          {tab === "deals" && <DealsPanel acc={accId} filters={filters} day={day} onClearDay={() => setDay(null)} onOpen={openDeal} tagHints={tagHints} cur={cur} />}
          {tab === "discipline" && (
            <div className="grid gap-3">
              <DisciplinePanel acc={accId} filters={filters} onOpen={openDeal} params={params} setParams={setParams} cur={cur} />
              <ExcursionPanel acc={accId} filters={filters} />
            </div>
          )}
          {tab === "review" && <ReviewPanel acc={accId} onOpen={openDeal} tagHints={tagHints} cur={cur} />}
        </>
      )}

      {open && <DealDialog acc={accId} deal={open} onClose={() => setOpen(null)} tagHints={tagHints} cur={cur} />}
    </>
  );
}

function EmptyAccounts() {
  return (
    <Panel title="Chưa có tài khoản nào" icon={BookOpen}>
      <p className="m-0 text-muted">Nhật ký cần lịch sử deal. Cài <b>EA agent</b> trên MT4/MT5 để gửi lịch sử deal về hệ thống (chỉ đọc), hoặc dùng tài khoản <b>paper</b> của hệ thống. Khi có dữ liệu, tài khoản sẽ hiện ở ô chọn phía trên.</p>
    </Panel>
  );
}
function EmptyAccount({ acc }) {
  return (
    <Panel title={`${acc.name || acc.account_id} chưa có lệnh nào`} icon={BookOpen}>
      <div className="grid gap-2 text-muted">
        <p className="m-0 flex items-start gap-2"><AlertTriangle size={15} className="text-accent shrink-0 mt-[3px]" aria-hidden="true" />
          {acc.kind === "mt"
            ? <span>Tài khoản MT này chưa có deal đã đóng. Hãy để <b>EA agent</b> trên MT4/MT5 gửi lịch sử deal về hệ thống; sau khi nhận, thống kê sẽ xuất hiện tại đây (không cần thao tác thêm).</span>
            : <span>Tài khoản paper này chưa có lệnh đã đóng (n=0). Khi bot/chiến lược paper đóng lệnh, nhật ký sẽ tự cập nhật. Có thể chọn tài khoản khác ở ô phía trên.</span>}
        </p>
        <p className="m-0 text-[12px] text-faint num">{fN(acc.n_trades, 0)} lượt khớp lệnh (đếm fill; thống kê dùng lệnh đã đóng)</p>
      </div>
    </Panel>
  );
}
