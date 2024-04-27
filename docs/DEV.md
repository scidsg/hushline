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
1. `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
2. `eval "$(/opt/homebrew/bin/brew shellenv)"`
3. `brew install python git git-lfs redis rust poetry`

#### Clone the Repo
4. `git clone https://github.com/scidsg/hushline.git`
5. `cd hushline`
6. `/opt/homebrew/bin/python3 -m venv venv`
7. `source venv/bin/activate`
8. `poetry install`
9. `source env.sh`
10. `sudo lsof -ti:5000 | xargs kill -9` _Optional_
11. `poetry run flask db upgrade` _Optional_
12. `poetry run make init-db run`

### Windows

| Tested Platform | Date |
|-|-|
|  |  |

### Linux

| Tested Platform | Date |
|-|-|
|  |  |
