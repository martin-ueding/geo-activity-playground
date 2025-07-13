#!/bin/bash

set -eu

version="$(poetry version --short)"
today=$(date +%Y-%m-%d)

sed -i "s/## Unreleased/## Version $version — $today/" docs/changelog.md
git ca -m "Bump version to $version"

# Upload the code.
git push

# Tag this version and upload the tag.
git tag "$(poetry version --short)"
git push --tags

poetry build
poetry publish --username __token__ --password "$PYPI_TOKEN_GEO_ACTIVITY_PLAYGROUND"

poetry run mkdocs gh-deploy

echo 'Go to https://github.com/martin-ueding/geo-activity-playground/releases/new to create a new release on GitHub.'