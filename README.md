# 🤫 Hush Line

[Hush Line](https://hushline.app) is a free and open-source, self-hosted anonymous tip line that makes it easy for organizations or individuals to install and use. It's intended for journalists and newsrooms to offer a public tip line; by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

[More project information...](https://github.com/scidsg/project-info/tree/main/hush-line)

## Easy Install

```bash
curl --proto '=https' --tlsv1.2 -sSfL https://install.hushline.app | bash
```

Need help? Check out our [documentation](https://scidsg.github.io/hushline-docs/book/intro.html) for a full installation guide.

![0-cover](https://github.com/scidsg/hushline/assets/28545431/771b1e4d-2404-4d58-b395-7f4a4cfb6913) 

## Contribution Guidelines

❤️ We're excited that you're interested in contributing to Hush Line. To maintain the quality of our codebase and ensure the best experience for everyone, we ask that you follow these guidelines:

### Code of Conduct

By contributing to Hush Line, you agree to our [Code of Conduct](https://github.com/scidsg/business-resources/blob/main/Policies%20%26%20Procedures/Code%20of%20Conduct.md).

### Reporting Bugs

If you find a bug in the software, we appreciate your help in reporting it. To report a bug:

1. **Check Existing Issues**: Before creating a new issue, please check if it has already been reported. If it has, you can add any new information you have to the existing issue.
2. **Create a New Issue**: If the bug hasn't been reported, create a new issue and provide as much detail as possible, including:
   - A clear and descriptive title.
   - Steps to reproduce the bug.
   - Expected behavior and what actually happens.
   - Any relevant screenshots or error messages.
   - Your operating system, browser, and any other relevant system information.

### Submitting Pull Requests

Contributions to the codebase are submitted via pull requests (PRs). Here's how to do it:

1. **Create a New Branch**: Always create a new branch for your changes.
2. **Make Your Changes**: Implement your changes in your branch.
3. **Follow Coding Standards**: Ensure your code adheres to the coding standards set for this project.
4. **Write Good Commit Messages**: Write concise and descriptive commit messages. This helps maintainers understand and review your changes better.
5. **Test Your Changes**: Before submitting your PR, test your changes thoroughly. Please link to a [Gist](https://gist.github.com) containing your terminal's output of the end-to-end install of Hush Line. For an example of a Gist, refer to the QA table below under the "Install Gist" column.
6. **Create a Pull Request**: Once you are ready, create a pull request against the main branch of the repository. In your pull request description, explain your changes and reference any related issue(s).
7. **Review by Maintainers**: Wait for the maintainers to review your pull request. Be ready to make changes if they suggest any.

By following these guidelines, you help to ensure a smooth and efficient contribution process for everyone.

## QA

| Repo           | Install Type | Host              | OS/Source                        | OS Codename  | Installed  | Install Gist                                                                       | Display Working | Display Version | Confirmation Email | Home | Info Page | Message Sent | Message Received | Message Decrypted | Close Button | Auditor | Date        | Commit Hash
|----------------|--------------|-------------------|----------------------------------|--------------|-------------------------------------------------------------------------------------------------|-----------------|-----------------|--------------------|------|-----------|--------------|------------------|-------------------|--------------|---------|-------------|-------------|--------|
| main           | Tor-only     | Digital Ocean     | Debian 12 x64                    | Bookworm     | ✅         | [link](https://gist.github.com/glenn-sorrentino/7774228a6750c4a7418860ed66ae2a8f)  | NA              | NA              | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Nov-14-2023 | [6fc9d61](https://github.com/scidsg/hushline/pull/186/commits/6fc9d61369f54e7663dc3eabf3dbcdd3b0016eaf)
| main           | Tor + Public | Digital Ocean     | Debian 12 x64                    | Bookworm     | ✅         | [link](https://gist.github.com/glenn-sorrentino/ebd7379566c330ab85000b868e4fb9bb)  | NA              | NA              | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Nov-07-2023 | [08155d0](https://github.com/scidsg/hushline/commit/08155d07d582e44fc12617afdba9e3c95cacdc51)
| main           | Tor-only     | Pi 5 4GB          | Raspberry Pi OS Full (64-bit)    | Bookworm     | ✅         | [link](https://gist.github.com/glenn-sorrentino/2855a078d775f92f11b21876b61b8699)  | NA              | NA              | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Nov-13-2023 | [08155d0](https://github.com/scidsg/hushline/commit/08155d07d582e44fc12617afdba9e3c95cacdc51)
| main           | Tor-only     | Pi 4 4GB          | Raspberry Pi OS Full (64-bit)    | Bookworm     | ✅         | [link](https://gist.github.com/glenn-sorrentino/c144d92346095682539a0735eebb06e7)  | NA              | NA              | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Nov-08-2023 | [08155d0](https://github.com/scidsg/hushline/commit/08155d07d582e44fc12617afdba9e3c95cacdc51)
| main           | Tor-only     | Pi 4 4GB          | Raspberry Pi OS (Legacy, 64-bit) | Bullseye     | ✅         | [link](https://gist.github.com/glenn-sorrentino/6e5fd237c02a916c6f4aa236f5a362d9)  | NA              | NA              | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
| personal-server| Tor-only     | Pi 4 4GB          | Raspberry Pi OS (Legacy, 64-bit) | Bullseye     | ✅         | [link](https://gist.github.com/glenn-sorrentino/3de2a2ea11b0228f4892907514b0ac4c)  | ✅              | 2.2             | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
| ps-0.2a        | Tor-only     | Pi 4 4GB          | Raspberry Pi OS (Legacy, 64-bit) | Bullseye     | ✅         | [link](https://gist.github.com/glenn-sorrentino/dfe7650d23d4666507ea4e778d1da0e8)  | ✅              | 2.2             | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Nov-6-2023  | [e2e826c](https://github.com/scidsg/hushline/tree/e2e826c71de73f785f4530982e222cbbbc800dd4)
| alpha-ps-0.1   | Tor-only     | Pi 4 4GB          | alpha-ps-0.1.img                 | Bullseye     | ✅         |  NA                                                                                | ✅              | 2.2             | ✅                | ✅    | ✅       | ✅           | ✅              | ✅                | ✅           | Glenn   | Oct-25-2023 | [984ad9c](https://github.com/scidsg/hushline/tree/984ad9c86b547ccd2af3dac124f9294f4d1e1c4b)
