import datetime

from werkzeug.datastructures import MultiDict

from .meta_search import is_search_active
from .meta_search import parse_search_params
from .meta_search import primitives_to_jinja
from .meta_search import primitives_to_json
from .meta_search import primitives_to_url_str


def test_empty_query() -> None:
    primitives = parse_search_params(MultiDict())
    assert primitives == {}
    assert not is_search_active(primitives)


def test_parse_equipment() -> None:
    args = MultiDict([("equipment", "1"), ("equipment", "2")])
    primitives = parse_search_params(args)
    assert primitives == {"equipment": [1, 2]}
    assert is_search_active(primitives)


def test_parse_dates() -> None:
    args = MultiDict([("start_begin", "2025-01-01"), ("start_end", "2025-01-04")])
    primitives = parse_search_params(args)
    assert primitives == {"start_begin": "2025-01-01", "start_end": "2025-01-04"}


def test_parse_name() -> None:
    args = MultiDict([("name", "Test")])
    primitives = parse_search_params(args)
    assert primitives == {"name": "Test"}


def test_parse_name_case_sensitive() -> None:
    args = MultiDict([("name", "Test"), ("name_case_sensitive", "true")])
    primitives = parse_search_params(args)
    assert primitives == {"name": "Test", "name_case_sensitive": True}


def test_parse_distance() -> None:
    args = MultiDict([("distance_km_min", "10"), ("distance_km_max", "50.5")])
    primitives = parse_search_params(args)
    assert primitives == {"distance_km_min": 10.0, "distance_km_max": 50.5}


def test_primitives_to_json() -> None:
    primitives = {"equipment": [1, 2], "name": "Test"}
    json_str = primitives_to_json(primitives)
    # Keys should be sorted
    assert json_str == '{"equipment": [1, 2], "name": "Test"}'


def test_primitives_to_url_str() -> None:
    primitives = {"equipment": [1, 2], "name": "Test Query"}
    url_str = primitives_to_url_str(primitives)
    assert "equipment=1" in url_str
    assert "equipment=2" in url_str
    assert "name=Test+Query" in url_str


def test_primitives_to_jinja() -> None:
    primitives = {"equipment": [1], "name": "Test"}
    jinja_dict = primitives_to_jinja(primitives)
    assert jinja_dict["equipment"] == [1]
    assert jinja_dict["name"] == "Test"
    assert jinja_dict["kind"] == []  # Default value
    assert jinja_dict["active"] == True


def test_primitives_to_jinja_empty() -> None:
    primitives = {}
    jinja_dict = primitives_to_jinja(primitives)
    assert jinja_dict["equipment"] == []
    assert jinja_dict["name"] == ""
    assert jinja_dict["active"] == False
