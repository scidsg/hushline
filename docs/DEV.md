# Developer Docs

## Creating Database Migrations

We use the [SQLAlchemy](https://www.sqlalchemy.org/) ORM for our database and manage migrations with [Alembic](https://alembic.sqlalchemy.org/).
When you update database models, you will need to create an Alembic migration so that the production database will be updated.

When your code changes are ready, create a migration by running the command the command `MESSAGE='some message' make new-database-migration` where `MESSAGE` is a short and concise message explaining what the migration does.

Migrations are tested as part of the test suite.
You will need to write your own tests to ensure the upgrade and downgrade behave as expected.
See [`./tests/test_migrations.py`](./tests/test_migrations.py) and [`./tests/migrations/`](./tests/migrations/) for examples.

## Submit Loading Feedback

The login, registration, and public submit-message forms use a submit-button spinner while POST/GET requests from those submit actions are in progress.

## Canonical External URLs

Security-sensitive absolute URLs must be generated from canonical deployment config, not from the incoming request host.

Set one of these in deployed environments:

- `PUBLIC_BASE_URL=https://your-public-origin`
- `SERVER_NAME=your-public-hostname`

`PUBLIC_BASE_URL` is preferred for user-visible or third-party callback URLs because it pins both scheme and host. If neither value is set, production requests that need canonical external URLs will now fail closed instead of deriving the host from request headers.
