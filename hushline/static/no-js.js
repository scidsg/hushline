try {
  if (sessionStorage.getItem("hushline:first-load-splash-seen") === "true") {
    document.documentElement.classList.add("splash-seen");
  }
} catch {}

document.documentElement.classList.remove("no-js");
