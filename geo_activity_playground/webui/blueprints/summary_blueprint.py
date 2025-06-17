import abc
import datetime
import uuid
from collections.abc import Callable
from collections.abc import Iterable

import altair as alt
import pandas as pd
import sqlalchemy
from flask import Blueprint
from flask import render_template
from flask import request

from ...core.activities import ActivityRepository
from ...core.config import Config
from ...core.datamodel import DB
from ...core.datamodel import PlotSpec
from ...core.meta_search import apply_search_query
from ...core.parametric_plot import make_parametric_plot
from ...core.visualizations import PLOTS
from ..columns import column_distance
from ..columns import column_elevation_gain
from ..columns import ColumnDescription
from ..plot_util import make_kind_scale
from ..search_util import search_query_from_form
from ..search_util import SearchQueryHistory


class DataFilter(abc.ABC):
    @abc.abstractmethod
    def filter(self, activities: pd.DataFrame) -> pd.DataFrame:
        pass


class DataGrouper(abc.ABC):
    @abc.abstractmethod
    def group(self, activities: pd.DataFrame) -> Iterable[tuple[str, pd.DataFrame]]:
        pass


class DataVisualizer(abc.ABC):
    @abc.abstractmethod
    def visualize(self, activities: pd.DataFrame) -> str:
        pass


class ModularPlot:
    def __init__(
        self,
        name: str,
        data_filter: DataFilter,
        data_grouper: DataGrouper,
        data_visualizer: DataVisualizer,
    ) -> None:
        self.name = name
        self.data_filter = data_filter
        self.data_grouper = data_grouper
        self.data_visualizer = data_visualizer

    def __str__(self) -> str:
        return self.name

    def render_html(self, activities: pd.DataFrame) -> str:
        filtered = self.data_filter.filter(activities)
        rendered_parts = {
            key: self.data_visualizer.visualize(group)
            for key, group in self.data_grouper.group(filtered)
        }
        if len(rendered_parts) > 1:
            return render_template(
                "summary/tabbed.html.j2", parts=sorted(rendered_parts.items())
            )
        else:
            return list(rendered_parts.values())[0]


def _render_plot_to_html(chart: alt.Chart) -> str:
    chart_json = chart.to_json(format="vega")
    return render_template(
        "summary/vega-chart.html.j2",
        chart_name=f"id-{uuid.uuid4()}",
        chart_json=chart_json,
    )


class WeeklyAmountVisualizer(DataVisualizer):
    def __init__(self, column: ColumnDescription) -> None:
        self.column = column

    def visualize(self, activities: pd.DataFrame) -> str:
        week_kind_total_distance = (
            activities[["iso_year", "week", "kind", self.column.name]]
            .groupby(["iso_year", "week", "kind"])
            .sum()
            .reset_index()
        )
        week_kind_total_distance["year_week"] = [
            f"{year}-{week:02d}"
            for year, week in zip(
                week_kind_total_distance["iso_year"], week_kind_total_distance["week"]
            )
        ]

        return _render_plot_to_html(
            alt.Chart(
                week_kind_total_distance,
                title=f"Weekly {self.column.display_name}",
            )
            .mark_bar()
            .encode(
                alt.X("year_week", title="Year and Week"),
                alt.Y(
                    self.column.name,
                    title=f"{self.column.display_name} / {self.column.unit}",
                ),
                alt.Color("kind", title="Kind"),
                [
                    alt.Tooltip("year_week", title="Year and Week"),
                    alt.Tooltip("kind", title="Kind"),
                    alt.Tooltip(
                        self.column.name,
                        title=f"{self.column.display_name} / {self.column.unit}",
                        format=self.column.format,
                    ),
                ],
            )
        )


def make_summary_blueprint(
    repository: ActivityRepository,
    config: Config,
    search_query_history: SearchQueryHistory,
) -> Blueprint:
    blueprint = Blueprint("summary", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = apply_search_query(repository.meta, query)

        kind_scale = make_kind_scale(repository.meta, config)
        df = activities

        plot_context = {}
        for name, plot_function in PLOTS.items():
            if isinstance(plot_function, dict):
                plot_context[name] = {
                    key: value(df) for key, value in plot_function.items()
                }
            else:
                plot_context[name] = plot_function(df)

        return render_template(
            "summary/index.html.j2",
            query=query.to_jinja(),
            custom_plots=[
                (spec, make_parametric_plot(repository.meta, spec))
                for spec in DB.session.scalars(sqlalchemy.select(PlotSpec)).all()
            ],
            **plot_context,
        )

    return blueprint
