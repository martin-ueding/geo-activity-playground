import altair as alt
import pandas as pd

from ..core.datamodel import UiConfig


def make_kind_scale(meta: pd.DataFrame, config: UiConfig) -> alt.Scale:
    kinds = sorted(meta["kind"].unique())
    return alt.Scale(domain=kinds, scheme=config.color_scheme_for_kind)
