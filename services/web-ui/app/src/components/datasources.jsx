import { Gauge } from "lucide-react";
import { Async, Chip, Panel } from "./ui";
import { useDataSources, useNow } from "../lib/queries";
import { dateTime, rel } from "../lib/format";

// Chỉ hiển thị trạng thái TỔNG HỢP trung tính. Không nêu tên nguồn/nhà cung cấp dữ liệu (xem scripts/lint-sources.cjs).
const grp = (list) => {
  const l = list || [];
  if (l.some((s) => s.state === "active")) return { tone: "up", label: "Tốt" };
  if (l.some((s) => s.state === "needs_key")) return { tone: "accent", label: "Cần cấu hình" };
  return { tone: "", label: "Tạm ngưng" };
};

export function DataSourcesPanels() {
  const q = useDataSources();
  const now = useNow(1000);
  const d = q.data;
  const rec = d?.reconcile;
  const results = rec?.results || [];
  const recSt = results.some((r) => r.status === "warn" || r.status === "error")
    ? { tone: "down", label: "Có lệch" }
    : results.some((r) => r.status === "ok") ? { tone: "up", label: "Khớp" } : { tone: "", label: "Chưa có dữ liệu" };
  const rows = d ? [
    { k: "Dữ liệu giá", st: d.market_error ? { tone: "down", label: "Không phản hồi" } : grp(d.market), note: "Nến và giá tick" },
    { k: "Tin tức", st: d.news_error ? { tone: "down", label: "Không phản hồi" } : grp(d.news), note: "Tin và lịch kinh tế" },
    { k: "Đối chiếu giá", st: recSt, note: results.length ? `${results.length} cặp được kiểm tra${rec.generated_at ? ` · chạy ${rel(rec.generated_at, now)}` : ""}` : "Chạy mỗi 15 phút; cuối tuần chưa có dữ liệu" },
  ] : [];
  return (
    <div className="grid gap-3 mt-3">
      <Panel title="Tình trạng dữ liệu" icon={Gauge} pad={false} scroll
        right={rec?.generated_at && <span className="text-[11.5px] text-faint hidden sm:inline" title={dateTime(rec.generated_at)}>cập nhật {rel(rec.generated_at, now)}</span>}>
        <Async q={q} rows={3} empty="Chưa đọc được trạng thái dữ liệu." isEmpty={() => !rows.length}>
          {() => (
            <div className="scroll-x">
              <table className="tbl" style={{ minWidth: 420 }}>
                <thead><tr><th>Hạng mục</th><th>Trạng thái</th><th>Ghi chú</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.k}>
                      <td className="font-medium whitespace-nowrap">{r.k}</td>
                      <td><Chip tone={r.st.tone}>{r.st.label}</Chip></td>
                      <td className="text-[11.5px] text-muted">{r.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </Panel>
    </div>
  );
}
