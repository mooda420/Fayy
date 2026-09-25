import sys
from pathlib import Path

import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from shadows import building_shadow  # noqa: E402


def test_east_sun_casts_shadow_west():
    b = box(0, 0, 20, 20)
    s = building_shadow(b, 100, 45, 90)
    minx, miny, maxx, maxy = s.bounds
    assert minx == pytest.approx(-100, abs=0.5)
    assert maxx == pytest.approx(20)
    assert (miny, maxy) == pytest.approx((0, 20))
    assert s.area == pytest.approx(20 * 120, rel=1e-6)


def test_overhead_sun_shadow_is_footprint():
    b = box(0, 0, 20, 20)
    s = building_shadow(b, 100, 90, 180)
    assert s.symmetric_difference(b).area == pytest.approx(0, abs=1e-6)


def test_concave_footprint_is_exact():
    from shapely.geometry import Polygon
    u = Polygon([(0, 0), (30, 0), (30, 30), (20, 30), (20, 10), (10, 10), (10, 30), (0, 30)])
    s = building_shadow(u, 10, 45, 180)  # sun due south -> shadow 10 m north
    assert s.bounds == pytest.approx((0, 0, 30, 40))
    assert s.contains(u)
