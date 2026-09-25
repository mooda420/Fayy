"""Run the full Fayy precompute pipeline end to end: python pipeline/run_all.py [--skip-fetch]"""
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data  # noqa: E402
from config import (BBOX, DATE_LABELS, DATE_PRESETS, INTERIM, METRIC_CRS, OUT,  # noqa: E402
                    SLOTS)
from export import write_geojson, write_graph, write_meta, write_shadow  # noqa: E402
from exposure import edge_lines, sun_fractions  # noqa: E402
from shadows import shadow_union, sun_positions  # noqa: E402


def main():
    t0 = time.time()
    if "--skip-fetch" not in sys.argv or not (INTERIM / "buildings.gpkg").exists():
        fetch_data.main()
    stats = json.loads((OUT / "stats.json").read_text())
    bld = gpd.read_file(INTERIM / "buildings.gpkg").to_crs(METRIC_CRS)
    moto = ox.load_graphml(INTERIM / "moto.graphml")
    walk = ox.load_graphml(INTERIM / "walk.graphml")
    bounds = gpd.GeoSeries.from_xy([BBOX[0], BBOX[2]], [BBOX[1], BBOX[3]], crs=4326).to_crs(METRIC_CRS).total_bounds
    pad = (bounds[0] - 800, bounds[1] - 800, bounds[2] + 800, bounds[3] + 800)

    write_geojson(bld, OUT / "buildings.geojson", props=("height",))
    moto_lines, walk_lines = edge_lines(moto), edge_lines(walk)
    moto_geoms = [x[4] for x in moto_lines]
    walk_geoms = [x[4] for x in walk_lines]
    moto_frac, walk_frac, slots_meta = [], [], []
    geoms, heights = list(bld.geometry), list(bld["height"])
    for dkey, day in DATE_PRESETS.items():
        sun = sun_positions(day)
        for slot in SLOTS:
            alt, az = sun[slot]
            shade = shadow_union(geoms, heights, alt, az, pad)
            write_shadow(shade, OUT / f"shadows_{dkey}_{slot}.geojson")
            mf, wf = sun_fractions(moto_geoms, shade), sun_fractions(walk_geoms, shade)
            moto_frac.append(mf)
            walk_frac.append(wf)
            slots_meta.append({"date": dkey, "slot": slot, "alt": round(alt, 1), "az": round(az, 1),
                               "moto_sun": round(float(mf.mean()), 3), "walk_sun": round(float(wf.mean()), 3)})
            print(f"{dkey} {slot}: alt {alt:5.1f} az {az:5.1f} moto sun {mf.mean():.2f} walk sun {wf.mean():.2f}")
    stats["moto_edges_export"] = write_graph(moto, moto_lines, moto_frac, OUT / "graph_moto.json")
    stats["walk_edges_export"] = write_graph(walk, walk_lines, walk_frac, OUT / "graph_walk.json", bidirectional=True)
    (OUT / "stats.json").write_text(json.dumps(stats, indent=1))
    write_meta({"bbox": BBOX, "slots": SLOTS,
                "dates": [{"key": k, "label": DATE_LABELS[k], "iso": d.isoformat()} for k, d in DATE_PRESETS.items()],
                "index": slots_meta})
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
