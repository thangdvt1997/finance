import { CalendarDays, CalendarRange, Download, ExternalLink } from "lucide-react";
import { Async, Chip, Disclaimer, PageHead, Panel } from "../components/ui";
import { useReports } from "../lib/queries";
import { dateTime } from "../lib/format";

const KIND = { daily: "Báo cáo ngày", weekly: "Báo cáo tuần" };
const fileUrl = (it, ext) => `/api/v1/reports/${it.kind}/${it.period}.${ext}`;
const size = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);

function ReportRow({ it }) {
  const miss = it.sections_fail || [];
  return (
    <li className="rounded-md border border-line bg-panel2 p-3 grid gap-2 sm:grid-cols-[1fr_auto] items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <b>{KIND[it.kind] || it.kind} · {it.period}</b>
          <Chip title="Báo cáo chỉ đọc / mô phỏng, không đặt lệnh">READ-ONLY</Chip>
          {it.status === "ok" ? <Chip tone="up">Đầy đủ</Chip> : <Chip tone="accent" title={miss.join(", ")}>Thiếu {miss.length} mục</Chip>}
        </div>
        <div className="text-[12px] text-muted">
          Tạo lúc {dateTime(it.generated_at)} · HTML {size(it.bytes)}{it.pdf_bytes ? ` · PDF ${size(it.pdf_bytes)}` : " · chưa có PDF"}
        </div>
        {miss.length > 0 && <div className="text-[11.5px] text-faint">Mục chưa có dữ liệu: {miss.join(", ")}</div>}
        <div className="text-[11px] text-faint font-mono truncate" title={it.sha256}>sha256 {String(it.sha256 || "").slice(0, 16)}…</div>
      </div>
      <div className="flex flex-wrap gap-2">
        <a className="btn no-underline" href={fileUrl(it, "html")} target="_blank" rel="noopener noreferrer"><ExternalLink size={13} aria-hidden="true" /> Xem</a>
        {it.pdf_bytes > 0 && <a className="btn no-underline" href={fileUrl(it, "pdf")} download><Download size={13} aria-hidden="true" /> Tải PDF</a>}
        <a className="btn no-underline" href={fileUrl(it, "html")} download={`${it.kind}-${it.period}.html`}><Download size={13} aria-hidden="true" /> Tải HTML</a>
      </div>
    </li>
  );
}

function Group({ kind, icon, items, next }) {
  const list = items.filter((i) => i.kind === kind);
  return (
    <Panel title={KIND[kind]} icon={icon} right={next ? <span className="text-[12px] text-muted">Lần chạy kế tiếp: {dateTime(next)}</span> : null}>
      {list.length === 0 ? (
        <p className="m-0 text-muted">Chưa có {KIND[kind].toLowerCase()} nào. Báo cáo được tạo tự động theo lịch.</p>
      ) : (
        <ul className="m-0 p-0 list-none grid gap-2">{list.map((it) => <ReportRow key={`${it.kind}-${it.period}`} it={it} />)}</ul>
      )}
    </Panel>
  );
}

export default function Reports() {
  const q = useReports();
  return (
    <>
      <PageHead title="Báo cáo" sub="Báo cáo tự động hằng ngày (06:30) và hằng tuần (Chủ nhật 19:00, giờ Việt Nam): HTML xem trực tiếp và PDF để lưu/in." />
      <Disclaimer>Báo cáo chỉ đọc / mô phỏng, không phải lời khuyên đầu tư. Thông tin chuyên gia và chỉ báo chỉ để tham khảo.</Disclaimer>
      <div className="grid gap-3 mt-3">
        <Async q={q} rows={5} isEmpty={(d) => !d} empty="Chưa có dữ liệu báo cáo.">
          {(d) => {
            const items = [...(d.items || [])].sort((a, b) => String(b.period).localeCompare(String(a.period)));
            return (
              <>
                <Group kind="daily" icon={CalendarDays} items={items} next={d.next_runs?.daily} />
                <Group kind="weekly" icon={CalendarRange} items={items} next={d.next_runs?.weekly} />
              </>
            );
          }}
        </Async>
      </div>
    </>
  );
}
