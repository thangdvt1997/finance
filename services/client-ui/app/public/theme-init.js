// Chạy trước khi vẽ để tránh nháy sáng/tối (CSP không cho inline script).
(function () {
  try {
    var t = localStorage.getItem("tc-theme");
    if (t !== "light" && t !== "dark") t = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.dataset.theme = t;
  } catch (e) {}
})();
