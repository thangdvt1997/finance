//+------------------------------------------------------------------+
//| FeedProbe.mq5 - SCRIPT DOC-CHI do tai quet tick N symbol.          |
//| Khong co ham giao dich, khong WebRequest. Ghi MQL5/Files/probe.txt |
//+------------------------------------------------------------------+
#property script_show_inputs
#include <MTAgent/Core.mqh>
input string SymbolList = "";   // danh sach symbol cach nhau dau phay
input string Phases     = "7,30,60,100,172"; // so symbol moi pha
input int    PhaseSec   = 60;
input int    SleepMs    = 20;   // chu ky quet
input int    UseCopy    = 1;    // 1 = them CopyTicks
void OnStart()
{
   string lst = SymbolList;
   int fh = FileOpen("symlist.txt", FILE_READ|FILE_TXT|FILE_ANSI);
   if(fh != INVALID_HANDLE) { lst = FileReadString(fh); FileClose(fh); }
   for(int w = 0; w < 120 && !TerminalInfoInteger(TERMINAL_CONNECTED); w++) Sleep(1000);
   string syms[]; int n = StringSplit(lst, ',', syms);
   string ph[]; int np = StringSplit(Phases, ',', ph);
   int h = FileOpen("probe.txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
   FileWriteString(h, "n_syms_total="+(string)n+" connected="+(string)TerminalInfoInteger(TERMINAL_CONNECTED)+" ping_us="+(string)TerminalInfoInteger(TERMINAL_PING_LAST)+"\n"); FileFlush(h);
   int sel = 0;
   if(UseCopy == 3)
   {
      for(int i = 0; i < n; i++) SymbolSelect(syms[i], true);
      Sleep(3000);
      MqlRates r[];
      for(int rep = 0; rep < 8; rep++)
      {
         ulong a = GetMicrosecondCount(); int okc = 0;
         for(int i = 0; i < n; i++) if(CopyRates(syms[i], PERIOD_M1, 0, 2, r) == 2) okc++;
         FileWriteString(h, "M1_scan rep="+(string)rep+" ok="+(string)okc+" ms="+DoubleToString((GetMicrosecondCount()-a)/1000.0,1)+"\n"); FileFlush(h);
         Sleep(1000);
      }
      uchar buf[]; ArrayResize(buf, 10240); for(int q = 0; q < 10240; q++) buf[q] = (uchar)(65 + q % 26);
      ulong a2 = GetMicrosecondCount(); string sg = "";
      for(int rep = 0; rep < 20; rep++) sg = AGT_HmacHex("0123456789abcdef0123456789abcdef", buf, 10240);
      FileWriteString(h, "HMAC_10KB avg_ms="+DoubleToString((GetMicrosecondCount()-a2)/1000.0/20,2)+" len="+(string)StringLen(sg)+"\n");
      string js = ""; ulong a3 = GetMicrosecondCount(); MqlTick t2;
      for(int rep = 0; rep < 20; rep++) { js = "["; for(int i = 0; i < n; i++) { SymbolInfoTick(syms[i], t2); js += (i>0?",":"") + "{\"symbol\":" + AGT_S(syms[i]) + ",\"bid\":" + AGT_D(t2.bid) + ",\"ask\":" + AGT_D(t2.ask) + ",\"time_msc\":" + AGT_L(t2.time_msc) + "}"; } js += "]"; }
      FileWriteString(h, "JSON_162quotes avg_ms="+DoubleToString((GetMicrosecondCount()-a3)/1000.0/20,2)+" bytes="+(string)StringLen(js)+"\n");
      FileWriteString(h, "done\n"); FileClose(h); return;
   }
   for(int p = 0; p < np; p++)
   {
      int m = (int)MathMin((int)StringToInteger(ph[p]), n);
      uint t0 = GetTickCount();
      int ok = 0;
      for(int i = sel; i < m; i++) { if(SymbolSelect(syms[i], true)) ok++; }
      sel = MathMax(sel, m);
      uint tsel = GetTickCount() - t0;
      Sleep(3000);   // cho nap
      long last[]; ArrayResize(last, m); ArrayInitialize(last, 0);
      long lastc[]; ArrayResize(lastc, m); ArrayInitialize(lastc, 0);
      long seen = 0, copied = 0, cycles = 0, active = 0; double sum_ms = 0, max_ms = 0;
      bool act[]; ArrayResize(act, m); ArrayInitialize(act, false);
      MqlTick tk; MqlTick arr[];
      uint pe = GetTickCount() + PhaseSec * 1000;
      while(GetTickCount() < pe && !IsStopped())
      {
         ulong a = GetMicrosecondCount();
         for(int i = 0; i < m; i++)
         {
            if(UseCopy != 2 && SymbolInfoTick(syms[i], tk))
            {
               if(tk.time_msc != last[i]) { if(last[i] != 0) seen++; last[i] = tk.time_msc; act[i] = true; }
            }
            if(UseCopy >= 1)
            {
               if(lastc[i] == 0) lastc[i] = (long)TimeTradeServer() * 1000 - 1;
               int c = CopyTicks(syms[i], arr, COPY_TICKS_ALL, lastc[i] + 1, 5000);
               if(c > 0) { copied += c; lastc[i] = arr[c-1].time_msc; }
            }
         }
         double ms = (GetMicrosecondCount() - a) / 1000.0; sum_ms += ms; if(ms > max_ms) max_ms = ms; cycles++;
         Sleep(SleepMs);
      }
      for(int i = 0; i < m; i++) if(act[i]) active++;
      FileWriteString(h, "phase n="+(string)m+" selected_ok="+(string)ok+" sel_ms="+(string)tsel+" sec="+(string)PhaseSec+" cycles="+(string)cycles+
         " avg_cycle_ms="+DoubleToString(cycles>0?sum_ms/cycles:0,2)+" max_cycle_ms="+DoubleToString(max_ms,1)+
         " sampled_changes_per_s="+DoubleToString((double)seen/PhaseSec,1)+" copyticks_per_s="+DoubleToString((double)copied/PhaseSec,1)+" active_syms="+(string)active+
         " mem_used_mb="+(string)TerminalInfoInteger(TERMINAL_MEMORY_USED)+" cpu_core="+(string)TerminalInfoInteger(TERMINAL_CPU_CORES)+"\n"); FileFlush(h);
   }
   FileWriteString(h, "done\n"); FileClose(h);
}
