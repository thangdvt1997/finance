// Phân loại tài sản cho danh sách mã. Ưu tiên trường `class` từ /v1/symbols; thiếu thì suy ra từ bảng ánh xạ dự phòng.
export const CLASSES = [
  { id: "forex", label: "Forex" },
  { id: "crypto", label: "Tiền ảo" },
  { id: "commodity", label: "Kim loại & hàng hoá" },
  { id: "index", label: "Chỉ số & ETF" },
  { id: "us", label: "Cổ phiếu Mỹ" },
  { id: "vn", label: "Cổ phiếu VN" },
  { id: "bond", label: "Trái phiếu" },
];
export const CLASS_LABEL = Object.fromEntries(CLASSES.map((c) => [c.id, c.label]));

// Giá trị `class` từ API (nhiều cách đặt tên) -> id nội bộ
const ALIAS = {
  forex: "forex", fx: "forex", currency: "forex", currencies: "forex", currency_pair: "forex",
  crypto: "crypto", cryptocurrency: "crypto", coin: "crypto", coins: "crypto", digital_asset: "crypto",
  commodity: "commodity", commodities: "commodity", metal: "commodity", metals: "commodity", energy: "commodity",
  agri: "commodity", agriculture: "commodity", agricultural: "commodity", softs: "commodity", precious_metal: "commodity",
  index: "index", indices: "index", etf: "index", index_etf: "index", etf_index: "index", equity_index: "index", fund: "index",
  us: "us", us_stock: "us", us_equity: "us", stock_us: "us", equity_us: "us", us_equities: "us", stock: "us", equity: "us",
  vn: "vn", vn_stock: "vn", vn_equity: "vn", stock_vn: "vn", equity_vn: "vn", vietnam: "vn",
  bond: "bond", bonds: "bond", rates: "bond", rate: "bond", fixed_income: "bond", treasury: "bond", macro: "bond", yield: "bond",
};

const CCY = new Set("USD EUR GBP JPY AUD NZD CAD CHF CNH CNY SGD HKD SEK NOK DKK PLN TRY ZAR MXN THB INR KRW VND RUB HUF CZK ILS".split(" "));
const CRYPTO_BASE = /^(BTC|ETH|BNB|SOL|XRP|ADA|DOGE|LTC|DOT|AVAX|LINK|MATIC|POL|TRX|SHIB|ATOM|XLM|BCH|ETC|UNI|NEAR|APT|ARB|OP|TON|PEPE|SUI|FIL|ICP|HBAR|AAVE|ALGO|XMR|EOS|VET|INJ|RNDR|IMX|MKR|GRT|FTM|SAND|MANA|AXS|CRV|LDO|RUNE|SEI|TIA|WLD|BONK|WIF|FLOKI|USDT|USDC)/;
const US_BOND_ETF = new Set("AGG BND IEF IEI SHY TLT TLH LQD HYG JNK TIP GOVT BIL SHV VGSH VGIT VGLT MUB EMB BNDX".split(" "));
const US_COMM_ETF = new Set("GLD IAU SLV USO BNO UNG CPER CANE CORN SOYB WEAT DBA DBC PDBC UGA UNL PPLT PALL GDX GDXJ DBB WOOD COW JO NIB BAL".split(" "));
const US_INDEX_ETF = new Set("SPY QQQ IWM DIA VTI VOO IVV VT VEA VWO EEM EFA INDA VNM FEZ ACWI RSP MDY IJH IJR SCHB SCHX XLE XLF XLK XLV XLY XLP XLI XLU XLB XLRE XLC SMH SOXX ARKK TQQQ SQQQ SPXL".split(" "));
const COMM_RE = /^(XAU|XAG|XPT|XPD|XCU|WTI|BRENT|UKOIL|USOIL|NGAS|NATGAS|COPPER|CORN|WHEAT|SOY|SUGAR|COFFEE|COCOA|COTTON|OIL|GOLD|SILVER|PLATINUM|PALLADIUM)/;
const INDEX_RE = /^(SPX|NDX|NAS100|US30|US500|US100|DJI|DJIA|DAX|GER40|GER30|UK100|FTSE|NIKKEI|JP225|N225|HK50|HSI|CAC40|FRA40|AUS200|VNINDEX|VN30|HNX|UPCOM|VIX|DXY|USDX)/;

/** Suy ra loại tài sản từ tên mã (dự phòng khi API chưa có `class`). */
export function guessClass(symbol) {
  const s = String(symbol || "").toUpperCase();
  if (!s) return "forex";
  if (s.startsWith("FRED:")) return "bond";
  if (s.startsWith("VN:")) return /^VN:(VNINDEX|VN30|HNX|UPCOM)/.test(s) ? "index" : "vn";
  if (/^(CRYPTO|BINANCE|BYBIT|OKX|COINBASE|KRAKEN):/.test(s)) return "crypto";
  if (s.startsWith("US:")) {
    const t = s.slice(3);
    if (US_BOND_ETF.has(t)) return "bond";
    if (US_COMM_ETF.has(t)) return "commodity";
    if (US_INDEX_ETF.has(t) || /^EW[A-Z]$/.test(t) || /^XL[A-Z]{1,2}$/.test(t)) return "index";
    return "us";
  }
  const bare = s.replace(/[-/_]/g, "");
  if (COMM_RE.test(bare)) return "commodity";
  if (INDEX_RE.test(bare) || s.startsWith("^")) return "index";
  if (/(USDT|USDC|BUSD)$/.test(bare) || (CRYPTO_BASE.test(bare) && /(USD|EUR|BTC|ETH)$/.test(bare))) return "crypto";
  if (/^[A-Z]{6}$/.test(bare) && CCY.has(bare.slice(0, 3)) && CCY.has(bare.slice(3))) return "forex";
  if (/^[A-Z]{6}$/.test(bare)) return "forex";
  return "us";
}

/** id loại tài sản của 1 symbol (info = phần tử /v1/symbols). */
export function classOf(info) {
  const raw = info?.class ?? info?.asset_class ?? info?.category;
  if (raw) {
    const k = ALIAS[String(raw).toLowerCase().replace(/[\s-]+/g, "_")];
    if (k) return k;
  }
  return guessClass(info?.symbol ?? info);
}

/** Nhãn gọn cho dòng phụ: tên đầy đủ nếu có, không thì loại tài sản. */
export const subLabel = (info) => info?.name || CLASS_LABEL[classOf(info)] || "";
