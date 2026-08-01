# Run the Tests

The test suite lives entirely in the `tests/` directory, mirroring the package structure of `src/geo_activity_playground/`. Run it with:

```bash
uv run pytest
```

## What the tests cover

Most tests drive the application through the Flask test client against an in-memory database, so a single request exercises the view, the database queries and the template together. The fixtures in `tests/conftest.py` provide the building blocks:

- `playground` — a temporary directory as the working directory, since the program addresses its state through relative paths.
- `app` — the application built by the very same `create_app` factory that production uses.
- `client` — a test client for that application.
- `seeded_app` and `seeded_client` — an application whose database has been filled by importing the activity files in `testdata/Zeeland/`, which runs the real import pipeline and therefore yields activities, kinds, equipments, tile visits and clusters.
- `testdata_dir` — the path to the `testdata/` directory.

Templates are rendered with `jinja2.StrictUndefined` in tests. A variable that a view forgets to pass raises an error instead of silently rendering as an empty string. `tests/test_route_crawl.py` fetches every `GET` route of the application against the seeded database, which makes that check apply to the whole web interface.

`tests/test_schema_drift.py` builds a database with the Alembic migrations and compares it against the models. It fails when a model change has no corresponding migration.

## Test data from other users

Activity files from other people are valuable for testing the importers but cannot be committed to this repository. Collect them in a directory somewhere outside the repository and point the environment variable `GAP_TEST_CORPUS` at it:

```bash
GAP_TEST_CORPUS=~/gap-test-corpus uv run pytest
```

`tests/test_external_corpus.py` then parses every activity file in that tree and asserts that it yields a sensible time series. Without the variable the module is skipped. When somebody reports a file that cannot be imported, drop it into that directory.

## Running the tests before pushing

The pre-commit hooks keep committing fast by only running the formatters. The test suite runs on push instead, which needs the pre-push hook to be installed once:

```bash
pre-commit install --hook-type pre-push
```

You can trigger it manually with:

```bash
pre-commit run --hook-stage pre-push --all-files
```
