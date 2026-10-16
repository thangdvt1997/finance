import { useId } from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { AlertTriangle, Clock, Moon } from "lucide-react";
import { useClock } from "../lib/clock";
import { ageText, freshness, marketClosed } from "../lib/freshness";
import { dateTime as fmtDateTime } from "../lib/format";
import { EmptyState, ErrorState, TableSkeleton, ChartSkeleton } from "./ux/States";
import { InfoTip } from "./ux/Term";
import { termKeyOf } from "../ux/termkeys";
import { tzOffsetLabel, isVnTz } from "../ux/fmtconfig";

export const cn = (...a) => twMerge(clsx(a));

export function Panel({ title, icon: Icon, right, children, className, bodyClass, pad = true, id, fill, scroll }) {
  const hid = useId();
  return (
    <section className={cn("panel flex flex-col", fill && "fill", className)} aria-labelledby={title ? hid : undefined} id={id}>
      {(title || right) && (
        <div className="panel-h">
          {Icon && <Icon size={14} className="text-muted shrink-0" aria-hidden="true" />}
          <h2 id={hid} className="truncate">{title}</h2>
          <div className="ml-auto flex items-center gap-2 min-w-0">{right}</div>
        </div>
      )}
      <div className={cn(pad && "panel-b", "flex-1 min-h-0", scroll && "scroll-y", bodyClass)}>{children}</div>
    </section>
  );
}

export function Skeleton({ rows = 4, h = 14, className }) {
  return (
    <div className={cn("grid gap-2", className)} role="status" aria-label="Đang tải">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel" style={{ height: h, width: `${96 - ((i * 13) % 30)}%` }} />
      ))}
    </div>
  );
}

/** Trạng thái chuẩn: loading (skeleton: dòng | bảng | biểu đồ) | lỗi (chẩn đoán + thử lại) | rỗng (có hướng dẫn) | dữ liệu. */
export function Async({ q, empty = "Chưa có dữ liệu.", hint, rows = 4, isEmpty, variant, cols, height, actions, what, children }) {
  if (q.isPending) return variant === "table" ? <TableSkeleton rows={rows} cols={cols} /> : variant === "chart" ? <ChartSkeleton height={height} /> : <Skeleton rows={rows} />;
  if (q.isError && [502, 503, 504].includes(q.error?.status)) return <EmptyState compact title="Dịch vụ đang khởi tạo" hint="Dữ liệu sẽ hiện khi dịch vụ sẵn sàng; giao diện tự thử lại." actions={[{ label: q.isFetching ? "Đang thử lại…" : "Thử lại", onClick: () => q.refetch() }]} />;
  if (q.isError && q.error?.status === 404) return <EmptyState compact title="Chưa có dữ liệu" hint="Mục này chưa có dữ liệu cho lựa chọn hiện tại." />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} what={what} />;
  const data = q.data;
  const emptyNow = isEmpty ? isEmpty(data) : Array.isArray(data) ? data.length === 0 : data?.items ? data.items.length === 0 : !data;
  if (emptyNow) return <EmptyState compact title={empty} hint={hint} actions={actions} />;
  return children(data);
}

export function Chip({ tone, children, title, className }) {
  return <span className={cn("chip", tone, className)} title={title}>{children}</span>;
}

export function Seg({ value, onChange, options, label, className }) {
  return (
    <div className={cn("seg", className)} role="group" aria-label={label}>
      {options.map((o) => {
        const v = typeof o === "string" ? o : o.value;
        const l = typeof o === "string" ? o : o.label;
        return (
          <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

export function Sparkline({ values, width = 84, height = 26, up }) {
  if (!values || values.length < 2) return <svg width={width} height={height} aria-hidden="true" />;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * (width - 2) + 1).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`);
  const col = up ?? values[values.length - 1] >= values[0] ? "var(--up)" : "var(--down)";
  const area = `${pts.join(" ")} ${width - 1},${height} 1,${height}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="block">
      <polygon points={area} fill={col} opacity=".12" />
      <polyline points={pts.join(" ")} fill="none" stroke={col} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function ImpactDots({ impact }) {
  const n = impact === "high" ? 3 : impact === "med" ? 2 : 1;
  const col = impact === "high" ? "var(--down)" : impact === "med" ? "var(--accent)" : "var(--faint)";
  const label = impact === "high" ? "Tác động cao" : impact === "med" ? "Tác động vừa" : "Tác động thấp";
  return (
    <span className="inline-flex gap-[3px]" role="img" aria-label={label} title={label}>
      {[1, 2, 3].map((i) => (
        <span key={i} className="block w-[6px] h-[10px] rounded-[1.5px]" style={{ background: i <= n ? col : "var(--line2)" }} />
      ))}
    </span>
  );
}

export function PageHead({ title, sub, right }) {
  return (
    <div className="page-head">
      <div className="min-w-0">
        <h1 className="text-[19px] font-semibold tracking-tight m-0">{title}</h1>
        {sub && <p className="m-0 text-muted text-[12.5px] max-w-[70ch]">{sub}</p>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">{right}</div>
    </div>
  );
}

export function Disclaimer({ children }) {
  return (
    <div role="note" className="flex gap-2 items-start rounded-md border border-line2 bg-panel2 px-3 py-2 text-[12.5px] text-muted">
      <AlertTriangle size={15} className="text-accent shrink-0 mt-[2px]" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Stat({ label, value, sub, tone, big, term }) {
  const tid = term === false ? null : term || (typeof label === "string" ? termKeyOf(label) : null); // tooltip giải thích thuật ngữ tự gắn theo nhãn
  return (
    <div className="min-w-0">
      <div className="text-[11.5px] text-muted flex items-center gap-[2px] min-w-0"><span className="truncate">{label}</span>{tid && <InfoTip id={tid} label={String(label)} />}</div>
      <div className={cn("num", big ? "text-[20px]" : "text-[15px]", tone)}>{value}</div>
      {sub && <div className="text-[11.5px] text-faint truncate">{sub}</div>}
    </div>
  );
}

export function Loadmore({ shown, pageSize, onMore, loading }) {
  if (shown < pageSize) return null;
  return (
    <div className="pt-3">
      <button className="btn" onClick={onMore} disabled={loading}>{loading ? "Đang tải…" : "Tải thêm"}</button>
    </div>
  );
}

const FRESH_UI = {
  ok: { icon: Clock, word: "", label: "dữ liệu mới" },
  warn: { icon: Clock, word: "chậm", label: "dữ liệu hơi chậm" },
  stale: { icon: AlertTriangle, word: "cũ", label: "dữ liệu cũ" },
  idle: { icon: Moon, word: "nghỉ", label: "thị trường nghỉ, dữ liệu giữ nguyên lần cuối" },
  none: { icon: AlertTriangle, word: "", label: "chưa có dữ liệu" },
};

/**
 * Huy hiệu "nguồn · tuổi dữ liệu". Xanh ≤ warnAfterS, vàng ≤ staleAfterS, đỏ > staleAfterS hoặc không có dữ liệu;
 * xám (biểu tượng trăng) khi thị trường nghỉ (symbol/closed) để không báo đỏ giả. Mọi huy hiệu dùng chung một timer (lib/clock).
 * Không chỉ dựa vào màu: có biểu tượng + chữ ("chậm"/"cũ"/"nghỉ") + sr-only.
 */
export function Freshness({ ts, source, now, warnAfterS = 30, staleAfterS = 180, symbol, closed, compact, stack, label, className }) {
  const tick = useClock();
  const nowMs = now ?? tick;
  const isClosed = closed ?? marketClosed(symbol, nowMs);
  const { level, ageS } = freshness({ ts, nowMs, warnAfterS, staleAfterS, closed: isClosed });
  const u = FRESH_UI[level];
  const Icon = u.icon;
  const abs = level === "none" ? "chưa có bản ghi" : `${fmtDateTime(ts)}:${String(new Date(ts).getSeconds()).padStart(2, "0")} (${isVnTz() ? "giờ VN" : tzOffsetLabel()})`;
  const tip = `${label ? label + " · " : ""}${abs} · ${u.label}`;
  const text = level === "none" ? "chưa có dữ liệu" : ageText(ageS);
  return (
    <span className={cn("fresh", level, compact && "compact", stack && "stack", className)} title={tip}>
      <Icon size={11} aria-hidden="true" />
      <span className="num">{text}</span>
      {u.word && level !== "none" && <span className="fresh-word">· {u.word}</span>}
      <span className="sr-only">{`. Trạng thái: ${u.label}.`}</span>
    </span>
  );
}

/** Huy hiệu cho một danh sách bản ghi: tuổi của bản ghi MỚI NHẤT + các nguồn (tối đa 3). */
export function LatestFresh({ items, tsKey, sourceKey = "source", label, compact, className, ...thr }) {
  let best = null;
  for (const it of items || []) {
    const t = Date.parse(it?.[tsKey]);
    if (Number.isFinite(t) && (best == null || t > best)) best = t;
  }
  return <Freshness ts={best} label={label} compact={compact} className={className} {...thr} />;
}
