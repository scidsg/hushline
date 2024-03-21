# Hush Line Threat Model

Adapted from the threat/risk models published by [Cwtch](https://docs.cwtch.im/security/risk/), [SecureDrop](https://docs.securedrop.org/en/latest/threat_model/threat_model.html), and [Pond](https://web.archive.org/web/20150326154506/https://pond.imperialviolet.org/threat.html).

## Introduction

Hush Line is a secure communication platform designed with a strong focus on privacy and anonymity. This document outlines the threat model for Hush Line, highlighting potential threats, the data Hush Line collects, how it is secured, and what users can expect in terms of privacy and security.

## Data Collection and Encryption

Hush Line collects minimal data to maintain the functionality of the service while prioritizing user privacy. Here's a detailed look at the data handling mechanisms:

### User Data

- **Usernames and Display Names:** Stored and encrypted using symmetric encryption. These identifiers allow users to interact within the platform while preserving their anonymity.
- **Password Hashes:** User passwords are hashed using bcrypt, ensuring that even if data is compromised, actual passwords are not exposed.
- **Two-Factor Authentication (2FA) Secrets:** For users opting for 2FA, these secrets are encrypted and stored securely. 2FA provides an additional layer of security, mitigating the risk of unauthorized account access.
- **Email and SMTP Settings:** For users who choose to receive notifications or use email-based functionalities, these settings are encrypted and stored. Users are encouraged to use email addresses not linked to their real identity for enhanced privacy.
- **PGP Keys:** For end-to-end encrypted communication, users can provide their PGP keys. These keys are stored in an encrypted format, enabling secure message exchange without exposing the content to Hush Line servers.

### Communication Data

- **Messages:** All messages are encrypted end-to-end. Hush Line servers only store encrypted blobs, making it impossible to access the content without the corresponding decryption keys, which are held by the end users.

### Logs and Metadata

- **Access Logs:** Hush Line minimizes logging to essential operational data, which is anonymized to prevent linking back to users. IP addresses are obfuscated, and logs are rotated regularly to ensure that historical data cannot be exploited to compromise user privacy.
- **Rate Limiting and Security Measures:** The platform employs rate limiting and other security measures to protect against abuse and DoS attacks. These mechanisms are designed to be privacy-preserving and do not log personally identifiable information.

## Threats and Mitigations

### Network Observers and Global Adversaries

- **Mitigation:** All data in transit is encrypted using TLS, and users are encouraged to access Hush Line via Tor for additional anonymity. This prevents network observers from deciphering the content or metadata of communications.

### Account Compromise

- **Mitigation:** Strong password policies, optional 2FA, and secure password reset mechanisms are in place to protect user accounts. Users are educated on best practices for maintaining account security.

### Legal and Coercive Pressure

- **Mitigation:** Hush Line is designed to hold minimal information that could be of interest in legal contexts. Furthermore, the use of encryption for stored data ensures that, even under pressure, Hush Line cannot divulge meaningful user data.

### Phishing and Social Engineering

- **Mitigation:** User education and secure design principles minimize the risk of phishing. Features like displaying the last login time and alerting users to new logins from unfamiliar devices help users detect unauthorized access attempts.

## Verification System

Hush Line employs a verification system to ensure that users can trust the source of communication. This system is particularly important for users who are public figures or have a wide audience. The verification system includes:

### Verified Accounts

- **Display of Verification Status:** Hush Line indicates verified accounts with a distinctive badge (⭐️ Verified Account). This visual indicator helps users distinguish authentic accounts from potential impersonators, reducing the risk of phishing attacks.

## User Education

### Encryption Awareness

- **Encryption Indicators:** The platform informs users whether their messages will be encrypted. For accounts with a public PGP key, messages are encrypted, ensuring that only the intended recipient can decrypt and read them. This feature is highlighted through messages on the submission form, emphasizing the importance of encryption for sensitive information.

### User Guidance

- **Informative Messages for Senders and Receivers:** Hush Line educates its users about the significance of encryption and the steps required to ensure message confidentiality. This includes prompts for receivers to add a public PGP key if they haven't already, and notifications for senders about the encryption status of their message.

### IP Address Disclosure

- **Transparency about IP Visibility:** The platform informs users about the visibility of their IP addresses when submitting a message. This disclosure encourages the use of privacy-enhancing tools like Tor Browser for users seeking additional anonymity.

## Assumptions

The following assumptions are accepted in the threat model of the Hush Line product:

### Assumptions About the Individual Submitting a Message

- The individual submitting a message does so in good faith.
- The individual submitting a message wants to remain anonymous, against a network observer, forensic analysis, or to Hush Line servers.
- The individual submitting a message is accessing the official Hush Line site.

### Assumptions About the Person or Organization Receiving a Message

- The receiver operates Hush Line in good faith.

### Assumptions About the Hush Line Server

- The server is operated in good faith.
- The server is single-use and configured with the official scripts on the GitHub main repo.
- The server has no other software other than what is required for the operation of Hush Line.

### Assumptions About the Source’s Computer

- The computer has an updated version of a popular browser including Chrome, Firefox, or Safari, and for anonymous connections, an updated version of Tor Browser.
- The computer is not compromised by malware.

### Assumptions About Science & Design

- Science & Design wants to preserve the anonymity of its sources.
- Science & Design acts in the interest of allowing sources to submit messages, regardless of the contents of their contents.
- The users of the system, and those with physical access to the servers, can be trusted to uphold the previous assumptions unless the entire organization has been compromised.
- Science & Design is prepared to push back on any and all requests to compromise the integrity of the system and its users, including requests to deanonymize sources, block document submissions, or hand over encrypted or decrypted submissions.

### Assumptions About the World

- The security assumptions of RSA (4096-bit GPG and SSH keys) are valid.
- The security assumptions of bcrypt with randomly-generated salts are valid.
- The security/anonymity assumptions of Tor and the onion service protocol are valid.
- The security assumptions of the Tails operating system are valid.
- The security assumptions of Hush Line dependencies, specifically Debian, the Linux kernel, application packages, application dependencies are valid.

### Other Assumptions or Factors

- The level of press freedom may vary in both geography and time.
- The number of daily Tor users in a country can greatly vary.

## Conclusion

Hush Line's threat model acknowledges the variety of adversaries that users may face and implements a robust security architecture to mitigate these risks. By encrypting data at rest, minimizing data collection, and educating users on security practices, Hush Line aims to offer a secure and private platform for communication.