//+------------------------------------------------------------------+
//| MTAgentExport.mq5 - SCRIPT DOC-CHI: xuat thong tin tai khoan, danh |
//| sach symbol va lich su nen NATIVE (CopyRates) ra MQL5/Files/export.|
//| KHONG co ham giao dich. Khong ghi mat khau/token.                  |
//| Mode=info   -> info.txt + symbols.csv                              |
//| Mode=export -> <SYM>_<TF>.bin (MqlRates 60 byte, moi->cu theo khoi)|
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict
input string Mode       = "info";   // info | export
input string SymbolList = "";       // vd "XAUUSD,EURUSD" (export)
input string TfList     = "ALL";    // ALL hoac "M1,H1"
input int    MaxWaitSec = 90;       // cho dong bo moi (symbol,TF)

ENUM_TIMEFRAMES TFS[21] = {PERIOD_M1,PERIOD_M2,PERIOD_M3,PERIOD_M4,PERIOD_M5,PERIOD_M6,PERIOD_M10,PERIOD_M12,
  PERIOD_M15,PERIOD_M20,PERIOD_M30,PERIOD_H1,PERIOD_H2,PERIOD_H3,PERIOD_H4,PERIOD_H6,PERIOD_H8,PERIOD_H12,
  PERIOD_D1,PERIOD_W1,PERIOD_MN1};
string TFN[21] = {"M1","M2","M3","M4","M5","M6","M10","M12","M15","M20","M30","H1","H2","H3","H4","H6","H8","H12","D1","W1","MN1"};

string SafeName(string s){ StringReplace(s,"#","_H_"); StringReplace(s,"/","_"); StringReplace(s,".","_"); StringReplace(s,"\\","_"); return s; }

void Info()
{
  int h=FileOpen("export\info.txt",FILE_WRITE|FILE_TXT|FILE_ANSI);
  if(h==INVALID_HANDLE){ Print("cannot open info.txt err=",GetLastError()); return; }
  FileWriteString(h,"login="+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"\n");
  FileWriteString(h,"name="+AccountInfoString(ACCOUNT_NAME)+"\n");
  FileWriteString(h,"server="+AccountInfoString(ACCOUNT_SERVER)+"\n");
  FileWriteString(h,"company="+AccountInfoString(ACCOUNT_COMPANY)+"\n");
  FileWriteString(h,"currency="+AccountInfoString(ACCOUNT_CURRENCY)+"\n");
  FileWriteString(h,"leverage="+(string)AccountInfoInteger(ACCOUNT_LEVERAGE)+"\n");
  FileWriteString(h,"margin_mode="+(string)AccountInfoInteger(ACCOUNT_MARGIN_MODE)+" (0 netting,1 exchange,2 hedging)\n");
  FileWriteString(h,"trade_mode="+(string)AccountInfoInteger(ACCOUNT_TRADE_MODE)+" (0 demo)\n");
  FileWriteString(h,"trade_allowed="+(string)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)+"\n");
  FileWriteString(h,"balance="+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2)+"\n");
  FileWriteString(h,"equity="+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2)+"\n");
  FileWriteString(h,"positions="+(string)PositionsTotal()+" orders="+(string)OrdersTotal()+"\n");
  FileWriteString(h,"connected="+(string)TerminalInfoInteger(TERMINAL_CONNECTED)+"\n");
  FileWriteString(h,"ping_last_us="+(string)TerminalInfoInteger(TERMINAL_PING_LAST)+"\n");
  FileWriteString(h,"build="+(string)TerminalInfoInteger(TERMINAL_BUILD)+"\n");
  FileWriteString(h,"maxbars="+(string)TerminalInfoInteger(TERMINAL_MAXBARS)+"\n");
  FileWriteString(h,"time_current="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+"\n");
  FileWriteString(h,"time_gmt="+TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS)+"\n");
  FileWriteString(h,"server_offset_s="+(string)(long)(TimeTradeServer()-TimeGMT())+"\n");
  FileWriteString(h,"symbols_total="+(string)SymbolsTotal(false)+" marketwatch="+(string)SymbolsTotal(true)+"\n");
  FileClose(h);
  int n=SymbolsTotal(false);
  int s=FileOpen("export\symbols.csv",FILE_WRITE|FILE_TXT|FILE_ANSI);
  if(s==INVALID_HANDLE) return;
  FileWriteString(s,"name;path;desc;digits;selected;contract;base;profit;trade_mode\n");
  for(int i=0;i<n;i++){
    string nm=SymbolName(i,false);
    string d=SymbolInfoString(nm,SYMBOL_DESCRIPTION); StringReplace(d,";",",");
    FileWriteString(s,nm+";"+SymbolInfoString(nm,SYMBOL_PATH)+";"+d+";"+(string)SymbolInfoInteger(nm,SYMBOL_DIGITS)+";"+
      (string)SymbolInfoInteger(nm,SYMBOL_SELECT)+";"+DoubleToString(SymbolInfoDouble(nm,SYMBOL_TRADE_CONTRACT_SIZE),2)+";"+
      SymbolInfoString(nm,SYMBOL_CURRENCY_BASE)+";"+SymbolInfoString(nm,SYMBOL_CURRENCY_PROFIT)+";"+
      (string)SymbolInfoInteger(nm,SYMBOL_TRADE_MODE)+"\n");
  }
  FileClose(s);
  Print("info done symbols=",n);
}

bool WantTf(string tn){ if(TfList=="ALL") return true; return StringFind(","+TfList+",",","+tn+",")>=0; }

void ExportTF(string sym,ENUM_TIMEFRAMES tf,string tn,int st)
{
  uint t_start=GetTickCount();
  MqlRates tmp[];
  datetime first=0; int tries=0;
  while(tries<MaxWaitSec*2){
    CopyRates(sym,tf,0,2,tmp);
    first=(datetime)SeriesInfoInteger(sym,tf,SERIES_SERVER_FIRSTDATE);
    if(SeriesInfoInteger(sym,tf,SERIES_SYNCHRONIZED) && first>0) break;
    Sleep(500); tries++;
  }
  string fn="export\\"+SafeName(sym)+"_"+tn+".bin";
  FileDelete(fn);
  int fh=FileOpen(fn,FILE_WRITE|FILE_BIN);
  if(fh==INVALID_HANDLE){ Print("open fail ",fn," err=",GetLastError()); return; }
  long total=0; datetime minT=0,maxT=0;
  long win=(long)PeriodSeconds(tf)*50000; if(win<=0) win=86400L*3650;
  datetime t1=TimeCurrent()+86400;
  int empties=0;
  MqlRates arr[];
  while(t1>first && !IsStopped()){
    datetime t0=(datetime)((long)t1-win); if(t0<first) t0=first;
    int n=-1;
    for(int r=0;r<6;r++){ ResetLastError(); n=CopyRates(sym,tf,t0,t1,arr); if(n>0) break; Sleep(400); }
    if(n>0){
      FileWriteArray(fh,arr,0,n);
      total+=n; if(minT==0||arr[0].time<minT) minT=arr[0].time; if(arr[n-1].time>maxT) maxT=arr[n-1].time;
      empties=0;
    } else { empties++; if(empties>=40) break; }
    if(t0<=first) break;
    t1=(datetime)((long)t0-1);
  }
  FileClose(fh);
  int sh=FileOpen("export\status.csv",FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
  if(sh!=INVALID_HANDLE){ FileSeek(sh,0,SEEK_END);
    FileWriteString(sh,sym+";"+tn+";"+(string)total+";"+TimeToString(minT,TIME_DATE|TIME_MINUTES)+";"+TimeToString(maxT,TIME_DATE|TIME_MINUTES)+";"+
      TimeToString(first,TIME_DATE|TIME_MINUTES)+";"+(string)((GetTickCount()-t_start)/1000)+"s\n"); FileClose(sh); }
  Print("exported ",sym," ",tn," bars=",total," ",TimeToString(minT)," -> ",TimeToString(maxT));
}

void OnStart()
{
  if(Mode=="info"){ Info(); return; }
  string syms[]; int ns=StringSplit(SymbolList,',',syms);
  for(int i=0;i<ns;i++){
    string sym=syms[i]; StringTrimLeft(sym); StringTrimRight(sym);
    if(!SymbolSelect(sym,true)){ Print("SymbolSelect fail ",sym); continue; }
    for(int k=0;k<21 && !IsStopped();k++){ if(WantTf(TFN[k])) ExportTF(sym,TFS[k],TFN[k],i); }
  }
  Print("export ALL DONE");
}
