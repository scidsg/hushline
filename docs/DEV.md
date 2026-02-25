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
