-- Kiem tra chat luong lich su D1 sau backfill (chay: psql -f). 1) tong quan, 2) khoang trong > 10 ngay, 3) nhay gia > 15% /ngay, 4) lech giua nguon tren ngay trung
WITH d AS (SELECT DISTINCT ON (symbol, ts_open) symbol, ts_open, o, h, l, c, source FROM bars WHERE tf='D1' ORDER BY symbol, ts_open, source)
SELECT symbol, count(*) n, min(ts_open)::date first, max(ts_open)::date last, round(((max(ts_open)::date-min(ts_open)::date)/365.25)::numeric,1) years,
       string_agg(DISTINCT source, '>' ) srcs FROM d GROUP BY symbol ORDER BY symbol;
WITH d AS (SELECT DISTINCT ON (symbol, ts_open) symbol, ts_open, c FROM bars WHERE tf='D1' ORDER BY symbol, ts_open, source),
g AS (SELECT symbol, ts_open, lag(ts_open) OVER w prev, c, lag(c) OVER w pc FROM d WINDOW w AS (PARTITION BY symbol ORDER BY ts_open))
SELECT 'GAP>10d' k, symbol, prev::date, ts_open::date, (ts_open::date-prev::date) days FROM g WHERE ts_open-prev > interval '10 days' ORDER BY symbol, ts_open;
WITH d AS (SELECT DISTINCT ON (symbol, ts_open) symbol, ts_open, c FROM bars WHERE tf='D1' ORDER BY symbol, ts_open, source),
g AS (SELECT symbol, ts_open, c, lag(c) OVER (PARTITION BY symbol ORDER BY ts_open) pc FROM d)
SELECT 'JUMP>15%' k, symbol, ts_open::date, round((c/pc-1)::numeric*100,1) pct FROM g WHERE abs(c/pc-1) > 0.15 ORDER BY symbol, ts_open;
SELECT 'OVERLAP' k, a.symbol, a.source sa, b.source sb, count(*) days, round((100*avg(abs(a.c/b.c-1)))::numeric,3) mean_abs_diff_pct, round((100*max(abs(a.c/b.c-1)))::numeric,3) max_pct
FROM bars a JOIN bars b ON a.symbol=b.symbol AND a.tf=b.tf AND a.ts_open=b.ts_open AND a.source<b.source
WHERE a.tf='D1' GROUP BY 2,3,4 ORDER BY 2;
