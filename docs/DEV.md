# Hush Line Dev

| Contents |
|-|
| 1. [Local Development](#local-development) |

## Local Development

This guide preps your machine to run Hush Line locally using the included `Makefile`.

### Mac

| Tested Platform | OS Version | Browser | Status | Date | Notes |
|-|-|-|-|-|-|
| Macbook M2 | OSX 13.2.1 | Firefox 124.0.2 | ✅ | Apr. 2024 | |
| Macbook M1 | OSX 14.4.1 | Firefox 124.0.2 | ✅ | Apr. 2024 | |
| Macbook M1 | OSX 14.4.1 | Safari 17.4.1 | ☑️ | Apr. 2024 | App starts but a CSRF token mismatch blocks registration. |

#### Install Packages
- `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- `eval "$(/opt/homebrew/bin/brew shellenv)"`
- `brew install python git git-lfs redis rust poetry`

#### Clone the Repo
- `git clone https://github.com/scidsg/hushline.git`
- `cd hushline`
- `git switch dev-env` # Temporary until we merge back into Main
- `/opt/homebrew/bin/python3 -m venv venv`
- `source venv/bin/activate`
- `poetry install`
- `source env.sh`
- `poetry run make init-db run`

### Windows

| Tested Platform | Date |
|-|-|
|  |  |

## Linux

| Tested Platform | Date |
|-|-|
|  |  |
