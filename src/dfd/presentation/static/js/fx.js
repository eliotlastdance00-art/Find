// The world behind the interface and the passages into it: a field of drifting points with
// depth, a "warp" for entrances, the opening sequence and the curtain used when signing in/out.
// Pure decoration: nothing here carries information, and reduced-motion turns all of it off.
import { reducedMotion } from "./motion.js";
import { esc, icons } from "./ui.js";

const PALETTE = {
  dark: [[167, 157, 255], [34, 211, 238], [245, 196, 94]],
  light: [[85, 70, 232], [14, 116, 144], [180, 120, 20]],
};

// Points live in a box x,y in [-1, 1], z in (0, 1]; z shrinking moves them towards the viewer.
function makeWorld(canvas, { alwaysDark = false } = {}) {
  const context = canvas.getContext("2d");
  const points = [];
  let width = 0;
  let height = 0;
  let speed = 1;
  let goal = 1;
  let frame = 0;
  let alive = true;
  const eye = { x: 0, y: 0, tx: 0, ty: 0 };

  const place = (point, anywhere) => {
    point.x = Math.random() * 2 - 1;
    point.y = Math.random() * 2 - 1;
    point.z = anywhere ? 0.08 + Math.random() * 0.92 : 1;
    point.tone = Math.random() < 0.12 ? 2 : Math.random() < 0.5 ? 0 : 1;
    point.px = null;
    return point;
  };

  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const wanted = Math.round(Math.min(130, Math.max(36, (width * height) / 15000)));
    while (points.length < wanted) points.push(place({}, true));
    points.length = wanted;
    if (reducedMotion()) draw();
  }

  function draw() {
    const palette = PALETTE[alwaysDark || document.documentElement.dataset.theme !== "light" ? "dark" : "light"];
    const strength = palette === PALETTE.light ? 0.75 : 1;
    context.clearRect(0, 0, width, height);
    eye.x += (eye.tx - eye.x) * 0.05;
    eye.y += (eye.ty - eye.y) * 0.05;
    speed += (goal - speed) * 0.06;
    const cx = width / 2 + eye.x * 26;
    const cy = height / 2 + eye.y * 18;
    const reach = Math.max(width, height) * 0.62;
    const fast = speed > 4;
    const seen = [];
    for (const point of points) {
      point.z -= 0.00042 * speed;
      const x = cx + (point.x / point.z) * reach * 0.5;
      const y = cy + (point.y / point.z) * reach * 0.5;
      if (point.z <= 0.03 || x < -60 || x > width + 60 || y < -60 || y > height + 60) {
        place(point, false);
        continue;
      }
      const near = 1 - point.z;
      const alpha = Math.min(1, near * 1.5) * (fast ? 0.9 : 0.55) * strength;
      const [r, g, b] = palette[point.tone];
      if (fast && point.px !== null) {
        context.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
        context.lineWidth = 0.6 + near * 1.8;
        context.beginPath();
        context.moveTo(point.px, point.py);
        context.lineTo(x, y);
        context.stroke();
      } else {
        context.fillStyle = `rgba(${r},${g},${b},${alpha})`;
        context.beginPath();
        context.arc(x, y, 0.5 + near * 1.9, 0, 6.2832);
        context.fill();
      }
      point.px = x;
      point.py = y;
      if (!fast && near > 0.35) seen.push(x, y, near);
    }
    // Threads between neighbours: the "evidence board" hint. Skipped while warping.
    context.lineWidth = 1;
    const [r, g, b] = palette[0];
    for (let i = 0; i < seen.length; i += 3) {
      for (let j = i + 3; j < seen.length; j += 3) {
        const dx = seen[i] - seen[j];
        const dy = seen[i + 1] - seen[j + 1];
        const distance = dx * dx + dy * dy;
        if (distance < 13000) {
          context.strokeStyle = `rgba(${r},${g},${b},${(1 - distance / 13000) * 0.16 * strength})`;
          context.beginPath();
          context.moveTo(seen[i], seen[i + 1]);
          context.lineTo(seen[j], seen[j + 1]);
          context.stroke();
        }
      }
    }
  }

  function loop() {
    if (!alive) return;
    if (!document.hidden && canvas.isConnected) draw();
    frame = requestAnimationFrame(loop);
  }

  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();
  if (!reducedMotion()) frame = requestAnimationFrame(loop);

  return {
    look(x, y) { eye.tx = x; eye.ty = y; },
    // Rush forward for `ms`, then settle back to the idle drift.
    warp(ms, force = 46) {
      goal = force;
      for (const point of points) point.px = null;
      setTimeout(() => { goal = 1; }, ms);
    },
    destroy() {
      alive = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
    },
  };
}

let world = null;

// The page-wide world. Also lights whichever card the pointer is over.
export function mountWorld() {
  if (world) return world;
  const canvas = document.createElement("canvas");
  canvas.className = "world";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);
  world = makeWorld(canvas);
  world.canvas = canvas;

  let lit = null;
  window.addEventListener("pointermove", (event) => {
    world.look((event.clientX / window.innerWidth) * 2 - 1, (event.clientY / window.innerHeight) * 2 - 1);
    const target = event.target instanceof Element ? event.target.closest(".card, .dropzone, .auth-box") : null;
    if (lit && lit !== target) {
      lit.style.removeProperty("--px");
      lit.style.removeProperty("--py");
    }
    lit = target;
    if (!target) return;
    const box = target.getBoundingClientRect();
    target.style.setProperty("--px", `${event.clientX - box.left}px`);
    target.style.setProperty("--py", `${event.clientY - box.top}px`);
  }, { passive: true });
  return world;
}

// A second, always-dark world for the sign-in scene. Returns its handle; call destroy() on leave.
export const sceneWorld = (canvas) => makeWorld(canvas, { alwaysDark: true });

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - (-2 * p + 2) ** 3 / 2);

// Opens a round hole in `node` from (x, y) until the whole screen shows through.
function openHole(node, x, y, ms) {
  const rim = document.createElement("i");
  rim.className = "hole-rim";
  document.body.append(rim);
  const reach = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y)) + 60;
  const started = performance.now();
  return new Promise((resolve) => {
    const step = (now) => {
      const progress = Math.min(1, (now - started) / ms);
      const radius = ease(progress) * reach;
      const mask = `radial-gradient(circle at ${x}px ${y}px, transparent ${radius}px, #000 ${radius + 36}px)`;
      node.style.webkitMaskImage = mask;
      node.style.maskImage = mask;
      rim.style.cssText = `left:${x - radius}px;top:${y - radius}px;width:${radius * 2}px;height:${radius * 2}px;opacity:${1 - progress}`;
      if (progress < 1) requestAnimationFrame(step); else { rim.remove(); resolve(); }
    };
    requestAnimationFrame(step);
  });
}

// A dark backdrop and, above the rushing points, what is written on it. Two layers so that the
// world can pass between them.
function curtain(className, html) {
  const node = document.createElement("div");
  node.className = `curtain ${className}`;
  const core = document.createElement("div");
  core.className = `curtain-core ${className}`;
  core.innerHTML = html;
  document.body.append(node, core);
  const close = () => { node.remove(); core.remove(); };
  return { node, core, close };
}

const halo = `<span class="halo" aria-hidden="true"><i></i><i></i><i></i></span>`;
const letters = (text) => [...text].map((ch, i) => (ch === " " ? " " : `<span style="--i:${i}">${esc(ch)}</span>`)).join("");

const INTRO_KEY = "dfd.intro";

// The opening: the mark arrives out of the dark, the title assembles, a short loader follows the
// real start-up, then the view flies through the lens into the application. Played once per
// browser tab; any key or click skips it. Returns null when it should not play.
export function playIntro(texts) {
  if (reducedMotion() || sessionStorage.getItem(INTRO_KEY)) return null;
  sessionStorage.setItem(INTRO_KEY, "1");
  const { node, core, close } = curtain("intro", `
    <div class="intro-mark">${halo}${icons.logo}</div>
    <div class="intro-title" aria-label="${esc(texts.name)}">${letters(texts.name.toUpperCase())}</div>
    <div class="intro-tag">${esc(texts.tagline)}</div>
    <div class="intro-load"><i></i></div>
    <div class="intro-status" aria-live="polite">${esc(texts.loading)}</div>
    <div class="intro-skip">${esc(texts.skip)}</div>`);
  const bar = core.querySelector(".intro-load > i");
  const status = core.querySelector(".intro-status");
  const started = performance.now();
  let skipped = false;
  const skip = () => { skipped = true; };
  window.addEventListener("pointerdown", skip, { once: true });
  window.addEventListener("keydown", skip, { once: true });
  world?.canvas.classList.add("front");
  world?.warp(900, 30);
  bar.style.width = "38%";

  return {
    step(text, fraction) {
      status.textContent = text;
      bar.style.width = `${Math.round(fraction * 100)}%`;
    },
    // Call when the application underneath is rendered.
    async finish(text) {
      status.textContent = text;
      bar.style.width = "100%";
      const rest = 2700 - (performance.now() - started);
      for (let left = rest; left > 0 && !skipped; left -= 60) await wait(60);
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
      const mark = core.querySelector(".intro-mark").getBoundingClientRect();
      core.classList.add("leaving");
      world?.warp(650);
      await wait(140);
      await openHole(node, mark.left + mark.width * 0.24, mark.top + mark.height * 0.42, 760);
      close();
      world?.canvas.classList.remove("front");
    },
  };
}

// The passage between the sign-in scene and the application (and back). The curtain closes from
// (x, y), `action` swaps the screen behind it, then it opens again from the centre.
export async function transit({ title, sub, x, y }, action) {
  if (reducedMotion()) { await action(); return; }
  const { node, core, close } = curtain("transit", `
    <div class="transit-mark">${halo}${icons.logo}</div>
    <div class="transit-title">${esc(title)}</div>
    <div class="transit-sub">${esc(sub)}</div>`);
  const reach = Math.hypot(window.innerWidth, window.innerHeight);
  const closing = node.animate(
    [{ clipPath: `circle(0px at ${x}px ${y}px)` }, { clipPath: `circle(${reach}px at ${x}px ${y}px)` }],
    { duration: 520, easing: "cubic-bezier(.6, 0, .3, 1)" },
  );
  world?.canvas.classList.add("front");
  world?.warp(1500);
  await closing.finished.catch(() => {});
  await action();
  await wait(1150);
  core.classList.add("leaving");
  await wait(120);
  await openHole(node, window.innerWidth / 2, window.innerHeight * 0.42, 700);
  close();
  world?.canvas.classList.remove("front");
}
