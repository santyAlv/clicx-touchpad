const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

function field(canvas, { color, idle, reactive, cols, rows, track }) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const pointer = { x: -1e3, y: -1e3, active: false };
  let frame = 0;
  let running = false;

  const size = () => canvas.getBoundingClientRect();

  const resize = () => {
    const rect = size();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    paint(rect.width, rect.height);
  };

  const paint = (w, h) => {
    ctx.clearRect(0, 0, w, h);
    if (w < 8 || h < 8) return;
    const padX = w * 0.08;
    const padY = h * 0.08;
    const stepX = (w - padX * 2) / Math.max(1, cols - 1);
    const stepY = (h - padY * 2) / Math.max(1, rows - 1);
    const reach = Math.max(stepX, stepY) * 3.4;

    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const x = padX + c * stepX;
        const y = padY + r * stepY;
        const dist = Math.hypot(x - pointer.x, y - pointer.y);
        const t = pointer.active ? Math.max(0, 1 - dist / reach) : 0;
        const wave = reduced.matches
          ? 0
          : Math.sin(frame * 0.012 + c * 0.35 + r * 0.22) * 0.18;
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.2 + t * 0.75;
        ctx.arc(x, y, idle + (reactive - idle) * t * t + wave * idle, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  };

  const tick = () => {
    running = true;
    frame += 1;
    const rect = size();
    paint(rect.width, rect.height);
    if (!reduced.matches) requestAnimationFrame(tick);
    else running = false;
  };

  const onMove = (event) => {
    const rect = size();
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    pointer.active = true;
    if (!running) tick();
  };

  const onLeave = () => {
    pointer.active = false;
    pointer.x = -1e3;
    pointer.y = -1e3;
  };

  const root = track ?? canvas;
  root.addEventListener("pointermove", onMove);
  root.addEventListener("pointerleave", onLeave);
  window.addEventListener("resize", resize);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resize).observe(canvas);
  }
  resize();
  tick();
}

const hero = document.querySelector(".hero");
const heroCanvas = document.querySelector("#dot-field");
const padCanvas = document.querySelector("#pad-field");

if (heroCanvas instanceof HTMLCanvasElement && hero instanceof HTMLElement) {
  field(heroCanvas, {
    color: "#618764",
    idle: 1.15,
    reactive: 4.2,
    cols: 28,
    rows: 18,
    track: hero,
  });
}

if (padCanvas instanceof HTMLCanvasElement && hero instanceof HTMLElement) {
  field(padCanvas, {
    color: "#C5D4B0",
    idle: 1.7,
    reactive: 5.6,
    cols: 10,
    rows: 15,
    track: hero,
  });
}
