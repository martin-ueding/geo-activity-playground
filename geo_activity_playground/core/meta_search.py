import dataclasses
import datetime
from typing import Optional

import numpy as np
import pandas as pd


@dataclasses.dataclass
class SearchQuery:
    equipment: list[str] = dataclasses.field(default_factory=list)
    kind: list[str] = dataclasses.field(default_factory=list)
    name: Optional[str] = None
    start_begin: Optional[datetime.datetime] = None
    start_end: Optional[datetime.datetime] = None


def apply_search_query(
    activity_meta: pd.DataFrame, search_query: SearchQuery
) -> pd.DataFrame:
    mask = _make_mask(len(activity_meta), True)
    mask &= _filter_column(activity_meta["equipment"], search_query.equipment)
    mask &= _filter_column(activity_meta["kind"], search_query.kind)

    return activity_meta.loc[mask]


def _make_mask(n: int, default: bool) -> pd.Series:
    if default:
        return pd.Series(np.ones((n,), dtype=np.bool))
    else:
        return pd.Series(np.zeros((n,), dtype=np.bool))


def _filter_column(column: pd.Series, values: list):
    if len(values) == 0:
        return _make_mask(len(column), True)
    else:
        sub_mask = _make_mask(len(column), False)
        for equipment in values:
            sub_mask |= column == equipment
        return sub_mask
