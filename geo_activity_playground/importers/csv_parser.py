"""

The grammar that we have looks like this:

    document ::= line "\\n" ...

    line ::= cell [ "," cell ...]

    cell ::= '"' text '"' | text

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
