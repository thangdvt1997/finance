// Track record chuyên gia (dữ liệu CÔNG KHAI, không theo tài khoản): gateway /v1/experts/leaderboard|consensus. Hợp đồng: services/track-record/CONTRACT.md.
// Bản gọn cho client. Dữ liệu mẫu: thêm ?mockexp=1 vào URL (nhớ trong sessionStorage; ?mockexp=0 tắt).
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "./api";

const FLAG = "tc-mockexp";
function mockOn() {
  try {
    const p = new URLSearchParams(location.search + (location.hash.includes("?") ? "&" + location.hash.split("?")[1] : ""));
    if (p.get("mockexp") === "1") sessionStorage.setItem(FLAG, "1");
    if (p.get("mockexp") === "0") sessionStorage.removeItem(FLAG);
    return sessionStorage.getItem(FLAG) === "1";
  } catch { return false; }
}
const get = async (path, params, signal) => (mockOn() ? (await import("./trackrecordFixture.js")).handle(path, params) : api(path, params, signal));
const q = (key, path, params, opts = {}) => ({ queryKey: ["tr", key, params], queryFn: ({ signal }) => get(path, params, signal), staleTime: 30_000, placeholderData: keepPreviousData, retry: (n, e) => n < 2 && !(e?.status >= 400 && e.status < 500), ...opts });
export const useLeaderboard = (p) => useQuery(q("lb", "/experts/leaderboard", p, { refetchInterval: 120_000 }));
export const useConsensus = (p) => useQuery(q("cs", "/experts/consensus", p, { refetchInterval: 120_000 }));

const nf = (n, dp) => Number(n).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
export const pc = (v, dp = 1) => (v == null || Number.isNaN(v) ? "—" : `${nf(v * 100, dp)}%`);
export const sgn = (v, dp = 0, suf = "") => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(Math.abs(v), dp)}${suf}`);
