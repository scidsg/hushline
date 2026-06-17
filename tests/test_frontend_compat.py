import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_package_json_declares_node_20_plus() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    engines = package_json.get("engines", {})
    assert engines.get("node") == ">=20"


def test_theme_select_rules_set_closed_control_text_color() -> None:
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert re.search(
        r"select\s*\{\s*appearance: none;\s*"
        r'background-image: url\("\.\./img/dropdown\.png"\);\s*'
        r"color: var\(--color-text\);\s*"
        r"-webkit-text-fill-color: currentColor;",
        scss,
    )
    assert re.search(
        r"select\s*\{\s*appearance: none;\s*"
        r'background-image: url\("\.\./img/dropdown-dm\.png"\);\s*'
        r"color: var\(--color-text-dark\);\s*"
        r"-webkit-text-fill-color: currentColor;",
        scss,
    )


def test_webpack_compose_services_use_lockfile_guard_script() -> None:
    script = (ROOT / "scripts/webpack_dev_start.sh").read_text(encoding="utf-8")

    assert "wait_for_file /app/package.json" in script
    assert "wait_for_file /app/package-lock.json" in script
    assert "npm_config_update_notifier=false npm ci --no-audit --no-fund" in script
    assert "exec npm run build:dev" in script

    for compose_name in (
        "docker-compose.yaml",
        "docker-compose.personal-server.yaml",
        "docker-compose.stripe.yaml",
    ):
        compose = (ROOT / compose_name).read_text(encoding="utf-8")
        assert "./scripts/webpack_dev_start.sh" in compose
        assert "npm ci --no-audit --no-fund" not in compose


def test_static_js_bundles_avoid_eval_wrappers() -> None:
    webpack_config = (ROOT / "webpack.config.js").read_text(encoding="utf-8")

    assert 'devtool: isDev ? "source-map" : false,' in webpack_config

    for static_js in sorted((ROOT / "hushline/static/js").glob("*.js")):
        bundle = static_js.read_text(encoding="utf-8")
        assert "eval(" not in bundle, static_js.name
        assert "webpack://" not in bundle, static_js.name


def test_embed_resize_bundle_is_declared_and_height_only() -> None:
    webpack_config = (ROOT / "webpack.config.js").read_text(encoding="utf-8")
    js = (ROOT / "assets/js/embed-resize.js").read_text(encoding="utf-8")

    assert '"embed-resize",' in webpack_config
    assert 'const MESSAGE_TYPE = "hushline:embed:height";' in js
    assert "const MIN_HEIGHT = 320;" in js
    assert "const MAX_HEIGHT = 4096;" in js
    assert "const HEIGHT_STEP = 32;" in js
    assert 'document.querySelector(".embed-shell")' in js
    assert "root.getBoundingClientRect()" in js
    assert "window.parent.postMessage(message, origin)" in js
    assert "ResizeObserver" in js
    assert "MutationObserver" in js
    assert "field_" not in js
    assert "csrf" not in js.lower()
    assert "cipher" not in js.lower()
    assert "reply" not in js.lower()


def test_client_side_encryption_has_platform_guards() -> None:
    js = (ROOT / "assets/js/client-side-encryption.js").read_text(encoding="utf-8")

    assert "function assertClientCryptoSupport()" in js
    assert "function getRecipientPublicKeys()" in js
    assert "recipientPublicKeysEl.textContent" in js
    assert "function getRecipientPublicKeyEntries()" in js
    assert "recipientPublicKeyEntriesEl.textContent" in js
    assert "Number.isInteger(entry.id)" in js
    assert "window.isSecureContext" in js
    assert "window.crypto.subtle" in js
    assert "window.ReadableStream" in js
    assert 'typeof BigInt === "undefined"' in js
    assert 'typeof openpgp === "undefined"' in js
    assert "function getDicewareWords()" in js
    assert "Encryption module failed to initialize." in js
    assert "Encryption padding dictionary is unavailable." in js
    assert "Encrypted email body field is missing." in js
    assert "const recipientPublicKeys = getRecipientPublicKeys();" in js
    assert "const recipientPublicKeyEntries = getRecipientPublicKeyEntries();" in js
    assert "const encryptedEmailFieldsByRecipient = {};" in js
    assert "encrypted_email_fields_by_recipient" in js
    assert "assertClientCryptoSupport();" in js
    assert "async function submitEncryptedForm(form)" in js
    assert "body: new FormData(form)" in js
    assert 'credentials: "same-origin"' in js
    assert 'Accept: "text/html"' in js
    assert "response.url.startsWith(window.location.origin)" in js
    assert 'window.history.replaceState({}, "", response.url);' in js
    assert "document.write(html);" in js
    assert "form.submit();" not in js


def test_client_side_encryption_prepares_chat_conversation_copies() -> None:
    js = (ROOT / "assets/js/client-side-encryption.js").read_text(encoding="utf-8")
    profile_template = (ROOT / "hushline/templates/profile.html").read_text(encoding="utf-8")
    embed_template = (ROOT / "hushline/templates/embed_profile.html").read_text(encoding="utf-8")

    assert "async function encryptForChatPublicKey(" in js
    assert 'algorithm: "ECDH-P256-AES-GCM"' in js
    assert 'purpose: "hushline.chat.initial_message"' in js
    assert "initial_conversation_nonce: initialConversationNonce" in js
    assert "sender_public_signing_key_fingerprint" in js
    assert "recipient_public_key_fingerprint" in js
    assert "canonicalStringify(envelopeContext)" in js
    assert "await signChatEnvelope(envelope, signingKey)" in js
    assert "signingPrivateKeyForChatKey" in js
    assert 'const sessionStorageKey = "hushline:chat-private-jwk";' in js
    assert 'getChatPublicKey("recipientChatPublicKey")' in js
    assert 'getChatKeyDescriptor("recipientChatKey")' in js
    assert 'getChatKeyDescriptor("senderChatKey")' in js
    assert "recipient: await encryptForChatPublicKey(" in js
    assert "encryptedCopies.sender = await encryptForChatPublicKey(" in js
    assert "function replaceSubmittedFieldsWithConversationPlaceholder()" in js
    assert 'hiddenInput.value = "Stored in encrypted conversation.";' in js
    assert "if (recipientPublicKeys.length === 0)" in js
    assert "replaceSubmittedFieldsWithConversationPlaceholder();" in js
    assert "encrypted_conversation_copies" in js
    assert "plaintext_private_key" not in js
    assert "decrypted_private_key" not in js
    assert "derived wrapping key" not in js.lower()
    assert 'id="senderChatPublicKey"' in profile_template
    assert 'id="senderChatPublicKey"' in embed_template
    assert 'id="recipientChatKey"' in profile_template
    assert 'id="senderChatKey"' in profile_template


def test_chat_key_lifecycle_imports_private_key_for_message_decryption() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    static_js = (ROOT / "hushline/static/js/chat-key-lifecycle.js").read_text(encoding="utf-8")

    assert "unlockedChatPrivateKey = await importPrivateKey(" in js
    assert "conversationMessageSenderSigningFingerprintFromPayload" in js
    assert "conversationMessageSenderSigningFingerprintFromPayload" in static_js
    assert "participantPublicKeyBySigningFingerprint" in js
    assert "participantPublicKeyBySigningFingerprint" in static_js
    assert "conversationParticipantSigningPublicKeys" in js
    assert "conversationParticipantSigningPublicKeys" in static_js
    assert "privateKeyBundle.ecdh_private_jwk" in js
    assert "unlockedChatSigningPrivateKey = await importSigningPrivateKey(" in js
    assert "privateKeyBundle.signing_private_jwk" in js
    assert 'key_ops: ["deriveKey"]' in js
    assert '["deriveKey"]' in js
    assert 'key_ops: ["sign"]' in js
    assert '["sign"]' in js
    assert "deriveChatMessageKey(" in js
    assert "decryptChatCiphertext" in js


def test_settings_chat_key_provisioning_generates_decryptable_ecdh_key() -> None:
    js = (ROOT / "assets/js/settings.js").read_text(encoding="utf-8")

    assert 'name: "ECDH"' in js
    assert '["deriveKey"]' in js
    assert '["deriveBits"]' not in js
    assert 'form.dataset.chatKeyAction === "rotate"' in js
    assert "confirm(form.dataset.confirmMessage)" in js
    assert "Rotating chat key..." in js
    assert "Old conversations encrypted to earlier keys are no longer readable." in js


def test_chat_key_lifecycle_restores_unlocked_key_for_authenticated_tab_session() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    login_template = (ROOT / "hushline/templates/login.html").read_text(encoding="utf-8")

    assert 'const sessionStorageKey = "hushline:chat-private-jwk";' in js
    assert 'const legacyBrowserStorageKey = "hushline:chat-private-jwk:browser-session";' in js
    assert "browserStorageMaxAgeMs" not in js
    assert 'const crossTabChannelName = "hushline:chat-key-session";' in js
    assert "new BroadcastChannel(crossTabChannelName)" in js
    assert "sessionStorage.setItem(" in js
    assert "sessionStorage.getItem(sessionStorageKey)" in js
    assert "sessionStorage.removeItem(sessionStorageKey)" in js
    assert "localStorage.setItem" not in js
    assert "localStorage.getItem" not in js
    assert "localStorage.removeItem(legacyBrowserStorageKey)" in js
    assert "restoreConversationFromSession" in js
    assert "restoreUnlockedChatKeyFromOtherTab" in js
    assert "async function signingPrivateKeyForChatKey(chatKey)" in js
    assert "function setConversationSecureBadgeVisible(visible)" in js
    assert "setConversationSecureBadgeVisible(true);" in js
    assert "setConversationSecureBadgeVisible(false);" in js
    assert "ensureChatKeyUnlockedAfterAuth(password, responseDocument)" in js
    assert "provisionChatKey(chatKeyUrl, password, sourceDocument)" in js
    assert "createChatKeyPayload(password)" in js
    assert "populateLoginChatKeyPayload(form, password)" in js
    assert "payloadInput.value = JSON.stringify(created.payload);" in js
    assert 'name="chat_key_payload"' in login_template
    assert 'id="login-chat-key-payload"' in login_template
    assert "pendingLoginPassword" in js
    assert "request-unlocked-chat-key" in js
    assert "unlocked-chat-key" in js
    assert "pendingLoginPassword = null;" in js


def test_conversation_does_not_prompt_for_password_after_login() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    template = (ROOT / "hushline/templates/conversation.html").read_text(encoding="utf-8")

    assert 'id="conversationParticipantSigningPublicKeys"' in template
    assert "conversation-chat-password" not in js
    assert "unlockConversationFromPassword" not in js
    assert "conversation-chat-password" not in template
    assert "Unlock Chat" not in template
    assert "Log out and log back in to unlock chat" not in template
    assert "Log out and log back in to unlock chat" not in js
    assert "Secure chat unavailable" in template
    assert "Messages are encrypted until your browser chat key unlocks." in template


def test_conversation_presence_uses_root_csrf_token() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    template = (ROOT / "hushline/templates/conversation.html").read_text(encoding="utf-8")

    assert 'data-csrf-token="{{ global_csrf_token }}"' in template
    assert 'data-conversation-public-id="{{ conversation.public_id }}"' in template
    assert "data-conversation-id=" not in template
    assert 'const root = document.getElementById("conversation-chat");' in js
    assert 'conversation_public_id: root.dataset.conversationPublicId || ""' in js
    assert "conversation_id: root.dataset.conversationId" not in js
    assert "root?.dataset.csrfToken" in js
    assert "csrfTokenFromDocument()" in js


def test_conversation_chat_uses_full_width_and_dark_mode_styles() -> None:
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")
    composer_block = scss[
        scss.index(".conversation-composer {") : scss.index(
            ".conversation-composer textarea:disabled"
        )
    ]
    mobile_start = scss.index("@media (max-width: 720px)", scss.index(".conversation-composer {"))
    mobile_block = scss[
        mobile_start : scss.index("@media (prefers-color-scheme: dark)", mobile_start)
    ]

    assert ".conversation-page {" in scss
    assert ".conversation-main {" in scss
    assert ".conversation-main .container {" in scss
    assert "body.conversation-body {" in scss
    assert "--conversation-content-max-width: 960px;" in scss
    assert "--conversation-content-padding-inline: max(" in scss
    assert "--conversation-header-offset: 8rem;" in scss
    assert "--conversation-top-offset: calc(105px + env(safe-area-inset-top));" in scss
    assert "height: calc(100vh - var(--conversation-top-offset));" in scss
    assert "min-height: calc(100vh - var(--conversation-top-offset));" in scss
    assert ".banner + header + .conversation-main {" in scss
    assert "@media (max-width: 720px)" in scss
    assert "border: 0;" in scss
    assert "width: 100%;" in scss
    assert "max-width: none;" in scss
    assert "margin: 0;" in scss
    assert "padding-left: 0;" in scss
    assert "padding-right: 0;" in scss
    assert "width: 100vw;" in scss
    assert "padding: 0.75rem var(--conversation-content-padding-inline);" in scss
    assert "padding-top: 8rem;" in scss
    assert "@media (prefers-color-scheme: dark)" in scss
    assert ".conversation-message.is-own-message .conversation-message-body" in scss
    assert "background: var(--color-brand-dark-mid-saturation);" in scss
    assert ".conversation-composer textarea::placeholder" in scss
    assert "width: 100%;" in composer_block
    assert "box-sizing: border-box;" in composer_block
    assert "margin: 0;" in composer_block
    assert "padding: 0.5rem var(--conversation-content-padding-inline) 0.75rem;" in composer_block
    assert "bottom: 0;" in composer_block
    assert "border-radius: 0.25rem;" in composer_block
    assert "border-radius: 0.325rem;" in composer_block
    assert "border-radius: 999px;" not in composer_block
    assert "white-space: nowrap;" in composer_block
    assert ".conversation-thread {" in mobile_block
    assert ".conversation-composer {" in mobile_block
    assert "padding: 0.625rem;" in mobile_block


def test_conversation_secure_badge_sits_behind_chat_messages() -> None:
    template = (ROOT / "hushline/templates/conversation.html").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")
    base_template = (ROOT / "hushline/templates/base.html").read_text(encoding="utf-8")

    assert "{% block body_class %}conversation-body{% endblock %}" in template
    assert "{% block main_class %}conversation-main{% endblock %}" in template
    assert "{% block footer %}{% endblock %}" in template
    assert "{% block footer %}" in base_template
    assert ".conversation-main .container {" in scss
    assert "padding-top: 0;" in scss
    assert "padding-bottom: 0;" in scss
    assert "border-top: 0;" in scss
    assert "border-radius: 0;" in scss
    assert "padding: var(--conversation-top-offset) 0 0;" in scss
    assert 'class="conversation-identity"' in template
    back_link_position = template.index('class="conversation-back-link"')
    display_name_position = template.index("<h1>{{ conversation_name }}</h1>")
    username_position = template.index('class="conversation-profile-link"')
    thread_position = template.index('class="conversation-thread"')
    badge_position = template.index('class="conversation-secure-badge badge"')
    composer_position = template.index('id="conversation-compose-form"')
    assert back_link_position < display_name_position < username_position < thread_position
    assert thread_position < badge_position < composer_position
    assert "href=\"{{ url_for('inbox') }}\"" in template
    assert "Back to Inbox" in template
    assert "conversation.initial_message.username.display_name" not in template
    assert "conversation_username" in template
    assert "🔒 End-to-end encrypted" in template
    assert "Secure Chat" not in template
    assert "Started from a disclosure" not in template
    assert 'class="conversation-secure-badge badge"' in template
    assert 'aria-label="End-to-end encrypted"' in template
    assert "hidden\n      >🔒 End-to-end encrypted" in template
    assert "JavaScript is required for end-to-end encrypted chat." in template
    assert "There is no\n        server-side chat fallback for conversations." in template
    assert ".conversation-secure-badge {" in scss
    assert ".conversation-secure-badge[hidden] {" in scss
    assert "bottom: 5rem;" in scss
    assert "z-index: 0;" in scss
    assert "pointer-events: none;" in scss
    assert "transform: translateX(-50%) scale(0.95);" in scss
    assert ".conversation-noscript {" in scss
    assert ".conversation-back-link {" in scss
    assert ".conversation-message {" in scss
    assert "z-index: 2;" in scss
    assert ".conversation-secure-badge .badge" not in scss


def test_inbox_conversation_unread_dot_precedes_from_label() -> None:
    template = (ROOT / "hushline/templates/inbox.html").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")
    inbox_dark_mode_block = scss[
        scss.index(
            "@media (prefers-color-scheme: dark)",
            scss.index(".inbox-message-link {"),
        ) : scss.index(".settings-main,", scss.index(".inbox-message-link {"))
    ]

    title_position = template.index('class="inbox-message-recipient"')
    dot_position = template.index('class="conversation-unread-dot"', title_position)
    from_position = template.index("From: {{ conversation_name }}", title_position)
    meta_position = template.index('class="inbox-message-summary-meta conversation-summary-meta"')
    tip_date_position = template.index('class="inbox-message-summary-meta"', meta_position + 1)
    assert dot_position < from_position < meta_position
    assert tip_date_position > template.index("To: @{{ message.username.username }}")
    assert ".inbox-message-summary-meta {" in scss
    assert "position: absolute;" in scss
    assert "top: 0.75rem;" in scss
    assert "right: 1rem;" in scss
    assert "display: inline-flex;" in scss
    assert ".conversation-summary .conversation-unread-dot {" in scss
    assert "position: static;" in scss
    assert "width: 0.5rem;" in scss
    assert "height: 0.5rem;" in scss
    assert "margin-right: 0.125rem;" in scss
    assert "vertical-align: 0.06rem;" in scss
    assert ".inbox-main .message-list .message.inbox-message-summary {" in inbox_dark_mode_block
    assert ".inbox-main .message-list .message.conversation-summary {" in inbox_dark_mode_block
    assert "border-color: var(--color-border-dark-1);" in inbox_dark_mode_block
    assert "background: var(--color-dark-bg-alt);" in inbox_dark_mode_block
    assert ".inbox-main .inbox-message-summary time" in inbox_dark_mode_block
    assert "color: var(--color-text-dark-alt);" in inbox_dark_mode_block
    assert ".inbox-main .conversation-summary-avatar {" in inbox_dark_mode_block
    assert ".inbox-main .conversation-summary .conversation-unread-dot {" in inbox_dark_mode_block
    assert (
        "position: absolute;"
        not in scss[
            scss.index(".conversation-summary .conversation-unread-dot {") : scss.index(
                ".conversation-summary-main"
            )
        ]
    )


def test_inbox_polls_for_conversation_updates() -> None:
    js = (ROOT / "assets/js/inbox.js").read_text(encoding="utf-8")

    assert "const inboxPollIntervalMs = 5000;" in js
    assert "fetch(window.location.href" in js
    assert 'replaceIfChanged(".message-list", nextDocument)' in js
    assert 'replaceIfChanged(".inbox-tabs", nextDocument)' in js


def test_conversation_reply_submits_only_encrypted_copies() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    static_js = (ROOT / "hushline/static/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    expected_payload = (
        "body: JSON.stringify({\n          encrypted_copies: encryptedCopies,\n        })"
    )

    assert expected_payload in js
    assert expected_payload in static_js


def test_conversation_polling_does_not_mark_messages_read() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    static_js = (ROOT / "hushline/static/js/chat-key-lifecycle.js").read_text(encoding="utf-8")

    for bundle in (js, static_js):
        assert '"X-Hushline-Conversation-Refresh": "true"' in bundle
    assert "encryptedCopies[String(participantKey.participant_id)]" in js
    assert "encryptedCopies[String(participantKey.participant_id)]" in static_js
    assert "body: JSON.stringify(plaintext" not in js
    assert "body: JSON.stringify({ plaintext" not in js
    assert "body: JSON.stringify({ message" not in js
    assert "body: JSON.stringify({ body" not in js


def test_conversation_replies_and_polling_update_thread_in_place() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")
    static_js = (ROOT / "hushline/static/js/chat-key-lifecycle.js").read_text(encoding="utf-8")

    assert "refreshConversationMessages({ force: true, scroll: true })" in js
    assert 'cache: "no-store"' in js
    assert "await refreshConversationMessages({ force: true });" in js
    assert "bindConversationPolling(root);" in js
    assert "window.setInterval(refreshIfVisible, intervalMs);" in js
    assert "thread.replaceChildren(" in js
    assert "currentCopies.textContent = nextCopies.textContent;" in js
    assert "conversationMessagesSignature(nextDocument)" in js
    assert "window.location.reload()" not in js
    assert "thread.scrollTo({" in js
    assert "top: thread.scrollHeight" in js

    assert "refreshConversationMessages({ force: true, scroll: true })" in static_js
    assert 'cache: "no-store"' in static_js
    assert "await refreshConversationMessages({ force: true });" in static_js
    assert "bindConversationPolling(root);" in static_js
    assert "window.setInterval(refreshIfVisible, intervalMs);" in static_js
    assert "thread.replaceChildren(" in static_js
    assert "window.location.reload()" not in static_js
    assert "thread.scrollTo({" in static_js
    assert "scrollHeight" in static_js


def test_conversation_composer_enter_sends_shift_enter_keeps_newline() -> None:
    js = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")

    assert "handleConversationComposerKeydown" in js
    assert 'event.key !== "Enter" || event.shiftKey || event.isComposing' in js
    assert "event.preventDefault();" in js
    assert "form.requestSubmit();" in js
    assert '.addEventListener("keydown", handleConversationComposerKeydown);' in js


def test_profile_template_avoids_inline_submit_handlers() -> None:
    template = (ROOT / "hushline/templates/profile.html").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'id="messageForm"' in template
    assert 'onsubmit="' not in template
    assert "What's this?" in template
    assert 'class="badge badgeCaution"' in template
    assert 'role="tooltip"' in template
    assert 'id="recipientPublicKeys"' in template
    assert 'id="recipientPublicKeyEntries"' in template
    assert ".badgeHelpTooltipGroup" in scss
    assert ".badgeHelpTrigger" in scss
    assert ".badgeHelpTooltip" in scss


def test_verified_url_icon_uses_image_assets() -> None:
    image_loader = (ROOT / "assets/js/images.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'import "./../img/icon-verified-lm.png";' in image_loader
    assert 'import "./../img/icon-verified-dm.png";' in image_loader
    assert 'background-image: url("../img/icon-verified-lm.png");' in scss
    assert 'background-image: url("../img/icon-verified-dm.png");' in scss
    assert ".icon.verifiedURL::after" not in scss
    assert (ROOT / "assets/img/icon-verified-lm.png").is_file()
    assert (ROOT / "assets/img/icon-verified-dm.png").is_file()


def test_submit_spinner_hooks_exist_for_scoped_forms() -> None:
    js = (ROOT / "assets/js/global.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert "form[data-submit-spinner='true']" in js
    assert "submit-button-label" in js
    assert "submit-button-spinner" in js
    assert 'attributeFilter: ["disabled"]' in js
    assert 'button[data-submit-spinner-init="true"]' in scss
    assert "transform: translate(-50%, -50%);" in scss
    assert "translate(-50%, -50%) rotate(360deg)" in scss
    assert "@keyframes submit-button-spinner-rotate" in scss


def test_first_load_splash_hooks_exist() -> None:
    template = (ROOT / "hushline/templates/base.html").read_text(encoding="utf-8")
    js = (ROOT / "assets/js/global.js").read_text(encoding="utf-8")
    no_js = (ROOT / "hushline/static/no-js.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'id="first-load-splash"' in template
    assert 'name="first-load-splash-logo-src"' in template
    assert 'content="{{ first_load_splash_logo_url }}"' in template
    assert 'aria-hidden="true"' in template
    assert 'data-splash-duration-ms="{{ splash_screen_duration_ms }}"' in template
    assert 'data-splash-skip-seen-mark="{{' in template
    assert (
        "splash_logo_url or brand_logo_url or url_for('static', filename='img/splash-logo.png')"
        in template
    )
    assert 'src="{{ first_load_splash_logo_url }}"' in template
    assert "https://hushline.app/assets/img/social/logo.png" not in template
    image_loader = (ROOT / "assets/js/images.js").read_text(encoding="utf-8")
    assert 'import "./../img/splash-logo.png";' in image_loader
    assert (ROOT / "assets/img/splash-logo.png").is_file()
    assert (ROOT / "hushline/static/img/splash-logo.png").is_file()
    assert 'class="first-load-splash-spinner"' in template
    assert "FIRST_LOAD_SPLASH_SEEN_KEY" in js
    assert "FIRST_LOAD_SPLASH_LOGO_SRC_KEY" in js
    assert "hushline:first-load-splash-seen" in js
    assert "hushline:first-load-splash-logo-src" in js
    assert "getFirstLoadSplashLogoSrc(splash)" in js
    assert "const shouldSkipSeenMark =" in js
    assert "!shouldSkipSeenMark && hasSeenFirstLoadSplash(splash)" in js
    assert 'splash.dataset.splashSkipSeenMark === "true"' in js
    assert "Number.parseInt(" in js
    assert "const duration = configuredDuration >= 0 ? configuredDuration : 2000;" in js
    assert 'document.documentElement.classList.remove("splash-seen");' in js
    assert 'document.documentElement.classList.add("splash-seen");' in js
    assert 'sessionStorage.getItem("hushline:first-load-splash-seen")' in no_js
    assert 'meta[name="first-load-splash-logo-src"]' in no_js
    assert 'sessionStorage.getItem("hushline:first-load-splash-logo-src")' in no_js
    assert "seenSplashLogoSrc === splashLogoSrc" in no_js
    assert ".no-js .first-load-splash" in scss
    assert ".splash-seen .first-load-splash" in scss
    assert "width: clamp(8rem, 50vw, 13rem);" in scss
    assert "width: clamp(9rem, 15vw, 12rem);" in scss
    assert "border-right-color: transparent;" in scss
    assert "@keyframes first-load-splash-spinner-rotate" in scss


def test_native_pwa_splash_assets_and_manifest_fallback_exist() -> None:
    template = (ROOT / "hushline/templates/base.html").read_text(encoding="utf-8")
    static_manifest = json.loads(
        (ROOT / "hushline/static/manifest.json").read_text(encoding="utf-8")
    )

    assert "{% else %}" in template
    assert "apple-touch-startup-image" in template
    assert "url_for('static', filename='splash/launch-" in template
    assert static_manifest["background_color"] == "#fbf3ff"
    for filename in (
        "launch-828x1792.png",
        "launch-1080x2340.png",
        "launch-1125x2436.png",
        "launch-1170x2532.png",
        "launch-1179x2556.png",
        "launch-1242x2688.png",
        "launch-1284x2778.png",
    ):
        assert (ROOT / "hushline/static/splash" / filename).is_file()


def test_service_worker_does_not_cache_navigation_html() -> None:
    service_worker = (ROOT / "assets/js/service-worker.js").read_text(encoding="utf-8")

    assert re.search(r'const CACHE_NAME = "hushline-cache-v\d+";', service_worker)
    assert '"/"' not in service_worker
    assert 'event.request.mode === "navigate"' in service_worker
    assert "event.respondWith(fetch(event.request));" in service_worker


def test_directory_search_accessibility_hooks_exist() -> None:
    directory_template = (ROOT / "hushline/templates/directory.html").read_text(encoding="utf-8")
    directory_js = (ROOT / "assets/js/directory.js").read_text(encoding="utf-8")
    directory_verified_js = (ROOT / "assets/js/directory_verified.js").read_text(encoding="utf-8")
    user_search_js = (ROOT / "assets/js/user_search.js").read_text(encoding="utf-8")
    directory_verified_static_js = (ROOT / "hushline/static/js/directory_verified.js").read_text(
        encoding="utf-8"
    )
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="directory-sticky-shell"' in directory_template
    assert 'id="directory-search-status"' in directory_template
    assert 'id="public-record-count"' in directory_template
    assert 'id="newsroom-count"' in directory_template
    assert 'id="all-filters-toggle"' in directory_template
    assert 'id="all-filters-panel"' in directory_template
    assert 'id="attorney-filters-toggle"' in directory_template
    assert 'id="attorney-filters-panel"' in directory_template
    assert 'id="newsroom-filters-toggle"' in directory_template
    assert 'id="newsroom-filters-panel"' in directory_template
    assert 'data-filter-toggle-label="true"' in directory_template
    assert 'data-filter-toggle-badge="true"' in directory_template
    assert "Clear Filters" in directory_template
    assert 'class="visually-hidden"' in directory_template
    assert 'role="status"' in directory_template
    assert 'aria-live="polite"' in directory_template
    assert (
        'const searchStatus = document.getElementById("directory-search-status");' in directory_js
    )
    assert (
        'const searchStatus = document.getElementById("directory-search-status");'
        in directory_verified_js
    )
    assert 'const publicRecordCountBadge = document.getElementById("public-record-count");' in (
        directory_verified_js
    )
    assert 'const allFiltersToggle = document.getElementById("all-filters-toggle");' in (
        directory_verified_js
    )
    assert 'const allFiltersPanel = document.getElementById("all-filters-panel");' in (
        directory_verified_js
    )
    assert 'const allListingTypeFilter = document.getElementById("all-listing-type-filter");' in (
        directory_verified_js
    )
    assert (
        'const attorneyFiltersToggle = document.getElementById("attorney-filters-toggle");'
        in directory_verified_js
    )
    assert (
        'const attorneyFiltersPanel = document.getElementById("attorney-filters-panel");'
        in directory_verified_js
    )
    assert (
        'const attorneyCountryFilter = document.getElementById("attorney-country-filter");'
        in directory_verified_js
    )
    assert (
        'const attorneyRegionFilter = document.getElementById("attorney-region-filter");'
        in directory_verified_js
    )
    assert "Showing all users." in directory_js
    assert "Showing all" in directory_verified_js
    assert 'searchInput.placeholder = "Search attorneys...";' in directory_verified_js
    assert 'searchInput.placeholder = "Search journalists and newsrooms...";' in (
        directory_verified_js
    )
    assert 'searchInput.placeholder = "Search GlobaLeaks instances...";' in directory_verified_js
    assert 'return "attorneys";' in directory_verified_js
    assert 'return "journalists and newsrooms";' in directory_verified_js
    assert 'return "GlobaLeaks instances";' in directory_verified_js
    assert 'tab === "public-records" || tab === "newsrooms"' in directory_verified_js
    assert 'tab === "public-records" || tab === "newsrooms"' in directory_verified_static_js
    assert 'aria-label="Info-only account">📇 Info Only</span>' in directory_verified_js
    assert 'aria-label="Info-only account">📇 Info Only</span>' in directory_verified_static_js
    assert "window.location.search" in directory_verified_js
    assert "window.location.search" in directory_verified_static_js
    assert "function escapeHtml(value)" in user_search_js
    assert "return escapeHtml(sourceText);" in user_search_js
    assert '<mark class="search-highlight">${escapeHtml(match[0])}</mark>' in user_search_js
    assert "function createLocationFilterController(config)" in directory_verified_js
    assert "controller.activeFilterCount = function () {" in directory_verified_js
    assert "controller.updateCountBadge = function () {" in directory_verified_js
    assert "updateLocationFilterCountBadges();" in directory_verified_js
    assert 'const directoryPath = window.location.pathname.replace(/\\/$/, "");' in (
        directory_verified_js
    )
    assert "function usersJsonSearchForTab(tab, search)" in directory_verified_js
    assert "usersJsonSearchForTab(tab, search)" in directory_verified_js
    assert 'metadataPath: "all-filters.json"' in directory_verified_js
    assert 'metadataPath: "attorney-filters.json"' in directory_verified_js
    assert 'metadataPath: "newsroom-filters.json"' in directory_verified_js
    assert 'resultsLabelPlural: "journalists and newsrooms"' in directory_verified_js
    assert "fetch(`${directoryPath}/${controller.metadataPath}${search}`)" in directory_verified_js
    assert "controller.countryLabelForValue = function (value) {" in directory_verified_js
    assert "controller.countryFilter.innerHTML = '<option value=\"\">All</option>';" in (
        directory_verified_js
    )
    assert 'const directoryPath = window.location.pathname.replace(/\\/$/, "");' in (directory_js)
    assert "fetch(`${directoryPath}/users.json`)" in directory_js
    assert "window.history.replaceState" in directory_verified_js
    assert "new AbortController();" in directory_verified_js
    assert 'controller.panel.setAttribute("aria-busy", isLoading ? "true" : "false");' in (
        directory_verified_js
    )
    assert "controller.inferredCountryForRegionCode = function (regionCode) {" in (
        directory_verified_js
    )
    assert "controller.updateSelectExpandedLabels = function (isExpanded) {" in (
        directory_verified_js
    )
    assert 'controller.countryFilter.addEventListener("change", function () {' in (
        directory_verified_js
    )
    assert 'controller.regionFilter.addEventListener("change", function () {' in (
        directory_verified_js
    )
    assert 'select.addEventListener("focus", syncExpandedLabelsOnOpen);' in directory_verified_js
    assert 'select.addEventListener("blur", syncExpandedLabelsOnClose);' in directory_verified_js
    assert "controller.countryFilter.value = controller.inferredCountryForRegionCode(" in (
        directory_verified_js
    )
    assert "controller.updateClearVisibility();" in directory_verified_js
    assert 'button[type="submit"]' not in directory_template
    assert "setSearchStatus(`Updating ${controller.resultsLabelPlural} results.`);" in (
        directory_verified_js
    )
    assert "controller.panel.hidden = !controller.panel.hidden;" in directory_verified_js
    assert 'const toggleLabel = controller.toggle.querySelector("[data-filter-toggle-label]");' in (
        directory_verified_js
    )
    assert 'const toggleBadge = controller.toggle.querySelector("[data-filter-toggle-badge]");' in (
        directory_verified_js
    )
    assert "toggleBadge.hidden = isExpanded || activeFilterCount === 0;" in directory_verified_js
    assert 'toggleBadge.setAttribute("aria-label", `${activeFilterCount} active filters`);' in (
        directory_verified_js
    )
    assert "active filters" in directory_verified_static_js
    assert "data-filter-toggle-badge" in directory_verified_static_js
    assert "Hide Filters" in directory_verified_static_js
    assert "Show Filters" in directory_verified_static_js
    assert "eval(" not in directory_verified_static_js
    assert "webpack://" not in directory_verified_static_js
    assert "all_tab_sort_transliterated" in directory_verified_js
    assert "all_tab_sort_normalized" in directory_verified_js
    assert "show_caution_badge" in directory_js
    assert "show_caution_badge" in directory_verified_js
    assert "all_tab_sort_transliterated" in directory_verified_static_js
    assert "all_tab_sort_normalized" in directory_verified_static_js
    assert "show_caution_badge" in directory_verified_static_js
    assert "all_tab_sort_transliterated ??" in directory_verified_js
    assert "all_tab_sort_transliterated ??" in directory_verified_static_js
    assert "localeCompare" not in directory_verified_js
    assert "localeCompare" not in directory_verified_static_js
    assert "Caution: display name may be mistaken for admin" in directory_js
    assert "Caution: display name may be mistaken for admin" in directory_verified_js
    assert "Caution: display name may be mistaken for admin" in directory_verified_static_js
    assert "const safeDisplayName = userSearch.escapeHtml(" in directory_js
    assert "const safeDisplayName = userSearch.escapeHtml(" in directory_verified_js
    assert 'const safeBio = userSearch.escapeHtml(user.bio || "No bio");' in directory_js
    assert 'const safeBio = userSearch.escapeHtml(user.bio || "No bio");' in directory_verified_js
    assert 'const safeBio = userSearch.escapeHtml(user.bio || "No description");' in (
        directory_verified_js
    )
    safe_user_aria = (
        'aria-label="${safeUserType}, Display name:${safeDisplayName}, Username: '
        '${safeUsername}, Bio: ${safeBio}"'
    )
    assert safe_user_aria in directory_js
    assert safe_user_aria in directory_verified_js
    assert (
        'aria-label="${safeListingType}, Display name:${safeDisplayName}, Description: ${safeBio}"'
        in directory_verified_js
    )
    assert (
        'aria-label="${userType}, Display name:${user.display_name || user.primary_username}'
        not in (directory_verified_js)
    )
    assert (
        'aria-label="${userType}, Display name:${user.display_name || user.primary_username}'
        not in (directory_js)
    )
    assert "user.city," in directory_verified_js
    assert "user.country," in directory_verified_js
    assert "user.subdivision," in directory_verified_js
    assert "Array.isArray(user.countries)" in directory_verified_js
    assert "users.json" in directory_verified_static_js
    assert "usersJsonSearchForTab" in directory_verified_static_js
    assert "all-filters.json" in directory_verified_static_js
    assert "attorney-filters.json" in directory_verified_static_js
    assert "fetch(`${directoryPath}/${controller.metadataPath}${search}`)" in (
        directory_verified_static_js
    )
    assert "function setFeaturedSlideInteractive(slide, isInteractive)" in directory_verified_js
    assert 'slide.setAttribute("inert", "");' in directory_verified_js
    assert 'slide.removeAttribute("inert");' in directory_verified_js
    assert "[data-featured-original-tabindex]" in directory_verified_js
    assert re.search(
        r"\.featured-directory \.user \{[^}]*box-shadow: var\(--shadow-dynamic\);",
        scss,
    )
    assert re.search(r"\.featured-directory \{[^}]*overflow: visible;", scss)
    assert "--featured-carousel-peek: var(--container-padding, 1.25rem);" in scss
    assert "--featured-carousel-shadow-overflow: 0.75rem;" in scss
    assert "clip-path: inset(0 0 calc(-1 * var(--featured-carousel-shadow-overflow)) 0);" in scss
    assert re.search(
        r"\.featured-directory\.is-enhanced \.featured-directory-window \{[^}]*"
        r"margin-bottom: calc\(-1 \* var\(--featured-carousel-shadow-overflow\)\);[^}]*"
        r"overflow: hidden;[^}]*"
        r"padding-bottom: var\(--featured-carousel-shadow-overflow\);",
        scss,
    )
    assert re.search(
        r"\.featured-directory\.is-enhanced \.featured-directory-slide \{[^}]*"
        r"position: relative;[^}]*"
        r"z-index: 1;",
        scss,
    )
    assert re.search(
        r"\.featured-directory\.is-enhanced \.featured-directory-slide\.active \{[^}]*"
        r"z-index: 2;",
        scss,
    )
    assert "controller.countryLabelForValue = function (value) {" in directory_verified_static_js
    assert "replaceState" in directory_verified_static_js
    assert ".directory-sticky-shell" in scss
    assert ".directory-filter-panel" in scss
    assert ".visually-hidden" in scss


def test_directory_sticky_active_tab_scroll_to_top_hook_exists() -> None:
    directory_verified_js = (ROOT / "assets/js/directory_verified.js").read_text(encoding="utf-8")

    assert 'clickedTab.classList.contains("active")' in directory_verified_js
    assert 'directoryTabs.classList.contains("is-sticky")' in directory_verified_js
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)")' in directory_verified_js
    assert 'window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });' in (
        directory_verified_js
    )


def test_directory_tab_scroll_buttons_clamp_to_valid_bounds() -> None:
    directory_verified_js = (ROOT / "assets/js/directory_verified.js").read_text(encoding="utf-8")
    directory_verified_static_js = (ROOT / "hushline/static/js/directory_verified.js").read_text(
        encoding="utf-8"
    )
    max_scroll_left_prefix = "const maxScrollLeft = Math.max("
    max_scroll_left_expr = "directoryTabList.scrollWidth - directoryTabList.clientWidth"

    assert max_scroll_left_prefix in directory_verified_js
    assert max_scroll_left_expr in directory_verified_js
    assert "const nextScrollLeft = Math.min(" in directory_verified_js
    assert "directoryTabList.scrollTo({" in directory_verified_js
    assert "directoryTabList.scrollBy({" not in directory_verified_js
    assert max_scroll_left_prefix in directory_verified_static_js
    assert max_scroll_left_expr in directory_verified_static_js
    assert "const nextScrollLeft = Math.min(" in directory_verified_static_js
    assert "directoryTabList.scrollTo({" in directory_verified_static_js
    assert "directoryTabList.scrollBy({" not in directory_verified_static_js


def test_inbox_sticky_nav_hooks_exist() -> None:
    inbox_template = (ROOT / "hushline/templates/inbox.html").read_text(encoding="utf-8")
    inbox_js = (ROOT / "assets/js/inbox.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="inbox-tabs-nav"' in inbox_template
    assert 'const inboxTabsNav = document.querySelector(".inbox-tabs-nav");' in inbox_js
    assert "--inbox-tabs-top" in inbox_js
    assert ".inbox-tabs-nav {" in scss
    assert "position: sticky;" in scss
    assert "flex-wrap: nowrap;" in scss
    assert "overflow-x: auto;" in scss
    assert "flex: 0 0 auto;" in scss


def test_settings_field_delete_confirmation_blocks_submit_on_cancel() -> None:
    js = (ROOT / "assets/js/settings-fields.js").read_text(encoding="utf-8")

    assert '.querySelectorAll(".message-field-delete-button")' in js
    assert "return confirm(" in js


def test_settings_sticky_nav_hooks_exist() -> None:
    settings_template = (ROOT / "hushline/templates/settings/nav.html").read_text(
        encoding="utf-8",
    )
    settings_js = (ROOT / "assets/js/settings.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="settings-tabs"' in settings_template
    assert 'const settingsTabsNav = document.querySelector(".settings-tabs");' in settings_js
    assert "--settings-tabs-top" in settings_js
    assert ".settings-tabs {" in scss
    assert "position: sticky;" in scss


def test_profile_location_settings_use_country_select_and_dependency_script() -> None:
    profile_template = (ROOT / "hushline/templates/settings/profile.html").read_text(
        encoding="utf-8"
    )
    profile_forms_template = (ROOT / "hushline/templates/settings/profile-forms.html").read_text(
        encoding="utf-8"
    )
    location_asset_js = (ROOT / "assets/js/settings-location.js").read_text(encoding="utf-8")
    location_js = (ROOT / "hushline/static/js/settings-location.js").read_text(encoding="utf-8")
    webpack_config = (ROOT / "webpack.config.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert "settings-location.js" in profile_template
    assert "autocomplete='country-name'" in profile_forms_template
    assert "autocomplete='address-level2'" in profile_forms_template
    assert "autocomplete='address-level1'" in profile_forms_template
    assert "data_states_url=url_for('.profile_states')" in profile_forms_template
    assert "data_cities_url=url_for('.profile_cities')" in profile_forms_template
    assert 'const countryInput = document.getElementById("country");' in location_asset_js
    assert '"settings-location",' in webpack_config
    assert 'const countryInput = document.getElementById("country");' in location_js
    assert 'const subdivisionInput = document.getElementById("subdivision");' in location_js
    assert 'const cityInput = document.getElementById("city");' in location_js
    assert "const statesUrl = countryInput.dataset.statesUrl;" in location_js
    assert "const citiesUrl = subdivisionInput.dataset.citiesUrl;" in location_js
    assert "async function loadStates(selectedValue)" in location_js
    assert "async function loadCities(selectedValue)" in location_js
    assert 'countryInput.addEventListener("change", async function () {' in location_js
    assert 'subdivisionInput.addEventListener("change", async function () {' in location_js
    assert "${statesUrl}?country=${encodeURIComponent(country)}" in location_js
    assert "const params = new URLSearchParams({" in location_js
    assert '#country:has(option:checked[value=""])' in scss
    assert '#subdivision:has(option:checked[value=""])' in scss
    assert '#city:has(option:checked[value=""])' in scss


def test_profile_settings_template_contains_updated_ui_copy() -> None:
    profile_forms_template = (ROOT / "hushline/templates/settings/profile-forms.html").read_text(
        encoding="utf-8"
    )
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")
    normalized_template = " ".join(profile_forms_template.split())

    assert "<h4>Profile Information</h4>" in profile_forms_template
    assert "Add your account category to help people find you more easily." in normalized_template
    assert (
        "Selecting Journalist or Newsroom will automatically add you to the Journalists tab"
        in normalized_template
    )
    assert "in the Directory if you opt in." in normalized_template
    assert "The same logic applies to Attorneys and Law Offices." in normalized_template
    assert "<h5>Location Information</h5>" in profile_forms_template
    assert "Including location information makes your account more relevant to" in (
        normalized_template
    )
    assert "whistleblowers and helps people discover your profile when they search" in (
        normalized_template
    )
    assert "with filters." in normalized_template
    assert "<h5>Add Your Bio</h5>" in profile_forms_template
    assert "Include information about who you are and how you can help potential" in (
        normalized_template
    )
    assert "whistleblowers." in normalized_template
    assert "<h5>Custom Fields</h5>" in profile_forms_template
    assert "<h4>Customize Your Tip Line Form</h4>" in profile_forms_template
    assert "<h5>Profile Details</h5>" not in profile_forms_template
    assert "<h4>Message Fields</h4>" not in profile_forms_template
    assert "h4+form p {" in scss
    assert "margin-bottom: 1rem;" in scss


def test_settings_field_builder_select_hooks_are_wrapper_safe() -> None:
    settings_fields_js = (ROOT / "assets/js/settings-fields.js").read_text(encoding="utf-8")

    assert "function getFieldFormRoot(fieldType)" in settings_fields_js
    assert 'return fieldType.closest("form");' in settings_fields_js
    assert (
        "const choicesContainer = getFieldFormRoot(fieldType)?.querySelector(" in settings_fields_js
    )
    assert (
        "const requiredCheckboxContainer = getFieldFormRoot(fieldType)?.querySelector("
        in settings_fields_js
    )
    assert "const requiredCheckbox = getFieldFormRoot(fieldType)?.querySelector(" in (
        settings_fields_js
    )
