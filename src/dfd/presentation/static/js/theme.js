// Runs before first paint so the saved theme is applied without a flash.
(function () {
  var saved = localStorage.getItem("dfd.theme");
  // Dark unless chosen otherwise: the interface is designed as a night scene. "auto" follows the device.
  var theme = saved === "light" || saved === "dark"
    ? saved
    : saved === "auto" && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
})();
