import json
import logging

import altair as alt
import geojson
import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.kalman_filter import kalman_filter_track, speed_from_positions
from ..authenticator import Authenticator, needs_authentication

logger = logging.getLogger(__name__)

DEFAULTS = {
    "sigma_gps": 15.0,
    "sigma_process": 2.0,
    "gate_chi2": 9.21,
}


def make_filter_playground_blueprint(
    repository: ActivityRepository,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("filter_playground", __name__)

    @blueprint.route("/<int:id>")
    @needs_authentication(authenticator)
    def show(id: int) -> ResponseReturnValue:
        activity = repository.get_activity_by_id(id)
        time_series = repository.get_time_series(id)

        if "latitude" not in time_series.columns:
            return render_template(
                "filter_playground/index.html.j2",
                activity=activity,
                original_geojson="{}",
                defaults=DEFAULTS,
                initial_data=None,
            )

        original_geojson_str = _make_track_geojson(
            time_series["latitude"].values,
            time_series["longitude"].values,
            time_series,
        )
        initial_data = _run_filter(time_series, **DEFAULTS)

        return render_template(
            "filter_playground/index.html.j2",
            activity=activity,
            original_geojson=original_geojson_str,
            defaults=DEFAULTS,
            initial_data=initial_data,
        )

    @blueprint.route("/<int:id>/compute")
    @needs_authentication(authenticator)
    def compute(id: int) -> ResponseReturnValue:
        time_series = repository.get_time_series(id)

        if "latitude" not in time_series.columns:
            return jsonify({"error": "No GPS data"}), 400

        sigma_gps = float(request.args.get("sigma_gps", DEFAULTS["sigma_gps"]))
        sigma_process = float(
            request.args.get("sigma_process", DEFAULTS["sigma_process"])
        )
        gate_chi2 = float(request.args.get("gate_chi2", DEFAULTS["gate_chi2"]))

        return jsonify(_run_filter(time_series, sigma_gps, sigma_process, gate_chi2))

    return blueprint


def _run_filter(
    time_series: pd.DataFrame,
    sigma_gps: float,
    sigma_process: float,
    gate_chi2: float,
) -> dict:
    filtered_lat, filtered_lon, excluded = kalman_filter_track(
        time_series, sigma_gps, sigma_process, gate_chi2
    )
    filtered_geojson_str = _make_track_geojson(filtered_lat, filtered_lon, time_series)

    raw_lat = time_series["latitude"].values
    raw_lon = time_series["longitude"].values
    excluded_features = [
        geojson.Feature(geometry=geojson.Point((float(raw_lon[i]), float(raw_lat[i]))))
        for i in np.where(excluded)[0]
    ]
    excluded_geojson_str = geojson.dumps(geojson.FeatureCollection(excluded_features))

    speed_plot_json = _speed_comparison_plot(time_series, filtered_lat, filtered_lon)

    return {
        "filtered_geojson": filtered_geojson_str,
        "excluded_geojson": excluded_geojson_str,
        "speed_plot": json.loads(speed_plot_json),
        "excluded_count": int(excluded.sum()),
        "total_count": len(excluded),
    }


def _make_track_geojson(
    lat: np.ndarray, lon: np.ndarray, time_series: pd.DataFrame
) -> str:
    if "segment_id" in time_series.columns:
        seg_ids = time_series["segment_id"].values
        features = []
        for seg in np.unique(seg_ids):
            mask = seg_ids == seg
            coords = [(float(lon[i]), float(lat[i])) for i in np.where(mask)[0]]
            if len(coords) >= 2:
                features.append(geojson.LineString(coords))
        return geojson.dumps(geojson.FeatureCollection(features))

    coords = [(float(lo), float(la)) for la, lo in zip(lat, lon)]
    return geojson.dumps(geojson.FeatureCollection([geojson.LineString(coords)]))


def _speed_comparison_plot(
    time_series: pd.DataFrame,
    filtered_lat: np.ndarray,
    filtered_lon: np.ndarray,
) -> str:
    times = time_series["time"].values
    raw_speed = (
        time_series["speed"].values
        if "speed" in time_series.columns
        else speed_from_positions(
            time_series["latitude"].values, time_series["longitude"].values, times
        )
    )
    filtered_speed = speed_from_positions(filtered_lat, filtered_lon, times)

    df = pd.concat(
        [
            pd.DataFrame({"time": times, "speed": raw_speed, "series": _("Raw")}),
            pd.DataFrame(
                {"time": times, "speed": filtered_speed, "series": _("Filtered")}
            ),
        ]
    ).dropna(subset=["speed"])

    return (
        alt.Chart(df, title=_("Speed comparison"))
        .mark_line()
        .encode(
            alt.X("time:T", title=_("Time")),
            alt.Y("speed:Q", title=_("Speed / km/h")),
            alt.Color("series:N", title=_("Series")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )
