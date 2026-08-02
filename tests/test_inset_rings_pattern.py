import numpy as np

from geo_activity_playground.features.explorer.tile_rendering import InsetRingsPattern

ORANGE = np.array([[[1.0, 0.5, 0.0, 1.0]]], dtype=np.float32)
BLUE = np.array([[[0.0, 0.4, 1.0, 1.0]]], dtype=np.float32)


def test_two_rings_are_nested_and_leave_the_core_transparent():
    rgba = InsetRingsPattern([ORANGE, BLUE]).rasterize((256, 256))
    thickness = 256 // 24

    assert np.allclose(rgba[0, 128], ORANGE.flatten())
    assert np.allclose(rgba[thickness, 128], BLUE.flatten())
    assert rgba[128, 128, 3] == 0.0


def test_single_ring_leaves_the_core_transparent():
    rgba = InsetRingsPattern([ORANGE]).rasterize((256, 256))

    assert np.allclose(rgba[0, 128], ORANGE.flatten())
    assert rgba[128, 128, 3] == 0.0


def test_rings_stay_one_pixel_wide_on_small_tiles():
    rgba = InsetRingsPattern([ORANGE, BLUE]).rasterize((8, 8))

    assert np.allclose(rgba[0, 4], ORANGE.flatten())
    assert np.allclose(rgba[1, 4], BLUE.flatten())
    assert rgba[4, 4, 3] == 0.0


def test_inner_ring_is_dropped_when_there_is_no_room():
    rgba = InsetRingsPattern([ORANGE, BLUE]).rasterize((1, 1))

    assert np.allclose(rgba[0, 0], ORANGE.flatten())


def test_borders_never_reach_outside_the_tile():
    """Adjacent tiles cannot overlap because every ring stays within its own array."""
    rgba = InsetRingsPattern([ORANGE, BLUE]).rasterize((64, 64))

    assert rgba.shape == (64, 64, 4)
    assert np.all(rgba[..., 3] <= 1.0)
