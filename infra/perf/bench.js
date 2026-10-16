// k6 — baseline/after-test qua nginx (web-ui) với phiên QA. Chạy bởi infra/perf/run_bench.sh (container perf-k6 trên VPS; KHÔNG chạy trên laptop).
// Mỗi endpoint 1 kịch bản riêng chạy nối tiếp (VUS đồng thời cao) + 1 kịch bản "mixed" mô phỏng dashboard.
// CF-Connecting-IP ngẫu nhiên mỗi request (nginx tin dải docker nội bộ) để KHÔNG chạm limit_req theo IP -> đo năng lực dịch vụ, không đo rate limit.
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE || 'http://web-ui:8080';
const COOKIE = __ENV.COOKIE || '';
const VUS = parseInt(__ENV.VUS || '200');
const DUR = __ENV.DUR || '15s';
const ONLY = (__ENV.ONLY || '').split(',').filter(Boolean);
const MODE = __ENV.MODE || 'web';   // web = qua nginx (cookie phiên) | gw = thẳng api-gateway (X-API-Key, principal service) — cô lập khỏi churn của web-ui
const API_KEY = __ENV.API_KEY || '';

const EPS = {
  overview: '/api/v1/overview',
  bars_h1: '/api/v1/bars?symbol=EURUSD&tf=H1&limit=500',
  bars_m1: '/api/v1/bars?symbol=EURUSD&tf=M1&limit=500',
  bars_d1: '/api/v1/bars?symbol=EURUSD&tf=D1&limit=500',
  symbols: '/api/v1/symbols',
  quotes: '/api/v1/quotes/latest',
  news: '/api/v1/news?limit=50',
  calendar: '/api/v1/calendar?limit=100',
  an_overview: '/api/v1/analytics/overview',
  an_screener: '/api/v1/analytics/screener?tf=H1',
  an_corr: '/api/v1/analytics/correlation?tf=D1',
  intel_strength: '/api/v1/intel/strength',
  intel_heatmap: '/api/v1/intel/heatmap',
  intel_movers: '/api/v1/intel/movers',
  intel_pulse: '/api/v1/intel/pulse',
  intel_fx: '/api/v1/intel/fx',
  vn_overview: '/api/v1/vn/overview',
  vn_heatmap: '/api/v1/vn/heatmap',
  risk: '/api/v1/risk/accounts',
  static_index: '/',
  static_js: '@asset',
};
const sel = Object.keys(EPS).filter((n) => (!ONLY.length || ONLY.includes(n)) && (MODE === 'web' || !n.startsWith('static')));
const names = sel.concat(!ONLY.length || ONLY.includes('mixed') ? ['mixed'] : []);
const GAP = parseInt(__ENV.GAP || '12');   // nghỉ giữa các kịch bản để hàng đợi cũ xả hết (tránh nhiễu chéo)
const SLOT = parseInt(DUR) + GAP;

export const options = {
  insecureSkipTLSVerify: true,
  scenarios: Object.fromEntries(names.map((n, i) => [n, {
    executor: 'constant-vus', vus: VUS, duration: n === 'mixed' ? '30s' : DUR, startTime: `${i * SLOT}s`, exec: n === 'mixed' ? 'mixed' : 'single',
    env: { EP: n }, tags: { ep: n },
  }])),
  thresholds: Object.fromEntries(names.flatMap((n) => [[`http_req_duration{ep:${n}}`, ['p(95)<1e9']], [`http_req_failed{ep:${n}}`, ['rate<2']],
                                                         [`http_reqs{ep:${n}}`, ['count>=0']], [`data_received{ep:${n}}`, ['count>=0']]])),
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  const r = http.get(`${BASE}/`, { headers: { Cookie: COOKIE } });
  const m = /\/assets\/[^"']+\.js/.exec(r.body || '');
  return { asset: m ? m[0] : '/' };
}
function hdr() {
  const ip = `10.${__VU % 250}.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}`;
  if (MODE === 'gw') return { headers: { 'X-API-Key': API_KEY } };
  return { headers: { Cookie: COOKIE, 'CF-Connecting-IP': ip, 'Accept-Encoding': 'gzip' } };
}
function hit(url, tag) {
  const r = http.get(`${BASE}${MODE === 'gw' ? url.replace('/api/v1', '/v1') : url}`, { ...hdr(), tags: { ep: tag } });
  check(r, { 'status 200': (x) => x.status === 200 });
  return r;
}
export function single(data) {
  const n = __ENV.EP;
  hit(EPS[n] === '@asset' ? data.asset : EPS[n], n);
}
const MIX = ['overview', 'overview', 'overview', 'bars_h1', 'bars_h1', 'bars_m1', 'symbols', 'quotes', 'quotes', 'quotes', 'news', 'calendar', 'an_overview', 'intel_strength',
             'intel_heatmap', 'intel_pulse', 'vn_overview', 'risk', 'static_index'];
export function mixed() {
  hit(EPS[MIX[Math.floor(Math.random() * MIX.length)]], 'mixed');
}
export function handleSummary(data) {
  const out = {};
  for (const n of names) {
    const d = data.metrics[`http_req_duration{ep:${n}}`], c = data.metrics[`http_reqs{ep:${n}}`], f = data.metrics[`http_req_failed{ep:${n}}`], b = data.metrics[`data_received{ep:${n}}`];
    if (!d || !c) continue;
    const secs = n === 'mixed' ? 30 : parseInt(DUR);
    out[n] = { reqs: c.values.count, rps: +(c.values.count / secs).toFixed(1), p50: +d.values.med.toFixed(1), p90: +d.values['p(90)'].toFixed(1), p95: +d.values['p(95)'].toFixed(1),
               p99: +d.values['p(99)'].toFixed(1), max: +d.values.max.toFixed(0), fail_pct: f ? +(f.values.rate * 100).toFixed(2) : null, kb_per_req: b && c.values.count ? +(b.values.count / c.values.count / 1024).toFixed(1) : null };
  }
  return { ['/out/bench_' + (__ENV.LABEL || 'run') + '.json']: JSON.stringify(out, null, 1),
           stdout: Object.entries(out).map(([k, v]) => `${k.padEnd(16)} rps=${v.rps} p50=${v.p50} p95=${v.p95} p99=${v.p99} fail=${v.fail_pct}% kb=${v.kb_per_req}`).join('\n') + '\n' };
}
