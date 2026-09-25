"""Rider-shift simulation and shade-canopy ranking, written to docs/data/fleet.json.

Reads the exported motorcycle graph so routes match the browser exactly (Balanced, k=3).
"""
import heapq
import json
import math
import random
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INTERIM, METRIC_CRS, OUT  # noqa: E402

K_BALANCED = 3
SHIFT_SEED, RANDOM_SEED = 42, 7
SHIFT_SLOTS = ["1100", "1130", "1200", "1230", "1300", "1330", "1400", "1430", "1500"]
N_RANDOM = 200
UNAVOIDABLE_SUN = 50
TOP_N = 10

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


class Graph:
    def __init__(self, g):
        self.nodes, self.edges = g["nodes"], g["edges"]
        self.adj = defaultdict(list)
        for i, e in enumerate(self.edges):
            self.adj[e[0]].append((i, e[1]))
            if g.get("bidirectional"):
                self.adj[e[1]].append((i, e[0]))
        self.live = [n for n in self.nodes if self.adj[n[0]]]

    def nearest(self, lon, lat):
        c = math.cos(math.radians(lat))
        return min(self.live, key=lambda n: ((n[1] - lon) * c) ** 2 + (n[2] - lat) ** 2)[0]

    def route(self, src, dst, k, si):
        dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == dst:
                break
            if d > dist[u]:
                continue
            for ei, v in self.adj[u]:
                e = self.edges[ei]
                nd = d + e[3] * (1 + k * e[5][si] / 100)
                if nd < dist.get(v, math.inf):
                    dist[v], prev[v] = nd, ei
                    heapq.heappush(pq, (nd, v))
        if dst not in dist:
            return None
        path, v = [], dst
        while v != src:
            ei = prev[v]
            path.append(ei)
            e = self.edges[ei]
            v = e[0] if e[1] == v else e[1]
        return path[::-1]

    def sun_s(self, path, si):
        return sum(self.edges[i][3] * self.edges[i][5][si] / 100 for i in path)


def shift_schedule():
    rnd = random.Random(SHIFT_SEED)
    trips = []
    for slot in SHIFT_SLOTS:
        for _ in range(2):
            r, tw = rnd.randrange(len(RESTAURANTS)), rnd.randrange(len(TOWERS))
            trips.append({"slot": slot, "r": r, "t": tw})
    return trips


def random_trips(g, day_slots):
    rnd = random.Random(RANDOM_SEED)
    trips = []
    while len(trips) < N_RANDOM:
        a, b = rnd.sample(g.live, 2)
        c = math.cos(math.radians(a[2]))
        if math.hypot((a[1] - b[1]) * c, a[2] - b[2]) * 111320 < 800:
            continue
        trips.append((a[0], b[0], rnd.choice(day_slots)))
    return trips


def english_name(lon, lat):
    """English street name via the free Nominatim reverse geocoder; None on failure."""
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=17&accept-language=en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Fayy shade-routing hackathon demo"})
        with urllib.request.urlopen(req, timeout=20) as r:
            addr = json.loads(r.read()).get("address", {})
        time.sleep(1.1)
        return addr.get("road")
    except OSError:
        return None


def street_names(points):
    try:
        G = ox.load_graphml(INTERIM / "moto.graphml")
    except OSError:
        return [None] * len(points)
    edges = ox.graph_to_gdfs(G, nodes=False)[["name", "geometry"]].to_crs(METRIC_CRS)
    edges = edges[edges["name"].notna()]
    pts = gpd.GeoSeries([Point(lon, lat) for lon, lat in points], crs=4326).to_crs(METRIC_CRS)
    out = []
    for p in pts:
        name = edges.loc[edges.geometry.distance(p).idxmin(), "name"]
        name = name[0] if isinstance(name, list) else name
        lon, lat = gpd.GeoSeries([p], crs=METRIC_CRS).to_crs(4326).iloc[0].coords[0]
        out.append(english_name(lon, lat) or name)
    return out


def main():
    meta = json.loads((OUT / "meta.json").read_text())
    g = Graph(json.loads((OUT / "graph_moto.json").read_text()))
    slots = meta["slots"]
    shift = shift_schedule()
    r_nodes = [g.nearest(lon, lat) for _, lon, lat in RESTAURANTS]
    t_nodes = [g.nearest(lon, lat) for _, lon, lat in TOWERS]
    out = {"k": K_BALANCED, "restaurants": RESTAURANTS, "towers": TOWERS, "shift": shift, "canopy": {}}

    for di, d in enumerate(meta["dates"]):
        sunny_slots = [s for s in slots if meta["index"][di * len(slots) + slots.index(s)]["alt"] > 2]
        trips = [(r_nodes[x["r"]], t_nodes[x["t"]], x["slot"]) for x in shift] + random_trips(g, sunny_slots)
        load, count = defaultdict(float), defaultdict(int)
        for src, dst, slot in trips:
            si = di * len(slots) + slots.index(slot)
            path = g.route(src, dst, K_BALANCED, si)
            for ei in path or []:
                e = g.edges[ei]
                if e[5][si] >= UNAVOIDABLE_SUN:
                    key = tuple(sorted((e[0], e[1])))
                    load[key] += e[3] * e[5][si] / 100 / 60
                    count[key] += 1
        by_pair = {}
        for i, e in enumerate(g.edges):
            by_pair.setdefault(tuple(sorted((e[0], e[1]))), i)
        top = sorted(load, key=load.get, reverse=True)[:TOP_N]
        mids = [g.edges[by_pair[k]][4][len(g.edges[by_pair[k]][4]) // 2] for k in top]
        names = street_names(mids)
        out["canopy"][d["key"]] = [
            {"minutes": round(load[k], 1), "trips": count[k], "length_m": round(g.edges[by_pair[k]][2]),
             "name": names[j], "coords": g.edges[by_pair[k]][4], "mid": mids[j]}
            for j, k in enumerate(top)
        ]
        print(f"canopy {d['key']}: {len(trips)} trips, top edge {out['canopy'][d['key']][0]['minutes']} min")
    (OUT / "fleet.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
