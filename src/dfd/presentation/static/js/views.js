// One function per screen. Each receives a context and may return a cleanup callback.
import { api, auth, media } from "./api.js";
import { errorText, lang, LANGS, t } from "./i18n.js";
import { countTo, detectMedia, extensionOf, previewFile, wait } from "./motion.js";
import {
  confirmDialog, emptyState, esc, formatBytes, formatDate, formatDuration, gauge, icons, pct,
  ring, spinner, timeline, toast, typeIcon, verdictBadge, zoneBar,
} from "./ui.js";

const KINDS = ["image", "video", "audio"];
const ACCEPT = "image/*,video/*,audio/*,.mkv,.flac,.m4a,.webm";
const STAGES = ["preprocessing", "analyzing", "explaining", "done"];
const ACTIVE = new Set(["queued", "preprocessing", "analyzing", "explaining"]);

const fail = (error) => toast(errorText(error.code ?? "error"), "error");

// Small animated drawings that stand for a picture, a video and a sound recording.
function kindArt(kind) {
  if (kind === "image") {
    return `<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="9" width="36" height="30" rx="6"/><circle class="art-sun" cx="17" cy="19" r="3.4" fill="currentColor" stroke="none"/><path class="art-hill" d="m7 34 10-9 8 7 6-5 10 8"/></svg>`;
  }
  if (kind === "video") {
    return `<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="9" width="36" height="30" rx="6"/><path class="art-play" d="m20.500 17.500 10 6.500-10 6.500z" fill="currentColor"/></svg>`;
  }
  return `<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true">${[10, 17, 24, 31, 38].map((x, i) => `<path class="art-bar" style="animation-delay:${i * -0.18}s" d="M${x} 14v20"/>`).join("")}</svg>`;
}

function pageHead(title, lead, actions = "") {
  return `<div class="page-head"><div><h1>${esc(title)}</h1>${lead ? `<p>${esc(lead)}</p>` : ""}</div>${actions ? `<div class="actions">${actions}</div>` : ""}</div>`;
}

function modelBanners(meta) {
  const models = meta?.models ?? {};
  const out = [];
  for (const kind of ["visual", "audio"]) {
    if (!models[kind]?.available) out.push(`<div class="banner banner-warn">${icons.alert}<span>${esc(t(`models.missing.${kind}`))}</span></div>`);
  }
  if (Object.values(models).some((m) => m.available && m.provisional)) {
    out.push(`<div class="banner banner-info">${icons.info}<span>${esc(t("models.provisional"))}</span></div>`);
  }
  return out.join("");
}

function scanRow(scan) {
  const target = scan.status === "done" ? "result" : "scan";
  const right = scan.status === "done"
    ? `${verdictBadge(scan.verdict)}`
    : `<span class="badge badge-${scan.status === "failed" ? "fake" : "neutral"}">${esc(t(`status.${scan.status}`))}</span>`;
  return `
    <a class="list-item" href="#/${target}/${esc(scan.id)}">
      <span class="file-ico">${typeIcon(scan.media_type)}</span>
      <span class="file-meta"><b>${esc(scan.filename)}</b><span>${esc(formatDate(scan.created_at))} · ${esc(formatBytes(scan.size_bytes))}</span></span>
      ${right}
    </a>`;
}

// Loads the scan for scan-specific screens; renders an empty state when there is none.
async function loadScan(ctx, title) {
  const id = ctx.id ?? ctx.state.current;
  const cta = `<a class="btn btn-primary" href="#/upload">${icons.upload}${esc(t("scan.empty.cta"))}</a>`;
  if (!id) {
    ctx.root.innerHTML = pageHead(title) + `<div class="card">${emptyState("upload", t("scan.empty"), cta)}</div>`;
    return null;
  }
  ctx.root.innerHTML = pageHead(title) + spinner();
  try {
    const scan = await api.scan(id);
    ctx.setCurrent(scan);
    return scan;
  } catch (error) {
    if (error.code === "scan_not_found") ctx.setCurrent(null);
    ctx.root.innerHTML = pageHead(title) + `<div class="card">${emptyState("alert", errorText(error.code), cta)}</div>`;
    return null;
  }
}

function pendingState(scan, title) {
  const action = `<a class="btn btn-primary" href="#/scan/${esc(scan.id)}">${icons.scan}${esc(t("nav.scan"))}</a>`;
  return pageHead(title) + `<div class="card">${emptyState("scan", t("result.pending"), action)}</div>`;
}

function notesFor(scan) {
  const details = scan.details ?? {};
  const notes = (details.notes ?? []).map((code) => t(`note.${code}`));
  if (details.visual?.provisional || details.audio?.provisional) notes.push(t("note.provisional"));
  if (scan.media_type === "video" && details.audio) notes.push(t("note.video_audio"));
  notes.push(t("note.disclaimer"));
  return notes;
}

function frameItems(details) {
  return (details.frames ?? []).map((f) => ({
    prob: f.prob,
    label: f.t == null ? t("regions.face", { i: f.index + 1 }) : t("result.timeline.frame", { i: f.index, t: f.t.toFixed(1) }),
  }));
}

function segmentItems(details) {
  return (details.segments ?? []).map((s) => ({
    prob: s.prob,
    label: t("result.timeline.segment", { a: s.start.toFixed(1), b: s.end.toFixed(1) }),
  }));
}

/* ------------------------------------------------------------------ login */
export function login(ctx) {
  const open = ctx.state.meta?.registration_open !== false;
  let mode = "login";
  const render = () => {
    ctx.root.innerHTML = `
      <div class="auth">
        <section class="auth-hero">
          <div class="brand">${icons.logo}<div><div class="brand-name">${esc(t("app.name"))}</div><div class="brand-tag">${esc(t("app.tagline"))}</div></div></div>
          <div>
            <h1>${esc(t("hero.title"))}</h1>
            <p>${esc(t("hero.text"))}</p>
            <ul>
              <li><i>${icons.regions}</i>${esc(t("hero.f1"))}</li>
              <li><i>${icons.audio}</i>${esc(t("hero.f2"))}</li>
              <li><i>${icons.report}</i>${esc(t("hero.f3"))}</li>
            </ul>
          </div>
          <div class="brand-tag">v${esc(ctx.state.meta?.version ?? "")}</div>
          <div class="hero-mark" aria-hidden="true">${icons.logo}</div>
        </section>
        <section class="auth-panel">
          <div class="auth-top">${ctx.controls()}</div>
          <div class="auth-box">
            <div class="auth-brand">${icons.logo}<div><div class="brand-name">${esc(t("app.name"))}</div><div class="brand-tag">${esc(t("app.tagline"))}</div></div></div>
            <div><h2>${esc(t("login.title"))}</h2><p class="muted">${esc(t("login.subtitle"))}</p></div>
            <div class="tabs" role="tablist">
              <button role="tab" data-mode="login" aria-selected="${mode === "login"}">${esc(t("login.tab.login"))}</button>
              <button role="tab" data-mode="register" aria-selected="${mode === "register"}">${esc(t("login.tab.register"))}</button>
            </div>
            ${mode === "register" && !open ? `<div class="banner banner-warn">${icons.alert}<span>${esc(t("login.closed"))}</span></div>` : ""}
            <form class="form" novalidate>
              <div class="field">
                <label for="username">${esc(t("login.username"))}</label>
                <input class="input" id="username" name="username" autocomplete="username" required maxlength="32" autofocus>
                ${mode === "register" ? `<small>${esc(t("login.hint.username"))}</small>` : ""}
              </div>
              <div class="field">
                <label for="password">${esc(t("login.password"))}</label>
                <input class="input" id="password" name="password" type="password" required maxlength="128" autocomplete="${mode === "login" ? "current-password" : "new-password"}">
                ${mode === "register" ? `<small>${esc(t("login.hint.password"))}</small>` : ""}
              </div>
              <div class="form-error" role="alert" hidden></div>
              <button class="btn btn-primary btn-lg" type="submit" ${mode === "register" && !open ? "disabled" : ""}>${esc(t(mode === "login" ? "login.submit" : "login.register"))}</button>
              ${mode === "register" && open ? `<small class="muted">${esc(t("login.first"))}</small>` : ""}
            </form>
          </div>
        </section>
      </div>`;
    ctx.bindControls(ctx.root);
    ctx.root.querySelectorAll("[data-mode]").forEach((tab) => tab.addEventListener("click", () => { mode = tab.dataset.mode; render(); }));
    const form = ctx.root.querySelector("form");
    const errorBox = form.querySelector(".form-error");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button[type=submit]");
      const username = form.username.value.trim();
      const password = form.password.value;
      if (!username || !password) return;
      button.disabled = true;
      errorBox.hidden = true;
      try {
        auth.set(await (mode === "login" ? api.login(username, password) : api.register(username, password)));
        ctx.navigate("upload");
      } catch (error) {
        errorBox.textContent = errorText(error.code);
        errorBox.hidden = false;
        button.disabled = false;
      }
    });
  };
  render();
}

/* ----------------------------------------------------------------- upload */
export async function upload(ctx) {
  const limits = ctx.state.meta?.limits ?? { max_upload_mb: 200, max_duration_s: 600 };
  ctx.root.innerHTML = `
    ${pageHead(t("upload.title"), t("upload.lead"))}
    ${modelBanners(ctx.state.meta)}
    <div class="dropzone" data-state="idle" tabindex="0" role="button" aria-label="${esc(t("upload.browse"))}">
      <div class="dz-idle">
        <div class="dz-orbit" aria-hidden="true"><i></i><i></i><div class="dz-icon">${icons.upload}</div></div>
        <div>
          <div class="dz-title"><span class="for-mouse">${esc(t("upload.drop"))}</span><span class="for-touch">${esc(t("upload.tap"))}</span></div>
          <div class="muted for-mouse">${esc(t("upload.or"))}</div>
        </div>
        <button class="btn btn-primary btn-lg" type="button" data-browse>${icons.plus}${esc(t("upload.browse"))}</button>
        <div class="dz-kinds" aria-label="${esc(t("upload.kinds"))}">
          ${KINDS.map((kind) => `<div class="dz-kind kind-${kind}"><span class="dz-kind-ico">${kindArt(kind)}</span><b>${esc(t(`type.${kind}`))}</b></div>`).join("")}
        </div>
        <div class="muted dz-limit">${esc(t("upload.limit", { mb: limits.max_upload_mb, min: Math.round(limits.max_duration_s / 60) }))}</div>
      </div>
      <div class="dz-picked" hidden>
        <div class="dz-preview"><div class="dz-media"></div><i class="dz-sweep" aria-hidden="true"></i><span class="dz-kind-ico dz-fallback" aria-hidden="true"></span></div>
        <div class="dz-detected" aria-live="polite"><span class="dz-check">${icons.check}</span><b></b></div>
        <div class="dz-file"><b></b><span></span></div>
        <div class="progress"><i></i></div>
        <div class="muted dz-status" aria-live="polite"></div>
      </div>
      <div class="dz-bad" hidden role="alert">
        <div class="dz-bad-ico">${icons.x}</div>
        <div><div class="dz-title"></div><p class="muted"></p></div>
        <button class="btn btn-lg" type="button" data-browse>${icons.plus}${esc(t("upload.again"))}</button>
      </div>
      <input type="file" accept="${ACCEPT}" hidden>
    </div>
    <div>
      <div class="card-head"><h2>${esc(t("upload.how"))}</h2></div>
      <div class="grid-3">
        ${[1, 2, 3].map((n) => `<div class="card step"><span class="step-n">${n}</span><h2>${esc(t(`upload.step${n}.t`))}</h2><p>${esc(t(`upload.step${n}.d`))}</p></div>`).join("")}
      </div>
    </div>
    <div class="recent"></div>`;

  const zone = ctx.root.querySelector(".dropzone");
  const input = zone.querySelector("input");
  const picked = zone.querySelector(".dz-picked");
  const bad = zone.querySelector(".dz-bad");
  const bar = picked.querySelector(".progress");
  const status = picked.querySelector(".dz-status");
  let busy = false;
  let release = null;

  const show = (state) => {
    zone.dataset.state = state;
    zone.querySelector(".dz-idle").hidden = state !== "idle";
    picked.hidden = state !== "picked";
    bad.hidden = state !== "bad";
  };

  // The file is refused: say so in place, in words, without listing extensions.
  const refuse = (title, text) => {
    release?.();
    release = null;
    bad.querySelector(".dz-title").textContent = title;
    bad.querySelector("p").textContent = text;
    show("bad");
    zone.classList.remove("shake");
    void zone.offsetWidth;  // restart the animation when the same mistake is repeated
    zone.classList.add("shake");
  };

  async function send(file) {
    if (busy || !file) return;
    if (file.size === 0) return refuse(t("upload.bad.other"), errorText("empty_file"));
    if (file.size > limits.max_upload_mb * 1024 * 1024) return refuse(t("upload.bad.other"), errorText("file_too_large"));
    busy = true;
    const kind = await detectMedia(file);
    if (!ctx.alive()) return;
    if (!kind) {
      busy = false;
      input.value = "";
      const ext = extensionOf(file.name);
      return refuse(t("upload.bad.title"), t("upload.bad.text", { name: ext ? `.${ext}` : file.name }));
    }

    // Show what was recognised straight away; the upload runs behind the preview.
    const started = performance.now();
    release?.();
    picked.className = `dz-picked kind-${kind}`;
    picked.querySelector(".dz-preview").classList.remove("no-preview");
    picked.querySelector(".dz-fallback").innerHTML = kindArt(kind);
    picked.querySelector(".dz-detected b").textContent = t(`upload.detected.${kind}`);
    picked.querySelector(".dz-file b").textContent = file.name;
    picked.querySelector(".dz-file span").textContent = formatBytes(file.size);
    bar.classList.remove("indeterminate");
    bar.firstElementChild.style.width = "0%";
    status.textContent = "";
    show("picked");
    release = previewFile(picked.querySelector(".dz-media"), file, kind);
    zone.classList.add("busy");
    try {
      const scan = await api.upload(file, (fraction) => {
        bar.firstElementChild.style.width = `${(fraction * 100).toFixed(1)}%`;
        if (fraction >= 1) {
          bar.classList.add("indeterminate");
          status.textContent = t("upload.checking");
        } else {
          status.textContent = t("upload.uploading", { pct: Math.round(fraction * 100) });
        }
      });
      bar.classList.remove("indeterminate");
      bar.firstElementChild.style.width = "100%";
      status.textContent = t("upload.sent");
      picked.classList.add("sent");
      // Small files arrive at once: keep the recognition on screen long enough to be read.
      await wait(Math.max(350, 1500 - (performance.now() - started)));
      if (!ctx.alive()) return;
      ctx.setCurrent(scan);
      ctx.navigate(`scan/${scan.id}`);
    } catch (error) {
      const code = error.code ?? "error";
      if (code === "unsupported_media") {
        const ext = extensionOf(file.name);
        refuse(t("upload.bad.title"), t("upload.bad.text", { name: ext ? `.${ext}` : file.name }));
      } else {
        refuse(t("upload.bad.other"), errorText(code));
      }
    } finally {
      busy = false;
      zone.classList.remove("busy");
      input.value = "";
    }
  }

  zone.addEventListener("click", () => { if (!busy) input.click(); });
  zone.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && event.target === zone) { event.preventDefault(); input.click(); }
  });
  input.addEventListener("click", (event) => event.stopPropagation());
  input.addEventListener("change", () => send(input.files[0]));
  for (const name of ["dragenter", "dragover"]) zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("over"); });
  for (const name of ["dragleave", "drop"]) zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("over"); });
  zone.addEventListener("drop", (event) => send(event.dataTransfer.files[0]));

  try {
    const recent = await api.history({ limit: 5 });
    if (recent.items.length && ctx.alive()) {
      ctx.root.querySelector(".recent").innerHTML = `
        <div class="card-head"><h2>${esc(t("upload.recent"))}</h2><a class="btn btn-sm btn-ghost" href="#/history">${esc(t("nav.history"))}${icons.arrow}</a></div>
        <div class="card list">${recent.items.map(scanRow).join("")}</div>`;
    }
  } catch { /* the list is optional */ }
  return () => release?.();
}

/* ------------------------------------------------------------------- scan */
const EQ_BARS = 36;

function previewOf(scan) {
  const src = esc(media.source(scan));
  const phase = ACTIVE.has(scan.status) ? scan.status : "idle";
  const fx = `
    <div class="fx" aria-hidden="true">
      <i class="fx-grid"></i><i class="fx-line"></i><i class="fx-heat"></i>
      <i class="fx-corner tl"></i><i class="fx-corner tr"></i><i class="fx-corner bl"></i><i class="fx-corner br"></i>
      <span class="fx-chip"><i></i><span data-fx-label>${esc(phase === "idle" ? "" : t(`scan.fx.${phase}`))}</span></span>
    </div>`;
  if (scan.media_type === "image") return `<div class="preview" data-kind="image" data-phase="${phase}"><img src="${src}" alt="${esc(scan.filename)}">${fx}</div>`;
  if (scan.media_type === "video") return `<div class="preview" data-kind="video" data-phase="${phase}"><video src="${src}" controls preload="metadata" playsinline></video>${fx}</div>`;
  const bars = Array.from({ length: EQ_BARS }, (_, i) => `<i style="--i:${i};--h:${(0.3 + 0.7 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.6))).toFixed(2)}"></i>`).join("");
  return `<div class="preview" data-kind="audio" data-phase="${phase}"><div class="preview-audio"><div class="eq" aria-hidden="true">${bars}</div><audio src="${src}" controls preload="metadata"></audio></div>${fx}</div>`;
}

function factsOf(scan) {
  const info = scan.details?.media ?? {};
  const rows = [
    [t("file.name"), esc(scan.filename)],
    [t("file.type"), esc(t(`type.${scan.media_type}`))],
    [t("file.size"), esc(formatBytes(scan.size_bytes))],
  ];
  if (info.duration_s != null) rows.push([t("file.duration"), esc(formatDuration(info.duration_s))]);
  if (info.width && info.height) rows.push([t("file.resolution"), `${info.width} × ${info.height}`]);
  if (scan.media_type === "video") rows.push([t("file.audio"), esc(t(info.has_audio ? "common.yes" : "common.no"))]);
  rows.push([t("file.uploaded"), esc(formatDate(scan.created_at))]);
  rows.push([t("file.hash"), `<span class="mono" title="${esc(scan.sha256)}">${esc(scan.sha256.slice(0, 16))}…</span> <button class="btn btn-sm btn-ghost" data-copy="${esc(scan.sha256)}" title="${esc(t("common.copy"))}">${icons.copy}</button>`]);
  return `<dl class="facts">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
}

function stepper(status) {
  const position = status === "done" ? STAGES.length : Math.max(0, STAGES.indexOf(status));
  return `<div class="stepper">${STAGES.map((stage, i) => {
    const state = i < position ? "done" : (i === position && ACTIVE.has(status) ? "active" : "");
    return `<div class="stage ${state}"><span class="stage-dot">${state === "done" ? icons.check : i + 1}</span><div><b>${esc(t(`scan.stage.${stage}`))}</b><small>${esc(t(`scan.stage.${stage}.d`))}</small></div></div>`;
  }).join("")}</div>`;
}

export async function scan(ctx) {
  let current = await loadScan(ctx, t("scan.title"));
  if (!current) return undefined;
  const controller = new AbortController();
  let pollTimer;

  const panel = () => {
    const { status } = current;
    if (status === "uploaded") {
      return `<div class="banner banner-info">${icons.info}<span>${esc(t("scan.ready"))}</span></div>
              <button class="btn btn-primary btn-lg" data-start>${icons.scan}${esc(t("scan.start"))}</button>`;
    }
    if (status === "failed") {
      return `<div class="banner banner-error">${icons.alert}<span><b>${esc(t("scan.failed"))}.</b> ${esc(errorText(current.error ?? "error"))}</span></div>
              <button class="btn btn-primary btn-lg" data-start>${icons.scan}${esc(t("scan.retry"))}</button>`;
    }
    const done = status === "done";
    const stage = done ? "done" : status;
    return `
      <div class="scan-hero ${done ? `is-done tone-${esc(current.verdict ?? "inconclusive")}` : "is-live"}">
        ${ring(done ? 1 : current.progress)}
        <div class="scan-hero-text">
          <b data-label>${esc(done ? t("scan.done") : t(`scan.stage.${stage}`))}</b>
          <span data-sub>${esc(done ? t("scan.stage.done.d") : stage === "queued" ? t("scan.fx.queued") : t(`scan.stage.${stage}.d`))}</span>
        </div>
      </div>
      <div data-stepper>${stepper(status)}</div>
      ${done ? `<div class="row scan-outcome">${verdictBadge(current.verdict, true)}<a class="btn btn-primary" href="#/result/${esc(current.id)}">${esc(t("scan.view"))}${icons.arrow}</a></div>` : ""}`;
  };

  const setPhase = (status) => {
    const box = ctx.root.querySelector(".preview");
    if (!box) return;
    const phase = ACTIVE.has(status) ? status : "idle";
    if (box.dataset.phase === phase) return;
    box.dataset.phase = phase;
    const label = box.querySelector("[data-fx-label]");
    if (label && phase !== "idle") label.textContent = t(`scan.fx.${phase}`);
  };

  const render = () => {
    ctx.root.innerHTML = `
      ${pageHead(t("scan.title"), current.filename)}
      <div class="split">
        <div class="stack">${previewOf(current)}</div>
        <div class="stack">
          <div class="card card-pad stack" data-panel>${panel()}</div>
          <div class="card card-pad">${factsOf(current)}</div>
        </div>
      </div>`;
    bind();
  };

  const updateProgress = (event) => {
    const before = Math.round(current.progress * 100);
    current = { ...current, status: event.status, progress: event.progress, error: event.error, verdict: event.verdict };
    setPhase(event.status);
    const box = ctx.root.querySelector("[data-panel]");
    if (!box) return;
    if (!box.querySelector("[data-stepper]") || !ACTIVE.has(event.status)) { box.innerHTML = panel(); bind(); return; }
    const value = Math.round(event.progress * 100);
    box.querySelector(".ring-value").setAttribute("stroke-dasharray", `${value} 100`);
    countTo(box.querySelector("[data-pct]"), value, { from: before, duration: 450 });
    box.querySelector("[data-label]").textContent = t(`scan.stage.${event.status}`);
    box.querySelector("[data-sub]").textContent = event.status === "queued" ? t("scan.fx.queued") : t(`scan.stage.${event.status}.d`);
    box.querySelector("[data-stepper]").innerHTML = stepper(event.status);
  };

  const finish = async () => {
    try { current = await api.scan(current.id); } catch { return; }
    if (!ctx.alive()) return;
    ctx.setCurrent(current);
    if (current.status === "done") {
      setTimeout(() => { if (ctx.alive()) ctx.navigate(`result/${current.id}`); }, 1500);
    }
    setPhase(current.status);
    const box = ctx.root.querySelector("[data-panel]");
    if (box) { box.innerHTML = panel(); bind(); }
  };

  // After two missed polls the screen says so instead of animating as if work continued.
  let misses = 0;
  const setOffline = (offline) => {
    const hero = ctx.root.querySelector(".scan-hero");
    if (!hero || hero.classList.contains("is-offline") === offline) return;
    hero.classList.toggle("is-offline", offline);
    ctx.root.querySelector(".preview")?.classList.toggle("is-paused", offline);
    const sub = hero.querySelector("[data-sub]");
    if (sub && offline) sub.textContent = t("err.network");
  };

  const poll = () => {
    pollTimer = setTimeout(async () => {
      if (!ctx.alive()) return;
      try {
        const fresh = await api.scan(current.id);
        misses = 0;
        setOffline(false);
        updateProgress(fresh);
        if (ACTIVE.has(fresh.status)) poll(); else finish();
      } catch {
        misses += 1;
        if (misses >= 2) setOffline(true);
        poll();
      }
    }, misses >= 2 ? 4000 : 1500);
  };

  const follow = async () => {
    try {
      await api.events(current.id, updateProgress, controller.signal);
      if (ctx.alive()) (ACTIVE.has(current.status) ? poll() : finish());
    } catch (error) {
      if (error.name !== "AbortError" && ctx.alive()) poll();  // stream unavailable: fall back to polling
    }
  };

  function bind() {
    ctx.root.querySelector("[data-start]")?.addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      try {
        current = await api.start(current.id);
        setPhase(current.status);
        ctx.root.querySelector("[data-panel]").innerHTML = panel();
        follow();
      } catch (error) {
        fail(error);
        event.currentTarget.disabled = false;
      }
    });
    ctx.root.querySelector("[data-copy]")?.addEventListener("click", async (event) => {
      try {
        await navigator.clipboard.writeText(event.currentTarget.dataset.copy);
        toast(t("common.copied"), "success");
      } catch { /* clipboard may be blocked inside an iframe */ }
    });
  }

  render();
  if (ACTIVE.has(current.status)) follow();
  return () => { controller.abort(); clearTimeout(pollTimer); };
}

/* ----------------------------------------------------------------- result */
function modalityCard(kind, data) {
  if (!data) return "";
  return `
    <div class="card modality">
      <div class="modality-top">
        <span class="file-ico">${kind === "visual" ? icons.regions : icons.audio}</span>
        <div><b>${esc(t(`result.${kind}`))}</b><br>${verdictBadge(data.verdict)}</div>
        <span class="val">${esc(pct(data.prob))}</span>
      </div>
      ${zoneBar(data.prob, data.real_max, data.fake_min)}
      <small>${esc(t("result.band", { a: (data.real_max * 100).toFixed(0), b: (data.fake_min * 100).toFixed(0) }))} · ${esc(t("result.model"))}: ${esc(data.model)}</small>
    </div>`;
}

export async function result(ctx) {
  const scan = await loadScan(ctx, t("result.title"));
  if (!scan) return;
  if (scan.status !== "done") { ctx.root.innerHTML = pendingState(scan, t("result.title")); return; }
  const details = scan.details ?? {};
  const verdict = scan.verdict ?? "inconclusive";
  const frames = frameItems(details);
  const segments = segmentItems(details);
  const info = details.media ?? {};
  const kpis = [[t("result.took"), formatDuration((scan.duration_ms ?? 0) / 1000)]];
  if (info.frames_sampled != null) kpis.push([t("result.frames"), info.frames_sampled]);
  if (info.faces_found != null) kpis.push([t("result.faces"), info.faces_found]);
  kpis.push([t("file.type"), t(`type.${scan.media_type}`)]);

  ctx.root.innerHTML = `
    ${pageHead(t("result.title"), scan.filename, `
      <a class="btn" href="#/regions/${esc(scan.id)}">${icons.regions}${esc(t("result.to.regions"))}</a>
      <a class="btn" href="#/report/${esc(scan.id)}">${icons.report}${esc(t("result.to.report"))}</a>
      <a class="btn btn-primary" href="#/upload">${icons.plus}${esc(t("result.new"))}</a>`)}
    <div class="card verdict-card tone-${esc(verdict)}">
      ${gauge(scan.prob_fake, verdict)}
      <div class="verdict-text">
        ${verdictBadge(verdict, true)}
        <p>${esc(t(`verdict.${verdict}.d`))}</p>
      </div>
    </div>
    ${details.visual || details.audio ? `<div class="grid-2">${modalityCard("visual", details.visual)}${modalityCard("audio", details.audio)}</div>` : ""}
    ${frames.length > 1 && details.visual ? `<div class="card card-pad"><div class="card-head"><h2>${esc(t("result.timeline.frames"))}</h2></div>${timeline(frames, details.visual.real_max, details.visual.fake_min)}</div>` : ""}
    ${segments.length > 1 && details.audio ? `<div class="card card-pad"><div class="card-head"><h2>${esc(t("result.timeline.audio"))}</h2></div>${timeline(segments, details.audio.real_max, details.audio.fake_min)}</div>` : ""}
    <div class="grid-2">
      <div class="card card-pad"><div class="card-head"><h2>${esc(t("result.notes"))}</h2></div>
        <ul class="notes">${notesFor(scan).map((note) => `<li>${icons.info}<span>${esc(note)}</span></li>`).join("")}</ul>
      </div>
      <div class="card card-pad"><div class="kpis">${kpis.map(([k, v]) => `<div class="kpi"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div></div>
    </div>`;
}

/* ---------------------------------------------------------------- regions */
export async function regions(ctx) {
  const scan = await loadScan(ctx, t("regions.title"));
  if (!scan) return;
  if (scan.status !== "done") { ctx.root.innerHTML = pendingState(scan, t("regions.title")); return; }
  const details = scan.details ?? {};
  const shots = (details.frames ?? []).filter((f) => f.face && f.heatmap).sort((a, b) => b.prob - a.prob);
  const isVideo = scan.media_type === "video";
  let body;
  if (scan.media_type === "audio") {
    const segments = segmentItems(details);
    body = `<div class="banner banner-info">${icons.info}<span>${esc(t("regions.audio"))}</span></div>
      ${segments.length && details.audio ? `<div class="card card-pad"><div class="card-head"><h2>${esc(t("result.timeline.audio"))}</h2></div>${timeline(segments, details.audio.real_max, details.audio.fake_min)}</div>` : ""}`;
  } else if (!shots.length) {
    body = `<div class="card">${emptyState("regions", (details.notes ?? []).includes("no_face_found") ? t("note.no_face_found") : t("regions.none"))}</div>`;
  } else {
    body = `
      <div class="card card-pad row" style="justify-content:space-between">
        <label class="slider">${esc(t("regions.opacity"))}<input type="range" min="0" max="100" value="85" aria-label="${esc(t("regions.opacity"))}"><b data-opacity>85%</b></label>
        <div class="heat-legend">${esc(t("regions.legend.low"))}<i></i>${esc(t("regions.legend.high"))}</div>
      </div>
      ${details.overview ? `<div class="card card-pad"><div class="card-head"><h2>${esc(t("regions.overview"))}</h2></div><div class="overview-img"><img src="${esc(media.file(scan, details.overview))}" alt="${esc(t("regions.overview"))}" loading="lazy"></div></div>` : ""}
      <div>
        <div class="card-head"><h2>${esc(t(isVideo ? "regions.frames" : "regions.faces"))}</h2></div>
        <div class="heat-grid">${shots.map((f) => `
          <figure class="heat" style="margin:0">
            <div class="heat-img" role="button" tabindex="0" title="${esc(t("regions.opacity"))}">
              <img src="${esc(media.file(scan, f.face))}" alt="" loading="lazy">
              <img class="heat-layer" src="${esc(media.file(scan, f.heatmap))}" alt="" loading="lazy">
            </div>
            <figcaption class="heat-cap">
              <span>${esc(isVideo ? `${t("regions.frame", { i: f.index })} · ${f.t.toFixed(1)} ${t("common.seconds")}` : t("regions.face", { i: f.index + 1 }))}</span>
              ${details.visual ? `<b class="badge badge-${zoneClass(f.prob, details.visual)}">${esc(pct(f.prob))}</b>` : `<b>${esc(pct(f.prob))}</b>`}
            </figcaption>
          </figure>`).join("")}</div>
      </div>`;
  }
  ctx.root.innerHTML = pageHead(t("regions.title"), t("regions.lead"), `<a class="btn" href="#/result/${esc(scan.id)}">${icons.result}${esc(t("nav.result"))}</a>`) + body;

  const slider = ctx.root.querySelector("input[type=range]");
  const grid = ctx.root.querySelector(".heat-grid");
  slider?.addEventListener("input", () => {
    grid.style.setProperty("--heat", slider.value / 100);
    ctx.root.querySelector("[data-opacity]").textContent = `${slider.value}%`;
  });
  grid?.addEventListener("click", (event) => event.target.closest(".heat-img")?.classList.toggle("off"));
  grid?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.target.closest(".heat-img")?.classList.toggle("off"); }
  });
}

function zoneClass(prob, modality) {
  if (prob >= modality.fake_min) return "fake";
  return prob <= modality.real_max ? "real" : "suspicious";
}

/* ----------------------------------------------------------------- report */
export async function report(ctx) {
  const scan = await loadScan(ctx, t("report.title"));
  if (!scan) return;
  if (scan.status !== "done") { ctx.root.innerHTML = pendingState(scan, t("report.title")); return; }
  let language = lang();
  const render = () => {
    ctx.root.innerHTML = `
      ${pageHead(t("report.title"), t("report.lead"))}
      <div class="card card-pad stack">
        <div class="row" style="justify-content:space-between">
          <div class="row">
            <span class="file-ico">${typeIcon(scan.media_type)}</span>
            <div class="file-meta"><b>${esc(scan.filename)}</b><span>${esc(formatDate(scan.created_at))}</span></div>
            ${verdictBadge(scan.verdict)}
          </div>
          <div class="row">
            <span class="muted" style="font-size:13px">${esc(t("report.lang"))}</span>
            <div class="seg" role="group" aria-label="${esc(t("report.lang"))}">${LANGS.map((code) => `<button data-report-lang="${code}" aria-pressed="${code === language}">${code.toUpperCase()}</button>`).join("")}</div>
            <a class="btn" href="${esc(media.report(scan, language))}" target="_blank" rel="noopener">${icons.external}${esc(t("report.open"))}</a>
            <a class="btn btn-primary" href="${esc(media.report(scan, language, true))}" download>${icons.download}${esc(t("report.download"))}</a>
          </div>
        </div>
        <p class="muted" style="font-size:14px">${esc(t("report.contains"))}</p>
      </div>
      <div class="card card-pad">
        <div class="card-head"><h2>${esc(t("report.preview"))}</h2></div>
        <iframe class="pdf-frame" title="${esc(t("report.preview"))}" src="${esc(media.report(scan, language))}#view=FitH"></iframe>
        <p class="muted" style="font-size:13px;margin-top:10px">${esc(t("report.fallback"))}</p>
      </div>`;
    ctx.root.querySelectorAll("[data-report-lang]").forEach((button) => button.addEventListener("click", () => { language = button.dataset.reportLang; render(); }));
  };
  render();
}

/* ---------------------------------------------------------------- history */
export async function history(ctx) {
  const query = { q: "", verdict: "", media_type: "", limit: 10, offset: 0 };
  ctx.root.innerHTML = `
    ${pageHead(t("history.title"), t("history.lead"), `<a class="btn btn-primary" href="#/upload">${icons.plus}${esc(t("result.new"))}</a>`)}
    <div class="grid-4" data-stats></div>
    <div class="filters">
      <div class="search">${icons.search}<input class="input" type="search" placeholder="${esc(t("history.search"))}" aria-label="${esc(t("history.search"))}"></div>
      <select class="select" data-filter="verdict" aria-label="${esc(t("history.verdict"))}">
        <option value="">${esc(t("history.verdict"))}: ${esc(t("common.all"))}</option>
        ${["real", "suspicious", "fake", "inconclusive"].map((v) => `<option value="${v}">${esc(t(`verdict.${v}`))}</option>`).join("")}
      </select>
      <select class="select" data-filter="media_type" aria-label="${esc(t("history.type"))}">
        <option value="">${esc(t("history.type"))}: ${esc(t("common.all"))}</option>
        ${["image", "video", "audio"].map((v) => `<option value="${v}">${esc(t(`type.${v}`))}</option>`).join("")}
      </select>
    </div>
    <div class="card" data-table>${spinner()}</div>`;

  const table = ctx.root.querySelector("[data-table]");

  async function loadStats() {
    try {
      const stats = await api.stats();
      if (!ctx.alive()) return;
      const cell = (label, value, dot) => `<div class="card stat"><span>${dot ? `<i class="dot dot-${dot}"></i>` : ""}${esc(label)}</span><b>${value}</b></div>`;
      ctx.root.querySelector("[data-stats]").innerHTML =
        cell(t("history.total"), stats.total) + cell(t("verdict.real"), stats.real, "real") +
        cell(t("verdict.suspicious"), stats.suspicious, "suspicious") + cell(t("verdict.fake"), stats.fake, "fake");
    } catch { /* stats are optional */ }
  }

  async function load() {
    let page;
    try { page = await api.history(query); } catch (error) { fail(error); return; }
    if (!ctx.alive()) return;
    if (!page.items.length) { table.innerHTML = emptyState("history", t("history.empty")); return; }
    const from = page.offset + 1;
    const to = page.offset + page.items.length;
    table.innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th>${esc(t("history.col.file"))}</th><th>${esc(t("history.col.verdict"))}</th><th>${esc(t("history.col.prob"))}</th><th>${esc(t("history.col.date"))}</th><th></th></tr></thead>
        <tbody>${page.items.map((item) => `
          <tr data-id="${esc(item.id)}" data-done="${item.status === "done"}">
            <td><div class="cell-file"><span class="file-ico">${typeIcon(item.media_type)}</span><b title="${esc(item.filename)}">${esc(item.filename)}</b></div></td>
            <td>${item.status === "done" ? verdictBadge(item.verdict) : `<span class="badge badge-${item.status === "failed" ? "fake" : "neutral"}">${esc(t(`status.${item.status}`))}</span>`}</td>
            <td class="num">${esc(pct(item.prob_fake))}</td>
            <td class="date">${esc(formatDate(item.created_at))}</td>
            <td><div class="cell-actions">
              ${item.status === "done" ? `<a class="btn btn-icon btn-ghost" href="#/report/${esc(item.id)}" title="${esc(t("nav.report"))}" aria-label="${esc(t("nav.report"))}">${icons.report}</a>` : ""}
              <button class="btn btn-icon btn-ghost" data-delete="${esc(item.id)}" data-name="${esc(item.filename)}" title="${esc(t("common.delete"))}" aria-label="${esc(t("common.delete"))}">${icons.trash}</button>
            </div></td>
          </tr>`).join("")}</tbody>
      </table></div>
      <div class="pager">
        <span>${esc(t("history.page", { a: from, b: to, n: page.total }))}</span>
        <div class="row">
          <button class="btn btn-sm" data-page="-1" ${page.offset === 0 ? "disabled" : ""}>${esc(t("history.prev"))}</button>
          <button class="btn btn-sm" data-page="1" ${to >= page.total ? "disabled" : ""}>${esc(t("history.next"))}</button>
        </div>
      </div>`;
  }

  table.addEventListener("click", async (event) => {
    const remove = event.target.closest("[data-delete]");
    if (remove) {
      event.stopPropagation();
      if (!(await confirmDialog(t("history.confirm", { name: remove.dataset.name }), t("common.delete")))) return;
      try {
        await api.remove(remove.dataset.delete);
        if (ctx.state.current === remove.dataset.delete) ctx.setCurrent(null);
        toast(t("history.deleted"), "success");
        if (query.offset > 0 && table.querySelectorAll("tbody tr").length === 1) query.offset -= query.limit;
        load();
        loadStats();
      } catch (error) { fail(error); }
      return;
    }
    const pager = event.target.closest("[data-page]");
    if (pager) { query.offset = Math.max(0, query.offset + Number(pager.dataset.page) * query.limit); load(); return; }
    if (event.target.closest("a")) return;
    const row = event.target.closest("tr[data-id]");
    if (row) ctx.navigate(`${row.dataset.done === "true" ? "result" : "scan"}/${row.dataset.id}`);
  });

  let debounce;
  ctx.root.querySelector("input[type=search]").addEventListener("input", (event) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { query.q = event.target.value.trim(); query.offset = 0; load(); }, 250);
  });
  ctx.root.querySelectorAll("[data-filter]").forEach((select) => select.addEventListener("change", () => {
    query[select.dataset.filter] = select.value;
    query.offset = 0;
    load();
  }));

  loadStats();
  await load();
  return () => clearTimeout(debounce);
}
