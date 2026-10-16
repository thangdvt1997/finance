// Huy hiệu số sự cố đang hoạt động trên mục "Sự cố" của thanh điều hướng. Bám 45 giây/lần, tạm dừng khi tab ẩn (TanStack Query). Chỉ vai trò có quyền incident.read.
import { useIncidentCounts, usePerm } from "../../lib/fleetQueries";

export function NavBadge({ id }) {
  const p = usePerm();
  const on = id === "su-co" && !p.loading && p.has("incident.read");
  const q = useIncidentCounts(on);
  if (!on || q.isError) return null;
  const n = (q.data?.open || 0) + (q.data?.ack || 0);
  const crit = q.data?.critical_active || 0;
  if (!n) return null;
  return <span className="fl-navbadge" aria-label={`${n} sự cố đang hoạt động${crit ? `, ${crit} nghiêm trọng` : ""}`} title={`${n} sự cố đang hoạt động${crit ? ` (${crit} nghiêm trọng)` : ""}`}>{n > 99 ? "99+" : n}</span>;
}
