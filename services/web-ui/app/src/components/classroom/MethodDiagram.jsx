// Sơ đồ kịch bản + quan hệ (SVG thuần). Bấm/ Enter vào nút mở phòng của kịch bản. Quan hệ phân biệt bằng kiểu nét + nhãn chữ (không chỉ màu).
import { REL_BY, REGIMES, roleLabel } from "./methodsApi";

const STYLE = { exclusive: ["var(--down)", "6 4", false], complementary: ["var(--up)", "", false], priority: ["var(--accent)", "", true], regime: ["var(--info)", "2 4", false], mirror: ["var(--fg)", "8 3 2 3", false], timeframe: ["var(--info)", "", true] };
const W = 640, NW = 150, NH = 44;

export default function MethodDiagram({ scenarios, relations, t, lang, onOpen }) {
  const n = scenarios.length;
  if (!n) return <p className="m-0 text-[12.5px] text-muted" role="note">{t("Chưa có kịch bản nào trong phương pháp. Thêm kịch bản để thấy sơ đồ.", "No scenarios in this method yet. Add scenarios to see the diagram.")}</p>;
  const cols = n <= 3 ? n : n <= 6 ? 3 : 4, rowsN = Math.ceil(n / cols), H = Math.max(150, rowsN * 110 + 30);
  const pos = {}; scenarios.forEach((s, i) => { const c = i % cols, r = Math.floor(i / cols), inRow = r === rowsN - 1 ? n - r * cols : cols; const gap = W / inRow; pos[s.rid] = { x: gap * (i % cols + 0.5), y: 55 + r * 110 }; });
  const kinds = [...new Set(relations.map((r) => r.kind))];
  return (
    <div className="grid gap-2">
      <svg className="cm-svg" viewBox={`0 0 ${W} ${H}`} role="group" aria-label={t("Sơ đồ kịch bản và quan hệ", "Scenario and relation diagram")}>
        <defs>{Object.entries(STYLE).map(([k, [c]]) => <marker key={k} id={`cm-ar-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={c} /></marker>)}</defs>
        {relations.map((r) => {
          const a = pos[r.a], b = pos[r.b]; if (!a || !b || r.a === r.b) return null;
          const [c, d, dir] = STYLE[r.kind] || STYLE.complementary, mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - 18 - (a.y === b.y ? 14 : 0);
          const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy) || 1, sx = a.x + (dx / L) * (NW / 2 + 2) * (Math.abs(dx) > Math.abs(dy) ? 1 : 0.2), ex = b.x - (dx / L) * (NW / 2 + 6) * (Math.abs(dx) > Math.abs(dy) ? 1 : 0.2);
          const sy = a.y + (Math.abs(dx) > Math.abs(dy) ? 0 : Math.sign(dy) * (NH / 2 + 2)), ey = b.y - (Math.abs(dx) > Math.abs(dy) ? 0 : Math.sign(dy) * (NH / 2 + 6));
          const lab = REL_BY[r.kind] ? (lang === "en" ? REL_BY[r.kind][2] : REL_BY[r.kind][1]) : r.kind;
          return <g key={r.id}><path className="cm-edge" d={`M${sx} ${sy} Q${mx} ${my} ${ex} ${ey}`} stroke={c} strokeDasharray={d} markerEnd={dir ? `url(#cm-ar-${r.kind})` : undefined} /><text x={mx} y={my + 6} textAnchor="middle" fontSize="10.5" fill="var(--fg)" stroke="var(--panel2)" strokeWidth="3" paintOrder="stroke">{lab}</text></g>;
        })}
        {scenarios.map((s) => {
          const p = pos[s.rid], label = (s.title || s.rid).slice(0, 22), rg = relations.find((r) => r.kind === "regime" && r.a === s.rid);
          const go = () => onOpen?.(s.rid);
          return (
            <g key={s.rid} className="cm-node" tabIndex={0} role="button" aria-label={`${t("Mở phòng", "Open room")}: ${s.title}`} onClick={go} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }}>
              <rect x={p.x - NW / 2} y={p.y - NH / 2} width={NW} height={NH} rx="8" />
              <text x={p.x} y={p.y - 3} textAnchor="middle">{label}</text>
              <text className="s" x={p.x} y={p.y + 13} textAnchor="middle">{s.clarity != null ? `${t("Độ rõ", "Clarity")} ${s.clarity}` : t("Chưa có độ rõ", "No clarity yet")}{s.role ? ` · ${roleLabel(s.role, lang === "en")}` : ""}</text>
              {rg && <text className="s" x={p.x} y={p.y + NH / 2 + 13} textAnchor="middle">{t("Regime", "Regime")}: {(REGIMES.find((g) => g[0] === rg.regime) || [])[lang === "en" ? 2 : 1] || rg.regime}</text>}
            </g>
          );
        })}
      </svg>
      {kinds.length > 0 && <ul className="m-0 p-0 list-none flex flex-wrap gap-x-4 gap-y-1 text-[12px]" aria-label={t("Chú giải", "Legend")}>{kinds.map((k) => { const [c, d] = STYLE[k] || STYLE.complementary; return <li key={k} className="inline-flex items-center gap-1"><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" stroke={c} strokeWidth="2" strokeDasharray={d} /></svg>{REL_BY[k] ? (lang === "en" ? REL_BY[k][2] : REL_BY[k][1]) : k}</li>; })}</ul>}
    </div>
  );
}
