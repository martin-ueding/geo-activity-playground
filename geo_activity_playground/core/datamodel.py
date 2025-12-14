import datetime
import json
import logging
import os
import pathlib
import shutil
import urllib.parse
import uuid
import zoneinfo
from typing import Any
from typing import Optional
from typing import TypedDict

import numpy as np
import pandas as pd
import sqlalchemy
import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from .config import Config
from .paths import activity_extracted_meta_dir
from .paths import activity_extracted_time_series_dir
from .paths import TIME_SERIES_DIR


logger = logging.getLogger(__name__)


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
    consider_for_achievements: bool
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
    name: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    distance_km: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    time_series_uuid: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)

    # Where it comes from:
    path: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    upstream_id: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)

    # Crop data:
    index_begin: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    index_end: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # Temporal data:
    start: Mapped[Optional[datetime.datetime]] = mapped_column(
        sa.DateTime, nullable=True
    )
    iana_timezone: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    elapsed_time: Mapped[Optional[datetime.timedelta]] = mapped_column(
        sa.Interval, nullable=True
    )
    moving_time: Mapped[Optional[datetime.timedelta]] = mapped_column(
        sa.Interval, nullable=True
    )

    # Geographic data:
    start_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_country: Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)

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

    photos: Mapped[list["Photo"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    segment_matches: Mapped[list["SegmentMatch"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    segment_checks: Mapped[list["SegmentCheck"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.start} {self.name}"

    @property
    def average_speed_moving_kmh(self) -> Optional[float]:
        if self.distance_km and self.moving_time:
            return self.distance_km / (self.moving_time.total_seconds() / 3_600)
        else:
            return None

    @property
    def average_speed_elapsed_kmh(self) -> Optional[float]:
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
        except OSError as e:
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
        return " ".join(bits)

    def delete_data(self) -> None:
        for path in [
            TIME_SERIES_DIR() / f"{self.id}.parquet",
            activity_extracted_meta_dir() / f"{self.upstream_id}.pickle",
            activity_extracted_time_series_dir() / f"{self.upstream_id}.pickle",
        ]:
            path.unlink(missing_ok=True)

    @property
    def start_local_tz(self) -> Optional[datetime.datetime]:
        if self.start and self.iana_timezone:
            return self.start.replace(
                microsecond=0, tzinfo=zoneinfo.ZoneInfo("UTC")
            ).astimezone(zoneinfo.ZoneInfo(self.iana_timezone))
        else:
            return self.start

    @property
    def start_utc(self) -> Optional[datetime.datetime]:
        if self.start:
            return self.start.replace(microsecond=0, tzinfo=zoneinfo.ZoneInfo("UTC"))
        else:
            return None


class Tag(DB.Model):
    __tablename__ = "tags"
    __table_args__ = (sa.UniqueConstraint("tag", name="tags_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String, unique=True)
    color: Mapped[str] = mapped_column(String, nullable=True)

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


def query_activity_meta(clauses: list = []) -> pd.DataFrame:
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
            Kind.consider_for_achievements,
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
            if pd.isna(start) or iana_timezone is None:
                start_local.append(start)
            else:
                start_local.append(
                    start.tz_localize(zoneinfo.ZoneInfo("UTC"))
                    .tz_convert(iana_timezone)
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

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )
    default_for_kinds: Mapped[list["Kind"]] = relationship(
        back_populates="default_equipment", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.offset_km} km)"

    __table_args__ = (sa.UniqueConstraint("name", name="equipments_name"),)


def get_or_make_equipment(name: str, config: Config) -> Equipment:
    equipments = DB.session.scalars(
        sqlalchemy.select(Equipment).where(Equipment.name == name)
    ).all()
    if equipments:
        assert (
            len(equipments) == 1
        ), f"There must be only one equipment with name '{name}'."
        return equipments[0]
    else:
        equipment = Equipment(
            name=name, offset_km=config.equipment_offsets.get(name, 0)
        )
        return equipment


class Kind(DB.Model):
    __tablename__ = "kinds"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)
    consider_for_achievements: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, nullable=False
    )

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
    replaced_by_id: Mapped[Optional[int]] = mapped_column(
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
        kind = Kind(
            name=name,
            consider_for_achievements=True,
        )
        return kind


class SquarePlannerBookmark(DB.Model):
    __tablename__ = "square_planner_bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)

    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    __table_args__ = (sa.UniqueConstraint("zoom", "x", "y", "size", name="kinds_name"),)


class PlotSpec(DB.Model):
    __tablename__ = "plot_specs"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    mark: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    x: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    y: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    color: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    shape: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    size: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    row: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    opacity: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    column: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    facet: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    group_by: Mapped[str] = mapped_column(sa.String, nullable=True, default="")

    FIELDS = [
        "name",
        "mark",
        "x",
        "y",
        "color",
        "shape",
        "size",
        "row",
        "opacity",
        "column",
        "facet",
        "group_by",
    ]

    def __str__(self) -> str:
        return self.name

    def to_json(self) -> str:
        return json.dumps(
            {key: getattr(self, key) for key in self.FIELDS if getattr(self, key)}
        )


class Photo(DB.Model):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str] = mapped_column(sa.String, nullable=False)
    time: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    latitude: Mapped[float] = mapped_column(sa.Float, nullable=False)
    longitude: Mapped[float] = mapped_column(sa.Float, nullable=False)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="activity_id"), nullable=False
    )
    activity: Mapped["Activity"] = relationship(back_populates="photos")

    @property
    def path(self) -> pathlib.Path:
        return pathlib.Path(self.filename)


class ExplorerTileBookmark(DB.Model):
    __tablename__ = "explorer_tile_bookmarks"
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.tile_x}, {self.tile_y}) @ {self.zoom}"


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
    first_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Last visit info
    last_activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="tile_visit_last_activity_id"),
        nullable=False,
    )
    last_activity: Mapped["Activity"] = relationship(foreign_keys=[last_activity_id])
    last_time: Mapped[Optional[datetime.datetime]] = mapped_column(
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
            bits.append(f'name is "{data['name']}"')

        if data.get("equipment"):
            equipment_names = [
                DB.session.get_one(Equipment, eid).name for eid in data["equipment"]
            ]
            bits.append(
                "equipment is " + (" or ".join(f'"{name}"' for name in equipment_names))
            )

        if data.get("kind"):
            kind_names = [DB.session.get_one(Kind, kid).name for kid in data["kind"]]
            bits.append("kind is " + (" or ".join(f'"{name}"' for name in kind_names)))

        if data.get("tag"):
            tag_names = [DB.session.get_one(Tag, tid).tag for tid in data["tag"]]
            bits.append("tag is " + (" or ".join(f'"{name}"' for name in tag_names)))

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


class Segment(DB.Model):
    """A user-defined segment (polyline) for tracking repeated efforts."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    # Coordinates as a `list[tuple[float, float]]` with lat-lon order. That is opposite to GeoJSON.
    coordinates_json: Mapped[str] = mapped_column(sa.Text, nullable=False, default="[]")

    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    matches: Mapped[list["SegmentMatch"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )

    checks: Mapped[list["SegmentCheck"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )

    @property
    def coordinates(self) -> list[list[float]]:
        """Get coordinates as list of [lat, lon] pairs."""
        return json.loads(self.coordinates_json)

    @coordinates.setter
    def coordinates(self, value: list[list[float]]) -> None:
        """Set coordinates from list of [lat, lon] pairs."""
        self.coordinates_json = json.dumps(value)

    @property
    def length_km(self) -> float:
        """Calculate approximate length of segment in kilometers."""
        from .coordinates import get_distance

        coords = self.coordinates
        total = 0.0
        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i]
            lon2, lat2 = coords[i + 1]
            total += get_distance(lat1, lon1, lat2, lon2)
        return total / 1000  # Convert meters to km

    def __str__(self) -> str:
        return f"{self.name} ({self.length_km:.2f} km)"


class SegmentMatch(DB.Model):
    """Records when an activity passes through a segment.

    Stores the entry and exit points/times for computing segment duration
    and comparing efforts.
    """

    __tablename__ = "segment_matches"

    id: Mapped[int] = mapped_column(primary_key=True)

    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", name="segment_match_segment_id"),
        nullable=False,
        index=True,
    )
    segment: Mapped["Segment"] = relationship(back_populates="matches")

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="segment_match_activity_id"),
        nullable=False,
        index=True,
    )
    activity: Mapped["Activity"] = relationship(back_populates="segment_matches")

    # Entry point in the activity time series
    entry_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entry_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Exit point in the activity time series
    exit_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    exit_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Computed duration for easy querying/sorting
    duration: Mapped[Optional[datetime.timedelta]] = mapped_column(
        sa.Interval, nullable=True
    )

    # Distance covered in this segment effort (may differ slightly from segment length)
    distance_km: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)

    def __repr__(self) -> str:
        duration_str = str(self.duration).split(".")[0] if self.duration else "unknown"
        return f"SegmentMatch(segment={self.segment.name}, activity={self.activity_id}, duration={duration_str})"


class SegmentCheck(DB.Model):
    """Records when an activity passes through a segment.

    Stores the entry and exit points/times for computing segment duration
    and comparing efforts.
    """

    __tablename__ = "segment_checks"

    id: Mapped[int] = mapped_column(primary_key=True)

    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", name="segment_check_segment_id"),
        nullable=False,
        index=True,
    )
    segment: Mapped["Segment"] = relationship(back_populates="checks")

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="segment_check_activity_id"),
        nullable=False,
        index=True,
    )
    activity: Mapped["Activity"] = relationship(back_populates="segment_checks")

    __table_args__ = (
        sa.UniqueConstraint(
            "segment_id", "activity_id", name="unique_segment_activity_check"
        ),
    )
