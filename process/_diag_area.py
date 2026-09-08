"""Why does a particular map view show cells with no access estimate?

Takes a lat/lon and a radius, and for every population grid cell in that window
reports: whether it reached the grid summary at all, its population, how many sample
points it has, and its access values.  Then does the same for the destinations drawn
in that window -- whether they are associated with a network node, and whether that
node touches the low-stress subgraph the measure actually routes over.

Written for round 2 validation feedback (Minneapolis, Sep 2026): "there are PT stops
that look like they should be accessible ... within grid cells that for some reason
have no estimates for access".

Writes nothing.  Usage, inside the container:

    /env/bin/python _diag_area.py "<codename>" <lat> <lon> [radius_m] [spec]
"""
import sys

import ghsci

codename = sys.argv[1]
lat, lon = float(sys.argv[2]), float(sys.argv[3])
radius = float(sys.argv[4]) if len(sys.argv) > 4 else 500
spec = sys.argv[5] if len(sys.argv) > 5 else 'pt_any'

r = ghsci.Region(codename)
grid = r.config['population_grid']
summary = r.config['grid_summary']
srid = r.config['crs']['srid']
pt = f'ST_Transform(ST_SetSRID(ST_MakePoint({lon},{lat}),4326),{srid})'

print(f'\n{r.name}: cells within {radius:g} m of ({lat}, {lon})\n')

# 1. the cells in the window (spatially indexed, so cheap)
cells = r.get_df(
    f'SELECT grid_id, pop_est::float AS pop_est FROM {grid} '
    f'WHERE ST_DWithin(geom, {pt}, {radius})',
)
if cells is None or cells.empty:
    sys.exit('  no grid cells in that window.')
ids = ','.join(str(int(i)) for i in cells['grid_id'])

# 2. sample points, counted over the same window rather than per cell
pts = r.get_df(
    f'SELECT grid_id, count(*)::float AS n FROM urban_sample_points '
    f'WHERE grid_id IN ({ids}) GROUP BY grid_id',
)
counts = dict(zip(pts['grid_id'], pts['n'])) if pts is not None and not pts.empty else {}

# 3. the summary rows for exactly those cells
cols = [
    f'pct_access_cycle_safe_{spec}_{d}m' for d in (500, 1000, 2000, 5000)
] + [f'avg_cycle_dist_safe_{spec}']
available = set(
    r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name = '{summary}'",
    )['column_name'],
)
cols = [c for c in cols if c in available]
if not cols:
    sys.exit(f'  no columns for spec {spec} on {summary}.')
sel = ', '.join(f'"{c}"::float AS "{c}"' for c in cols)
rows = r.get_df(f'SELECT grid_id, {sel} FROM {summary} WHERE grid_id IN ({ids})')
present = {int(g) for g in rows['grid_id']} if rows is not None and not rows.empty else set()

n = len(cells)
print(
    f'  {n} population grid cells; {len(present)} reached the grid summary, '
    f'{n - len(present)} did not -- no polygon is drawn for those at all.\n',
)

missing = cells[~cells['grid_id'].isin(present)]
if len(missing):
    no_pts = sum(1 for g in missing['grid_id'] if counts.get(g, 0) == 0)
    print('  the cells with no polygon:')
    print(f'    population 0:        {int((missing["pop_est"] == 0).sum()):>4} of {len(missing)}')
    print(f'    zero sample points:  {no_pts:>4} of {len(missing)}')
    print(f'    highest population among them: {missing["pop_est"].max():.0f}')
    print()

if rows is not None and not rows.empty:
    merged = rows.merge(cells, on='grid_id')
    last = f'pct_access_cycle_safe_{spec}_5000m'
    zero = merged[merged[last].fillna(0) == 0] if last in merged else merged.iloc[0:0]
    print(f'  the {len(merged)} cells that ARE in the summary:')
    print(f'    {len(zero)} have 0% access at 5000 m, holding '
          f'{zero["pop_est"].sum():,.0f} of {merged["pop_est"].sum():,.0f} people here')
    print()
    head = '    grid_id      pop  pts' + ''.join(
        f'{c.split("_")[-1]:>8}' for c in cols[:-1]
    ) + f'{"avg_m":>9}'
    print(head)
    for _, c in merged.sort_values('grid_id').head(30).iterrows():
        def f(v, w=8):
            return f'{"-":>{w}}' if v is None or v != v else f'{v:>{w}.1f}'
        print(
            f'    {int(c.grid_id):<10}{c.pop_est:>5.0f}'
            f'{int(counts.get(c.grid_id, 0)):>5}'
            + ''.join(f(c[k]) for k in cols[:-1])
            + f(c[cols[-1]], 9),
        )

# 4. the destinations drawn there, and whether they are usable as destinations
print(f'\n  destinations ({spec}) in the window:\n')
layer, where = 'destinations', f"dest_name = '{spec}'"
if spec == 'pt_frequent':
    layer, where = 'pt_stops_headway', 'headway <= 20'
dcols = set(
    r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name = '{layer}'",
    )['column_name'],
)
if 'n1' not in dcols:
    sys.exit(f'    {layer} carries no n1/n2 node association.')
dests = r.get_df(
    f'SELECT n1::float AS n1, n1_distance::float AS n1_distance '
    f'FROM {layer} WHERE {where} AND ST_DWithin(geom, {pt}, {radius})',
)
if dests is None or dests.empty:
    sys.exit('    none in this window.')
unassociated = int(dests['n1'].isna().sum())
print(
    f'    {len(dests)} destinations; {unassociated} have no nearest network node '
    '(n1 IS NULL), so they are never counted',
)
nodes = sorted({int(x) for x in dests['n1'].dropna()})
if nodes:
    nid = ','.join(str(x) for x in nodes)
    reach = r.get_df(f"""
        SELECT count(DISTINCT n)::float AS n FROM (
            SELECT "from" AS n FROM edges
             WHERE lvl_traf_stress <= 2 AND (bike_permitted OR foot_dismount)
               AND "from" IN ({nid})
            UNION
            SELECT "to" FROM edges
             WHERE lvl_traf_stress <= 2 AND (bike_permitted OR foot_dismount)
               AND "to" IN ({nid})
        ) t
    """)
    print(
        f'    {len(nodes)} distinct nearest nodes, of which '
        f'{int(reach.iloc[0, 0])} touch a low-stress (LTS<=2, ridable or walkable) '
        'edge -- the network the "allowing dismount" measure routes over',
    )
