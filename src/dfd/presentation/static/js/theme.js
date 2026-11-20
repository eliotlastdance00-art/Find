// Runs before first paint so the saved theme is applied without a flash.
(function () {
  var saved = localStorage.getItem("dfd.theme");
  var theme = saved === "light" || saved === "dark"
    ? saved
    : (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.dataset.theme = theme;
})();
