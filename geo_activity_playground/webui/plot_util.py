import altair as alt
import pandas as pd

from ..core.config import Config


def make_kind_scale(meta: pd.DataFrame, config: Config) -> alt.Scale:
    kinds = sorted(meta["kind"].unique())
    return alt.Scale(domain=kinds, scheme=config.color_scheme_for_kind)
