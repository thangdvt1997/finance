import { useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, EyeOff, FileDown, Loader2, Send, Undo2 } from "lucide-react";
import { Dialog } from "../../dialog";
import { toast } from "../../../ux/bus";
import { Banner, GBtn, Pill, PRIMARY, ago, fmtDTfull } from "../bits";
import { KIND_VN, dmy, fileHref, kb } from "./reportsApi";

/** Bảng báo cáo của một tài khoản + phát hành/thu hồi (có xác nhận) + xem HTML/PDF (mở tab mới: iframe bị CSP chặn). */
export default function ReportList({ items, accountId, release }) {
  const [ask, setAsk] = useState(null);   // {it, to}
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState("");
  const k = (it) => `${it.kind}:${it.period}`;
  const doRelease = async () => {
    const { it, to } = ask;
    setBusy(k(it)); setErr(null);
    try {
      await release.mutateAsync({ account_id: accountId, kind: it.kind, period: it.period, released: to });
      toast({ tone: "ok", title: to ? "Đã phát hành cho khách" : "Đã thu hồi — khách không còn thấy", body: `Báo cáo ${KIND_VN[it.kind].toLowerCase()} ${dmy(it.period)}` });
      setAsk(null);
    } catch (e) { setErr(e); } finally { setBusy(""); }
  };
  const close = () => { if (!busy) { setAsk(null); setErr(null); } };
  return (
    <>
      <div className="fl-tablewrap relative">
        <table className="fl-tbl">
          <caption className="fl-sr">Báo cáo đã tạo của tài khoản {accountId}</caption>
          <thead><tr><th scope="col">Loại · Kỳ</th><th scope="col">Tạo lúc</th><th scope="col">Với khách</th><th scope="col">Dữ liệu</th><th scope="col"><span className="fl-sr">Thao tác</span></th></tr></thead>
          <tbody>
            {items.map((it) => {
              const miss = it.sections_fail || [];
              const rel = !!it.released;
              const b = busy === k(it);
              return (
                <tr key={k(it)} style={{ cursor: "default" }}>
                  <td className="whitespace-nowrap"><b>{KIND_VN[it.kind] || it.kind}</b> <span className="num text-muted">· {dmy(it.period)}</span></td>
                  <td className="whitespace-nowrap" title={fmtDTfull(it.generated_at)}><span className="num">{ago(it.generated_at)}</span></td>
                  <td>{rel ? <Pill tone="ok" icon={CheckCircle2} title={it.released_at ? `Phát hành ${fmtDTfull(it.released_at)}` : undefined}>Đã phát hành cho khách</Pill> : <Pill tone="mute" icon={EyeOff}>Nháp — khách chưa thấy</Pill>}</td>
                  <td>{it.status === "ok" ? <Pill tone="ok" icon={CheckCircle2}>Đầy đủ</Pill> : <Pill tone="warn" icon={AlertTriangle} title={miss.join(", ")}>Thiếu {miss.length || "một số"} mục{!it.has_pdf && !it.pdf_bytes ? " · chưa có PDF" : ""}</Pill>}</td>
                  <td>
                    <div className="flex flex-wrap gap-1.5 justify-end min-w-[15rem]">
                      <a className="btn no-underline" href={fileHref(it, "html")} target="_blank" rel="noopener noreferrer"><ExternalLink size={13} aria-hidden="true" />Xem HTML<span className="fl-sr"> (tab mới)</span></a>
                      {(it.has_pdf || it.pdf_bytes > 0) && <a className="btn no-underline" href={fileHref(it, "pdf")} target="_blank" rel="noopener noreferrer"><FileDown size={13} aria-hidden="true" />PDF {it.pdf_bytes ? <span className="text-muted">{kb(it.pdf_bytes)}</span> : null}</a>}
                      {rel
                        ? <GBtn master perm="report.read" onClick={() => setAsk({ it, to: false })} disabled={b}>{b ? <Loader2 size={13} className="animate-spin" aria-hidden="true" /> : <Undo2 size={13} aria-hidden="true" />}Thu hồi</GBtn>
                        : <GBtn master perm="report.read" className={PRIMARY} onClick={() => setAsk({ it, to: true })} disabled={b}>{b ? <Loader2 size={13} className="animate-spin" aria-hidden="true" /> : <Send size={13} aria-hidden="true" />}Phát hành</GBtn>}
                    </div>
                  </td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
      <Dialog open={!!ask} onClose={close} title={ask?.to ? "Phát hành báo cáo cho khách?" : "Thu hồi báo cáo?"}
        footer={<><button type="button" className="btn" onClick={close} disabled={!!busy}>Huỷ</button>
          <button type="button" className={`btn ${ask?.to ? PRIMARY : ""}`} onClick={doRelease} disabled={!!busy}>{busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : null}{ask?.to ? "Phát hành" : "Thu hồi"}</button></>}>
        <div className="grid gap-3 p-3 text-[12.5px]">
          {ask && <p className="m-0">Báo cáo <b>{KIND_VN[ask.it.kind].toLowerCase()}</b> kỳ <b className="num">{dmy(ask.it.period)}</b> của <b className="num">{accountId}</b>.</p>}
          {ask?.to ? <Banner tone="warn" title="Khách sẽ thấy báo cáo này ngay">Hãy chắc chắn bạn đã mở xem bản HTML/PDF. Có thể thu hồi bất cứ lúc nào.</Banner>
            : <Banner tone="info" title="Khách sẽ không còn thấy báo cáo này">Báo cáo quay về trạng thái nháp; khách đã tải về trước đó vẫn giữ bản của họ.</Banner>}
          {err && <Banner tone="bad" title={err.code === "unavailable" ? "Chưa khả dụng" : "Không thực hiện được"}>{err.code === "unavailable" ? "Máy chủ chưa mở thao tác phát hành." : err.message}</Banner>}
        </div>
      </Dialog>
    </>
  );
}
