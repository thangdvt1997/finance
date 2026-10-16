//+------------------------------------------------------------------+
//| MTAgentMarketFeed.mq5 - EA FEED GIA CHI DOC (MT5), tach rieng EA tai khoan.
//| Quet MarketWatch (Forex/Metals/Indexes) -> gom batch (conflate 1 tick moi/symbol,
//| nen M1 da dong) -> POST /ingest/v1 (Bearer + HMAC + nonce). KHONG co code giao dich.
//| Contract: docs/handoff/FEED_ALL_contract.md. Tai dung cac ham hash/JSON cua Core.mqh.
//+------------------------------------------------------------------+
#property copyright "trading-system"
#property version   "1.00"
#property description "READ-ONLY market feed: tick + M1 nhieu symbol -> mt-bridge"
#include <MTAgent/Core.mqh>

#define MF_VER "MF1.0"

input string BridgeUrl       = "https://bridge.example.com/ingest/v1"; // them URL goc vao Allow WebRequest
input string AccountId       = "";     // de trong = "mt5:<login>-feed" (RIENG voi EA tai khoan)
input string Token           = "";     // de trong neu dung PairCode
input string PairCode        = "";     // ma ghep cap cho account feed (khong phai mat khau)
input string HmacSecret      = "";     // de trong khi dung PairCode
input bool   IncludeForex    = true;
input bool   IncludeMetals   = true;
input bool   IncludeIndexes  = true;
input string ExcludeSymbols  = "EURUSD,XAUUSD,GBPUSD,USDJPY,US500,US30,USTEC"; // da do EA tai khoan lo
input string ExtraSymbols    = "";     // them ten symbol (cach nhau dau phay)
input string SymbolsFile     = "feed_symbols.txt"; // MQL5/Files, moi dong/dau phay 1 ma (input string <=255 ky tu nen doc tu file); khong co file -> tu quet theo Include*
input int    MaxSymbols      = 200;
input int    ScanMs          = 40;     // chu ky timer (quet SymbolInfoTick 162 ma ~0.07 ms/vong)
input int    FlushMs         = 250;    // chu ky gui batch
input int    MaxMsgPerSec    = 4;      // tran so request/giay
input int    MaxQuotesPerBatch = 400;  // <= 400 (gioi han bridge), <= 64 KB/batch
input int    WarmPerTimer    = 8;      // so ma nap lich su M1 moi nhip timer (khong block)
input int    BackfillM1      = 120;    // nen M1 da dong gui khi khoi dong (<=300)
input int    HeartbeatSec    = 5;      // batch rong de bao song
input int    TimeoutMs       = 1500;
input int    StartDelaySec   = 0;      // cho truoc khi dung WebRequest (lab: 90 s de script GUI kip them URL vao Allow WebRequest, tranh dung do voi hop thoai Options)
input bool   AllowInsecureHttp = false;

string   f_sym[];
ulong    f_seen_msc[];    // time_msc tick moi nhat da thay (dedupe)
ulong    f_sent_msc[];    // time_msc da duoc bridge xac nhan
double   f_bid[], f_ask[];
long     f_time[];        // tick.time_msc (epoch gio server, mili-giay)
ulong    f_snap_msc[];    // msc dua vao batch dang bay
datetime f_m1_sent[];     // cursor nen M1 da xac nhan
datetime f_m1_pend[];
int      f_n = 0, f_rr = 0;
uint     f_next_ms = 0, f_scan_ms = 0;
uint     f_last_post_ms = 0;
long     f_ticks = 0, f_posts = 0, f_quotes_sent = 0;
uint     f_stat_ms = 0;
int      f_warm = 0;      // so ma da nap lich su M1 (warm-up theo dot)
uint     f_bar_ms = 0;
uint     f_start_ms = 0;
uint     f_flush_gap = 250;

string FeedCredFile() { return "MTAgentFeed_" + IntegerToString(AGT_LoginNum()) + ".cred"; }

bool FeedInList(string csv, string s)
{
   string p[];
   int n = StringSplit(csv, ',', p);
   for(int i = 0; i < n; i++) if(AGT_Trim(p[i]) == s) return true;
   return false;
}

bool FeedLoadCred()
{
   int h = FileOpen(FeedCredFile(), FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return false;
   string t = AGT_Trim(FileReadString(h));
   string sec = FileIsEnding(h) ? "" : AGT_Trim(FileReadString(h));
   FileClose(h);
   if(StringLen(t) < 16) return false;
   g_token = t;
   if(StringLen(g_hmac_secret) == 0) g_hmac_secret = sec;
   return true;
}

void FeedSaveCred()
{
   int h = FileOpen(FeedCredFile(), FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) { Print("MTFeed: khong luu duoc credential, loi ", GetLastError()); return; }
   FileWrite(h, g_token); FileWrite(h, g_hmac_secret); FileClose(h);
}

// Ghep cap (khac Core: file cred rieng, ea=MF1.0)
bool FeedRegister()
{
   string body = "{\"v\":1,\"platform\":\"mt5\",\"login\":" + AGT_L(AGT_LoginNum()) + ",\"server\":" + AGT_S(AGT_Cut(AccountInfoString(ACCOUNT_SERVER), 64)) +
                 ",\"company\":" + AGT_S(AGT_Cut(AccountInfoString(ACCOUNT_COMPANY), 64)) + ",\"build\":" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)) +
                 ",\"ea\":" + AGT_S(MF_VER) + ",\"pair_code\":" + AGT_S(g_pair_code) + ",\"account_id\":" + AGT_S(g_account_id) + "}";
   char data[], res[]; string rh = "";
   int n = StringToCharArray(body, data, 0, StringLen(body), CP_UTF8);
   if(n > 0) ArrayResize(data, n);
   ResetLastError();
   // ghep cap di qua auth (hash, DB) co the > TimeoutMs gui batch; timeout som lam MAT credential (da cap 1 lan) -> dung timeout rieng 15 s
   int code = WebRequest("POST", g_url + "/register", "Content-Type: application/json\r\n", MathMax(g_timeout_ms, 15000), data, res, rh);
   if(code == -1) { g_status = "ghep cap: WebRequest loi " + IntegerToString(GetLastError()); g_prov_next = TimeLocal() + 30; return false; }
   string js = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
   string st = AGT_JsonStr(js, "status"), tok = AGT_JsonStr(js, "token");
   if(code == 200 && StringLen(tok) >= 16)
   {
      g_token = tok;
      string hs = AGT_JsonStr(js, "hmac_secret");
      if(StringLen(hs) > 0 && StringLen(g_hmac_secret) == 0) g_hmac_secret = hs;
      FeedSaveCred();
      g_prov = 0; g_status = "ghep cap ok (" + st + ")";
      Print("MTFeed: ghep cap thanh cong status=", st);
      return true;
   }
   g_status = "ghep cap: " + (StringLen(st) > 0 ? st : "HTTP " + IntegerToString(code));
   Print("MTFeed: ", g_status);
   g_prov_next = TimeLocal() + (st == "pending" ? 30 : 90);
   return false;
}

void FeedAdd(string s)
{
   if(f_n >= MaxSymbols) return;
   for(int i = 0; i < f_n; i++) if(f_sym[i] == s) return;
   if(!SymbolSelect(s, true)) return;
   ArrayResize(f_sym, f_n + 1);
   f_sym[f_n] = s;
   f_n++;
}

bool FeedLoadFile()
{
   int h = FileOpen(SymbolsFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return false;
   while(!FileIsEnding(h) && f_n < MaxSymbols)
   {
      string ln = FileReadString(h);
      string p[];
      int n = StringSplit(ln, ',', p);
      for(int k = 0; k < n; k++)
      {
         string e = AGT_Trim(p[k]);
         if(StringLen(e) > 0 && StringGetCharacter(e, 0) != '#') FeedAdd(e);
      }
   }
   FileClose(h);
   return f_n > 0;
}

void FeedDiscover()
{
   if(!FeedLoadFile()) FeedDiscoverScan();
   FeedInitArrays();
}

void FeedDiscoverScan()
{
   int tot = SymbolsTotal(false);
   for(int i = 0; i < tot && f_n < MaxSymbols; i++)
   {
      string nm = SymbolName(i, false);
      if(FeedInList(ExcludeSymbols, nm)) continue;
      string path = SymbolInfoString(nm, SYMBOL_PATH);
      bool ok = (IncludeForex && StringFind(path, "Forex\\") == 0) ||
                (IncludeMetals && StringFind(path, "Metals\\") == 0) ||
                (IncludeIndexes && StringFind(path, "Indexes\\") == 0);
      if(ok) FeedAdd(nm);
   }
   string p[];
   int n = StringSplit(ExtraSymbols, ',', p);
   for(int k = 0; k < n; k++) { string e = AGT_Trim(p[k]); if(StringLen(e) > 0 && !FeedInList(ExcludeSymbols, e)) FeedAdd(e); }
}

void FeedInitArrays()
{
   ArrayResize(f_seen_msc, f_n); ArrayResize(f_sent_msc, f_n); ArrayResize(f_snap_msc, f_n);
   ArrayResize(f_bid, f_n); ArrayResize(f_ask, f_n); ArrayResize(f_time, f_n);
   ArrayResize(f_m1_sent, f_n); ArrayResize(f_m1_pend, f_n);
   ArrayInitialize(f_seen_msc, 0); ArrayInitialize(f_sent_msc, 0); ArrayInitialize(f_snap_msc, 0);
   ArrayInitialize(f_bid, 0); ArrayInitialize(f_ask, 0); ArrayInitialize(f_time, 0);
   ArrayInitialize(f_m1_sent, 0); ArrayInitialize(f_m1_pend, 0);
}

int OnInit()
{
   g_url = BridgeUrl; g_token = Token; g_pair_code = PairCode; g_timeout_ms = TimeoutMs;
   g_hmac_secret = HmacSecret;
   g_account_id = (StringLen(AccountId) > 0) ? AccountId : "mt5:" + IntegerToString(AGT_LoginNum()) + "-feed";
   if(StringFind(BridgeUrl, "https://") != 0 && !(AllowInsecureHttp && StringFind(BridgeUrl, "http://") == 0))
   { Print("MTFeed: BridgeUrl phai https:// (http:// chi khi AllowInsecureHttp)"); return INIT_PARAMETERS_INCORRECT; }
   if(StringLen(g_token) < 16 && StringLen(g_pair_code) == 0) { Print("MTFeed: can Token hoac PairCode"); return INIT_PARAMETERS_INCORRECT; }
   g_prov = 0;
   if(StringLen(g_token) < 16) { if(!FeedLoadCred()) { g_prov = 1; g_prov_next = 0; } }
   FeedDiscover();
   if(f_n == 0) { Print("MTFeed: khong co symbol nao"); return INIT_FAILED; }
   MathSrand((int)(GetTickCount() + (uint)AGT_LoginNum()));
   g_interval = 1;
   // GetTickCount() trong Wine = uptime may chu (>24.8 ngay -> (int)now am): KHONG khoi tao moc bang 0, neu khong (int)(now - 0) < 0 va flush/stat khong bao gio chay
   uint t0 = GetTickCount();
   f_start_ms = (StartDelaySec > 0) ? t0 : 0;
   f_next_ms = t0; f_stat_ms = t0; f_last_post_ms = t0 - 1000 * (uint)HeartbeatSec; f_bar_ms = t0 - 1000;
   Print("MTFeed: init ok account=", g_account_id, " symbols=", f_n, " (READ-ONLY)");
   f_flush_gap = (uint)MathMax(FlushMs, 1000 / MathMax(1, MaxMsgPerSec));
   EventSetMillisecondTimer(MathMax(10, ScanMs));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); Comment(""); }

// Nap lich su M1 theo dot (CopyRates lanh ~0.35 s/ma, KHONG block 57 s trong OnInit)
void FeedWarm()
{
   if(f_warm >= f_n) return;
   MqlRates r[];
   int bfw = MathMax(2, MathMin(BackfillM1, 300) + 2);   // nap luon so nen se backfill: iTime/iOpen sau do doc cache, khong block
   int e = MathMin(f_n, f_warm + MathMax(1, WarmPerTimer));
   for(int i = f_warm; i < e; i++) CopyRates(f_sym[i], PERIOD_M1, 0, bfw, r);
   f_warm = e;
   if(f_warm >= f_n) Print("MTFeed: warm-up M1 xong ", f_n, " ma");
}

void FeedScan()
{
   for(int i = 0; i < f_n; i++)
   {
      MqlTick tk;
      if(!SymbolInfoTick(f_sym[i], tk)) continue;
      if(tk.time_msc == 0 || (ulong)tk.time_msc == f_seen_msc[i]) continue;   // dedupe (symbol,time_msc)
      if(tk.bid <= 0.0 || tk.ask <= 0.0 || tk.ask < tk.bid) continue;
      f_seen_msc[i] = (ulong)tk.time_msc;
      f_bid[i] = tk.bid; f_ask[i] = tk.ask; f_time[i] = (long)tk.time_msc;
      f_ticks++;
   }
}

// Nen M1 da dong (cursor), toi da cap nen/batch. Dung CopyRates 1 lan/ma (nhanh), khong lap iTime/iOpen tung nen.
string FeedBarsJson(int &cnt, int cap)
{
   string out = "";
   cnt = 0;
   int bf = (BackfillM1 > 300 ? 300 : (BackfillM1 < 1 ? 1 : BackfillM1));
   MqlRates r[];
   datetime nowsrv = TimeCurrent();
   for(int i = 0; i < f_n && i < f_warm; i++)
   {
      f_m1_pend[i] = 0;
      int want = (f_m1_sent[i] == 0) ? bf : (int)MathMin(bf, 2 + (nowsrv - f_m1_sent[i]) / 60);
      if(want < 1) want = 1;
      if(cnt + want > cap && f_m1_sent[i] == 0) want = MathMax(0, cap - cnt);   // backfill dan dan neu gan day tran
      if(want < 1) continue;
      int got = CopyRates(f_sym[i], PERIOD_M1, 1, want, r);   // r[] tang dan theo thoi gian; bat dau tu nen da dong gan nhat
      if(got <= 0) continue;
      if(r[got - 1].time <= f_m1_sent[i]) continue;
      int added = 0; datetime lastt = 0;
      for(int k = 0; k < got && cnt < cap; k++)
      {
         if(r[k].time <= f_m1_sent[i]) continue;
         if(r[k].open <= 0 || r[k].high <= 0 || r[k].low <= 0 || r[k].close <= 0) continue;
         out += (cnt > 0 ? "," : "") + "{\"symbol\":" + AGT_S(f_sym[i]) + ",\"tf\":\"M1\",\"time\":" + AGT_L((long)r[k].time) +
                ",\"o\":" + AGT_D(r[k].open) + ",\"h\":" + AGT_D(r[k].high) + ",\"l\":" + AGT_D(r[k].low) + ",\"c\":" + AGT_D(r[k].close) +
                ",\"v\":" + AGT_D((double)r[k].tick_volume) + "}";
         cnt++; added++; lastt = r[k].time;
      }
      if(added > 0) f_m1_pend[i] = lastt;
   }
   return out;
}

// Quote: moi symbol 1 tick moi nhat chua gui (conflate), vong tron de cong bang
string FeedQuotesJson(int &cnt)
{
   string out = "";
   cnt = 0;
   int cap = MathMin(400, MathMax(1, MaxQuotesPerBatch));
   ArrayInitialize(f_snap_msc, 0);
   for(int j = 0; j < f_n && cnt < cap; j++)
   {
      int i = (f_rr + j) % f_n;
      if(f_seen_msc[i] == 0 || f_seen_msc[i] == f_sent_msc[i]) continue;
      out += (cnt > 0 ? "," : "") + "{\"symbol\":" + AGT_S(f_sym[i]) + ",\"bid\":" + AGT_D(f_bid[i]) + ",\"ask\":" + AGT_D(f_ask[i]) + ",\"time\":" + StringFormat("%I64d.%03d", f_time[i] / 1000, (int)(f_time[i] % 1000)) + "}";
      f_snap_msc[i] = f_seen_msc[i];
      cnt++;
   }
   f_rr = (f_rr + 1) % f_n;
   return out;
}

void FeedFlush()
{
   uint now = GetTickCount();
   if((int)(now - f_next_ms) < 0) return;
   uint tf0 = GetTickCount();
   int nq = 0, nb = 0;
   string qj = FeedQuotesJson(nq);
   string bj = "";
   if((int)(now - f_bar_ms) >= 1000) { f_bar_ms = now; bj = FeedBarsJson(nb, 900); }   // nen M1 kiem tra 1 lan/giay
   else for(int i = 0; i < f_n; i++) f_m1_pend[i] = 0;
   if(nq == 0 && nb == 0 && (int)(now - f_last_post_ms) < HeartbeatSec * 1000) return;
   uint tf1 = GetTickCount();
   long gmt = (long)TimeGMT();
   g_cur_ts = AGT_L(gmt);
   g_cur_nonce = AGT_Nonce();
   string body = "{\"v\":1,\"account_id\":" + AGT_S(g_account_id) + ",\"platform\":\"mt5\",\"ts\":" + g_cur_ts +
                 ",\"server_time\":" + AGT_L((long)TimeTradeServer()) + ",\"nonce\":" + AGT_S(g_cur_nonce) + ",\"seq\":" + IntegerToString(g_seq) +
                 ",\"quotes\":[" + qj + "],\"bars\":[" + bj + "],\"agent\":" + AGT_AgentJson() + "}";
   int code = AGT_Post(body);
   f_last_post_ms = now;
   if(f_posts < 3) Print("MTFeed: POST dau code=", code, " build=", tf1 - tf0, "ms", " q=", nq, " b=", nb, " rtt=", g_last_rtt, "ms bytes=", StringLen(body));
   uint minGap = f_flush_gap;
   if(code == 200 || code == 409)
   {
      for(int s = 0; s < f_n; s++)
      {
         if(f_snap_msc[s] != 0) f_sent_msc[s] = f_snap_msc[s];
         if(f_m1_pend[s] != 0) f_m1_sent[s] = f_m1_pend[s];
      }
      g_fail = 0; g_last_ok = TimeLocal(); g_status = "ok";
      f_posts++; f_quotes_sent += nq;
      f_next_ms = now + minGap;
   }
   else if(code == 202) { g_status = "cho master duyet (pending)"; f_next_ms = now + 30000; }
   else
   {
      g_fail++;
      if(code == 401) g_status = "401 token/HMAC sai hoac dong ho lech";
      else if(code == 403) g_status = "403 tai khoan bi dinh chi";
      else if(code == 429) g_status = "429 gui qua nhanh";
      else if(code != -1) g_status = "HTTP " + IntegerToString(code);
      int back = 1;
      for(int i2 = 0; i2 < g_fail && back < 60; i2++) back *= 2;
      if(code == 429 && back < 4) back = 4;
      if(code == 403) back = 60;
      if(back > 60) back = 60;
      f_next_ms = now + (uint)back * 1000;   // trang thai (quote moi nhat/cursor nen) giu nguyen -> khong phinh hang doi
      if(g_fail <= 3 || g_fail % 10 == 0) Print("MTFeed: gui that bai code=", code, " ", g_status, " thu lai sau ", back, "s");
   }
}

void OnTimer()
{
   if(f_start_ms != 0 && (int)(GetTickCount() - f_start_ms) < StartDelaySec * 1000) return;   // im lang hoan toan: hop thoai Options (script GUI) treo neu EA dang nap lich su
   if(g_prov == 1)
   {
      if(TimeLocal() >= g_prov_next) FeedRegister();
      Comment("MTFeed ", MF_VER, " (READ-ONLY)\n", g_status);
      return;
   }
   FeedWarm();
   FeedScan();
   FeedFlush();
   uint now = GetTickCount();
   if((int)(now - f_stat_ms) >= 30000)
   {
      f_stat_ms = now;
      string sil = ""; int nsil = 0; datetime srv = TimeTradeServer();
      for(int q = 0; q < f_n; q++)
      {
         datetime lt = (datetime)SymbolInfoInteger(f_sym[q], SYMBOL_TIME);
         if(lt == 0 || srv - lt > 300) { nsil++; if(nsil <= 40) sil += f_sym[q] + " "; }
      }
      Print("MTFeed: silent>5p=", nsil, " [", sil, "]");
      Print("MTFeed: stat symbols=", f_n, " ticks=", f_ticks, " posts=", f_posts, " quotes_sent=", f_quotes_sent, " fail=", g_fail, " rtt=", g_last_rtt, "ms status=", g_status);
      Comment("MTFeed ", MF_VER, " (READ-ONLY)\nacc=", g_account_id, " sym=", f_n, " status=", g_status, "\nticks=", f_ticks, " posts=", f_posts, " rtt=", g_last_rtt, "ms");
   }
}
