// "Dạy kịch bản mới" (tab AI Trading > Kịch bản nến & sóng): nạp YAML + ảnh mẫu -> detector thử/golden -> backtest nền trung thực -> test khoá (1 lần, xác nhận rõ).
// CHỈ nghiên cứu/paper. API (master): POST /ai-trading/scenarios, POST /ai-trading/scenarios/{id}/jobs, GET /ai-trading/scenarios/{id}/jobs.
// Nhãn trung thực luôn hiện: dev = walk-forward ngoài mẫu; test khoá mở tối đa 1 lần; không có nút đặt lệnh.
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileUp, FlaskConical, GraduationCap, Lock, Play, ShieldAlert, XCircle } from "lucide-react";
import { Chip, Disclaimer, Panel, Stat } from "../ui";
import { Dialog } from "../dialog";
import { api, apiWrite } from "../../lib/api";

const EN2 = {
  "Dạy kịch bản mới": "Teach a new scenario",
  "Nạp một kịch bản bằng YAML (luật khai báo, không viết mã) + ảnh mẫu. Hệ thống kiểm tra schema, chạy detector thử trên dữ liệu dev, golden test, rồi backtest trung thực chạy nền. Chỉ nghiên cứu/paper — không đặt lệnh.":
    "Load a scenario as YAML (declarative rules, no code) + sample images. The system validates the schema, runs the detector on dev data, a golden test, then an honest background backtest. Research/paper only — no orders.",
  "YAML kịch bản": "Scenario YAML", "Nạp mẫu": "Load template", "Chọn tệp YAML": "Pick YAML file", "Ảnh mẫu (png/jpg/webp, tối đa 5 ảnh, mỗi ảnh ≤ 700 KB)": "Sample images (png/jpg/webp, up to 5, each ≤ 700 KB)",
  "Kiểm tra & lưu kịch bản": "Validate & save scenario", "Đang lưu…": "Saving…", "Đã lưu kịch bản": "Scenario saved",
  "Mỗi lần sửa luật phải dùng id mới (họ family giữ nguyên) để số lần thử được đếm đúng và DSR trừ đúng.": "Every rule change needs a new id (keep the same family) so the number of trials is counted and the DSR is deflated correctly.",
  "Quy trình trung thực": "Honest workflow", "1. Detector thử + golden": "1. Detector test + golden", "2. Backtest nền (walk-forward)": "2. Background backtest (walk-forward)", "3. Mở test khoá": "3. Open locked test",
  "Chạy": "Run", "Đang chạy…": "Running…", "Xếp hàng": "Queued", "Đang chạy": "Running", "Xong": "Done", "Lỗi": "Failed",
  "Test khoá của kịch bản này chỉ mở MỘT lần, không lặp lại và được ghi nhật ký. Chỉ mở khi bạn đã chốt luật; sau khi mở không thể chỉnh theo kết quả test (phải tạo id mới).": "The locked test of this scenario can be opened ONLY ONCE, cannot be repeated and is logged. Open it only after you fixed the rules; afterwards you cannot tune on test results (a new id is required).",
  "Mở test khoá (một lần)": "Open locked test (once)", "Xác nhận mở test khoá": "Confirm opening the locked test", "Gõ đúng id kịch bản để xác nhận:": "Type the exact scenario id to confirm:", "Huỷ": "Cancel", "Mở test khoá": "Open locked test",
  "Đã mở test khoá": "Locked test opened", "Chưa mở": "Not opened", "Cần chạy backtest dev xong trước.": "Run the dev backtest first.",
  "Kết quả detector (dev)": "Detector result (dev)", "Mã:khung": "Symbol:TF", "Tín hiệu": "Signals", "Mỗi 1000 nến": "Per 1000 bars", "Ví dụ": "Examples", "Golden test": "Golden test", "Đạt": "Pass", "Không đạt": "Fail", "Từ chối": "Rejected", "Không có dữ liệu": "No data",
  "Walk-forward dev (ngoài mẫu)": "Walk-forward dev (out-of-sample)", "Test khoá (1 lần)": "Locked test (once)", "Kỳ vọng": "Expectancy", "p so với ngẫu nhiên": "p vs random", "Số lệnh": "Trades",
  "Khoảng tin cậy 95%": "95% CI", "Sụt vốn tối đa": "Max drawdown", "Kỳ vọng trước chi phí": "Gross expectancy", "Số lần thử (DSR)": "Trials (DSR)", "PBO (quá khớp)": "PBO (overfit)",
  "Kết quả KHÔNG có edge hoặc chưa chứng minh là kết quả bình thường: đừng chỉnh luật theo test.": "No-edge or unproven is a normal outcome: do not tune the rules on the test.",
  "Ảnh mẫu": "Sample images", "Tiến trình job": "Job progress", "Tải sổ lệnh dev (CSV)": "Download dev ledger (CSV)", "Tải sổ lệnh test (CSV)": "Download test ledger (CSV)",
  "Nhãn": "Labels", "Chỉ nghiên cứu/paper": "Research/paper only", "Test khoá riêng cho id này": "Own locked test for this id", "Snapshot dữ liệu": "Data snapshot",
  "Thử nghiệm trong họ": "Trials in family", "Chưa chạy": "Not run", "Lịch sử job": "Job history", "Không tải được trạng thái job.": "Could not load job status.",
};
const TEMPLATE = `id: SC-MY-1               # 3-32 ký tự [A-Za-z0-9_-]; sửa luật = id mới
name: "Tên kịch bản"
summary: "Mô tả ngắn"
side: sell
symbols: [EURUSD]        # tối đa 4 mã (dữ liệu lịch sử có sẵn)
tfs: [H1]                # M15 | H1 | H4 | D1
detector:
  cooldown_bars: 8
  rules:                 # AND; luật: move_atr, bear_body, bear_engulf, upper_wick, break_low, ma, rsi, hours
    - {rule: move_atr, dir: up, bars: 6, min: 2.0}
    - {rule: upper_wick, min_ratio: 0.4}
    - {rule: bear_body, min_atr: 0.3}
levels:
  sl: {type: swing_high, bars: 6, buffer_atr: [0.25, 0.5]}
  tp_r: [1.0, 2.0]
  max_hold: 60
# golden:                # (tuỳ chọn) nến phải kích hoạt; bar_ts = giờ mở nến (UTC), nằm TRƯỚC vùng test khoá
#   - {symbol: EURUSD, tf: H1, bar_ts: "2024-08-23T18:00", expect: true}
`;
const MAX_IMG = 700 * 1024;
const STATUS = { queued: ["Xếp hàng", ""], running: ["Đang chạy", "info"], done: ["Xong", "up"], failed: ["Lỗi", "down"] };
const rr = (v, dp = 2) => (v == null || !Number.isFinite(+v) ? "—" : `${+v > 0 ? "+" : ""}${(+v).toFixed(dp).replace(".", ",")}R`);
const pv = (v) => (v == null || !Number.isFinite(+v) ? "—" : (+v).toFixed(3).replace(".", ","));
const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const imgUrl = (u) => (u ? `/api${u.startsWith("/") ? "" : "/"}${u}` : null);
const makeT = (T) => { const en = T("Tổng quan") === "Overview"; return (s) => { const r = T(s); return r !== s ? r : en ? EN2[s] ?? s : s; }; };

const toB64 = (file) => new Promise((res, rej) => {
  const fr = new FileReader();
  fr.onload = () => res(String(fr.result).split(",")[1] || "");
  fr.onerror = () => rej(new Error("read"));
  fr.readAsDataURL(file);
});

// ---------------------------------------------------------------- Form nạp
export function TeachPanel({ T, onCreated }) {
  const t = makeT(T);
  const qc = useQueryClient();
  const [yaml, setYaml] = useState("");
  const [files, setFiles] = useState([]);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const fileRef = useRef(null);
  const save = useMutation({
    mutationFn: async () => {
      const names = files.map((f) => f.name);
      const imgs = {};
      for (const f of files) imgs[f.name] = await toB64(f);
      const body = yaml.split("\n").filter((l) => !/^images\s*:/.test(l)).join("\n") + (names.length ? `\nimages: ${JSON.stringify(names)}\n` : "\n");
      return apiWrite("POST", "/ai-trading/scenarios", { yaml: body, images: imgs }, { maxBytes: 6 * 1024 * 1024 - 1024 });
    },
    onSuccess: (r) => { setErr(""); setOk(`${t("Đã lưu kịch bản")}: ${r.id}`); qc.invalidateQueries({ queryKey: ["ai-trading"] }); onCreated?.(r.id); },
    onError: (e) => { setOk(""); setErr(e?.message || "Lỗi"); },
  });
  const [prev, setPrev] = useState({});
  const pickImgs = (e) => {
    const fs = [...(e.target.files || [])];
    const bad = fs.find((f) => f.size > MAX_IMG || !/\.(png|jpe?g|webp)$/i.test(f.name) || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,58}\.(png|jpe?g|webp)$/i.test(f.name));
    if (fs.length > 5 || bad) { setErr(fs.length > 5 ? "Tối đa 5 ảnh." : `Ảnh không hợp lệ: ${bad.name} (tên chỉ chữ/số/_/-, png/jpg/webp, ≤ 700 KB).`); e.target.value = ""; return; }
    setErr(""); setFiles(fs); setPrev({});
    fs.forEach((f) => toB64(f).then((b) => setPrev((p) => ({ ...p, [f.name]: `data:${f.type};base64,${b}` }))).catch(() => {}));   // CSP chỉ cho img data:/self (không blob:)
  };
  const pickYaml = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 16 * 1024) { setErr("YAML tối đa 16 KB."); return; }
    f.text().then((x) => { setYaml(x); setErr(""); });
  };
  return (
    <Panel title={t("Dạy kịch bản mới")} icon={GraduationCap}>
      <div className="grid gap-3">
        <p className="m-0 text-[12.5px] text-muted">{t("Nạp một kịch bản bằng YAML (luật khai báo, không viết mã) + ảnh mẫu. Hệ thống kiểm tra schema, chạy detector thử trên dữ liệu dev, golden test, rồi backtest trung thực chạy nền. Chỉ nghiên cứu/paper — không đặt lệnh.")}</p>
        <label className="grid gap-1 text-[12px] text-muted">
          <span>{t("YAML kịch bản")}</span>
          <textarea className="field w-full font-mono" style={{ height: "auto", minHeight: "14rem", padding: ".5rem .6rem", fontSize: 12.5 }} rows={14} spellCheck={false}
            value={yaml} onChange={(e) => setYaml(e.target.value)} placeholder={TEMPLATE} aria-label={t("YAML kịch bản")} maxLength={16000} />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn" onClick={() => setYaml(TEMPLATE)}><FileUp size={15} aria-hidden="true" /> {t("Nạp mẫu")}</button>
          <label className="btn cursor-pointer"><FileUp size={15} aria-hidden="true" /> {t("Chọn tệp YAML")}<input type="file" accept=".yaml,.yml,text/yaml" className="sr-only" onChange={pickYaml} /></label>
        </div>
        <label className="grid gap-1 text-[12px] text-muted">
          <span>{t("Ảnh mẫu (png/jpg/webp, tối đa 5 ảnh, mỗi ảnh ≤ 700 KB)")}</span>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={pickImgs} className="text-[12.5px]" />
        </label>
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2" aria-label={t("Ảnh mẫu")}>
            {files.map((f) => <figure key={f.name} className="m-0 grid gap-0.5 w-24"><img src={prev[f.name]} alt={f.name} className="w-24 h-16 object-cover rounded border border-line2" /><figcaption className="text-[10.5px] text-muted truncate">{f.name}</figcaption></figure>)}
          </div>
        )}
        <div className="text-[11.5px] text-muted">{t("Mỗi lần sửa luật phải dùng id mới (họ family giữ nguyên) để số lần thử được đếm đúng và DSR trừ đúng.")}</div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn" disabled={save.isPending || yaml.trim().length < 20} onClick={() => save.mutate()}>
            <Play size={15} aria-hidden="true" /> {save.isPending ? t("Đang lưu…") : t("Kiểm tra & lưu kịch bản")}
          </button>
          {ok && <span role="status" className="text-[12.5px]" style={{ color: "var(--up, #1a9d5b)" }}>{ok}</span>}
        </div>
        {err && <div role="alert" className="text-[12.5px] rounded border border-line2 p-2" style={{ color: "var(--down, #d64545)" }}>{err}</div>}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- Quy trình cho 1 kịch bản người dùng nạp
function JobChip({ j, t }) {
  const [l, tn] = STATUS[j.status] || [j.status, ""];
  return <Chip tone={tn}>{t(l)}</Chip>;
}

function Bar({ v }) {
  const p = Math.max(0, Math.min(100, Math.round((v || 0) * 100)));
  return <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p} className="h-1.5 rounded bg-panel2 border border-line2 overflow-hidden"><div style={{ width: `${p}%`, height: "100%", background: "var(--accent)" }} /></div>;
}

export function ScenarioFlow({ x, T }) {
  const t = makeT(T);
  const qc = useQueryClient();
  const sc = x.scenario || {};
  const id = x.id;
  const [confirm, setConfirm] = useState(false);
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState("");
  const jobs = useQuery({
    queryKey: ["ai-trading", "jobs", id], queryFn: ({ signal }) => api(`/ai-trading/scenarios/${encodeURIComponent(id)}/jobs`, {}, signal),
    refetchInterval: (q) => ((q.state.data?.items || []).some((j) => j.status === "queued" || j.status === "running") ? 2500 : 20000),
  });
  const items = jobs.data?.items || [];
  const active = items.find((j) => j.status === "queued" || j.status === "running");
  const last = items[items.length - 1];
  const prevActive = useRef(null);
  if (prevActive.current && !active) qc.invalidateQueries({ queryKey: ["ai-trading"] });   // job vừa xong -> làm mới thẻ/kết quả
  prevActive.current = active?.id || null;
  const run = useMutation({
    mutationFn: ({ type, confirm: c }) => apiWrite("POST", `/ai-trading/scenarios/${encodeURIComponent(id)}/jobs`, c ? { type, confirm: c } : { type }),
    onSuccess: () => { setErr(""); setConfirm(false); setTyped(""); qc.invalidateQueries({ queryKey: ["ai-trading", "jobs", id] }); },
    onError: (e) => { setErr(e?.message || "Lỗi"); setConfirm(false); },
  });
  const det = sc.detector, dev = sc.dev || {}, te = sc.test;
  const devDone = dev.status === "done", opened = !!sc.test_opened;
  const pooled = dev.oos?.pooled;
  const teSum = te?.summary;
  const step = (type, label, enabled, done, extra) => (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <span className="text-[13px] flex-1 min-w-[12rem]">{t(label)} {done && <CheckCircle2 size={14} className="inline align-text-bottom" aria-label={t("Xong")} />}</span>
      {extra}
      <button type="button" className="btn" disabled={!enabled || !!active || run.isPending} onClick={() => run.mutate({ type })}>
        <Play size={14} aria-hidden="true" /> {active?.type === type ? t("Đang chạy…") : t("Chạy")}
      </button>
    </div>
  );
  return (
    <Panel title={t("Quy trình trung thực")} icon={FlaskConical}>
      <div className="grid gap-3">
        <div className="flex flex-wrap gap-2 items-center" aria-label={t("Nhãn")}>
          <Chip tone="info">{t("Chỉ nghiên cứu/paper")}</Chip>
          <Chip>{t("Test khoá riêng cho id này")}</Chip>
          <Chip>{t("Thử nghiệm trong họ")}: {sc.family_trials ?? 1}</Chip>
          {dev.snapshot_sha && <Chip title={dev.snapshot_sha}>{t("Snapshot dữ liệu")}: {dev.snapshot_sha}</Chip>}
        </div>
        <div className="grid divide-y divide-[var(--line2)]">
          {step("detector_test", "1. Detector thử + golden", true, det?.status === "done")}
          {step("backtest", "2. Backtest nền (walk-forward)", !opened, devDone)}
          <div className="flex flex-wrap items-center gap-2 py-1">
            <span className="text-[13px] flex-1 min-w-[12rem]">{t("3. Mở test khoá")} {opened ? <Chip tone="info">{t("Đã mở test khoá")}</Chip> : <Chip>{t("Chưa mở")}</Chip>}</span>
            <button type="button" className="btn" disabled={!devDone || opened || !!active || run.isPending} onClick={() => { setErr(""); setConfirm(true); }}>
              <Lock size={14} aria-hidden="true" /> {t("Mở test khoá (một lần)")}
            </button>
          </div>
          {!devDone && !opened && <div className="text-[11.5px] text-muted py-1">{t("Cần chạy backtest dev xong trước.")}</div>}
        </div>
        {err && <div role="alert" className="text-[12.5px] rounded border border-line2 p-2" style={{ color: "var(--down, #d64545)" }}>{err}</div>}
        <div aria-label={t("Tiến trình job")}>
          {jobs.isError ? <span className="text-[12px] text-muted">{t("Không tải được trạng thái job.")}</span> : last ? (
            <div className="grid gap-1">
              <div className="flex flex-wrap items-center gap-2 text-[12.5px]"><JobChip j={last} t={t} /><b>{last.type}</b><span className="text-muted">{last.stage}</span></div>
              <Bar v={last.status === "done" ? 1 : last.progress} />
              <div className="text-[12px] text-muted">{last.message}</div>
            </div>
          ) : <span className="text-[12px] text-muted">{t("Chưa chạy")}</span>}
        </div>
        {det?.status === "done" && (
          <div className="grid gap-2">
            <div className="text-[12.5px] font-semibold">{t("Kết quả detector (dev)")}</div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]"><thead><tr className="text-left text-muted"><th>{t("Mã:khung")}</th><th>{t("Tín hiệu")}</th><th>{t("Mỗi 1000 nến")}</th><th>{t("Ví dụ")}</th></tr></thead>
                <tbody>{Object.entries(det.by_series || {}).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.n_signals}</td><td>{String(v.per_1000_bars).replace(".", ",")}</td><td className="text-muted">{(v.examples || []).slice(0, 2).join(", ")}</td></tr>)}</tbody></table>
            </div>
            {(det.golden || []).length > 0 && (
              <div className="grid gap-1" aria-label={t("Golden test")}>
                <div className="text-[12.5px] font-semibold">{t("Golden test")} ({det.golden_pass}/{det.golden_total})</div>
                {det.golden.map((g, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 text-[12.5px]">
                    {g.status === "pass" ? <CheckCircle2 size={14} aria-hidden="true" /> : <XCircle size={14} aria-hidden="true" />}
                    <Chip tone={g.status === "pass" ? "up" : "down"}>{t(g.status === "pass" ? "Đạt" : g.status === "fail" ? "Không đạt" : g.status === "rejected" ? "Từ chối" : "Không có dữ liệu")}</Chip>
                    <span>{g.symbol}:{g.tf} {g.bar_ts}</span><span className="text-muted">{g.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {(pooled || teSum) && (
          <div className="grid gap-3">
            {pooled && (
              <div className="grid gap-1">
                <div className="flex flex-wrap items-center gap-2 text-[12.5px] font-semibold">{t("Walk-forward dev (ngoài mẫu)")} <Chip>{x.backtest?.splits?.dev?.n ?? pooled.n} {t("Số lệnh").toLowerCase()}</Chip></div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  <Stat label={t("Kỳ vọng")} value={rr(pooled.exp_r)} tone={tone(pooled.exp_r)} term={false} />
                  <Stat label={t("Khoảng tin cậy 95%")} value={Array.isArray(pooled.ci95) ? `${rr(pooled.ci95[0])} … ${rr(pooled.ci95[1])}` : "—"} term={false} />
                  <Stat label={t("p so với ngẫu nhiên")} value={pv(dev.oos?.p_vs_random)} term={false} />
                  <Stat label={t("Kỳ vọng trước chi phí")} value={rr(dev.oos_gross_exp_r)} term={false} />
                  <Stat label="DSR" value={pv(dev.dsr?.dsr)} sub={`${t("Số lần thử (DSR)")}: ${dev.n_trials ?? "—"}`} term={false} />
                  <Stat label={t("PBO (quá khớp)")} value={pv(dev.pbo?.pbo)} term={false} />
                </div>
                {devDone && <a className="btn self-start" href={`/api/v1/ai-trading/ledger.csv?strategy=${encodeURIComponent(id)}&source=backtest_dev`} download>{t("Tải sổ lệnh dev (CSV)")}</a>}
              </div>
            )}
            {te?.status === "done" && teSum && (
              <div className="grid gap-1">
                <div className="flex flex-wrap items-center gap-2 text-[12.5px] font-semibold"><Lock size={13} aria-hidden="true" /> {t("Test khoá (1 lần)")} <Chip>{teSum.n} {t("Số lệnh").toLowerCase()}</Chip></div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <Stat label={t("Kỳ vọng")} value={rr(teSum.exp_r)} tone={tone(teSum.exp_r)} term={false} />
                  <Stat label={t("Khoảng tin cậy 95%")} value={Array.isArray(teSum.ci95) ? `${rr(teSum.ci95[0])} … ${rr(teSum.ci95[1])}` : "—"} term={false} />
                  <Stat label={t("p so với ngẫu nhiên")} value={pv(te.p_vs_random)} term={false} />
                  <Stat label={t("Sụt vốn tối đa")} value={teSum.maxdd_r == null ? "—" : `-${Math.abs(+teSum.maxdd_r).toFixed(1).replace(".", ",")}R`} tone="down" term={false} />
                </div>
                <a className="btn self-start" href={`/api/v1/ai-trading/ledger.csv?strategy=${encodeURIComponent(id)}&source=backtest_test`} download>{t("Tải sổ lệnh test (CSV)")}</a>
              </div>
            )}
            {te?.status === "failed" && <Disclaimer>{te.error}</Disclaimer>}
            <Disclaimer>{t("Kết quả KHÔNG có edge hoặc chưa chứng minh là kết quả bình thường: đừng chỉnh luật theo test.")}</Disclaimer>
          </div>
        )}
        {(sc.images || []).length > 0 && (
          <div className="grid gap-1">
            <div className="text-[12.5px] font-semibold">{t("Ảnh mẫu")}</div>
            <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(min(100%,180px),1fr))]">
              {sc.images.map((im) => <a key={im.name} href={imgUrl(im.url)} target="_blank" rel="noreferrer"><img src={imgUrl(im.url)} alt={im.name} loading="lazy" className="w-full rounded border border-line2 bg-panel2" /></a>)}
            </div>
          </div>
        )}
        {items.length > 1 && (
          <details><summary className="text-[12px] text-muted cursor-pointer">{t("Lịch sử job")} ({items.length})</summary>
            <ul className="m-0 pl-4 text-[12px]">{[...items].reverse().map((j) => <li key={j.id}>{j.type} · {j.status} · {String(j.created_at).slice(0, 16)} {j.error ? `· ${j.error}` : ""}</li>)}</ul>
          </details>
        )}
      </div>
      <Dialog open={confirm} onClose={() => { setConfirm(false); setTyped(""); }} title={t("Xác nhận mở test khoá")}
        footer={<>
          <button type="button" className="btn" onClick={() => { setConfirm(false); setTyped(""); }}>{t("Huỷ")}</button>
          <button type="button" className="btn" disabled={typed !== id || run.isPending} onClick={() => run.mutate({ type: "final_test", confirm: id })}><Lock size={14} aria-hidden="true" /> {t("Mở test khoá")}</button>
        </>}>
        <div className="grid gap-2 text-[13px]">
          <div className="flex gap-2 items-start"><ShieldAlert size={18} aria-hidden="true" className="shrink-0" /><p className="m-0">{t("Test khoá của kịch bản này chỉ mở MỘT lần, không lặp lại và được ghi nhật ký. Chỉ mở khi bạn đã chốt luật; sau khi mở không thể chỉnh theo kết quả test (phải tạo id mới).")}</p></div>
          <label className="grid gap-1">{t("Gõ đúng id kịch bản để xác nhận:")} <b>{id}</b>
            <input className="field" data-autofocus value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" aria-label={id} />
          </label>
        </div>
      </Dialog>
    </Panel>
  );
}
