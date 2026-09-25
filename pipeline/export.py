"""Write compact JSON/GeoJSON outputs into docs/data/."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import METRIC_CRS, OUT  # noqa: E402

TO_WGS = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)


def _dump(obj, path):
    Path(path).write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def write_geojson(gdf, path, props=(), precision=6):
    g = gdf.to_crs("EPSG:4326")
    g = g.set_geometry(g.geometry.set_precision(10 ** -precision))
    g = g[~g.geometry.is_empty]
    feats = []
    for _, r in g.iterrows():
        f = {"type": "Feature", "properties": {p: r[p] for p in props},
             "geometry": json.loads(gpd.GeoSeries([r.geometry]).to_json())["features"][0]["geometry"]}
        feats.append(f)
    _dump({"type": "FeatureCollection", "features": feats}, path)


def write_shadow(shade_metric, path):
    gdf = gpd.GeoDataFrame(geometry=[shade_metric], crs=METRIC_CRS).explode(index_parts=False)
    write_geojson(gdf, path)


def write_graph(G, lines, fractions, path, bidirectional=False):
    """nodes: [id, lon, lat]; edges: [from, to, length_m, time_s, [[lon,lat]...], [sun% per slot]]."""
    node_ids = {n: i for i, n in enumerate(G.nodes)}
    lon, lat = TO_WGS.transform([G.nodes[n]["x"] for n in G.nodes], [G.nodes[n]["y"] for n in G.nodes])
    nodes = [[i, round(x, 6), round(y, 6)] for i, x, y in zip(range(len(node_ids)), lon, lat)]
    seen, edges = set(), []
    for idx, (u, v, k, d, geom) in enumerate(lines):
        a, b = node_ids[u], node_ids[v]
        if bidirectional:
            key = (min(a, b), max(a, b), round(d["length"]))
            if key in seen:
                continue
            seen.add(key)
        xs, ys = TO_WGS.transform(*geom.xy)
        coords = [[round(x, 6), round(y, 6)] for x, y in zip(xs, ys)]
        sun = [int(round(100 * fractions[s][idx])) for s in range(len(fractions))]
        edges.append([a, b, round(float(d["length"]), 1), round(float(d["travel_time"]), 1), coords, sun])
    _dump({"bidirectional": bidirectional, "nodes": nodes, "edges": edges}, path)
    return len(edges)


def write_meta(meta):
    _dump(meta, OUT / "meta.json")


def np_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError
