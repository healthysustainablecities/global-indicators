"""One-way streets in a cycling study region: how many, and is their direction right?

Read-only diagnostic for the directed cycling routing (see "The edge costs" in
subprocesses/cycling_indicators_readme.md).  Run after ``_cycling_lts_network``:

    /env/bin/python _diag_oneway.py "data/Cycling/Valencia/Valencia"

Reports, for the region:

1. How much of the ridable network is one-way for cycling, by highway class and by
   Level of Traffic Stress, and how much of the one-way network permits contraflow
   cycling -- i.e. how much directed routing can be expected to change.
2. Where the network records the direction of its one-way streets (``oneway_from``,
   written by ``_03_create_network_resources``), how well the fallback used for older
   networks recovers it.  The fallback reads the direction from the edge geometry, or
   for two-vertex edges from the node order of the OpenStreetMap way; this is the only
   independent check of it, so run it on at least one rebuilt region before trusting
   the fallback on a network that predates ``oneway_from``.
"""

import os
import sys

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(os.getcwd(), 'subprocesses'))

import ghsci  # noqa: E402
import pandas as pd  # noqa: E402
from _cycling_lts_network import (  # noqa: E402
    _columns,
    _oneway_direction_sql,
    cycling_config,
)


def oneway_extent(r):
    """Ridable length that is one-way for cycling, by highway class and by LTS."""
    edges = r.get_df(
        """
        SELECT highway, lvl_traf_stress AS lts, length,
               COALESCE(bike_oneway, false) AS bike_oneway,
               lower(oneway::text) IN ('true', 't', 'yes', '1', '-1', 'reverse')
                   AS osm_oneway
        FROM edges WHERE bike_permitted
        """,
    )
    edges['highway'] = edges['highway'].astype(str)
    total_km = edges['length'].sum() / 1000

    def table(by):
        g = edges.groupby(by)
        out = pd.DataFrame(
            {
                'ridable_km': g['length'].sum() / 1000,
                'oneway_km': g.apply(
                    lambda d: d.loc[d['bike_oneway'], 'length'].sum() / 1000,
                ),
            },
        )
        out['pct_oneway'] = 100 * out['oneway_km'] / out['ridable_km']
        return out.sort_values('ridable_km', ascending=False).round(1)

    osm_km = edges.loc[edges['osm_oneway'], 'length'].sum() / 1000
    bike_km = edges.loc[edges['bike_oneway'], 'length'].sum() / 1000
    print(f'\nRidable network: {total_km:,.0f} km')
    print(
        f'  tagged one-way: {osm_km:,.0f} km ({100 * osm_km / total_km:.1f}%), '
        f'of which {osm_km - bike_km:,.1f} km permits contraflow cycling',
    )
    print(
        f'  one-way for cycling: {bike_km:,.0f} km '
        f'({100 * bike_km / total_km:.1f}% of ridable length)',
    )
    print('\nBy highway class (largest first):')
    print(table('highway').head(12).to_string())
    print('\nBy Level of Traffic Stress:')
    print(table('lts').to_string())


def direction_agreement(r):
    """Agreement of the fallback direction with the recorded ``oneway_from``."""
    if 'oneway_from' not in _columns(r, 'edges'):
        print(
            '\nedges has no oneway_from column (network built before it was '
            'recorded), so the fallback direction cannot be checked here.',
        )
        return
    line = f'{r.config["osm_prefix"]}_line'
    line = line if _columns(r, line) else None
    fallback = r.get_df(_oneway_direction_sql(line, False)).set_index('ogc_fid')
    recorded = r.get_df(_oneway_direction_sql(line, True)).set_index('ogc_fid')
    both = fallback.join(recorded, lsuffix='_fallback', rsuffix='_recorded')
    both = both[both['resolved_by_recorded'] == 'recorded']
    both['agree'] = both['fwd_from_to_fallback'] == both['fwd_from_to_recorded']
    summary = both.groupby('resolved_by_fallback')['agree'].agg(
        edges='size',
        agree='sum',
    )
    summary['pct_agree'] = (100 * summary['agree'] / summary['edges']).round(2)
    print(
        '\nFallback direction against the recorded direction, by the source the '
        'fallback used:',
    )
    print(summary.to_string())
    print(
        f"  overall: {int(both['agree'].sum()):,} of {len(both):,} one-way edges "
        f"({100 * both['agree'].mean():.2f}%)",
    )


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        sys.exit(__doc__)
    r = ghsci.Region(codename)
    if cycling_config(r) is None:
        sys.exit('cycling_indicators is not enabled for this region.')
    if 'bike_oneway' not in _columns(r, 'edges'):
        sys.exit('edges has no bike_oneway column; run _cycling_lts_network first.')
    print(f'One-way streets: {r.name}')
    oneway_extent(r)
    direction_agreement(r)
    r.engine.dispose()


if __name__ == '__main__':
    main()
