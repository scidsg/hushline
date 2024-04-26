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

#### Test Changes

1. `poetry run pre-commit run --all-files --verbose`

The expected output looks like this:

```
(venv) glennsorrentino@m1 hushline % poetry run pre-commit run --all-files --verbose
trim trailing whitespace.................................................Passed
- hook id: trailing-whitespace
- duration: 0.06s
fix end of files.........................................................Passed
- hook id: end-of-file-fixer
- duration: 0.05s
check yaml...............................................................Passed
- hook id: check-yaml
- duration: 0.04s
check for added large files..............................................Passed
- hook id: check-added-large-files
- duration: 0.08s
black....................................................................Passed
- hook id: black
- duration: 0.23s

All done! ✨ 🍰 ✨
20 files left unchanged.

isort....................................................................Passed
- hook id: isort
- duration: 0.09s
flake8...................................................................Passed
- hook id: flake8
- duration: 0.3s
mypy.....................................................................Passed
- hook id: mypy
- duration: 0.2s

Success: no issues found in 20 source files

(venv) glennsorrentino@m1 hushline %
```
2. `poetry run make test`

The expected output shold look like this:

```
(venv) glennsorrentino@m1 hushline % make test
================================================================================ test session starts ================================================================================
platform darwin -- Python 3.12.2, pytest-8.1.1, pluggy-1.5.0 -- /Users/glennsorrentino/Nextcloud/Git/hushline/venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/glennsorrentino/Nextcloud/Git/hushline
configfile: pyproject.toml
plugins: mock-3.14.0
collected 8 items

tests/test_registration_and_login.py::test_user_registration_with_invite_code_disabled PASSED                                                                                 [ 12%]
tests/test_registration_and_login.py::test_user_registration_with_invite_code_enabled PASSED                                                                                  [ 25%]
tests/test_registration_and_login.py::test_register_page_loads PASSED                                                                                                         [ 37%]
tests/test_registration_and_login.py::test_login_link PASSED                                                                                                                  [ 50%]
tests/test_registration_and_login.py::test_registration_link PASSED                                                                                                           [ 62%]
tests/test_registration_and_login.py::test_user_login_after_registration PASSED                                                                                               [ 75%]
tests/test_submit_message.py::test_submit_message_page_loads PASSED                                                                                                           [ 87%]
tests/test_submit_message.py::test_submit_message PASSED
```

### Windows

| Tested Platform | Date |
|-|-|
|  |  |

## Linux

| Tested Platform | Date |
|-|-|
|  |  |
