//+------------------------------------------------------------------+
//| MTAgentSmoke.mq4 - SCRIPT thu nghiem (MT4). Chay 1 lan, gui     |
//| vai batch qua cung loi Core.mqh roi thoat. Dung de kiem chung    |
//| khi terminal MT4 CHUA dang nhap (EA khong khoi dong khi offline).|
//| Cau hinh doc tu MQL4/Files/MTAgentSmoke.set (dang key=value,     |
//| cung khoa voi EA: BridgeUrl, AccountId, Token, Symbols...).      |
//| READ-ONLY: khong co ham giao dich.                               |
//+------------------------------------------------------------------+
#property copyright "trading-system"
#property version   "1.00"
#property strict
#include <MTAgent/Core.mqh>

string SM_Get(string &keys[], string &vals[], int n, string key, string def)
{
   for(int i = 0; i < n; i++)
      if(keys[i] == key) return vals[i];
   return def;
}

void OnStart()
{
   int h = FileOpen("MTAgentSmoke.set", FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("MTAgentSmoke: khong mo duoc MQL4/Files/MTAgentSmoke.set err=", GetLastError());
      return;
   }
   string keys[], vals[];
   int n = 0;
   while(!FileIsEnding(h))
   {
      string ln = AGT_Trim(FileReadString(h));
      int p = StringFind(ln, "=");
      if(p <= 0) continue;
      ArrayResize(keys, n + 1);
      ArrayResize(vals, n + 1);
      keys[n] = StringSubstr(ln, 0, p);
      vals[n] = StringSubstr(ln, p + 1);
      n++;
   }
   FileClose(h);
   bool allow_http = (SM_Get(keys, vals, n, "AllowInsecureHttp", "false") == "true");
   if(!AGT_Init(SM_Get(keys, vals, n, "BridgeUrl", ""), SM_Get(keys, vals, n, "Token", ""), SM_Get(keys, vals, n, "AccountId", ""),
                SM_Get(keys, vals, n, "Symbols", "EURUSD"), SM_Get(keys, vals, n, "Timeframes", "M1,M5,M15,H1,H4,D1"),
                1, (int)StringToInteger(SM_Get(keys, vals, n, "BackfillBars", "50")),
                (int)StringToInteger(SM_Get(keys, vals, n, "HistoryDays", "365")), 5000, allow_http))
      return;
   g_hmac_secret = SM_Get(keys, vals, n, "HmacSecret", "");   // tai khoan lab bat HMAC (X-MT-Sig)
   Print("MTAgentSmoke: url=[", g_url, "] len=", StringLen(g_url), " acc=[", g_account_id, "] tokenlen=", StringLen(g_token), " nkeys=", n);
   int fo = FileOpen("MTAgentSmoke.out", FILE_WRITE | FILE_TXT | FILE_ANSI);   // ket qua cho script/CI doc
   if(fo != INVALID_HANDLE) FileWrite(fo, "url=[" + g_url + "] account=" + g_account_id + " tokenlen=" + IntegerToString(StringLen(g_token)) + " nkeys=" + IntegerToString(n));
   int rounds = (int)StringToInteger(SM_Get(keys, vals, n, "Rounds", "8"));
   for(int i = 0; i < rounds && !IsStopped(); i++)
   {
      AGT_Tick();
      Print("MTAgentSmoke: round ", i + 1, " status=", g_status, " fail=", g_fail);
      if(fo != INVALID_HANDLE) FileWrite(fo, "round " + IntegerToString(i + 1) + " status=" + g_status + " fail=" + IntegerToString(g_fail) + " last_err=" + IntegerToString(GetLastError()));
      Sleep(1200);
   }
   if(fo != INVALID_HANDLE) FileClose(fo);
}
