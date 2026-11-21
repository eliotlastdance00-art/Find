// The investigation on the scan screen: a magnifying glass that travels over the file and really
// enlarges what is under it, and the detective's running commentary.
// The glass is an illustration of "being examined": where it stops is not a finding. The words
// only say what the server is doing in the current stage.
import { reducedMotion } from "./motion.js";

const ZOOM = 2.1;
const TEMPO = {
  queued: { travel: 2600, dwell: 300 },
  preprocessing: { travel: 1100, dwell: 120 },   // a quick look over the whole thing
  analyzing: { travel: 1300, dwell: 900 },       // stop and study
  explaining: { travel: 1700, dwell: 1300 },
};
const ease = (p) => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);

// The part of `media` that shows the picture (object-fit: contain leaves bars around it).
function pictureRect(media, box) {
  const frame = media.getBoundingClientRect();
  const own = { x: frame.left - box.left, y: frame.top - box.top, w: frame.width, h: frame.height };
  const naturalW = media.naturalWidth || media.videoWidth;
  const naturalH = media.naturalHeight || media.videoHeight;
  if (!naturalW || !naturalH || !own.w || !own.h) return own;
  const scale = Math.min(own.w / naturalW, own.h / naturalH);
  const w = naturalW * scale;
  const h = naturalH * scale;
  return { x: own.x + (own.w - w) / 2, y: own.y + (own.h - h) / 2, w, h };
}

// Starts the glass inside `.preview`. Returns { stop }.
export function investigate(preview) {
  const lens = preview.querySelector("[data-lens]");
  const layer = lens?.querySelector(".lens-zoom");
  const kind = preview.dataset.kind;
  const media = preview.querySelector(kind === "audio" ? ".eq" : kind === "video" ? "video" : "img");
  if (!lens || !layer || !media) return { stop() {} };

  // A copy of the media inside the glass, laid out exactly like the original and scaled up.
  let copy;
  let snapshot = null;
  let captured = false;
  if (kind === "image") {
    copy = new Image();
    copy.alt = "";
    copy.src = media.currentSrc || media.src;
  } else if (kind === "video") {
    copy = document.createElement("canvas");
    snapshot = () => {
      if (media.readyState < 2 || !media.videoWidth) return;
      const scale = Math.min(1, 960 / media.videoWidth);
      copy.width = Math.round(media.videoWidth * scale);
      copy.height = Math.round(media.videoHeight * scale);
      try {
        const pen = copy.getContext("2d");
        pen.drawImage(media, 0, 0, copy.width, copy.height);
        // Right after loading, a browser may hand out an empty frame: keep trying until one arrives.
        captured = pen.getImageData(copy.width >> 1, copy.height >> 1, 1, 1).data[3] > 0;
      } catch {
        captured = true;   // the frame cannot be read here: the glass stays plain
      }
    };
    for (const name of ["loadeddata", "seeked", "pause"]) media.addEventListener(name, snapshot);
    snapshot();
  } else {
    copy = media.cloneNode(true);
  }
  copy.classList.add("lens-copy");
  layer.replaceChildren(copy);

  let alive = true;
  let from = null;
  let to = null;
  let legStart = 0;
  let legTravel = 0;
  let legDwell = 0;
  let lastShot = 0;

  const bounds = () => {
    const box = preview.getBoundingClientRect();
    const area = kind === "audio"
      ? (() => { const r = media.getBoundingClientRect(); return { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height }; })()
      : pictureRect(media, box);
    const frame = media.getBoundingClientRect();
    return { box, area, own: { x: frame.left - box.left, y: frame.top - box.top, w: frame.width, h: frame.height } };
  };

  const pick = (area) => (kind === "audio"
    ? { x: area.x + area.w * (0.08 + Math.random() * 0.84), y: area.y + area.h / 2 }
    // Faces sit mostly in the upper middle of a frame: look there more often, but look everywhere.
    : { x: area.x + area.w * (0.16 + Math.random() * 0.68), y: area.y + area.h * (0.14 + Math.random() * (Math.random() < 0.7 ? 0.46 : 0.72)) });

  function frame(now) {
    if (!alive || !preview.isConnected) return;
    requestAnimationFrame(frame);
    const phase = preview.dataset.phase;
    if (phase === "idle" || preview.classList.contains("is-paused")) { from = null; return; }
    const { box, area, own } = bounds();
    if (!area.w || !area.h) return;
    const size = lens.offsetWidth;
    if (!from) {
      from = { x: area.x + area.w / 2, y: area.y + area.h / 2 };
      to = pick(area);
      legStart = now;
      ({ travel: legTravel, dwell: legDwell } = TEMPO[phase] ?? TEMPO.analyzing);
    }
    let elapsed = now - legStart;
    if (elapsed > legTravel + legDwell) {
      from = to;
      to = pick(area);
      legStart = now;
      elapsed = 0;
      const tempo = TEMPO[phase] ?? TEMPO.analyzing;
      legTravel = tempo.travel * (0.8 + Math.random() * 0.5);
      legDwell = tempo.dwell * (0.6 + Math.random() * 0.9);
    }
    const progress = ease(Math.min(1, elapsed / legTravel));
    const studying = elapsed > legTravel;
    // While studying a spot the hand is never perfectly still.
    const sway = studying ? 3.2 : 0;
    const x = from.x + (to.x - from.x) * progress + Math.sin(now / 310) * sway;
    const y = from.y + (to.y - from.y) * progress + Math.cos(now / 270) * sway;
    lens.classList.toggle("is-studying", studying);
    lens.style.transform = `translate3d(${x - size / 2}px, ${y - size / 2}px, 0)`;
    copy.style.left = `${own.x}px`;
    copy.style.top = `${own.y}px`;
    copy.style.width = `${own.w}px`;
    copy.style.height = `${own.h}px`;
    layer.style.width = `${box.width}px`;
    layer.style.height = `${box.height}px`;
    layer.style.transform = `translate3d(${size / 2 - x * ZOOM}px, ${size / 2 - y * ZOOM}px, 0) scale(${ZOOM})`;
    if (snapshot && (!captured || !media.paused) && now - lastShot > 400) { lastShot = now; snapshot(); }
  }

  if (reducedMotion()) lens.hidden = true; else requestAnimationFrame(frame);
  return { stop() { alive = false; } };
}

// Types `lines()` into `node`, one after another, like someone thinking aloud.
export function narrator(node) {
  let timer = 0;
  let run = 0;
  const type = (text, then) => {
    const mine = run;
    if (reducedMotion()) { node.textContent = text; return; }
    let shown = 0;
    node.textContent = "";
    node.classList.add("is-typing");
    const tick = () => {
      if (mine !== run || !node.isConnected) return;
      shown += 1;
      node.textContent = text.slice(0, shown);
      if (shown < text.length) timer = setTimeout(tick, 20);
      else { node.classList.remove("is-typing"); then?.(); }
    };
    tick();
  };
  return {
    // `lines`: the stage's own line first, then asides; they rotate while the stage lasts.
    say(lines) {
      run += 1;
      clearTimeout(timer);
      const mine = run;
      let index = 0;
      const next = () => type(lines[index % lines.length], () => {
        if (lines.length < 2) return;
        timer = setTimeout(() => { if (mine === run) { index += 1; next(); } }, 3600);
      });
      next();
    },
    stop() { run += 1; clearTimeout(timer); },
  };
}
