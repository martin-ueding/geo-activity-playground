import pytest

from geo_activity_playground.features.places.visits import visit_sequence

HOME = 1
BAKERY = 2
WORK = 3


@pytest.mark.parametrize(
    ("stay_place_ids", "visits"),
    [
        ([HOME, HOME], [HOME, HOME]),
        ([HOME, None, HOME], [HOME, HOME]),
        ([HOME, BAKERY, HOME], [HOME, BAKERY, HOME]),
        ([HOME, BAKERY, BAKERY, HOME], [HOME, BAKERY, HOME]),
        ([HOME, HOME, BAKERY, HOME], [HOME, BAKERY, HOME]),
        ([HOME, BAKERY, HOME, HOME], [HOME, BAKERY, HOME]),
        ([HOME, WORK, WORK], [HOME, WORK]),
        ([None, BAKERY, None], [None, BAKERY, None]),
        ([None, None], [None, None]),
        ([], []),
    ],
)
def test_visit_sequence(
    stay_place_ids: list[int | None], visits: list[int | None]
) -> None:
    assert visit_sequence(stay_place_ids) == visits
