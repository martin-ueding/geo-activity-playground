#!/bin/bash

set -eu

version=$(grep -m 1 '^version = ' pyproject.toml | cut -d '"' -f 2)
today=$(date +%Y-%m-%d)

sed -i "s/## Unreleased/## Version $version — $today/" docs/changelog.md
git ca -m "Bump version to $version"

# Upload the code.
git push

# Tag this version and upload the tag.
git tag "$version"
git push --tags

uv build
uv publish --token "$PYPI_TOKEN_GEO_ACTIVITY_PLAYGROUND"

uv run mkdocs gh-deploy

echo 'Go to https://github.com/martin-ueding/geo-activity-playground/releases/new to create a new release on GitHub.'