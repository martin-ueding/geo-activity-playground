# LLM Instructions

These are the instructions for an LLM coding agent.

This project is a Flask application that uses SQLAlchemy for persistence.

Use modern Python syntax with type annotations.

Don't try to generate Alembic migrations by hand. Just let me run the migration generation script myself.

This project is i18n'ed. Use `_(…)` for user facing strings.

If similar functionality already exist, please asks me to generalize it before creating duplicated code.

You can likely use the `gh` command line utility to make use of GitHub. The tickets are part of a project and are moved along the statuses there. I let the users know about the status when I make changes.

Changes are documented in `docs/changelog.md`, the format is documented within and should be obvious. New changelog entries always go into a `## Unreleased` section, not to existing released versions.