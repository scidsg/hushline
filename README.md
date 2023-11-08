# 🤫 Hush Line

[Hush Line](https://hushline.app) is a free and open-source, self-hosted anonymous tip line that makes it easy for organizations or individuals to install and use. It's intended for journalists and newsrooms to offer a public tip line; by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

[More project information...](https://github.com/scidsg/project-info/tree/main/hush-line)

## Easy Install

```bash
curl --proto '=https' --tlsv1.2 -sSfL https://install.hushline.app | bash
```

Need help? Check out our [documentation](https://scidsg.github.io/hushline-docs/book/intro.html) for a full installation guide.

![0-cover](https://github.com/scidsg/hushline/assets/28545431/771b1e4d-2404-4d58-b395-7f4a4cfb6913) 

## QA

| Repo           | Install Type | OS/Source                        | OS Codename  | Installed | Install Gist                           | Display Working | Display Version | Confirmation Email | Home | Info Page | Message Sent | Message Received | Message Decrypted | Close Button | Host          | Auditor | Date        | Commit Hash
|----------------|--------------|----------------------------------|-----------|-----------|---------------------------------------|-----------------|-----------------|--------------------|------|-----------|--------------|------------------|-------------------|--------------|---------------|---------|-------------|--------|
| main           | Tor-only     | Debian 12 x64                    |Bookworm   | ✅         | [link](https://gist.github.com/glenn-sorrentino/cc13f7d0cfd5aefb203362ddc5834f9c)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Digital Ocean | Glenn   | Nov-07-2023 | [08155d0](https://github.com/scidsg/hushline/commit/08155d07d582e44fc12617afdba9e3c95cacdc51)
| main           | Tor + Public | Debian 12 x64                    |Bookworm   | ✅         | [link](https://gist.github.com/glenn-sorrentino/ebd7379566c330ab85000b868e4fb9bb)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Digital Ocean      | Glenn   | Nov-07-2023 | [08155d0](https://github.com/scidsg/hushline/commit/08155d07d582e44fc12617afdba9e3c95cacdc51)
| main           | Tor-only     | Raspberry Pi OS Full (64-bit)    |Bookworm   | ✅         | [link](https://gist.github.com/glenn-sorrentino/6e5fd237c02a916c6f4aa236f5a362d9)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
| main           | Tor-only     | Raspberry Pi OS (Legacy, 64-bit) |Bullseye   | ✅         | [link](https://gist.github.com/glenn-sorrentino/6e5fd237c02a916c6f4aa236f5a362d9)  | NA              | NA              | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
| personal-server| Tor-only     | Raspberry Pi OS (Legacy, 64-bit) |Bullseye   | ✅         | [link](https://gist.github.com/glenn-sorrentino/3de2a2ea11b0228f4892907514b0ac4c)  | ✅              | 2.2             | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB      | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
| ps-0.2a   | Tor-only     | Raspberry Pi OS (Legacy, 64-bit)      |Bullseye   | ✅         |  [link](https://gist.github.com/glenn-sorrentino/dfe7650d23d4666507ea4e778d1da0e8)        | ✅              | 2.2             | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB      | Glenn   | Nov-6-2023 | [e2e826c](https://github.com/scidsg/hushline/tree/e2e826c71de73f785f4530982e222cbbbc800dd4)
| alpha-ps-0.1   | Tor-only     | alpha-ps-0.1.img                 |Bullseye   | ✅         |  NA                                     | ✅              | 2.2             | ✅                  | ✅    | ✅         | ✅            | ✅                | ✅                 | ✅            | Pi 4 4GB      | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
