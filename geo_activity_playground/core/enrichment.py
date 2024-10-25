import datetime
import logging
import pickle
from typing import Any
from typing import Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.activities import make_activity_meta
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.paths import activity_enriched_meta_dir
from geo_activity_playground.core.paths import activity_enriched_time_series_dir
from geo_activity_playground.core.paths import activity_extracted_meta_dir
from geo_activity_playground.core.paths import activity_extracted_time_series_dir
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.time_conversion import convert_to_datetime_ns

logger = logging.getLogger(__name__)


def enrich_activities(config: Config) -> None:
    # Delete removed activities.
    for enriched_metadata_path in activity_enriched_meta_dir().glob("*.pickle"):
        if not (activity_extracted_meta_dir() / enriched_metadata_path.name).exists():
            logger.warning(f"Deleting {enriched_metadata_path}")
            enriched_metadata_path.unlink()
    for enriched_time_series_path in activity_enriched_time_series_dir().glob(
        "*.parquet"
    ):
        if not (
            activity_extracted_time_series_dir() / enriched_time_series_path.name
        ).exists():
            logger.warning(f"Deleting {enriched_time_series_path}")
            enriched_time_series_path.unlink()

    # Get new metadata paths.
    new_extracted_metadata_paths = []
    for extracted_metadata_path in activity_extracted_meta_dir().glob("*.pickle"):
        enriched_metadata_path = (
            activity_enriched_meta_dir() / extracted_metadata_path.name
        )
        if (
            not enriched_metadata_path.exists()
            or enriched_metadata_path.stat().st_mtime
            < extracted_metadata_path.stat().st_mtime
        ):
            extracted_time_series_path = (
                activity_extracted_time_series_dir()
                / f"{extracted_metadata_path.stem}.parquet"
            )
            if extracted_time_series_path.exists():
                new_extracted_metadata_paths.append(extracted_metadata_path)
            else:
                logger.error(
                    f"Extracted activity metadata {extracted_metadata_path} is lacking the corresponding time series path {extracted_time_series_path}. Likely that is an activity without location data. Deleting this."
                )
                extracted_metadata_path.unlink()

    for extracted_metadata_path in tqdm(
        new_extracted_metadata_paths, desc="Enrich new activity data"
    ):
        # Read extracted data.
        activity_id = extracted_metadata_path.stem
        extracted_time_series_path = (
            activity_extracted_time_series_dir() / f"{activity_id}.parquet"
        )
        time_series = pd.read_parquet(extracted_time_series_path)
        with open(extracted_metadata_path, "rb") as f:
            extracted_metadata = pickle.load(f)

        metadata = make_activity_meta()
        metadata.update(extracted_metadata)

        # Skip activities that don't have geo information attached to them. This shouldn't happen, though.
        if "latitude" not in time_series.columns:
            logger.warning(
                f"Activity {metadata} doesn't have latitude/longitude information. Ignoring this one."
            )
            continue

        # Rename kinds if needed.
        if metadata["kind"] in config.kind_renames:
            metadata["kind"] = config.kind_renames[metadata["kind"]]

        # Enrich time series.
        if metadata["kind"] in config.kinds_without_achievements:
            metadata["consider_for_achievements"] = False
        time_series = _embellish_single_time_series(
            time_series, metadata.get("start", None), config.time_diff_threshold_seconds
        )
        metadata.update(_get_metadata_from_timeseries(time_series))

        # Write enriched data.
        enriched_metadata_path = activity_enriched_meta_dir() / f"{activity_id}.pickle"
        enriched_time_series_path = (
            activity_enriched_time_series_dir() / f"{activity_id}.parquet"
        )
        with open(enriched_metadata_path, "wb") as f:
            pickle.dump(metadata, f)
        time_series.to_parquet(enriched_time_series_path)


def _get_metadata_from_timeseries(timeseries: pd.DataFrame) -> ActivityMeta:
    metadata = ActivityMeta()

    # Extract some meta data from the time series.
    metadata["start"] = timeseries["time"].iloc[0]
    metadata["elapsed_time"] = timeseries["time"].iloc[-1] - timeseries["time"].iloc[0]
    metadata["distance_km"] = timeseries["distance_km"].iloc[-1]
    if "calories" in timeseries.columns:
        metadata["calories"] = timeseries["calories"].iloc[-1]
    metadata["moving_time"] = _compute_moving_time(timeseries)

    metadata["start_latitude"] = timeseries["latitude"].iloc[0]
    metadata["end_latitude"] = timeseries["latitude"].iloc[-1]
    metadata["start_longitude"] = timeseries["longitude"].iloc[0]
    metadata["end_longitude"] = timeseries["longitude"].iloc[-1]

    return metadata


def _compute_moving_time(time_series: pd.DataFrame) -> datetime.timedelta:
    def moving_time(group) -> datetime.timedelta:
        selection = group["speed"] > 1.0
        time_diff = group["time"].diff().loc[selection]
        return time_diff.sum()

    return (
        time_series.groupby("segment_id").apply(moving_time, include_groups=False).sum()
    )


def _embellish_single_time_series(
    timeseries: pd.DataFrame,
    start: Optional[datetime.datetime],
    time_diff_threshold_seconds: int,
) -> pd.DataFrame:
    if start is not None and pd.api.types.is_dtype_equal(
        timeseries["time"].dtype, "int64"
    ):
        time = timeseries["time"]
        del timeseries["time"]
        timeseries["time"] = [
            convert_to_datetime_ns(start + datetime.timedelta(seconds=t)) for t in time
        ]
    timeseries["time"] = convert_to_datetime_ns(timeseries["time"])
    assert pd.api.types.is_dtype_equal(timeseries["time"].dtype, "datetime64[ns]"), (
        timeseries["time"].dtype,
        timeseries["time"].iloc[0],
    )

    distances = get_distance(
        timeseries["latitude"].shift(1),
        timeseries["longitude"].shift(1),
        timeseries["latitude"],
        timeseries["longitude"],
    ).fillna(0.0)
    if time_diff_threshold_seconds:
        time_diff = (
            timeseries["time"] - timeseries["time"].shift(1)
        ).dt.total_seconds()
        jump_indices = time_diff >= time_diff_threshold_seconds
        distances.loc[jump_indices] = 0.0

    if "distance_km" not in timeseries.columns:
        timeseries["distance_km"] = pd.Series(np.cumsum(distances)) / 1000

    if "speed" not in timeseries.columns:
        timeseries["speed"] = (
            timeseries["distance_km"].diff()
            / (timeseries["time"].diff().dt.total_seconds() + 1e-3)
            * 3600
        )

    potential_jumps = (timeseries["speed"] > 40) & (timeseries["speed"].diff() > 10)
    if np.any(potential_jumps):
        timeseries = timeseries.loc[~potential_jumps].copy()

    if "segment_id" not in timeseries.columns:
        if time_diff_threshold_seconds:
            timeseries["segment_id"] = np.cumsum(jump_indices)
        else:
            timeseries["segment_id"] = 0

    if "x" not in timeseries.columns:
        x, y = compute_tile_float(timeseries["latitude"], timeseries["longitude"], 0)
        timeseries["x"] = x
        timeseries["y"] = y

    return timeseries
