// Landing: decorative waveform bars + scroll reveal (IntersectionObserver; no scroll hijacking).
(function () {
  const bars = document.querySelector(".wavebars");
  if (bars) {
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;   // deterministic decoration, not data
    for (let i = 0; i < 64; i++) {
      const e = document.createElement("i");
      const env = Math.sin((i / 64) * Math.PI) * .7 + .3;
      e.style.setProperty("--h", Math.round(10 + rnd() * 78 * env) + "%");
      e.style.setProperty("--d", (rnd() * 2).toFixed(2) + "s");
      bars.appendChild(e);
    }
  }
  const els = document.querySelectorAll(".reveal");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) { els.forEach(e => e.classList.add("in")); return; }
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .12 });
  els.forEach(e => io.observe(e));
})();
