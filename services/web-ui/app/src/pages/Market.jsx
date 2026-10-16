// Trang "Thị trường": danh sách mã (theo loại tài sản) + không gian biểu đồ chuyên nghiệp (ChartWorkspace: nhiều biểu đồ đồng bộ, replay,
// mẫu, công cụ vẽ mở rộng, lớp phủ phiên/lịch/tin/cảnh báo). Logic biểu đồ nằm ở components/chart/ChartWorkspace.jsx.
// BỐ CỤC: .mkt-ws có chiều cao cố định theo vùng nội dung (xem index.css) → panel danh sách cuộn nội bộ, chart lấp đầy phần còn lại.
import { useEffect, useMemo, useState } from "react";
import { PageHead } from "../components/ui";
import { RiskBanner } from "../components/risk";
import { useRiskSymbol, useSymbols } from "../lib/queries";
import { symbolLabel } from "../lib/format";
import { lget, lset } from "../lib/lstore";
import SymbolList from "../components/chart/SymbolList";
import ChartWorkspace from "../components/chart/ChartWorkspace";
import { KNOWN_TFS } from "../components/chart/chartData";

const FAV_KEY = "ts-fav";

function parseArg(arg) {
  const [s, qs] = String(arg || "").split("?");
  const tf = new URLSearchParams(qs || "").get("tf");
  return { symbol: s ? decodeURIComponent(s) : null, tf: KNOWN_TFS.includes(tf) ? tf : null };
}

export default function Market({ arg }) {
  const init = useMemo(() => parseArg(arg), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [req, setReq] = useState({ symbol: null, tf: null, n: 0 });
  const [active, setActive] = useState({ symbol: init.symbol || lget("ts-mkt-last", {}).symbol || "EURUSD", tf: init.tf || "H1" });
  const [favs, setFavs] = useState(() => { const f = lget(FAV_KEY, []); return Array.isArray(f) ? f : []; });
  const [cls, setCls] = useState(() => lget("ts-mkt-cls", "all"));
  useEffect(() => { lset(FAV_KEY, favs); }, [favs]);
  useEffect(() => { lset("ts-mkt-cls", cls); }, [cls]);
  // điều hướng từ nơi khác (#/thi-truong/XAUUSD?tf=H4)
  useEffect(() => { const a = parseArg(arg); if (a.symbol) setReq((r) => ({ symbol: a.symbol, tf: a.tf, n: r.n + 1 })); }, [arg]);

  const syms = useSymbols();
  const risk = useRiskSymbol(active.symbol);
  const toggleFav = (s) => setFavs((f) => (f.includes(s) ? f.filter((x) => x !== s) : [...f, s]));

  return (
    <>
      <PageHead title="Thị trường" sub="Biểu đồ nhiều ô đồng bộ, chỉ báo, công cụ vẽ, replay và tín hiệu kỹ thuật. Chọn mã ở danh sách, đổi bố cục ở thanh công cụ." />
      <RiskBanner state={risk.data} symbolLabel={symbolLabel(active.symbol)} />
      <div className="mkt-ws">
        <aside className="panel mkt-list" aria-label="Danh sách mã">
          <SymbolList symbols={syms.data} loading={syms.isPending} error={syms.isError} active={active.symbol} onPick={(s) => setReq((r) => ({ symbol: s, tf: null, n: r.n + 1 }))}
            favs={favs} onFav={toggleFav} cls={cls} onCls={setCls} />
        </aside>
        <ChartWorkspace initialSymbol={init.symbol} initialTf={init.tf} request={req} onActive={(a) => setActive({ symbol: a.symbol, tf: a.tf })} favs={favs} onToggleFav={toggleFav} />
      </div>
    </>
  );
}
