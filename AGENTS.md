# LLM Instructions

These are the instructions for an LLM coding agent.

Project context:

- This is a hobby project that analyzes outdoor activity tracks.
- This project is a Flask application that uses SQLAlchemy for persistence.
- Documentation is done with Markdown and VitePress.

## Coding

Rule: Use modern Python syntax with type annotations.

Rule: Generate Alembic migrations with `uv run alembic revision --autogenerate -m 'MESSAGE'` using the `database.sqlite` checked into the repository as a schema anchor.
Reason: Writing migrations oneself is error-prone, Alembic does valuable checks.

Rule: Use `_(…)` for user facing strings.

Rule: If similar functionality already exist, please asks me to generalize it before creating duplicated code.
Reason: Duplicated code has a cognitive burden.

## Documentation

Rule: Document changes in the `docs/changelog.md` in the `## Unreleased` section.

Rule: Changelog entries go into separate `docs:` commits.
Reason: Reverting a feature doesn't undo the past.

Rule: When adding a new documentation file, it needs to be added to `docs/.vitepress/config.ts`.

## Git

Rule: Work on `main` in this particular project.

Rule: Add references like `Refs: GH-123` to the trailer of the commit message.

Rule: Never use magic terms like "fixes" that would close a GitHub ticket on push.

Rule: Don't commit code that I haven't reviewed.

Rule: Use conventional commits without scope.
Reason: Version bumps are done based on conventional commits. The project is too small for scopes.
Example: See git log.

## Communication

Rule: Only post updates to the GitHub tickets when I tell you to.

Rule: When posting content to GitHub using the `gh` CLI, be aware of newlines.
Reason: When one isn't careful, literal `\n` end up in the GitHub text.
