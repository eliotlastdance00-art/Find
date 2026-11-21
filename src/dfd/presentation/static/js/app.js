// Application shell: session, hash router, sidebar/topbar, language and theme switching.
import { api, auth } from "./api.js";
import { lang, LANGS, setLang, t } from "./i18n.js";
import { reducedMotion, reveal } from "./motion.js";
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
let shellStale = true;   // the frame (menu, top bar) is rebuilt only when language or theme change
let lastIndex = -1;

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
  syncNav();
}

const hrefOf = (item) => (item.scoped && state.current ? `#/${item.route}/${state.current}` : `#/${item.route}`);

// Moves the highlight to the open screen and keeps the links pointing at the current file.
function syncNav(route) {
  const nav = app.querySelector(".nav");
  if (!nav) return;
  const active = route ?? nav.dataset.route;
  nav.dataset.route = active;
  nav.style.setProperty("--active", Math.max(0, NAV.findIndex((item) => item.route === active)));
  nav.querySelectorAll("a").forEach((link, i) => {
    const item = NAV[i];
    const on = item.route === active;
    link.setAttribute("href", hrefOf(item));
    link.classList.toggle("active", on);
    if (on) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
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
    shellStale = true;
    render();
  }));
  root.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("dfd.theme", next);
    shellStale = true;
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
  const link = (item) => `<a href="${hrefOf(item)}">${icons[item.icon]}<span class="lbl">${esc(t(`nav.${item.route}`))}</span><span class="lbl-short">${esc(t(`nav.short.${item.route}`))}</span><span class="num">${item.num}</span></a>`;
  return `
    <div class="shell">
      <aside class="sidebar">
        <a class="brand" href="#/upload">${icons.logo}<div><div class="brand-name">${esc(t("app.name"))}</div><div class="brand-tag">${esc(t("app.tagline"))}</div></div></a>
        <nav class="nav" aria-label="Menu" style="--count:${NAV.length}"><i class="nav-pill" aria-hidden="true"></i>${NAV.map(link).join("")}</nav>
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
          <div class="crumb"><b data-crumb-title>${esc(t(`nav.${route}`))}</b><span data-crumb-file></span></div>
          <div class="topbar-actions">
            ${controls()}
            <button class="btn btn-icon btn-ghost mobile-logout" data-logout title="${esc(t("nav.logout"))}" aria-label="${esc(t("nav.logout"))}">${icons.logout}</button>
          </div>
        </header>
        <main class="content"><div class="view" id="view"></div></main>
      </div>
    </div>`;
}

// Builds the frame once and afterwards only swaps the screen inside it, so the menu
// highlight can travel between items instead of being redrawn.
function mountShell(route) {
  let view = app.querySelector("#view");
  if (shellStale || !view) {
    app.innerHTML = shell(route);
    bindControls(app);
    app.querySelectorAll("[data-logout]").forEach((button) => button.addEventListener("click", logout));
    shellStale = false;
    lastIndex = -1;
    view = app.querySelector("#view");
    if (state.current && state.currentName) {
      app.querySelector("[data-crumb-file]").innerHTML = `<span>/</span><b>${esc(state.currentName)}</b>`;
    }
  }
  const index = NAV.findIndex((item) => item.route === route);
  // Screens further along the menu come in from the right, earlier ones from the left.
  view.style.setProperty("--dx", lastIndex < 0 || index === lastIndex ? "0px" : index > lastIndex ? "18px" : "-18px");
  if (index !== lastIndex && lastIndex >= 0) window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
  lastIndex = index;
  view.replaceChildren();
  app.querySelector("[data-crumb-title]").textContent = t(`nav.${route}`);
  syncNav(route);
  return view;
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
    shellStale = true;
    context.root = app;
    views.login(context);
    return;
  }
  context.root = mountShell(name);
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
  // Gauges, markers and counters are rendered empty; fill them whenever they enter the page.
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; reveal(app); });
  }).observe(app, { childList: true, subtree: true });
  render();
}

boot();
