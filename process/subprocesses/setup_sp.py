"""
Define functions for spatial indicator analyses.

This module contains functions to set up sample points stats within study regions.
"""

import geopandas as gpd
import numpy
import numpy as np
import os
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import text
from tqdm import tqdm


def spatial_join_index_to_gdf(
    gdf,
    join_gdf,
    join_type='within',
    dropna=True,
):
    """Append to a geodataframe the named index of another using spatial join.

    Parameters
    ----------
    gdf: GeoDataFrame
    join_gdf: GeoDataFrame
    join_type: str (default 'within')
    dropna: True

    Returns
    -------
    GeoDataFrame
    """
    gdf_columns = list(gdf.columns)
    gdf = gpd.sjoin(gdf, join_gdf, how='left', predicate=join_type)
    if 'index_right' in gdf.columns:
        gdf = gdf.rename(columns={'index_right': join_gdf.index.name})
    gdf = gdf[gdf_columns + [join_gdf.index.name]]
    if dropna:
        gdf = gdf[~gdf[join_gdf.index.name].isna()]
        gdf[join_gdf.index.name] = gdf[join_gdf.index.name].astype(
            join_gdf.index.dtype,
        )
    return gdf


def filter_ids(df, query, message):
    """Pandas query designed to filter and report feedback on counts before and after query.

    Parameters
    ----------
    df: DataFrame
    query: str Pandas query string
    message: str An informative message to print describing query in plain language

    Returns
    -------
    DataFrame
    """
    print(message)
    pre_discard = len(df)
    df = df.query(query)
    post_discard = len(df)
    print(
        f'  {pre_discard - post_discard} sample points discarded, '
        f'leaving {post_discard} remaining.',
    )
    return df


_DEST_LOOKUP_TABLE = '_dest_node_lookup'


def _run_lookup_batch(
    engine,
    batch_osmids,
    distance,
    edge_table='edges',
    cost='length',
    reverse_cost='length',
    where=None,
):
    """Insert pgr_drivingDistance results for one batch of seed nodes into _dest_node_lookup.

    Uses a spatially filtered edge subgraph restricted to edges whose bounding box
    intersects a buffer of `distance` metres around the batch seed nodes, so pgRouting
    works on a small local graph rather than the full city network.  Safe to call from
    multiple threads concurrently; each invocation acquires its own connection from the
    SQLAlchemy pool.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine (thread-safe connection pool).
    batch_osmids : list of int
        OSM node IDs ("from"/"to" values) to use as pgr_drivingDistance seed nodes.
    distance : int or float
        Maximum network search distance in metres.
    """
    array_literal = 'ARRAY[' + ','.join(str(x) for x in batch_osmids) + ']::bigint[]'
    # "from"/"to" are the osmid bigints used to derive n1/n2 in destination tables —
    # the correct node ID space for the seed array and for start_vid/node in the result.
    # ogc_fid is the SERIAL PRIMARY KEY on edges, avoiding row_number() OVER ().
    # The && operator hits the edges_geom_idx GiST index for a fast spatial pre-filter.
    where_sql = f' AND ({where})' if where else ''
    edge_sql = (
        f'SELECT e.ogc_fid AS id, e."from" AS source, e."to" AS target, '
        f'e.{cost}::float AS cost, e.{reverse_cost}::float AS reverse_cost '
        f'FROM {edge_table} e '
        f'WHERE e.geom && ('
        f'  SELECT ST_Expand(ST_Collect(n.geom), {distance}) '
        f'  FROM nodes n WHERE n.osmid = ANY({array_literal})){where_sql}'
    )
    insert_sql = (
        f'INSERT INTO {_DEST_LOOKUP_TABLE} (start_vid, node, dist) '
        f'SELECT start_vid::bigint, node::bigint, agg_cost::float '
        f'FROM pgr_drivingDistance($edge${edge_sql}$edge$, {array_literal}, {distance}, false)'
    )
    with engine.begin() as conn:
        conn.execute(text(insert_sql))


def _run_lookup_batch_no_filter(
    engine,
    batch_osmids,
    distance,
    edge_table='edges',
    cost='length',
    reverse_cost='length',
    where=None,
):
    """Insert pgr_drivingDistance results using the full edge table (no spatial filter).

    Fallback for seed nodes that were silently skipped by pgRouting in the
    spatial-filter pass (e.g. nodes whose osmid did not appear as "from"/"to" in
    any edge that intersected the batch bounding box).  Runs on the complete edge
    table so no seed can be missed.  Only called for the small residual set of
    missing seeds, so the performance cost is acceptable.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine.
    batch_osmids : list of int
        OSM node IDs to seed pgr_drivingDistance.
    distance : int or float
        Maximum network search distance in metres.
    """
    array_literal = 'ARRAY[' + ','.join(str(x) for x in batch_osmids) + ']::bigint[]'
    where_sql = f' WHERE {where}' if where else ''
    edge_sql = (
        f'SELECT e.ogc_fid AS id, e."from" AS source, e."to" AS target, '
        f'e.{cost}::float AS cost, e.{reverse_cost}::float AS reverse_cost '
        f'FROM {edge_table} e{where_sql}'
    )
    insert_sql = (
        f'INSERT INTO {_DEST_LOOKUP_TABLE} (start_vid, node, dist) '
        f'SELECT start_vid::bigint, node::bigint, agg_cost::float '
        f'FROM pgr_drivingDistance($edge${edge_sql}$edge$, {array_literal}, {distance}, false)'
    )
    with engine.begin() as conn:
        conn.execute(text(insert_sql))


def build_dest_node_lookup(
    r,
    active_layers,
    distance,
    batch_size=500,
    n_workers=None,
    edge_table='edges',
    cost='length',
    reverse_cost='length',
    where=None,
):
    """Pre-compute network distances from all destination nodes to reachable nodes.

    Creates (or replaces) a PostgreSQL table '_dest_node_lookup' by running
    pgr_drivingDistance in batches over seed nodes drawn from the n1/n2 columns of
    all active destination layers.  Each batch uses a spatially filtered edge subgraph
    restricted to edges within `distance` metres of the batch seeds, so pgRouting
    processes a small local graph instead of the full city network.  Seeds are ordered
    spatially before batching so each batch covers a compact geographic cluster,
    keeping the spatial filter tight and the edge subgraph small.  Progress is reported
    via tqdm.  Batches may run in parallel across multiple database connections when
    n_workers > 1.

    Parameters
    ----------
    r : Region
    active_layers : set or list of str
        Names of destination tables that have n1/n2 columns.
    distance : int or float
        Maximum search distance in metres.
    batch_size : int
        Number of seed nodes per pgr_drivingDistance call (default 500).
    n_workers : int or None
        Worker threads for parallel batch execution.  None auto-detects as
        min(4, cpu_count // 2), falling back to 1 if cpu_count is unavailable.
    edge_table : str
        Routable edge table to query (default 'edges').
    cost, reverse_cost : str
        Edge columns used as forward / reverse traversal cost (default 'length').
        Routing is undirected, so both are supplied to pgr_drivingDistance.
    where : str or None
        Optional SQL condition restricting the edge subgraph, e.g. for cycling
        'lvl_traf_stress <= 2 AND bike_permitted'.

    Returns
    -------
    bool
        True on success; False if no active layers or no seed nodes found.
    """
    if not active_layers:
        print('  WARNING: no active destination layers found; skipping lookup table build.')
        return False

    if n_workers is None:
        cpu_count = os.cpu_count() or 1
        n_workers = max(1, min(4, cpu_count // 2))

    # Fetch unique seed osmids from all active destination layers into Python
    union_parts = (
        [f'SELECT n1::bigint AS osmid FROM {layer} WHERE n1 IS NOT NULL'
         for layer in sorted(active_layers)]
        + [f'SELECT n2::bigint AS osmid FROM {layer} WHERE n2 IS NOT NULL'
           for layer in sorted(active_layers)]
    )
    # Join to nodes to get geometry, then order spatially so consecutive seeds are
    # geographically close.  This keeps the ST_Expand bounding box tight for each
    # batch, limiting the edge subgraph pgRouting must load.
    # The inner SELECT includes the sort columns so DISTINCT + ORDER BY is valid.
    seeds_sql = (
        f'SELECT osmid FROM ('
        f'  SELECT DISTINCT s.osmid, ST_X(n.geom) AS _x, ST_Y(n.geom) AS _y '
        f'  FROM ({" UNION ALL ".join(union_parts)}) s '
        f'  JOIN nodes n ON n.osmid = s.osmid'
        f') _seeds ORDER BY _x, _y'
    )
    seed_df = r.get_df(seeds_sql)
    if seed_df is None or seed_df.empty:
        print('  WARNING: no seed nodes returned; skipping lookup table build.')
        return False
    seed_osmids = seed_df['osmid'].astype('int64').tolist()

    batches = [seed_osmids[i:i + batch_size] for i in range(0, len(seed_osmids), batch_size)]
    n_batches = len(batches)
    print(
        f'  {len(seed_osmids)} seed nodes \u2192 {n_batches} batches '
        f'(batch_size={batch_size}, workers={n_workers})',
    )

    # Create the lookup table upfront with an explicit schema so concurrent INSERTs are safe.
    # UNLOGGED: this is transient scratch data (rebuilt on demand, dropped after use), so
    # skipping WAL avoids gigabytes of write amplification on large cities (measured 15 GB
    # for Dar es Salaam) with no reliability cost — on a crash the analysis step re-runs.
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_DEST_LOOKUP_TABLE}'))
        conn.execute(text(
            f'CREATE UNLOGGED TABLE {_DEST_LOOKUP_TABLE} (start_vid bigint, node bigint, dist float)'
        ))

    if n_workers == 1 or n_batches == 1:
        for batch in tqdm(batches, unit='batch'):
            _run_lookup_batch(
                r.engine, batch, distance, edge_table, cost, reverse_cost, where,
            )
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = [
                executor.submit(
                    _run_lookup_batch, r.engine, batch, distance,
                    edge_table, cost, reverse_cost, where,
                )
                for batch in batches
            ]
            for future in tqdm(
                as_completed(futures),
                total=n_batches,
                unit='batch',
            ):
                future.result()  # re-raise any exception from the worker thread

    # Mop-up pass: find seeds that pgRouting silently skipped because their osmid
    # did not appear as source/target in any edge that passed the spatial filter.
    # These are processed with the full edge table to guarantee complete coverage.
    with r.engine.connect() as conn:
        found_seeds = {row[0] for row in conn.execute(
            text(f'SELECT DISTINCT start_vid FROM {_DEST_LOOKUP_TABLE}')
        )}
    missing_seeds = [s for s in seed_osmids if s not in found_seeds]
    if missing_seeds:
        print(f'  {len(missing_seeds)} seeds missing from lookup; running fallback pass...')
        fallback_batches = [
            missing_seeds[i:i + batch_size]
            for i in range(0, len(missing_seeds), batch_size)
        ]
        for batch in tqdm(
            fallback_batches,
            desc='  pgr_drivingDistance (fallback)',
            unit='batch',
        ):
            _run_lookup_batch_no_filter(
                r.engine, batch, distance, edge_table, cost, reverse_cost, where,
            )
    else:
        print('  All seeds covered.')

    with r.engine.begin() as conn:
        conn.execute(text(f'CREATE INDEX ON {_DEST_LOOKUP_TABLE} (start_vid)'))
        # ANALYZE the freshly bulk-loaded + indexed table so the planner has row-count
        # and distribution statistics before the downstream aggregation joins.  Without
        # it the planner flies blind and can pick a catastrophic plan for the strict
        # component join (measured: a single pass 340s -> 0.3s with ANALYZE).
        conn.execute(text(f'ANALYZE {_DEST_LOOKUP_TABLE}'))

    return True


def _dist_from_lookup(r, layer, where_clause, node_index, col_name):
    """Compute per-network-node minimum distance to the nearest POI via SQL JOIN.

    Joins the pre-built '_dest_node_lookup' PostgreSQL table against the
    layer's n1/n2 columns, adds per-destination offsets, and returns the minimum
    adjusted distance per network node.  All aggregation runs in PostgreSQL;
    only the compact (osmid, dist) result is fetched into Python.

    Parameters
    ----------
    r : Region
    layer : str
        Name of the destination PostGIS table.
    where_clause : str
        SQL WHERE condition (without 'WHERE' keyword), or '' for unfiltered.
    node_index : Index
        Full ordered index of network node osmids (sets -999 defaults).
    col_name : str
        Name for the returned Series.

    Returns
    -------
    Series indexed by osmid; -999 for nodes outside the distance threshold.
    """
    default = pd.Series(-999.0, index=node_index, name=col_name)
    cond = f'WHERE {where_clause}' if where_clause else ''
    sql = (
        f'SELECT l.node::bigint AS osmid, MIN(l.dist + p.offset)::float AS dist '
        f'FROM {_DEST_LOOKUP_TABLE} l '
        f'JOIN ('
        f'  SELECT n1::bigint AS start_vid, n1_distance::float AS offset FROM {layer} {cond} '
        f'  UNION ALL '
        f'  SELECT n2::bigint AS start_vid, n2_distance::float AS offset FROM {layer} {cond}'
        f') p ON l.start_vid = p.start_vid '
        f'GROUP BY l.node'
    )
    # get_df swallows driver exceptions and returns None; a transient failure here
    # must NOT silently default distances to -999 — that fabricates "nothing within
    # reach", drops derived layers (e.g. activity centres) and corrupts results
    # downstream (observed intermittently with the ADBC driver).  Retry on a fresh
    # connection; if the query persistently fails, fail the run loudly instead.
    import time as _time

    result = None
    for attempt in range(3):
        result = r.get_df(sql)
        if result is not None:
            break
        print(
            f'  WARNING: _dist_from_lookup query failed for {col_name} ({layer}); '
            f'retrying ({attempt + 1}/3)...',
        )
        _time.sleep(2)
    if result is None:
        raise RuntimeError(
            f'_dist_from_lookup: query failed after 3 attempts for {col_name} '
            f'({layer}); refusing to silently default distances to -999.',
        )
    if len(result) == 0:
        return default
    result = result.dropna(subset=['osmid'])
    if result.empty:
        return default
    result['osmid'] = result['osmid'].astype('int64')
    result['dist'] = result['dist'].astype(float)
    series = result.set_index('osmid')['dist']
    series.name = col_name
    default.update(series)
    return default


def cal_dist_node_to_nearest_pois(
    r,
    layer,
    node_index,
    category_field=None,
    categories=None,
    filter_field=None,
    filter_iterations=None,
    output_names=None,
    output_prefix='',
):
    """Calculate the distance from each network node to the nearest POI within the distance threshold.

    Queries the pre-built '_dest_node_lookup' PostgreSQL table via SQL JOINs so
    that the expensive pgr_drivingDistance result stays in the database.
    Per-analysis aggregation (offset addition, MIN grouping) runs in PostgreSQL;
    only the compact result is fetched into Python by _dist_from_lookup.

    Parameters
    ----------
    r : Region
        Study region object providing database connection
    layer : str
        Name of the PostGIS table containing the destination points-of-interest
    node_index : Index
        Full ordered index of network node osmids.
    category_field : str, optional
        Field to filter POI rows by values in the categories list
    categories : list, optional
        List of category values found in category_field
    filter_field : str, optional
        Field to filter POI rows using SQL-compatible expressions from filter_iterations
    filter_iterations : list, optional
        List of SQL-compatible filter expressions applied to filter_field (e.g. ['>=0', '<=30'])
    output_names : list, optional
        Names for output columns (must match order of categories or filter_iterations)
    output_prefix : str
        Prefix to prepend to output_names (default '')

    Returns
    -------
    DataFrame
        Indexed by osmid, one column per category/iteration, distances in metres or -999
    """
    columns = nearest_poi_query_columns(
        category_field=category_field,
        categories=categories,
        filter_field=filter_field,
        filter_iterations=filter_iterations,
        output_names=output_names,
        output_prefix=output_prefix,
    )
    return pd.concat(
        [
            _dist_from_lookup(r, layer, where_clause, node_index, col_name)
            for col_name, where_clause in columns
        ],
        axis=1,
    )


def drop_dest_node_lookup(r):
    """Drop the temporary destination-node distance lookup table if it exists."""
    with r.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {_DEST_LOOKUP_TABLE}'))


def graph_from_edge_arrays(u, v, w):
    """Build an undirected min-cost sparse graph from edge endpoint/weight arrays.

    Matches ``pgr_drivingDistance(..., directed := false)`` semantics: every edge is
    traversable both ways, and parallel edges between the same node pair reduce to
    the cheapest.  Returns ``(csr_matrix, node_ids)`` where ``node_ids`` is the
    sorted array mapping graph index -> network osmid.
    """
    from scipy.sparse import csr_matrix

    u = np.asarray(u, dtype='int64')
    v = np.asarray(v, dtype='int64')
    w = np.asarray(w, dtype='float64')
    node_ids = np.unique(np.concatenate([u, v]))
    u = np.searchsorted(node_ids, u)
    v = np.searchsorted(node_ids, v)
    # canonicalise parallel edges to their minimum weight, then emit both arcs so a
    # directed Dijkstra behaves as the undirected minimum-cost graph
    lo, hi = np.minimum(u, v), np.maximum(u, v)
    pairs = pd.DataFrame({'lo': lo, 'hi': hi, 'w': w}).groupby(
        ['lo', 'hi'], as_index=False,
    )['w'].min()
    n = len(node_ids)
    graph = csr_matrix(
        (
            np.concatenate([pairs['w'], pairs['w']]),
            (
                np.concatenate([pairs['lo'], pairs['hi']]),
                np.concatenate([pairs['hi'], pairs['lo']]),
            ),
        ),
        shape=(n, n),
    )
    return graph, node_ids


def load_network_graph(
    r,
    edge_table='edges',
    cost='length',
    reverse_cost='length',
    where=None,
):
    """Load a routable subgraph as an undirected min-cost sparse matrix.

    Matches ``pgr_drivingDistance(..., directed := false)`` semantics: every edge is
    traversable both ways, and where cost and reverse_cost differ (or parallel edges
    exist between the same node pair) the cheapest applies.  Returns
    ``(csr_matrix, node_ids)`` where ``node_ids`` is the sorted array mapping graph
    index -> network osmid.
    """
    cols = f'"from" AS u, "to" AS v, {cost}::float AS cost'
    if reverse_cost != cost:
        cols += f', {reverse_cost}::float AS reverse_cost'
    where_sql = f' WHERE {where}' if where else ''
    edges = r.get_df(f'SELECT {cols} FROM {edge_table}{where_sql}')
    w = edges['cost'].to_numpy('float64')
    if 'reverse_cost' in edges.columns:
        w = np.fmin(w, edges['reverse_cost'].to_numpy('float64'))
    return graph_from_edge_arrays(
        edges['u'].to_numpy('int64'), edges['v'].to_numpy('int64'), w,
    )


def neighbourhood_reachable_nodes(
    graph,
    node_ids,
    source_ids,
    distance,
    chunk_size=None,
    progress=True,
):
    """Per source node: the graph nodes reachable within ``distance``, nearest first.

    In-memory equivalent of ``networkx.all_pairs_dijkstra_path_length(G, cutoff)``
    restricted to the requested sources: for each source, yields the array of node
    osmids whose shortest-path distance is <= ``distance`` (inclusive, matching the
    networkx cutoff), ordered by increasing distance -- the order in which
    networkx's Dijkstra discovers them (ties may order differently).  A source
    absent from the graph (a node with no edges) yields just itself, as networkx
    returns the source at distance zero.

    Parameters
    ----------
    graph : csr_matrix
        Undirected min-cost graph from graph_from_edge_arrays.
    node_ids : ndarray
        Sorted osmids mapping graph index -> network node.
    source_ids : ndarray
        Node osmids to compute neighbourhoods for (yields follow this order).
    distance : int or float
        Maximum network distance in metres (inclusive).
    chunk_size : int or None
        Sources per scipy dijkstra call; None auto-sizes to bound the dense
        per-chunk distance matrix at ~300 MB.
    progress : bool
        Show a tqdm progress bar over sources.

    Yields
    ------
    ndarray of node osmids per source, nearest first.
    """
    from scipy.sparse.csgraph import dijkstra

    n = graph.shape[0]
    if chunk_size is None:
        chunk_size = int(max(64, min(4096, 4e7 // max(n, 1))))
    source_ids = np.asarray(source_ids, dtype='int64')
    pos = np.searchsorted(node_ids, source_ids)
    pos_clipped = np.clip(pos, 0, max(n - 1, 0))
    in_graph = (
        node_ids[pos_clipped] == source_ids
        if n
        else np.zeros(len(source_ids), bool)
    )
    iterator = range(0, len(source_ids), chunk_size)
    if progress:
        iterator = tqdm(
            iterator,
            total=(len(source_ids) + chunk_size - 1) // chunk_size,
            unit='chunk',
        )
    # 0.5 m exploration guard so nodes at exactly the cutoff are visited (the
    # networkx cutoff is inclusive); exact values are kept, then masked
    limit = float(distance) + 0.5
    for start in iterator:
        chunk_pos = pos_clipped[start:start + chunk_size]
        chunk_in_graph = in_graph[start:start + chunk_size]
        dist_chunk = dijkstra(
            graph, directed=True, indices=chunk_pos, limit=limit,
        )
        for row, source, present in zip(
            dist_chunk, source_ids[start:start + chunk_size], chunk_in_graph,
        ):
            if not present:
                yield np.array([source], dtype='int64')
                continue
            within = np.flatnonzero(row <= distance)
            order = np.argsort(row[within], kind='stable')
            yield node_ids[within[order]]


def nearest_poi_query_columns(
    category_field=None,
    categories=None,
    filter_field=None,
    filter_iterations=None,
    output_names=None,
    output_prefix='',
):
    """Resolve a nearest-node analysis to its (column name, SQL WHERE clause) pairs.

    Single source of truth for how an analysis' categories / filter iterations map
    to output columns and destination-layer SQL filters, shared by the pgRouting
    engine (cal_dist_node_to_nearest_pois) and the in-memory engine
    (cal_dist_nodes_to_nearest_pois_inmemory) so the two cannot drift.

    Returns
    -------
    list of (col_name, where_clause) tuples; where_clause is '' for unfiltered.
    """
    if category_field is not None and categories is not None:
        if output_names is None:
            output_names = categories
        return [
            (
                f'{output_prefix}{output_names[categories.index(x)]}',
                f"""{category_field} = '{str(x).replace("'", "''")}'""",
            )
            for x in categories
        ]
    elif filter_field is not None and filter_iterations is not None:
        if output_names is None:
            output_names = filter_iterations
        return [
            (
                f'{output_prefix}{output_names[filter_iterations.index(x)]}',
                f"{filter_field} {str(x).replace('==', '=')}",
            )
            for x in filter_iterations
        ]
    else:
        if output_names is None:
            output_names = ['POI']
        return [(f'{output_prefix}{output_names[0]}', '')]


def _nearest_poi_distances_from_graph(
    graph,
    node_ids,
    column_seeds,
    distance,
    chunk_size=None,
    progress=True,
):
    """Exact in-memory equivalent of the destination-node lookup + per-column MIN join.

    Reproduces the pgRouting semantics precisely: network distances from every seed
    (destination node) are capped at ``distance`` (inclusive, as
    ``pgr_drivingDistance``) BEFORE the per-destination offset is added, so -- exactly
    like ``MIN(l.dist + p.offset)`` over the lookup table -- reported minima may exceed
    ``distance`` by up to the offset, and a nearer-in-total pair whose network leg
    exceeds the cap is excluded.  (A super-source formulation, as used by the cycling
    engine where thresholds apply to the total, would cap the total instead and could
    differ in the above-threshold tail.)

    Seeds are routed once each (chunked multi-seed Dijkstra), however many columns
    they appear in, mirroring the shared lookup table.

    Parameters
    ----------
    graph : csr_matrix
        Undirected min-cost graph from load_network_graph.
    node_ids : ndarray
        Sorted osmids mapping graph index -> network node.
    column_seeds : dict
        col_name -> DataFrame with columns ``dest_node`` (osmid) and ``offset``
        (metres).  Rows whose dest_node is not a graph vertex are ignored (such a
        node appears in no edge, so pgRouting never returns it either).
    distance : int or float
        Network-distance cap in metres.
    chunk_size : int or None
        Seeds routed per scipy dijkstra call; None auto-sizes to bound the dense
        per-chunk distance matrix at ~300 MB.
    progress : bool
        Show a tqdm progress bar over chunks.

    Returns
    -------
    dict of col_name -> ndarray aligned to node_ids; np.inf where no destination's
    network leg is within ``distance``.
    """
    from scipy.sparse.csgraph import dijkstra

    n = graph.shape[0]
    if chunk_size is None:
        chunk_size = int(max(64, min(4096, 4e7 // max(n, 1))))

    results = {col: np.full(n, np.inf) for col in column_seeds}
    # per-column seed graph positions with the minimum offset per seed (the SQL MIN
    # over duplicate (column, seed) pairs)
    col_entries = {}
    all_seed_positions = []
    for col, rows in column_seeds.items():
        if rows is None or len(rows) == 0:
            col_entries[col] = (
                np.array([], dtype='int64'), np.array([], dtype='float64'),
            )
            continue
        rows = rows.dropna(subset=['dest_node', 'offset'])
        dest = rows['dest_node'].to_numpy('int64')
        pos = np.searchsorted(node_ids, dest)
        pos_clipped = np.clip(pos, 0, max(n - 1, 0))
        in_graph = (
            node_ids[pos_clipped] == dest if n else np.zeros(len(dest), bool)
        )
        dedup = (
            pd.DataFrame(
                {
                    'pos': pos_clipped[in_graph],
                    'off': rows['offset'].to_numpy('float64')[in_graph],
                },
            )
            .groupby('pos', as_index=False)['off']
            .min()
        )
        col_entries[col] = (
            dedup['pos'].to_numpy('int64'), dedup['off'].to_numpy('float64'),
        )
        if len(dedup):
            all_seed_positions.append(col_entries[col][0])
    if not all_seed_positions:
        return results
    seed_positions = np.unique(np.concatenate(all_seed_positions))

    # 0.5 m exploration guard so nodes at exactly the cap are visited
    # (pgr_drivingDistance's agg_cost <= distance is inclusive); exact values are
    # kept, then everything beyond the cap is masked out
    limit = float(distance) + 0.5
    starts = range(0, len(seed_positions), chunk_size)
    if progress:
        starts = tqdm(
            starts,
            total=(len(seed_positions) + chunk_size - 1) // chunk_size,
            unit='chunk',
        )
    for start in starts:
        chunk = seed_positions[start:start + chunk_size]
        dist_chunk = dijkstra(graph, directed=True, indices=chunk, limit=limit)
        dist_chunk[dist_chunk > distance] = np.inf  # the network-distance cap
        for col, (pos, off) in col_entries.items():
            sel = np.searchsorted(chunk, pos)
            sel_clipped = np.clip(sel, 0, len(chunk) - 1)
            in_chunk = chunk[sel_clipped] == pos
            out = results[col]
            for row, offset in zip(sel_clipped[in_chunk], off[in_chunk]):
                np.minimum(out, dist_chunk[row] + offset, out=out)
    return results


def cal_dist_nodes_to_nearest_pois_inmemory(
    r,
    layer_columns,
    distance,
    node_index,
    edge_table='edges',
    cost='length',
    reverse_cost='length',
    where=None,
    chunk_size=None,
):
    """In-memory engine: nearest-POI distances for every network node, all columns at once.

    Drop-in equivalent of build_dest_node_lookup + per-analysis
    cal_dist_node_to_nearest_pois, computed with scipy sparse Dijkstra instead of
    pgr_drivingDistance.  Destination WHERE clauses are still evaluated by
    PostgreSQL (identical clause text via nearest_poi_query_columns), and the
    network-distance cap is applied before destination offsets are added, so the
    results match the pgRouting engine exactly.

    Parameters
    ----------
    r : Region
    layer_columns : list of (layer, col_name, where_clause)
        One entry per output column, where_clause as produced by
        nearest_poi_query_columns ('' for unfiltered).
    distance : int or float
        Maximum network search distance in metres.
    node_index : Index
        Full ordered index of network node osmids (sets -999 defaults).
    edge_table, cost, reverse_cost, where :
        Routable graph selection, as for build_dest_node_lookup.
    chunk_size : int or None
        Seeds per Dijkstra call (None auto-sizes to bound memory).

    Returns
    -------
    DataFrame indexed by node_index, one column per layer_columns entry (in
    order); -999 where no destination's network leg is within ``distance``.
    """
    graph, node_ids = load_network_graph(
        r, edge_table, cost, reverse_cost, where,
    )
    column_seeds = {}
    for layer, col_name, where_clause in layer_columns:
        cond = f'WHERE {where_clause} ' if where_clause else ''
        column_seeds[col_name] = r.get_df(
            f'SELECT n1::bigint AS dest_node, n1_distance::float AS "offset" '
            f'FROM {layer} {cond}'
            f'UNION ALL '
            f'SELECT n2::bigint, n2_distance::float FROM {layer} {cond}',
        )
    results = _nearest_poi_distances_from_graph(
        graph, node_ids, column_seeds, distance, chunk_size,
    )
    columns = []
    for layer, col_name, where_clause in layer_columns:
        default = pd.Series(-999.0, index=node_index, name=col_name)
        vals = results[col_name]
        finite = np.isfinite(vals)
        if finite.any():
            default.update(
                pd.Series(vals[finite], index=node_ids[finite], name=col_name),
            )
        columns.append(default)
    return pd.concat(columns, axis=1)


def create_full_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    density_statistics,
):
    """Create long form working dataset of sample points to evaluate respective node distances and densities.

    This is achieved by first allocating sample points coincident with nodes their direct estimates, and then through a sub-function process_distant_nodes() deriving estimates for sample points based on terminal nodes of the edge segments on which they are located, accounting for respective distances.

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    density_statistics: list
        list of density statistic sample point indicator names

    Returns
    -------
    GeoDataFrame
    """
    print(
        'Derive sample point estimates for accessibility and densities based on node distance relations',
    )
    simple_nodes = gdf_nodes_poi_dist.join(gdf_nodes_simple)
    print(
        '\t - match sample points whose locations coincide with intersections directly with intersection record data',
    )
    coincident_nodes = (
        pd.concat(
            [
                samplePointsData.query('n1_distance==0')[['n1']].rename(
                    {'n1': 'node'},
                    axis='columns',
                ),
                samplePointsData.query('n1_distance!=0 and n2_distance==0')[
                    ['n2']
                ].rename({'n2': 'node'}, axis='columns'),
            ],
        )
        .join(simple_nodes, on='node', how='left')[
            [
                x
                for x in simple_nodes.columns
                if x not in ['grid_id', 'geometry']
            ]
        ]
        .copy()
    )
    distant_nodes = process_distant_nodes(
        samplePointsData,
        gdf_nodes_simple,
        gdf_nodes_poi_dist,
        density_statistics,
    )
    full_nodes = pd.concat([coincident_nodes, distant_nodes]).sort_index()
    return full_nodes


def process_distant_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    density_statistics,
):
    """Create long form working dataset of sample points to evaluate respective node distances and densities.

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    density_statistics: list
        list of density statistic sample point indicator names

    Returns
    -------
    GeoDataFrame
    """
    print(
        '\t - for sample points not co-located with intersections, derive estimates by:',
    )
    print('\t\t - accounting for distances')
    distant_nodes = samplePointsData.query(
        'n1_distance!=0 and n2_distance!=0',
    )[['n1', 'n2', 'n1_distance', 'n2_distance']].copy()
    distant_nodes['nodes'] = distant_nodes.apply(
        lambda x: [[int(x.n1), x.n1_distance], [int(x.n2), x.n2_distance]],
        axis=1,
    )
    distant_nodes = distant_nodes[['nodes']].explode('nodes')
    distant_nodes[['node', 'node_distance_m']] = pd.DataFrame(
        distant_nodes.nodes.values.tolist(),
        index=distant_nodes.index,
    )
    distant_nodes = distant_nodes[['node', 'node_distance_m']].join(
        gdf_nodes_poi_dist,
        on='node',
        how='left',
    )
    distance_fields = []
    for d in list(gdf_nodes_poi_dist.columns):
        distant_nodes[d] = distant_nodes[d] + distant_nodes['node_distance_m']
        distance_fields.append(d)

    print(
        '\t\t - calculating proximity-weighted average of density statistics for each sample point',
    )
    # define aggregation functions for per sample point estimates
    # ie. we take
    #       - minimum of full distances
    #       - and weighted mean of densities
    # The latter is so that if distance from two nodes for a point are 10m and 30m
    #  the weight of 10m is 0.75 and the weight of 30m is 0.25.
    #  ie. 1 - (10/(10+30)) = 0.75    , and 1 - (30/(10+30)) = 0.25
    # ie. the more proximal node is the dominant source of the density estimate, but the distal one still has
    # some contribution to ensure smooth interpolation across sample points (ie. a 'best guess' at true value).
    # This is not perfect; ideally the densities would be calculated for the sample points directly.
    # But it is better than just assigning the value of the nearest node (which may be hundreds of metres away).
    #
    # An important exceptional case which needs to be accounted for is a sample point co-located with a node
    # intersection which is the beginning and end of a cul-de-sac loop.  In such a case, n1 and n2 are identical,
    # and the distance to each is zero, which therefore results in a division by zero error. To resolve this issue,
    # and a general rule of efficiency, if distance to any node is zero that nodes esimates shall be employed directly.
    # This is why the weighting and full distance calculation is only considered for sample points with "distant nodes",
    # and not those with "coincident nodes".

    node_weight_denominator = (
        distant_nodes['node_distance_m'].groupby(distant_nodes.index).sum()
    )
    distant_nodes = distant_nodes[
        ['node', 'node_distance_m'] + distance_fields
    ].join(node_weight_denominator, how='left', rsuffix='_denominator')
    distant_nodes['density_weight'] = 1 - (
        distant_nodes['node_distance_m']
        / distant_nodes['node_distance_m_denominator']
    )
    # join up full nodes with density fields
    distant_nodes = distant_nodes.join(
        gdf_nodes_simple[density_statistics],
        on='node',
        how='left',
    )
    for statistic in density_statistics:
        distant_nodes[statistic] = (
            distant_nodes[statistic] * distant_nodes.density_weight
        )
    agg_functions = dict(
        zip(
            distance_fields + density_statistics,
            ['min'] * len(distance_fields) + ['sum'] * len(density_statistics),
        ),
    )
    distant_nodes = distant_nodes.groupby(distant_nodes.index).agg(
        agg_functions,
    )
    return distant_nodes


# Cumulative opportunities (binary)
# 1 if d <= access_dist
# 0 if d > access_dist
def binary_access_score(df, distance_names, threshold=500):
    """Calculate accessibiity score using binary measure.

    1 if access <= access_dist, 0 otherwise.

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of original distance field names
    threshold: int
        access distance threshold, default is 500 meters

    Returns
    -------
    DataFrame
    """
    df1 = (df[distance_names] <= threshold).fillna(False).astype(int)
    # If any of distance_names were all null in DF, should be returned as all null
    nulls = df[distance_names].isnull().all()
    df1[nulls.index[nulls]] = np.nan
    return df1


# Soft threshold access score
# Higgs, C., Badland, H., Simons, K. et al. (2019) The Urban Liveability Index
def soft_access_score(df, distance_names, threshold=500, k=5):
    """Calculate accessibiity score using soft threshold approach.

    1 / (1+ e^(k *((dist-access_dist)/access_dist)))

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of original distance field names
    threshold: int
        access distance threshold, default is 500 meters
    k: int
        the slope of decay, default is 5

    Returns
    -------
    DataFrame
    """
    df1 = 1 / (
        1 + numpy.exp(k * ((df[distance_names] - threshold) / threshold))
    )
    df1 = df1.fillna(0).astype(float)
    # If any of distance_names were all null in DF, should be returned as all null
    nulls = df[distance_names].isnull().all()
    df1[nulls.index[nulls]] = np.nan
    return df1


# Cumulative-Gaussian
# Reference: Vale, D. S., & Pereira, M. (2017).
# The influence of the impedance function on gravity-based pedestrian accessibility measures
def cumulative_gaussian_access_score(
    df,
    distance_names,
    threshold=500,
    k=129842,
):
    """Calculate accessibiity score using Cumulative-Gaussian approach.

    1 if d <= access_dist ; otherwise, e ^(-1 *((d^2)/k)) if d > access_dist

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of field names for distance records
    threshold: int
        access distance threshold
    k: int
        the slope of decay

    Returns
    -------
    DataFrame
    """
    df1 = df[distance_names].copy()
    df1 = df1.astype(float)
    df1[df1 <= threshold] = 1
    df1[df1 > threshold] = numpy.exp(
        -1 * (((df1[df1 > threshold] - threshold) ** 2) / k),
    )
    df1 = df1.fillna(0).astype(float)
    return df1


def split_list(alist, wanted_parts=1):
    """Split list.

    Parameters
    ----------
    alist: list
        the split list
    wanted_parts: int
        the number of parts (default: {1})

    Returns
    -------
    list
    """
    length = len(alist)
    # return all parts in a list, like [[],[],[]]
    return [
        alist[i * length // wanted_parts : (i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]
