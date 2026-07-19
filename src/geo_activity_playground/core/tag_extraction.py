import logging
import re

import sqlalchemy

from .datamodel import DB, Activity, Tag

logger = logging.getLogger(__name__)

SPACE_PATTERN = re.compile(r"\s+")


def apply_tag_extraction(activity: Activity, tags: list[Tag]) -> bool:
    if not activity.name:
        return False

    changed = False
    name = activity.name
    had_destructive_match = False

    for tag in tags:
        extraction_regex = tag.extraction_regex
        if not extraction_regex:
            continue

        try:
            match = re.search(extraction_regex, name)
        except re.error as e:
            logger.warning(
                f"Ignoring invalid extraction regex {extraction_regex!r} for tag {tag.tag!r}: {e}"
            )
            continue

        if match is None:
            continue

        if tag not in activity.tags:
            activity.tags.append(tag)
            changed = True

        if tag.extraction_destructive:
            start, end = match.span()
            name = f"{name[:start]} {name[end:]}"
            had_destructive_match = True

    if had_destructive_match:
        normalized_name = SPACE_PATTERN.sub(" ", name).strip()
        if normalized_name != activity.name:
            activity.name = normalized_name
            changed = True

    return changed


def get_tags_with_extraction_regex() -> list[Tag]:
    return DB.session.scalars(
        sqlalchemy.select(Tag)
        .where(
            Tag.extraction_regex.is_not(None),
            Tag.extraction_regex != "",
        )
        .order_by(Tag.id)
    ).all()


def apply_tag_extraction_from_database(activity: Activity) -> bool:
    return apply_tag_extraction(activity, get_tags_with_extraction_regex())
