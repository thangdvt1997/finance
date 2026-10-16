// Harness QA (chỉ dùng cho ảnh mẫu): dựng ExamplesGrid + TestResultCard với dữ liệu GIẢ, chặn fetch. Không đưa vào bản chạy.
import { createRoot } from "react-dom/client";
import ExamplesGrid from "../../app/src/components/classroom/ExamplesGrid";
import TestResultCard from "../../app/src/components/classroom/TestResultCard";
import "../../app/src/index.css";
import "./extra.css";
const q = new URLSearchParams(location.search), lang = q.get("lang") || "vi", view = q.get("view") || "grid";
document.documentElement.dataset.theme = q.get("theme") || "dark";
const rf = window.fetch; window.fetch = async (u, o) => /ai-trading|csrf/.test(String(u)) ? new Response(JSON.stringify({ token: "t", csrf: "t", label: {}, summary: {} }), { status: 200, headers: { "content-type": "application/json" } }) : rf(u, o);
const ex = Array.from({ length: 8 }, (_, i) => ({ id: `e${i + 1}`, symbol: ["EURUSD", "GBPUSD", "XAUUSD"][i % 3], tf: i % 2 ? "H1" : "M15", ts: "2026-01-01", image_url: `/api/v1/ai-trading/class/rooms/r1/media/ex${i + 1}`, entry: 1.0912 + i / 1e4, sl: 1.095, note: "Bóng trên 48% thân (MINH HOẠ)", waves: [{ n: 1, x: .15, y: .7 }, { n: 2, x: .4, y: .35 }, { n: 3, x: .6, y: .55 }, { n: 4, x: .85, y: .25 }] }));
const labels = [{ example_id: "e1", verdict: "dung", reason: "Đúng hình, bóng dài" }, { example_id: "e2", verdict: "sai", reason: "Thiếu nén, xu hướng tiếp diễn" }, { example_id: "e3", verdict: "sai", reason: "Xu hướng mạnh, không nén" }, { example_id: "e4", verdict: "gan_dung" }];
const res = { scenario_id: "CL-DEMO-1", verdict: "no_edge", metrics: { expectancy_r: -0.12, ci95: [-0.31, 0.07], p_vs_random: 0.41, trades: 83, baseline_expectancy_r: -0.04, pbo: 0.62, dsr: 0.31, max_dd_r: 9.4, win_rate: 0.38, equity: Array.from({ length: 83 }, (_, i) => -0.12 * i + Math.sin(i / 4) * 3) }, honesty: ["Số MINH HOẠ, không phải dữ liệu thật."], disclaimer: "Không phải khuyến nghị; chỉ nghiên cứu/paper." };
const App = () => view === "grid" ? <ExamplesGrid lang={lang} rid="r1" examples={view === "grid" && q.get("empty") ? [] : ex} labels={labels} onSend={() => {}} onClose={() => {}} />
  : <TestResultCard lang={lang} result={q.get("pos") ? { ...res, verdict: "edge", metrics: { ...res.metrics, expectancy_r: 0.2, ci95: [0.05, 0.35], p_vs_random: 0.02, trades: 240 } } : res} role="master" rid="r1" onSend={() => {}} onEdit={() => {}} />;
createRoot(document.getElementById("r")).render(<div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}><App /></div>);
