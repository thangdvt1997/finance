//+------------------------------------------------------------------+
//| MTAgent/Core.mqh  - phan dung chung cho EA MQL4 va MQL5          |
//| READ-ONLY: chi DOC tai khoan/vi the/gia/nen va DAY RA bridge     |
//| qua HTTPS (WebRequest, outbound). Khong co ham giao dich nao,    |
//| khong nhan lenh tu bridge.                                       |
//| Giao thuc: xem services/mt-bridge/src/mtbridge/protocol.py       |
//| Nhanh LICH SU: gui deal/lenh DA DONG theo cursor (khoa `deals`),  |
//| chi DOC lich su (OrderSelect MODE_HISTORY / HistorySelect...).    |
//| TRANG THAI: xem mt-agent/LAB.md (bien dich + kiem chung lab).     |
//| Y tuong ket noi EA<->Python tham khao darwinex/dwxconnect        |
//| (BSD-3), khong sao chep ma.                                      |
//+------------------------------------------------------------------+
#ifndef MTAGENT_CORE_MQH
#define MTAGENT_CORE_MQH

#define AGT_VERSION          1
#define AGT_EA_VERSION       "1.1"
#define AGT_MAX_BARS_BATCH   900
#define AGT_MAX_SYMBOLS      32
#define AGT_MAX_TF           6
#define AGT_MAX_DEALS_BATCH  200   // deal toi da moi request
#define AGT_DEAL_SCAN_S      15    // quet lich su toi da moi 15s (tru khi con du lo)
#define AGT_COMMENT_MAX      64

string   g_url        = "";
string   g_token      = "";
string   g_account_id = "";
int      g_timeout_ms = 5000;
int      g_interval   = 3;
int      g_backfill   = 50;
int      g_history_days = 365;   // 0 = tat gui lich su
string   g_symbols[];
int      g_tf_code[];
string   g_tf_name[];
int      g_nsym = 0;
int      g_ntf  = 0;
datetime g_last_bar_sent[];   // chi so = s*g_ntf + t ; cap nhat CHI khi bridge da xac nhan (cursor = hang doi gui lai)
datetime g_pending_bar[];
int      g_seq        = 0;
int      g_fail       = 0;
datetime g_next_send  = 0;
datetime g_last_ok    = 0;
string   g_status     = "init";

// ---- cap phat/ghep cap (provisioning): xem mt-agent/README.md. KHONG bao gio in/ghi log token + HMAC secret.
string   g_hmac_secret = "";     // secret HMAC (input HmacSecret, hoac do master cap qua ghep cap)
string   g_cur_ts      = "";
string   g_cur_nonce   = "";
string   g_pair_code   = "";     // PairCode nguoi dung nhap (de trong neu da co Token)
string   g_pair_shown  = "";     // ma ghep cap hien thi cho client (server tra ve hoac ma da nhap)
int      g_prov        = 0;      // 0 = da co credential, gui du lieu; 1 = dang cho ghep cap (khong co Token)
datetime g_prov_next   = 0;
int      g_last_rtt    = 0;      // do tre WebRequest lan gui truoc (ms) -> bao len bridge de master xem suc khoe

// ---- trang thai gui lich su (deals)
bool     g_deal_cursor_ok      = false;   // cursor khoi tao o lan quet dau (can TimeCurrent() > 0)
datetime g_deal_cursor_time    = 0;       // close_time lon nhat da gui thanh cong
ulong    g_deal_sent_at_cursor[];         // ticket da gui co close_time == cursor (chong gui lai)
int      g_deal_pending_n      = 0;       // lo dang cho bridge xac nhan
string   g_deal_pending_json   = "";
datetime g_deal_pending_cursor = 0;
ulong    g_deal_pending_set[];
datetime g_deal_next_scan      = 0;
bool     g_deal_more           = false;   // vua gui du lo -> quet tiep ngay
int      g_deal_rej            = 0;       // so lan lien tiep bridge tra 422 khi dang cho lo deals
ulong    g_dc_ticket[];                   // ung vien (scratch)
datetime g_dc_ct[];
int      g_dc_pos[];
int      g_dc_n                = 0;


//---------------------------------------------------------------- tai khoan
long AGT_LoginNum()
{
#ifdef __MQL5__
   return (long)AccountInfoInteger(ACCOUNT_LOGIN);
#else
   return (long)AccountNumber();
#endif
}

//---------------------------------------------------------------- JSON helpers
string AGT_Esc(string s)
{
   string out = "";
   int n = StringLen(s);
   for(int i = 0; i < n; i++)
   {
      int c = (int)StringGetCharacter(s, i);
      if(c == 34 || c == 92)            // " va backslash
         out += "\\" + CharToString((uchar)c);
      else if(c < 32 || c > 126)        // chi ASCII de do dai ky tu == so byte UTF-8
         out += "?";
      else
         out += CharToString((uchar)c);
   }
   return out;
}

string AGT_S(string s) { return "\"" + AGT_Esc(s) + "\""; }

string AGT_D(double v)
{
   if(v != v || v > 1.0e15 || v < -1.0e15) return "0";
   return DoubleToString(v, 8);
}

string AGT_L(long v) { return IntegerToString(v); }

//---------------------------------------------------------------- cau hinh
int AGT_TfFromName(string n)
{
   if(n == "M1")  return PERIOD_M1;
   if(n == "M5")  return PERIOD_M5;
   if(n == "M15") return PERIOD_M15;
   if(n == "H1")  return PERIOD_H1;
   if(n == "H4")  return PERIOD_H4;
   if(n == "D1")  return PERIOD_D1;
   return -1;
}

string AGT_Trim(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

string AGT_Plat()
{
#ifdef __MQL5__
   return "mt5";
#else
   return "mt4";
#endif
}

string AGT_CredFile() { return "MTAgent_" + AGT_Plat() + "_" + IntegerToString(AGT_LoginNum()) + ".cred"; }

// Credential do ghep cap cap phat luu o thu muc MQL*/Files cua terminal nay (cung muc do nhay cam nhu input Token).
bool AGT_LoadCred()
{
   int h = FileOpen(AGT_CredFile(), FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return false;
   string t = AGT_Trim(FileReadString(h));
   string sec = "";
   if(!FileIsEnding(h)) sec = AGT_Trim(FileReadString(h));
   FileClose(h);
   if(StringLen(t) < 16) return false;
   g_token = t;
   if(StringLen(g_hmac_secret) == 0) g_hmac_secret = sec;
   return true;
}

void AGT_SaveCred(string t, string sec)
{
   int h = FileOpen(AGT_CredFile(), FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) { Print("MTAgent: khong luu duoc credential (loi ", GetLastError(), "): se phai ghep cap lai sau khi khoi dong lai EA"); return; }
   FileWrite(h, t);
   FileWrite(h, sec);
   FileClose(h);
}

bool AGT_Init(string url, string token, string account_id, string symbols_csv, string tf_csv,
              int interval_s, int backfill, int history_days, int timeout_ms, bool allow_http)
{
   g_url = url; g_token = token; g_account_id = account_id;
   if(StringLen(g_account_id) == 0) g_account_id = AGT_Plat() + ":" + IntegerToString(AGT_LoginNum());   // quy uoc <platform>:<login>
   g_prov = 0;
   g_interval = (interval_s < 1 ? 1 : interval_s);
   g_backfill = (backfill < 0 ? 0 : (backfill > 200 ? 200 : backfill));
   g_history_days = (history_days < 0 ? 0 : (history_days > 3650 ? 3650 : history_days));
   g_deal_cursor_ok = false;
   g_deal_cursor_time = 0;
   ArrayResize(g_deal_sent_at_cursor, 0);
   ArrayResize(g_deal_pending_set, 0);
   g_deal_pending_n = 0;
   g_deal_pending_json = "";
   g_deal_next_scan = 0;
   g_deal_more = false;
   g_deal_rej = 0;
   g_timeout_ms = timeout_ms;
   if(StringLen(g_token) < 16 && StringLen(g_pair_code) == 0)
   {
      Print("MTAgent: can Token (>=16 ky tu) HOAC PairCode do master cap");
      return false;
   }
   if(StringLen(g_token) < 16)   // che do ghep cap: dung lai credential da cap truoc do (neu co), khong thi xin cap bang PairCode
   {
      if(AGT_LoadCred()) Print("MTAgent: dung credential da ghep cap truoc do (", AGT_CredFile(), ")");
      else { g_prov = 1; g_prov_next = 0; g_pair_shown = g_pair_code; }
   }
   if(StringFind(url, "https://") != 0 && !(allow_http && StringFind(url, "http://") == 0))
   {
      Print("MTAgent: BridgeUrl phai la https:// (http:// chi khi AllowInsecureHttp=true, chi de thu nghiem)");
      return false;
   }
   string parts[];
   int n = StringSplit(symbols_csv, ',', parts);
   g_nsym = 0;
   ArrayResize(g_symbols, 0);
   for(int i = 0; i < n && g_nsym < AGT_MAX_SYMBOLS; i++)
   {
      string s = AGT_Trim(parts[i]);
      if(StringLen(s) == 0) continue;
      ArrayResize(g_symbols, g_nsym + 1);
      g_symbols[g_nsym] = s;
      g_nsym++;
      SymbolSelect(s, true);
   }
   string tfs[];
   n = StringSplit(tf_csv, ',', tfs);
   g_ntf = 0;
   ArrayResize(g_tf_code, 0);
   ArrayResize(g_tf_name, 0);
   for(int j = 0; j < n && g_ntf < AGT_MAX_TF; j++)
   {
      string tn = AGT_Trim(tfs[j]);
      int code = AGT_TfFromName(tn);
      if(code < 0) continue;
      ArrayResize(g_tf_code, g_ntf + 1);
      ArrayResize(g_tf_name, g_ntf + 1);
      g_tf_code[g_ntf] = code;
      g_tf_name[g_ntf] = tn;
      g_ntf++;
   }
   int total = g_nsym * g_ntf;
   ArrayResize(g_last_bar_sent, total > 0 ? total : 1);
   ArrayResize(g_pending_bar, total > 0 ? total : 1);
   ArrayInitialize(g_last_bar_sent, 0);
   ArrayInitialize(g_pending_bar, 0);
   MathSrand((int)(GetTickCount() + (uint)AGT_LoginNum()));
   g_next_send = 0;
   g_status = "started";
   Print("MTAgent: init ok account=", g_account_id, " url=", g_url, " symbols=", g_nsym, " tf=", g_ntf, " history_days=", g_history_days, " (READ-ONLY)");
   return true;
}

string AGT_AccountJson()
{
   long   login = AGT_LoginNum();
   string server, cur, mode;
   long   lev;
   double bal, eq, mg, fr;
#ifdef __MQL5__
   server = AccountInfoString(ACCOUNT_SERVER);
   cur    = AccountInfoString(ACCOUNT_CURRENCY);
   lev    = (long)AccountInfoInteger(ACCOUNT_LEVERAGE);
   bal    = AccountInfoDouble(ACCOUNT_BALANCE);
   eq     = AccountInfoDouble(ACCOUNT_EQUITY);
   mg     = AccountInfoDouble(ACCOUNT_MARGIN);
   fr     = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   mode   = ((long)AccountInfoInteger(ACCOUNT_MARGIN_MODE) == (long)ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) ? "hedging" : "netting";
#else
   server = AccountServer();
   cur    = AccountCurrency();
   lev    = (long)AccountLeverage();
   bal    = AccountBalance();
   eq     = AccountEquity();
   mg     = AccountMargin();
   fr     = AccountFreeMargin();
   mode   = "hedging";
#endif
   bool ta = ((long)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) != 0);
   string ml = (mg > 0.0) ? AGT_D(eq / mg * 100.0) : "null";
   return "{\"login\":" + AGT_L(login) + ",\"server\":" + AGT_S(server) + ",\"currency\":" + AGT_S(cur) +
          ",\"leverage\":" + AGT_L(lev) + ",\"balance\":" + AGT_D(bal) + ",\"equity\":" + AGT_D(eq) +
          ",\"margin\":" + AGT_D(mg) + ",\"free_margin\":" + AGT_D(fr) + ",\"margin_level\":" + ml +
          ",\"margin_mode\":" + AGT_S(mode) + ",\"trade_allowed\":" + (ta ? "true" : "false") + "}";
}

//---------------------------------------------------------------- vi the (dang mo)
string AGT_PositionsJson()
{
   string out = "[";
   int cnt = 0;
#ifdef __MQL5__
   int total = PositionsTotal();
   for(int i = 0; i < total && cnt < 500; i++)
   {
      ulong tk = PositionGetTicket(i);   // chon vi the theo chi so
      if(tk == 0) continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      int    typ = (int)PositionGetInteger(POSITION_TYPE);
      if(typ > 1) continue;
      string one = "{\"ticket\":" + AGT_L((long)tk) + ",\"symbol\":" + AGT_S(sym) + ",\"type\":" + IntegerToString(typ) +
         ",\"lots\":" + AGT_D(PositionGetDouble(POSITION_VOLUME)) + ",\"open_price\":" + AGT_D(PositionGetDouble(POSITION_PRICE_OPEN)) +
         ",\"price\":" + AGT_D(PositionGetDouble(POSITION_PRICE_CURRENT)) + ",\"sl\":" + AGT_D(PositionGetDouble(POSITION_SL)) +
         ",\"tp\":" + AGT_D(PositionGetDouble(POSITION_TP)) + ",\"profit\":" + AGT_D(PositionGetDouble(POSITION_PROFIT)) +
         ",\"swap\":" + AGT_D(PositionGetDouble(POSITION_SWAP)) + ",\"magic\":" + AGT_L((long)PositionGetInteger(POSITION_MAGIC)) +
         ",\"comment\":" + AGT_S(PositionGetString(POSITION_COMMENT)) + ",\"open_time\":" + AGT_L((long)PositionGetInteger(POSITION_TIME)) + "}";
      out += (cnt > 0 ? "," : "") + one;
      cnt++;
   }
#else
   int total = OrdersTotal();
   for(int i = 0; i < total && cnt < 500; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int typ = OrderType();
      if(typ > 1) continue;              // 0 buy, 1 sell; con lai la lenh cho
      string sym = OrderSymbol();
      double cur = MarketInfo(sym, (typ == 0 ? MODE_BID : MODE_ASK));
      string one = "{\"ticket\":" + AGT_L((long)OrderTicket()) + ",\"symbol\":" + AGT_S(sym) + ",\"type\":" + IntegerToString(typ) +
         ",\"lots\":" + AGT_D(OrderLots()) + ",\"open_price\":" + AGT_D(OrderOpenPrice()) +
         ",\"price\":" + AGT_D(cur) + ",\"sl\":" + AGT_D(OrderStopLoss()) +
         ",\"tp\":" + AGT_D(OrderTakeProfit()) + ",\"profit\":" + AGT_D(OrderProfit()) +
         ",\"swap\":" + AGT_D(OrderSwap()) + ",\"magic\":" + AGT_L((long)OrderMagicNumber()) +
         ",\"comment\":" + AGT_S(OrderComment()) + ",\"open_time\":" + AGT_L((long)OrderOpenTime()) + "}";
      out += (cnt > 0 ? "," : "") + one;
      cnt++;
   }
#endif
   return out + "]";
}

//---------------------------------------------------------------- lenh cho
string AGT_OrdersJson()
{
   string out = "[";
   int cnt = 0;
#ifdef __MQL5__
   int total = OrdersTotal();
   for(int i = 0; i < total && cnt < 500; i++)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      int typ = (int)OrderGetInteger(ORDER_TYPE);
      if(typ < 2 || typ > 7) continue;
      string one = "{\"ticket\":" + AGT_L((long)tk) + ",\"symbol\":" + AGT_S(OrderGetString(ORDER_SYMBOL)) + ",\"type\":" + IntegerToString(typ) +
         ",\"lots\":" + AGT_D(OrderGetDouble(ORDER_VOLUME_CURRENT)) + ",\"price\":" + AGT_D(OrderGetDouble(ORDER_PRICE_OPEN)) +
         ",\"sl\":" + AGT_D(OrderGetDouble(ORDER_SL)) + ",\"tp\":" + AGT_D(OrderGetDouble(ORDER_TP)) +
         ",\"magic\":" + AGT_L((long)OrderGetInteger(ORDER_MAGIC)) + ",\"comment\":" + AGT_S(OrderGetString(ORDER_COMMENT)) +
         ",\"setup_time\":" + AGT_L((long)OrderGetInteger(ORDER_TIME_SETUP)) + "}";
      out += (cnt > 0 ? "," : "") + one;
      cnt++;
   }
#else
   int total = OrdersTotal();
   for(int i = 0; i < total && cnt < 500; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int typ = OrderType();
      if(typ < 2 || typ > 5) continue;
      string one = "{\"ticket\":" + AGT_L((long)OrderTicket()) + ",\"symbol\":" + AGT_S(OrderSymbol()) + ",\"type\":" + IntegerToString(typ) +
         ",\"lots\":" + AGT_D(OrderLots()) + ",\"price\":" + AGT_D(OrderOpenPrice()) +
         ",\"sl\":" + AGT_D(OrderStopLoss()) + ",\"tp\":" + AGT_D(OrderTakeProfit()) +
         ",\"magic\":" + AGT_L((long)OrderMagicNumber()) + ",\"comment\":" + AGT_S(OrderComment()) +
         ",\"setup_time\":" + AGT_L((long)OrderOpenTime()) + "}";
      out += (cnt > 0 ? "," : "") + one;
      cnt++;
   }
#endif
   return out + "]";
}

//---------------------------------------------------------------- gia
string AGT_QuotesJson()
{
   string out = "[";
   int cnt = 0;
   for(int s = 0; s < g_nsym; s++)
   {
      string sym = g_symbols[s];
      double bid = 0.0, ask = 0.0;
      long   tm = 0;
#ifdef __MQL5__
      MqlTick tk;
      if(!SymbolInfoTick(sym, tk)) continue;
      bid = tk.bid; ask = tk.ask; tm = (long)tk.time;
#else
      bid = MarketInfo(sym, MODE_BID);
      ask = MarketInfo(sym, MODE_ASK);
      tm  = (long)MarketInfo(sym, MODE_TIME);
#endif
      if(bid <= 0.0 || ask <= 0.0 || tm <= 0) continue;
      out += (cnt > 0 ? "," : "") + "{\"symbol\":" + AGT_S(sym) + ",\"bid\":" + AGT_D(bid) + ",\"ask\":" + AGT_D(ask) + ",\"time\":" + AGT_L(tm) + "}";
      cnt++;
   }
   return out + "]";
}

//---------------------------------------------------------------- nen da dong (cursor)
string AGT_BarsJson()
{
   string out = "[";
   int cnt = 0;
   for(int s = 0; s < g_nsym; s++)
   {
      for(int t = 0; t < g_ntf; t++)
      {
         int idx = s * g_ntf + t;
         g_pending_bar[idx] = 0;
         string sym = g_symbols[s];
         ENUM_TIMEFRAMES tf = (ENUM_TIMEFRAMES)g_tf_code[t];
         datetime newest = iTime(sym, tf, 1);
         if(newest == 0 || newest <= g_last_bar_sent[idx]) continue;
         int maxk = 0;
         for(int k = 1; k <= g_backfill + 1; k++)
         {
            datetime tk = iTime(sym, tf, k);
            if(tk == 0 || tk <= g_last_bar_sent[idx]) break;
            maxk = k;
            if(g_last_bar_sent[idx] == 0 && k >= g_backfill) break;   // lan dau: chi lay N nen gan nhat
         }
         if(maxk == 0 || cnt + maxk > AGT_MAX_BARS_BATCH) continue;  // de lan sau
         for(int k2 = maxk; k2 >= 1; k2--)
         {
            out += (cnt > 0 ? "," : "") + "{\"symbol\":" + AGT_S(sym) + ",\"tf\":" + AGT_S(g_tf_name[t]) + ",\"time\":" + AGT_L((long)iTime(sym, tf, k2)) +
                   ",\"o\":" + AGT_D(iOpen(sym, tf, k2)) + ",\"h\":" + AGT_D(iHigh(sym, tf, k2)) + ",\"l\":" + AGT_D(iLow(sym, tf, k2)) +
                   ",\"c\":" + AGT_D(iClose(sym, tf, k2)) + ",\"v\":" + AGT_D((double)iVolume(sym, tf, k2)) + "}";
            cnt++;
         }
         g_pending_bar[idx] = newest;
      }
   }
   return out + "]";
}

void AGT_CommitBars()
{
   int total = g_nsym * g_ntf;
   for(int i = 0; i < total; i++)
      if(g_pending_bar[i] != 0) g_last_bar_sent[i] = g_pending_bar[i];
}


//---------------------------------------------------------------- lich su giao dich da dong (deals)
// 1 deal = 1 giao dich DONG (MT4: 1 lenh dong; MT5: 1 deal OUT/OUT_BY/INOUT) hoac 1 thao tac so du (type 2).
// Cursor = close_time lon nhat da gui + tap ticket da gui co close_time == cursor. Chi tien cursor khi bridge tra 200/409.
// Han che MT4: chi thay phan lich su dang nap o tab Account History cua terminal (chinh cua so thoi gian o do).
struct AGT_DealRec
{
   ulong    ticket;
   ulong    position_id;
   string   symbol;
   int      type;          // 0 buy / 1 sell (huong vi the da dong) / 2 balance op
   double   lots;
   double   open_price;
   double   close_price;
   double   sl;
   double   tp;
   datetime open_time;
   datetime close_time;
   double   profit;
   double   swap;
   double   commission;
   long     magic;
   string   comment;
   string   reason;
};

bool AGT_DealIsSent(ulong tk)
{
   int n = ArraySize(g_deal_sent_at_cursor);
   for(int i = 0; i < n; i++)
      if(g_deal_sent_at_cursor[i] == tk) return true;
   return false;
}

// them ung vien neu chua gui: close_time > cursor, hoac == cursor ma ticket chua o tap da gui
void AGT_DealAddCand(ulong tk, datetime ct, int pos)
{
   if(ct <= 0) return;
   if(ct < g_deal_cursor_time) return;
   if(ct == g_deal_cursor_time && AGT_DealIsSent(tk)) return;
   ArrayResize(g_dc_ticket, g_dc_n + 1, 1024);
   ArrayResize(g_dc_ct, g_dc_n + 1, 1024);
   ArrayResize(g_dc_pos, g_dc_n + 1, 1024);
   g_dc_ticket[g_dc_n] = tk;
   g_dc_ct[g_dc_n] = ct;
   g_dc_pos[g_dc_n] = pos;
   g_dc_n++;
}

// sap xep ung vien tang dan theo close_time (khoa = ct<<32 | chi so), tra ve toi da AGT_MAX_DEALS_BATCH chi so
int AGT_DealSelect(int &order[])
{
   int total = g_dc_n;
   ulong keys[];
   ArrayResize(keys, total);
   for(int i = 0; i < total; i++)
      keys[i] = (((ulong)g_dc_ct[i]) << 32) | (ulong)i;
   ArraySort(keys);
   int n = (total < AGT_MAX_DEALS_BATCH ? total : AGT_MAX_DEALS_BATCH);
   ArrayResize(order, n);
   for(int j = 0; j < n; j++)
      order[j] = (int)(keys[j] & 0xFFFFFFFF);
   return n;
}

string AGT_Cut(string s, int maxlen)
{
   if(StringLen(s) > maxlen) return StringSubstr(s, 0, maxlen);
   return s;
}

#ifdef __MQL5__
string AGT_ReasonMt5(long r)
{
   if(r == DEAL_REASON_SL) return "sl";
   if(r == DEAL_REASON_TP) return "tp";
   if(r == DEAL_REASON_SO) return "so";
   if(r == DEAL_REASON_EXPERT) return "expert";
   if(r == DEAL_REASON_CLIENT || r == DEAL_REASON_MOBILE || r == DEAL_REASON_WEB) return "client";
   return "";
}
#else
string AGT_ReasonFromComment(string c)
{
   string lc = c;
   StringToLower(lc);
   if(StringFind(lc, "[sl]") >= 0) return "sl";
   if(StringFind(lc, "[tp]") >= 0) return "tp";
   if(StringFind(lc, "so:") == 0) return "so";
   return "";
}
#endif

string AGT_DealJson(AGT_DealRec &d)
{
   return "{\"ticket\":" + AGT_L((long)d.ticket) + ",\"position_id\":" + AGT_L((long)d.position_id) + ",\"symbol\":" + AGT_S(d.symbol) +
          ",\"type\":" + IntegerToString(d.type) + ",\"lots\":" + AGT_D(d.lots) + ",\"open_price\":" + AGT_D(d.open_price) +
          ",\"close_price\":" + AGT_D(d.close_price) + ",\"sl\":" + AGT_D(d.sl) + ",\"tp\":" + AGT_D(d.tp) +
          ",\"open_time\":" + AGT_L((long)d.open_time) + ",\"close_time\":" + AGT_L((long)d.close_time) +
          ",\"profit\":" + AGT_D(d.profit) + ",\"swap\":" + AGT_D(d.swap) + ",\"commission\":" + AGT_D(d.commission) +
          ",\"magic\":" + AGT_L(d.magic) + ",\"comment\":" + AGT_S(AGT_Cut(d.comment, AGT_COMMENT_MAX)) +
          ",\"reason\":" + AGT_S(d.reason) + "}";
}

// Quet lich su, tra ve so deal trong recs[] (da sap xep, <= AGT_MAX_DEALS_BATCH)
int AGT_CollectDeals(AGT_DealRec &recs[])
{
   g_dc_n = 0;
#ifdef __MQL5__
   if(!HistorySelect(g_deal_cursor_time, TimeCurrent() + 86400)) return 0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      datetime ct = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
      if(ct < g_deal_cursor_time) continue;
      long dt = HistoryDealGetInteger(tk, DEAL_TYPE);
      if(dt == DEAL_TYPE_BUY || dt == DEAL_TYPE_SELL)
      {
         long en = HistoryDealGetInteger(tk, DEAL_ENTRY);
         if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY && en != DEAL_ENTRY_INOUT) continue;
      }
      AGT_DealAddCand(tk, ct, i);
   }
   if(g_dc_n == 0) return 0;
   int ord[];
   int n = AGT_DealSelect(ord);
   ArrayResize(recs, n);
   // doc het thuoc tinh deal (trong vung chon hien tai) TRUOC khi dung HistorySelectByPosition (doi vung chon)
   for(int k = 0; k < n; k++)
   {
      ulong tk2 = g_dc_ticket[ord[k]];
      long dt2 = HistoryDealGetInteger(tk2, DEAL_TYPE);
      recs[k].ticket = tk2;
      recs[k].position_id = (ulong)HistoryDealGetInteger(tk2, DEAL_POSITION_ID);
      recs[k].close_time = (datetime)HistoryDealGetInteger(tk2, DEAL_TIME);
      recs[k].open_time = recs[k].close_time;
      recs[k].magic = HistoryDealGetInteger(tk2, DEAL_MAGIC);
      recs[k].comment = HistoryDealGetString(tk2, DEAL_COMMENT);
      double pr = HistoryDealGetDouble(tk2, DEAL_PROFIT);
      double sw = HistoryDealGetDouble(tk2, DEAL_SWAP);
      double cm = HistoryDealGetDouble(tk2, DEAL_COMMISSION) + HistoryDealGetDouble(tk2, DEAL_FEE);
      recs[k].sl = HistoryDealGetDouble(tk2, DEAL_SL);
      recs[k].tp = HistoryDealGetDouble(tk2, DEAL_TP);
      recs[k].open_price = 0.0;
      if(dt2 == DEAL_TYPE_BUY || dt2 == DEAL_TYPE_SELL)
      {
         recs[k].type = (dt2 == DEAL_TYPE_BUY ? 1 : 0);   // deal BUY dong vi the SELL
         recs[k].symbol = HistoryDealGetString(tk2, DEAL_SYMBOL);
         recs[k].lots = HistoryDealGetDouble(tk2, DEAL_VOLUME);
         recs[k].close_price = HistoryDealGetDouble(tk2, DEAL_PRICE);
         recs[k].profit = pr;
         recs[k].swap = sw;
         recs[k].commission = cm;
         recs[k].reason = AGT_ReasonMt5(HistoryDealGetInteger(tk2, DEAL_REASON));
      }
      else
      {
         recs[k].type = 2;
         recs[k].symbol = "";
         recs[k].lots = 0.0;
         recs[k].close_price = 0.0;
         recs[k].sl = 0.0;
         recs[k].tp = 0.0;
         recs[k].profit = pr + cm + sw;
         recs[k].swap = 0.0;
         recs[k].commission = 0.0;
         recs[k].reason = "";
      }
   }
   // gop phan MO cua tung position (deal IN): gia TB theo volume, thoi gian dau tien, SL/TP dau tien, commission theo ty le
   bool done[];
   ArrayResize(done, n);
   ArrayInitialize(done, false);
   for(int a = 0; a < n; a++)
   {
      if(done[a] || recs[a].type == 2 || recs[a].position_id == 0) continue;
      ulong pid = recs[a].position_id;
      double volin = 0.0, commin = 0.0, pxw = 0.0, slin = 0.0, tpin = 0.0;
      datetime ot = 0;
      bool have = false;
      if(HistorySelectByPosition(pid))
      {
         int pt = HistoryDealsTotal();
         for(int q = 0; q < pt; q++)
         {
            ulong tq = HistoryDealGetTicket(q);
            if(tq == 0) continue;
            long dtq = HistoryDealGetInteger(tq, DEAL_TYPE);
            if(dtq != DEAL_TYPE_BUY && dtq != DEAL_TYPE_SELL) continue;
            if(HistoryDealGetInteger(tq, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
            double v = HistoryDealGetDouble(tq, DEAL_VOLUME);
            datetime tt = (datetime)HistoryDealGetInteger(tq, DEAL_TIME);
            if(!have || tt < ot)
            {
               ot = tt;
               slin = HistoryDealGetDouble(tq, DEAL_SL);
               tpin = HistoryDealGetDouble(tq, DEAL_TP);
            }
            have = true;
            volin += v;
            pxw += v * HistoryDealGetDouble(tq, DEAL_PRICE);
            commin += HistoryDealGetDouble(tq, DEAL_COMMISSION) + HistoryDealGetDouble(tq, DEAL_FEE);
         }
      }
      for(int b = a; b < n; b++)
      {
         if(done[b] || recs[b].type == 2 || recs[b].position_id != pid) continue;
         done[b] = true;
         if(!have || volin <= 0.0) continue;
         recs[b].open_price = pxw / volin;
         recs[b].open_time = ot;
         if(slin != 0.0) recs[b].sl = slin;
         if(tpin != 0.0) recs[b].tp = tpin;
         recs[b].commission += commin * recs[b].lots / volin;
      }
   }
   return n;
#else
   int total = OrdersHistoryTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      int typ = OrderType();
      datetime ct = OrderCloseTime();
      if(typ == 6 || typ == 7)                 // balance / credit
      {
         if(ct <= 0) ct = OrderOpenTime();
      }
      else if(typ > 1 || ct <= 0) continue;    // bo lenh cho da xoa / lenh chua dong
      AGT_DealAddCand((ulong)OrderTicket(), ct, i);
   }
   if(g_dc_n == 0) return 0;
   int ord[];
   int n = AGT_DealSelect(ord);
   ArrayResize(recs, n);
   for(int k = 0; k < n; k++)
   {
      if(!OrderSelect(g_dc_pos[ord[k]], SELECT_BY_POS, MODE_HISTORY)) { recs[k].ticket = 0; continue; }
      int ty = OrderType();
      recs[k].ticket = (ulong)OrderTicket();
      recs[k].position_id = (ulong)OrderTicket();
      recs[k].magic = (long)OrderMagicNumber();
      recs[k].comment = OrderComment();
      recs[k].commission = OrderCommission();
      recs[k].swap = OrderSwap();
      recs[k].profit = OrderProfit();
      recs[k].close_time = g_dc_ct[ord[k]];
      if(ty == 6 || ty == 7)
      {
         recs[k].type = 2;
         recs[k].symbol = "";
         recs[k].lots = 0.0;
         recs[k].open_price = 0.0;
         recs[k].close_price = 0.0;
         recs[k].sl = 0.0;
         recs[k].tp = 0.0;
         recs[k].open_time = recs[k].close_time;
         recs[k].swap = 0.0;
         recs[k].commission = 0.0;
         recs[k].reason = "";
      }
      else
      {
         recs[k].type = ty;
         recs[k].symbol = OrderSymbol();
         recs[k].lots = OrderLots();
         recs[k].open_price = OrderOpenPrice();
         recs[k].close_price = OrderClosePrice();
         recs[k].sl = OrderStopLoss();
         recs[k].tp = OrderTakeProfit();
         recs[k].open_time = OrderOpenTime();
         recs[k].reason = AGT_ReasonFromComment(recs[k].comment);
      }
   }
   return n;
#endif
}

// Tra ve mang JSON deals ("[...]") hoac "" neu khong co deal moi / chua toi lan quet.
// Lo dang cho xac nhan (gui that bai) duoc giu nguyen de gui lai dung lo do.
string AGT_DealsJson()
{
   if(g_history_days <= 0) return "";
   if(g_deal_pending_n > 0) return g_deal_pending_json;
   if(!g_deal_more && TimeLocal() < g_deal_next_scan) return "";
   g_deal_next_scan = TimeLocal() + AGT_DEAL_SCAN_S;
   if(!g_deal_cursor_ok)
   {
      datetime now = TimeCurrent();
      if(now <= 0) return "";
      g_deal_cursor_time = now - (datetime)g_history_days * 86400;
      g_deal_cursor_ok = true;
   }
   AGT_DealRec recs[];
   int n = AGT_CollectDeals(recs);
   if(n <= 0) { g_deal_more = false; return ""; }
   string out = "[";
   int cnt = 0;
   datetime newc = 0;
   for(int i = 0; i < n; i++)
   {
      if(recs[i].ticket == 0) continue;
      out += (cnt > 0 ? "," : "") + AGT_DealJson(recs[i]);
      cnt++;
      if(recs[i].close_time > newc) newc = recs[i].close_time;
   }
   if(cnt == 0) { g_deal_more = false; return ""; }
   out += "]";
   // tap ticket da gui tai cursor moi
   ArrayResize(g_deal_pending_set, 0);
   int m = 0;
   if(newc == g_deal_cursor_time)
   {
      m = ArraySize(g_deal_sent_at_cursor);
      ArrayResize(g_deal_pending_set, m);
      for(int s = 0; s < m; s++) g_deal_pending_set[s] = g_deal_sent_at_cursor[s];
   }
   for(int j = 0; j < n; j++)
   {
      if(recs[j].ticket == 0 || recs[j].close_time != newc) continue;
      ArrayResize(g_deal_pending_set, m + 1);
      g_deal_pending_set[m] = recs[j].ticket;
      m++;
   }
   g_deal_pending_cursor = newc;
   g_deal_pending_n = cnt;
   g_deal_pending_json = out;
   return out;
}

// Goi SAU KHI bridge tra 200/409: tien cursor + tap da gui; neu lo day thi quet tiep ngay
void AGT_CommitDeals()
{
   if(g_deal_pending_n <= 0) return;
   g_deal_cursor_time = g_deal_pending_cursor;
   int m = ArraySize(g_deal_pending_set);
   ArrayResize(g_deal_sent_at_cursor, m);
   for(int i = 0; i < m; i++) g_deal_sent_at_cursor[i] = g_deal_pending_set[i];
   g_deal_more = (g_deal_pending_n >= AGT_MAX_DEALS_BATCH);
   g_deal_pending_n = 0;
   g_deal_pending_json = "";
   g_deal_rej = 0;
}


//---------------------------------------------------------------- HMAC-SHA256 (thuan MQL4/MQL5, khong phu thuoc CryptEncode)
// Chu ky gui kem header X-MT-Sig = hex(HMAC_SHA256(secret, "<ts>.<nonce>." + body)) - khop mtbridge.protocol.sign().
// LUU Y: doan nay duoc sinh/kiem tra thuat toan bang mirror Python (khop hashlib/hmac) nhung CHUA bien dich bang MetaEditor
// trong lab: hay chay mt-agent/lab/scripts/compile.sh mt4|mt5 va thu 1 batch voi bridge (HMAC bat) truoc khi dung that.
uint AGT_SHA_K[64] = {0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};

uint AGT_Ror(uint x, int n) { return (x >> n) | (x << (32 - n)); }

void AGT_Sha256(const uchar &msg[], int len, uchar &out[])
{
   uint h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
   int padlen = ((len + 9 + 63) / 64) * 64;
   uchar buf[];
   ArrayResize(buf, padlen);
   ArrayInitialize(buf, 0);
   for(int i = 0; i < len; i++) buf[i] = msg[i];
   buf[len] = 0x80;
   ulong bits = (ulong)len * 8;
   for(int j = 0; j < 8; j++) buf[padlen - 1 - j] = (uchar)((bits >> (8 * j)) & 0xFF);
   uint w[64];
   ArrayInitialize(w, 0);
   for(int off = 0; off < padlen; off += 64)
   {
      for(int t = 0; t < 16; t++)
         w[t] = ((uint)buf[off + 4*t] << 24) | ((uint)buf[off + 4*t + 1] << 16) | ((uint)buf[off + 4*t + 2] << 8) | (uint)buf[off + 4*t + 3];
      for(int t2 = 16; t2 < 64; t2++)
      {
         uint s0 = AGT_Ror(w[t2-15], 7) ^ AGT_Ror(w[t2-15], 18) ^ (w[t2-15] >> 3);
         uint s1 = AGT_Ror(w[t2-2], 17) ^ AGT_Ror(w[t2-2], 19) ^ (w[t2-2] >> 10);
         w[t2] = w[t2-16] + s0 + w[t2-7] + s1;
      }
      uint a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
      for(int t3 = 0; t3 < 64; t3++)
      {
         uint S1 = AGT_Ror(e, 6) ^ AGT_Ror(e, 11) ^ AGT_Ror(e, 25);
         uint ch = (e & f) ^ ((~e) & g);
         uint t1 = hh + S1 + ch + AGT_SHA_K[t3] + w[t3];
         uint S0 = AGT_Ror(a, 2) ^ AGT_Ror(a, 13) ^ AGT_Ror(a, 22);
         uint mj = (a & b) ^ (a & c) ^ (b & c);
         uint t22 = S0 + mj;
         hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t22;
      }
      h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
   }
   ArrayResize(out, 32);
   for(int k = 0; k < 8; k++)
   {
      out[4*k]     = (uchar)((h[k] >> 24) & 0xFF);
      out[4*k + 1] = (uchar)((h[k] >> 16) & 0xFF);
      out[4*k + 2] = (uchar)((h[k] >> 8) & 0xFF);
      out[4*k + 3] = (uchar)(h[k] & 0xFF);
   }
}

// msg[0..mlen) ; tra ve hex thuong (64 ky tu)
string AGT_HmacHex(string secret, const uchar &msg[], int mlen)
{
   uchar key[], k64[];
   int kl = StringToCharArray(secret, key, 0, StringLen(secret), CP_UTF8);
   if(kl > 0) ArrayResize(key, kl); else kl = 0;
   ArrayResize(k64, 64);
   ArrayInitialize(k64, 0);
   if(kl > 64) { uchar kh[]; AGT_Sha256(key, kl, kh); for(int i = 0; i < 32; i++) k64[i] = kh[i]; }
   else for(int i2 = 0; i2 < kl; i2++) k64[i2] = key[i2];
   uchar inner[], outer[], ih[], oh[];
   ArrayResize(inner, 64 + mlen);
   ArrayResize(outer, 64 + 32);
   for(int i3 = 0; i3 < 64; i3++) { inner[i3] = (uchar)(k64[i3] ^ 0x36); outer[i3] = (uchar)(k64[i3] ^ 0x5c); }
   for(int i4 = 0; i4 < mlen; i4++) inner[64 + i4] = msg[i4];
   AGT_Sha256(inner, 64 + mlen, ih);
   for(int i5 = 0; i5 < 32; i5++) outer[64 + i5] = ih[i5];
   AGT_Sha256(outer, 96, oh);
   string hex = "";
   string d16 = "0123456789abcdef";
   for(int i6 = 0; i6 < 32; i6++)
      hex += StringSubstr(d16, (oh[i6] >> 4) & 15, 1) + StringSubstr(d16, oh[i6] & 15, 1);
   return hex;
}

//---------------------------------------------------------------- gui
string AGT_Nonce()
{
   g_seq++;
   return IntegerToString(AGT_LoginNum()) + "-" + IntegerToString((long)TimeGMT()) + "-" + IntegerToString((long)GetTickCount()) + "-" +
          IntegerToString(g_seq) + "-" + IntegerToString(MathRand());
}

string AGT_AgentJson()
{
   string comp;
#ifdef __MQL5__
   comp = AccountInfoString(ACCOUNT_COMPANY);
#else
   comp = AccountCompany();
#endif
   int build = (int)TerminalInfoInteger(TERMINAL_BUILD);
   return "{\"ea\":" + AGT_S(AGT_EA_VERSION) + ",\"build\":" + IntegerToString(build) + ",\"company\":" + AGT_S(AGT_Cut(comp, 64)) +
          ",\"rtt_ms\":" + IntegerToString(g_last_rtt) + ",\"fail\":" + IntegerToString(g_fail) + "}";
}

// Lay gia tri chuoi don gian "key":"value" tu JSON phan hoi (khong co thu vien JSON trong MQL; gia tri la ky tu an toan)
string AGT_JsonStr(string js, string key)
{
   string pat = "\"" + key + "\":\"";
   int p = StringFind(js, pat);
   if(p < 0) return "";
   int b = p + StringLen(pat);
   int e = StringFind(js, "\"", b);
   if(e < 0) return "";
   return StringSubstr(js, b, e - b);
}

// Tu khai bao / ghep cap: POST <BridgeUrl>/register. Khong gui Authorization. Tra ve true khi da nhan credential.
bool AGT_Register()
{
   string srv, comp;
#ifdef __MQL5__
   srv = AccountInfoString(ACCOUNT_SERVER);
   comp = AccountInfoString(ACCOUNT_COMPANY);
#else
   srv = AccountServer();
   comp = AccountCompany();
#endif
   string body = "{\"v\":1,\"platform\":" + AGT_S(AGT_Plat()) + ",\"login\":" + AGT_L(AGT_LoginNum()) + ",\"server\":" + AGT_S(AGT_Cut(srv, 64)) +
                 ",\"company\":" + AGT_S(AGT_Cut(comp, 64)) + ",\"build\":" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)) +
                 ",\"ea\":" + AGT_S(AGT_EA_VERSION) + ",\"pair_code\":" + AGT_S(g_pair_code) + ",\"account_id\":" + AGT_S(g_account_id) + "}";
   char data[], res[];
   string rh = "";
   int n = StringToCharArray(body, data, 0, StringLen(body), CP_UTF8);
   if(n > 0) ArrayResize(data, n);
   ResetLastError();
   int code = WebRequest("POST", g_url + "/register", "Content-Type: application/json\r\n", g_timeout_ms, data, res, rh);
   if(code == -1)
   {
      int err = GetLastError();
      g_status = "ghep cap: WebRequest loi " + IntegerToString(err) + (err == 4060 ? " (them URL vao Allow WebRequest)" : "");
      g_prov_next = TimeLocal() + 30;
      return false;
   }
   string js = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
   string st = AGT_JsonStr(js, "status");
   string pc = AGT_JsonStr(js, "pairing_code");
   if(StringLen(pc) > 0) g_pair_shown = pc;
   string tok = AGT_JsonStr(js, "token");
   if(code == 200 && StringLen(tok) >= 16)
   {
      g_token = tok;
      string hs = AGT_JsonStr(js, "hmac_secret");
      if(StringLen(hs) > 0 && StringLen(g_hmac_secret) == 0) g_hmac_secret = hs;
      AGT_SaveCred(g_token, g_hmac_secret);
      g_prov = 0;
      g_status = "ghep cap thanh cong (" + st + ")";
      Print("MTAgent: ghep cap thanh cong, status=", st, " (credential da luu, khong hien thi)");
      return true;
   }
   g_status = "ghep cap: " + (StringLen(st) > 0 ? st : "HTTP " + IntegerToString(code)) + (StringLen(AGT_JsonStr(js, "message")) > 0 ? " - " + AGT_JsonStr(js, "message") : "");
   Print("MTAgent: ", g_status, StringLen(g_pair_shown) > 0 ? "  ma_ghep_cap=" + g_pair_shown : "");
   g_prov_next = TimeLocal() + (st == "pending" ? 30 : 90);
   return false;
}

string AGT_BuildBatch()
{
   long gmt = (long)TimeGMT();
   long srv = (long)TimeCurrent();
   string nonce_now = AGT_Nonce();
   g_cur_ts = AGT_L(gmt);
   g_cur_nonce = nonce_now;
   string plat = "mt4";
#ifdef __MQL5__
   plat = "mt5";
#endif
   string dj = AGT_DealsJson();
   string tail = (StringLen(dj) > 0 ? ",\"deals\":" + dj : "") + ",\"agent\":" + AGT_AgentJson() + "}";
   return "{\"v\":1,\"account_id\":" + AGT_S(g_account_id) + ",\"platform\":" + AGT_S(plat) + ",\"ts\":" + AGT_L(gmt) +
          ",\"server_time\":" + AGT_L(srv) + ",\"nonce\":" + AGT_S(nonce_now) + ",\"seq\":" + IntegerToString(g_seq) +
          ",\"account\":" + AGT_AccountJson() + ",\"positions\":" + AGT_PositionsJson() + ",\"orders\":" + AGT_OrdersJson() +
          ",\"quotes\":" + AGT_QuotesJson() + ",\"bars\":" + AGT_BarsJson() + tail;
}

int AGT_Post(string body)
{
   char data[], res[];
   string rh = "";
   int n = StringToCharArray(body, data, 0, StringLen(body), CP_UTF8);
   if(n > 0) ArrayResize(data, n);
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + g_token + "\r\nX-MT-Account: " + g_account_id + "\r\n";
   if(StringLen(g_hmac_secret) > 0)   // bridge bat hmac_secret_env: ky "<ts>.<nonce>." + body
   {
      uchar pre[], full[];
      int pl = StringToCharArray(g_cur_ts + "." + g_cur_nonce + ".", pre, 0, StringLen(g_cur_ts + "." + g_cur_nonce + "."), CP_UTF8);
      if(pl > 0) ArrayResize(pre, pl); else pl = 0;
      int dl = ArraySize(data);
      ArrayResize(full, pl + dl);
      for(int q = 0; q < pl; q++) full[q] = pre[q];
      for(int q2 = 0; q2 < dl; q2++) full[pl + q2] = data[q2];
      headers += "X-MT-Sig: " + AGT_HmacHex(g_hmac_secret, full, pl + dl) + "\r\n";
   }
   ResetLastError();
   uint t0 = GetTickCount();
   int code = WebRequest("POST", g_url, headers, g_timeout_ms, data, res, rh);
   g_last_rtt = (int)(GetTickCount() - t0);
   if(code == -1)
   {
      int err = GetLastError();
      g_status = "WebRequest loi " + IntegerToString(err) + (err == 4060 ? " (them URL vao Tools>Options>Expert Advisors>Allow WebRequest)" : "");
   }
   return code;
}

void AGT_Show()
{
   Comment("MTAgent v" + AGT_EA_VERSION + " (READ-ONLY - khong giao dich)\nacc=", g_account_id, "  status=", g_status, "\nlast_ok=", TimeToString(g_last_ok, TIME_DATE | TIME_SECONDS),
           "  fail=", g_fail, "  rtt=", g_last_rtt, "ms", (StringLen(g_pair_shown) > 0 && g_prov == 1) ? "\nMa ghep cap: " + g_pair_shown : "");
}

// Goi moi giay tu OnTimer.
void AGT_Tick()
{
   static bool first = true;
   if(first) { first = false; Print("MTAgent: timer dau tien, bat dau gui"); }
   if(g_prov == 1)   // chua co credential: xin cap bang PairCode (khong gui du lieu)
   {
      if(TimeLocal() >= g_prov_next) AGT_Register();
      AGT_Show();
      return;
   }
   if(TimeLocal() < g_next_send) return;
   string body = AGT_BuildBatch();
   int code = AGT_Post(body);
   if(code == 202)   // bridge nhan dien dung nhung tai khoan CHUA duoc master duyet: khong coi la da giao (cursor khong tien)
   {
      g_fail = 0;
      g_status = "cho master duyet (pending)";
      g_next_send = TimeLocal() + 30;
      AGT_Show();
      return;
   }
   if(code == 200 || code == 409)   // 409 = bridge da nhan nonce nay roi (replay) -> coi nhu da giao
   {
      AGT_CommitBars();
      AGT_CommitDeals();
      g_fail = 0;
      g_last_ok = TimeLocal();
      g_status = "ok";
      g_next_send = TimeLocal() + g_interval;
   }
   else
   {
      g_fail++;
      if(code == 422 && g_deal_pending_n > 0)   // deals bi tu choi schema: bo lo sau 2 lan de khong chan snapshot/vi the
      {
         g_deal_rej++;
         if(g_deal_rej >= 2) { Print("MTAgent: bridge tu choi (422) lo deals ", g_deal_pending_n, " -> bo qua lo nay"); AGT_CommitDeals(); }
      }
      if(code == 401) g_status = "401: token/HMAC sai hoac da bi thu hoi - kiem tra Token/HmacSecret/dong ho";
      else if(code == 403) g_status = "403: tai khoan bi DINH CHI - lien he master";
      else if(code == 429) g_status = "429: gui qua nhanh - tang SendIntervalSec";
      else if(code != -1) g_status = "HTTP " + IntegerToString(code) + " (kiem tra token/schema/dong ho)";
      int backoff = 1;
      for(int i = 0; i < g_fail && backoff < 60; i++) backoff *= 2;
      if(backoff > 60) backoff = 60;
      if(code == 403 && backoff < 60) backoff = 60;
      g_next_send = TimeLocal() + backoff;     // gui lai: nen/snapshot duoc dung lai tu cursor, nonce+ts moi
      Print("MTAgent: gui that bai code=", code, " status=", g_status, " thu lai sau ", backoff, "s");
   }
   AGT_Show();
}

#endif
