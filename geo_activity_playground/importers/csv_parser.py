"""
CSV parser that can handle newlines in cells.

In the Strava export there is a file `activities.csv`. With CSV being a horrible format, there are of course issues with it. One is that the activity description can have newlines in it, they are in the CSV file in verbatim. Therefore we need to have a CSV parser that can handle it. `pandas.read_csv` cannot do it.

The grammar that we have looks like this:

    document ::= line [line ...]

    line ::= cell [ "," cell ...] "\n"

    cell ::= '"' text_with_comma '"' | text_without_comma

    text_with_comma ::= (token | '\\n' | ',') ...
    text_without_comma ::= token ...

This module implements a "recursive descent parser" that parses this grammar.
"""


def parse_csv(text: str) -> dict[str, list]:
    text = text.strip() + "\n"
    result = {}
    index = 0
    columns, index = _parse_line(text, index)
    result = {column: [] for column in columns}
    while index < len(text):
        line, index = _parse_line(text, index)
        assert len(line) == len(
            columns
        ), f"Expected {len(columns)} columns at {index=}, got {len(line)} columns"
        for col, cell in zip(columns, line):
            result[col].append(cell)

    return result


def _parse_line(text: str, start: int) -> tuple[list, int]:
    index = start
    result = []
    while index < len(text) and text[index] != "\n":
        cell, index = _parse_cell(text, index)
        result.append(cell)
        if text[index] == "\n":
            return result, index + 1
        else:
            assert text[index] == ",", f"Expected ',' at {index=}, got {text[index]}"
            index += 1
    assert False, "We should never get here"


def _parse_cell(text: str, start: int) -> tuple[str, int]:
    characters = []
    escape = False
    within_quotes = False
    i = start
    for i in range(start, len(text) + 1):
        if i == len(text):
            break

        c = text[i]

        if c == '"' and not escape:
            within_quotes = not within_quotes
            continue
        elif c == "\\":
            escape = True
            continue
        elif (c == "," or c == "\n") and not within_quotes:
            break
        else:
            characters.append(c)
            escape = False

    return "".join(characters), i
