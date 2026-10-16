// Thanh trạng thái model: cục bộ / Claude API, tốc độ trả lời (ký tự/giây, đo lúc streaming), chi phí nếu máy chủ trả về.
import { Cloud, Cpu, Gauge } from "lucide-react";
import { Chip } from "../ui";

export default function ModelStatus({ llm, speed, streaming, t, className = "" }) {
  if (!llm) return <span className={`text-[11.5px] text-muted ${className}`}>{t("Mô hình: đang kiểm tra…", "Model: checking…")}</span>;
  const cloud = llm.provider === "claude", Ic = cloud ? Cloud : Cpu;
  const off = llm.enabled === false;
  const cost = llm.cost_usd ?? llm.cost;
  return (
    <span className={`cr-model ${className}`} role="status" aria-label={t("Trạng thái mô hình", "Model status")} title={llm.note || ""}>
      <Chip tone={off ? "down" : cloud ? "accent" : "info"}><Ic size={11} aria-hidden="true" className="inline mr-1" />{cloud ? t("Claude API", "Claude API") : t("Cục bộ", "Local")}{off ? ` · ${t("tắt", "off")}` : ""}</Chip>
      {speed > 0 && <span className="cr-mstat"><Gauge size={11} aria-hidden="true" />{Math.round(speed)} {t("ký tự/giây", "chars/s")}</span>}
      {streaming && !speed && <span className="cr-mstat">{t("đang trả lời…", "replying…")}</span>}
      {cost != null && Number.isFinite(+cost) && <span className="cr-mstat">${(+cost).toFixed(3)}</span>}
    </span>
  );
}
