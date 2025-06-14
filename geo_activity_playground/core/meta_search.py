import dataclasses
import datetime
import re
import urllib.parse
from collections.abc import Sequence
from typing import Optional

import dateutil.parser
import numpy as np
import pandas as pd
import sqlalchemy

from .datamodel import Activity
from .datamodel import DB
from .datamodel import Equipment
from .datamodel import Kind
from .datamodel import query_activity_meta
from .datamodel import Tag


@dataclasses.dataclass
class SearchQuery:
    equipment: list[Equipment] = dataclasses.field(default_factory=list)
    kind: list[Kind] = dataclasses.field(default_factory=list)
    tag: list[Tag] = dataclasses.field(default_factory=list)
    name: Optional[str] = None
    name_case_sensitive: bool = False
    start_begin: Optional[datetime.date] = None
    start_end: Optional[datetime.date] = None
    distance_km_min: Optional[float] = None
    distance_km_max: Optional[float] = None

    def __str__(self) -> str:
        bits = []
        if self.name:
            bits.append(f"name is “{self.name}”")
        if self.equipment:
            bits.append(
                "equipment is "
                + (" or ".join(f"“{equipment.name}”" for equipment in self.equipment))
            )
        if self.kind:
            bits.append(
                "kind is " + (" or ".join(f"“{kind.name}”" for kind in self.kind))
            )
        if self.tag:
            bits.append("tag is " + (" or ".join(f"“{tag.tag}”" for tag in self.tag)))
        if self.start_begin:
            bits.append(f"after “{self.start_begin.isoformat()}”")
        if self.start_end:
            bits.append(f"until “{self.start_end.isoformat()}”")
        return " and ".join(bits)

    @property
    def active(self) -> bool:
        return (
            self.equipment
            or self.kind
            or self.name
            or self.start_begin
            or self.start_end
            or self.tag
            or self.distance_km_min
            or self.distance_km_max
        )

    def to_primitives(self) -> dict:
        return {
            "equipment": [equipment.id for equipment in self.equipment],
            "kind": [kind.id for kind in self.kind],
            "tag": [tag.id for tag in self.tag],
            "name": self.name or "",
            "name_case_sensitive": self.name_case_sensitive,
            "start_begin": _format_optional_date(self.start_begin),
            "start_end": _format_optional_date(self.start_end),
            "distance_km_min": self.distance_km_min,
            "distance_km_max": self.distance_km_max,
        }

    @classmethod
    def from_primitives(cls, d: dict) -> "SearchQuery":
        return cls(
            equipment=[
                DB.session.get_one(Equipment, id) for id in d.get("equipment", [])
            ],
            kind=[DB.session.get_one(Kind, id) for id in d.get("kind", [])],
            tag=[DB.session.get_one(Tag, id) for id in d.get("tag", [])],
            name=d.get("name", None),
            name_case_sensitive=d.get("name_case_sensitive", False),
            start_begin=_parse_date_or_none(d.get("start_begin", None)),
            start_end=_parse_date_or_none(d.get("start_end", None)),
            distance_km_min=d.get("distance_km_min", None),
            distance_km_max=d.get("distance_km_max", None),
        )

    def to_jinja(self) -> dict:
        result = self.to_primitives()
        result["active"] = self.active
        return result

    def to_url_str(self) -> str:
        variables = []
        for equipment in self.equipment:
            variables.append(("equipment", equipment.id))
        for kind in self.kind:
            variables.append(("kind", kind.id))
        for tag in self.tag:
            variables.append(("tag", tag.id))
        if self.name:
            variables.append(("name", self.name))
        if self.name_case_sensitive:
            variables.append(("name_case_sensitive", "true"))
        if self.start_begin:
            variables.append(("start_begin", self.start_begin.isoformat()))
        if self.start_end:
            variables.append(("start_end", self.start_end.isoformat()))
        if self.distance_km_min:
            variables.append(("distance_km_min", self.distance_km_min))
        if self.distance_km_max:
            variables.append(("distance_km_max", self.distance_km_max))

        return "&".join(
            f"{key}={urllib.parse.quote_plus(str(value))}" for key, value in variables
        )


def apply_search_query(
    activity_meta: pd.DataFrame, search_query: SearchQuery
) -> pd.DataFrame:

    filter_clauses = []

    if search_query.equipment:
        filter_clauses.append(
            sqlalchemy.or_(
                *[
                    Activity.equipment == equipment
                    for equipment in search_query.equipment
                ]
            )
        )

    if search_query.kind:
        filter_clauses.append(
            sqlalchemy.or_(*[Activity.kind == kind for kind in search_query.kind])
        )

    if search_query.tag:
        filter_clauses.append(
            sqlalchemy.or_(*[Activity.tags.contains(tag) for tag in search_query.tag])
        )

    if search_query.name:
        filter_clauses.append(
            Activity.name.contains(search_query.name)
            if search_query.name_case_sensitive
            else Activity.name.icontains(search_query.name)
        )

    if search_query.start_begin:
        filter_clauses.append(Activity.start >= search_query.start_begin)
    if search_query.start_end:
        filter_clauses.append(Activity.start < search_query.start_end)

    if search_query.distance_km_min:
        filter_clauses.append(Activity.distance_km >= search_query.distance_km_min)
    if search_query.distance_km_max:
        filter_clauses.append(Activity.distance_km <= search_query.distance_km_max)

    return query_activity_meta(filter_clauses)


def _format_optional_date(date: Optional[datetime.date]) -> str:
    if date is None:
        return ""
    else:
        return date.isoformat()


def _make_mask(
    index: pd.Index,
    default: bool,
) -> pd.Series:
    if default:
        return pd.Series(np.ones((len(index),), dtype=np.bool), index=index)
    else:
        return pd.Series(np.zeros((len(index),), dtype=np.bool), index=index)


def _filter_column(column: pd.Series, values: list):
    sub_mask = _make_mask(column.index, False)
    for equipment in values:
        sub_mask |= column == equipment
    return sub_mask


def _parse_date_or_none(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    else:
        return dateutil.parser.parse(s).date()
