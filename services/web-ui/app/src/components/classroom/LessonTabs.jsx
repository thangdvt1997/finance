// Nối tab "Ví dụ" và "Test" của AI Training Class với dữ liệu thật: ExamplesGrid (lưới nhãn) + TestResultCard (thẻ kết quả trung thực).
import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { cget } from "./classApi";
import { useCls } from "./ctx";
import ExamplesGrid from "./ExamplesGrid";
import TestResultCard from "./TestResultCard";

/** Nhãn của phòng (dùng chung với Checklist): [{example_id, verdict, reason}] */
export function useLabels(rid) {
  const q = useQuery({ queryKey: ["cls", rid, "labels"], enabled: !!rid, queryFn: ({ signal }) => cget(`/rooms/${encodeURIComponent(rid)}/labels`, {}, signal), refetchInterval: 8000, retry: false });
  return { items: q.data?.items || [], summary: q.data?.summary || {}, q };
}

export function ExamplesTab({ lang, rid, scans, labels, onSend }) {
  const qc = useQueryClient();
  const examples = useMemo(() => {
    const last = scans[scans.length - 1];
    return (last?.data?.examples || []).slice(0, 10).map((e) => ({ ...e, round: last.data?.round }));
  }, [scans]);
  const onLabel = () => { qc.invalidateQueries({ queryKey: ["cls", rid, "labels"] }); qc.invalidateQueries({ queryKey: ["cls", rid, "profile"] }); qc.invalidateQueries({ queryKey: ["cls", rid, "canvas"] }); };
  return <ExamplesGrid lang={lang} rid={rid} examples={examples} labels={labels} onLabel={onLabel} onSend={onSend} />;
}

export function TestTab({ lang, rid, messages, onSend, onEdit, role }) {
  const { t } = useCls();
  const res = useMemo(() => messages.filter((m) => m.kind === "result_card" && m.data).slice(-3).reverse(), [messages]);
  return (
    <div className="grid gap-3">
      <div className="flex gap-2 items-center flex-wrap">
        <button type="button" className="btn" onClick={() => onSend("/test").catch(() => {})}>{t("Chạy test", "Run test")}</button>
        <span className="text-[12px] text-muted">{t("Test paper trung thực (walk-forward). Cần xác nhận; không mở test khoá.", "Honest paper test (walk-forward). Needs confirmation; no locked test.")}</span>
      </div>
      {!res.length && <p className="m-0 text-[13px] text-muted">{t("Chưa có kết quả test. Không có edge là kết quả bình thường; hãy làm rõ kịch bản và gắn nhãn ví dụ trước khi test.", "No test result yet. No edge is a normal outcome; clarify the scenario and label examples before testing.")}</p>}
      {res.map((m) => <TestResultCard key={m.id} lang={lang} result={m.data} role={role} rid={rid} onSend={onSend} onEdit={onEdit} />)}
    </div>
  );
}
