from geo_activity_playground.importers.csv_parser import _parse_cell
from geo_activity_playground.importers.csv_parser import _parse_line
from geo_activity_playground.importers.csv_parser import parse_csv


def test_parse_csv() -> None:
    data = """
A,B,C
a,"b,b",c
d,"e
f",g
"""
    expected = {"A": ["a", "d"], "B": ["b,b", "e\nf"], "C": ["c", "g"]}
    assert parse_csv(data) == expected


def test_parse_cell_plain() -> None:
    assert _parse_cell("foo", 0) == ("foo", 3)


def test_parse_cell_with_quotes() -> None:
    assert _parse_cell('"foo"', 0) == ("foo", 5)


def test_parse_cell_with_escape() -> None:
    assert _parse_cell('"f\\"oo"', 0) == ('f"oo', 7)


def test_parse_cell_with_newline() -> None:
    assert _parse_cell('"f\noo"', 0) == ("f\noo", 6)


def test_parse_line_newline() -> None:
    assert _parse_line("a,b,c\n", 0) == (["a", "b", "c"], 6)
