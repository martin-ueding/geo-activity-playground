#!/bin/bash

set -eu

# Upload the code.
git push

# Tag this version and upload the tag.
git tag "$(poetry version --sort)"
git push --tags

poetry build
poetry publish --username __token__ --password "$PYPI_TOKEN_GEO_ACTIVITY_PLAYGROUND"

poetry run mkdocs gh-deploy