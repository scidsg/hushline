# Local Contributor Onboarding Prompt

This document is a copy-paste prompt for an AI assistant that will walk a brand-new contributor through getting Hush Line running locally with Docker.

It is designed for someone starting from a completely new machine and assumes little or no terminal, Git, or Docker experience.

## How To Use It

1. Open your AI assistant of choice.
2. Copy the full prompt below into a new chat.
3. Answer the assistant's first question with your operating system: `macOS`, `Windows`, or `Linux`.
4. Follow the steps one at a time.
5. If anything fails, paste the exact error message back into the chat.

## Prompt

```text
Help a brand-new, non-technical contributor get Hush Line running locally with Docker on a completely new machine.

Requirements:
- explain every step in plain English
- do not assume terminal, Git, Docker, or software development experience
- proceed one step at a time
- after each major step, ask the user to confirm what they see before moving on
- if something fails, troubleshoot calmly using the exact error message
- avoid jargon unless you define it immediately
- do not dump the entire setup at once
- break everything into small numbered steps
- include copy/paste commands in fenced code blocks
- when GUI steps are involved, tell the user exactly where to click
- always explain what success looks like before moving on
- adapt instructions to the user’s operating system
- if you do not yet know their operating system, ask first

Project context:
- Project name: Hush Line
- Repository URL: https://github.com/scidsg/hushline
- Local app URL after startup: http://localhost:8080

Important setup facts:
- Hush Line uses Docker for the main local development stack
- for basic local setup, the user does NOT need to install Python, Poetry, Node, npm, Postgres, or LocalStack on the host machine
- the host machine DOES need:
  - Git
  - Make
  - Docker Desktop or Docker Engine with Docker Compose
  - a terminal application
  - optionally a code editor such as VS Code

Repository commands to use:
- start the app:
  - `docker compose up`
- common commands:
  - `make lint`
  - `make test`
  - `docker compose down -v --remove-orphans`
- if a clean bootstrap is needed:
  - `./scripts/agent_issue_bootstrap.sh`

Operating system guidance:
- on macOS:
  - Git and Make usually come from Xcode Command Line Tools
  - Docker Desktop is the preferred Docker install
- on Windows:
  - prefer WSL2 with Ubuntu plus Docker Desktop integration
- on Linux:
  - install Git, Make, Docker Engine, and the Docker Compose plugin using the native package manager

Use this process:
1. Ask the user which operating system they are using:
   - macOS
   - Windows
   - Linux
2. Give exact install steps for that operating system.
3. Verify each required tool with commands such as:
   - `git --version`
   - `make --version`
   - `docker --version`
   - `docker compose version`
4. Help the user clone the repository:
   - `git clone https://github.com/scidsg/hushline.git`
   - `cd hushline`
5. Make sure Docker is actually running before startup.
6. Start Hush Line locally:
   - first try `docker compose up`
   - explain that the first run may take several minutes
   - explain that Docker may download images and build containers during the first run
7. If the app does not come up cleanly, use the reset/bootstrap path:
   - `docker compose down -v --remove-orphans`
   - `./scripts/agent_issue_bootstrap.sh`
   - then rerun `docker compose up`
8. Once the app is running, tell the user to open:
   - `http://localhost:8080`
9. Confirm that they can see the Hush Line homepage.
10. End with a short beginner-friendly tutorial of the top 3 local flows.

Repository-specific tutorial details:
- local dev seed data includes demo users
- use these local-only demo credentials:
  - username: `admin`
  - password: `Test-testtesttesttest-1`
  - username: `artvandelay`
  - password: `Test-testtesttesttest-1`
- make clear that these are local demo accounts only

The final tutorial must cover these 3 flows:

Flow 1: Anonymous visitor sends a message
- open `http://localhost:8080`
- open the directory
- open a profile such as `Art Vandelay`
- start the message form
- fill out a test message
- solve the math captcha if shown
- submit the message
- explain what success looks like

Flow 2: Recipient logs in and checks the inbox
- log out if needed
- go to the login page
- log in as:
  - username: `artvandelay`
  - password: `Test-testtesttesttest-1`
- open the Inbox
- click a sample message
- change the message status if that option is visible
- explain what success looks like

Flow 3: Admin logs in and changes a visible setting
- log out if needed
- log in as:
  - username: `admin`
  - password: `Test-testtesttesttest-1`
- go to the admin/settings area
- choose one simple visible change, such as a guidance or branding-related setting
- save it
- refresh the relevant page to confirm the change worked
- explain what success looks like
- remind the user that this is local demo data, so it is safe to experiment

Troubleshooting guidance:
- if Docker is installed but not running, explain how to open Docker Desktop and wait for it to finish starting
- if a command says “command not found,” explain what that means and how to install the missing tool
- if ports are already in use, explain that another app is already using that address and suggest stopping old Docker containers first
- if the first build takes a long time, explain that this is normal and the first run is the slowest
- if the user gets stuck, ask for the exact error message and continue from there

Start by asking:
“What operating system are you using: macOS, Windows, or Linux?”
```
