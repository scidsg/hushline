// Drafts travel only between this page and the exact tab opened by the user.
// No draft text is put in a URL, browser storage, or a network request.
const requestType = "hushline-case-draft-request";
const responseType = "hushline-case-draft-response";

export function createCaseHandoff() {
  const pending = new Map();
  const origin = window.location.origin;
  function receive(event) {
    if (event.origin !== origin || event.data?.type !== requestType) return;
    const draft = pending.get(event.source);
    if (!draft) return;
    try {
      const destination = new URL(event.source.location.href);
      if (
        destination.origin !== origin ||
        !(
          destination.pathname.startsWith("/to/") ||
          (draft.selfImport && destination.pathname === "/case-builder/import")
        )
      )
        return;
      event.source.postMessage(
        { type: responseType, text: draft.text },
        origin,
      );
      pending.delete(event.source);
      clearTimeout(draft.timer);
    } catch {
      // A tab on a different origin is never allowed to receive a draft.
    }
  }
  window.addEventListener("message", receive);
  function clear() {
    for (const draft of pending.values()) clearTimeout(draft.timer);
    pending.clear();
  }
  window.addEventListener("pagehide", clear);
  return {
    open(url, text) {
      const destination = new URL(url, window.location.href);
      if (destination.origin !== origin) throw new Error("Invalid destination");
      const tab = window.open(destination.href, "_blank");
      if (!tab) return false;
      const timer = setTimeout(() => pending.delete(tab), 60 * 60 * 1000);
      pending.set(tab, {
        text,
        timer,
        selfImport: destination.pathname === "/case-builder/self",
      });
      return true;
    },
    clear,
  };
}

export function requestCaseDraft(onDraft) {
  const parent = window.opener;
  if (!parent) return;
  const origin = window.location.origin;
  try {
    if (
      parent.location.origin !== origin ||
      parent.location.pathname !== "/case-builder"
    )
      return;
  } catch {
    return;
  }
  function receive(event) {
    if (
      event.source !== parent ||
      event.origin !== origin ||
      event.data?.type !== responseType
    )
      return;
    if (
      typeof event.data.text !== "string" ||
      !event.data.text.trim() ||
      event.data.text.length > 50000
    )
      return;
    window.removeEventListener("message", receive);
    onDraft(event.data.text);
    window.opener = null;
  }
  window.addEventListener("message", receive);
  parent.postMessage({ type: requestType }, origin);
}

export function receiveCaseDraft() {
  const fields = Array.from(document.querySelectorAll("#messageForm textarea"));
  const field =
    fields.find((item) => item.dataset.label?.toLowerCase() === "message") ||
    (fields.length === 1 ? fields[0] : null);
  if (!field || field.disabled || field.value) return;
  requestCaseDraft((text) => {
    if (!field.value) {
      field.value = text;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      const notice = document.createElement("p");
      notice.className = "contextBanner";
      notice.setAttribute("role", "status");
      notice.textContent =
        "Your Case Builder outline is ready. Review the recipient and message before sending.";
      field.closest(".field-group").prepend(notice);
    }
  });
}
