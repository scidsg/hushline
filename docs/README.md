# Hush Line Documentation

For the most up-to-date end-user documentation visit https://hushline.app/docs.html.

## Contents

1. [Deploying Development Instances](#deploying-development-instances)
2. [Local Development Environment](#local-development-environment)
3. [Configuration](#configuration)

## Deploying Development Instances

PRs opened against the `scisdg/hushline` repo can be deployed to isolated development instances.

### Pre-requisites

In order to create and destroy development instances, you will need the ability to tag pull requests. This requires "triage" permissions on the `scisdg/hushline` repo at minimum.

### Requirements

In order to successfully deploy a development instance, a PR must successfully build the docker image. If the docker image fails to build (which includes tests passing) it will fail to deploy.

### Deploying a Development Instance

To create a development instance from a pull request, add the `deploy` label to the PR, triggering the `Deploy/Destroy Branch Dev Environment` GitHub Actions workflow. This workflow will create a new Terraform workspace for the staged changes, plan, and apply the changes. Once this workflow completes, a comment with the url for the development instance will be added to the pull request.

### Redeploying after pushing changes to the PR

When changes are pushed to a PR which has been deployed to a development instance, the development instance will automatically be redeployed. You do not need to re-run the `deploy` workflow.

### Destroying dev instances

Dev instances are automatically destroyed when a PR is closed or merged. Additionally, dev instances can be explicitly destroyed by applying the `destroy` label.

### Caveats

The destroy workflow will only attempt to destroy development instances if the PR has the `deploy` label. This is to avoid failed destroy workflow runs on PRs which were never deployed.

## Local Development Environment

Hush Line is written in Python. To ensure code integrity and consistency, we use [Ruff](https://docs.astral.sh/ruff/) for linting and [mypy](https://www.mypy-lang.org/) for static type checking.

The recommended development environment is [Visual Studio Code](https://code.visualstudio.com/) with the following extensions:

- [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Mypy](https://marketplace.visualstudio.com/items?itemName=matangover.mypy)

You need Python, Poetry, and pipx. If you're on macOS, install these with [Homebrew](https://brew.sh/):

```sh
brew install python poetry pipx
```

We use Docker containers to run Hush Line. Download Docker Desktop, then start the application.

You also need Rust to install some of the Python dependencies. Install [rustup](https://rustup.rs/) like this:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### Getting started

**Clone the Hush Line code:**

```sh
git clone https://github.com/scidsg/hushline.git
cd hushline
```

**Launch Hush Line:**

```sh
docker compose up
```

**Run one of the database migrations:**

```sh
make migrate-dev  # for current dev DB settings
make migrate-prod # for current alembic migrations
```

**Run the app in debug mode:**

```sh
make run
```

**Run the tests:**

```sh
# in one terminal
./scripts/local-postgres.sh
# in another terminal
make test
```

**Run the linters:**

```sh
make lint
```

**Format the code:**

```sh
make fix
```

### Making DB changes

Create a new revision:

```sh
make revision name="my db changes"
```

Test the migrations:

```sh
PYTEST_ADDOPTS='--alembic' make test
```

## Testing with Stripe

```sh
make run-full
```

In a separate terminal:

```sh
stripe listen --forward-to localhost:8080/premium/webhook
```

## Configuration

Hush Line is configured via environment variables.
The following env vars are available to configure the app.

Note: There may be additional env vars the code uses, but if they are undocumented, their use is unsupported.

To support customization of the app, there are two methods of setting arbitrary config values.

- All values of the form `HL_CFG_*` will have the prefix `HL_CFG_` stripped and will be set as strings in the config. (e.g., `HL_CFG_FOO='bar'` will set the config `FOO` to the string `bar`)
- All values of the form `HL_CFG_JSON_*` will have the prefix `HL_CFG_JSON_` stripped and will be parsed as JSON then set in the config. (e.g., `HL_CFG_FOO='123'` will set the config `FOO` to the int `123` and `HL_CFG_BAZ='"true"'` [note the quotes] will the config `BAZ` to the string `true`)

### Web App

These configs are needed for the web app.

<table>
  <thead>
    <tr>
      <th>Env Var</th>
      <th>Required</th>
      <th>Type/Format</th>
      <th>Default</th>
      <th>Purpose</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>ALIAS_MODE</code></td>
      <td>false</td>
      <td>string</td>
      <td><code>always</code></td>
      <td>
        Whether users should be able to create "aliases" (additional usernames by which they are addressable).
        Values:
          `always` - users can always create unlimited aliases.
          `premium` - only users with a paid plan can create a limited number of aliases.
          `never` - aliases are disabled for all users.
      </td>
    </tr>
    <tr>
      <td><code>DIRECTORY_VERIFIED_TAB_ENABLED</code></td>
      <td>false</td>
      <td>boolean</td>
      <td><code>true</code></td>
      <td>
        Enable the "Verified" tab on the Hush Line directory.
        When set to <code>true</code>, the directory shows only verified users with a second tab for all users.
        When set to <code>false</code>, a single tab with all users is displayed.
      </td>
    </tr>
    <tr>
      <td><code>ENCRYPTION_KEY</code></td>
      <td>true</td>
      <td>string</td>
      <td></td>
      <td>The key used for handling crypto operations on DB fields.</td>
    </tr>
    <tr>
      <td><code>ONION_HOSTNAME</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>Tor Onion Service host name that the Hush Line app is additionally available as.</td>
    <tr>
      <td><code>NOTIFICATIONS_ADDRESS</code></td>
      <td>false</td>
      <td>email address</td>
      <td></td>
      <td>Email address to use for sending message notifications</td>
    </tr>
    <tr>
      <td><code>REGISTRATION_CODES_REQUIRED</code></td>
      <td>false</td>
      <td>boolean</td>
      <td><code>true</code></td>
      <td>Whether or not new user registrations require invite codes.</td>
    </tr>
    <tr>
      <td><code>REQUIRE_PGP</code></td>
      <td>false</td>
      <td>boolean</td>
      <td><code>false</code></td>
      <td>Whether users are required to use PGP to receive messages.</td>
    </tr>
    <tr>
      <td><code>SECRET_KEY</code></td>
      <td>true</td>
      <td>string</td>
      <td></td>
      <td>The Flask secret key used for signing cookies.</td>
    </tr>
    <tr>
      <td><code>SERVER_NAME</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>Set the server/host name in Flask</td>
    </tr>
    <tr>
      <td><code>SMTP_ENCRYPTION</code></td>
      <td>false</td>
      <td>string</td>
      <td>StartTLS</td>
      <td>SMTP encryption method for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_FORWARDING_MESSAGE_HTML</code></td>
      <td>false</td>
      <td>HTML</td>
      <td></td>
      <td>Message to display on the Email settings page below the SMTP forwarding config.</td>
    </tr>
    <tr>
      <td><code>SMTP_PASSWORD</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>SMTP password for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_PORT</code></td>
      <td>false</td>
      <td>integer</td>
      <td></td>
      <td>SMTP port for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_SERVER</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>SMTP server for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_USERNAME</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>SMTP username for sending notifications</td>
    </tr>
    <tr>
      <td><code>SQLALCHEMY_DATABASE_URI</code></td>
      <td>true</td>
      <td>URL</td>
      <td></td>
      <td>SqlAlchemy database connection string</td>
    </tr>
    <tr>
      <td><code>STRIPE_PUBLISHABLE_KEY</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/keys" target="_blank">Stripe publishable key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>STRIPE_SECRET_KEY</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/keys" target="_blank">Stripe secret key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>STRIPE_WEBHOOK_SECRET</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/webhooks#endpoint-secrets" target="_blank">Stripe webhook key</a> for enabling payments</td>
    </tr>
  </tbody>
</table>

### Stripe Worker

<table>
  <thead>
    <tr>
      <th>Env Var</th>
      <th>Required</th>
      <th>Type/Format</th>
      <th>Default</th>
      <th>Purpose</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>SQLALCHEMY_DATABASE_URI</code></td>
      <td>true</td>
      <td>URL</td>
      <td></td>
      <td>SqlAlchemy database connection string</td>
    </tr>
    <tr>
      <td><code>STRIPE_PUBLISHABLE_KEY</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/keys" target="_blank">Stripe publishable key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>STRIPE_SECRET_KEY</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/keys" target="_blank">Stripe secret key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>STRIPE_WEBHOOK_SECRET</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/webhooks#endpoint-secrets" target="_blank">Stripe webhook key</a> for enabling payments</td>
    </tr>
  </tbody>
</table>
