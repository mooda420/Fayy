"""Download buildings (Overture, OSM fallback) and street graphs (OSM via osmnx)."""
import csv
import json
import subprocess
import sys

import geopandas as gpd
import numpy as np
import osmnx as ox

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import (BBOX, DEFAULT_HEIGHT_M, FLOOR_HEIGHT_M, INTERIM, METRIC_CRS,  # noqa: E402
                    MOTO_CAP_KPH, MOTO_FALLBACK_KPH, OUT, OVERRIDES, RAW, WALK_SPEED_MS)

ox.settings.use_cache = True
ox.settings.cache_folder = str(RAW / "osmnx_cache")


def _num(v):
    try:
        f = float(str(v).split(";")[0].replace("m", "").strip())
        return f if np.isfinite(f) and f > 0 else None
    except (TypeError, ValueError):
        return None


def download_overture():
    out = RAW / "buildings.geojson"
    if out.exists() and out.stat().st_size > 1000:
        return out
    bbox = ",".join(str(v) for v in BBOX)
    exe = str(__import__("pathlib").Path(sys.executable).with_name("overturemaps"))
    subprocess.run([exe, "download", f"--bbox={bbox}", "-f", "geojson",
                    "--type=building", "--no-stac", "-o", str(out)], check=True)
    return out


def load_buildings():
    source = "overture"
    try:
        gdf = gpd.read_file(download_overture())
        gdf["name"] = gdf["names"].apply(_primary_name) if "names" in gdf else None
        gdf["raw_height"] = gdf.get("height")
        gdf["raw_floors"] = gdf.get("num_floors")
        gdf["bid"] = gdf["id"].astype(str)
        gdf = gdf.reset_index(drop=True)
        try:
            gdf = fill_from_osm(gdf)
        except Exception as exc:  # noqa: BLE001
            print(f"OSM height fill skipped: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"Overture failed ({exc}); falling back to OSM buildings")
        source = "osm"
        w, s, e, n = BBOX
        gdf = ox.features_from_bbox(bbox=(w, s, e, n), tags={"building": True}).reset_index()
        gdf["raw_height"] = gdf.get("height")
        gdf["raw_floors"] = gdf.get("building:levels")
        gdf["bid"] = gdf["element"].astype(str) + "/" + gdf["id"].astype(str)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    return gdf, source


def _primary_name(names):
    if isinstance(names, str):
        try:
            names = json.loads(names)
        except ValueError:
            return None
    if isinstance(names, dict):
        return names.get("primary")
    return None


def osm_buildings():
    w, s, e, n = BBOX
    osm = ox.features_from_bbox(bbox=(w, s, e, n), tags={"building": True}).reset_index()
    osm = osm[osm.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    osm["raw_height"] = osm["height"] if "height" in osm else None
    osm["raw_floors"] = osm["building:levels"] if "building:levels" in osm else None
    osm["bid"] = osm["element"].astype(str) + "/" + osm["id"].astype(str)
    return osm


def fill_from_osm(gdf):
    """Fill Overture buildings lacking height/floors from the best-overlapping OSM building."""
    osm = osm_buildings()
    osm = osm[osm["raw_height"].apply(_num).notna() | osm["raw_floors"].apply(_num).notna()]
    if osm.empty:
        return gdf
    a = gdf.to_crs(METRIC_CRS)
    b = osm[["raw_height", "raw_floors", "geometry"]].to_crs(METRIC_CRS).reset_index(drop=True)
    gdf["raw_height"] = gdf["raw_height"].astype(object)
    gdf["raw_floors"] = gdf["raw_floors"].astype(object)
    missing = a["raw_height"].apply(_num).isna() & a["raw_floors"].apply(_num).isna()
    tree = b.sindex
    filled = 0
    for i in a.index[missing]:
        g = a.geometry[i]
        best, best_share = None, 0.5
        for j in tree.query(g, predicate="intersects"):
            share = g.intersection(b.geometry[j]).area / max(g.area, 1e-9)
            if share > best_share:
                best, best_share = j, share
        if best is not None:
            gdf.at[i, "raw_height"] = b.at[best, "raw_height"]
            gdf.at[i, "raw_floors"] = b.at[best, "raw_floors"]
            filled += 1
    print(f"filled {filled} Overture buildings with OSM height/levels")
    gdf.attrs["osm_filled"] = filled
    return gdf


def load_overrides():
    table = {}
    if OVERRIDES.exists():
        with open(OVERRIDES, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                table[row["key"].strip().lower()] = float(row["height_m"])
    return table


def assign_heights(gdf):
    overrides = load_overrides()
    heights, sources = [], []
    for _, r in gdf.iterrows():
        name = (r.get("name") or "")
        key_hits = [overrides.get(str(r["bid"]).lower()), overrides.get(str(name).strip().lower())]
        ov = next((k for k in key_hits if k), None)
        h, f = _num(r.get("raw_height")), _num(r.get("raw_floors"))
        if ov:
            heights.append(ov); sources.append("override")
        elif h:
            heights.append(h); sources.append("height")
        elif f:
            heights.append(f * FLOOR_HEIGHT_M); sources.append("floors")
        else:
            heights.append(DEFAULT_HEIGHT_M); sources.append("default")
    gdf["height"] = np.round(heights, 1)
    gdf["height_source"] = sources
    return gdf


def fetch_buildings():
    gdf, source = load_buildings()
    osm_filled = gdf.attrs.get("osm_filled", 0)
    gdf = assign_heights(gdf)
    gdf = gdf[["bid", "name", "height", "height_source", "geometry"]].to_crs(METRIC_CRS)
    gdf = gdf[gdf.geometry.area > 4].reset_index(drop=True)
    counts = gdf["height_source"].value_counts().to_dict()
    n = len(gdf)
    stats = {
        "source": source,
        "buildings": n,
        "with_height": int(counts.get("height", 0)),
        "from_floors": int(counts.get("floors", 0)),
        "from_override": int(counts.get("override", 0)),
        "defaulted": int(counts.get("default", 0)),
        "osm_filled": int(osm_filled),
    }
    stats["real_pct"] = round(100 * (n - stats["defaulted"]) / max(n, 1), 1)
    print("Height coverage:", json.dumps(stats))
    gdf.to_file(INTERIM / "buildings.gpkg", driver="GPKG")
    return gdf, stats


def fetch_graphs():
    w, s, e, n = BBOX
    moto = ox.graph_from_bbox(bbox=(w, s, e, n), network_type="drive_service", simplify=True)
    moto = ox.truncate.largest_component(moto, strongly=True)
    moto = ox.add_edge_speeds(moto, fallback=MOTO_FALLBACK_KPH)
    for _, _, d in moto.edges(data=True):
        d["speed_kph"] = min(float(d["speed_kph"]), MOTO_CAP_KPH)
    moto = ox.add_edge_travel_times(moto)
    walk = ox.graph_from_bbox(bbox=(w, s, e, n), network_type="walk", simplify=True)
    walk = ox.truncate.largest_component(walk, strongly=False)
    for _, _, d in walk.edges(data=True):
        d["travel_time"] = d["length"] / WALK_SPEED_MS
    moto_p = ox.project_graph(moto, to_crs=METRIC_CRS)
    walk_p = ox.project_graph(walk, to_crs=METRIC_CRS)
    ox.save_graphml(moto_p, INTERIM / "moto.graphml")
    ox.save_graphml(walk_p, INTERIM / "walk.graphml")
    print(f"moto graph: {len(moto_p)} nodes / {moto_p.number_of_edges()} edges; "
          f"walk graph: {len(walk_p)} nodes / {walk_p.number_of_edges()} edges")
    return moto_p, walk_p


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    INTERIM.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    _, stats = fetch_buildings()
    moto, walk = fetch_graphs()
    stats["moto_edges"] = moto.number_of_edges()
    stats["walk_edges"] = walk.number_of_edges()
    (OUT / "stats.json").write_text(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
