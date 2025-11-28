import datetime
import json
import urllib.parse
from typing import Optional

import dateutil.parser
import pandas as pd
import sqlalchemy
from werkzeug.datastructures import MultiDict

from .datamodel import Activity
from .datamodel import DB
from .datamodel import query_activity_meta
from .datamodel import StoredSearchQuery
from .datamodel import Tag


def parse_search_params(args: MultiDict) -> dict:
    """Parse URL/form parameters into a primitives dict. Only includes non-empty values."""
    result = {}

    equipment = list(map(int, args.getlist("equipment")))
    if equipment:
        result["equipment"] = equipment

    kind = list(map(int, args.getlist("kind")))
    if kind:
        result["kind"] = kind

    tag = list(map(int, args.getlist("tag")))
    if tag:
        result["tag"] = tag

    name = args.get("name", None)
    if name:
        result["name"] = name

    if args.get("name_case_sensitive", "false") == "true":
        result["name_case_sensitive"] = True

    start_begin = args.get("start_begin", None)
    if start_begin:
        result["start_begin"] = start_begin

    start_end = args.get("start_end", None)
    if start_end:
        result["start_end"] = start_end

    distance_km_min = _optional_float(args.get("distance_km_min", None))
    if distance_km_min is not None:
        result["distance_km_min"] = distance_km_min

    distance_km_max = _optional_float(args.get("distance_km_max", None))
    if distance_km_max is not None:
        result["distance_km_max"] = distance_km_max

    return result


def is_search_active(primitives: dict) -> bool:
    """Check if the search has any active filters."""
    return bool(primitives)


def primitives_to_json(primitives: dict) -> str:
    """Convert primitives to JSON string for storage. Keys are sorted for consistent comparison."""
    return json.dumps(primitives, sort_keys=True)


def primitives_to_url_str(primitives: dict) -> str:
    """Convert a primitives dict to URL query string."""
    variables = []
    for equipment_id in primitives.get("equipment", []):
        variables.append(("equipment", equipment_id))
    for kind_id in primitives.get("kind", []):
        variables.append(("kind", kind_id))
    for tag_id in primitives.get("tag", []):
        variables.append(("tag", tag_id))
    if primitives.get("name"):
        variables.append(("name", primitives["name"]))
    if primitives.get("name_case_sensitive"):
        variables.append(("name_case_sensitive", "true"))
    if primitives.get("start_begin"):
        variables.append(("start_begin", primitives["start_begin"]))
    if primitives.get("start_end"):
        variables.append(("start_end", primitives["start_end"]))
    if primitives.get("distance_km_min") is not None:
        variables.append(("distance_km_min", primitives["distance_km_min"]))
    if primitives.get("distance_km_max") is not None:
        variables.append(("distance_km_max", primitives["distance_km_max"]))

    return "&".join(
        f"{key}={urllib.parse.quote_plus(str(value))}" for key, value in variables
    )


def primitives_to_jinja(primitives: dict) -> dict:
    """Convert primitives to Jinja template format with defaults for form fields."""
    return {
        "equipment": primitives.get("equipment", []),
        "kind": primitives.get("kind", []),
        "tag": primitives.get("tag", []),
        "name": primitives.get("name", ""),
        "name_case_sensitive": primitives.get("name_case_sensitive", False),
        "start_begin": primitives.get("start_begin", ""),
        "start_end": primitives.get("start_end", ""),
        "distance_km_min": primitives.get("distance_km_min"),
        "distance_km_max": primitives.get("distance_km_max"),
        "active": bool(primitives),
    }


def register_search_query(primitives: dict) -> Optional[StoredSearchQuery]:
    """Store or update a search query in the database. Returns the stored query or None if inactive."""
    if not primitives:
        return None

    query_json = primitives_to_json(primitives)

    # Check if this query already exists
    existing = DB.session.scalars(
        sqlalchemy.select(StoredSearchQuery).where(
            StoredSearchQuery.query_json == query_json
        )
    ).first()

    if existing:
        existing.last_used = datetime.datetime.now()
        DB.session.commit()
        return existing
    else:
        stored = StoredSearchQuery(
            query_json=query_json,
            is_favorite=False,
            last_used=datetime.datetime.now(),
        )
        DB.session.add(stored)
        DB.session.commit()
        return stored


def get_stored_queries(limit_recent: int = 10) -> list[StoredSearchQuery]:
    """Get stored queries: all favorites, then up to limit_recent non-favorites."""
    favorites = list(
        DB.session.scalars(
            sqlalchemy.select(StoredSearchQuery)
            .where(StoredSearchQuery.is_favorite == True)
            .order_by(StoredSearchQuery.last_used.desc())
        ).all()
    )

    recent = list(
        DB.session.scalars(
            sqlalchemy.select(StoredSearchQuery)
            .where(StoredSearchQuery.is_favorite == False)
            .order_by(StoredSearchQuery.last_used.desc())
            .limit(limit_recent)
        ).all()
    )

    return favorites + recent


def apply_search_filter(primitives: dict) -> pd.DataFrame:
    """Apply filter from primitives dict and return matching activities."""
    filter_clauses = []

    if primitives.get("equipment"):
        filter_clauses.append(Activity.equipment_id.in_(primitives["equipment"]))

    if primitives.get("kind"):
        filter_clauses.append(Activity.kind_id.in_(primitives["kind"]))

    if primitives.get("tag"):
        filter_clauses.append(
            sqlalchemy.or_(
                *[Activity.tags.any(Tag.id == tid) for tid in primitives["tag"]]
            )
        )

    if primitives.get("name"):
        if primitives.get("name_case_sensitive"):
            filter_clauses.append(Activity.name.contains(primitives["name"]))
        else:
            filter_clauses.append(Activity.name.icontains(primitives["name"]))

    if primitives.get("start_begin"):
        start_begin = _parse_date_or_none(primitives["start_begin"])
        if start_begin:
            filter_clauses.append(Activity.start >= start_begin)

    if primitives.get("start_end"):
        start_end = _parse_date_or_none(primitives["start_end"])
        if start_end:
            filter_clauses.append(Activity.start < start_end)

    if primitives.get("distance_km_min") is not None:
        filter_clauses.append(Activity.distance_km >= primitives["distance_km_min"])

    if primitives.get("distance_km_max") is not None:
        filter_clauses.append(Activity.distance_km <= primitives["distance_km_max"])

    return query_activity_meta(filter_clauses)


def _optional_float(s: Optional[str]) -> Optional[float]:
    if s:
        return float(s)
    else:
        return None


def _parse_date_or_none(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    else:
        return dateutil.parser.parse(s).date()
