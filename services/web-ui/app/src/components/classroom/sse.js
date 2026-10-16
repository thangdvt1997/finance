// Đọc luồng SSE qua fetch (POST, có CSRF qua apiWrite-token). onEvent({event,data}) với data đã JSON.parse nếu được.
export async function readSSE(res, onEvent, signal) {
  const rd = res.body.getReader(), dec = new TextDecoder(); let buf = "";
  for (;;) {
    if (signal?.aborted) { try { await rd.cancel(); } catch { /* bỏ */ } return; }
    const { value, done } = await rd.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let k;
    while ((k = buf.search(/\r?\n\r?\n/)) >= 0) {
      const raw = buf.slice(0, k); buf = buf.slice(k).replace(/^\r?\n\r?\n/, "");
      let ev = "message"; const data = [];
      for (const ln of raw.split(/\r?\n/)) { if (ln.startsWith("event:")) ev = ln.slice(6).trim(); else if (ln.startsWith("data:")) data.push(ln.slice(5).replace(/^ /, "")); }
      if (!data.length) continue;
      const txt = data.join("\n"); let d = txt; try { d = JSON.parse(txt); } catch { /* chuỗi thô */ }
      onEvent({ event: ev, data: d });
    }
  }
}
