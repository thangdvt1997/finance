//+------------------------------------------------------------------+
//| MTAgentDealFixture.mq5 - SCRIPT kiem chung (MT5). Gui 1 lo deals |
//| CO DINH (comment "FIXTURE-JRN", magic 990001..990003) qua cung   |
//| ham AGT_* cua Core.mqh de kiem chung dinh dang JSON/bridge khi   |
//| terminal lab khong co lich su that. Gui 2 lan (thu idempotent).  |
//| READ-ONLY: khong co ham giao dich; chi POST toi bridge.          |
//| Ghi them MQL5/Files/MTAgentDealFixture.json (body da gui).       |
//+------------------------------------------------------------------+
#property copyright "trading-system"
#property version   "1.00"
#property script_show_inputs
#include <MTAgent/Core.mqh>

input string BridgeUrl         = "http://bridge.lab/ingest/v1";
input string AccountId         = "";
input string Token             = "";
input string HmacSecret        = "";
input bool   AllowInsecureHttp = true;

void FX_Set(AGT_DealRec &d, ulong tk, ulong pid, string sym, int typ, double lots, double op, double cp, double sl, double tp,
            long ot, long ct, double pr, double sw, double cm, long magic, string cmt, string rs)
{
   d.ticket = tk; d.position_id = pid; d.symbol = sym; d.type = typ; d.lots = lots; d.open_price = op; d.close_price = cp;
   d.sl = sl; d.tp = tp; d.open_time = (datetime)ot; d.close_time = (datetime)ct; d.profit = pr; d.swap = sw; d.commission = cm;
   d.magic = magic; d.comment = cmt; d.reason = rs;
}

void OnStart()
{
   if(!AGT_Init(BridgeUrl, Token, AccountId, "EURUSD", "M1", 1, 0, 0, 5000, AllowInsecureHttp))   // history_days=0: khong quet lich su that
      return;
   g_hmac_secret = HmacSecret;
   long base = (long)TimeCurrent();
   if(base <= 0) base = (long)TimeGMT();
   AGT_DealRec d[5];
   FX_Set(d[0], 990001001, 990001001, "EURUSD", 0, 0.10, 1.08000, 1.08250, 1.07800, 1.08300, base - 7200, base - 3600, 25.00, -0.30, -0.70, 990001, "FIXTURE-JRN buy tp", "tp");
   FX_Set(d[1], 990001002, 990001002, "EURUSD", 1, 0.20, 1.08500, 1.08700, 1.08800, 1.08000, base - 5400, base - 1800, -40.00, -0.50, -1.40, 990002, "FIXTURE-JRN sell sl", "sl");
   FX_Set(d[2], 990001003, 990001003, "XAUUSD", 0, 0.05, 2400.50, 2399.00, 0.0, 0.0, base - 3000, base - 900, -7.50, 0.0, -0.35, 990003, "FIXTURE-JRN expert close", "expert");
   FX_Set(d[3], 990001004, 0, "", 2, 0.0, 0.0, 0.0, 0.0, 0.0, base - 8000, base - 8000, 1000.00, 0.0, 0.0, 990003, "FIXTURE-JRN balance deposit", "");
   FX_Set(d[4], 990001005, 990001005, "EURUSD", 1, 0.01, 0.0, 1.08100, 0.0, 0.0, base - 600, base - 300, 0.12, 0.0, 0.0, 990001, "FIXTURE-JRN \"quoted\" client", "client");
   string arr = "[";
   for(int i = 0; i < 5; i++) arr += (i > 0 ? "," : "") + AGT_DealJson(d[i]);
   arr += "]";
   int fo = FileOpen("MTAgentDealFixture.json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   for(int r = 0; r < 2; r++)
   {
      string body = AGT_BuildBatch();
      int L = StringLen(body);
      body = StringSubstr(body, 0, L - 1) + ",\"deals\":" + arr + "}";
      int code = AGT_Post(body);
      for(int tries = 0; code == -1 && tries < 20 && !IsStopped(); tries++)   // URL WebRequest co the chua duoc them (lab them bang GUI sau khi len)
      {
         Sleep(10000);
         body = AGT_BuildBatch();
         body = StringSubstr(body, 0, StringLen(body) - 1) + ",\"deals\":" + arr + "}";
         code = AGT_Post(body);
      }
      Print("MTAgentDealFixture: send ", r + 1, " http=", code, " status=", g_status, " bytes=", StringLen(body));
      if(fo != INVALID_HANDLE) { FileWrite(fo, "send " + IntegerToString(r + 1) + " http=" + IntegerToString(code)); if(r == 0) FileWrite(fo, body); }
      Sleep(1500);
   }
   if(fo != INVALID_HANDLE) FileClose(fo);
}
