import "../vn.css";
import { useEffect, useState } from "react";
import { Async, Chip, Disclaimer, PageHead, Skeleton, cn } from "../components/ui";
import { IndexCard } from "../components/vn/vnbits";
import { EventsTab, ForeignTab, ScreenerTab, SymbolTab } from "../components/vn/tabs2";
import { HeatmapTab, MoversTab, OverviewTab } from "../components/vn/tabs";
import { useVnOverview, useVnStatus } from "../lib/vn";
import { dateY } from "../lib/format";

const TABS = [
  ["tong-quan", "Tổng quan"], ["heatmap", "Bản đồ nhiệt ngành"], ["top", "Top & trần/sàn"], ["ngoai", "Khối ngoại"],
  ["loc", "Bộ lọc cổ phiếu"], ["su-kien", "Sự kiện & tin"], ["ma", "Chi tiết mã"],
];
const PHASE = { pre: "Trước phiên", ato: "ATO", continuous: "Khớp liên tục", lunch: "Nghỉ trưa", atc: "ATC", plo: "Thoả thuận", closed: "Đóng cửa" };
const FLOOR = { HOSE: "HOSE", HNX: "HNX", UPCOM: "UPCoM" };

function SessionPills({ session }) {
  return (
    <div className="flex flex-wrap gap-1" aria-label="Phiên giao dịch hiện tại theo sàn (giờ Việt Nam)">
      {Object.entries(session || {}).map(([f, s]) => (
        <Chip key={f} className={s.open ? "up" : ""} title={`${s.label}${s.next_label ? ` · kế tiếp: ${s.next_label}` : ""} (không xét ngày lễ)`}>
          {FLOOR[f]} · {PHASE[s.code] || s.label}
        </Chip>
      ))}
    </div>
  );
}

export default function ChungKhoanVN({ arg }) {
  const [tab, ...rest] = (arg || "tong-quan").split("/");
  const active = TABS.some(([k]) => k === tab) ? tab : "tong-quan";
  const code = active === "ma" ? rest[0] : undefined;
  const ov = useVnOverview();
  const st = useVnStatus();
  const [, force] = useState(0);
  useEffect(() => { const t = setInterval(() => force((n) => n + 1), 60_000); return () => clearInterval(t); }, []); // cập nhật nhãn phiên mỗi phút

  const stale = st.data?.stale;
  return (
    <>
      <PageHead title="Chứng khoán Việt Nam"
        sub="Số liệu cuối ngày của HOSE, HNX, UPCoM: chỉ số, độ rộng, ngành, khối ngoại, bộ lọc cổ phiếu và sự kiện. Chỉ đọc, không đặt lệnh."
        right={<>
          {ov.data && <SessionPills session={ov.data.session} />}
          {ov.data && <Chip className={stale ? "down" : ""} title={ov.data.delay}>Dữ liệu chốt phiên {dateY(ov.data.as_of)}{stale ? " · chậm" : ""}</Chip>}
        </>} />
      {stale && <Disclaimer>Dữ liệu chưa theo kịp phiên mới nhất ({st.data.expected_latest}). Nếu quá hạn kéo dài, nguồn dữ liệu có thể đã thay đổi: xem trang Hệ thống.</Disclaimer>}
      <Async q={ov} rows={3} isEmpty={(d) => !d?.indices} empty="Đang nạp dữ liệu lần đầu." hint="Lần chạy đầu mất vài phút (lịch sử 30 phiên); tải lại trang sau.">
        {(d) => <div className="vn-idx" role="list" aria-label="Chỉ số chính">{d.indices.map((ix) => <div role="listitem" key={ix.code}><IndexCard ix={ix} /></div>)}</div>}
      </Async>
      <div className="vn-tabs" role="tablist" aria-label="Mục chứng khoán Việt Nam">
        {TABS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={active === k} onClick={() => { location.hash = `#/chung-khoan-vn/${k}`; }}>{l}</button>
        ))}
      </div>
      <div role="tabpanel" className="grid gap-3 min-w-0">
        {active === "tong-quan" && (ov.data ? <OverviewTab ov={ov.data} /> : <Skeleton rows={8} h={18} />)}
        {active === "heatmap" && <HeatmapTab />}
        {active === "top" && <MoversTab />}
        {active === "ngoai" && <ForeignTab />}
        {active === "loc" && <ScreenerTab />}
        {active === "su-kien" && <EventsTab />}
        {active === "ma" && <SymbolTab code={code} />}
      </div>
      <p className={cn("m-0 text-[11.5px] text-faint")}>
        Dữ liệu cuối ngày, không chính thức · không phải khuyến nghị đầu tư. Chưa có: giá realtime trong phiên, tự doanh, BCTC chi tiết.
      </p>
    </>
  );
}
