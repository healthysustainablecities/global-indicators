"""Snapshot a region's results, and compare two snapshots value for value.

For confirming that a change of code (a merge, a refactor, a different source for
the network) leaves a region's results as they were.  Inside the ghsci container:

    /env/bin/python _compare_region_tables.py dump <codename> <folder>
    /env/bin/python _compare_region_tables.py compare <folder A> <folder B>

``dump`` writes each result table present (pedestrian and cycling, sample point
to city) to Parquet, without geometry, with a per-step timing summary taken from
the region's ``script_log``.  ``compare`` matches rows by their identifier and
counts the values that differ beyond a relative tolerance of 1e-9, by column.

The network is compared as a set of edges described without reference to anything
that varies between two builds of the same network (edge row numbers; which end
of an undirected edge is listed first): each edge by its end nodes, length,
stress, and its costs with and against the legal direction of travel.

Run the same code twice first: what differs between two identical runs is the
noise floor against which a real change has to be judged.
"""

import json
import os
import sys

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.getcwd(), 'subprocesses'))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# table -> identifying column; a table that is absent is skipped
KEYED = {
    'indicators_region': None,
    'indicators_sample_points': 'point_id',
    'urban_sample_points': 'point_id',
    'sample_points_cycling': 'point_id',
    'nodes_pop_intersect_density': 'osmid',
    'nodes': 'osmid',
}
# columns that name the run rather than describe a result
IGNORE = {'db', 'study_region', 'geom', 'geometry', 'geom_4326'}

EDGE_SQL = """
SELECT LEAST(u, v) AS a, GREATEST(u, v) AS b,
       round(length::numeric, 2)::float AS length,
       lower(oneway::text) AS oneway{cycling}
FROM edges
"""
EDGE_CYCLING = """,
       lvl_traf_stress, bike_permitted, foot_dismount, bike_oneway,
       CASE WHEN bike_oneway AND bike_permitted
            THEN CASE WHEN bike_fwd_from_to THEN "from" ELSE "to" END
       END AS legal_from,
       round(LEAST(cost_dist_ft, cost_dist_tf)::numeric, 2)::float AS dist_lo,
       round(GREATEST(cost_dist_ft, cost_dist_tf)::numeric, 2)::float AS dist_hi,
       round(LEAST(cost_lts_ft, cost_lts_tf)::numeric, 2)::float AS lts_lo,
       round(GREATEST(cost_lts_ft, cost_lts_tf)::numeric, 2)::float AS lts_hi,
       round(LEAST(cost_ride_ft, cost_ride_tf)::numeric, 2)::float AS ride_lo,
       round(GREATEST(cost_ride_ft, cost_ride_tf)::numeric, 2)::float AS ride_hi"""


def _columns(r, table):
    sql = (
        'SELECT column_name, udt_name FROM information_schema.columns '
        f"WHERE table_schema = 'public' AND table_name = '{table}'"
    )
    return r.get_df(sql)


def dump(codename, folder):
    import ghsci

    r = ghsci.Region(codename)
    os.makedirs(folder, exist_ok=True)
    tables = dict(KEYED)
    grids = r.get_df(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename ~ '^indicators_[0-9]+m_[0-9]+$'",
    )['tablename'].tolist()
    tables.update({grid: 'grid_id' for grid in grids})
    written = {}
    for table, key in tables.items():
        columns = _columns(r, table)
        if columns.empty:
            continue
        keep = [
            c
            for c, kind in zip(columns['column_name'], columns['udt_name'])
            if kind != 'geometry' and c not in IGNORE
        ]
        frame = r.get_df(
            f'SELECT {", ".join(chr(34) + c + chr(34) for c in keep)} FROM {table}',
        )
        frame = pd.DataFrame(frame).convert_dtypes(dtype_backend='numpy_nullable')
        frame.to_parquet(f'{folder}/{table}.parquet', index=False)
        written[table] = {'key': key, 'rows': len(frame)}
    cycling = 'cost_dist_ft' in set(_columns(r, 'edges')['column_name'])
    edges = pd.DataFrame(
        r.get_df(EDGE_SQL.format(cycling=EDGE_CYCLING if cycling else '')),
    ).convert_dtypes(dtype_backend='numpy_nullable')
    edges.to_parquet(f'{folder}/edges.parquet', index=False)
    written['edges'] = {'key': '(multiset)', 'rows': len(edges)}
    log = pd.DataFrame(
        r.get_df(
            'SELECT script, datetime_completed FROM script_log '
            'ORDER BY datetime_completed',
        ),
    )
    with open(f'{folder}/_snapshot.json', 'w') as f:
        json.dump(
            {
                'codename': codename,
                'tables': written,
                'script_log': log.astype(str).values.tolist(),
            },
            f,
            indent=1,
        )
    for table, info in written.items():
        print(f"  {table}: {info['rows']:,} rows")
    r.engine.dispose()


def _differs(x, y):
    """Boolean array: do two aligned columns differ (beyond 1e-9 relative)?"""
    xn, yn = pd.isna(x).to_numpy(), pd.isna(y).to_numpy()
    out = xn != yn
    both = ~xn & ~yn
    if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
        a = x.to_numpy('float64', na_value=np.nan)
        b = y.to_numpy('float64', na_value=np.nan)
        with np.errstate(invalid='ignore'):
            far = np.abs(a - b) > 1e-9 * np.maximum(1, np.abs(a))
        out |= both & far
    else:
        out |= both & (x.astype(str).to_numpy() != y.astype(str).to_numpy())
    return out


def compare(folder_a, folder_b):
    with open(f'{folder_a}/_snapshot.json') as f:
        a_info = json.load(f)
    with open(f'{folder_b}/_snapshot.json') as f:
        b_info = json.load(f)
    print(f"A: {folder_a} ({a_info['codename']})")
    print(f"B: {folder_b} ({b_info['codename']})\n")
    total = differing = 0
    for table, info in a_info['tables'].items():
        if table not in b_info['tables']:
            print(f'{table}: only in A')
            continue
        a = pd.read_parquet(f'{folder_a}/{table}.parquet')
        b = pd.read_parquet(f'{folder_b}/{table}.parquet')
        if table == 'edges':
            cols = [c for c in a.columns if c in b.columns]
            ra = a[cols].astype(str).agg('|'.join, axis=1).value_counts()
            rb = b[cols].astype(str).agg('|'.join, axis=1).value_counts()
            only_a = int(ra.sub(rb, fill_value=0).clip(lower=0).sum())
            only_b = int(rb.sub(ra, fill_value=0).clip(lower=0).sum())
            print(
                f'edges: {len(a):,} vs {len(b):,}; described identically except '
                f'{only_a:,} only in A and {only_b:,} only in B '
                f'({len(cols)} attributes)',
            )
            differing += only_a + only_b
            continue
        key = info['key']
        if key:
            a, b = a.set_index(key), b.set_index(key)
        shared = a.index.intersection(b.index)
        unmatched = len(a.index.symmetric_difference(b.index))
        cols = [c for c in a.columns if c in b.columns]
        extra = sorted(set(a.columns) ^ set(b.columns))
        a, b = a.loc[shared, cols], b.loc[shared, cols]
        by_column = {}
        for c in cols:
            n = int(_differs(a[c], b[c]).sum())
            if n:
                d = None
                if pd.api.types.is_numeric_dtype(a[c]):
                    d = float(
                        (a[c].astype('float64') - b[c].astype('float64'))
                        .abs()
                        .max(),
                    )
                by_column[c] = (n, d)
        n_values = len(shared) * len(cols)
        n_diff = sum(n for n, _ in by_column.values())
        total += n_values
        differing += n_diff + unmatched
        print(
            f'{table}: rows {len(a):,}; unmatched ids {unmatched}; '
            f'values compared {n_values:,}; differing {n_diff:,}'
            + (f'; columns in one only: {extra[:6]}' if extra else ''),
        )
        for c, (n, d) in sorted(by_column.items(), key=lambda kv: -kv[1][0])[:10]:
            print(
                f'     {c}: {n:,}' + (f' (largest {d:.6g})' if d is not None else ''),
            )
    print(f'\nvalues compared {total:,}; differences {differing:,}')


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'dump':
        dump(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == 'compare':
        compare(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
