(function () {
  const script = document.currentScript;
  const MESSAGE_TYPE = "hushline:embed:height";
  const MIN_HEIGHT = 320;
  const MAX_HEIGHT = 4096;
  const HEIGHT_STEP = 32;

  function allowedOrigins() {
    try {
      const parsed = JSON.parse(script?.dataset.allowedOrigins || "[]");
      return Array.isArray(parsed)
        ? parsed.filter((origin) => typeof origin === "string" && origin.length > 0)
        : [];
    } catch {
      return [];
    }
  }

  const targetOrigins = allowedOrigins();
  if (window.parent === window || targetOrigins.length === 0) {
    return;
  }

  function boundedHeight(height) {
    const rounded = Math.ceil(height / HEIGHT_STEP) * HEIGHT_STEP;
    return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, rounded));
  }

  function contentRoot() {
    return document.querySelector(".embed-shell") || document.body || document.documentElement;
  }

  function contentHeight() {
    const root = contentRoot();
    const rect = root.getBoundingClientRect();
    const top = rect.top + window.scrollY;
    return Math.max(
      rect.bottom + window.scrollY,
      top + (root.scrollHeight || 0),
    );
  }

  let lastHeight = 0;
  let pendingAnimationFrame = 0;

  function publishHeight() {
    pendingAnimationFrame = 0;
    const height = boundedHeight(contentHeight());
    if (height === lastHeight) {
      return;
    }
    lastHeight = height;
    const message = {
      type: MESSAGE_TYPE,
      version: 1,
      height,
    };
    for (const origin of targetOrigins) {
      window.parent.postMessage(message, origin);
    }
  }

  function queueHeightPublish() {
    if (pendingAnimationFrame) {
      return;
    }
    pendingAnimationFrame = window.requestAnimationFrame(publishHeight);
  }

  function start() {
    queueHeightPublish();
    window.addEventListener("load", queueHeightPublish);
    window.addEventListener("pageshow", queueHeightPublish);

    if ("ResizeObserver" in window) {
      const resizeObserver = new ResizeObserver(queueHeightPublish);
      resizeObserver.observe(contentRoot());
      if (document.body) {
        resizeObserver.observe(document.body);
      }
    }

    if ("MutationObserver" in window && document.body) {
      const mutationObserver = new MutationObserver(queueHeightPublish);
      mutationObserver.observe(document.body, {
        attributes: true,
        childList: true,
        subtree: true,
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
