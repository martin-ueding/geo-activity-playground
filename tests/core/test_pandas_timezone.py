import datetime
import tempfile
import zoneinfo

import altair as alt
import pandas as pd


def test_dataframe_timezone() -> None:
    df = pd.DataFrame(
        {
            "time": [
                datetime.datetime(
                    2025, 1, 1, 1, 1, 1, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
                )
            ]
        }
    )

    with tempfile.TemporaryFile() as f:
        df.to_parquet(f)


def test_altair_timezone() -> None:
    df = pd.DataFrame(
        {
            "time": [
                datetime.datetime(
                    2025, 1, 1, 1, 1, 1, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
                )
            ]
        }
    )

    chart = alt.Chart(df).mark_tick().encode(alt.X("time"))
    chart.to_json(format="vega")
