import altair as alt
import pandas as pd


def make_kind_scale(meta: pd.DataFrame) -> alt.Scale:
    kinds = sorted(meta["kind"].unique())
    return alt.Scale(domain=kinds, scheme="category10")
