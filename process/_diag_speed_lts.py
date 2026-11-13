"""Read-only diagnostic: where does each street's speed come from, and what LTS does
it produce?

Written for round 2 validation feedback (Shirley Shiqin Liu, Minneapolis, Sep 2026):
"all secondary roads are categorized as LTS 2, as the default speed is set to 40km/h.
However ... the default speed for secondary highways should be 55km/h."

The premise does not match the code, and this report is the evidence either way:

  * ``DEFAULT_SPEED_KMH`` in ``_cycling_lts_network`` already gives secondary 55, and
    a region may override it (``cycling_indicators.speed_limits.defaults``, as
    Minneapolis-Urban.yml does -- also with 55).
  * but a default only *fills a gap*: ``assign_speed`` is ``speed.fillna(default)``,
    so wherever OpenStreetMap carries a ``maxspeed`` tag, that tag wins.  A US
    secondary posted 30 mph parses to 48 km/h, and 25 mph to 40 km/h.
  * so a secondary road's LTS turns on its *tagged* speed and whether it has a
    cycle lane, not on the default.  Without a lane at 48 km/h no LTS 1/2/3 rule
    matches (the arterial LTS 3 rule needs <= 40) and it falls through to LTS 4;
    with ``cycleway=lane`` at <= 50 it is LTS 2.

For each highway class the report gives: edge count and km, how many edges carry an
OSM maxspeed tag against how many took a default, the speeds in use, the cycling
facility mix, and the resulting LTS distribution.  Where a class is dominated by one
tagged speed, that speed is named -- that is usually the number a validator is
actually reacting to.

Writes nothing.  Usage, inside the container:

    /env/bin/python _diag_speed_lts.py "data/Cycling/Minneapolis/Minneapolis-Urban.yml"
    /env/bin/python _diag_speed_lts.py "<codename>" --classes secondary,primary,residential

``--lts1-speed N`` additionally reports what would move if the LTS 1 mixed-traffic
speed threshold (``cycling_indicators.lts_rules.mixed_traffic_lts1_speed``) were N
rather than the configured value -- the network-level half of the US residential
street question, answerable without re-running the accessibility analysis:

    /env/bin/python _diag_speed_lts.py "<codename>" --lts1-speed 40
"""
import sys

import ghsci
import pandas as pd

sys.path.insert(0, 'subprocesses')
import _cycling_lts_network as lts  # noqa: E402

# the classes a validator is most likely to ask about; --classes overrides
DEFAULT_CLASSES = [
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary',
    'residential', 'unclassified', 'living_street', 'service',
]


def _pct(n, d):
    return f'{100 * n / d:.1f}%' if d else '-'


def _top(series, n=3):
    """The n most common values, as 'value (share)' strings."""
    if series.empty:
        return '-'
    counts = series.value_counts()
    total = counts.sum()
    return ', '.join(
        f'{v:g} ({_pct(c, total)})' if isinstance(v, float) else f'{v} ({_pct(c, total)})'
        for v, c in counts.head(n).items()
    )


def main():
    codename = sys.argv[1]
    classes = DEFAULT_CLASSES
    if '--classes' in sys.argv:
        classes = sys.argv[sys.argv.index('--classes') + 1].split(',')

    permutation = None
    if '--lts1-speed' in sys.argv:
        permutation = float(sys.argv[sys.argv.index('--lts1-speed') + 1])

    r = ghsci.Region(codename)
    config = lts.cycling_config(r) or {}
    speed_config = config.get('speed_limits', {})
    defaults = lts.load_speed_defaults(speed_config)

    edges = lts.load_edges(r)
    highway, facility = lts.classify_cycleway(edges)
    edges['highway'] = highway
    edges['bike_facility'] = facility
    # the tagged speed, before any default is applied: this is the distinction the
    # whole diagnostic turns on
    tagged = pd.Series(lts.parse_speed_kmh(edges['maxspeed']), index=edges.index)
    edges['maxspeed_kmh'] = lts.assign_speed(edges, defaults)
    if speed_config.get('zones'):
        edges = lts.apply_speed_zones(r, edges, speed_config['zones'])
    edges['adt'] = lts.assign_adt(edges['highway'])
    edges['maxspeed_kmh'], edges['adt'] = lts.apply_motor_restriction(
        edges, edges['maxspeed_kmh'], edges['adt'],
    )
    lts1_speed = float(
        (config.get('lts_rules') or {}).get(
            'mixed_traffic_lts1_speed', lts.MIXED_TRAFFIC_LTS1_SPEED,
        ),
    )
    edges['lvl_traf_stress'] = lts.assign_lts(
        edges['highway'], edges['bike_facility'],
        edges['maxspeed_kmh'], edges['adt'],
        mixed_traffic_lts1_speed=lts1_speed,
    )
    edges['tagged_kmh'] = tagged
    edges['km'] = edges['length'] / 1000

    print(f'\n{r.name} ({r.codename}) -- speed provenance and resulting LTS\n')
    print(
        'Configured defaults (km/h), where OpenStreetMap has no maxspeed tag: '
        + ', '.join(
            f'{c}={defaults[c]:g}' for c in classes if c in defaults
        ),
    )
    if speed_config.get('zones'):
        print(f'Speed zones configured: {len(speed_config["zones"])}')
    print(
        f'\nmixed_traffic_lts1_speed: {lts1_speed:g} km/h'
        ' (LTS 1 threshold for low-volume local streets in mixed traffic)\n',
    )

    header = (
        f'{"highway":<14}{"edges":>9}{"km":>9}{"tagged":>9}{"default":>9}  '
        f'{"speeds in use (km/h)":<34}{"LTS 1":>7}{"LTS 2":>7}{"LTS 3":>7}{"LTS 4":>7}'
    )
    print(header)
    print('-' * len(header))
    for c in classes:
        sub = edges[edges['highway'] == c]
        if sub.empty:
            continue
        n = len(sub)
        has_tag = int(sub['tagged_kmh'].notna().sum())
        counts = sub['lvl_traf_stress'].value_counts()
        print(
            f'{c:<14}{n:>9,}{sub["km"].sum():>9,.0f}'
            f'{_pct(has_tag, n):>9}{_pct(n - has_tag, n):>9}  '
            f'{_top(sub["maxspeed_kmh"].dropna()):<34}'
            + ''.join(f'{_pct(counts.get(i, 0), n):>7}' for i in [1, 2, 3, 4]),
        )

    # why a class lands where it does: the facility mix decides between the LTS
    # rules once the speed is known
    print('\nCycling facility mix (what the LTS rules match on alongside speed):\n')
    for c in classes:
        sub = edges[edges['highway'] == c]
        if sub.empty:
            continue
        print(f'  {c:<14}{_top(sub["bike_facility"], 4)}')

    # the cross-tabulation a validator can argue with directly
    print('\nSpeed x LTS, for the classes with the most disputed ratings:\n')
    for c in [x for x in ('secondary', 'primary', 'tertiary', 'residential') if x in classes]:
        sub = edges[edges['highway'] == c]
        if sub.empty:
            continue
        print(f'  {c}:')
        tab = pd.crosstab(
            sub['maxspeed_kmh'], sub['lvl_traf_stress'], margins=True,
        )
        print(tab.to_string().replace('\n', '\n    '), '\n')

    if permutation is not None and permutation != lts1_speed:
        alt = lts.assign_lts(
            edges['highway'], edges['bike_facility'],
            edges['maxspeed_kmh'], edges['adt'],
            mixed_traffic_lts1_speed=permutation,
        )
        moved = edges[alt != edges['lvl_traf_stress']]
        print(
            f'Permutation: mixed_traffic_lts1_speed {lts1_speed:g} -> '
            f'{permutation:g} km/h\n',
        )
        if moved.empty:
            print('  no edges change class.\n')
        else:
            print(
                f'  {len(moved):,} edges ({moved["km"].sum():,.0f} km, '
                f'{_pct(len(moved), len(edges))} of the network) change class:\n',
            )
            shift = pd.crosstab(
                moved['lvl_traf_stress'], alt.loc[moved.index], margins=True,
            )
            shift.index.name = 'from LTS'
            shift.columns.name = 'to LTS'
            print('   ', shift.to_string().replace('\n', '\n    '), '\n')
            print('  by highway class:')
            for c in classes:
                sub = moved[moved['highway'] == c]
                if not sub.empty:
                    total = int((edges['highway'] == c).sum())
                    print(
                        f'    {c:<14}{len(sub):>9,} of {total:,} '
                        f'({_pct(len(sub), total)})',
                    )
            print(
                '\n  Only the lts1 measure can move as a result: an edge changing'
                '\n  between LTS 1 and LTS 2 stays inside LTS <= 2, so low_stress and'
                '\n  low_stress_ride are unaffected.  Confirming the access-level'
                '\n  effect needs a full re-run with the setting in the region yml.\n',
            )


if __name__ == '__main__':
    main()
