// Pop-up menus and the two dialogs opened from them (about the system, signing out).
import { lang, LANG_NAMES, LANGS, t } from "./i18n.js";
import { esc, icons } from "./ui.js";

let current = null;

export function closePopover(refocus = true) {
  if (!current) return;
  const { node, anchor, dispose } = current;
  current = null;
  dispose();
  anchor.setAttribute("aria-expanded", "false");
  if (refocus && anchor.isConnected) anchor.focus({ preventScroll: true });
  node.classList.add("closing");
  setTimeout(() => node.remove(), 150);
}

function place(node, anchor) {
  const box = anchor.getBoundingClientRect();
  const width = node.offsetWidth;
  const height = node.offsetHeight;
  const gap = 10;
  let left;
  let top;
  let origin;
  if (anchor.dataset.popSide === "right") {
    left = box.right + gap;
    top = box.bottom - height;
    origin = "left bottom";
  } else {
    const up = box.top > window.innerHeight - box.bottom;
    const fromRight = box.left + box.width / 2 > window.innerWidth / 2;
    top = up ? box.top - gap - height : box.bottom + gap;
    left = fromRight ? box.right - width : box.left;
    origin = `${fromRight ? "right" : "left"} ${up ? "bottom" : "top"}`;
  }
  node.style.left = `${Math.max(8, Math.min(left, window.innerWidth - width - 8))}px`;
  node.style.top = `${Math.max(8, Math.min(top, window.innerHeight - height - 8))}px`;
  node.style.transformOrigin = origin;
}

// Opens `html` as a menu attached to `anchor`. Clicking the anchor again closes it.
export function openPopover(anchor, html, className = "") {
  if (current?.anchor === anchor) { closePopover(); return null; }
  closePopover(false);
  const node = document.createElement("div");
  node.className = `pop ${className}`;
  node.setAttribute("role", "menu");
  node.innerHTML = html;
  document.body.append(node);
  place(node, anchor);
  anchor.setAttribute("aria-expanded", "true");

  const items = () => [...node.querySelectorAll("button:not(:disabled)")];
  const onDown = (event) => { if (!node.contains(event.target) && !anchor.contains(event.target)) closePopover(false); };
  const onKey = (event) => {
    if (event.key === "Escape") { event.preventDefault(); closePopover(); return; }
    if (event.key === "Tab") { closePopover(false); return; }
    const move = { ArrowDown: 1, ArrowUp: -1, Home: "first", End: "last" }[event.key];
    if (!move) return;
    event.preventDefault();
    const list = items();
    const at = list.indexOf(document.activeElement);
    const next = move === "first" ? 0 : move === "last" ? list.length - 1 : (at + move + list.length) % list.length;
    list[next]?.focus();
  };
  const away = () => closePopover(false);
  document.addEventListener("pointerdown", onDown, true);
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("resize", away);
  window.addEventListener("hashchange", away);
  current = {
    node,
    anchor,
    dispose() {
      document.removeEventListener("pointerdown", onDown, true);
      document.removeEventListener("keydown", onKey, true);
      window.removeEventListener("resize", away);
      window.removeEventListener("hashchange", away);
    },
  };
  (node.querySelector('[aria-checked="true"]') ?? items()[0])?.focus({ preventScroll: true });
  return node;
}

const langRows = () => LANGS.map((code, i) => `
  <button class="pop-item" role="menuitemradio" aria-checked="${code === lang()}" data-pick-lang="${code}" lang="${code}" style="--i:${i}">
    <span class="lang-code">${code.toUpperCase()}</span><span class="grow">${esc(LANG_NAMES[code])}</span>${icons.check}
  </button>`).join("");

export const languageMenu = () => `<div class="pop-label">${esc(t("lang.label"))}</div>${langRows()}`;

export const themeChoice = () => localStorage.getItem("dfd.theme") ?? "dark";

export function accountMenu(user, meta) {
  const choice = themeChoice();
  const themes = [["light", "sun"], ["dark", "moon"], ["auto", "monitor"]];
  return `
    <div class="acct-head">
      <span class="avatar avatar-lg">${esc(user.username.slice(0, 1).toUpperCase())}</span>
      <div class="grow"><b>${esc(user.username)}</b><span class="role">${esc(t(`role.${user.role}`))}</span></div>
    </div>
    <div class="acct-stats" data-acct-stats>
      ${["total", "real", "suspicious", "fake"].map((key) => `<div class="tone-${key}"><b data-stat="${key}">–</b><span>${esc(t(key === "total" ? "acct.total" : `verdict.${key}`))}</span></div>`).join("")}
    </div>
    <div class="pop-label">${esc(t("theme.label"))}</div>
    <div class="theme-seg" role="radiogroup" aria-label="${esc(t("theme.label"))}">
      ${themes.map(([name, icon]) => `<button role="radio" aria-checked="${name === choice}" data-set-theme="${name}">${icons[icon]}<span>${esc(t(`theme.${name}`))}</span></button>`).join("")}
    </div>
    <div class="pop-label">${esc(t("lang.label"))}</div>
    ${langRows()}
    <div class="pop-sep"></div>
    <button class="pop-item" role="menuitem" data-about>${icons.info}<span class="grow">${esc(t("menu.about"))}</span><span class="pop-hint">v${esc(meta?.version ?? "")}</span></button>
    <button class="pop-item danger" role="menuitem" data-signout>${icons.logout}<span class="grow">${esc(t("nav.logout"))}</span></button>`;
}

function dialog(className, html) {
  const node = document.createElement("dialog");
  node.className = `dialog ${className}`;
  node.innerHTML = html;
  node.addEventListener("click", (event) => {
    const value = event.target.closest("button[value]")?.value;
    if (value) node.close(value);
    else if (event.target === node) node.close("cancel");   // a click on the backdrop
  });
  document.body.append(node);
  node.showModal();
  return new Promise((resolve) => node.addEventListener("close", () => { resolve(node.returnValue); node.remove(); }));
}

// What is installed: version, the two models with their real state, the upload limits.
export function aboutDialog(meta) {
  const models = meta?.models ?? {};
  const row = (kind, icon) => {
    const model = models[kind] ?? {};
    const state = !model.available ? "missing" : model.provisional ? "provisional" : "ready";
    return `
      <div class="about-model is-${state}">
        <span class="file-ico">${icons[icon]}</span>
        <div class="grow"><b>${esc(t(`about.${kind}`))}</b><span>${esc(model.available ? `${model.name} ${model.version}` : "—")}</span></div>
        <span class="about-state"><i></i>${esc(t(`about.${state}`))}</span>
      </div>`;
  };
  const limits = meta?.limits ?? {};
  return dialog("about", `
    <div class="about-top">${icons.logo}<div><h2>${esc(t("app.name"))}</h2><p class="muted">${esc(t("app.tagline"))}</p></div></div>
    <dl class="facts"><div><dt>${esc(t("about.version"))}</dt><dd class="mono">${esc(meta?.version ?? "—")}</dd></div></dl>
    <div class="pop-label">${esc(t("about.models"))}</div>
    ${row("visual", "regions")}${row("audio", "audio")}
    <div class="pop-label">${esc(t("about.limits"))}</div>
    <p class="muted">${esc(t("about.limit.text", { mb: limits.max_upload_mb ?? "—", min: Math.round((limits.max_duration_s ?? 0) / 60) || "—" }))}</p>
    <div class="dialog-actions"><button class="btn btn-primary" value="ok" autofocus>${esc(t("common.close"))}</button></div>`);
}

// Resolves to true when the user really wants to leave.
export async function signOutDialog(user) {
  const answer = await dialog("signout", `
    <div class="signout-art"><span class="avatar avatar-lg">${esc(user.username.slice(0, 1).toUpperCase())}</span><i>${icons.logout}</i></div>
    <h2>${esc(t("logout.confirm"))}</h2>
    <p class="muted">${esc(t("logout.sub"))}</p>
    <div class="dialog-actions">
      <button class="btn" value="cancel" autofocus>${esc(t("logout.stay"))}</button>
      <button class="btn btn-danger" value="ok">${icons.logout}${esc(t("nav.logout"))}</button>
    </div>`);
  return answer === "ok";
}
