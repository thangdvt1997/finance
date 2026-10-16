#!/usr/bin/env node
// Ngăn tái phát: giao diện KHÔNG được in tên nguồn dữ liệu. Quét app/src (bỏ chú thích) và, nếu có, app/dist (chuỗi trong bundle).
// Dùng: node scripts/lint-sources.cjs [--dist]   -> exit 1 nếu thấy từ cấm ngoài danh sách cho phép.
const fs = require("fs"), path = require("path");
const BANNED = ["dukascopy", "frankfurter", "yahoo", "vnstock", "vndirect", "finfo", "okx", "kucoin", "binance", "bybit", "coinbase", "kraken", "ccxt", "alpaca", "tiingo", "oanda", "truefx",
  "gdelt", "reuters", "cafef", "vnexpress", "myfxbook", "actionforex", "fair economy", "faireconomy", "forexfactory", "investinglive", "oilprice", "mql5", "kbs", "stooq", "twelvedata", "finnhub", "alphavantage"];
const BANNED_UP = ["BLS", "CFTC", "FRED", "FMP"];
const NB = "(?<![\p{L}\p{N}_])", NA = "(?![\p{L}\p{N}_])";
const re = new RegExp(NB + "(" + BANNED.map((x) => x.replace(/ /g, "\s+")).join("|") + ")" + NA, "giu");
const reUp = new RegExp(NB + "(" + BANNED_UP.join("|") + ")" + NA, "gu");
// Tệp được phép chứa danh sách từ cấm (định nghĩa bộ lọc scrub) hoặc nhận diện mã (không hiển thị).
const ALLOW = [/lib.format.js$/, /lib.assetClass.js$/];
const root = path.join(__dirname, "..", "app");
const files = [];
(function walk(d) { for (const f of fs.readdirSync(d)) { const p = path.join(d, f); const st = fs.statSync(p); if (st.isDirectory()) { if (f !== "node_modules") walk(p); } else if (/\.(jsx?|html|css)$/.test(f)) files.push(p); } })(path.join(root, "src"));
if (process.argv.includes("--dist") && fs.existsSync(path.join(root, "dist"))) (function walk(d) { for (const f of fs.readdirSync(d)) { const p = path.join(d, f); if (fs.statSync(p).isDirectory()) walk(p); else if (/\.(js|html)$/.test(f)) files.push(p); } })(path.join(root, "dist"));
let bad = 0;
for (const f of files) {
  if (ALLOW.some((a) => a.test(f))) continue;
  let txt = fs.readFileSync(f, "utf8");
  txt = txt.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
  txt.split("\n").forEach((line, i) => {
    const code = line.replace(/(^|[^:])\/\/.*$/, "$1"); // bỏ chú thích //
    for (const r of [re, reUp]) { r.lastIndex = 0; let m; while ((m = r.exec(code))) { bad++; console.error(`${path.relative(root, f)}:${i + 1}: "${m[1]}"  ${code.trim().slice(0, 100)}`); } }
  });
}
if (bad) { console.error(`\n${bad} chỗ chứa tên nguồn dữ liệu. Không hiển thị tên nguồn trên giao diện; dùng scrub() hoặc bỏ chuỗi.`); process.exit(1); }
console.log("OK: không có tên nguồn dữ liệu trong chuỗi giao diện.");
