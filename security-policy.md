# Hush Line Security Policy

At Hush Line, developed by Science & Design, Inc., we prioritize the security of our application and the privacy of our users. This security policy outlines the measures and features we implement to ensure a secure environment for all users of Hush Line.

## Two-Factor Authentication (2FA)

- Hush Line offers 2FA, adding an extra layer of security by requiring two forms of identification before granting access to an account.

## HTTPS with Let's Encrypt

- All traffic is encrypted using HTTPS, with certificates provided by Let's Encrypt, ensuring secure communication between users and our servers.

## End-to-End Encrypted Messages (E2EE) with OpenPGP.js

- PGP-enabled messages are encrypted from the sender's device to the recipient's device, preventing any unauthorized access in transit.

## Tor Onion Service

- Hush Line offers a Tor onion service, allowing users to access the application with enhanced privacy and security.
## Security Headers

Hush Line implements a series of HTTP security headers to protect our users and their data. These headers help mitigate various types of attacks and ensure secure communication between clients and our servers. Below are the security headers we use and their purposes:

### Strict-Transport-Security

- `Strict-Transport-Security: max-age=63072000; includeSubdomains`
  - Ensures that browsers only connect to Hush Line over HTTPS, preventing man-in-the-middle attacks. The `max-age` directive specifies that the policy is remembered for two years.

### X-Frame-Options

- `X-Frame-Options: DENY`
  - Prevents the website from being framed by other sites, mitigating clickjacking attacks.

### X-Content-Type-Options

- `X-Content-Type-Options: nosniff`
  - Stops browsers from trying to MIME-sniff the content type, which can prevent certain types of attacks like drive-by downloads.

### Onion-Location

- `Onion-Location: http://$ONION_ADDRESS\$request_uri`
  - Provides an Onion-Location header which helps users on the Tor network to be aware of the site's onion service counterpart, enhancing privacy and security.

## Content-Security-Policy (CSP)

The Content-Security-Policy (CSP) header is a powerful tool used by web applications to mitigate the risk of Cross-Site Scripting (XSS) attacks and other types of code injection attacks. By specifying which content sources are trustworthy, CSP prevents the browser from loading malicious assets. Here's a breakdown of the CSP directive used:

- `default-src 'self';` Only allow content from the site's own origin. This is the default policy for loading resources such as JavaScript, images, CSS, fonts, AJAX requests, frames, HTML5 media, and other data.
- `script-src 'self' https://js.stripe.com https://unpkg.com;` Allow scripts to be loaded from the site's own origin, Stripe (for payment processing), and unpkg (a content delivery network for npm packages).
- `img-src 'self' data: https:;` Allow images from the site's origin, inline images using data URIs, and images loaded over HTTPS from any origin.
- `style-src 'self';` Only allow stylesheets from the site's own origin.
- `frame-ancestors 'none';` Prevent the site from being framed (embedded within an <iframe>) by other sites, mitigating Clickjacking attacks.
- `connect-src 'self' https://api.stripe.com;` Restrict the origins to which you can connect (via XHR, WebSockets, and EventSource).
- `child-src https://js.stripe.com;` Define valid sources for web workers and nested browsing contexts loaded using elements such as <frame> and <iframe>.
- `frame-src https://js.stripe.com;` Specify valid sources for frames.

## Permissions-Policy

The Permissions-Policy header allows a site to control which features and APIs can be used in the browser. This policy helps enhance privacy and security by restricting access to certain browser features that can be abused by malicious content. Here's an explanation of the directives used:

- `geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=();`
  - This configuration disables all the listed features for the website, meaning the site will not have access to geolocation data, MIDI devices, push notifications, synchronous XMLHttpRequests during page dismissal, microphone, camera, magnetometer, gyroscope, speaker, vibration API, fullscreen requests, payment requests, and Federated Learning of Cohorts (FLoC), a web tracking and profiling technology.

## Referrer-Policy

- `Referrer-Policy: no-referrer`
  - Ensures that no referrer information is passed along with requests made from Hush Line, enhancing user privacy.

## X-XSS-Protection

- `X-XSS-Protection: 1; mode=block`
  - Activates the browser's XSS filtering capabilities to prevent cross-site scripting attacks.

By implementing these security headers, Hush Line aims to provide a secure platform for our users, safeguarding their information against a wide array of potential threats. We continuously evaluate and update our security practices to adapt to the evolving digital landscape.

## Strong Password Policy

- Users are required to create complex passwords, meeting specific criteria to ensure account security.

## 30 Minute Session Timeout

- Sessions expire after 30 minutes of inactivity, reducing the risk of unauthorized access.

## OCSP Stapling

- Online Certificate Status Protocol (OCSP) Stapling is utilized to provide fresher certificate revocation information.

## SSL Resolver Timeout

- Configured to minimize the risk of Denial of Service (DoS) attacks through carefully timed resolver timeouts.

## Security.txt Server File

- A `security.txt` file is provided, making it easier for researchers to report security vulnerabilities.

## Environment Variables for Storing Secrets

- Sensitive information, such as database credentials and encryption keys, is stored securely using environment variables.

## Database Encryption At Rest

- Databases are encrypted at rest to protect sensitive data from unauthorized access if physical security is compromised.

## Input Sanitation with Flask-WTF

- Input from users is sanitized using Flask-WTF, preventing injection attacks and ensuring data integrity.

## UFW and Fail2Ban

- The Uncomplicated Firewall (UFW) and Fail2Ban are configured to protect against unauthorized access and automated attacks.

## Automatic Updates with `unattended-upgrades`

- Security patches and updates are automatically applied to ensure the application is protected against known vulnerabilities.

## Onion Binding with Sauteed Onions

- Integrates with Sauteed Onions to provide a seamless experience between the clearnet and onion services.

## Secure Cookie Delivery and Prevention of JavaScript Access to Cookies

- Cookies are delivered securely and configured to prevent access from JavaScript, enhancing privacy and security.

## Reporting Security Vulnerabilities

We encourage responsible disclosure of any security vulnerabilities. Please report any security concerns to us via Hush Line:

- https://beta.hushline.app/submit_message/scidsg-security

Our security team will investigate all reported issues and take appropriate actions to mitigate any vulnerabilities.

## Commitment to Security

Hush Line, under the stewardship of Science & Design, Inc., is committed to continuously improving the security of our application. We monitor the latest security best practices and engage with the security community to stay ahead of potential threats.

This document is subject to updates and modifications. We recommend users and developers to stay informed about our latest security practices and updates.
