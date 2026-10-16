// Thanh trên AI Training Class: tên kịch bản, phiên bản, Độ rõ ý tưởng (0-100) + gợi ý hàng mơ hồ nhất, nút hành động, trạng thái model.
import { BookOpenCheck, Compass, Download, GraduationCap, LayoutTemplate, Lightbulb, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Play, Save, Users } from "lucide-react";
import { Chip, cn } from "../ui";
import ModelStatus from "./ModelStatus";

const tone = (s) => (s >= 70 ? "up" : s >= 40 ? "accent" : "down");

export default function TopBar({ t, title, version, clarity, onHint, onSave, onTest, onExport, onDemo, onGuide, onTemplates, onTour, llm, speed, streaming, busy, hasRoom, left, right, onToggleLeft, onToggleRight, onRooms }) {
  const sc = clarity?.score ?? 0, wk = clarity?.weakest;
  return (
    <div className="cr-top panel" data-tour="topbar">
      <div className="cr-top-l">
        <button type="button" className="cr-iconbtn big cr-only-m" onClick={onRooms} aria-label={t("Danh sách phòng", "Rooms")}><Users size={17} /></button>
        <button type="button" className="cr-iconbtn big cr-only-d" onClick={onToggleLeft} aria-pressed={!left} aria-label={left ? t("Thu gọn cột phòng", "Collapse rooms column") : t("Mở cột phòng", "Expand rooms column")}>{left ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}</button>
        <GraduationCap size={16} aria-hidden="true" className="text-muted shrink-0" />
        <h2 className="m-0 text-[14px] font-semibold truncate min-w-0" title={title}>{title || t("Chưa chọn kịch bản", "No scenario selected")}</h2>
        {version != null && <Chip tone="accent">v{version}</Chip>}
      </div>
      {hasRoom && (
        <div className="cr-clarity" data-tour="clarity">
          <div className="flex items-baseline gap-2">
            <span className="text-[12px] font-semibold" id="cr-clarity-l">{t("Độ rõ ý tưởng", "Idea clarity")}</span>
            <b className={cn("num text-[14px]", `cr-sc-${tone(sc)}`)}>{sc}<span className="text-[11px] text-muted">/100</span></b>
            <span className="text-[11.5px] text-muted hidden sm:inline">{clarity?.confirmed ?? 0}/{clarity?.total ?? 16} {t("đã xác nhận", "confirmed")}</span>
          </div>
          <div className="cr-meter" role="progressbar" aria-labelledby="cr-clarity-l" aria-valuemin={0} aria-valuemax={100} aria-valuenow={sc} aria-valuetext={`${sc}/100`}><i className={`t-${tone(sc)}`} style={{ width: `${sc}%` }} /></div>
          {wk ? <button type="button" className="cr-hint" onClick={() => onHint(wk)} title={clarity?.next || t("Hàng mơ hồ nhất: bấm để xem và hỏi tiếp", "Vaguest row: click to view and ask on")}><Lightbulb size={12} aria-hidden="true" />{t("Mơ hồ nhất", "Vaguest")}: <b>{wk.label}</b></button> : <span className="text-[11.5px] text-muted">{t("Các hàng đã đủ rõ.", "All rows are clear enough.")}</span>}
        </div>
      )}
      <div className="cr-top-r">
        {hasRoom && <span className="cr-act-g" data-tour="actions">
          <button type="button" className="btn cr-act-b" onClick={onSave} aria-label={t("Lưu phiên bản", "Save version")} title={t("Lưu phiên bản", "Save version")} disabled={busy}><Save size={14} aria-hidden="true" /><span className="cr-lbl">{t("Lưu phiên bản", "Save version")}</span></button>
          <button type="button" className="btn cr-act-b" onClick={onTest} aria-label={t("Chạy test", "Run test")} title={t("Chạy test", "Run test")} disabled={busy}><Play size={14} aria-hidden="true" /><span className="cr-lbl">{t("Chạy test", "Run test")}</span></button>
          <button type="button" className="btn ghost cr-act-b" onClick={onExport} aria-label={t("Xuất", "Export")} title={t("Xuất", "Export")}><Download size={14} aria-hidden="true" /><span className="cr-lbl">{t("Xuất", "Export")}</span></button>
        </span>}
        <span className="cr-sep" aria-hidden="true" />
        <button type="button" className="btn ghost cr-act-b" onClick={onDemo} aria-label={t("Xem demo", "Watch demo")} title={t("Xem demo", "Watch demo")} data-tour="demo"><BookOpenCheck size={14} aria-hidden="true" /><span className="cr-lbl">{t("Xem demo", "Watch demo")}</span></button>
        <button type="button" className="btn ghost cr-act-b" onClick={onGuide} aria-label={t("Cách dạy", "How to teach")} title={t("Cách dạy", "How to teach")} data-tour="guide"><Lightbulb size={14} aria-hidden="true" /><span className="cr-lbl">{t("Cách dạy", "How to teach")}</span></button>
        <button type="button" className="btn ghost cr-act-b" onClick={onTemplates} aria-label={t("Mẫu", "Templates")} title={t("Mẫu", "Templates")}><LayoutTemplate size={14} aria-hidden="true" /><span className="cr-lbl">{t("Mẫu", "Templates")}</span></button>
        <button type="button" className="btn ghost cr-act-b" onClick={onTour} aria-label={t("Tham quan giao diện", "Interface tour")}><Compass size={14} aria-hidden="true" /><span className="cr-lbl cr-lbl-xl">{t("Tham quan", "Tour")}</span></button>
        <button type="button" className="cr-iconbtn big cr-only-d" onClick={onToggleRight} aria-pressed={!right} aria-label={right ? t("Thu gọn cột hồ sơ", "Collapse profile column") : t("Mở cột hồ sơ", "Expand profile column")}>{right ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}</button>
      </div>
      <ModelStatus llm={llm} speed={speed} streaming={streaming} t={t} className="cr-top-m" />
    </div>
  );
}
