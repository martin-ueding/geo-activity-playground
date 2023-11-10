import altair as alt
import pandas as pd

alt.data_transformers.enable("vegafusion")


def activity_track_plot(time_series: pd.DataFrame) -> str:
    chart = (
        alt.Chart(time_series)
        .mark_line()
        .encode(alt.Latitude("latitude"), alt.Longitude("longitude"))
    )
    return chart.to_json(format="vega")
