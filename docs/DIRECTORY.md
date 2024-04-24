# Directory Structure

## Hush Line Core

```
hushline/
├── docs/
├── files/
├── hushline/
│   ├── __init__.py
│   ├── ...
│   ├── static/
│   └── templates/
├── migrations/
├── tests/
├── .env
├── .pre-commit-config.yaml
├── env.sh # For Makefile
├── Makefile
├── docker-compose.yml
├── poetry.lock
├── pyproject.toml
└── setup.cfg
```


## Hush Line Infrastructure

```
hushline-infra/
├── etc/
│   └── tor/
│       └── torrc
├── opt/
│   └── nginx/
│       ├── hushline.conf
│       └── nginx.conf
├── root/
│   ├── .profile
│   └── .screenrc
├── deploy-config.yaml
├── deploy-nginx.yaml
├── devops.py
└── variables.json
```
