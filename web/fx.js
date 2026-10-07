(() => {
  "use strict";
  // Gentle cursor-following background. Skipped on touch screens and for people who prefer reduced motion.
  if (!window.matchMedia("(pointer: fine)").matches) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const root = document.documentElement;
  const target = { x: window.innerWidth / 2, y: window.innerHeight * 0.22 };
  const current = { x: target.x, y: target.y };
  let frame = null;

  function tick() {
    current.x += (target.x - current.x) * 0.08;
    current.y += (target.y - current.y) * 0.08;
    root.style.setProperty("--mx", current.x.toFixed(1) + "px");
    root.style.setProperty("--my", current.y.toFixed(1) + "px");
    root.style.setProperty("--px", (current.x / window.innerWidth - 0.5).toFixed(3));
    root.style.setProperty("--py", (current.y / window.innerHeight - 0.5).toFixed(3));
    const moving = Math.abs(target.x - current.x) > 0.3 || Math.abs(target.y - current.y) > 0.3;
    frame = moving ? requestAnimationFrame(tick) : null;
  }

  window.addEventListener("pointermove", (event) => {
    target.x = event.clientX;
    target.y = event.clientY;
    if (frame === null) frame = requestAnimationFrame(tick);
  }, { passive: true });

  tick();
})();