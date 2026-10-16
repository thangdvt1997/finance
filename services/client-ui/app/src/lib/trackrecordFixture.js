// Dữ liệu mẫu cho giao diện "track record chuyên gia" (QA/dev khi backend chưa chạy). Bật: thêm ?mockexp=1 vào URL (nhớ trong sessionStorage; ?mockexp=0 tắt).
// Hình dạng JSON bám services/track-record/CONTRACT.md. Nhãn trung lập (không tên website/nguồn). Tất cả là DỮ LIỆU GIẢ, chỉ để xem bố cục.
const DISCLAIMER = "Chỉ tham khảo, quá khứ không đảm bảo tương lai. Đa số ý kiến công khai không vượt được ngẫu nhiên.";
const NOW = Date.now();
const DAY = 86400e3;
const iso = (ms) => new Date(ms).toISOString();

function rng(seed) {
  let s = 0;
  for (const c of String(seed)) s = (s * 31 + c.charCodeAt(0)) >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
function wilson(k, n, z = 1.96) {
  if (!n) return [null, null];
  const p = k / n, d = 1 + (z * z) / n, c = p + (z * z) / (2 * n), m = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [(c - m) / d, (c + m) / d];
}

const ENT = [
  // id, label, kind, lang, n(1W), hits, mean_ret, beats
  ["e01", "Chuyên gia phân tích #1", "analyst", "vi", 64, 41, 0.31, true],
  ["e02", "Ngân hàng trung ương #1", "central_bank", "en", 48, 27, 0.08, false],
  ["e03", "Vị thế đầu cơ — EUR", "positioning", "en", 120, 66, 0.12, false],
  ["e04", "Luồng tin #3", "media", "vi", 36, 16, -0.09, false],
  ["e05", "Vị thế đầu cơ — Vàng", "positioning", "en", 31, 18, 0.2, false],
  ["e06", "Chuyên gia phân tích #2", "analyst", "en", 22, 14, 0.25, false],
  ["e07", "Luồng tin #1", "media", "vi", 18, 9, 0.02, false],
  ["e08", "Nhà cung cấp tín hiệu #1", "signal_provider", "other", 14, 6, -0.12, false],
  ["e09", "Ngân hàng trung ương #2", "central_bank", "en", 9, 6, 0.3, false],
  ["e10", "Luồng tin #2", "media", "vi", 7, 3, -0.02, false],
  ["e11", "Chuyên gia phân tích #3", "analyst", "vi", 4, 3, 0.4, false],
  ["e12", "Vị thế đầu cơ — Dầu", "positioning", "en", 2, 1, 0, false],
  ["e13", "Luồng tin #4", "media", "other", 0, 0, null, false],
];
const SCOPES_N = { all: 1, forex: 0.6, metal: 0.25, index: 0.15, crypto: 0.1 };

function card(e, horizon, scope) {
  const [id, label, kind, lang, n0, h0, m0, beats] = e;
  const hf = horizon === "1D" ? 1.6 : horizon === "1M" ? 0.45 : 1;
  const sf = SCOPES_N[scope] ?? 0.1;
  const n = Math.round(n0 * hf * sf), hits = Math.min(n, Math.round(h0 * hf * sf + (horizon === "1M" ? -0.5 : 0)));
  const rated = n >= 30;
  const [lo, hi] = wilson(hits, n);
  const hr = n ? hits / n : null;
  const post = (hits + 5) / (n + 10);
  const sc = Math.round(100 * post * 10) / 10;
  const mean = m0 == null || !n ? null : m0 * (horizon === "1D" ? 0.4 : horizon === "1M" ? 2.2 : 1);
  const bb = rated && beats && horizon === "1W" && scope === "all";
  return {
    entity_id: id, label, kind, lang, n, n_total: Math.round(n0 * 1.4) + 3, hit_rate: hr, ci_low: lo, ci_high: hi,
    mean_ret_pct: mean, ret_ci_low: mean == null ? null : mean - 0.5 / Math.sqrt(Math.max(1, n / 10)), ret_ci_high: mean == null ? null : mean + 0.5 / Math.sqrt(Math.max(1, n / 10)),
    p_value: n ? (bb ? 0.004 : 0.12 + (n % 7) * 0.1) : null, q_value: n ? (bb ? 0.03 : Math.min(0.98, 0.2 + (n % 9) * 0.09)) : null,
    beats_baseline: bb, score: sc, prior_score: 50, weight: rated ? Math.min(2, Math.max(0.25, 1 + 6 * (post - 0.5))) : 1,
    status: rated ? "rated" : "insufficient", rank: null, n_needed: Math.max(0, 30 - n), last_view_at: iso(NOW - (n % 5) * DAY / 2), symbols_n: Math.min(9, 1 + (n % 7)),
  };
}
const base = () => ({ method_version: "2026.10-fixture", as_of: iso(NOW), disclaimer: DISCLAIMER });

function leaderboard(p) {
  const horizon = p.horizon || "1W", scope = p.scope || "all";
  let rows = ENT.map((e) => card(e, horizon, scope));
  if (p.kind) rows = rows.filter((r) => r.kind === p.kind);
  if (p.lang) rows = rows.filter((r) => r.lang === p.lang);
  if (p.include_insufficient === "false" || p.include_insufficient === false) rows = rows.filter((r) => r.status === "rated");
  rows.filter((r) => r.status === "rated").sort((a, b) => b.score - a.score).forEach((r, i) => { r.rank = i + 1; });
  rows.sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999) || b.n - a.n);
  const rated = rows.filter((r) => r.status === "rated").length;
  return {
    ...base(), horizon, scope, min_n: 30, baseline: { hit_rate: 0.5, note: "ngẫu nhiên (hướng ngẫu nhiên, hoán vị)" },
    summary: { entities: rows.length, rated, insufficient: rows.length - rated, beating_baseline: rows.filter((r) => r.beats_baseline).length, tests: rated, expected_false_positives: Math.round(rated * 0.1 * 10) / 10, fdr_q: 0.1 },
    rows,
  };
}

function trackRecord(id, p) {
  const e = ENT.find((x) => x[0] === id) || ENT[0];
  const horizon = p.horizon || "1W", scope = p.scope || "all";
  const r = rng(id);
  const horizons = { "1D": { card: card(e, "1D", scope) }, "1W": { card: card(e, "1W", scope) }, "1M": { card: card(e, "1M", scope) } };
  const c = card(e, horizon, scope);
  const N = Math.max(8, Math.min(40, e[4]));
  const rolling = [], pts = [];
  let hits = 0, cum = 0;
  const drift = (e[6] || 0) * 0.15;
  for (let i = 1; i <= N; i++) {
    hits += r() < (e[5] / Math.max(1, e[4])) ? 1 : 0;
    const [lo, hi] = wilson(hits, i);
    const t = iso(NOW - (N - i) * 3 * DAY);
    rolling.push({ t, n: i, hit_rate: hits / i, ci_low: lo, ci_high: hi });
    cum += drift + (r() - 0.5) * 0.9;
    const w = 0.35 * Math.sqrt(i) * 1.1;
    pts.push({ t, cum_ret_pct: cum, rand_p05: -w, rand_p50: (r() - 0.5) * 0.1, rand_p95: w });
  }
  const assets = ["forex", "metal", "index", "crypto"];
  const scopes = assets.map((s, i) => { const k = Math.round(e[4] * (0.5 - i * 0.12)); const h = Math.round(k * (e[5] / Math.max(1, e[4]))); const [lo, hi] = wilson(h, Math.max(k, 0)); return { scope: s, n: Math.max(k, 0), hit_rate: k > 0 ? h / k : null, ci_low: lo, ci_high: hi, mean_ret_pct: k > 0 ? (e[6] || 0) * (1 - i * 0.3) : null, status: k >= 30 ? "rated" : "insufficient" }; }).filter((x) => x.n > 0);
  const regimes = ["trend", "range", "high_vol", "low_vol"].map((g, i) => { const k = Math.max(0, Math.round(e[4] * (0.35 - i * 0.07))); const h = Math.round(k * (e[5] / Math.max(1, e[4])) * (g === "range" ? 0.85 : 1)); const [lo, hi] = wilson(h, k); return { regime: g, n: k, hit_rate: k ? h / k : null, ci_low: lo, ci_high: hi, mean_ret_pct: k ? (e[6] || 0) * (g === "range" ? 0.2 : 1) : null }; }).filter((x) => x.n > 0);
  const syms = ["EURUSD", "XAUUSD", "GBPUSD", "US:SPX", "USDJPY", "CRYPTO:BTCUSD"];
  const recent = Array.from({ length: Math.min(14, Math.max(2, e[4])) }, (_, i) => {
    const pending = i < 2;
    const o = () => { if (pending) return null; const ret = Math.round((r() - 0.45) * 160) / 100; return { ret_pct: ret, hit: ret > 0 }; };
    return { view_id: `${id}-v${i}`, symbol: syms[(i + e[4]) % syms.length], direction: r() < 0.5 ? "bullish" : "bearish", published_at: iso(NOW - (i * 1.3 + 0.2) * DAY), invalidation: i % 3 === 0 ? 1.0821 + i * 0.001 : null, state: pending ? "pending" : "resolved", outcome: { "1D": o(), "1W": i < 4 ? null : o(), "1M": i < 9 ? null : o() } };
  });
  return { ...base(), entity: { entity_id: id, label: e[1], kind: e[2], lang: e[3], first_view_at: iso(NOW - N * 3 * DAY), last_view_at: iso(NOW - DAY / 3), n_total: c.n_total }, card: c, horizons, by_scope: scopes, by_regime: regimes, rolling, equity: { points: pts, note: "Tổng lợi suất log %, không phí, vào lệnh ở giá mở cửa nến D1 kế tiếp sau thời điểm ghi nhận." }, recent, chain: { head_hash: "9f3ac1d0e5b7" + id, verified: true } };
}

function consensus(p) {
  const wd = Number(p.window_days) || 14;
  const defs = [["EURUSD", "forex", 7, 1.4, 0.4], ["XAUUSD", "metal", 5, 3.5, 0.3], ["GBPUSD", "forex", 4, 1.1, 2.1], ["USDJPY", "forex", 3, 0.7, 2.5], ["US:SPX", "index", 6, 3.0, 1.9], ["CRYPTO:BTCUSD", "crypto", 3, 1.6, 1.4], ["USOIL", "commodity", 2, 0.9, 0.2], ["AUDUSD", "forex", 1, 0, 1]];
  const rows = defs.map(([symbol, ac, n, bw, sw]) => {
    const bn = Math.round(n * (bw / (bw + sw || 1))), sn = n - bn;
    const net = (bw - sw) / ((bw + sw) || 1);
    const level = n >= 3 && Math.abs(net) >= 0.6 ? "consensus" : Math.abs(net) >= 0.3 ? "weak" : "none";
    const top = ENT.slice(0, Math.min(n, 5)).map((e, i) => ({ entity_id: e[0], label: e[1], direction: i < bn ? "bullish" : "bearish", weight: Math.round((1 + (e[5] / Math.max(1, e[4]) - 0.5) * 3) * 100) / 100, status: e[4] >= 30 ? "rated" : "insufficient", published_at: iso(NOW - (i + 1) * DAY / 2) }));
    return { symbol, asset_class: ac, n_experts: n, bullish: { n: bn, weight: bw }, bearish: { n: sn, weight: sw }, net_weighted: net, net_unweighted: (bn - sn) / n, agreement: Math.max(bn, sn) / n, level, latest_at: iso(NOW - DAY / 4), top };
  }).filter((r) => r.n_experts >= (Number(p.min_experts) || 1));
  return { ...base(), window_days: wd, scope: p.scope || "all", rows: p.scope && p.scope !== "all" ? rows.filter((r) => r.asset_class === p.scope) : rows };
}

function feed(p) {
  const syms = ["EURUSD", "XAUUSD", "GBPUSD", "US:SPX", "USDJPY", "CRYPTO:BTCUSD", "USOIL"];
  const cls = { EURUSD: "forex", XAUUSD: "metal", GBPUSD: "forex", "US:SPX": "index", USDJPY: "forex", "CRYPTO:BTCUSD": "crypto", USOIL: "commodity" };
  let items = Array.from({ length: 120 }, (_, i) => { const e = ENT[i % (ENT.length - 1)]; const s = syms[(i * 3) % syms.length]; return { view_id: `f${i}`, entity_id: e[0], label: e[1], kind: e[2], symbol: s, asset_class: cls[s], direction: (i * 7) % 3 === 0 ? "bearish" : "bullish", published_at: iso(NOW - i * 2.7 * 3600e3), invalidation: i % 4 === 0 ? 1.08 : null, horizon_hint: i % 5 === 0 ? "1W" : null, status: e[4] >= 30 ? "rated" : "insufficient", weight: e[4] >= 30 ? 1.2 : 1 }; });
  if (p.symbol) items = items.filter((x) => x.symbol === p.symbol || x.symbol.endsWith(`:${p.symbol}`));
  if (p.direction) items = items.filter((x) => x.direction === p.direction);
  if (p.entity_id) items = items.filter((x) => x.entity_id === p.entity_id);
  const lim = Math.min(200, Number(p.limit) || 50);
  return { ...base(), items: items.slice(0, lim), next_before: items.length > lim ? items[lim - 1].published_at : null };
}

const methodology = () => ({
  ...base(),
  summary: "Mỗi quan điểm có hướng (tăng/giảm) được chấm bằng lợi suất giả định: vào ở giá mở cửa nến ngày đầu tiên SAU thời điểm ghi nhận, thoát sau 1, 5 hoặc 21 nến ngày. Không có bước nhìn trước tương lai.",
  sections: [
    { title: "Đủ mẫu", text: "Cần tối thiểu 30 quan điểm độc lập đã chấm mới được xếp hạng. Dưới ngưỡng đó chỉ hiển thị số liệu thô, không có thứ hạng." },
    { title: "So với ngẫu nhiên", text: "Hit-rate được so với 50% bằng khoảng tin cậy Wilson; lợi suất so với phân phối hướng ngẫu nhiên (hoán vị). Huy hiệu chỉ hiện khi q-value (BH-FDR) dưới 0,10 và cả hai khoảng tin cậy cùng nằm phía có lợi." },
    { title: "Điểm uy tín", text: "Điểm 0–100 là trung bình hậu nghiệm Beta, co về 50 khi ít bằng chứng." },
    { title: "Trọng số", text: "Dùng cho bản đồ đồng thuận: 1 khi chưa đủ mẫu; khi đủ mẫu tăng/giảm theo điểm, trong khoảng 0,25–2,0." },
  ],
});

export async function handle(path, params = {}) {
  await new Promise((r) => setTimeout(r, 120));
  const p = path.replace(/^\/experts/, "");
  if (p === "/leaderboard") return leaderboard(params);
  if (p === "/consensus") return consensus(params);
  if (p === "/feed") return feed(params);
  if (p === "/methodology") return methodology();
  const m = p.match(/^\/([^/]+)\/track-record$/);
  if (m) return trackRecord(m[1], params);
  throw new Error(`mock: ${path}`);
}
