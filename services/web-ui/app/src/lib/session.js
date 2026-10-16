// Phiên giao dịch theo giờ địa phương từng sàn (có DST) -> mở/đóng. Chỉ mang tính tham khảo (không tính ngày lễ).
const SESSIONS = [
  { id: "tokyo", name: "Tokyo", tz: "Asia/Tokyo", open: 9, close: 15 },
  { id: "london", name: "London", tz: "Europe/London", open: 8, close: 16.5 },
  { id: "ny", name: "New York", tz: "America/New_York", open: 9.5, close: 16 },
  { id: "hanoi", name: "Hà Nội", tz: "Asia/Ho_Chi_Minh", open: 9, close: 15, breaks: [[11.5, 13]] },
];
export function sessions(now = new Date()) {
  return SESSIONS.map((s) => {
    const p = Object.fromEntries(
      new Intl.DateTimeFormat("en-GB", { timeZone: s.tz, hour12: false, weekday: "short", hour: "2-digit", minute: "2-digit" })
        .formatToParts(now)
        .map((x) => [x.type, x.value]),
    );
    const h = (Number(p.hour) % 24) + Number(p.minute) / 60;
    const weekend = p.weekday === "Sat" || p.weekday === "Sun";
    let open = !weekend && h >= s.open && h < s.close;
    if (open && s.breaks?.some(([a, b]) => h >= a && h < b)) open = false;
    return { ...s, clock: `${p.hour}:${p.minute}`, open, weekend };
  });
}
