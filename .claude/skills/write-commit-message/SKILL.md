---
name: write-commit-message
description: Style rules for writing commit messages in this project.
---

# Write a Commit Message

## When to use this

After you have made some changes, you will be asked to commit. Only commit when asked.

## Prerequesites

The developer had the opportunity to look at the changes and sign them off.

## Steps

Formulate a commit message that uses conventional commits without scopes, e.g. `feat: added widget`.

Add trailers for the GitHub Issue that we're working. Use `Refs: GH-123` by default. If it is completely clear that the commit closes the issues, use `Closes: GH-123` instead.

The code changes go into one commit, the changelog entry goes into a separate commit.