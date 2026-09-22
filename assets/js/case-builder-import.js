import { requestCaseDraft } from "./case-builder-handoff";

export function bindCaseImport() {
  const root = document.getElementById("case-import");
  if (!root || root.dataset.bound) return;
  root.dataset.bound = "true";
  const status = document.getElementById("case-import-status");
  const retry = document.getElementById("case-import-retry");
  const csrf = root.querySelector("input[name='csrf_token']").value;
  let draft = "";
  let busy = false;
  async function save() {
    if (!draft || busy) return;
    busy = true;
    retry.hidden = true;
    status.textContent = "Encrypting your case for your inbox…";
    try {
      const keys = window.HushLineChatKeys;
      const key = await keys.fetchChatKey("/settings/chat-key.json");
      if (!key || !(await keys.signingPrivateKeyForChatKey(key)))
        throw new Error("locked");
      const headers = {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      };
      const prepared = await fetch(root.dataset.url, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: "{}",
      });
      if (!prepared.ok) throw new Error("unavailable");
      const target = await prepared.json();
      if (!target.saved) {
        const participantId = String(target.participant_key.participant_id);
        const encrypted = await keys.encryptForPublicKey(
          JSON.stringify({
            content: draft,
            created_at: new Date().toISOString(),
          }),
          target.participant_key,
          {
            purpose: "hushline.chat.message",
            conversation_public_id: target.conversation_public_id,
            sender_participant_id: participantId,
          },
        );
        const response = await fetch(target.message_url, {
          method: "POST",
          credentials: "same-origin",
          headers,
          body: JSON.stringify({
            case_import: true,
            encrypted_copies: { [participantId]: encrypted },
          }),
        });
        if (!response.ok) throw new Error("unsaved");
      }
      draft = "";
      window.location.replace(target.inbox_url);
    } catch {
      status.textContent =
        "Your case could not be saved. Keep Case Builder open and try again. Your original outline is still in Case Builder.";
      retry.hidden = false;
    } finally {
      busy = false;
    }
  }
  retry.addEventListener("click", save);
  requestCaseDraft((text) => {
    draft = text;
    void save();
  });
  window.addEventListener("pagehide", () => {
    draft = "";
  });
}
