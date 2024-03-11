# Hush Line Privacy Policy

**Effective Date: March 11, 2024**

## Introduction

This Privacy Policy outlines our commitment to protecting the privacy and security of the personal information collected from users of our app. By using our app, you consent to the data practices described in this policy.

## Information Collection

- **User Provided Information:** We collect personal information that you provide to us, such as your username, display name, email address, and encrypted password. Additionally, we collect Two-Factor Authentication (2FA) data, SMTP settings, and PGP keys if you choose to provide them.
- **Automated Information Collection:** We use custom Nginx logging to remove IP addresses and country codes from access logs.

### Log Example
```
0.0.0.0 - - "GET /submit_message/scidsg HTTP/1.1" 200 929 "-"
0.0.0.0 - - "GET /static/style.css HTTP/1.1" 304 0 "-"
0.0.0.0 - - "GET /static/script.js HTTP/1.1" 304 0 "-"
0.0.0.0 - - "POST /submit_message/scidsg HTTP/1.1" 302 231 "-"
0.0.0.0 - - "GET /submit_message/scidsg HTTP/1.1" 200 973 "-"
0.0.0.0 - - "GET /static/style.css HTTP/1.1" 304 0 "-"
0.0.0.0 - - "GET /static/script.js HTTP/1.1" 304 0 "-"
```

## Use of Information

The information we collect is used for the following purposes:

- To provide and maintain our app's functionality, including user authentication, message encryption, and SMTP email services.

## Data Storage and Security

- **Data Encryption:** We use Fernet symmetric encryption to secure sensitive data such as password hashes and 2FA secrets. PGP keys are also encrypted for additional security.
- **Database Security:** User data is stored in a MySQL database with restricted access to protect against unauthorized access.
- **Form Handling and Validation:** We utilize Flask-WTF for secure form handling and validation, ensuring the integrity and confidentiality of user input.
- **Cryptography and Security Measures:** Our app employs advanced cryptography techniques (such as `pyotp` and `gnupg`) and Fernet encryption to enhance data security.
- **Server Security:** We use fail2ban to protect against brute-force attacks and UFW (Uncomplicated Firewall) for managing network traffic.
- **Data Retention:** We retain your information as long as your account is active or as needed to provide you services. After account deletion or prolonged inactivity, we may retain certain data for legal or operational purposes, typically not exceeding 90 days.

### DB Example Query
```
id: 1
username: scidsg
display_name: Science & Design
password_hash: gAAAAABlmgU-WeEuGr7b-HlwHJ5pIzxD3g9hLPStc8kUBZMiKyFVnj66Um6H4Sz2STfG6W8VBTP2zO2cG19ofqmdfQolx_Da6m_X3lHUajdlh1yp1alf_BoAoBvMxPUDkDRrrUWuaR1T0fJYeXY-C63ulfN6F2oCmQ==
totp_secret: gAAAAABlmgXSWumslIWNS7FEEAjf6nFqyeamKYTf0dmwnIUIRaLTzDcgDHeHimST4Lb3eIUwu-8fRVT9kiiSb3igbh-tANjLEIQV2E8ohkEPwmCJ8_wYR3ediBsGaTWMQHaIykV3sznk
email: gAAAAABlmjX3GyR8cJ03-MbSb7E3ozM10I_hDA4E22GmUxibQFLsI92lbKDwcMpXwGt_kZnJZgorMhpplbRPFHvytnL0aJOnrejkrua2YVwhrsuu0GwK8GA=
smtp_server: gAAAAABlmjX31SvRZLqFxdTPb0mTVdi9Hm6YJwnqItRNlcZKsJZGkSp55H4AkInkVblzyCyYuB0C4JCkzYVnuXQXt5TqTDiNPw==
smtp_port: 587
smtp_username: gAAAAABlmjX3SFNOr6xkrHtVMUTmcbzDKKAvWaGEXZstusPPrRKFTjgeBOXdFmClmxvZ50yU7uSXT2-yzhMqQS-yaSh7qJUSqxizMP36rxRhT_6qPuhECq0=
smtp_password: gAAAAABlmjX3tJFpAFZkFcXbF2PfN9sDMinQ-GG0DO2-AO_2b9OeMtzlDwO5jPhZs-u0_hjjKip7b09r0QPAK89hfOuMsJOleG9HVif2sjiDiVDZj4_OyRY=
pgp_key: [REDACTED]
is_verified: True
```

## Password Policy

- **Complexity Requirements:** Passwords must include uppercase and lowercase letters, digits, and a special character.
- **Length Requirements:** Passwords must be between 18 and 128 characters long.
- **Encryption:** Passwords are encrypted using `bcrypt` and securely stored.

## Additional Security Measures

- **Unattended Upgrades:** Our servers are configured with `unattended-upgrades` for important security patches.
- **Secure Server Configuration:** We use Nginx with privacy-preserving logging and HTTPS to ensure secure communication.
- **Tor Network Support:** The app supports access via the Tor network, providing additional anonymity options for users.
- **Fail2Ban and UFW:** We use `fail2ban` to monitor and mitigate unauthorized access attempts and `ufw` to manage network traffic, enhancing server security.

## Cookies and Tracking Technologies

Our app uses essential cookies to provide basic functionality and security features. These cookies do not track your activity on third-party websites or services. You can manage your cookie preferences through your browser settings.

## International Data Transfers

If you are accessing our app from outside the United States, please be aware that your information may be transferred to, stored, and processed by us and our service providers in the United States and other countries where our servers reside. We rely on recognized legal mechanisms such as Standard Contractual Clauses for such transfers.

## Data Sharing and Disclosure

We do not sell, rent, or lease our user data to third parties. However, we may share your data in the following situations:

- **Legal Compliance:** We may disclose your information if required by law or in response to legal requests by public authorities.
- **Service Providers:** We may employ third-party companies to facilitate our service, such as hosting providers, who are bound by strict confidentiality obligations.

## User Rights

You have rights over your personal data, including:

- **Access and Correction:** You can access and update your personal information via your account settings.
- **Deletion:** You can request the deletion of your account and associated data, subject to legal and operational considerations.
- **Data Portability:** You can request a copy of your data in a structured, commonly used, and machine-readable format.
- **Objection and Restriction:** You can object to or request the restriction of the processing of your personal data under certain circumstances.
- **Complaints:** You have the right to lodge a complaint with a supervisory authority if you believe your rights have been violated.

## Age Restrictions

Our app is intended for users who are 18 years of age or older. We do not knowingly collect personal information from children under 18. If we become aware that a child under 18 has provided us with personal information, we will take steps to delete such information.

## Third-Party Links

Our app may contain links to third-party websites or services that are not operated by us. This privacy policy does not apply to those third-party sites, and we encourage you to review their respective privacy policies.

## Data Breach Notification

In the event of a data breach that compromises the security, confidentiality, or integrity of your personal information, we will notify you promptly via email or prominent notice on our app, in compliance with applicable laws.

## Changes to Privacy Policy

We reserve the right to modify this policy at any time. We will notify you of any changes by posting the new policy on this page and updating the "Effective Date" at the top of this policy.

## Contact Us

If you have any questions about this Privacy Policy, please contact us at [https://tips.hushline.app/submit_message/scidsg](https://tips.hushline.app/submit_message/scidsg).
