import datetime
import json
import logging
import pathlib
import urllib.parse
import zoneinfo
from typing import Optional, TypedDict

import numpy as np
import pandas as pd
import sqlalchemy
import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .paths import (
    TIME_SERIES_DIR,
    activity_extracted_meta_dir,
    activity_extracted_time_series_dir,
)

logger = logging.getLogger(__name__)

# Squares from large to small, so that a lower zoom level with its larger tiles
# gets the visually larger emoji.
_TILE_EMOJI = ["🟨", "◼️", "◽", "▪️"]


DEFAULT_UNKNOWN_NAME = "Unknown"


def format_timedelta(v: datetime.timedelta):
    if pd.isna(v):
        return "—"
    else:
        seconds = v.total_seconds()
        h = int(seconds // 3600)
        m = int(seconds // 60 % 60)
        s = int(seconds // 1 % 60)
        return f"{h}:{m:02d}:{s:02d}"


class ActivityMeta(TypedDict):
    average_speed_elapsed_kmh: float
    average_speed_moving_kmh: float
    calories: float
    commute: bool
    copernicus_elevation_gain: float
    distance_km: float
    elapsed_time: datetime.timedelta
    elevation_gain: float
    end_latitude: float
    end_longitude: float
    equipment: str
    id: int
    kind: str
    moving_time: datetime.timedelta
    name: str
    path: str
    start_latitude: float
    start_longitude: float
    start: np.datetime64
    steps: int


class Base(DeclarativeBase):
    pass


DB = SQLAlchemy(model_class=Base)

activity_tag_association_table = Table(
    "activity_tag_association_table",
    Base.metadata,
    Column("left_id", ForeignKey("activities.id"), primary_key=True),
    Column("right_id", ForeignKey("tags.id"), primary_key=True),
)


class Activity(DB.Model):
    __tablename__ = "activities"

    # Housekeeping data:
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    time_series_uuid: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    # Where it comes from:
    path: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    upstream_id: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    source: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    # Metadata as found inside the activity file, before path extraction and user edits:
    name_from_file: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    kind_from_file: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    # Crop data:
    index_begin: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    index_end: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # Temporal data:
    start: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True)
    iana_timezone: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    elapsed_time: Mapped[datetime.timedelta | None] = mapped_column(
        sa.Interval, nullable=True
    )
    moving_time: Mapped[datetime.timedelta | None] = mapped_column(
        sa.Interval, nullable=True
    )

    # Geographic data:
    start_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_country: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    # Elevation data:
    elevation_gain: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_elevation: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_elevation: Mapped[float] = mapped_column(sa.Float, nullable=True)

    # Health data:
    calories: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    steps: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # Tile achievements:
    num_new_tiles_14: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    num_new_tiles_17: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # References to other tables:
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="equipment_id"), nullable=True
    )
    equipment: Mapped["Equipment"] = relationship(back_populates="activities")
    kind_id: Mapped[int] = mapped_column(
        ForeignKey("kinds.id", name="kind_id"), nullable=True
    )
    kind: Mapped["Kind"] = relationship(back_populates="activities")

    tags: Mapped[list["Tag"]] = relationship(
        secondary=activity_tag_association_table, back_populates="activities"
    )

    photos: Mapped[list["Photo"]] = relationship(  # noqa: F821
        back_populates="activity", cascade="all, delete-orphan"
    )

    segment_matches: Mapped[list["SegmentMatch"]] = relationship(  # noqa: F821
        back_populates="activity", cascade="all, delete-orphan"
    )

    segment_checks: Mapped[list["SegmentCheck"]] = relationship(  # noqa: F821
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.start} {self.name}"

    @property
    def average_speed_moving_kmh(self) -> float | None:
        if self.distance_km and self.moving_time:
            return self.distance_km / (self.moving_time.total_seconds() / 3_600)
        else:
            return None

    @property
    def average_speed_elapsed_kmh(self) -> float | None:
        if self.distance_km and self.elapsed_time:
            return self.distance_km / (self.elapsed_time.total_seconds() / 3_600)
        else:
            return None

    @property
    def time_series_path(self) -> pathlib.Path:
        return TIME_SERIES_DIR() / f"{self.time_series_uuid}.parquet"

    @property
    def raw_time_series(self) -> pd.DataFrame:
        try:
            time_series = pd.read_parquet(self.time_series_path)
            if "altitude" in time_series.columns:
                time_series.rename(columns={"altitude": "elevation"}, inplace=True)
            return time_series
        except OSError:
            logger.error(f"Error while reading {self.time_series_path}.")
            raise

    def replace_time_series(self, time_series: pd.DataFrame) -> None:
        time_series.to_parquet(self.time_series_path)

    @property
    def time_series(self) -> pd.DataFrame:
        if self.index_begin or self.index_end:
            return self.raw_time_series.iloc[
                self.index_begin or 0 : self.index_end or -1
            ]
        else:
            return self.raw_time_series

    @property
    def emoji_string(self) -> str:
        bits = []
        if self.kind:
            bits.append(f"{self.kind.name} with")
        if self.distance_km:
            bits.append(f"📏 {round(self.distance_km, 1)} km")
        if self.elapsed_time:
            bits.append(f"⏱️ {format_timedelta(self.elapsed_time)} h")
        if self.elevation_gain:
            bits.append(f"⛰️ {round(self.elevation_gain, 1)} m")
        if self.calories:
            bits.append(f"🍭 {self.calories} kcal")
        if self.steps:
            bits.append(f"👣 {self.steps}")
        counts = self.new_tile_counts
        ui_config = DB.session.get(UiConfig, 1)
        zoom_levels = sorted(ui_config.explorer_zoom_levels) if ui_config else []
        bits.extend(
            f"{_TILE_EMOJI[min(index, len(_TILE_EMOJI) - 1)]} {counts[zoom]}"
            for index, zoom in enumerate(zoom_levels)
            if counts.get(zoom)
        )
        return " ".join(bits)

    @property
    def new_tile_counts(self) -> dict[int, int]:
        """Number of tiles first visited by this activity, per zoom level."""
        return {
            row.zoom: row.count
            for row in DB.session.execute(
                sa.select(TileVisit.zoom, sa.func.count().label("count"))
                .where(TileVisit.first_activity_id == self.id)
                .group_by(TileVisit.zoom)
                .order_by(TileVisit.zoom)
            )
        }

    def delete_data(self) -> None:
        for path in [
            self.time_series_path,
            activity_extracted_meta_dir() / f"{self.upstream_id}.pickle",
            activity_extracted_time_series_dir() / f"{self.upstream_id}.pickle",
        ]:
            path.unlink(missing_ok=True)

    @property
    def start_local_tz(self) -> datetime.datetime | None:
        if self.start and self.iana_timezone:
            return self.start.replace(
                microsecond=0, tzinfo=zoneinfo.ZoneInfo("UTC")
            ).astimezone(zoneinfo.ZoneInfo(self.iana_timezone))
        else:
            return self.start

    @property
    def start_utc(self) -> datetime.datetime | None:
        if self.start:
            return self.start.replace(microsecond=0, tzinfo=zoneinfo.ZoneInfo("UTC"))
        else:
            return None


class DuplicateCandidate(DB.Model):
    """A pair of activities from different sources suspected to be the same ride.

    Detected when a newly imported activity's start time and distance/duration
    are close to an existing activity from a different source. Cleared once
    the user resolves it (merging one into the other) or it is auto-resolved.
    """

    __tablename__ = "duplicate_candidates"
    __table_args__ = (sa.UniqueConstraint("activity_a_id", "activity_b_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_a_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"), nullable=False
    )
    activity_b_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"), nullable=False
    )
    detected_at: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)

    activity_a: Mapped["Activity"] = relationship(foreign_keys=[activity_a_id])
    activity_b: Mapped["Activity"] = relationship(foreign_keys=[activity_b_id])


class Tag(DB.Model):
    __tablename__ = "tags"
    __table_args__ = (sa.UniqueConstraint("tag", name="tags_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String, unique=True)
    color: Mapped[str] = mapped_column(String, nullable=True)
    extraction_regex: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_destructive: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=True, default=False
    )

    activities: Mapped[list[Activity]] = relationship(
        secondary=activity_tag_association_table, back_populates="tags"
    )


def get_or_make_tag(tag: str) -> Tag:
    tags = DB.session.scalars(sqlalchemy.select(Tag).where(Tag.tag == tag)).all()
    if tags:
        assert len(tags) == 1, f"There must be only one tag with name '{tag}'."
        return tags[0]
    else:
        tag = Tag(tag=tag)
        DB.session.add(tag)
        return tag


def count_activities() -> int:
    return DB.session.scalars(
        sqlalchemy.select(sqlalchemy.func.count()).select_from(Activity)
    ).one()


def last_activity_date() -> datetime.datetime | None:
    result = DB.session.scalars(
        sqlalchemy.select(Activity).order_by(Activity.start)
    ).all()
    if result:
        return result[-1].start_local_tz
    else:
        return None


def get_activity_ids() -> list[int]:
    return DB.session.scalars(
        sqlalchemy.select(Activity.id).order_by(Activity.start, Activity.id)
    ).all()


def iter_activities(new_to_old: bool = True, drop_na: bool = False) -> list[Activity]:
    query = sqlalchemy.select(Activity)
    if drop_na:
        query = query.where(Activity.start.is_not(None))
    result = DB.session.scalars(query.order_by(Activity.start)).all()
    direction = -1 if new_to_old else 1
    return result[::direction]


def get_activity_by_id(id: int) -> Activity:
    activity = DB.session.scalar(
        sqlalchemy.select(Activity).where(Activity.id == int(id))
    )
    if activity is None:
        raise ValueError(f"Cannot find activity {id} in DB.session.")
    return activity


def get_time_series(id: int) -> pd.DataFrame:
    return get_activity_by_id(id).time_series


def query_activity_meta(clauses: list | None = None) -> pd.DataFrame:
    if clauses is None:
        clauses = []
    rows = DB.session.execute(
        sqlalchemy.select(
            Activity.id,
            Activity.name,
            Activity.path,
            Activity.distance_km,
            Activity.start,
            Activity.iana_timezone,
            Activity.elapsed_time,
            Activity.moving_time,
            Activity.start_latitude,
            Activity.start_longitude,
            Activity.end_latitude,
            Activity.end_longitude,
            Activity.elevation_gain,
            Activity.start_elevation,
            Activity.end_elevation,
            Activity.calories,
            Activity.steps,
            Activity.num_new_tiles_14,
            Activity.num_new_tiles_17,
            Equipment.name.label("equipment"),
            Kind.name.label("kind"),
        )
        .join(Activity.equipment)
        .join(Activity.kind)
        .where(*clauses)
        .order_by(Activity.start)
    ).all()
    df = pd.DataFrame(rows)

    if len(df):
        # If the search yields only activities without time information, the dtype isn't derived correctly.
        df["start"] = pd.to_datetime(df["start"])
        # start = df["start"].to_list()
        # random.shuffle(start)
        # df["start"] = pd.Series(start)
        df["elapsed_time"] = pd.to_timedelta(df["elapsed_time"])

        start_local = []
        for start, iana_timezone in zip(df["start"], df["iana_timezone"]):
            tz = "UTC" if pd.isna(iana_timezone) else iana_timezone
            if pd.isna(start):
                start_local.append(start)
            else:
                start_local.append(
                    start.tz_localize(zoneinfo.ZoneInfo("UTC"))
                    .tz_convert(zoneinfo.ZoneInfo(tz))
                    .tz_localize(None)
                )
        df["start_local"] = start_local

        # Work around bytes stored in DB.
        df["calories"] = [
            sum(a * 256**b for b, a in enumerate(c)) if isinstance(c, bytes) else c
            for c in df["calories"]
        ]

        for old, new in [
            ("elapsed_time", "average_speed_elapsed_kmh"),
            ("moving_time", "average_speed_moving_kmh"),
        ]:
            df[new] = pd.NA
            mask = df[old].dt.total_seconds() > 0
            df.loc[mask, new] = df.loc[mask, "distance_km"] / (
                df.loc[mask, old].dt.total_seconds() / 3_600
            )

        df["date"] = df["start_local"].dt.date
        df["year"] = df["start_local"].dt.year
        df["month"] = df["start_local"].dt.month
        df["day"] = df["start_local"].dt.day
        df["week"] = df["start_local"].dt.isocalendar().week
        df["day_of_week"] = df["start_local"].dt.day_of_week
        df["iso_year"] = df["start_local"].dt.isocalendar().year
        df["iso_day"] = df["start_local"].dt.isocalendar().day
        df["hours"] = df["elapsed_time"].dt.total_seconds() / 3_600
        df["hours_moving"] = df["moving_time"].dt.total_seconds() / 3_600
        df["iso_year_week"] = [
            f"{year:04d}-{week:02d}" for year, week in zip(df["iso_year"], df["week"])
        ]

        df.index = df["id"]

    return df


class Equipment(DB.Model):
    __tablename__ = "equipments"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)
    offset_km: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    picture_filename: Mapped[str | None] = mapped_column(String, nullable=True)

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )
    default_for_kinds: Mapped[list["Kind"]] = relationship(
        back_populates="default_equipment", cascade="all, delete-orphan"
    )
    maintenance_actions: Mapped[list["MaintenanceAction"]] = relationship(  # noqa: F821
        back_populates="equipment", cascade="all, delete-orphan"
    )
    recurring_tasks: Mapped[list["RecurringTask"]] = relationship(  # noqa: F821
        back_populates="equipment", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.offset_km} km)"

    @property
    def total_distance_km(self) -> float:
        tracked = DB.session.execute(
            sqlalchemy.select(sqlalchemy.func.sum(Activity.distance_km)).where(
                Activity.equipment_id == self.id
            )
        ).scalar()
        return (tracked or 0.0) + self.offset_km

    __table_args__ = (sa.UniqueConstraint("name", name="equipments_name"),)


def get_or_make_equipment(name: str) -> Equipment:
    equipments = DB.session.scalars(
        sqlalchemy.select(Equipment).where(Equipment.name == name)
    ).all()
    if equipments:
        assert len(equipments) == 1, (
            f"There must be only one equipment with name '{name}'."
        )
        return equipments[0]
    else:
        equipment = Equipment(name=name)
        return equipment


class Kind(DB.Model):
    __tablename__ = "kinds"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="kind", cascade="all, delete-orphan"
    )
    default_equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="default_equipment_id"), nullable=True
    )
    default_equipment: Mapped["Equipment"] = relationship(
        back_populates="default_for_kinds"
    )

    # Alternative name mapping: if this kind is an alias, replaced_by_id points to the canonical kind
    replaced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("kinds.id", name="kind_replaced_by_id"), nullable=True
    )
    replaced_by: Mapped[Optional["Kind"]] = relationship(
        "Kind", remote_side=[id], foreign_keys=[replaced_by_id]
    )

    __table_args__ = (sa.UniqueConstraint("name", name="kinds_name"),)


def get_or_make_kind(name: str) -> Kind:
    kinds = DB.session.scalars(sqlalchemy.select(Kind).where(Kind.name == name)).all()
    if kinds:
        assert len(kinds) == 1, f"There must be only one kind with name '{name}'."
        kind = kinds[0]
        return kind.replaced_by or kind
    else:
        kind = Kind(name=name)
        return kind


class TileVisit(DB.Model):
    """Records visit statistics for each explored tile.

    This table stores aggregate information about tile visits including
    first visit, last visit, and total visit count. It serves as the
    source of truth for tile exploration data.
    """

    __tablename__ = "tile_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # First visit info
    first_activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="tile_visit_first_activity_id"),
        nullable=False,
        index=True,
    )
    first_activity: Mapped["Activity"] = relationship(foreign_keys=[first_activity_id])
    first_time: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Last visit info
    last_activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="tile_visit_last_activity_id"),
        nullable=False,
        index=True,
    )
    last_activity: Mapped["Activity"] = relationship(foreign_keys=[last_activity_id])
    last_time: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Visit count
    visit_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)

    __table_args__ = (
        sa.Index("idx_tile_visits_zoom_tile", "zoom", "tile_x", "tile_y"),
        sa.UniqueConstraint(
            "zoom", "tile_x", "tile_y", name="unique_tile_visit_per_zoom"
        ),
    )

    def __repr__(self) -> str:
        return f"TileVisit(zoom={self.zoom}, x={self.tile_x}, y={self.tile_y}, visits={self.visit_count})"


class ActivityTile(DB.Model):
    """Which activities pass through which tile, per zoom level.

    This is the unfiltered record of every activity, which makes it the source
    the tile visit aggregate is derived from. Also queried by viewport/tile for
    the heatmap, the "activities through tile" view, and segment matching.
    """

    __tablename__ = "activity_tile"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="activity_tile_activity_id"),
        nullable=False,
        index=True,
    )
    time: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True)
    """When the activity entered this tile.

    ``None`` for rows written before this was recorded; the activity start time
    is used instead, which is coarser when two rides overlap in time.
    """

    __table_args__ = (
        sa.Index("idx_activity_tile_zoom_tile", "zoom", "tile_x", "tile_y"),
        sa.Index("idx_activity_tile_zoom_activity", "zoom", "activity_id"),
    )


class StoredSearchQuery(DB.Model):
    __tablename__ = "stored_search_queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_json: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    is_favorite: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    last_used: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)

    def __str__(self) -> str:
        data = json.loads(self.query_json)
        bits = []

        if data.get("name"):
            bits.append(f'name is "{data["name"]}"')

        if data.get("equipment"):
            equipment_names = [
                DB.session.get_one(Equipment, eid).name for eid in data["equipment"]
            ]
            bits.append(
                "equipment is " + (" or ".join(f'"{name}"' for name in equipment_names))
            )

        if data.get("kind"):
            kind_names = []
            for kid in data["kind"]:
                if kind := DB.session.get(Kind, kid):
                    kind_names.append(kind.name)
            bits.append("kind is " + (" or ".join(f'"{name}"' for name in kind_names)))

        if data.get("tag"):
            tag_names = [DB.session.get_one(Tag, tid).tag for tid in data["tag"]]
            bits.append("tag is " + (" or ".join(f'"{name}"' for name in tag_names)))

        if data.get("tag_exclude"):
            tag_names = [
                DB.session.get_one(Tag, tid).tag for tid in data["tag_exclude"]
            ]
            bits.append(
                "tag is not " + (" or ".join(f'"{name}"' for name in tag_names))
            )

        if data.get("start_begin"):
            bits.append(f"after {data['start_begin']}")

        if data.get("start_end"):
            bits.append(f"until {data['start_end']}")

        if data.get("distance_km_min"):
            bits.append(f"at least {data['distance_km_min']} km")

        if data.get("distance_km_max"):
            bits.append(f"at most {data['distance_km_max']} km")

        return " and ".join(bits)

    def to_url_str(self) -> str:
        """Convert the stored query to a URL query string."""
        data = json.loads(self.query_json)
        variables = []

        for equipment_id in data.get("equipment", []):
            variables.append(("equipment", equipment_id))
        for kind_id in data.get("kind", []):
            variables.append(("kind", kind_id))
        for tag_id in data.get("tag", []):
            variables.append(("tag", tag_id))
        for tag_id in data.get("tag_exclude", []):
            variables.append(("tag_exclude", tag_id))
        if data.get("name"):
            variables.append(("name", data["name"]))
        if data.get("name_case_sensitive"):
            variables.append(("name_case_sensitive", "true"))
        if data.get("start_begin"):
            variables.append(("start_begin", data["start_begin"]))
        if data.get("start_end"):
            variables.append(("start_end", data["start_end"]))
        if data.get("distance_km_min") is not None:
            variables.append(("distance_km_min", data["distance_km_min"]))
        if data.get("distance_km_max") is not None:
            variables.append(("distance_km_max", data["distance_km_max"]))

        return "&".join(
            f"{key}={urllib.parse.quote_plus(str(value))}" for key, value in variables
        )


class HeartRateConfig(DB.Model):
    """Single-row settings for heart-rate zone computation."""

    __tablename__ = "config_heart_rate"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    birth_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    heart_rate_resting: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0
    )
    heart_rate_maximum: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


class ActivityImportConfig(DB.Model):
    """Single-row settings governing how activities are imported and enriched."""

    __tablename__ = "config_activity_import"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    metadata_extraction_regexes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(sa.JSON), nullable=False, default=list
    )
    ignore_suffixes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(sa.JSON), nullable=False, default=list
    )
    time_diff_threshold_seconds: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True, default=30
    )
    reliable_elevation_measurements: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True
    )
    kind_renames: Mapped[dict[str, str]] = mapped_column(
        MutableDict.as_mutable(sa.JSON), nullable=False, default=dict
    )
    segment_max_distance: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=20
    )
    segment_split_distance: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=100
    )
    upload_password: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    duplicate_matching_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    duplicate_matching_auto_resolve: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    duplicate_time_tolerance_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=300, server_default="300"
    )
    duplicate_relative_tolerance: Mapped[float] = mapped_column(
        sa.Float, nullable=False, default=0.1, server_default="0.1"
    )
    duplicate_source_priorities: Mapped[dict[str, int]] = mapped_column(
        MutableDict.as_mutable(sa.JSON),
        nullable=False,
        default=lambda: {"directory": 10, "strava": 20, "hammerhead": 30},
        server_default='{"directory": 10, "strava": 20, "hammerhead": 30}',
    )
    """Lower number wins when a cross-source duplicate is auto-resolved.

    Sources missing from this mapping are treated as lowest priority, so an
    activity from a source added later never silently wins over one that is
    already ranked.
    """


class UiConfig(DB.Model):
    """Single-row settings for display, colors, and interface preferences."""

    __tablename__ = "config_ui"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    cluster_color_strategy: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="colorful_cluster"
    )
    color_scheme_for_counts: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="teals"
    )
    color_scheme_for_kind: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="category10"
    )
    color_scheme_for_heatmap: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="hot"
    )
    color_strategy_cmap_opacity: Mapped[float] = mapped_column(
        sa.Float, nullable=False, default=0.5
    )
    activity_line_color: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="#e41a1c", server_default="#e41a1c"
    )
    """Color of the solid activity track line, drawn both as a tile layer and
    as a GeoJSON overlay on the activity page."""
    eighth_marker_min_distance_km: Mapped[float] = mapped_column(
        sa.Float, nullable=False, default=30.0
    )
    eighth_marker_min_duration_hours: Mapped[float] = mapped_column(
        sa.Float, nullable=False, default=3.0
    )
    explorer_zoom_levels: Mapped[list[int]] = mapped_column(
        MutableList.as_mutable(sa.JSON), nullable=False, default=lambda: [14, 17]
    )
    count_inaccessible_in_cluster: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    explorer_filter_json: Mapped[str] = mapped_column(
        sa.Text, nullable=False, default="{}", server_default="{}"
    )
    """Search primitives deciding which activities count for explorer tiles.

    An empty object counts every activity. This replaces the former
    ``Kind.consider_for_achievements`` flag, which had to be applied while
    building the tile visits and could therefore not be varied afterwards.
    """
    show_progress_markers: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True
    )
    visible_table_columns: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(sa.JSON),
        nullable=False,
        default=lambda: ["distance", "duration", "direction", "equipment", "kind"],
    )
    search_map_tiles_per_page: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=50
    )
    heatmap_cache_min_activities: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=5
    )
    sharepic_suppressed_fields: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(sa.JSON), nullable=False, default=list
    )
    kinds_without_achievements: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(sa.JSON), nullable=False, default=list
    )
    preferred_language: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    currency: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="", server_default=""
    )
    apply_privacy_zones_to_tracks: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    apply_privacy_zones_to_heatmap: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    explorer_grid_line_color: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="#80808080", server_default="#80808080"
    )
    """Color of the lines between explorer tiles, as #RRGGBBAA."""
    explorer_grid_line_min_width_px: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=64, server_default="64"
    )
    """Minimum on-screen width of an explorer tile, in pixels, before its grid
    lines are drawn. Lower values show the grid at lower zoom levels."""


class MapConfig(DB.Model):
    """Single-row settings for the base map tiles."""

    __tablename__ = "config_map"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    map_tile_url: Mapped[str] = mapped_column(
        sa.String,
        nullable=False,
        default="https://tile.openstreetmap.org/{zoom}/{x}/{y}.png",
    )
    map_tile_attribution: Mapped[str] = mapped_column(
        sa.String,
        nullable=False,
        default=(
            '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            ' | <a href="https://www.openstreetmap.org/fixthemap">Correct Map</a>'
        ),
    )
    map_style_url: Mapped[str | None] = mapped_column(sa.String, nullable=True)


class PrivacyZone(DB.Model):
    """A named polygon whose interior is stripped from shared time series."""

    __tablename__ = "privacy_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False, unique=True)
    # Polygon ring as a list of ``[longitude, latitude]`` points.
    points: Mapped[list[list[float]]] = mapped_column(sa.JSON, nullable=False)

    def filter_time_series(self, time_series: pd.DataFrame) -> pd.DataFrame:
        import shapely

        polygon = shapely.Polygon(self.points)
        shapely.prepare(polygon)
        mask = [
            not shapely.contains_xy(polygon, longitude, latitude)
            for longitude, latitude in zip(
                time_series["longitude"], time_series["latitude"]
            )
        ]
        return time_series.loc[mask]


def apply_privacy_zones(time_series: pd.DataFrame) -> pd.DataFrame:
    for privacy_zone in DB.session.scalars(sqlalchemy.select(PrivacyZone)).all():
        time_series = privacy_zone.filter_time_series(time_series)
    return time_series


def apply_privacy_zones_to_tracks_if_enabled(
    time_series: pd.DataFrame, ui_config: UiConfig
) -> pd.DataFrame:
    if not ui_config.apply_privacy_zones_to_tracks:
        return time_series
    return apply_privacy_zones(time_series)


class DatabaseMaintenanceState(DB.Model):
    """Single row recording when the database was last vacuumed and analyzed."""

    __tablename__ = "database_maintenance_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_run: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
