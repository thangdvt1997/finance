// Âm báo tạo bằng WebAudio (không tải file âm thanh). Chỉ phát sau thao tác người dùng (chính sách autoplay) -> ngữ cảnh được mở ở lần chạm đầu.
let ctx = null;
const mk = () => { try { const C = window.AudioContext || window.webkitAudioContext; return C ? new C() : null; } catch { return null; } };
const unlock = () => { ctx ||= mk(); if (ctx?.state === "suspended") ctx.resume().catch(() => {}); };
["pointerdown", "touchend", "click"].forEach((e) => addEventListener(e, unlock, { passive: true })); // chỉ cử chỉ chuột/chạm mới mở được AudioContext (tránh cảnh báo autoplay khi gõ phím)

const PAT = { info: [[660, 0.09]], warn: [[660, 0.1], [880, 0.12]], crit: [[880, 0.12], [660, 0.12], [880, 0.18]] };
export function beep(sev = "info", vol = 0.5) {
  ctx ||= mk();
  if (!ctx || ctx.state !== "running") return false;
  try {
    let t = ctx.currentTime + 0.01;
    for (const [f, d] of PAT[sev] || PAT.info) {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(Math.max(0.0002, 0.25 * vol), t + 0.015); g.gain.exponentialRampToValueAtTime(0.0001, t + d);
      o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + d + 0.02);
      t += d + 0.04;
    }
    return true;
  } catch { return false; }
}
export const soundReady = () => !!ctx && ctx.state === "running";
