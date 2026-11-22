// Small rendering helpers shared by all views. Every dynamic string goes through esc().
import { lang, locale, t } from "./i18n.js";
import { LOGO_SHAPE, LOGO_VIEWBOX } from "./logo.js";

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ESCAPES[ch]);

const path = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const icons = {
  logo: `<svg class="logo-mark" viewBox="${LOGO_VIEWBOX}" fill="currentColor" aria-hidden="true">${LOGO_SHAPE}</svg>`,
  upload: path('<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>'),
  scan: path('<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M4 12h16"/>'),
  result: path('<path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 12 19 5"/><circle cx="12" cy="12" r="1.5"/>'),
  regions: path('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="12" cy="11" r="3.2"/><path d="M7 18c1-2.4 2.8-3.5 5-3.5s4 1.1 5 3.5"/>'),
  report: path('<path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>'),
  history: path('<path d="M3.5 12a8.5 8.5 0 1 0 2.600-6.100L3.5 8.5"/><path d="M3.5 4v4.5H8M12 7.5V12l3 2"/>'),
  image: path('<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5"/>'),
  video: path('<rect x="3.5" y="5.5" width="12.5" height="13" rx="2.5"/><path d="m16 10.5 4.5-2.5v8L16 13.5"/>'),
  audio: path('<path d="M5 10v4M9 6v12M13 9v6M17 4v16M21 10v4"/>'),
  sun: path('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.300 5.300l1.400 1.400M17.300 17.300l1.400 1.400M5.300 18.7l1.400-1.400M17.300 6.700l1.400-1.400"/>'),
  moon: path('<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z"/>'),
  logout: path('<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9"/>'),
  check: path('<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
  alert: path('<path d="M12 4 2.8 19.5h18.400z"/><path d="M12 10v4.5M12 17.200v.1"/>'),
  x: path('<path d="M6 6l12 12M18 6 6 18"/>'),
  question: path('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.300c-.7.400-1 1-1 1.700M12 16.800v.1"/>'),
  download: path('<path d="M12 4v12m0 0-4.5-4.5M12 16l4.5-4.5"/><path d="M4 19.5h16"/>'),
  external: path('<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>'),
  trash: path('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>'),
  copy: path('<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M5.5 15.5h-.5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5h9A1.5 1.5 0 0 1 15.5 5v.5"/>'),
  arrow: path('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  search: path('<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.200-4.200"/>'),
  plus: path('<path d="M12 5v14M5 12h14"/>'),
  info: path('<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5v.1"/>'),
  globe: path('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.600 2.500 3.900 5.500 3.900 9s-1.300 6.500-3.900 9c-2.600-2.500-3.900-5.500-3.900-9S9.400 5.500 12 3z"/>'),
  chevron: path('<path d="m7 10 5 5 5-5"/>'),
  updown: path('<path d="m8 9.500 4-4 4 4M8 14.500l4 4 4-4"/>'),
  side: path('<path d="m14 7-5 5 5 5"/>'),
  monitor: path('<rect x="3.500" y="4.500" width="17" height="12" rx="2.500"/><path d="M9 20h6M12 16.500V20"/>'),
  folder: path('<path d="M3.500 7.500a2 2 0 0 1 2-2h4l2 2.500h7a2 2 0 0 1 2 2v7.500a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>'),
  lens: path('<circle cx="10.500" cy="10.500" r="6"/><path d="m15 15 5.500 5.500"/>'),
  pin: path('<path d="M12 21s6.500-5.600 6.500-10.500a6.500 6.500 0 0 0-13 0C5.500 15.400 12 21 12 21z"/><circle cx="12" cy="10.500" r="2.300"/>'),
  seal: path('<path d="M9 13.500V11a3 3 0 1 1 6 0v2.500"/><path d="M6 13.500h12v3H6zM5 20h14"/>'),
};

export const VERDICT_ICON = { real: "check", suspicious: "alert", fake: "x", inconclusive: "question" };
export const typeIcon = (type) => icons[type] ?? icons.report;

export function formatBytes(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${unit === 0 ? value : value.toFixed(1)} ${units[unit]}`;
}

export function formatDuration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} ${t("common.seconds")}`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
}

const pad = (n) => String(n).padStart(2, "0");
export function formatDate(iso) {
  const date = new Date(iso);
  // Browsers ship no Turkmen locale data, so that format is written out by hand.
  if (lang() === "tk") {
    return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  return new Intl.DateTimeFormat(locale(), { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export const pct = (value, digits = 1) => (value == null ? "—" : `${(value * 100).toFixed(digits)}%`);

export function zoneOf(prob, realMax, fakeMin) {
  if (prob >= fakeMin) return "fake";
  if (prob <= realMax) return "real";
  return "suspicious";
}

export function verdictBadge(verdict, large = false) {
  if (!verdict) return "";
  return `<span class="badge badge-${esc(verdict)}${large ? " badge-lg" : ""}">${icons[VERDICT_ICON[verdict]]}<span>${esc(t(`verdict.${verdict}`))}</span></span>`;
}

// Semi-circular gauge. `prob` may be null (inconclusive). It is drawn empty and filled by
// motion.reveal(), which the application shell runs for everything that enters the page.
export function gauge(prob, verdict, label = t("result.probability"), digits = 1) {
  const radius = 84;
  const length = Math.PI * radius;
  const filled = prob == null ? 0 : Math.max(0, Math.min(1, prob)) * length;
  return `
    <div class="gauge gauge-${esc(verdict ?? "inconclusive")}">
      <svg viewBox="0 0 200 116" role="img" aria-label="${esc(label)}: ${esc(pct(prob, digits))}">
        <path class="gauge-track" d="M16 100 A84 84 0 0 1 184 100" pathLength="${length}"/>
        <path class="gauge-value" d="M16 100 A84 84 0 0 1 184 100" stroke-dasharray="0 ${length}" data-dash="${filled} ${length}"/>
      </svg>
      <div class="gauge-label">
        <div class="gauge-number">${prob == null ? "—" : `<span data-count="${(prob * 100).toFixed(digits)}" data-digits="${digits}">0.0</span><small>%</small>`}</div>
        <div class="gauge-caption">${esc(label)}</div>
      </div>
    </div>`;
}

// Circular progress for a running scan; `progress` is 0..1.
let ringCount = 0;
export function ring(progress) {
  const value = Math.round(Math.max(0, Math.min(1, progress)) * 100);
  ringCount += 1;
  const id = `ring-g${ringCount}`;
  return `
    <div class="ring" role="img" aria-label="${value}%">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c6cff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>
        <circle class="ring-track" cx="60" cy="60" r="52"/>
        <circle class="ring-value" cx="60" cy="60" r="52" pathLength="100" stroke="url(#${id})" stroke-dasharray="${value} 100"/>
      </svg>
      <div class="ring-num"><b data-pct>${value}</b><small>%</small></div>
    </div>`;
}

// Horizontal 0..100% bar with the three decision zones and a marker at `prob`.
export function zoneBar(prob, realMax, fakeMin) {
  const a = realMax * 100;
  const b = fakeMin * 100;
  return `
    <div class="zonebar" role="img" aria-label="${esc(pct(prob))}">
      <div class="zonebar-track">
        <span class="zone zone-real" style="width:${a}%"></span>
        <span class="zone zone-suspicious" style="width:${Math.max(0, b - a)}%"></span>
        <span class="zone zone-fake" style="width:${100 - b}%"></span>
        <span class="zonebar-marker" style="left:0%" data-left="${Math.max(0, Math.min(100, prob * 100))}%"></span>
      </div>
      <div class="zonebar-scale"><span>0%</span><span>50%</span><span>100%</span></div>
    </div>`;
}

// Bar chart of probabilities over time; `items` = [{prob, label}].
export function timeline(items, realMax, fakeMin) {
  const width = 600;
  const height = 150;
  const top = 8;
  const plot = height - top - 4;
  const slot = width / Math.max(items.length, 1);
  const bar = Math.max(1.5, Math.min(44, slot * 0.72));
  const y = (value) => top + plot * (1 - value);
  const bars = items.map((item, i) => {
    const h = Math.max(1.5, plot * item.prob);
    const x = i * slot + (slot - bar) / 2;
    return `<rect class="tl-bar tl-${zoneOf(item.prob, realMax, fakeMin)}" style="animation-delay:${Math.min(i * 18, 700)}ms" x="${x.toFixed(2)}" y="${(top + plot - h).toFixed(2)}" width="${bar.toFixed(2)}" height="${h.toFixed(2)}" rx="${Math.min(3, bar / 2)}"><title>${esc(item.label)} — ${esc(pct(item.prob))}</title></rect>`;
  }).join("");
  const guides = [realMax, fakeMin].map((level) =>
    `<line class="tl-guide" x1="0" x2="${width}" y1="${y(level).toFixed(2)}" y2="${y(level).toFixed(2)}"/>`).join("");
  return `
    <div class="timeline">
      <div class="tl-axis"><span>100%</span><span>50%</span><span>0%</span></div>
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${guides}${bars}</svg>
    </div>
    <div class="legend">
      <span><i class="dot dot-real"></i>${esc(t("result.zone.real"))}</span>
      <span><i class="dot dot-suspicious"></i>${esc(t("result.zone.suspicious"))}</span>
      <span><i class="dot dot-fake"></i>${esc(t("result.zone.fake"))}</span>
    </div>`;
}

let toastTimer;
export function toast(message, kind = "info") {
  let node = document.getElementById("toast");
  if (!node) {
    node = document.createElement("div");
    node.id = "toast";
    node.setAttribute("role", "status");
    node.setAttribute("aria-live", "polite");
    document.body.append(node);
  }
  node.className = `toast toast-${kind} show`;
  node.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 4200);
}

// Promise-based confirmation dialog built on <dialog>.
export function confirmDialog(message, confirmLabel) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "dialog";
    dialog.innerHTML = `
      <p>${esc(message)}</p>
      <div class="dialog-actions">
        <button class="btn" value="cancel">${esc(t("common.cancel"))}</button>
        <button class="btn btn-danger" value="ok">${esc(confirmLabel)}</button>
      </div>`;
    dialog.addEventListener("click", (event) => {
      const value = event.target.closest("button")?.value;
      if (value) dialog.close(value);
    });
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "ok");
      dialog.remove();
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

export const emptyState = (icon, text, action = "") => `
  <div class="empty">
    <div class="empty-icon">${icons[icon]}</div>
    <p>${esc(text)}</p>
    ${action}
  </div>`;

export const spinner = () => `<div class="loading"><span class="spinner"></span>${esc(t("common.loading"))}</div>`;
