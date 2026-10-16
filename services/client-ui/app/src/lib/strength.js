// Sức mạnh tiền tệ rút gọn: mỗi cặp forex XXXYYY có biến động c% trong ngày -> XXX +c, YYY -c; lấy trung bình theo số cặp.
const CCY = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"];
export function strength(symbols) {
  const sum = {}, n = {};
  for (const s of symbols) {
    const m = /^([A-Z]{3})([A-Z]{3})$/.exec(s.symbol || "");
    if (!m || !CCY.includes(m[1]) || !CCY.includes(m[2]) || s.change_pct == null) continue;
    sum[m[1]] = (sum[m[1]] || 0) + s.change_pct; n[m[1]] = (n[m[1]] || 0) + 1;
    sum[m[2]] = (sum[m[2]] || 0) - s.change_pct; n[m[2]] = (n[m[2]] || 0) + 1;
  }
  return Object.keys(sum).map((ccy) => ({ ccy, v: sum[ccy] / n[ccy], n: n[ccy] })).sort((a, b) => b.v - a.v);
}
