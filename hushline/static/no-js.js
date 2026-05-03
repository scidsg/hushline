try {
  const splashLogo = document.querySelector(
    'meta[name="first-load-splash-logo-src"]',
  );
  const splashLogoSrc = splashLogo
    ? splashLogo.getAttribute("content") || ""
    : "";
  const seenSplashLogoSrc =
    sessionStorage.getItem("hushline:first-load-splash-logo-src") || "";

  if (
    sessionStorage.getItem("hushline:first-load-splash-seen") === "true" &&
    seenSplashLogoSrc === splashLogoSrc
  ) {
    document.documentElement.classList.add("splash-seen");
  }
} catch {}

document.documentElement.classList.remove("no-js");
