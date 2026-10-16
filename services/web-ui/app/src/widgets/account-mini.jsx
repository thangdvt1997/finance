import { Wallet } from "lucide-react";
import { Async, Chip, cn } from "../components/ui";
import { useAccounts } from "../lib/queries";
import { money, signCls } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "account-mini", title: "Tài khoản MT", icon: Wallet, group: "Tài khoản", desc: "Equity, balance, lãi/lỗ đang mở và mức margin (chỉ đọc).",
  defaultSize: { w: 7, h: 8 }, minSize: { w: 4, h: 4 },
  configSchema: [{ key: "only", label: "Chỉ hiện tài khoản (để trống = tất cả)", type: "text", default: "", placeholder: "vd: mt5:12345678" }],
};

export default function AccountMini() {
  const { config } = useWidget();
  const q = useAccounts();
  return (
    <div className="tm-fill tm-scroll tm-pad">
      <Async q={q} rows={3} empty="Chưa có tài khoản MT nào gửi dữ liệu." hint="Kết nối tài khoản investor ở trang Khách hàng." isEmpty={(d) => !d.length}>
        {(list) => (
          <div className="grid gap-2">
            {list.filter((a) => !config.only || a.account_id === config.only).map((a) => {
              const fl = (a.positions || []).reduce((s, p) => s + (p.profit || 0), 0);
              const level = a.margin ? (a.equity / a.margin) * 100 : null;
              return (
                <a key={a.account_id} href="#/tai-khoan" className="no-underline text-fg rounded-md border border-line p-2 hover:border-line2 block">
                  <div className="flex items-center gap-2 flex-wrap"><b className="break-all text-[12.5px]">{a.account_id}</b><Chip>{String(a.platform).toUpperCase()}</Chip><Chip tone="ro">CHỈ ĐỌC</Chip></div>
                  <div className="grid grid-cols-3 gap-2 mt-1.5">
                    <div><div className="tm-sub">Equity</div><div className="num text-[14px]">{money(a.equity)}</div></div>
                    <div><div className="tm-sub">Balance</div><div className="num text-[14px]">{money(a.balance)}</div></div>
                    <div><div className="tm-sub">Đang mở ({a.positions?.length || 0})</div><div className={cn("num text-[14px]", signCls(fl))}>{money(fl)}</div></div>
                  </div>
                  {level != null && <div className="tm-sub mt-1">Mức margin <b className={cn("num", level < 150 ? "down" : "up")}>{level.toFixed(0)}%</b></div>}
                </a>
              );
            })}
          </div>
        )}
      </Async>
    </div>
  );
}
