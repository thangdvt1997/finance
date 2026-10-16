// Chạy trước khi vẽ để tránh nháy sáng/tối và nháy màu nhấn/cỡ chữ. File riêng vì CSP không cho inline script.
(function () {
  try {
    var el = document.documentElement, d = el.dataset;
    var u = null;
    try { u = JSON.parse(localStorage.getItem("ts-ux") || "null"); } catch (e) {}
    var t = localStorage.getItem("ts-theme");
    if (u && u.theme === "auto") t = window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    else if (u && (u.theme === "light" || u.theme === "dark")) t = u.theme;
    if (t !== "light" && t !== "dark") t = "dark"; // mặc định tối (kiểu terminal); người dùng đổi trong Cài đặt, lựa chọn được nhớ
    d.theme = t;
    if (u) {
      if (u.accent) d.accent = u.accent;
      if (u.density) d.density = u.density;
      if (u.fontScale) d.fs = String(u.fontScale);
      if (u.updown) d.updown = u.updown;
      if (u.contrast) d.contrast = u.contrast;
      if (u.motion) d.motion = u.motion;
    }
  } catch (e) {}
})();
