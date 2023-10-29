# 🤫 Hush Line

[Hush Line](https://hushline.app) is a free and open-source, self-hosted anonymous tip line that makes it easy for organizations or individuals to install and use. It's intended for journalists and newsrooms to offer a public tip line; by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

## Easy Install

```bash
curl --proto '=https' --tlsv1.2 -sSfL https://install.hushline.app | bash
```

Still need help? Check out our [documentation](https://scidsg.github.io/hushline-docs/book/intro.html) for more information.

![0-cover](https://github.com/scidsg/hushline/assets/28545431/771b1e4d-2404-4d58-b395-7f4a4cfb6913)

[See more project information](https://github.com/scidsg/project-info/tree/main/hush-line).

## Why Hush Line?

Other tools in this space include SecureDrop and GlobalLeaks, two robust, widely adopted whistleblowing platforms whose installation can be complicated for non-technical users. Some systems require an admin to configure it and special infrastructure for it to operate. The security posture of these platforms is increased because the chances are high that you'll receive malicious and dirty data when you allow people to send you files anonymously. Both require significant time and money to manage. It's not much easier for the person sending a message, either. They might have to create accounts, download new software, or manage PGP keys. It requires a significant commitment. Even tools like Signal or Protonmail require end-users to reveal information about themselves unless they can find disposable phone numbers and email addresses. Not a requirement everyone feels comfortable with.

In contrast, Hush Line is a text-only, one-way messenger that is the first handshake in a relationship where two parties want to exchange information. It's a low-risk method of offering a safe channel for someone to reach you without requiring them to reveal anything about themselves, create an account, manage PGP keys, or acquire a burner phone, email address, or phone number.

The tool deploys to either an onion-only instance or Tor + public web. Hush Line is a web and email server and a Python app that encrypts messages with your public PGP key once a message gets submitted, then saves it, and finally emails the encrypted message to you. Your data never gets saved in an unencrypted state. And since all messages are sent to your email, you never have to log in to the device.

We configure Nginx with hardened security headers so no external and potentially nefarious resources can load, automatically set up renewing Let's Encrypt HTTPS certificates so your data is always transmitted safely, privacy-preserving logging which scrubs IP addresses before saving to server logs, and enable automatic updates by default so you never miss a critical security patch.

You only need a public PGP key on a keyserver and an SMTP-compatible email address. We ask for your key this way because uploading it includes verifying your email address, which helps us know you are who you say.

Built with popular and ubiquitous hardware and software in mind, Hush Line works seamlessly on Raspberry Pi and Debian-based operating systems. You can even add an e-paper display to make your Hush Line address easy to discover.

We offer a solution for those who want to help, who might have reportable or actionable information, but don't want to face retaliation or take on the risks of getting involved. In fact, over 70% of people have witnessed or experienced workplace harassment. Only 15% of those people ever make a formal written complaint. About 1% ever has something done about it. That's a big oversight for employers, which could become a significant liability left unattended. And the reason people don't report? They're afraid of retaliation.

How much better, safer, and more informed could our schools, workplaces, and society be with a safe way to share information that places the privacy of  communities first?

## QA

| Repo           | Install Type | OS/Source                        | Installed | Install Gist                           | Display Working | Display Version | Confirmation Email | Home | Info Page | Message Sent | Message Received | Message Decrypted | Close Button | Host          | Auditor | Date        |
|----------------|--------------|----------------------------------|-----------|---------------------------------------|-----------------|-----------------|--------------------|------|-----------|--------------|------------------|-------------------|--------------|---------------|---------|-------------|
| main           | Tor-only     | Debian 12 x64                    | ✅         | [link](https://gist.github.com/glenn-sorrentino/fd02fdc9e200a05183538b462919f9c3)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Digital Ocean | Glenn   | Oct-29-2023 |
| main           | Tor + Public | Debian 12 x64                    | ✅         | [link](https://gist.github.com/glenn-sorrentino/ae8e371486d16ab4ece10a51302e2a50)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Digital Ocean      | Glenn   | Oct-25-2023 |
| main           | Tor-only     | Raspbery Pi OS (Legacy, 64-bit)  | ✅         | [link](https://gist.github.com/glenn-sorrentino/6e5fd237c02a916c6f4aa236f5a362d9)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB | Glenn   | Oct-25-2023 |
| personal-server| Tor-only     | Raspbery Pi OS (Legacy, 64-bit)  | ✅         | [link](https://gist.github.com/glenn-sorrentino/3de2a2ea11b0228f4892907514b0ac4c)  | ✅              | 2.2             | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB      | Glenn   | Oct-25-2023 |
| alpha-ps-0.1   | Tor-only     | alpha-ps-0.1.img                 | ✅         |  NA                                     | ✅              | 2.2             | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB      | Glenn   | Oct-25-2023 |
