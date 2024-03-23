# Hush Line Threat Model

Adapted from the threat/risk models published by [Cwtch](https://docs.cwtch.im/security/risk/), [SecureDrop](https://docs.securedrop.org/en/latest/threat_model/threat_model.html), and [Pond](https://web.archive.org/web/20150326154506/https://pond.imperialviolet.org/threat.html).

## Introduction

Hush Line is a secure communication platform designed with a strong focus on privacy and anonymity. This document outlines the threat model for Hush Line, highlighting potential threats, the data Hush Line collects, how it is secured, and what users can expect in terms of privacy and security.

## Users

| User Type | Goal |
|-|-|
| Submitter | Send a message |
| Receiver | Read messages |
| Verifier | Verifies account owners (journalists, public figures, businesses) |
| Service Provider | Provide Hush Line service |
| Server Admin | Maintain the working order of the application |

## Adversaries

| User Type | Goal |
|-|-|
| Passive Observer | Passively logs client IP addresses and their corresponding inbound/outbound connections |
| Active Observer | Targets specific connections |
| Passive Attacker | Scans the internet for vulnerabilities of which to take advantage |
| Active Attacker | Seeks persistence, exploitation of known vulnerabilities, seizure of physical equipment |

## Assumptions

The following assumptions are accepted in the threat model of the Hush Line product:

### Assumptions About the Individual Submitting a Message

- The individual submitting a message does so in good faith.
- The individual submitting a message wants to remain anonymous against a network observer, forensic analysis, or to Hush Line servers.
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
- The security assumptions of Passlib with randomly generated salts are valid.
- The security/anonymity assumptions of Tor and the Onion service protocol are valid.
- The security assumptions of Hush Line dependencies, specifically Debian, the Linux kernel, application packages, and application dependencies, are valid.

### Other Assumptions or Factors

- The level of press freedom may vary in both geography and time.
- The number of daily Tor users in a country can greatly vary.

## Threats and Mitigations

### Server Compromise

- **Impacts:** If an attacker obtains the database encryption key, its contents may be decrypted. Still, we do not require PII. If you have SMTP delivery configured, your forwarding address will be visible. If you haven't added your own public PGP key to your account, message content will be visible.
- **Mitigation:** Hush Line does not require PII, including an email address, to use the service. To protect message content, users are encouraged to add their own PGP key. We store data encrypted in our database, remove IP addresses and country codes from access logs, and do not store timestamps or associate member data in any way. The database key is never hardcoded and is stored in environment variables, removing the chance of exposure to the source code.

### Network Observers

- **Mitigation:** All data in transit is encrypted using TLS, and users are encouraged to access Hush Line via Tor for additional anonymity. This prevents network observers from deciphering the content or metadata of communications.

### Account Compromise

- **Mitigation:** Strong password policies, optional 2FA, and secure password reset mechanisms are in place to protect user accounts. Users are educated on best practices for maintaining account security.

### Legal and Coercive Pressure

- **Mitigation:** Hush Line is designed to hold minimal information that could be of interest in legal contexts. Furthermore, the use of encryption for stored data ensures that, even under pressure, Hush Line cannot divulge meaningful user data.

## Verification System

Hush Line employs a verification system to ensure that users can trust the source of communication. This system is particularly important for users who are public figures or have a wide audience. The verification system includes:

### Verified Accounts

- **Display of Verification Status:** Hush Line indicates verified accounts with a distinctive badge (⭐️ Verified Account). This visual indicator helps users distinguish authentic accounts from potential impersonators, reducing the risk of phishing attacks.
- **Data Retention:** The information used to verify you is never saved, even temporarily.

## User Education

### Encryption Awareness

- **Encryption Indicators:** The platform informs users whether their messages will be encrypted. For accounts with a public PGP key, messages are encrypted, ensuring that only the intended recipient can decrypt and read them. This feature is highlighted through messages on the submission form, emphasizing the importance of encryption for sensitive information.

### User Guidance

- **Informative Messages for Senders and Receivers:** Hush Line educates its users about the significance of encryption and the steps required to ensure message confidentiality. This includes prompts for receivers to add a public PGP key if they haven't already, and notifications for senders about the encryption status of their message.

## Conclusion

Hush Line's threat model acknowledges the variety of adversaries that users may face and implements a robust security architecture to mitigate these risks. By encrypting data at rest, minimizing data collection, and educating users on security practices, Hush Line aims to offer a secure and private platform for communication.
