import functools

import altair as alt
import numpy as np
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.coordinates import Bounds
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.explorer.clusters import bounding_box_for_biggest_cluster
from geo_activity_playground.explorer.clusters import get_explorer_cluster_evolution
from geo_activity_playground.explorer.clusters import get_square_history
from geo_activity_playground.explorer.converters import get_tile_history
from geo_activity_playground.explorer.grid_file import get_border_tiles
from geo_activity_playground.explorer.grid_file import get_explored_geojson
from geo_activity_playground.explorer.grid_file import get_explored_tiles
from geo_activity_playground.explorer.grid_file import get_three_color_tiles
from geo_activity_playground.explorer.grid_file import make_grid_file_geojson
from geo_activity_playground.explorer.grid_file import make_grid_file_gpx


alt.data_transformers.enable("vegafusion")


class ExplorerController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self, zoom: int) -> dict:
        tiles = get_tile_history(self._repository, zoom)
        medians = tiles.median()
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )

        cluster_state = get_explorer_cluster_evolution(zoom)
        explored = get_three_color_tiles(tiles, self._repository, cluster_state, zoom)

        square_history = get_square_history(zoom)

        return {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": bounding_box_for_biggest_cluster(
                    cluster_state.clusters.values(), zoom
                )
                if len(cluster_state.memberships) > 0
                else {},
            },
            "explored": explored,
            "plot_tile_evolution": plot_tile_evolution(tiles),
            "plot_cluster_evolution": plot_cluster_evolution(
                cluster_state.cluster_evolution
            ),
            "plot_square_evolution": plot_square_evolution(
                square_history.square_history
            ),
            "zoom": zoom,
        }

    def export_missing_tiles(self, zoom, north, east, south, west, suffix: str) -> str:
        x1, y1 = compute_tile_float(north, west, zoom)
        x2, y2 = compute_tile_float(south, east, zoom)
        tile_bounds = Bounds(x1, y1, x2 + 2, y2 + 2)

        tiles = get_tile_history(self._repository, zoom)
        points = get_border_tiles(tiles, zoom, tile_bounds)
        if suffix == "geojson":
            return make_grid_file_geojson(points)
        elif suffix == "gpx":
            return make_grid_file_gpx(points)
        ...


def plot_tile_evolution(tiles: pd.DataFrame) -> str:
    if len(tiles) == 0:
        return ""
    tiles.sort_values("first_time", inplace=True)
    tiles["count"] = np.arange(1, len(tiles) + 1)
    return (
        alt.Chart(tiles, title="Tiles")
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("first_time", title="Time"), alt.Y("count", title="Number of tiles")
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def plot_cluster_evolution(cluster_evolution: pd.DataFrame) -> str:
    if len(cluster_evolution) == 0:
        return ""
    return (
        alt.Chart(cluster_evolution, title="Cluster")
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title="Time"),
            alt.Y("max_cluster_size", title="Maximum cluster size"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def plot_square_evolution(square_evolution: pd.DataFrame) -> str:
    if len(square_evolution) == 0:
        return ""
    return (
        alt.Chart(square_evolution, title="Square")
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title="Time"),
            alt.Y("max_square_size", title="Maximum square size"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )
