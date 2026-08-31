---
name: add-github-comment
description: Style rules for commenting on GitHub Issues.
---

# Add a GitHub Comment

## When to use

You have worked out changes and discussed them in the interactive agent session (Claude Code). After all the changes are signed off and you're told to update the user about the changes, you may post a comment.

## Steps

Formulate a concise and brief message in en-US for the user who reported the ticket. The user shall learn *what* has changed, *how* it was implemented, and *why* the implementation deviates from their original question.

Create a temporary Markdown file according to the following structure:

```markdown
[AI-generated]

## Changes made

## Implementation background
```

Do not use hard-wrap here.

Then add that as a comment to the given issue using this command line template:

```bash
gh issue comment $ISSUE_NUMBER --body-file $BODY_FILE
```