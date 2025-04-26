import numpy as np

from .missing_values import some


def test_none() -> None:
    assert some(None) == None


def test_nan() -> None:
    assert some(np.nan) == None


def test_float() -> None:
    assert some(1.0) == 1.0


def test_integer() -> None:
    assert some(1) == 1
