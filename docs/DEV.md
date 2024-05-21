# Hush Line Development

👋 Welcome to the Hush Line Development setup guide. This document provides detailed instructions for configuring your local development environment across Mac, Windows, and Linux systems. It includes specific steps for installing dependencies, cloning the repository, and initiating a local server using the included `Makefile`. The guide also covers utilizing tests, linters, and formatters to ensure code integrity and consistency. Follow these instructions to prepare your machine for Hush Line development 👇.

<img src="https://github.com/scidsg/hushline/assets/28545431/3108811e-226e-4451-9793-c893da96184c" width="80%">

<h2>Local Development</h2>

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) for your platform.

Clone the repo:

```sh
git clone https://github.com/scidsg/hushline.git
cd hushline
```

Start Hush Line for development:

```sh
make dev
```

Test changes:

```sh
make test
```

If you need to get a shell in the container to manually run commands:

```sh
make shell
```
