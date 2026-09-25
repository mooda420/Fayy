"""Shared configuration for the Fayy precompute pipeline."""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
OVERRIDES = ROOT / "data" / "overrides" / "heights_override.csv"
OUT = ROOT / "docs" / "data"

# west, south, east, north (Al Reem Island + Al Maryah Island / ADGM, Abu Dhabi)
BBOX = (54.378, 24.480, 54.425, 24.512)
CENTER_LON = (BBOX[0] + BBOX[2]) / 2
CENTER_LAT = (BBOX[1] + BBOX[3]) / 2

TZ = "Asia/Dubai"  # UAE-wide zone, UTC+4 (also Abu Dhabi)
METRIC_CRS = "EPSG:32640"  # UTM 40N

DATE_PRESETS = {
    "today": date(2026, 9, 25),
    "summer": date(2026, 7, 15),
}
DATE_LABELS = {"today": "Today (25 Sep)", "summer": "Peak summer (15 Jul)"}

# Every 30 min from 06:00 to 18:30 local time
SLOTS = [f"{h:02d}{m:02d}" for h in range(6, 19) for m in (0, 30)]

FLOOR_HEIGHT_M = 3.2
DEFAULT_HEIGHT_M = 12.0
# Footprint-area heuristic for buildings with no height data: (min_area_m2, height_m), largest first
AREA_HEIGHT_RULES = [(1500.0, 60.0), (600.0, 40.0)]
OVERRIDE_MATCH_M = 40.0
OVERRIDE_MAX_AREA_M2 = 6000.0
MAX_SHADOW_M = 600.0
MIN_SUN_ALT_DEG = 2.0

MOTO_FALLBACK_KPH = 40.0
MOTO_CAP_KPH = 60.0
WALK_SPEED_MS = 1.3
