(() => {
  // Simple visual model: sunrise=06:00, sunset=18:00, noon=12:00
  const sunrise = 6.0;
  const sunset = 18.0;

  const root = document.documentElement;

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function localHours() {
    const d = new Date();
    return d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600;
  }

  function computeShadow(hours) {
    const dayT = (hours - sunrise) / (sunset - sunrise);
    const inDay = dayT >= 0 && dayT <= 1;

    // sunrise -> right (sun), noon -> overhead, sunset -> left (sun)
    // shadows are opposite the sun, so we flip x later
    const az = (dayT - 1.0) * Math.PI;
    const elev = Math.sin(clamp(dayT, 0, 1) * Math.PI);

    const minLen = 6;
    const maxLen = 24;
    const len = inDay ? clamp(maxLen * (1 - elev) + minLen, minLen, maxLen) : 12;

    // Flip x so sunrise shadow goes LEFT, afternoon shadow goes RIGHT
    const dx = inDay ? -Math.cos(az + Math.PI) : -0.4;
    const dy = inDay ?  Math.sin(az + Math.PI) :  0.6;

    const x = Math.round(dx * len);
    const y = Math.round(dy * len);

    const blur = inDay ? Math.round(10 + (1 - elev) * 10) : 16;
    const spread = 0;

    const alpha = inDay ? (0.08 + (1 - elev) * 0.06) : 0.12;

    return `${x}px ${y}px ${blur}px ${spread}px rgba(0,0,0,${alpha.toFixed(3)})`;
  }

  function apply() {
    root.style.setProperty("--shadow-dynamic", computeShadow(localHours()));
  }

  apply();
  setInterval(apply, 60_000);

  window.addEventListener("visibilitychange", () => {
    if (!document.hidden) apply();
  });
})();
