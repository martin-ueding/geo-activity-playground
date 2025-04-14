import pytest

from .csv_parser import _parse_cell
from .csv_parser import _parse_line
from .csv_parser import parse_csv


def test_parse_csv() -> None:
    data = """
A,B,C
a,"b,b",c
d,"e
f",g
"""
    expected = [["A", "B", "C"], ["a", "b,b", "c"], ["d", "e\nf", "g"]]
    assert parse_csv(data) == expected


def test_parse_cell_plain() -> None:
    assert _parse_cell("foo", 0) == ("foo", 3)


def test_parse_cell_with_quotes() -> None:
    assert _parse_cell('"foo"', 0) == ("foo", 5)


def test_parse_cell_with_escape() -> None:
    assert _parse_cell('"f\\"oo"', 0) == ('f"oo', 7)


def test_parse_cell_with_newline() -> None:
    assert _parse_cell('"f\noo"', 0) == ("f\noo", 6)


def test_parse_cell_empty() -> None:
    assert _parse_cell("", 0) == ("", 0)


def test_parse_line() -> None:
    assert _parse_line("a,b,c\n", 0) == (["a", "b", "c"], 6)


def test_parse_line_empty_cell() -> None:
    assert _parse_line("a,,c\n", 0) == (["a", "", "c"], 5)


@pytest.mark.xfail
def test_parse_line_empty_cell_at_end() -> None:
    assert _parse_line("a,b,\n", 0) == (["a", "b", ""], 5)
