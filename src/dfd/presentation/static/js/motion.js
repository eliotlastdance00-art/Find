// Motion and media helpers: what a chosen file really is, local previews, small animations.
// Everything here is decoration or an early check; the server stays the authority.

export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const AUDIO_EXT = new Set(["wav", "mp3", "flac", "ogg", "oga", "opus", "m4a", "aac", "mka", "weba"]);
const startsWith = (bytes, magic, offset = 0) => magic.every((value, i) => bytes[offset + i] === value);
const ascii = (text) => [...text].map((ch) => ch.charCodeAt(0));

export const extensionOf = (name) => {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot + 1).toLowerCase() : "";
};

// Mirrors infrastructure/media/inspect.py::sniff. Returns "image", "av" or null.
function family(bytes) {
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) return "image";
  if (startsWith(bytes, [0x89, ...ascii("PNG\r\n"), 0x1a, 0x0a])) return "image";
  if (startsWith(bytes, ascii("BM"))) return "image";
  if (startsWith(bytes, ascii("ftyp"), 4)) return "av";
  if (startsWith(bytes, [0x1a, 0x45, 0xdf, 0xa3])) return "av";
  if (startsWith(bytes, ascii("fLaC")) || startsWith(bytes, ascii("OggS")) || startsWith(bytes, ascii("ID3"))) return "av";
  if (startsWith(bytes, ascii("RIFF"))) {
    if (startsWith(bytes, ascii("WEBP"), 8)) return "image";
    if (startsWith(bytes, ascii("WAVE"), 8) || startsWith(bytes, ascii("AVI "), 8)) return "av";
    return null;
  }
  if (bytes.length > 1 && bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0) return "av";
  return null;
}

// Resolves to "image" | "video" | "audio", or null when the server would refuse the file.
export async function detectMedia(file) {
  const type = file.type || "";
  const ext = extensionOf(file.name);
  const guess = type.startsWith("image/") ? "image"
    : type.startsWith("audio/") || AUDIO_EXT.has(ext) ? "audio"
      : "video";
  let bytes;
  try {
    bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  } catch {
    return type || ext ? guess : null;  // the file cannot be read here: let the server decide
  }
  const kind = family(bytes);
  if (kind === null) return null;
  if (kind === "image") return "image";
  return guess === "image" ? "video" : guess;
}

/* ---------------------------------------------------------------- previews */

function seeded(seed) {
  let state = seed % 2147483647 || 1;
  return () => (state = (state * 48271) % 2147483647) / 2147483647;
}

async function peaksOf(file, count) {
  const Context = window.AudioContext || window.webkitAudioContext;
  if (Context && file.size <= 12 * 1024 * 1024) {
    const context = new Context();
    try {
      const audio = await context.decodeAudioData(await file.arrayBuffer());
      const data = audio.getChannelData(0);
      const block = Math.max(1, Math.floor(data.length / count));
      const peaks = [];
      for (let i = 0; i < count; i += 1) {
        let top = 0;
        for (let j = i * block; j < (i + 1) * block; j += Math.max(1, Math.floor(block / 400))) {
          top = Math.max(top, Math.abs(data[j] || 0));
        }
        peaks.push(top);
      }
      const max = Math.max(...peaks, 0.001);
      return peaks.map((value) => value / max);
    } catch { /* not decodable in this browser: draw a neutral shape instead */ } finally {
      context.close?.();
    }
  }
  const random = seeded(file.size + file.name.length * 7919);
  return Array.from({ length: count }, (_, i) => 0.25 + 0.75 * random() * (0.55 + 0.45 * Math.sin((i / count) * Math.PI)));
}

function drawWaveform(canvas, peaks, alive) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = canvas.clientWidth || 280;
  const height = canvas.clientHeight || 120;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const style = getComputedStyle(canvas);
  const gradient = context.createLinearGradient(0, 0, width, 0);
  gradient.addColorStop(0, style.getPropertyValue("--brand").trim() || "#6d5efc");
  gradient.addColorStop(1, style.getPropertyValue("--brand-2").trim() || "#22d3ee");
  const slot = width / peaks.length;
  const bar = Math.max(2, slot * 0.58);
  const started = performance.now();
  const duration = reducedMotion() ? 1 : 900;
  const frame = (now) => {
    if (!alive()) return;
    const elapsed = now - started;
    context.clearRect(0, 0, width, height);
    context.fillStyle = gradient;
    peaks.forEach((peak, i) => {
      const local = Math.max(0, Math.min(1, (elapsed - (i / peaks.length) * duration * 0.6) / (duration * 0.4)));
      const eased = 1 - (1 - local) ** 3;
      const h = Math.max(3, peak * (height - 12) * eased);
      context.beginPath();
      context.roundRect?.(i * slot + (slot - bar) / 2, (height - h) / 2, bar, h, bar / 2);
      if (!context.roundRect) context.rect(i * slot + (slot - bar) / 2, (height - h) / 2, bar, h);
      context.fill();
    });
    if (elapsed < duration) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

// Fills `box` with a local preview of the chosen file. Returns a function that releases it.
export function previewFile(box, file, kind) {
  let live = true;
  let url = null;
  box.replaceChildren();
  if (kind === "audio") {
    const canvas = document.createElement("canvas");
    canvas.className = "dz-wave";
    box.append(canvas);
    peaksOf(file, 48).then((peaks) => { if (live) drawWaveform(canvas, peaks, () => live); });
  } else {
    url = URL.createObjectURL(file);
    const node = document.createElement(kind === "image" ? "img" : "video");
    node.addEventListener("error", () => box.classList.add("no-preview"));
    if (kind === "video") {
      node.muted = true;
      node.playsInline = true;
      node.preload = "metadata";
      // A still frame only: keep the browser's cast and picture-in-picture buttons off it.
      node.disableRemotePlayback = true;
      node.disablePictureInPicture = true;
      node.addEventListener("loadedmetadata", () => {
        try { node.currentTime = Math.min(0.2, (node.duration || 1) / 2); } catch { /* not seekable */ }
      });
    } else {
      node.alt = "";
    }
    node.src = url;
    box.append(node);
  }
  return () => {
    live = false;
    if (url) URL.revokeObjectURL(url);
  };
}

/* -------------------------------------------------------------- animations */

// Counts a number up (or down) inside `node`.
export function countTo(node, to, { from = 0, digits = 0, duration = 900 } = {}) {
  if (!node) return;
  if (reducedMotion() || from === to) { node.textContent = to.toFixed(digits); return; }
  const started = performance.now();
  const frame = (now) => {
    const progress = Math.min(1, (now - started) / duration);
    const eased = 1 - (1 - progress) ** 3;
    node.textContent = (from + (to - from) * eased).toFixed(digits);
    if (progress < 1 && node.isConnected) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

// Plays the entrance of gauges, zone markers and counters rendered with data-* targets.
// Each target is consumed, so calling this again only touches what was added since.
export function reveal(root) {
  const dashes = [...root.querySelectorAll("[data-dash]")];
  const markers = [...root.querySelectorAll("[data-left]")];
  if (dashes.length || markers.length) {
    for (const node of [...dashes, ...markers]) node.getBoundingClientRect();  // commit the empty state
    for (const node of dashes) { node.style.strokeDasharray = node.dataset.dash; delete node.dataset.dash; }
    for (const node of markers) { node.style.left = node.dataset.left; delete node.dataset.left; }
  }
  root.querySelectorAll("[data-count]").forEach((node) => {
    const target = Number(node.dataset.count);
    const digits = Number(node.dataset.digits ?? 0);
    delete node.dataset.count;
    countTo(node, target, { digits, duration: 1100 });
  });
}

export const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
