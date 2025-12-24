// time_shadows.js
(() => {
  // Simple visual model: sunrise=06:00, sunset=18:00
  const sunrise = 6.0;
  const sunset = 18.0;

  // DEBUG: set to a number (0–24) to force a specific time, or null for real time
  const DEBUG_HOUR = 6;

  const root = document.documentElement;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // Container: deeper, softer, more grounded
  const containerProfile = {
    minLen: 6,
    maxLen: 12,
    nightLen: 6,

    horizonA: 0.55,
    horizonB: 0.45,

    blurMin: 12,
    blurMax: 22,
    nightBlur: 18,

    spreadMin: -2,
    spreadMax: -6,
    nightSpread: -6,

    alphaMin: 0.08,
    alphaMax: 0.12,
    nightAlpha: 0.12,

    nightDx: -0.4,
    nightDy: 0.6,
  };

  // Cards: lighter, tighter, closer to surface
  const cardProfile = {
    minLen: 2,
    maxLen: 6,
    nightLen: 4,

    horizonA: 0.3,
    horizonB: 0.25,

    blurMin: 5,
    blurMax: 9,
    nightBlur: 7,

    spreadMin: 0,
    spreadMax: -1,
    nightSpread: 0,

    alphaMin: 0.03,
    alphaMax: 0.065,
    nightAlpha: 0.085,

    nightDx: -0.25,
    nightDy: 0.45,
  };

  let needsPaintNudge = true;

  function localHours() {
    if (DEBUG_HOUR !== null) return DEBUG_HOUR;
    const d = new Date();
    return d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600;
  }

  function setThemeByTime(hours) {
    const inDay = hours >= sunrise && hours < sunset;
    root.classList.toggle("dark", !inDay);
    root.classList.toggle("light", inDay);
  }

  function computeShadowParts(hours, p) {
    const dayT = (hours - sunrise) / (sunset - sunrise);
    const inDay = dayT >= 0 && dayT <= 1;

    if (!inDay) {
      return {
        x: Math.round(p.nightDx * p.nightLen),
        y: Math.round(p.nightDy * p.nightLen),
        blur: p.nightBlur,
        spread: p.nightSpread,
        alpha: p.nightAlpha,
      };
    }

    const az = (dayT - 1.0) * Math.PI;
    const elev = Math.sin(clamp(dayT, 0, 1) * Math.PI);

    const horizonScale = p.horizonA + p.horizonB * elev;
    const len = clamp(
      p.minLen + (p.maxLen - p.minLen) * (1 - elev) * horizonScale,
      p.minLen,
      p.maxLen
    );

    const x = Math.round(-Math.cos(az + Math.PI) * len);
    const y = Math.round(Math.sin(az + Math.PI) * len);

    const blur = Math.round(
      p.blurMin + (1 - elev) * (p.blurMax - p.blurMin)
    );

    const spread = Math.round(
      p.spreadMin + (1 - elev) * (p.spreadMax - p.spreadMin)
    );

    const alpha =
      p.alphaMin + (1 - elev) * (p.alphaMax - p.alphaMin);

    return { x, y, blur, spread, alpha };
  }

  function formatShadow({ x, y, blur, spread, alpha }) {
    return `${x}px ${y}px ${blur}px ${spread}px rgba(0,0,0,${alpha.toFixed(3)})`;
  }

  function paintNudgeOnce() {
    if (!needsPaintNudge) return;
    needsPaintNudge = false;

    const paintEl =
      document.querySelector(".container") ||
      document.querySelector("main") ||
      document.body;

    if (!paintEl) return;

    void paintEl.getBoundingClientRect();
    paintEl.style.webkitTransform = "translateZ(0)";
    requestAnimationFrame(() => {
      paintEl.style.webkitTransform = "";
    });
  }

  function apply() {
    const h = localHours();
    setThemeByTime(h);

    const containerShadow = computeShadowParts(h, containerProfile);
    const cardShadow = computeShadowParts(h, cardProfile);

    root.style.setProperty("--shadow-dynamic", formatShadow(containerShadow));
    root.style.setProperty(
      "--shadow-dynamic-card",
      formatShadow(cardShadow)
    );

    paintNudgeOnce();
  }

  // Init
  apply();

  // Safari / first-paint stabilization
  requestAnimationFrame(() => {
    needsPaintNudge = true;
    apply();
    requestAnimationFrame(apply);
  });

  window.addEventListener(
    "load",
    () => {
      needsPaintNudge = true;
      apply();
    },
    { once: true }
  );

  window.addEventListener("pageshow", (e) => {
    if (e.persisted) {
      needsPaintNudge = true;
      apply();
    }
  });

  setInterval(() => {
    needsPaintNudge = true;
    apply();
  }, 60_000);

  window.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      needsPaintNudge = true;
      apply();
    }
  });
})();
