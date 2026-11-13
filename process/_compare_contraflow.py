"""Before/after evidence for directed cycling routing, without asking anyone to re-rate.

Round 2 validators found routes riding against one-way streets.  Rather than repeat
the validation, this re-routes one region under each ``contraflow`` treatment and
compares them, using the same seed-42 sample of validation routes the validators
were shown:

    permit    one-way restrictions ignored: the routing the validators assessed
    prohibit  no travel against the flow
    dismount  the bike is walked against the flow (the default treatment)

Run after a full analysis of the region (inside the ghsci container):

    /env/bin/python _compare_contraflow.py "data/Cycling/Valencia/Valencia" \
        [--baseline /path/to/valencia_routes.json] [--outdir DIR]

It reports:

1. **Regression** (with ``--baseline``, a routes file exported before directed
   routing): do the routes under ``permit`` reproduce it, route for route?
2. **The problem and the fix**: metres *ridden* against a one-way street on the
   validation routes under each treatment.  Zero is the pass mark for ``dismount``
   and ``prohibit``; under ``permit`` it measures what the validators saw.
3. **Monotonicity**: per sample point, distance under ``prohibit`` >= ``dismount``
   >= ``permit``.
4. **Effect on the indicators**: population-weighted share of sample points with
   access, per measure, destination and threshold, under each treatment.

Only the six directed cost columns on ``edges`` are rewritten between treatments
(seconds, against minutes for the whole LTS step); they are left as the region's
configured treatment.  ``sample_points_cycling`` is not touched.
"""

import argparse
import json
import os
import sys

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.getcwd(), 'subprocesses'))

import _cycling_accessibility as ca  # noqa: E402
import _cycling_lts_network as lts  # noqa: E402
import _export_validation_routes as routes  # noqa: E402
import ghsci  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

MODES = ['permit', 'prohibit', 'dismount']


def set_directed_costs(r, config, mode):
    """Rewrite the directed cost columns on ``edges`` for one contraflow treatment."""
    danger_weight = float(config.get('danger_weight', lts.DANGER_WEIGHT))
    dismount_weight = float(config.get('dismount_weight', lts.DISMOUNT_WEIGHT))
    edges = r.get_df(
        'SELECT ogc_fid, "from", "to", length, lvl_traf_stress, foot_dismount, '
        'bike_permitted, bike_oneway, bike_fwd_from_to FROM edges',
    )
    edges = lts.add_impedance(r, edges, danger_weight, dismount_weight)
    edges = lts.add_directed_costs(edges, mode, dismount_weight)
    columns = lts.DIRECTED_COST_COLUMNS
    edges[['ogc_fid', *columns]].to_sql(
        '_contraflow_costs',
        r.engine,
        if_exists='replace',
        index=False,
    )
    with r.engine.begin() as conn:
        conn.execute(
            text(
                'UPDATE edges e SET '
                + ', '.join(f'{c} = t.{c}' for c in columns)
                + ' FROM _contraflow_costs t WHERE e.ogc_fid = t.ogc_fid',
            ),
        )
        conn.execute(text('DROP TABLE _contraflow_costs'))


def population_weights(r, index):
    """Each sample point's share of its grid cell's population."""
    sp = r.get_df('SELECT point_id, grid_id FROM urban_sample_points')
    pop = r.get_df(
        f"SELECT grid_id, pop_est FROM {r.config['population_grid']}",
    )
    sp = sp.merge(pop, on='grid_id', how='left')
    share = sp.groupby('grid_id')['point_id'].transform('size')
    weight = sp['pop_est'].fillna(0).astype('float64') / share
    return pd.Series(weight.to_numpy(), index=sp['point_id']).reindex(index)


def route_summary(path):
    """Per-route distance and metres ridden / walked against a one-way street."""
    with open(path) as f:
        data = json.load(f)
    rows = []
    for rt in data['routes']:
        segs = rt.get('seg') or []
        rows.append(
            {
                'p': rt['p'],
                'cat': rt['cat'],
                'meas': rt['meas'],
                'ok': bool(rt['ok']),
                'net': rt.get('net'),
                'ridden_against': sum(
                    s['m'] for s in segs if s.get('cf') and not s.get('d')
                ),
                'walked_against': sum(
                    s['m'] for s in segs if s.get('cf') and s.get('d')
                ),
            },
        )
    return pd.DataFrame(rows).set_index(['p', 'cat', 'meas'])


def compare(codename, baseline, outdir):  # noqa: C901
    r = ghsci.Region(codename)
    config = lts.cycling_config(r)
    if config is None:
        sys.exit('cycling_indicators is not enabled for this region.')
    configured = str(
        config.get('contraflow', lts.CONTRAFLOW_DEFAULT),
    ).lower()
    config = ca.effective_config(ca.accessibility_config(r), config)
    thresholds = tuple(
        sorted(set(config.get('distances') or (500, 1000, 2000, 5000))),
    )
    specs = ca.usable_destination_specs(
        r,
        config.get('destinations') or ca.DEFAULT_DESTINATIONS,
    )
    measures = ca.resolve_measures(config)
    trip_direction = ca.resolve_trip_direction(config)
    outdir = outdir or f'/tmp/contraflow/{routes.slugify(r.name)}'
    # the configured treatment last, so the edge costs are left as they were found
    modes = [m for m in MODES if m != configured] + [configured]

    points, exported = {}, {}
    for mode in modes:
        print(f'\n=== contraflow: {mode} ===', flush=True)
        set_directed_costs(r, config, mode)
        nodes_poi_dist, node_index = ca.cycling_poi_distance(
            r,
            thresholds,
            specs,
            measures,
            engine='inmemory',
            trip_direction=trip_direction,
        )
        sample_points = ca.cycling_sample_point_access(
            r,
            nodes_poi_dist,
            node_index,
            thresholds,
            specs,
            config,
            measures,
        )
        points[mode] = pd.DataFrame(
            sample_points.drop(columns='geometry', errors='ignore'),
        )
        mode_dir = f'{outdir}/{mode}'
        routes.export(codename, 20, 42, mode_dir, contraflow=mode)
        exported[mode] = route_summary(
            next(
                f'{mode_dir}/{f}'
                for f in os.listdir(mode_dir)
                if f.endswith('_routes.json')
            ),
        )

    print(f'\n\n##### {r.name}: contraflow treatments compared #####')

    if baseline:
        before = route_summary(baseline)
        after = exported['permit'].reindex(before.index)
        same_ok = before['ok'] == after['ok'].fillna(False)
        both = before['ok'] & after['ok'].fillna(False)
        diff = (before.loc[both, 'net'] - after.loc[both, 'net']).abs()
        print(
            f'\n1. Regression against {os.path.basename(baseline)} '
            f'({len(before)} routes), contraflow: permit',
        )
        print(f'   reachability identical: {int(same_ok.sum())} of {len(before)}')
        print(
            f'   distance identical (within 0.1 m): {int((diff <= 0.1).sum())} '
            f'of {int(both.sum())} routes reachable in both; '
            f'largest difference {diff.max():.1f} m',
        )
        if (diff > 0.1).any():
            print(diff[diff > 0.1].sort_values(ascending=False).head(10))

    print('\n2. Validation routes travelling against a one-way street')
    rows = []
    for mode in MODES:
        e = exported[mode]
        ok = e[e['ok']]
        rows.append(
            {
                'contraflow': mode,
                'routes': len(e),
                'reachable': len(ok),
                'ride_against_oneway': int((ok['ridden_against'] > 0).sum()),
                'points_affected': ok.loc[ok['ridden_against'] > 0]
                .index.get_level_values('p')
                .nunique(),
                'ridden_against_m': round(ok['ridden_against'].sum()),
                'walk_against_oneway': int((ok['walked_against'] > 0).sum()),
                'walked_against_m': round(ok['walked_against'].sum()),
            },
        )
    print(pd.DataFrame(rows).to_string(index=False))
    by_measure = (
        exported['permit']
        .assign(against=lambda d: d['ridden_against'] > 0)
        .groupby('meas')['against']
        .agg(['sum', 'size'])
    )
    print('\n   under permit, routes riding against the flow, by measure:')
    print(by_measure.to_string())
    flagged = sorted(
        exported['permit']
        .loc[exported['permit']['ridden_against'] > 0]
        .index.get_level_values('p')
        .unique(),
    )
    print(f'   sample points with any such route: {flagged}')

    print('\n3. Monotonicity (prohibit >= dismount >= permit), per sample point')
    dist_cols = [c for c in points['permit'] if 'nearest_node_' in c]
    worst = 0
    for col in dist_cols:
        values = {
            m: points[m][col]
            .reindex(points['permit'].index)
            .astype('float64')
            .fillna(np.inf)
            .to_numpy()
            for m in MODES
        }
        # unreached is recorded as a negative sentinel as well as missing
        values = {m: np.where(v < 0, np.inf, v) for m, v in values.items()}
        worst += int((values['prohibit'] < values['dismount'] - 1).sum())
        worst += int((values['dismount'] < values['permit'] - 1).sum())
    print(
        f'   violations beyond 1 m of rounding: {worst} across '
        f'{len(dist_cols)} distance columns x {len(points["permit"])} points',
    )

    print('\n4. Population-weighted access (% of population), by treatment')
    weights = population_weights(r, points['permit'].index).fillna(0)
    rows = []
    for key in measures:
        prefix = f'sp_cycle_{ca.MEASURES[key]["infix"]}access_'
        for col in points['permit'].columns:
            if not col.startswith(prefix):
                continue
            row = {'measure': key, 'indicator': col[len(prefix) :]}
            for mode in MODES:
                x = points[mode][col].reindex(weights.index).fillna(0).astype('float64')
                row[mode] = round(
                    100 * float((x * weights).sum()) / float(weights.sum()),
                    1,
                )
            row['dismount_minus_permit'] = round(
                row['dismount'] - row['permit'],
                1,
            )
            rows.append(row)
    table = pd.DataFrame(rows)
    os.makedirs(outdir, exist_ok=True)
    table.to_csv(f'{outdir}/access_by_contraflow.csv', index=False)
    headline = table[
        table['indicator'].str.contains(
            'fresh_food_market|pt_frequent|pt_any|public_open_space_large',
        )
    ]
    print(headline.to_string(index=False))
    print(f'\n   all {len(table)} indicators: {outdir}/access_by_contraflow.csv')
    print(
        f'   edge costs left as the configured treatment ({configured}); '
        f'routes for each treatment under {outdir}/<treatment>/',
    )
    r.engine.dispose()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('codename')
    ap.add_argument('--baseline', default=None)
    ap.add_argument('--outdir', default=None)
    a = ap.parse_args()
    compare(a.codename, a.baseline, a.outdir)
