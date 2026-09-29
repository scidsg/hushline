# Secure Your Account

Source: <https://hushline.app/library/docs/getting-started/secure-your-account/>

Before you publish your tip line, make sure the account behind it is hard to take over.

## Use a strong password

Start with a unique password you do not reuse anywhere else. Your tip line is only as trustworthy as the account protecting it.

## Choose a second factor

Hush Line supports authenticator-app codes and, when enabled by the instance operator,
WebAuthn security keys.

### Use an authenticator app

1. Open `Settings` -> `Authentication`.
2. Choose `Enable 2FA`.
3. Scan the QR code with your authenticator app or enter the text code manually.
4. Verify with the six-digit code to finish setup.

Once enabled, logins require both your password and the current TOTP code.

### Use security keys

Security-key enrollment appears under `Settings` -> `Authentication` -> `Manage MFA,
security keys, and recovery codes` when it is available for your account. Confirm your
password and any existing second factor, then follow the browser prompt. Enroll at least two
separate keys and store the backup away from the key you carry.

The launch support target is a FIDO2/[WebAuthn](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API) security key that performs user verification,
such as a PIN-capable key, over USB or NFC. The intended browser scope is the current stable
Chrome, Edge, Firefox, and Safari releases on the operating systems listed in the validation
matrix, using a secure connection. A combination is supported for release only after its matrix
row records `Pass`; browser, operating-system, key, and transport combinations vary. The
[physical validation matrix](../../WEBAUTHN-VALIDATION.md#physical-key-browser-and-device-matrix)
is the source of truth for combinations Hush Line has actually tested. Bluetooth, hybrid,
smart-card, built-in platform authenticators, and synced credentials may be offered by a
browser, but they are not part of the initial hardware-key validation claim.

Hush Line does not collect authenticator attestation or vendor identity. It therefore cannot
promise that a credential is hardware-bound, even if the browser presents it as a security
key. If your threat model requires a physical key, deliberately choose the external-key option
in the browser and verify that the key asks for touch and user verification.

WebAuthn assertions are bound to the configured Hush Line origin, which makes the security-key
step resistant to lookalike-site phishing. Hush Line still asks for a password first, and
authenticator-app codes and recovery codes remain alternative login paths when configured;
those fallbacks do not gain the same phishing resistance. Security keys also do not protect an
already-compromised authenticated browser session.

### Prepare for a lost key

After enrolling a factor, generate recovery codes and store them separately from every key.
If a key is lost, sign in with a separately stored backup key, your authenticator app, or an
unused recovery code. Then remove the lost key in authentication settings and enroll a
replacement. Hush Line support and instance administrators cannot bypass an enrolled second
factor. If every enrolled factor and every recovery code is unavailable, the account cannot be
recovered through an administrative password-only downgrade.

Recovery restores account access; it does not decrypt old two-way conversation history.

## Understand password resets and chat history

Two-way account conversations use Hush Line chat keys that are unlocked in your
browser. If you change your password while your active chat key is available,
Hush Line can rewrap that key as part of the password-change flow.

If you reset your password because the old password is unavailable, old chat
history encrypted to the previous key can remain locked. Treat password-manager
recovery and account access as part of your conversation security plan.

## Secure the email account tied to notifications

If tips are forwarded to your inbox, that email account becomes part of your security boundary. Apply the same care there:

- use a strong password
- enable 2FA on the mail account too
- restrict who can access the mailbox

## Protect your verification and public identity signals

Changing a verified username or display name can affect trust signals shown to sources. Make identity changes deliberately, especially after you have already published your tip line.

## Related docs

- [Prep Your Account](./prep-your-account.md)
- [Two-Way Conversations](../using-your-tip-line/two-way-conversations.md)
- [Account Verification](../using-your-tip-line/account-verification.md)
