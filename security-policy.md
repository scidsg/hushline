# Hush Line Security Policy

At Hush Line, developed by Science & Design, Inc., we prioritize the security of our application and the privacy of our users. This security policy outlines the measures and features we implement to ensure a secure environment for all users of Hush Line.

## Core Security Features

### Two-Factor Authentication (2FA)

- Hush Line offers 2FA, adding an extra layer of security by requiring two forms of identification before granting access to an account.

### HTTPS with Let's Encrypt

- All traffic is encrypted using HTTPS, with certificates provided by Let's Encrypt, ensuring secure communication between users and our servers.

### End-to-End Encrypted Messages (E2EE) with OpenPGP.js

- Messages are encrypted from the sender's device to the recipient's device, preventing any unauthorized access in transit.

### Tor Onion Service

- Hush Line offers a Tor onion service, allowing users to access the application with enhanced privacy and security.

### Hardened Content Security Policy

- A strict Content Security Policy (CSP) is implemented to prevent Cross-Site Scripting (XSS) and other code injection attacks.

### Strong Password Policy

- Users are required to create complex passwords, meeting specific criteria to ensure account security.

### 30 Minute Session Timeout

- Sessions expire after 30 minutes of inactivity, reducing the risk of unauthorized access.

### OCSP Stapling

- Online Certificate Status Protocol (OCSP) Stapling is utilized to provide fresher certificate revocation information.

### SSL Resolver Timeout

- Configured to minimize the risk of Denial of Service (DoS) attacks through carefully timed resolver timeouts.

### Security.txt Server File

- A `security.txt` file is provided, making it easier for researchers to report security vulnerabilities.

### Environment Variables for Storing Secrets

- Sensitive information, such as database credentials and encryption keys, is stored securely using environment variables.

### Database Encryption At Rest

- Databases are encrypted at rest to protect sensitive data from unauthorized access if physical security is compromised.

### Input Sanitation with Flask-WTF

- Input from users is sanitized using Flask-WTF, preventing injection attacks and ensuring data integrity.

### UFW and Fail2Ban

- The Uncomplicated Firewall (UFW) and Fail2Ban are configured to protect against unauthorized access and automated attacks.

### Automatic Updates with `unattended-upgrades`

- Security patches and updates are automatically applied to ensure the application is protected against known vulnerabilities.

### Onion Binding with Sauteed Onions

- Integrates with Sauteed Onions to provide a seamless experience between the clearnet and onion services.

### Secure Cookie Delivery and Prevention of JavaScript Access to Cookies

- Cookies are delivered securely and configured to prevent access from JavaScript, enhancing privacy and security.

## Reporting Security Vulnerabilities

We encourage responsible disclosure of any security vulnerabilities. Please report any security concerns to us via:

- Email: security@scidsg.org
- PGP Key: [PGP Public Key URL](https://hushline.app/public.asc)

Our security team will investigate all reported issues and take appropriate actions to mitigate any vulnerabilities.

## Commitment to Security

Hush Line, under the stewardship of Science & Design, Inc., is committed to continuously improving the security of our application. We monitor the latest security best practices and engage with the security community to stay ahead of potential threats.

This document is subject to updates and modifications. We recommend users and developers to stay informed about our latest security practices and updates.