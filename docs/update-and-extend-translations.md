# Update and Extend Translations

This guide explains how to work with the internationalization (i18n) system in Geo Activity Playground. The project uses [Flask-Babel](https://python-babel.github.io/flask-babel/) for translations, which is based on the standard gettext workflow.

## Overview

Translatable strings in templates are wrapped with `{{ _('...') }}` and in Python code with `_('...')`. These strings are extracted into `.pot` (template) and `.po` (language-specific) files, then compiled into binary `.mo` files that Flask-Babel uses at runtime.

The translation files are located in:

```
geo_activity_playground/webui/translations/
├── messages.pot                    # Template with all extracted strings
└── de/                             # German translations
    └── LC_MESSAGES/
        ├── messages.po             # Human-editable translation file
        └── messages.mo             # Compiled binary (generated)
```

## Adding Translatable Strings

When adding new user-facing text, wrap it with the translation function:

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

## Extracting New Strings

After adding new translatable strings, extract them to update the `.pot` template:

```bash
poetry run pybabel extract -F babel.cfg -o geo_activity_playground/webui/translations/messages.pot .
```

This scans all Python files and Jinja2 templates for `_()` calls and updates the template file.

## Updating Existing Translations

After extracting new strings, update all existing language catalogs:

```bash
poetry run pybabel update --no-fuzzy-matching -i geo_activity_playground/webui/translations/messages.pot -d geo_activity_playground/webui/translations
```

This merges new strings into each language's `.po` file, marking them as untranslated (with empty `msgstr`).

## Adding a New Language

To add support for a new language (e.g., French):

1. Initialize the language catalog:

    ```bash
    poetry run pybabel init -i geo_activity_playground/webui/translations/messages.pot -d geo_activity_playground/webui/translations -l fr
    ```

2. Add the language code to the supported locales in `app.py`:

    ```python
    app.config["BABEL_SUPPORTED_LOCALES"] = ["en", "de", "fr"]
    ```

3. Edit the generated `.po` file at `geo_activity_playground/webui/translations/fr/LC_MESSAGES/messages.po` to add translations.

## Editing Translations

The `.po` files are plain text and can be edited with any text editor. Each entry looks like:

```po
#: geo_activity_playground/webui/templates/page.html.j2:64
msgid "Activities"
msgstr "Aktivitäten"
```

- `#:` shows where the string is used (file and line number)
- `msgid` is the original English string
- `msgstr` is the translation (empty means untranslated)

For a better editing experience, consider using a dedicated PO editor like [Poedit](https://poedit.net/) or online platforms like [Weblate](https://weblate.org/) or [Transifex](https://www.transifex.com/).

## Compiling Translations

After editing `.po` files, compile them into binary `.mo` files:

```bash
poetry run pybabel compile -d geo_activity_playground/webui/translations
```

This must be done before the translations take effect. The `.mo` files are what Flask-Babel reads at runtime.

## Testing Translations

You can test translations by:

- Adding `?lang=de` (or another language code) to any URL
- Setting your browser's language preference
- The application respects the `Accept-Language` HTTP header

## Quick Reference

| Task | Command |
|------|---------|
| Extract strings | `poetry run pybabel extract -F babel.cfg -o geo_activity_playground/webui/translations/messages.pot .` |
| Update existing languages | `poetry run pybabel update --no-fuzzy-matching -i geo_activity_playground/webui/translations/messages.pot -d geo_activity_playground/webui/translations` |
| Add new language | `poetry run pybabel init -i geo_activity_playground/webui/translations/messages.pot -d geo_activity_playground/webui/translations -l LANG` |
| Compile translations | `poetry run pybabel compile -d geo_activity_playground/webui/translations` |

## Typical Workflow

When working on translations, the typical workflow is:

1. Add new `_()` wrapped strings in templates or Python code
2. Extract: `pybabel extract ...`
3. Update: `pybabel update ...`
4. Edit the `.po` files to add translations
5. Compile: `pybabel compile ...`
6. Test in the browser

