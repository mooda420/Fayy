"""Seeded rider-shift schedule for the Rider shift tab, written to docs/data/fleet.json.

Routes are computed in the browser (Balanced, k=3) from the exported motorcycle graph.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT  # noqa: E402

K_BALANCED = 3
SHIFT_SEED = 42
SHIFT_SLOTS = ["1100", "1130", "1200", "1230", "1300", "1330", "1400", "1430", "1500"]

RESTAURANTS = [
    ("The Galleria, Al Maryah", 54.3891, 24.5014),
    ("Reem Mall", 54.4006, 24.4884),
    ("Boutik Mall, Shams", 54.4079, 24.4958),
    ("Marina Square cafés", 54.3997, 24.4937),
    ("Reem Central Park", 54.4085, 24.5058),
    ("Najmat restaurants", 54.4039, 24.4867),
]
TOWERS = [
    ("Sky Tower", 54.40881, 24.496189),
    ("City of Lights C1", 54.40329, 24.49901),
    ("The Gate Tower 1", 54.407661, 24.49411),
    ("The Leaf", 54.394218, 24.49921),
    ("Marina Blue", 54.395538, 24.490749),
    ("Tala Tower", 54.392769, 24.49192),
    ("Maryah Plaza Residences", 54.391537, 24.497961),
    ("Al Maqam Tower", 54.389542, 24.500521),
    ("RAK Tower", 54.394958, 24.487431),
    ("Mangrove Place", 54.408852, 24.49703),
    ("Mismark Towers", 54.405113, 24.484217),
    ("The Bridges", 54.4077, 24.509274),
]


def shift_schedule():
    rnd = random.Random(SHIFT_SEED)
    trips = []
    for slot in SHIFT_SLOTS:
        for _ in range(2):
            trips.append({"slot": slot, "r": rnd.randrange(len(RESTAURANTS)), "t": rnd.randrange(len(TOWERS))})
    return trips


def main():
    out = {"k": K_BALANCED, "restaurants": RESTAURANTS, "towers": TOWERS, "shift": shift_schedule()}
    (OUT / "fleet.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"fleet: {len(out['shift'])} shift deliveries")


if __name__ == "__main__":
    main()
