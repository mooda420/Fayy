"""Sun position and building shadow geometry."""
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
import shapely
from shapely.geometry import MultiPolygon, Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (CENTER_LAT, CENTER_LON, MAX_SHADOW_M, MIN_SUN_ALT_DEG,  # noqa: E402
                    SLOTS, TZ)


def sun_positions(day, slots=SLOTS):
    """Return {slot: (altitude_deg, azimuth_deg)} for a date at the bbox centre."""
    times = pd.DatetimeIndex(
        [datetime(day.year, day.month, day.day, int(s[:2]), int(s[2:])) for s in slots]
    ).tz_localize(TZ)
    sp = pvlib.solarposition.get_solarposition(times, CENTER_LAT, CENTER_LON)
    return {s: (float(a), float(z)) for s, a, z in
            zip(slots, sp["apparent_elevation"], sp["azimuth"])}


def shadow_offset(height, altitude_deg, azimuth_deg):
    """Offset (dx east, dy north) of a roof point's shadow on flat ground."""
    if altitude_deg >= 90:
        return 0.0, 0.0
    length = min(height / math.tan(math.radians(altitude_deg)), MAX_SHADOW_M)
    a = math.radians(azimuth_deg)
    return -length * math.sin(a), -length * math.cos(a)


def _polygon_shadow(poly, dx, dy):
    parts = [poly, shapely.affinity.translate(poly, dx, dy)]
    for ring in [poly.exterior, *poly.interiors]:
        c = np.asarray(ring.coords)
        a, b = c[:-1], c[1:]
        quads = np.stack([a, b, b + (dx, dy), a + (dx, dy), a], axis=1)
        parts.extend(shapely.polygons(quads))
    return shapely.union_all(shapely.make_valid(np.array(parts, dtype=object)))


def building_shadow(geom, height, altitude_deg, azimuth_deg):
    """Exact shadow (footprint + swept prism) of an extruded polygon on flat ground."""
    dx, dy = shadow_offset(height, altitude_deg, azimuth_deg)
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return geom
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    return shapely.union_all([_polygon_shadow(p, dx, dy) for p in polys if isinstance(p, Polygon)])


def shadow_union(geoms, heights, altitude_deg, azimuth_deg, area_bounds):
    """Union of all building shadows for one sun position (metric CRS)."""
    if altitude_deg <= MIN_SUN_ALT_DEG:
        return box(*area_bounds)
    shadows = [building_shadow(g, h, altitude_deg, azimuth_deg) for g, h in zip(geoms, heights)]
    return shapely.union_all(shadows).simplify(1.0)
