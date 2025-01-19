from typing import Optional

from werkzeug.datastructures import MultiDict

from geo_activity_playground.core.meta_search import _parse_date_or_none
from geo_activity_playground.core.meta_search import SearchQuery


def search_query_from_form(args: MultiDict) -> SearchQuery:
    query = SearchQuery(
        equipment=args.getlist("equipment"),
        kind=args.getlist("kind"),
        name=args.get("name", None),
        name_case_sensitive=_parse_bool(args.get("name_case_sensitive", "false")),
        start_begin=_parse_date_or_none(args.get("start_begin", None)),
        start_end=_parse_date_or_none(args.get("start_end", None)),
    )

    return query


def _parse_bool(s: str) -> bool:
    return s == "true"
