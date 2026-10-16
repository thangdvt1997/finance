import { useEffect, useState } from "react";
import { CandlestickChart } from "lucide-react";
import ChartWorkspace from "../components/chart/ChartWorkspace";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "chart", title: "Biểu đồ", icon: CandlestickChart, group: "Biểu đồ", linkable: true,
  desc: "Biểu đồ chuyên nghiệp: nhiều ô đồng bộ, chỉ báo, công cụ vẽ (kênh hồi quy, Pitchfork, Fib, volume profile...), replay, mẫu, cảnh báo giá.",
  defaultSize: { w: 14, h: 18 }, minSize: { w: 8, h: 10 },
  configSchema: [
    { key: "symbol", label: "Mã", type: "symbol", default: "EURUSD" },
    { key: "tf", label: "Khung thời gian", type: "select", default: "H1", options: ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"] },
  ],
};

export default function ChartWidget() {
  const { id, symbol, setSymbol, config } = useWidget();
  const [req, setReq] = useState({ symbol: null, tf: null, n: 0 });
  useEffect(() => { if (symbol) setReq((r) => ({ symbol, tf: null, n: r.n + 1 })); }, [symbol]);
  return (
    <ChartWorkspace embedded storageKey={`ts-ws-w:${id}`} initialSymbol={symbol} initialTf={config?.tf} request={req} title="Biểu đồ"
      onActive={(a) => { if (a.symbol && a.symbol !== symbol) setSymbol(a.symbol); }} />
  );
}
