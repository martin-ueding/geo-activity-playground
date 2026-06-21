import linecache
import os
import tracemalloc
from collections.abc import Callable

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue


def _proc_memory_mib() -> dict[str, float]:
    result = {}
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                key, _, value = line.partition(":")
                if key in ("VmRSS", "VmPeak", "VmSwap", "VmSize"):
                    kb = int(value.split()[0])
                    result[key] = round(kb / 1024, 1)
    except OSError:
        pass
    return result


def _tracemalloc_top(n: int = 20) -> list[dict]:
    if not tracemalloc.is_tracing():
        return []
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")
    rows = []
    for stat in stats[:n]:
        frame = stat.traceback[0]
        line = linecache.getline(frame.filename, frame.lineno).strip()
        rows.append(
            {
                "file": frame.filename,
                "lineno": frame.lineno,
                "line": line,
                "size_mib": round(stat.size / 1024 / 1024, 3),
                "count": stat.count,
            }
        )
    return rows


def _try_import(module: str, name: str) -> Callable | None:
    try:
        import importlib

        mod = importlib.import_module(module)
        return getattr(mod, name)
    except Exception:
        return None


def _cache_infos() -> list[dict]:
    candidates: list[tuple[str, str, str]] = [
        ("get_config", "geo_activity_playground.core.config", "get_config"),
        ("get_tile", "geo_activity_playground.core.raster_map", "get_tile"),
        (
            "_get_elevation_arrays",
            "geo_activity_playground.core.copernicus_dem",
            "_get_elevation_arrays",
        ),
        (
            "_get_interpolator",
            "geo_activity_playground.core.copernicus_dem",
            "_get_interpolator",
        ),
        (
            "hex_color_to_float",
            "geo_activity_playground.webui.blueprints.explorer_blueprint",
            "hex_color_to_float",
        ),
    ]
    rows = []
    for label, module, name in candidates:
        fn = _try_import(module, name)
        if fn is None or not hasattr(fn, "cache_info"):
            continue
        info = fn.cache_info()
        rows.append(
            {
                "name": label,
                "hits": info.hits,
                "misses": info.misses,
                "maxsize": info.maxsize,
                "currsize": info.currsize,
            }
        )
    return rows


def make_memory_blueprint() -> Blueprint:
    blueprint = Blueprint("memory", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        return render_template(
            "memory/index.html.j2",
            pid=os.getpid(),
            proc_memory=_proc_memory_mib(),
            tracemalloc_active=tracemalloc.is_tracing(),
            top_allocations=_tracemalloc_top(),
            cache_infos=_cache_infos(),
        )

    @blueprint.route("/start-tracemalloc", methods=["POST"])
    def start_tracemalloc() -> ResponseReturnValue:
        tracemalloc.start()
        return ("", 204)

    @blueprint.route("/stop-tracemalloc", methods=["POST"])
    def stop_tracemalloc() -> ResponseReturnValue:
        tracemalloc.stop()
        return ("", 204)

    return blueprint
