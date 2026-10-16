import { useState } from "react";
import { Eye, LogOut } from "lucide-react";
import { Panel } from "../ui";
import { money, signCls } from "../../lib/format";
import { EquitySpark, Quick } from "./AccountDetail";
import { HealthChip, RiskChip } from "./bits";
import { endViewAs, getViewAs, useViewAsGrant } from "../../lib/fleetApi";

export const impKey = (id) => `clients.imp:${id}`;
export const markImpersonating = (id) => { try { sessionStorage.setItem(impKey(id), String(Date.now())); } catch { /* bỏ qua */ } };

/** "Xem như khách hàng": bản sao CHỈ-ĐỌC những gì khách thấy ở cổng khách (tài khoản, vị thế, rủi ro, nhật ký). Có banner cố định; việc bắt đầu xem được ghi audit (view_as). */
export default function ViewAs({ row, id }) {
  const [busy, setBusy] = useState(false);
  const grant = useViewAsGrant(); // nếu có phiên xem-như-khách do máy chủ cấp: banner đếm ngược dùng chung ở App (FleetRoot)
  let ok = false;
  try { ok = !!sessionStorage.getItem(impKey(id)); } catch { /* bỏ qua */ }
  const exit = async () => {
    setBusy(true);
    try { sessionStorage.removeItem(impKey(id)); } catch { /* bỏ qua */ }
    if (getViewAs()) { await endViewAs(getViewAs()); location.hash = "#/doi-tai-khoan"; return; }
    location.hash = `#/khach-hang/danh-sach/${id}`;
  };
  if (!ok || !row) {
    return (
      <Panel title="Xem như khách hàng" icon={Eye}>
        <p className="m-0 mb-3 text-muted">Cần mở từ hồ sơ khách hàng (nút “Xem như khách hàng”) để xác nhận và ghi nhật ký kiểm toán.</p>
        <a className="btn no-underline" href={row ? `#/khach-hang/danh-sach/${id}` : "#/khach-hang/danh-sach"}>Về hồ sơ</a>
      </Panel>
    );
  }
  return (
    <div className="grid gap-3">
      {!grant && <div role="status" className="imp-banner">
        <Eye size={16} aria-hidden="true" />
        <span className="min-w-0"><b>ĐANG XEM NHƯ KHÁCH HÀNG</b> · {row.client_name || row.account_id} · <span className="num">{row.account_id}</span> · chỉ đọc — mọi thao tác ghi bị vô hiệu; việc xem đã được ghi vào nhật ký kiểm toán.</span>
        <button className="btn ml-auto !h-8" onClick={exit} disabled={busy}><LogOut size={13} aria-hidden="true" />{busy ? "Đang thoát…" : "Thoát chế độ xem"}</button>
      </div>}
      <div className="imp-frame" aria-label={`Giao diện khách hàng ${row.account_id}`}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="m-0 text-[16px]">{row.label || row.login}</h2><HealthChip row={row} /><RiskChip level={row.riskLevel} reasons={row.riskReasons} />
          <span className="ml-auto text-[12px] text-muted">{row.platform.toUpperCase()} · {row.server}</span>
        </div>
        <Panel title="Tài khoản của tôi"><Quick row={row} /></Panel>
        <Panel title="Equity 7 ngày" bodyClass="flex flex-col"><EquitySpark id={row.account_id} /></Panel>
        <Panel title={`Vị thế đang mở (${row.positions.length})`} pad={false}>
          {row.positions.length ? <div className="scroll-x"><table className="tbl" style={{ minWidth: 420 }}><thead><tr><th>Symbol</th><th>Hướng</th><th className="r">Khối lượng</th><th className="r">Lãi/lỗ</th></tr></thead>
            <tbody>{row.positions.map((p) => <tr key={p.ticket}><td>{p.symbol}</td><td>{p.type === 1 ? "Bán" : "Mua"}</td><td className="r num">{p.volume}</td><td className={`r num ${signCls(p.profit)}`}>{money(p.profit)}</td></tr>)}</tbody></table></div>
            : <p className="m-0 p-3 text-muted">Không có vị thế đang mở.</p>}
        </Panel>
        {row.riskReasons.length > 0 && <Panel title="Rủi ro"><p className="m-0">{row.riskReasons.join(" · ")}</p></Panel>}
      </div>
    </div>
  );
}
