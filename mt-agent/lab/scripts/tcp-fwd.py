#!/usr/bin/env python3
"""tcp-fwd.py <listen_host> <listen_port> <dest_host> <dest_port>: forwarder TCP toi gian (asyncio).
Ly do: WebRequest cua MT4 chi dung cong 80/443; bridge nghe :8000 trong mang tradingsys_internal."""
import asyncio, sys
lh, lp, dh, dp = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
async def pipe(r, w):
    try:
        while (d := await r.read(65536)):
            w.write(d); await w.drain()
    except Exception:
        pass
    finally:
        try: w.close()
        except Exception: pass
async def handle(cr, cw):
    try:
        ur, uw = await asyncio.open_connection(dh, dp)
    except Exception:
        cw.close(); return
    await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
async def main():
    srv = await asyncio.start_server(handle, lh, lp)
    async with srv:
        await srv.serve_forever()
asyncio.run(main())
