from typing import Optional

from werkzeug.datastructures import MultiDict

from ..core.config import ConfigAccessor
from ..core.meta_search import _parse_date_or_none
from ..core.meta_search import SearchQuery
from .authenticator import Authenticator


def search_query_from_form(args: MultiDict) -> SearchQuery:
    query = SearchQuery.from_primitives(
        {
            "equipment": map(int, args.getlist("equipment")),
            "kind": map(int, args.getlist("kind")),
            "tag": map(int, args.getlist("tag")),
            "name": args.get("name", None),
            "name_case_sensitive": _parse_bool(
                args.get("name_case_sensitive", "false")
            ),
            "start_begin": args.get("start_begin", None),
            "start_end": args.get("start_end", None),
            "distance_km_min": _optional_float(args.get("distance_km_min", None)),
            "distance_km_max": _optional_float(args.get("distance_km_max", None)),
        }
    )

    return query


def _parse_bool(s: str) -> bool:
    return s == "true"


def _optional_float(s: str) -> Optional[float]:
    if s:
        return float(s)
    else:
        return None


class SearchQueryHistory:
    def __init__(
        self, config_accessor: ConfigAccessor, authenticator: Authenticator
    ) -> None:
        self._config_accessor = config_accessor
        self._authenticator = authenticator

    def register_query(self, search_query: SearchQuery) -> None:
        if not self._authenticator.is_authenticated():
            return

        if not search_query.active:
            return

        primitives = search_query.to_primitives()
        while primitives in self._config_accessor().search_queries_last:
            self._config_accessor().search_queries_last.remove(primitives)
        self._config_accessor().search_queries_last.append(primitives)
        while (
            len(self._config_accessor().search_queries_last)
            > self._config_accessor().search_queries_num_keep
        ):
            self._config_accessor().search_queries_last.pop(0)
        self._config_accessor.save()

    def prepare_favorites(self) -> list[dict]:
        return self._prepare_list(self._config_accessor().search_queries_favorites)

    def prepare_last(self) -> list[dict]:
        return self._prepare_list(self._config_accessor().search_queries_last)

    def _prepare_list(self, l: list[dict]) -> list[tuple[str, dict]]:
        result = []
        for elem in l:
            search_query = SearchQuery.from_primitives(elem)
            result.append((str(search_query), search_query.to_url_str()))
        return result
