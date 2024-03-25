# Hush Line Dev

| Contents |
|-|
| 1. [Local Development](#local-development) |

## Local Development

This guide preps your machine to run Hush Line locally using the included `Makefile`.

### Mac

| Tested Platform | Date |
|-|-|
| Mac M2 | Apr. 2024 |

#### Install Packages
- `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- `brew install python git git-lfs redis rust poetry`
- `echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc`
- `source ~/.zshrc`

#### Clone the Repo
- `https://github.com/scidsg/hushline.git`
- `cd hushline`
- `git switch dev-env` # Temporary until we merge back into Main
- `poetry run make init-db run`

### Windows

| Tested Platform | Date |
|-|-|
|  |  |

## Linux

| Tested Platform | Date |
|-|-|
|  |  |
