import altair as alt
import pandas as pd

alt.data_transformers.enable("vegafusion")


def activity_track_plot(df: pd.DataFrame) -> str:
    chart = (
        alt.Chart(df)
        .mark_line()
        .encode(alt.Latitude("latitude"), alt.Longitude("longitude"))
    )
    return chart.to_json(format="vega")
