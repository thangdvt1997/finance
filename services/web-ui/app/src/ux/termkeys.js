// Bảng tra nhẹ (nằm trong bundle chính): nhãn số liệu -> id thuật ngữ. Nội dung giải thích nằm ở ux/glossary.js và chỉ tải khi người dùng mở tooltip.
const MAP = {
  equity: "equity", "von thuc": "equity", balance: "balance", "so du": "balance", margin: "margin", "ky quy": "margin",
  "margin level": "margin-level", "muc ky quy": "margin-level", "free margin": "free-margin", "ky quy kha dung": "free-margin",
  drawdown: "drawdown", "max drawdown": "drawdown", "sut von": "drawdown", var: "var", "profit factor": "profit-factor", "he so loi nhuan": "profit-factor",
  "win rate": "win-rate", "ty le thang": "win-rate", expectancy: "expectancy", "ky vong": "expectancy", sharpe: "sharpe", sortino: "sharpe",
  spread: "spread", slippage: "slippage", "truot gia": "slippage", leverage: "leverage", "don bay": "leverage", swap: "swap",
  rsi: "rsi", atr: "atr", adx: "adx", macd: "macd", ema: "ema-sma", sma: "ema-sma", stochastic: "stoch", bollinger: "bollinger",
  correlation: "correlation", "tuong quan": "correlation", volatility: "volatility", "bien dong": "volatility", sentiment: "sentiment", "tam ly": "sentiment",
  pip: "pip", lot: "lot", "lai/lo dang mo": "floating", floating: "floating", "r:r": "rr", "risk reward": "rr",
};
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
/** "Drawdown từ đỉnh" -> "drawdown"; "Spread (ước tính)" -> "spread"; không khớp -> null. Thử cả nhãn, rồi bỏ dần từ cuối. */
export function termKeyOf(label) {
  let t = fold(label).replace(/\(.*?\)/g, " ").replace(/[^a-z0-9/: ]+/g, " ").replace(/\s+/g, " ").trim();
  if (!t) return null;
  const w = t.split(" ");
  if (w.length > 5) return null;
  for (let n = w.length; n >= 1; n--) { const k = w.slice(0, n).join(" "); if (MAP[k]) return MAP[k]; }
  return null;
}
