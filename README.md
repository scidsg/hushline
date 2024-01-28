# 🤫 Hush Line Personal Server

[Hush Line](https://hushline.app) Personal Server is the physical product for our free and open-source, anonymous tip line for organizations or individuals. It's for those who need uncompromising anonymity for their sources and complete control of their infrastructure. It comes ready to set up through a no-code, no-terminal, full-guided process. 

![IMG_7418](https://github.com/scidsg/hushline/assets/28545431/7f5470ca-a4f8-445a-87be-ea3de6cf26ff)
![IMG_7421](https://github.com/scidsg/hushline/assets/28545431/6fb3626a-a485-4156-8a5d-f894e46f3f4a)
![IMG_7359](https://github.com/scidsg/hushline/assets/28545431/5404f7eb-6782-47ef-9dd0-ce88b142fe72)

## Host it Yourself
Prefer to host it on your own hardware? 

### Easy Install
```bash
export DEBIAN_FRONTEND=noninteractive && apt update && apt -y dist-upgrade && apt -y autoremove && apt install -y git && git clone https://github.com/scidsg/hushline && cd hushline && chmod +x install.sh && ./install.sh
```

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
