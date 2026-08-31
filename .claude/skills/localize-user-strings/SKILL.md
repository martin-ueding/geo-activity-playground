---
name: localize-user-strings
description: Internationalize and localize all user-visible strings in the software and translate them to the pertinent languages.
---

# Localize User Strings

## When to use

Whenever you add additional user-visible strings to the program, follow this how-to.

## Steps

### Wrap strings

All user-visible strings need to be wrapped into the `_(…)` function in Python and Jinja code to mark them for internationalization.

**In Jinja2 templates:**

```jinja2
<h1>{{ _('My Page Title') }}</h1>
<p>{{ _('Welcome to the application!') }}</p>
```

**In Python code:**

```python
from flask_babel import gettext as _

flash(_('Activity saved successfully.'), 'success')
```

### Update files

Then run pybabel to extract the template:

```bash
uv run pybabel extract -F babel.cfg -o src/geo_activity_playground/webui/translations/messages.pot .
```

Update the langauge catalogs:

```bash
uv run pybabel update --no-fuzzy-matching -i src/geo_activity_playground/webui/translations/messages.pot -d src/geo_activity_playground/webui/translations
```

### Translate

You'll need to identify the missing strings and translate them. Be careful, don't edit the `.po` files yourself but use proper tooling for that.

### Re-sync

Finally re-sync the project such that the `.mo` files are generated:

```bash
uv sync --reinstall-package geo-activity-playground
```