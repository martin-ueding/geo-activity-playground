import dataclasses
import datetime
import re
from typing import Optional

import numpy as np
import pandas as pd


@dataclasses.dataclass
class SearchQuery:
    equipment: list[str] = dataclasses.field(default_factory=list)
    kind: list[str] = dataclasses.field(default_factory=list)
    name: Optional[str] = None
    start_begin: Optional[datetime.date] = None
    start_end: Optional[datetime.date] = None


def apply_search_query(
    activity_meta: pd.DataFrame, search_query: SearchQuery
) -> pd.DataFrame:
    mask = _make_mask(len(activity_meta), True)

    if search_query.equipment:
        mask &= _filter_column(activity_meta["equipment"], search_query.equipment)
    if search_query.kind:
        mask &= _filter_column(activity_meta["kind"], search_query.kind)
    if search_query.name:
        mask &= pd.Series(
            [
                re.search(search_query.name, activity_name, re.IGNORECASE)
                for activity_name in activity_meta["name"].dt.date()
            ]
        )
    if search_query.start_begin is not None:
        mask &= search_query.start_begin <= activity_meta["start"]
    if search_query.start_end is not None:
        mask &= activity_meta["start"] <= search_query.start_end

    return activity_meta.loc[mask]


def _make_mask(n: int, default: bool) -> pd.Series:
    if default:
        return pd.Series(np.ones((n,), dtype=np.bool))
    else:
        return pd.Series(np.zeros((n,), dtype=np.bool))


def _filter_column(column: pd.Series, values: list):
    sub_mask = _make_mask(len(column), False)
    for equipment in values:
        sub_mask |= column == equipment
    return sub_mask
