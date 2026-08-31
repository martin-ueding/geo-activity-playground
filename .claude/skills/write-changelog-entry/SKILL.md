---
name: write-changelog-entry
description: Style guidelines for writing a changelog entry for this project.
---

# Write a Changelog Entry

## When to use this

After creating a *user visible change*, write a changelog entry.

## Steps

Work on the `main` branch is not released, so new changelog entries go into `## Unreleased`. If that section doesn't exist, create it below the HTML comment line that marks the position.

Document each feature with one of the categories already present at the header of the file.

Write a changelog entry as a bullet list item in imperative and concise style with no more than 160 characters. Only include the "what" in the changelog entry; the "why" is in the ticket, the "how" is in the commit. Don't try to cram everything into a single sentence, use multiple ones. Just keep the detail level sensible and obey the length limit.

Add the relevant GitHub issues in parentheses. These don't count towards the 160 character limit.

A good changelog entry looks like this:

```markdown
- Set the `serve` options host, port, HTTP server, workers and threads via the `GAP_*` environment variables. ([GH-510](https://github.com/martin-ueding/geo-activity-playground/issues/510))
```

Commit using a separate `docs:` commit.

## Verifying

The pre-commit hook will enforce the 160 character limit and create links for all GitHub issues.