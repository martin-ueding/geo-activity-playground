from types import SimpleNamespace

from geo_activity_playground.webui.blueprints.segments_blueprint import segment_df


def test_segment_df_handles_empty_matches() -> None:
    segment = SimpleNamespace(matches=[])

    df = segment_df(segment)

    assert df.empty
    assert list(df.columns) == [
        "distance_km",
        "duration_s",
        "duration",
        "direction",
        "entry_time",
        "exit_time",
        "activity_id",
        "activity_name",
        "equipment_name",
        "kind_name",
    ]
