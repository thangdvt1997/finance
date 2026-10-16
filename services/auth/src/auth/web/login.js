"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var msg = $("msg");
  function show(t, ok) { msg.textContent = t; msg.hidden = !t; msg.className = "msg" + (ok ? " ok" : ""); }
  function forms(name) {
    ["f-login", "f-change", "f-pair"].forEach(function (f) { $(f).hidden = f !== name; });
    show("");
  }
  function nextUrl(role) {
    var n = new URLSearchParams(location.search).get("next") || "";
    // chỉ cho phép đường dẫn tương đối cùng origin (chống open-redirect)
    // cấm ký tự điều khiển: tab/CR/LF bị trình duyệt BỎ khi phân tích URL (tab giữa hai dấu / thành //evil.com) -> open-redirect; cấm cả dấu gạch ngược
    if (n && n.charAt(0) === "/" && n.charAt(1) !== "/" && n.charAt(1) !== "\\" && !/[\u0000-\u001f\u007f\\]/.test(n) && n.indexOf("/auth/login") !== 0) return n;
    return role === "master" ? "/" : "/c/";
  }
  function post(url, body) {
    return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, body: j }; }); });
  }
  function detail(r) {
    var d = r.body && r.body.detail;
    if (typeof d === "string") return d;
    return r.status === 429 ? "Quá nhiều lần thử. Vui lòng thử lại sau." : "Có lỗi xảy ra (" + r.status + ")";
  }
  var platform = $("platform");
  function sync() {
    var m = platform.value === "master";
    $("login-label").textContent = m ? "Tên đăng nhập" : "Số tài khoản";
    $("login").inputMode = m ? "text" : "numeric";
    $("server-row").hidden = m;
  }
  platform.addEventListener("change", sync); sync();
  $("to-pair").addEventListener("click", function (e) { e.preventDefault(); forms("f-pair"); });
  $("to-login").addEventListener("click", function (e) { e.preventDefault(); forms("f-login"); });

  var mustChange = false;
  function done(me) {
    if (me.must_change_password) { mustChange = true; $("cur").value = $("secret").value; forms("f-change"); show("Cần đổi mật khẩu lần đầu."); return; }
    location.replace(nextUrl(me.role));
  }
  $("f-login").addEventListener("submit", function (e) {
    e.preventDefault();
    var body = { platform: platform.value, login: $("login").value.trim(), secret: $("secret").value };
    if (platform.value !== "master" && $("server").value.trim()) body.server = $("server").value.trim();
    if (!$("totp-row").hidden && $("totp").value.trim()) body.totp = $("totp").value.trim();
    $("btn-login").disabled = true;
    post("/auth/login", body).then(function (r) {
      $("btn-login").disabled = false;
      if (r.status === 200) { done(r.body); return; }
      if (r.body && r.body.totp_required) { $("totp-row").hidden = false; $("totp").focus(); show("Nhập mã xác thực 2 bước."); return; }
      show(detail(r));
    }).catch(function () { $("btn-login").disabled = false; show("Không kết nối được máy chủ."); });
  });
  $("f-change").addEventListener("submit", function (e) {
    e.preventDefault();
    if ($("new1").value !== $("new2").value) { show("Hai mật khẩu mới không khớp."); return; }
    post("/auth/change-password", { current_password: $("cur").value, new_password: $("new1").value }).then(function (r) {
      if (r.status !== 200) { show(detail(r)); return; }
      fetch("/auth/me", { credentials: "same-origin" }).then(function (x) { return x.json(); }).then(function (me) { location.replace(nextUrl(me.role)); });
    });
  });
  $("f-pair").addEventListener("submit", function (e) {
    e.preventDefault();
    if ($("p-new1").value !== $("p-new2").value) { show("Hai mật khẩu không khớp."); return; }
    post("/auth/pair", { platform: $("p-platform").value, login: $("p-login").value.trim(), pairing_code: $("p-code").value.trim(), new_password: $("p-new1").value })
      .then(function (r) {
        if (r.status !== 200) { show(detail(r)); return; }
        forms("f-login"); show("Ghép cặp thành công. Hãy đăng nhập bằng mật khẩu mới.", true);
        platform.value = $("p-platform").value; sync(); $("login").value = $("p-login").value;
      });
  });
  // đã có phiên hợp lệ -> chuyển thẳng
  fetch("/auth/me", { credentials: "same-origin" }).then(function (r) { return r.status === 200 ? r.json() : null; })
    .then(function (me) { if (me) done(me); }).catch(function () {});
})();
