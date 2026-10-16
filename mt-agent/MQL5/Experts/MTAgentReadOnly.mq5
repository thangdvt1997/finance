//+------------------------------------------------------------------+
//| MTAgentReadOnly.mq5 - EA CHI DOC (MT5). Day du lieu RA bridge.   |
//| Khong co code giao dich. CHUA bien dich/chua kiem chung that.   |
//+------------------------------------------------------------------+
#property copyright "trading-system"
#property version   "1.10"
#property description "READ-ONLY monitor: day account/positions/quotes/bars toi bridge qua HTTPS"
#include <MTAgent/Core.mqh>

input string BridgeUrl         = "https://bridge.example.com/ingest/v1"; // HTTPS, them URL goc vao Allow WebRequest
input string AccountId         = "";      // de trong = tu dong "<mt4|mt5>:<so tai khoan>"; hoac phai khop account_id master cap
input string Token             = "";      // bearer token EA do master cap (>=16 ky tu). De trong neu dung PairCode
input string PairCode          = "";      // ma ghep cap do master cap: EA tu xin Token+HMAC (khong can dan token). KHONG phai mat khau giao dich
input string Symbols           = "EURUSD"; // ten SYMBOL cua broker, cach nhau dau phay
input string Timeframes        = "M1,M5,M15,H1,H4,D1";
input int    SendIntervalSec   = 3;
input int    BackfillBars      = 50;      // so nen da dong gui khi khoi dong
input int    HistoryDays       = 365;     // cua so backfill lich su giao dich da dong (ngay); 0 = tat gui lich su
input int    TimeoutMs         = 5000;
input bool   AllowInsecureHttp = false;   // chi de thu nghiem noi bo
input string HmacSecret        = "";      // secret ky HMAC do master cap (mac dinh BAT cho moi tai khoan moi); de trong khi dung PairCode (tu nhan)

int OnInit()
{
   g_pair_code = PairCode;
   if(StringLen(HmacSecret) > 0) g_hmac_secret = HmacSecret;
   if(!AGT_Init(BridgeUrl, Token, AccountId, Symbols, Timeframes, SendIntervalSec, BackfillBars, HistoryDays, TimeoutMs, AllowInsecureHttp))
      return INIT_PARAMETERS_INCORRECT;
   if(StringLen(HmacSecret) > 0) g_hmac_secret = HmacSecret;   // AGT_Init co the da nap secret tu ghep cap
   Print("MTAgent: EA v", AGT_EA_VERSION, " READ-ONLY. Khong nhap mat khau giao dich/investor o bat ky dau.");
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

void OnTimer()
{
   AGT_Tick();
}