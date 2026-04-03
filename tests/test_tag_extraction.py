from geo_activity_playground.core.datamodel import Activity, Tag
from geo_activity_playground.core.tag_extraction import apply_tag_extraction


def test_apply_tag_extraction_adds_matching_tag():
    activity = Activity(name="Morning Ride", tags=[])
    tag = Tag(tag="commute", extraction_regex=r"\bRide\b", extraction_destructive=False)

    changed = apply_tag_extraction(activity, [tag])

    assert changed is True
    assert activity.tags == [tag]
    assert activity.name == "Morning Ride"


def test_apply_tag_extraction_destructive_name_cleanup():
    activity = Activity(name="Morning Ride - Thule trailer", tags=[])
    tag = Tag(
        tag="thule",
        extraction_regex=r"-\s*Thule\s*trailer",
        extraction_destructive=True,
    )

    changed = apply_tag_extraction(activity, [tag])

    assert changed is True
    assert activity.tags == [tag]
    assert activity.name == "Morning Ride"


def test_apply_tag_extraction_ignores_invalid_regex():
    activity = Activity(name="Evening Ride", tags=[])
    tag = Tag(tag="broken", extraction_regex=r"(", extraction_destructive=True)

    changed = apply_tag_extraction(activity, [tag])

    assert changed is False
    assert activity.tags == []
    assert activity.name == "Evening Ride"
