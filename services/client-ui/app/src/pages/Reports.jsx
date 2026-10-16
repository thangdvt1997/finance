// "Báo cáo của tôi": báo cáo ngày/tuần/tháng theo tài khoản của phiên.
// Backend chưa có API báo cáo theo khách hàng (các /reports hiện chỉ dành cho quản trị) -> khi GET /user/reports không khả dụng,
// giao diện chạy bằng DỮ LIỆU MẪU có cờ rõ ràng và nút tải bị khoá. Khi API sẵn sàng (trả {items:[{kind,period,...}]}) trang tự dùng dữ liệu thật.
import { useCallback, useMemo, useState } from "react";
import { Download, FileBarChart, FlaskConical, Lock } from "lucide-react";
import { Chip, Kpi, Notice, PageHead, Panel, Seg, Sheet, Skeleton, cn } from "../components/ui";
import { accountTitle, useAuth } from "../lib/auth";
import { sampleReports } from "../lib/mock_today";
import { useMyReports } from "../lib/q_today";
import { f0, f1, signCls, smoney } from "../lib/format";
import { t } from "../lib/i18n";

const periodText = (r) => {
  const [y, m, d] = String(r.period).split("-");
  if (r.kind === "monthly") return t("Tháng {m}/{y}", { m, y });
  const day = `${d}/${m}/${y}`;
  return r.kind === "weekly" ? t("Tuần kết thúc {d}", { d: day }) : t("Ngày {d}", { d: day });
};
const kindTitle = (k) => (k === "weekly" ? t("Báo cáo tuần") : k === "monthly" ? t("Báo cáo tháng") : t("Báo cáo ngày"));

function ReportSheet({ r, sample, onClose }) {
  const dd = r.max_dd_pct;
  return (
    <Sheet title={`${kindTitle(r.kind)} · ${periodText(r)}`} onClose={onClose}>
      {sample && <Notice tone="warn" icon={FlaskConical} title={t("Dữ liệu mẫu — chờ backend")} className="mb-3">{t("Số liệu dưới đây là ví dụ để xem giao diện, không phải kết quả thật của bạn.")}</Notice>}
      <div className="kpi-grid">
        <Kpi label={t("Lãi/lỗ đã chốt")} value={smoney(r.pnl)} tone={signCls(r.pnl)} sub={r.currency} />
        <Kpi label={t("Số lệnh")} value={f0(r.trades)} />
        <Kpi label={t("Tỷ lệ thắng")} value={`${f0(r.win_rate)}%`} />
        <Kpi label={t("Sụt vốn tối đa")} value={dd == null ? "—" : `${f1(dd, 1)}%`} />
      </div>
      <p className="m-0 mt-3 text-[12.5px] text-faint">{t("Báo cáo chỉ tổng hợp số liệu tài khoản của bạn để tham khảo, không phải khuyến nghị đầu tư.")}</p>
    </Sheet>
  );
}

export default function Reports() {
  const { active } = useAuth();
  const q = useMyReports(active?.id);
  const [kind, setKind] = useState("all");
  const [open, setOpen] = useState(null);
  const close = useCallback(() => setOpen(null), []);
  const real = q.isSuccess && Array.isArray(q.data?.items) ? q.data.items.map((r) => ({ ...r, id: `${r.kind}-${r.period}` })) : null;
  const sample = !real;
  const rows = useMemo(() => (real || sampleReports()).filter((r) => kind === "all" || r.kind === kind), [real, kind]);

  return (
    <>
      <PageHead title={t("Báo cáo của tôi")} sub={t("Tổng hợp theo ngày, tuần, tháng cho tài khoản {a}.", { a: accountTitle(active) })} />
      {q.isPending ? <Skeleton rows={4} h={20} /> : (
        <>
          {sample && (
            <Notice tone="warn" icon={FlaskConical} title={t("Dữ liệu mẫu — chờ backend")}>
              {t("Báo cáo riêng cho từng khách hàng chưa khả dụng trên máy chủ. Danh sách dưới đây chỉ là ví dụ để xem giao diện; nút tải sẽ mở khi tính năng sẵn sàng.")}
            </Notice>
          )}
          <Panel title={t("Danh sách báo cáo")} icon={FileBarChart} pad={false}
            right={<Seg value={kind} onChange={setKind} label={t("Loại báo cáo")} scroll options={[{ value: "all", label: t("Tất cả") }, { value: "daily", label: t("Ngày") }, { value: "weekly", label: t("Tuần") }, { value: "monthly", label: t("Tháng") }]} />}>
            {rows.length === 0 ? <p className="m-0 p-4 text-muted text-[13.5px]">{t("Chưa có báo cáo nào.")}</p> : (
              <ul className="list-none m-0 p-0">
                {rows.map((r) => (
                  <li key={r.id || `${r.kind}-${r.period}`} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3.5 py-3 border-b border-line last:border-0">
                    <div className="min-w-0 flex-1 basis-[11rem]">
                      <div className="flex flex-wrap items-center gap-1.5"><b>{kindTitle(r.kind)}</b>{sample && <Chip tone="accent">{t("Dữ liệu mẫu")}</Chip>}</div>
                      <div className="text-[12.5px] text-muted">{periodText(r)}{r.trades != null ? ` · ${t("{n} lệnh", { n: f0(r.trades) })}` : ""}</div>
                    </div>
                    {r.pnl != null && <div className={cn("num font-semibold text-right", signCls(r.pnl))}>{smoney(r.pnl)}<div className="text-[11.5px] text-faint font-normal">{r.currency || ""}</div></div>}
                    <div className="flex items-center gap-2 ml-auto">
                      {sample
                        ? <button type="button" className="btn sm" onClick={() => setOpen(r)}>{t("Xem")}</button>
                        : <a className="btn sm" target="_blank" rel="noopener noreferrer" href={`/c/api/v1/account-reports/${encodeURIComponent(active?.id || "")}/${encodeURIComponent(r.period)}/html?kind=${encodeURIComponent(r.kind)}`}>{t("Xem")}</a>}
                      {sample
                        ? <button type="button" className="btn sm" disabled title={t("Chưa khả dụng: chờ backend")}><Lock size={14} aria-hidden="true" /> {t("Tải về")}<span className="sr-only"> ({t("chưa khả dụng")})</span></button>
                        : <a className="btn sm" href={`/c/api/v1/account-reports/${encodeURIComponent(active?.id || "")}/${encodeURIComponent(r.period)}/pdf?kind=${encodeURIComponent(r.kind)}`} download><Download size={14} aria-hidden="true" /> {t("Tải về")}</a>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <p className="m-0 text-[12px] text-faint">{t("Báo cáo chỉ gồm tài khoản của bạn. Số liệu để tham khảo, không phải khuyến nghị đầu tư.")}</p>
        </>
      )}
      {open && <ReportSheet r={open} sample={sample} onClose={close} />}
    </>
  );
}
