# Hush Line Privacy Policy

## Introduction

This Privacy Policy outlines our commitment to protecting the privacy and security of the personal information collected from users of our app. By using our app, you consent to the data practices described in this policy.
Information Collection

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
- **Data Retention:** We retain your information as long as your account is active or as needed to provide you services. You may request the deletion of your data, subject to legal and operational considerations.

## Data Sharing and Disclosure

We do not sell, rent, or lease our user data to third parties. However, we may share your data in the following situations:

- **Legal Compliance:** We may disclose your information if required by law or in response to legal requests by public authorities.
- **Service Providers:** We may employ third-party companies to facilitate our service, such as hosting providers.

## User Rights

You have the right to access, correct, or delete your personal data. You can typically manage your data through your account settings or by contacting us directly.

## Changes to Privacy Policy

We reserve the right to modify this policy at any time. We will notify you of any changes by posting the new policy on this page.

## Contact Us

If you have any questions about this Privacy Policy, please contact us at https://beta.hushline.app/submit_message/scidsg.
