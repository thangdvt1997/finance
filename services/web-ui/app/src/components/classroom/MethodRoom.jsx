// Phòng phương pháp: chat SSE ở mức phương pháp (cách kịch bản phối hợp, quản trị vốn chung, dừng giao dịch...) + option gợi ý + hồ sơ phương pháp (canvas).
// Tái dùng Bubble/Composer/ProfileCanvas của phòng kịch bản (qua ClassCtx với rid ảo `m:<mid>`).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip } from "../ui";
import { ClassCtx } from "./ctx";
import Bubble from "./MessageView";
import Composer from "./Composer";
import Markdown from "./Markdown";
import ProfileCanvas from "./ProfileCanvas";
import { mget, mwrite, enc, normCanvasRows, clarityOf, streamMethodMessage } from "./methodsApi";

const SEED = [["Khi nào dùng phương pháp này (bối cảnh, regime)?", "When should this method be used (context, regime)?"], ["Khi nhiều tín hiệu cùng lúc thì ưu tiên thế nào?", "When several signals fire at once, which comes first?"], ["Quản trị vốn chung: rủi ro mỗi lệnh, tổng rủi ro nóng, giới hạn lỗ ngày/ tuần?", "Shared risk: risk per trade, total open risk, daily/weekly loss limits?"], ["Quy tắc dừng giao dịch: tin lớn, spread, giờ rollover?", "Stop rules: major news, spread, rollover hours?"]];

export default function MethodRoom({ mid, lang, t, me, isMaster }) {
  const qc = useQueryClient(), vrid = `m:${mid}`;
  const [streaming, setStreaming] = useState(false), [live, setLive] = useState(null), [err, setErr] = useState(null), [tab, setTab] = useState("chat");
  const abort = useRef(null), box = useRef(null), comp = useRef(null);
  const dq = useQuery({ queryKey: ["cls", "m", mid, "room"], queryFn: ({ signal }) => mget(`/methods/${enc(mid)}/messages`, { limit: 50 }, signal), refetchInterval: streaming ? false : 6000, retry: false });
  const cq = useQuery({ queryKey: ["cls", "m", mid, "canvas"], queryFn: ({ signal }) => mget(`/methods/${enc(mid)}/canvas`, {}, signal), refetchInterval: 8000, retry: false });
  const msgs = useMemo(() => [...(dq.data?.items || [])].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0)).map((m) => ({ ...m, id: `local-m${m.id}` })), [dq.data]); // id "local-" ẩn nút ghim/ review (chỉ có ở phòng kịch bản)
  const chips = [...msgs].reverse().find((m) => m.author?.role === "ai" && (m.chips || []).length)?.chips || [];
  const rows = useMemo(() => normCanvasRows(cq.data, lang), [cq.data, lang]);
  const inv = () => { qc.invalidateQueries({ queryKey: ["cls", "m", mid] }); qc.invalidateQueries({ queryKey: ["cls", "methods"] }); };
  useEffect(() => { const e = box.current; if (e) e.scrollTop = e.scrollHeight; }, [msgs.length, live?.text]);

  const send = useCallback(async (text) => {
    if (streaming || !String(text || "").trim()) return;
    const ac = new AbortController(); abort.current = ac; setStreaming(true); setErr(null);
    setLive({ user: { id: "local-u", seq: 1e12, kind: "text", author: { user_id: me.user_id, name: me.display_name || me.user_id, role: me.role }, text, created_at: new Date().toISOString() }, text: "", got: false });
    try {
      await streamMethodMessage(mid, text, {
        user: (e) => setLive((l) => l && { ...l, user: e.message }),
        delta: (e) => setLive((l) => l && { ...l, text: l.text + (e.text || ""), got: true }),
        turn: (e) => setLive((l) => l && { ...l, final: e.message }),
        error: (e) => setErr(e.detail || t("AI gặp lỗi, thử lại.", "The AI hit an error, retry.")),
      }, ac.signal);
    } catch (e) { setErr(e.message); setLive(null); setStreaming(false); return; }
    try { await qc.refetchQueries({ queryKey: ["cls", "m", mid, "room"] }); } catch { /* bỏ */ }
    setLive(null); setStreaming(false); inv();
  }, [mid, streaming, me, t]); // eslint-disable-line react-hooks/exhaustive-deps
  const stop = () => { abort.current?.abort(); setStreaming(false); setLive(null); inv(); };
  const ctx = useMemo(() => ({ lang, t, me, rid: vrid, isMaster }), [lang, t, me, vrid, isMaster]);
  const confirm = async (row, on) => { try { await mwrite("POST", `/methods/${enc(mid)}/canvas/${enc(row.key)}/confirm`, { confirmed: on }); qc.invalidateQueries({ queryKey: ["cls", "m", mid, "canvas"] }); } catch { send(`${t("Xác nhận mục", "Confirm row")} «${row.label}»`).catch(() => {}); } };
  const edit = async (row, text) => { try { await mwrite("POST", `/methods/${enc(mid)}/canvas/${enc(row.key)}/edit`, { text }); qc.invalidateQueries({ queryKey: ["cls", "m", mid, "canvas"] }); } catch { await send(`${t("Sửa mục", "Correction for")} «${row.label}»: ${text}`); } };
  const model = useMemo(() => ({ confirm, edit, revert: () => {}, versions: [], error: null, serverCanvas: cq.isSuccess }), [cq.isSuccess, mid]); // eslint-disable-line react-hooks/exhaustive-deps
  const canvas = useMemo(() => ({ rows, clarity: { score: clarityOf(cq.data) ?? 0, next: cq.data?.clarity?.next_question || "" } }), [rows, cq.data]);
  const unavailable = dq.isError;
  const opts = chips.filter((c) => c && (c.text || c.label)).slice(0, 4);

  return (
    <ClassCtx.Provider value={ctx}>
      <div className="grid gap-2">
        <div className="flex gap-1 lg:hidden" role="tablist" aria-label={t("Phòng phương pháp", "Method room")}>
          {[["chat", t("Chat", "Chat")], ["canvas", t("Hồ sơ phương pháp", "Method profile")]].map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={`cm-tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}
        </div>
        <div className="cm-room">
          <div className={`cm-chat ${tab === "chat" ? "" : "max-lg:hidden"}`} aria-label={t("Chat phương pháp", "Method chat")}>
            <div className="cm-msgs" ref={box} role="log" aria-live="polite" aria-label={t("Hội thoại", "Conversation")}>
              {unavailable && <p className="m-2 text-[12.5px] text-muted" role="status">{dq.error?.status === 404 ? t("Phòng phương pháp chưa sẵn sàng trên máy chủ.", "The method room is not available on the server yet.") : dq.error?.message}</p>}
              {dq.isSuccess && !msgs.length && !live && (
                <div className="cr-start" role="note">
                  <h3 className="m-0 text-[14px] font-semibold">{t("Dạy AI cách các kịch bản phối hợp", "Teach the AI how the scenarios work together")}</h3>
                  <p className="m-0 text-[12.5px] text-muted">{t("Mỗi kịch bản có phòng riêng. Ở đây bàn về bức tranh chung: bối cảnh, thứ tự ưu tiên, vốn, dừng giao dịch. Bấm một gợi ý để bắt đầu:", "Each scenario has its own room. Here we cover the big picture: context, priority, capital, stop rules. Pick a prompt to start:")}</p>
                  <ul className="m-0 p-0 list-none grid gap-1 w-full">{SEED.map(([vi, en], i) => <li key={i}><button type="button" className="cr-chip cr-chip-wide" style={{ minHeight: 40 }} onClick={() => comp.current?.insert(lang === "en" ? en : vi)}>{lang === "en" ? en : vi}</button></li>)}</ul>
                </div>
              )}
              {msgs.map((m) => <Bubble key={m.id} msg={m} mine={m.author?.user_id === me.user_id} onSend={send} onFill={(s) => comp.current?.insert(s)} onChanged={inv} />)}
              {live && (<>
                {live.user && !msgs.some((m) => m.id === `local-m${live.user.id}`) && <Bubble msg={live.user} mine />}
                {live.final ? <Bubble msg={live.final} onSend={send} onChanged={inv} /> : <article className="cr-msg ai" aria-busy="true"><header className="cr-msg-h"><b>{t("AI học trò", "AI student")}</b><Chip>AI</Chip></header>{live.got ? <Markdown text={live.text} /> : <span className="cr-typing" role="status" aria-label={t("AI đang trả lời", "AI is replying")}><i /><i /><i /></span>}</article>}
              </>)}
            </div>
            <div>
              {err && <p role="alert" className="m-0 px-3 py-1 text-[12.5px] text-down">{err}</p>}
              {opts.length > 0 && !streaming && (
                <div className="cm-opts" role="group" aria-label={t("Gợi ý cho bạn", "Suggestions for you")}>
                  {opts.map((c, i) => <button key={i} type="button" className="cr-chip" style={{ minHeight: 40 }} onClick={() => send(c.text || c.command || c.label).catch(() => {})}>{c.label || c.text}</button>)}
                </div>
              )}
              <Composer ref={comp} chips={[]} streaming={streaming} ask disabled={unavailable} onSend={send} onStop={stop} onUpload={async () => {}} onChart={() => {}} />
            </div>
          </div>
          <div className={tab === "canvas" ? "" : "max-lg:hidden"}>
            <ProfileCanvas title={t("Hồ sơ phương pháp", "Method profile")} lang={lang} rid={null} canvas={canvas} model={model} onSend={send} onFill={(s) => comp.current?.insert(s)} />
          </div>
        </div>
        <p className="m-0 text-[11.5px] text-muted">{t("Chỉ nghiên cứu/paper: không có lệnh đặt lệnh. AI có thể sai; điều quan trọng cần bạn xác nhận.", "Research/paper only: no order path. The AI can be wrong; important items need your confirmation.")}</p>
      </div>
    </ClassCtx.Provider>
  );
}
