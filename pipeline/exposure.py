"""Sun fraction per street edge per time slot."""
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parent))


def edge_lines(G):
    """List of (u, v, key, data, LineString) in the graph's metric CRS."""
    out = []
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        if geom is None:
            geom = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])])
        out.append((u, v, k, d, geom))
    return out


def sun_fractions(lines, shade):
    """Fraction (0..1) of each line's length NOT covered by the shade geometry."""
    lines = np.asarray(lines, dtype=object)
    lengths = shapely.length(lines)
    polys = np.asarray(shapely.get_parts(shade), dtype=object)
    if len(polys) == 0:
        return np.ones(len(lines))
    tree = shapely.STRtree(polys)
    li, pi = tree.query(lines, predicate="intersects")
    shaded = np.zeros(len(lines))
    if len(li):
        inter = shapely.length(shapely.intersection(lines[li], polys[pi]))
        np.add.at(shaded, li, inter)
    frac = 1 - np.clip(shaded / np.maximum(lengths, 1e-9), 0, 1)
    frac[lengths < 1e-6] = 0.0
    return frac
