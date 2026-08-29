"""Export a stratified sample of validation routes for the interactive assessment.

For each sampled origin point this reconstructs the *actual* shortest path the
cycling accessibility indicators used to reach the nearest destination of each
target category, under each routing measure -- so a validator is shown the route
behind the number, not a re-derived approximation.

The reconstruction reuses the production routing exactly: the same subgraph
(measure ``where``), the same edge costs, and the same multi-source Dijkstra from
a virtual super-source wired to every destination node at its offset cost (see
``_nearest_distances_inmemory``).  Requesting ``return_predecessors`` from that
same pass yields the shortest-path tree, so walking predecessors from an origin
back to the super-source recovers the route the indicator costed.

Sampling: ``--n-points`` origins (default 20), stratified into four quadrants of
the urban study region, drawn within each quadrant with probability proportional
to the population of the 100 m grid cell containing the point (PPS), from a fixed
``--seed`` recorded in the output for reproducibility.

Each route is disaggregated into ridden and dismounted (walk-the-bike) segments,
with both the geometric distance and the penalised routing cost, so the distance
budget a validator sees matches the one the indicator spent.

The two *connection* legs are exported as geometry too, not just as numbers folded
into the total: sample points and destinations sit partway along an edge, and the
offsets the indicator charges are measured along that edge, so each leg is exported
as the corresponding sub-line (``ST_LineSubstring``).  Without them a drawn route
starts at a terminal node rather than at the point being assessed -- sometimes a few
hundred metres away, and occasionally the whole route (origin node == destination
node) is nothing but connection legs and so has no geometry at all.

Usage (inside the ghsci container):
    /env/bin/python subprocesses/_export_validation_routes.py \
        "data/Cycling/Melbourne/Melbourne.yml" \
        [--n-points 20] [--seed 42] [--outdir DIR]

Writes ``<outdir>/<slug>_routes.json`` (default outdir /tmp/validation_tiles/<slug>).
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

if __name__ == '__main__':
    # usage examples give configuration paths relative to the process
    # folder; as a module this leaves the caller's directory alone
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ghsci  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from _cycling_accessibility import (  # noqa: E402
    _DEST_TABLE,
    DEFAULT_DESTINATIONS,
    MEASURE_ORDER,
    MEASURES,
    _build_dest_table,
    _ensure_node_associations,
    resolve_measures,
    usable_destination_specs,
)
from _cycling_lts_network import cycling_config  # noqa: E402
from scipy.sparse import csr_matrix, hstack, vstack  # noqa: E402
from scipy.sparse.csgraph import dijkstra  # noqa: E402
from setup_sp import load_network_graph  # noqa: E402
from sqlalchemy import text  # noqa: E402

# The three strict destination categories shown per point.  Public transport
# falls back to any stop where no frequent-service (GTFS) layer exists.
TARGETS = [
    {
        'key': 'fresh_food_market',
        'label': 'Fresh food / market',
        'fallbacks': [],
    },
    {
        'key': 'pt_frequent',
        'label': 'Public transport (frequent)',
        'fallbacks': ['pt_any'],
    },
    {
        'key': 'public_open_space_large',
        'label': 'Public open space (large)',
        'fallbacks': [],
    },
]
PT_FALLBACK_LABEL = 'Public transport (any)'

MAX_BAND = 5000  # exploration limit: unreachable beyond the largest threshold
COORD_DP = 5
_PAIR_TABLE = '_cyc_route_pairs'


def slugify(name):
    ascii_name = (
        unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    )
    return re.sub(r'[^a-z0-9]+', '_', ascii_name.lower()).strip('_')


# --------------------------------------------------------------- sampling
def sample_points(r, n_points, seed):
    """Population-weighted, quadrant-stratified sample of origin points.

    Cells are drawn with probability proportional to population within each
    quadrant of the urban study region, then one sample point is taken at
    random from the chosen cell -- textbook PPS, and it keeps points where
    people actually live rather than spread over empty periphery.
    """
    rng = np.random.default_rng(seed)
    grid = r.config['grid_summary']
    bounds = r.get_df(
        'SELECT ST_XMin(g) x0, ST_YMin(g) y0, ST_XMax(g) x1, ST_YMax(g) y1 '
        'FROM (SELECT ST_Extent(geom) g FROM urban_study_region) s',
    ).iloc[0]
    xmid = (bounds['x0'] + bounds['x1']) / 2
    ymid = (bounds['y0'] + bounds['y1']) / 2

    pts = r.get_df(
        f"""SELECT p.point_id, p.n1::bigint AS n1, p.n2::bigint AS n2,
                   p.n1_distance, p.n2_distance, p.edge_ogc_fid,
                   ST_X(ST_Transform(p.geom, 4326)) AS lon,
                   ST_Y(ST_Transform(p.geom, 4326)) AS lat,
                   ST_X(p.geom) AS px, ST_Y(p.geom) AS py,
                   g.grid_id, COALESCE(g.pop_est, 0) AS pop_est
            FROM urban_sample_points p
            JOIN {grid} g ON ST_Intersects(g.geom, p.geom)
            WHERE p.n1 IS NOT NULL""",
    )
    if pts.empty:
        sys.exit('No sample points joined to the population grid.')

    pts['quadrant'] = np.where(
        pts['py'] >= ymid,
        'N',
        'S',
    ) + np.where(pts['px'] >= xmid, 'E', 'W')

    per = max(1, n_points // 4)
    chosen = []
    for q in ['NW', 'NE', 'SW', 'SE']:
        sub = pts[pts['quadrant'] == q]
        if sub.empty:
            continue
        cells = sub.groupby('grid_id')['pop_est'].first()
        cells = cells[cells > 0]
        if cells.empty:  # quadrant with no population
            cells = sub.groupby('grid_id')['pop_est'].first() + 1
        k = min(per, len(cells))
        p = cells.to_numpy(dtype=float)
        picked = rng.choice(
            cells.index.to_numpy(),
            size=k,
            replace=False,
            p=p / p.sum(),
        )
        for gid in picked:
            cand = sub[sub['grid_id'] == gid]
            chosen.append(cand.iloc[rng.integers(len(cand))])
    out = pd.DataFrame(chosen).reset_index(drop=True)
    # top up (or trim) to the requested count if quadrants were uneven
    if len(out) > n_points:
        out = out.iloc[:n_points]
    out.insert(0, 'id', range(1, len(out) + 1))
    return out


# ------------------------------------------------------ connection legs
def _line_coords(gj):
    """Parse a GeoJSON string to a flat coordinate list; [] where there is no line.

    ``ST_LineSubstring`` degenerates to a POINT when the two ends coincide (an
    offset of zero), which is not drawable and needs no drawing.
    """
    if not gj:
        return []
    g = json.loads(gj)
    if g['type'] == 'LineString':
        return g['coordinates']
    if g['type'] == 'MultiLineString':
        return [c for part in g['coordinates'] for c in part]
    return []


def _orient(coords, anchor, first=True):
    """Order a leg's coordinates so the end nearest *anchor* comes first (or last)."""
    if len(coords) < 2:
        return coords
    d0 = (coords[0][0] - anchor[0]) ** 2 + (coords[0][1] - anchor[1]) ** 2
    d1 = (coords[-1][0] - anchor[0]) ** 2 + (coords[-1][1] - anchor[1]) ** 2
    return coords if (d0 <= d1) == first else coords[::-1]


def _substring_sql(point_expr, node_expr):
    """SQL for the sub-line of ``e.geom`` between a point on it and a terminal node."""
    a = f'ST_LineLocatePoint(e.geom, {point_expr})'
    b = f'ST_LineLocatePoint(e.geom, {node_expr})'
    return (
        f'ST_AsGeoJSON(ST_Transform(ST_LineSubstring(e.geom, '
        f'LEAST({a}, {b}), GREATEST({a}, {b})), 4326), {COORD_DP})'
    )


def origin_connectors(r, pts):
    """Along-edge geometry from each sample point to each of its terminal nodes.

    Sample points are generated *along* edges, and ``n1_distance``/``n2_distance``
    are measured along that edge -- so the leg the indicator charges for is this
    sub-line, not a straight line to the node.  Both terminals are exported because
    which one a route leaves by varies with the measure and the category.
    """
    ids = ','.join(str(int(i)) for i in pts['point_id'])
    df = r.get_df(
        f"""SELECT p.point_id,
                   {_substring_sql('p.geom', 'na.geom')} AS c1,
                   {_substring_sql('p.geom', 'nb.geom')} AS c2
            FROM urban_sample_points p
            JOIN edges e ON e.ogc_fid = p.edge_ogc_fid
            LEFT JOIN nodes na ON na.osmid = p.n1
            LEFT JOIN nodes nb ON nb.osmid = p.n2
            WHERE p.point_id IN ({ids})""",
    )
    return {
        int(row.point_id): {
            '1': _line_coords(row.c1),
            '2': _line_coords(row.c2),
        }
        for row in df.itertuples(index=False)
    }


def destination_details(r, spec, nodes):
    """The destination each route actually reached, keyed by its network node.

    The super-source seeds every destination node at its *minimum* offset, so the
    destination a route reached is the min-offset record attached to that node --
    resolved here the same way.  Returns its true location, the point at which it
    snaps onto the network, the along-edge leg from the node to that snap point
    (the offset the indicator charges), and the perpendicular hop from the snap
    point to the destination itself, which the indicator does *not* charge.
    """
    if not nodes:
        return {}
    layer, where = spec['layer'], spec.get('where') or 'TRUE'
    ids = ','.join(str(int(n)) for n in nodes)
    cand = ' UNION ALL '.join(
        f'SELECT d.ctid AS cid, d.{col}::bigint AS node, d.{off}::float AS off, '
        f'd.edge_ogc_fid, d.geom AS dgeom, d.match_point_geom AS mgeom, '
        f'COALESCE(d.match_point_distance, 0)::float AS snap '
        f'FROM {layer} d WHERE ({where}) AND d.{col} IN ({ids})'
        for col, off in (('n1', 'n1_distance'), ('n2', 'n2_distance'))
    )
    df = r.get_df(
        f"""WITH cand AS ({cand}),
                 pick AS (SELECT DISTINCT ON (node) *
                          FROM cand ORDER BY node, off, cid)
            SELECT k.node, k.off, k.snap,
                   ST_X(ST_Transform(k.dgeom, 4326)) AS lon,
                   ST_Y(ST_Transform(k.dgeom, 4326)) AS lat,
                   ST_X(ST_Transform(k.mgeom, 4326)) AS mlon,
                   ST_Y(ST_Transform(k.mgeom, 4326)) AS mlat,
                   {_substring_sql('k.mgeom', 'n.geom')} AS gj
            FROM pick k
            LEFT JOIN edges e ON e.ogc_fid = k.edge_ogc_fid
            LEFT JOIN nodes n ON n.osmid = k.node""",
    )
    out = {}
    for row in df.itertuples(index=False):
        mp = [
            round(float(row.mlon), COORD_DP),
            round(float(row.mlat), COORD_DP),
        ]
        out[int(row.node)] = {
            'lon': round(float(row.lon), COORD_DP),
            'lat': round(float(row.lat), COORD_DP),
            'mp': mp,
            # node -> snap point, in travel order
            'c': _orient(_line_coords(row.gj), mp, first=False),
            'off': round(float(row.off or 0), 1),
            'snap': round(float(row.snap or 0), 1),
        }
    return out


# ------------------------------------------------------- route reconstruction
def measure_graph(r, measure):
    """Load a measure's routable subgraph once, for reuse across categories."""
    m = MEASURES[measure]
    return load_network_graph(
        r,
        cost=m['cost'],
        reverse_cost=m['reverse_cost'],
        where=m['where'],
    )


def measure_tree(r, graph, node_ids, spec_name, origin_nodes):
    """Shortest-path tree from a super-source over *spec_name*'s destinations.

    Returns ``(paths, dists, node_ids)`` where ``paths[node]`` is the node
    sequence origin -> ... -> destination-node (absent if unreachable within
    MAX_BAND).
    """
    n = graph.shape[0]
    rows = r.get_df(
        f"SELECT dest_node, COALESCE(offset_m,0)::float AS offset_m "
        f"FROM {_DEST_TABLE} WHERE spec = '{spec_name}'",
    )
    if rows.empty:
        return {}, {}, node_ids
    # identity co-location, mirroring _nearest_distances_inmemory: a destination
    # sharing an origin's node is reachable at its offset with no edge traversal,
    # even where that node has no edges in *this* measure's subgraph (and so is
    # absent from node_ids entirely).  Without this the export would fall back to
    # the other terminal and report a longer route than the indicator recorded --
    # which the no-dismount measure makes common, since dropping the walked links
    # strands nodes whose every edge is one.
    at_node = rows.groupby('dest_node')['offset_m'].min()

    def _apply_colocated(paths, dists):
        """Credit origins that *are* a destination node at their offset."""
        for osmid in origin_nodes:
            off = at_node.get(osmid)
            if off is None or off > MAX_BAND:
                continue
            if osmid not in dists or off < dists[osmid]:
                dists[osmid] = float(off)
                paths[osmid] = [int(osmid)]  # no edge traversal
        return paths, dists

    pos = np.searchsorted(node_ids, rows['dest_node'].to_numpy('int64'))
    pos_c = np.clip(pos, 0, n - 1)
    in_graph = node_ids[pos_c] == rows['dest_node'].to_numpy('int64')
    if not in_graph.any():
        return (*_apply_colocated({}, {}), node_ids)
    seed = (
        pd.DataFrame(
            {
                'pos': pos_c[in_graph],
                'off': rows['offset_m'].to_numpy()[in_graph],
            },
        )
        .groupby('pos', as_index=False)['off']
        .min()
    )

    super_row = csr_matrix(
        (seed['off'], (np.zeros(len(seed), dtype=int), seed['pos'])),
        shape=(1, n),
    )
    aug = vstack(
        [
            hstack([graph, csr_matrix((n, 1))]),
            hstack([super_row, csr_matrix((1, 1))]),
        ],
        format='csr',
    )

    dist, pred = dijkstra(
        aug,
        directed=True,
        indices=n,
        limit=float(MAX_BAND) + 0.5,
        return_predecessors=True,
    )
    paths, dists = {}, {}
    for osmid in origin_nodes:
        i = int(np.searchsorted(node_ids, osmid))
        if (
            i >= n
            or node_ids[i] != osmid
            or not np.isfinite(dist[i])
            or dist[i] > MAX_BAND
        ):
            continue
        # walk predecessors: origin <- ... <- super-source (index n)
        seq, cur, guard = [], i, 0
        while cur != n and cur >= 0 and guard < 100000:
            seq.append(int(node_ids[cur]))
            cur = int(pred[cur])
            guard += 1
        if cur != n or len(seq) == 0:
            continue
        paths[osmid] = seq  # origin first, destination node last
        dists[osmid] = float(dist[i])
    return (*_apply_colocated(paths, dists), node_ids)


def fetch_edges(r, pairs, measure):
    """Edge attributes + WGS84 geometry for the (u,v) pairs *measure* routes over.

    Restricted to the measure's own subgraph (``MEASURES[measure]['where']``) and,
    where a node pair carries parallel edges, resolved to the one the router would
    have traversed — the cheapest under that measure's cost, matching
    ``load_network_graph``'s ``fmin(cost, reverse_cost)``.  A shared lookup keyed on
    the node pair alone gets this wrong wherever a rideable and a walk-only edge
    join the same two nodes (974 such pairs in Melbourne), drawing the walked edge's
    length, stress and dismount flag onto a ridden route.
    """
    if not pairs:
        return {}
    m = MEASURES[measure]
    cost, rcost = m['cost'], m['reverse_cost']
    both = pd.DataFrame(
        [(u, v) for u, v in pairs] + [(v, u) for u, v in pairs],
        columns=['u', 'v'],
    ).drop_duplicates()
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_PAIR_TABLE}'))
        conn.execute(
            text(
                f'CREATE TABLE {_PAIR_TABLE} (u bigint, v bigint)',
            ),
        )
    both.to_sql(_PAIR_TABLE, r.engine, if_exists='append', index=False)
    with r.engine.begin() as conn:
        conn.execute(text(f'CREATE INDEX ON {_PAIR_TABLE} (u, v)'))
    df = r.get_df(
        f'''SELECT e."from" AS u, e."to" AS v, e.length, e.cost_dist,
                   e.cost_lts, e.lvl_traf_stress, e.foot_dismount,
                   e.highway, e.name,
                   LEAST(e.{cost}, e.{rcost}) AS route_cost,
                   ST_AsGeoJSON(ST_Transform(e.geom, 4326), {COORD_DP}) AS gj
            FROM edges e
            JOIN {_PAIR_TABLE} p ON e."from" = p.u AND e."to" = p.v
            WHERE {m['where']}''',
    )
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_PAIR_TABLE}'))
    lookup = {}
    for row in df.itertuples(index=False):
        key = (min(row.u, row.v), max(row.u, row.v))
        prev = lookup.get(key)
        if prev is None or (row.route_cost or 0) < (prev['route_cost'] or 0):
            lookup[key] = {
                'length': row.length,
                'cost_dist': row.cost_dist,
                'cost_lts': row.cost_lts,
                'lts': row.lvl_traf_stress,
                'route_cost': row.route_cost,
                'dismount': bool(row.foot_dismount),
                'highway': row.highway,
                'name': row.name,
                'gj': row.gj,
            }
    return lookup


def fetch_nodes(r, osmids):
    """WGS84 positions of the nodes a route passes through.

    Edge geometry is *not* reliably digitised from the edge's "from" node to its
    "to" node, so the only sound way to emit segments in travel order is to orient
    each one against the node it is traversed from.
    """
    if not osmids:
        return {}
    ids = ','.join(str(int(n)) for n in osmids)
    df = r.get_df(
        f'SELECT osmid, ST_X(ST_Transform(geom, 4326)) AS lon, '
        f'ST_Y(ST_Transform(geom, 4326)) AS lat '
        f'FROM nodes WHERE osmid IN ({ids})',
    )
    return {
        int(row.osmid): [
            round(float(row.lon), COORD_DP),
            round(float(row.lat), COORD_DP),
        ]
        for row in df.itertuples(index=False)
    }


def _clean(v):
    """Convert pandas NA/NaN to None, so the result is JSON-serialisable."""
    return (
        None
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA
        else v
    )


def build_segments(seq, lookup, node_xy, cost_col):
    """Turn a node sequence into drawable segments with distances and costs.

    Coordinates are emitted in *travel* order, oriented against the node each edge
    is traversed from, so the exported route is a continuous chain and its last
    coordinate really is the end the route arrives at.
    """
    segs, total, cost_total, dismount = [], 0.0, 0.0, 0.0
    for a, b in zip(seq[:-1], seq[1:]):
        e = lookup.get((min(a, b), max(a, b)))
        if e is None or not e['gj']:
            continue
        geom = json.loads(e['gj'])
        coords = geom['coordinates']
        if geom['type'] == 'MultiLineString':
            coords = [c for part in coords for c in part]
        if a in node_xy:
            coords = _orient(coords, node_xy[a], first=True)
        length = float(e['length'] or 0)
        cost = float(e[cost_col] or length)
        total += length
        cost_total += cost
        if e['dismount']:
            dismount += length
        lts = _clean(e['lts'])
        segs.append(
            {
                'c': coords,
                'lts': int(lts) if lts is not None else None,
                'd': 1 if e['dismount'] else 0,
                'm': round(length, 1),
                'cm': round(cost, 1),
                'hw': _clean(e['highway']),
                'n': _clean(e['name']),
            },
        )
    return segs, round(total, 1), round(cost_total, 1), round(dismount, 1)


# ------------------------------------------------------------------- export
def export(codename, n_points, seed, outdir):  # noqa: C901
    r = ghsci.Region(codename)
    config = cycling_config(r)
    if config is None:
        sys.exit('cycling_indicators is not enabled for this region.')
    slug = slugify(r.name)
    outdir = outdir or f'/tmp/validation_tiles/{slug}'
    os.makedirs(outdir, exist_ok=True)

    specs = usable_destination_specs(
        r,
        config.get('destinations') or DEFAULT_DESTINATIONS,
    )
    by_name = {s['name']: s for s in specs}
    targets = []
    for t in TARGETS:
        name = next(
            (k for k in [t['key']] + t['fallbacks'] if k in by_name),
            None,
        )
        if name is None:
            print(f"  (no layer for {t['key']}; skipped)", flush=True)
            continue
        label = PT_FALLBACK_LABEL if name == 'pt_any' else t['label']
        targets.append(
            {
                'key': t['key'],
                'spec': name,
                'label': label,
                'fallback': name != t['key'],
            },
        )
    if not targets:
        sys.exit('None of the target destination categories are available.')

    measures = [m for m in MEASURE_ORDER if m in resolve_measures(config)]
    _ensure_node_associations(
        r,
        {by_name[t['spec']]['layer'] for t in targets},
    )
    _build_dest_table(r, [by_name[t['spec']] for t in targets])

    pts = sample_points(r, n_points, seed)
    conns = origin_connectors(r, pts)
    print(
        f'{r.name}: {len(pts)} sampled points, '
        f'{len(measures)} measures x {len(targets)} categories',
        flush=True,
    )

    origin_nodes = sorted(
        set(pts['n1'].dropna().astype('int64'))
        | set(pts['n2'].dropna().astype('int64')),
    )
    trees = {}
    for measure in measures:
        graph, node_ids = measure_graph(r, measure)  # once per measure
        for t in targets:
            paths, dists, _ = measure_tree(
                r,
                graph,
                node_ids,
                t['spec'],
                origin_nodes,
            )
            trees[(measure, t['key'])] = (paths, dists)
            print(
                f"  {measure} / {t['key']}: {len(paths)} origins reached",
                flush=True,
            )

    # geometry for every node any route visits, and — per measure, since parallel
    # edges resolve differently in each subgraph — for every edge it traverses
    pairs_by_measure, visited = {m: set() for m in measures}, set()
    for (measure, _cat), (paths, _) in trees.items():
        for seq in paths.values():
            pairs_by_measure[measure].update(
                (min(a, b), max(a, b)) for a, b in zip(seq[:-1], seq[1:])
            )
            visited.update(seq)
    n_pairs = len(set().union(*pairs_by_measure.values())) if measures else 0
    print(
        f'  fetching {n_pairs} distinct edges, {len(visited)} nodes',
        flush=True,
    )
    lookups = {m: fetch_edges(r, pairs_by_measure[m], m) for m in measures}
    node_xy = fetch_nodes(r, visited)

    routes, wanted = [], {t['key']: set() for t in targets}
    for _, p in pts.iterrows():
        # Terminal-node rule must match setup_sp.create_full_nodes exactly, or the
        # route shown would not be the one the indicator costed: a point sitting on
        # a node takes that node with no offset (even where the other terminal
        # would be cheaper -- which happens when the connecting edge is outside
        # this measure's subgraph, or when penalised costs break the triangle
        # inequality against geometric offsets); otherwise both terminals compete.
        d1 = float(p['n1_distance'] or 0)
        d2 = float(p['n2_distance']) if pd.notna(p['n2_distance']) else None
        # ``which`` is the terminal's 1/2 label, so the drawn connection leg is the
        # one this route actually left the sample point by
        if d1 == 0:
            terminals = [(int(p['n1']), 0.0, 1)]
        elif d2 == 0 and pd.notna(p['n2']):
            terminals = [(int(p['n2']), 0.0, 2)]
        else:
            terminals = [(int(p['n1']), d1, 1)]
            if pd.notna(p['n2']):
                terminals.append((int(p['n2']), d2, 2))
        for measure in measures:
            cost_col = MEASURES[measure]['cost']
            for t in targets:
                paths, dists = trees[(measure, t['key'])]
                best = None
                for node, offset, which in terminals:
                    if node in dists and (
                        best is None or dists[node] + offset < best[1]
                    ):
                        best = (node, dists[node] + offset, offset, which)
                if best is None:
                    routes.append(
                        {
                            'p': int(p['id']),
                            'cat': t['key'],
                            'meas': measure,
                            'ok': False,
                        },
                    )
                    continue
                seq = paths[best[0]]
                segs, total, cost_total, dismount = build_segments(
                    seq,
                    lookups[measure],
                    node_xy,
                    cost_col,
                )
                wanted[t['key']].add(seq[-1])
                routes.append(
                    {
                        'p': int(p['id']),
                        'cat': t['key'],
                        'meas': measure,
                        'ok': True,
                        'm': total,
                        'cm': cost_total,
                        'dm': dismount,
                        'net': round(best[1], 1),
                        't': best[3],
                        'to': round(best[2], 1),
                        'dnode': seq[-1],
                        'seg': segs,
                    },
                )

    # the destination each route reached, and the leg from the network to it
    for t in targets:
        details = destination_details(r, by_name[t['spec']], wanted[t['key']])
        for rt in routes:
            if rt['ok'] and rt['cat'] == t['key']:
                info = details.get(rt.pop('dnode'))
                if info is not None:
                    rt['dest'] = info

    out = {
        'name': r.name,
        'slug': slug,
        'codename': codename,
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'seed': seed,
        'n_points': len(pts),
        'sampling': (
            'quadrants of the urban study region; cells drawn with '
            'probability proportional to grid-cell population (PPS), '
            'one sample point per drawn cell'
        ),
        'max_band_m': MAX_BAND,
        'measures': [
            {
                'key': m,
                'label': MEASURES[m]['label'],
                'short': MEASURES[m]['short'],
            }
            for m in measures
        ],
        'categories': [
            {
                'key': t['key'],
                'label': t['label'],
                'spec': t['spec'],
                'fallback': t['fallback'],
            }
            for t in targets
        ],
        'points': [
            {
                'id': int(p['id']),
                'q': p['quadrant'],
                'lon': round(float(p['lon']), COORD_DP),
                'lat': round(float(p['lat']), COORD_DP),
                'pop': round(float(p['pop_est']), 1),
                # connection legs to each terminal node, in travel order from the point
                'conn': {
                    k: _orient(
                        v,
                        [
                            round(float(p['lon']), COORD_DP),
                            round(float(p['lat']), COORD_DP),
                        ],
                        first=True,
                    )
                    for k, v in conns.get(int(p['point_id']), {}).items()
                    if v
                },
            }
            for _, p in pts.iterrows()
        ],
        'routes': routes,
    }
    path = f'{outdir}/{slug}_routes.json'
    with open(path, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    reach = sum(1 for x in routes if x['ok'])
    print(
        f'  wrote {path} ({os.path.getsize(path) / 1e6:.1f} MB; '
        f'{reach}/{len(routes)} routes reachable)',
        flush=True,
    )


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('codename')
    ap.add_argument('--n-points', type=int, default=20)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--outdir', default=None)
    a = ap.parse_args()
    export(a.codename, a.n_points, a.seed, a.outdir)
