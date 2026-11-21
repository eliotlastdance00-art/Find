// Application shell: session, hash router, sidebar/topbar, language and theme switching.
import { api, auth } from "./api.js";
import { mountWorld, playIntro, transit } from "./fx.js";
import { lang, LANG_NAMES, setLang, t } from "./i18n.js";
import { aboutDialog, accountMenu, closePopover, languageMenu, openPopover, signOutDialog, themeChoice } from "./menus.js";
import { reducedMotion, reveal } from "./motion.js";
import { esc, icons, toast } from "./ui.js";
import * as views from "./views.js";

const CURRENT_KEY = "dfd.current";
const RAIL_KEY = "dfd.rail";
const THEME_KEY = "dfd.theme";
const NAV = [
  { route: "upload", icon: "upload", num: 2 },
  { route: "scan", icon: "lens", num: 3, scoped: true },
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

const themeIcon = () => (document.documentElement.dataset.theme === "dark" ? icons.sun : icons.moon);
const systemTheme = () => (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");

// Language picker and theme toggle, shared by the sign-in scene and the top bar.
function controls() {
  return `
    <button class="lang-btn" data-lang-open aria-haspopup="menu" aria-expanded="false" aria-label="${esc(t("lang.label"))}: ${esc(LANG_NAMES[lang()])}">
      ${icons.globe}<span class="lang-btn-name">${esc(LANG_NAMES[lang()])}</span><span class="lang-btn-code">${lang().toUpperCase()}</span>${icons.chevron}
    </button>
    <button class="btn btn-icon btn-ghost theme-btn" data-theme-toggle title="${esc(t("theme.toggle"))}" aria-label="${esc(t("theme.toggle"))}">${themeIcon()}</button>`;
}

// Switches the colours; where the browser can, the new theme spreads from (x, y) like light
// from a lamp. `choice` is "light", "dark" or "auto" (follow the device).
function setTheme(choice, x = window.innerWidth / 2, y = 0) {
  localStorage.setItem(THEME_KEY, choice);
  const next = choice === "auto" ? systemTheme() : choice;
  const apply = () => {
    document.documentElement.dataset.theme = next;
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => { button.innerHTML = themeIcon(); });
    document.querySelectorAll("[data-set-theme]").forEach((button) => button.setAttribute("aria-checked", String(button.dataset.setTheme === choice)));
  };
  if (next === document.documentElement.dataset.theme || !document.startViewTransition || reducedMotion()) { apply(); return; }
  const reach = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  document.startViewTransition(apply).ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${reach}px at ${x}px ${y}px)`] },
      { duration: 560, easing: "cubic-bezier(.5, 0, .2, 1)", pseudoElement: "::view-transition-new(root)" },
    );
  }).catch(() => {});
}

function pickLanguage(code) {
  closePopover(false);
  if (code === lang()) return;
  setLang(code);
  shellStale = true;
  render();
}

function bindMenu(node) {
  if (!node) return;
  node.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.pickLang) pickLanguage(button.dataset.pickLang);
    else if (button.dataset.setTheme) setTheme(button.dataset.setTheme, event.clientX, event.clientY);
    else if ("about" in button.dataset) { closePopover(false); aboutDialog(state.meta); }
    else if ("signout" in button.dataset) { closePopover(false); logout(); }
  });
}

function bindControls(root) {
  root.querySelectorAll("[data-lang-open]").forEach((button) => button.addEventListener("click", () => {
    bindMenu(openPopover(button, languageMenu(), "pop-lang"));
  }));
  root.querySelectorAll("[data-theme-toggle]").forEach((button) => button.addEventListener("click", (event) => {
    const box = button.getBoundingClientRect();
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark",
      event.clientX || box.left + box.width / 2, event.clientY || box.top + box.height / 2);
  }));
}

function openAccount(button) {
  const rail = app.querySelector(".shell")?.dataset.rail === "1";
  button.dataset.popSide = rail && button.closest(".sidebar") ? "right" : "";
  const node = openPopover(button, accountMenu(auth.user, state.meta), "pop-account");
  if (!node) return;
  bindMenu(node);
  // Real numbers from the history, filled in when they arrive.
  api.stats().then((stats) => {
    node.querySelectorAll("[data-stat]").forEach((cell) => { cell.textContent = stats[cell.dataset.stat] ?? 0; });
  }).catch(() => {});
}

function setRail(collapsed) {
  const frame = app.querySelector(".shell");
  if (!frame) return;
  frame.dataset.rail = collapsed ? "1" : "0";
  localStorage.setItem(RAIL_KEY, collapsed ? "1" : "0");
  const toggle = frame.querySelector("[data-rail-toggle]");
  const label = t(collapsed ? "menu.expand" : "menu.collapse");
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", label);
  toggle.title = `${label} (Ctrl+B)`;
  closePopover(false);
}

async function logout() {
  const user = auth.user;
  if (!user || !(await signOutDialog(user))) return;
  await transit(
    { title: t("bye.title", { name: user.username }), sub: t("bye.sub"), x: window.innerWidth / 2, y: window.innerHeight / 2 },
    () => { auth.clear(); setCurrent(null); navigate("login"); },
  );
}

// After signing in: the curtain closes from the button, the application opens behind it.
function enter(user, origin) {
  const box = origin?.getBoundingClientRect();
  return transit(
    { title: t("welcome.title", { name: user.username }), sub: t("welcome.sub"),
      x: box ? box.left + box.width / 2 : window.innerWidth / 2, y: box ? box.top + box.height / 2 : window.innerHeight / 2 },
    () => navigate("upload"),
  );
}

function shell(route) {
  const user = auth.user;
  const initial = esc(user.username.slice(0, 1).toUpperCase());
  const models = Object.values(state.meta?.models ?? {});
  const ready = models.length > 0 && models.every((model) => model.available);
  const rail = localStorage.getItem(RAIL_KEY) === "1";
  const railLabel = esc(t(rail ? "menu.expand" : "menu.collapse"));
  const link = (item) => `<a href="${hrefOf(item)}" data-tip="${esc(t(`nav.${item.route}`))}">${icons[item.icon]}<span class="lbl">${esc(t(`nav.${item.route}`))}</span><span class="lbl-short">${esc(t(`nav.short.${item.route}`))}</span><span class="num">${item.num}</span></a>`;
  return `
    <div class="shell" data-rail="${rail ? "1" : "0"}">
      <aside class="sidebar">
        <a class="brand" href="#/upload">${icons.logo}<div class="brand-text"><div class="brand-name">${esc(t("app.name"))}</div><div class="brand-tag">${esc(t("app.tagline"))}</div></div></a>
        <button class="rail-toggle" data-rail-toggle aria-expanded="${!rail}" aria-label="${railLabel}" title="${railLabel} (Ctrl+B)">${icons.side}</button>
        <nav class="nav" aria-label="Menu" style="--count:${NAV.length}"><i class="nav-pill" aria-hidden="true"></i>${NAV.map(link).join("")}</nav>
        <div class="sidebar-foot">
          <div class="sys ${ready ? "is-ok" : "is-warn"}" data-tip="${esc(t(ready ? "sys.ready" : "sys.partial"))}"><i></i><span class="lbl">${esc(t(ready ? "sys.ready" : "sys.partial"))}</span><span class="sys-v">v${esc(state.meta?.version ?? "")}</span></div>
          <button class="user-chip" data-account aria-haspopup="menu" aria-expanded="false" aria-label="${esc(t("menu.account"))}: ${esc(user.username)}">
            <span class="avatar">${initial}</span>
            <span class="who"><b>${esc(user.username)}</b><span>${esc(t(`role.${user.role}`))}</span></span>
            ${icons.updown}
          </button>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <a class="topbar-brand" href="#/upload" aria-label="${esc(t("app.name"))}">${icons.logo}</a>
          <div class="crumb"><b data-crumb-title>${esc(t(`nav.${route}`))}</b><span data-crumb-file></span></div>
          <div class="topbar-actions">
            ${controls()}
            <button class="avatar avatar-btn" data-account aria-haspopup="menu" aria-expanded="false" aria-label="${esc(t("menu.account"))}: ${esc(user.username)}">${initial}</button>
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
    app.querySelectorAll("[data-account]").forEach((button) => button.addEventListener("click", () => openAccount(button)));
    app.querySelector("[data-rail-toggle]").addEventListener("click", () => setRail(app.querySelector(".shell").dataset.rail !== "1"));
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
    enter,
    alive: () => mine === generation,
  };
  document.title = `${t(name === "login" ? "login.title" : `nav.${name}`)} · ${t("app.name")}`;

  if (name === "login") {
    shellStale = true;
    closePopover(false);
    context.root = app;
    cleanup = views.login(context) ?? null;
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
  mountWorld();
  const intro = playIntro({ name: t("app.name"), tagline: t("app.tagline"), loading: t("intro.loading"), skip: t("intro.skip") });
  auth.onUnauthorized(() => { setCurrent(null); navigate("login"); });
  try { state.meta = await api.meta(); } catch { toast(t("err.network"), "error"); }
  intro?.step(t("intro.models"), 0.7);
  if (auth.token) {
    try { await api.me(); } catch { /* an expired session is handled by onUnauthorized */ }
  }
  // Ctrl/Cmd+B folds the side menu, as in most editors.
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "b" && app.querySelector(".shell")) {
      event.preventDefault();
      setRail(app.querySelector(".shell").dataset.rail !== "1");
    }
  });
  // "Auto" follows the device when it switches between day and night.
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { if (themeChoice() === "auto") setTheme("auto"); });
  window.addEventListener("hashchange", render);
  // Gauges, markers and counters are rendered empty; fill them whenever they enter the page.
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; reveal(app); });
  }).observe(app, { childList: true, subtree: true });
  render();
  await intro?.finish(t("intro.ready"));
}

boot();
