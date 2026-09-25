"""Rider-shift sample for the Rider shift tab, written to docs/data/fleet.json.

The 18 deliveries (6 pickups -> 12 drop-offs) are chosen, from a seeded pool of street
nodes, as the trips where the Balanced Fayy route avoids the most direct sun on the
afternoon shift. Routes are recomputed in the browser from graph_moto.json.
"""
import heapq
import json
import math
import random
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT  # noqa: E402

K_BALANCED = 3
SHIFT_SEED = 42
POOL = 300
N_PICKUPS, N_DROPS, N_DELIVERIES = 6, 12, 18
MIN_SEP_M = 250
MIN_TRIP_M = 1500
SHIFTS = {
    "afternoon": ["1530", "1600", "1630", "1700", "1730", "1800", "1830"],
    "midday": ["1100", "1130", "1200", "1230", "1300", "1330", "1400", "1430", "1500"],
}


def sssp(adj, edges, n, src, k, si):
    """Dijkstra on time * (1 + k * sun); returns cost and accumulated sun seconds / metres."""
    dist, sun, length = [math.inf] * n, [0.0] * n, [0.0] * n
    dist[src] = 0.0
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for ei, v in adj[u]:
            e = edges[ei]
            nd = d + e[3] * (1 + k * e[5][si] / 100)
            if nd < dist[v]:
                dist[v], sun[v], length[v] = nd, sun[u] + e[3] * e[5][si] / 100, length[u] + e[2]
                heapq.heappush(heap, (nd, v))
    return dist, sun, length


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 101_300, (a[1] - b[1]) * 111_200)


def place_name(lon, lat):
    """Short English place name via the free Nominatim reverse geocoder."""
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=18&accept-language=en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Fayy shade-routing hackathon demo"})
        with urllib.request.urlopen(req, timeout=20) as r:
            js = json.loads(r.read())
        time.sleep(1.1)
        addr = js.get("address", {})
        area = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter")
        parts = [x for x in (addr.get("road"), area) if x]
        return ", ".join(parts) or f"{lat:.4f}, {lon:.4f}"
    except OSError:
        return f"{lat:.4f}, {lon:.4f}"


def pick_trips(g, day_slots):
    edges, nodes = g["edges"], g["nodes"]
    n = len(nodes)
    adj = [[] for _ in range(n)]
    for i, e in enumerate(edges):
        adj[e[0]].append((i, e[1]))
    pos = {i: (nodes[i][1], nodes[i][2]) for i in range(n)}
    pool = random.Random(SHIFT_SEED).sample([i for i in range(n) if adj[i]], POOL)
    slots = SHIFTS["afternoon"]
    cands = []
    for j, slot in enumerate(slots):
        si = day_slots.index(slot)
        for a in pool:
            _, s0, l0 = sssp(adj, edges, n, a, 0, si)
            dk, sk, _ = sssp(adj, edges, n, a, K_BALANCED, si)
            for b in pool:
                if b != a and math.isfinite(dk[b]) and l0[b] >= MIN_TRIP_M:
                    cands.append((s0[b] - sk[b], a, b, j))
    cands.sort(reverse=True)
    quota = [0] * len(slots)
    for i in range(N_DELIVERIES):
        quota[i * len(slots) // N_DELIVERIES] += 1
    pickups, drops, trips, pairs = [], [], [], set()

    def fits(p, chosen, cap):
        if p in chosen:
            return True
        return len(chosen) < cap and all(metres(pos[p], pos[q]) >= MIN_SEP_M for q in pickups + drops)

    for _, a, b, j in cands:
        if quota[j] == 0 or (a, b) in pairs or a in drops or b in pickups:
            continue
        if not (fits(a, pickups, N_PICKUPS) and fits(b, drops, N_DROPS)):
            continue
        if a not in pickups:
            pickups.append(a)
        if b not in drops:
            drops.append(b)
        pairs.add((a, b))
        quota[j] -= 1
        trips.append((j, a, b))
        if len(trips) == N_DELIVERIES:
            break
    trips.sort()
    return pickups, drops, trips, pos


def main():
    g = json.loads((OUT / "graph_moto.json").read_text())
    meta = json.loads((OUT / "meta.json").read_text())
    pickups, drops, trips, pos = pick_trips(g, meta["slots"])
    named = lambda pts: [[place_name(*pos[p]), round(pos[p][0], 6), round(pos[p][1], 6)] for p in pts]
    pairs = [(pickups.index(a), drops.index(b)) for _, a, b in trips]
    out = {
        "k": K_BALANCED, "restaurants": named(pickups), "towers": named(drops),
        "shifts": {
            k: [{"slot": v[i * len(v) // N_DELIVERIES], "r": r, "t": t} for i, (r, t) in enumerate(pairs)]
            for k, v in SHIFTS.items()
        },
    }
    (OUT / "fleet.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"fleet: {len(trips)} deliveries, {len(pickups)} pickups, {len(drops)} drop-offs")


if __name__ == "__main__":
    main()
