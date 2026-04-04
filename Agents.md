# LLM Instructions

These are the instructions for an LLM coding agent.

This project is a Flask application that uses SQLAlchemy for persistence.

Use modern Python syntax with type annotations.

Don't try to generate Alembic migrations by hand. Just let me run the migration generation script myself.

This project is i18n'ed. Use `_(…)` for user facing strings.

If similar functionality already exist, please asks me to generalize it before creating duplicated code.

You can likely use the `gh` command line utility to make use of GitHub. The tickets are part of a project and are moved along the statuses there. I let the users know about the status when I make changes. Be careful of newline handling. If one is not careful, literal `\n` end up in the GitHub text.

Changes are documented in `docs/changelog.md`, the format is documented within and should be obvious. New changelog entries always go into a `## Unreleased` section, not to existing released versions.

## Ticket status commands (resolved IDs)

Use these exact constants for this repository/project:

- Owner: `martin-ueding`
- Repo: `martin-ueding/geo-activity-playground`
- Project: `GAP Kanban` (`number 4`, `id PVT_kwHOAA7oHM4A9xal`)
- Status field id: `PVTSSF_lAHOAA7oHM4A9xalzgxX-6Q`
- Status options:
  - Backlog: `f75ad846`
  - Ready: `61e4505c`
  - In Progress: `47fc9ee4`
  - Ready for Release: `df73e18b`
  - Waiting for User Feedback: `98236657`
  - Done: `6c55a62d`

Copy/paste flow for an issue number:

```bash
ISSUE_NUMBER=418
ITEM_ID=$(gh project item-list 4 --owner martin-ueding --format json | jq -r ".items[] | select(.content.type==\"Issue\" and .content.number==${ISSUE_NUMBER}) | .id")
gh project item-edit --id "$ITEM_ID" --project-id "PVT_kwHOAA7oHM4A9xal" --field-id "PVTSSF_lAHOAA7oHM4A9xalzgxX-6Q" --single-select-option-id "df73e18b"
gh issue view "$ISSUE_NUMBER" --repo "martin-ueding/geo-activity-playground" --json number,title,projectItems
```