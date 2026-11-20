// Application shell: session, hash router, sidebar/topbar, language and theme switching.
import { api, auth } from "./api.js";
import { lang, LANGS, setLang, t } from "./i18n.js";
import { esc, icons, toast } from "./ui.js";
import * as views from "./views.js";

const CURRENT_KEY = "dfd.current";
const NAV = [
  { route: "upload", icon: "upload", num: 2 },
  { route: "scan", icon: "scan", num: 3, scoped: true },
  { route: "result", icon: "result", num: 4, scoped: true },
  { route: "regions", icon: "regions", num: 5, scoped: true },
  { route: "report", icon: "report", num: 6, scoped: true },
  { route: "history", icon: "history", num: 7 },
];
const ROUTES = new Set(["login", ...NAV.map((item) => item.route)]);

const app = document.getElementById("app");
const state = { meta: null, current: localStorage.getItem(CURRENT_KEY), currentName: null };
let cleanup = null;
let generation = 0;

function parseRoute() {
  const [name, id] = location.hash.replace(/^#\/?/, "").split("/");
  return { name: ROUTES.has(name) ? name : "", id: id || null };
}

function navigate(path) {
  const target = `#/${path}`;
  if (location.hash === target) render(); else location.hash = target;
}

function setCurrent(scan) {
  state.current = scan?.id ?? null;
  state.currentName = scan?.filename ?? null;
  if (scan) localStorage.setItem(CURRENT_KEY, scan.id); else localStorage.removeItem(CURRENT_KEY);
  const crumb = document.querySelector("[data-crumb-file]");
  if (crumb) crumb.innerHTML = scan ? `<span>/</span><b>${esc(scan.filename)}</b>` : "";
}

// Language switch and theme toggle, shared by the login screen and the top bar.
function controls() {
  const theme = document.documentElement.dataset.theme;
  return `
    <div class="seg" role="group" aria-label="${esc(t("lang.label"))}">
      ${LANGS.map((code) => `<button data-lang="${code}" aria-pressed="${code === lang()}">${code.toUpperCase()}</button>`).join("")}
    </div>
    <button class="btn btn-icon btn-ghost" data-theme-toggle title="${esc(t("theme.toggle"))}" aria-label="${esc(t("theme.toggle"))}">${theme === "dark" ? icons.sun : icons.moon}</button>`;
}

function bindControls(root) {
  root.querySelectorAll("[data-lang]").forEach((button) => button.addEventListener("click", () => {
    setLang(button.dataset.lang);
    render();
  }));
  root.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("dfd.theme", next);
    render();
  });
}

function logout() {
  auth.clear();
  setCurrent(null);
  navigate("login");
}

function shell(route) {
  const user = auth.user;
  const link = (item) => {
    const href = item.scoped && state.current ? `#/${item.route}/${state.current}` : `#/${item.route}`;
    return `<a href="${href}" class="${item.route === route ? "active" : ""}" ${item.route === route ? 'aria-current="page"' : ""}>${icons[item.icon]}<span class="lbl">${esc(t(`nav.${item.route}`))}</span><span class="num">${item.num}</span></a>`;
  };
  return `
    <div class="shell">
      <aside class="sidebar">
        <a class="brand" href="#/upload">${icons.logo}<div><div class="brand-name">${esc(t("app.name"))}</div><div class="brand-tag">${esc(t("app.tagline"))}</div></div></a>
        <nav class="nav" aria-label="Menu">${NAV.map(link).join("")}</nav>
        <div class="sidebar-foot">
          <div class="user-chip">
            <span class="avatar">${esc(user.username.slice(0, 1).toUpperCase())}</span>
            <span class="who"><b>${esc(user.username)}</b><span>${esc(user.role)}</span></span>
            <button class="btn btn-icon btn-ghost" data-logout title="${esc(t("nav.logout"))}" aria-label="${esc(t("nav.logout"))}">${icons.logout}</button>
          </div>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <div class="crumb"><b>${esc(t(`nav.${route}`))}</b><span data-crumb-file></span></div>
          <div class="topbar-actions">
            ${controls()}
            <button class="btn btn-icon btn-ghost mobile-logout" data-logout title="${esc(t("nav.logout"))}" aria-label="${esc(t("nav.logout"))}">${icons.logout}</button>
          </div>
        </header>
        <main class="content"><div class="view" id="view"></div></main>
      </div>
    </div>`;
}

async function render() {
  generation += 1;
  const mine = generation;
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }

  let { name, id } = parseRoute();
  if (!auth.token) name = "login";
  else if (!name || name === "login") { navigate("upload"); return; }
  if (name === "login" && location.hash !== "#/login") history.replaceState(null, "", "#/login");

  const context = {
    id,
    state,
    navigate,
    setCurrent,
    controls,
    bindControls,
    alive: () => mine === generation,
  };
  document.title = `${t(name === "login" ? "login.title" : `nav.${name}`)} · ${t("app.name")}`;

  if (name === "login") {
    context.root = app;
    views.login(context);
    return;
  }
  app.innerHTML = shell(name);
  bindControls(app);
  app.querySelectorAll("[data-logout]").forEach((button) => button.addEventListener("click", logout));
  context.root = app.querySelector("#view");
  try {
    const result = await views[name](context);
    if (mine === generation) cleanup = typeof result === "function" ? result : null;
    else if (typeof result === "function") result();
  } catch (error) {
    console.error(error);
    toast(t("err.error"), "error");
  }
}

async function boot() {
  auth.onUnauthorized(() => { setCurrent(null); navigate("login"); });
  try { state.meta = await api.meta(); } catch { toast(t("err.network"), "error"); }
  if (auth.token) {
    try { await api.me(); } catch { /* an expired session is handled by onUnauthorized */ }
  }
  window.addEventListener("hashchange", render);
  render();
}

boot();
