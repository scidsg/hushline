# 🤫 Hush Line

[Hush Line](https://hushline.app) is a whistleblower platform that provides secure, anonymous tip lines with no self-hosting required. Sign up for a free account at <https://tips.hushline.app/register>

![Accessibility](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/scidsg/hushline/refs/heads/main/badges/badge.json)
![Performance](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/scidsg/hushline/refs/heads/main/badges/badge-performance.json)
![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/scidsg/hushline/refs/heads/main/badges/badge-coverage.json)
![Tests](https://github.com/scidsg/hushline/actions/workflows/tests.yml/badge.svg)
![GDPR Compliance](https://github.com/scidsg/hushline/actions/workflows/gdpr-compliance.yml/badge.svg)
![CCPA Compliance](https://github.com/scidsg/hushline/actions/workflows/ccpa-compliance.yml/badge.svg)
![Database Migration Compatibility Tests](https://github.com/scidsg/hushline/actions/workflows/migration-smoke.yml/badge.svg)
![E2EE and Privacy Regressions](https://github.com/scidsg/hushline/actions/workflows/e2ee-privacy-regressions.yml/badge.svg)
![Workflow Security Checks](https://github.com/scidsg/hushline/actions/workflows/workflow-security.yml/badge.svg)
![Python Dependency Audit](https://github.com/scidsg/hushline/actions/workflows/dependency-security-audit.yml/badge.svg)
![W3C Validators](https://github.com/scidsg/hushline/actions/workflows/w3c-validators.yml/badge.svg)
![Docs Screenshots](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/scidsg/hushline-screenshots/main/badge-docs-screenshots.json)

## Latest Screenshots

<table>
  <tr>
    <td valign="bottom" width="73%">
      <img
        src="https://github.com/scidsg/hushline-screenshots/blob/main/releases/latest/guest/guest-directory-verified-desktop-light-fold.png?raw=true"
        width="100%"
      />
    </td>
    <td valign="bottom" width="27%">
      <img
        src="https://github.com/scidsg/hushline-screenshots/blob/main/releases/latest/newman/auth-newman-onboarding-profile-mobile-light-fold.png?raw=true"
        width="100%"
      />
    </td>
  </tr>
</table>

[View the latest Hush Line screenshots](https://github.com/scidsg/hushline-screenshots/tree/main/releases/latest).

## Quickstart (Local)

```sh
git clone https://github.com/scidsg/hushline.git
cd hushline
docker compose up
```

Open `http://localhost:8080`.

Common development commands:

- `make test` to run the test suite
- `make lint` to run lint/type/style checks
- `make fix` to auto-format code
- `make run-full` to run with Stripe-enabled stack
- `docker compose down -v` to reset local Docker volumes for a clean database state

## Security and Privacy

- Threat model: [`docs/THREAT-MODEL.md`](./docs/THREAT-MODEL.md)
- Security policy / vulnerability reporting: [`SECURITY.md`](./SECURITY.md)
- Privacy policy: [`docs/PRIVACY.md`](./docs/PRIVACY.md)

## Documentation

- Start here: <https://hushline.app/library/docs/getting-started/start-here/>
- Project docs index: [`docs/README.md`](./docs/README.md)
- Developer docs: [`docs/DEV.md`](./docs/DEV.md)

## Hush Line Features

- 📋 Email Header Validation and Report
- 👋 New User Onboarding
- ⭐️ Verified accounts
- 🙋 Opt-in user directory
- 👁️ OCR Vision Assistant
- 🧅 Tor Onion Service
- 🔑 Proton Mail key import
- 🔒 End-to-end encryption
- ✅ Self-authenticating URLs
- 📤 Riseup.net email delivery
- 💌 Mailvelope integration for in-app decryption
- 🥸 Aliases
- ⏱️ TOTP-based two-factor authentication
- 🎨 Custom branding
- 🪧 Custom onboarding & whistleblower guidance
- 🏷️ Message statuses
- 🧠 Automated message replies based on status
- 💬 Unique reply status URL for submitters
- 🤖 Local, Private CAPTCHA
- 🙊 Profanity filter with `better-profanity`

## In The Media

### Privacy Guides

“After using their platform for the past few weeks, I can comfortably write that Hush Line accomplishes its mission astoundingly well. Not only is customer support excellent for enterprise users, but its integration with PGP encrypted email makes it a lifesaver for a Thunderbird user like me. The ability to receive encrypted notifications via email is honestly an underrated feature.”
<br>
<https://www.privacyguides.org/posts/2026/01/09/hush-line-review-an-accessible-whistleblowing-platform-for-journalists-and-lawyers-alike/><br>
<https://web.archive.org/web/20260110024015/https://www.privacyguides.org/posts/2026/01/09/hush-line-review-an-accessible-whistleblowing-platform-for-journalists-and-lawyers-alike/>

### Newsweek

“Investing in technology that protects privacy—such as Hush Line and Signal—is also important in sharing information that is anonymous, and can't be subpoenaed.”<br>
<https://www.newsweek.com/protecting-free-speech-about-more-letting-content-run-wild-opinion-2012746><br>
<https://web.archive.org/web/20250111062609/https://www.newsweek.com/protecting-free-speech-about-more-letting-content-run-wild-opinion-2012746>

### TIME

"Psst’s safe is based on Hush Line, a tool designed by the nonprofit Science & Design, Inc., as a simpler way for sources to reach out to journalists and lawyers. It’s a one-way conversation system, essentially functioning as a tip-line. Micah Lee, an engineer on Hush Line, says that the tool fills a gap in the market for an encrypted yet accessible central clearinghouse for sensitive information."<br>
<https://time.com/7208911/psst-whistleblower-collective/><br>
<https://web.archive.org/web/20250122105330/https://time.com/7208911/psst-whistleblower-collective/>

### Substack

“New systems in development, such as Hush Line, developed by entrepreneur Glenn Sorrentino, are the brave new frontier in reporting. Hush Line is a software application that offers a more secure ability to report anonymously.”<br>
<https://zacharyellison.substack.com/p/part-151-playing-the-whistleblower>

### Podcasts

"I'm working with a a non-profit software company called Science and Design that's worked on a number of really interesting products that are kind of nerdy and more on the journalism space, but they're working on something called Hush Line, which is a one-way encrypted anonymizing platform so that whistleblowers can reach out to individual journalists while remaining anonymous... it provides a non-technical person a way and a path and information, should they find themselves in a whistleblowing position, to not mitigate the danger because it's never not going to be dangerous, but prepare them for the process and give them an easy-to-use modern tool to responsibly disclose information to trustworthy journalists..."<br>
_Around the Bend_<br>
<https://www.youtube.com/watch?v=pO6q_t0wGGA&t=38m17s>

## Contribution Guidelines

❤️ We're excited that you're interested in contributing to Hush Line. To maintain the quality of our codebase and ensure the best experience for everyone, we ask that you agree to and follow our [Code of Conduct](https://github.com/scidsg/business-resources/blob/main/Policies%20%26%20Procedures/Code%20of%20Conduct.md).

_Branch protection check-run validation update._

_Auto-merge verification PR marker._
