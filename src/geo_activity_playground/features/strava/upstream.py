from ...core.import_exclusion import is_excluded

API_SOURCE = "strava"
EXPORT_SOURCE = "strava_export"
STRAVA_SOURCES = (API_SOURCE, EXPORT_SOURCE)


def is_strava_activity_excluded(strava_id: int | str) -> bool:
    """Both Strava sources share the activity IDs, so an exclusion via one holds for the other."""
    return any(is_excluded(source, str(strava_id)) for source in STRAVA_SOURCES)
