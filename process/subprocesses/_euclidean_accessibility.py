"""
Straight-line (Euclidean) catchment accessibility.

Optional GHSCI analysis step, gated by an ``accessibility.euclidean`` block in
the region configuration.  Some services are provided across a catchment far
larger than a walk -- a police station within 15 km, a fire station within
75 km -- and what matters for them is coverage rather than whether a resident
could walk there.  Routing over the pedestrian network at that scale would be
slow, and would also misrepresent the question, since an emergency response
does not follow footpaths.  This step therefore measures the straight-line
distance from each sample point to the nearest destination.

Catchment destinations are declared separately from the walking destinations
and are not inherited from them: a walking destination silently measured in a
straight line would be a different indicator under a familiar name.  Each may
be read from its own data file, because the destinations compiled for the
walking analyses are restricted to the study region buffered by 1.6 km, which
would omit the nearest station for much of a large catchment.  Features are
instead retained within each destination's own ``max_distance`` of the urban
study region, and distances beyond it are censored: a closer feature outside
the retained area might exist, so a longer distance could not be trusted.

Writes to the ``sample_points_euclidean`` table:

    sp_euclid_dist_<name>              straight-line distance (m) to the nearest
    sp_euclid_access_<name>_<d>m       within d metres (1 / 0)
    sp_euclid_beyond_<name>_<d>m       further than d metres, for an avoided
                                       destination (direction: avoid)

aggregated by ``_12_aggregation`` to ``pct_access_euclid_<name>_<d>m``,
``pct_beyond_euclid_<name>_<d>m`` and ``avg_euclid_dist_<name>``.

Configuration::

    accessibility:
      euclidean:
        destinations:
          - name: police_station
            data: MX/police.gpkg -where "type = 'police'"   # or layer + where
            distances: [15000]
            max_distance: 45000       # default: the largest distance

To run independently:  python subprocesses/_euclidean_accessibility.py <codename>
"""

import os
import re
import sys
import time

import ghsci
import numpy as np
import pandas as pd
from _accessibility_spec import AVOID, accessibility_config
from script_running_log import script_running_log
from sqlalchemy import text

DISTANCE_PREFIX = 'sp_euclid_dist_'
ACCESS_PREFIX = 'sp_euclid_access_'
BEYOND_PREFIX = 'sp_euclid_beyond_'
SAMPLE_POINT_TABLE = 'sample_points_euclidean'
DESTINATION_TABLE = 'euclidean_destinations'
NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


def resolve_spec(spec):
    """Resolve a catchment destination specification, filling defaults."""
    if not isinstance(spec, dict) or not spec.get('name'):
        raise ValueError(
            "Each accessibility.euclidean destination needs a 'name'.",
        )
    name = str(spec['name'])
    if not NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid catchment destination name '{name}': use lower-case "
            'letters, digits and underscores, starting with a letter.',
        )
    if bool(spec.get('data')) == bool(spec.get('layer')):
        raise ValueError(
            f"Catchment destination '{name}' needs either 'data' (a file to "
            "import) or 'layer' (a table already in the database).",
        )
    distances = sorted({int(d) for d in (spec.get('distances') or [])})
    if not distances or distances[0] <= 0:
        raise ValueError(
            f"Catchment destination '{name}' needs positive 'distances' "
            '(metres), e.g. [15000].',
        )
    max_distance = int(spec.get('max_distance') or distances[-1])
    if max_distance < distances[-1]:
        raise ValueError(
            f"max_distance for '{name}' ({max_distance} m) is less than its "
            f'largest distance ({distances[-1]} m).',
        )
    direction = str(spec.get('direction') or 'access').lower()
    if direction not in ('access', AVOID):
        raise ValueError(
            f"Unknown direction '{direction}' for '{name}' (expected "
            "'access' or 'avoid').",
        )
    return {
        **spec,
        'name': name,
        'distances': distances,
        'max_distance': max_distance,
        'direction': direction,
    }


def euclidean_config(r):
    """Resolve the catchment accessibility configuration, or None."""
    shared = accessibility_config(r)
    block = shared.get('euclidean') if isinstance(shared, dict) else None
    if not isinstance(block, dict) or not block.get('destinations'):
        return None
    specs = [resolve_spec(s) for s in block['destinations']]
    names = [s['name'] for s in specs]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        raise ValueError(
            f'Catchment destination names must be unique: {duplicated}',
        )
    return {**block, 'destinations': specs}


def spec_source(spec):
    """The table and filter a catchment destination is measured from."""
    if spec.get('data'):
        return DESTINATION_TABLE, f"dest_name = '{spec['name']}'"
    return spec['layer'], spec.get('where') or 'TRUE'


def catchment_scores(distances, specs):
    """Access (or beyond) scores at each band from nearest distances.

    A missing distance -- nothing within ``max_distance``, which is at least
    the largest band -- is outside every band.  A destination with no
    distance at all anywhere (no features) scores missing rather than 0.
    """
    columns = {}
    for spec in specs:
        name = spec['name']
        distance = distances[f'{DISTANCE_PREFIX}{name}'].astype('float64')
        none_found = distance.isna().all()
        for band in spec['distances']:
            within = (distance <= band).astype('float64')
            if none_found:
                within[:] = np.nan
            if spec['direction'] == AVOID:
                columns[f'{BEYOND_PREFIX}{name}_{band}m'] = 1 - within
            else:
                columns[f'{ACCESS_PREFIX}{name}_{band}m'] = within
    return pd.DataFrame(columns, index=distances.index)


def _data_source(data):
    source = str(data).strip()
    if os.path.isabs(source) or source.startswith('PG:'):
        return source
    return f'{ghsci.data_path}/{source}'


def _catchment_extent(r, distance):
    """'xmin ymin xmax ymax' of the urban study region expanded by a distance."""
    sql = f"""
        SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
        FROM (
            SELECT ST_Expand(ST_Extent(geom), {float(distance)}) AS e
            FROM urban_study_region
        ) t;
        """
    with r.engine.begin() as connection:
        row = connection.execute(text(sql)).first()
    return ' '.join(str(x) for x in row)


def import_destinations(r, specs):
    """Import file-based catchment destinations to ``euclidean_destinations``."""
    srid = r.config['crs']['srid']
    with r.engine.begin() as connection:
        connection.execute(text(f'DROP TABLE IF EXISTS {DESTINATION_TABLE}'))
        connection.execute(
            text(
                f'CREATE TABLE {DESTINATION_TABLE} ('
                'id serial PRIMARY KEY, dest_name text NOT NULL, '
                f'geom geometry(Geometry, {srid}))',
            ),
        )
    exclusion = 'exclusion_region' in r.get_tables()
    for spec in specs:
        if not spec.get('data'):
            continue
        staging = f'_euclid_{spec["name"]}'
        r.ogr_to_db(
            source=_data_source(spec['data']),
            layer=staging,
            query=(
                f'-spat {_catchment_extent(r, spec["max_distance"])} '
                f'-spat_srs {r.config["crs_srid"]}'
            ),
        )
        # features across an excluded boundary (e.g. an international border)
        # do not serve the study region, whatever their distance
        excluded = (
            'AND NOT EXISTS (SELECT 1 FROM exclusion_region x '
            'WHERE ST_Intersects(p.geom, x.geom))'
            if exclusion and spec.get('respect_exclusion', True)
            else ''
        )
        with r.engine.begin() as connection:
            if staging not in r.get_tables():
                print(
                    f"  - {spec['name']}: no features read from {spec['data']}",
                )
                continue
            count = connection.execute(
                text(
                    f"""
                    INSERT INTO {DESTINATION_TABLE} (dest_name, geom)
                    SELECT :name, ST_Force2D(p.geom)
                    FROM "{staging}" p
                    WHERE p.geom IS NOT NULL
                      AND EXISTS (
                        SELECT 1 FROM urban_study_region s
                        WHERE ST_DWithin(p.geom, s.geom, :distance)
                      )
                      {excluded};
                    """,
                ),
                {'name': spec['name'], 'distance': spec['max_distance']},
            ).rowcount
            connection.execute(text(f'DROP TABLE IF EXISTS "{staging}"'))
        print(
            f"  - {spec['name']}: {count} features within "
            f"{spec['max_distance']} m (source: {spec.get('source', spec['data'])})",
        )
    with r.engine.begin() as connection:
        connection.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS {DESTINATION_TABLE}_gix '
                f'ON {DESTINATION_TABLE} USING GIST (geom)',
            ),
        )
        connection.execute(text(f'ANALYZE {DESTINATION_TABLE}'))


def nearest_distances(r, specs):
    """Straight-line distance from each sample point to the nearest destination."""
    columns = {}
    for spec in specs:
        layer, where = spec_source(spec)
        if spec.get('layer'):
            with r.engine.begin() as connection:
                connection.execute(
                    text(
                        f'CREATE INDEX IF NOT EXISTS "{layer}_gix" '
                        f'ON "{layer}" USING GIST (geom)',
                    ),
                )
        # an index-assisted nearest neighbour search per sample point
        distance = r.get_df(
            f"""
            SELECT p.point_id, (
                SELECT ST_Distance(p.geom, e.geom)
                FROM "{layer}" e
                WHERE {where}
                ORDER BY p.geom <-> e.geom
                LIMIT 1
            ) AS distance
            FROM urban_sample_points p
            """,
            index_col='point_id',
        )['distance']
        distance = pd.to_numeric(distance, errors='coerce').astype('float64')
        distance[distance > spec['max_distance']] = np.nan
        columns[f'{DISTANCE_PREFIX}{spec["name"]}'] = distance
    return pd.DataFrame(columns)


def euclidean_accessibility(codename):
    start = time.time()
    script = '_euclidean_accessibility'
    task = 'Straight-line catchment accessibility for sample points'
    r = ghsci.Region(codename)
    config = euclidean_config(r)
    if config is None:
        print(
            'No accessibility.euclidean configuration for this region; '
            'skipping the straight-line catchment analysis.',
        )
        return
    specs = config['destinations']
    available = set(r.get_tables())
    usable = []
    for spec in specs:
        if spec.get('layer') and spec['layer'] not in available:
            print(
                f"  - skipping '{spec['name']}': layer '{spec['layer']}' not "
                'found',
            )
            continue
        usable.append(spec)
    if not usable:
        sys.exit('No catchment destinations available to analyse.')

    print('\nCalculating straight-line catchment accessibility...')
    import_destinations(r, usable)
    distances = nearest_distances(r, usable)
    scores = catchment_scores(distances, usable)
    sample_points = r.get_gdf(
        'SELECT point_id, grid_id, geom FROM urban_sample_points',
        index_col='point_id',
    )
    sample_points = pd.concat(
        [
            sample_points,
            distances.round(0).astype('Int64'),
            scores,
        ],
        axis=1,
    ).set_geometry('geom')
    sample_points.index.name = 'point_id'
    with r.engine.connect() as connection:
        sample_points.to_postgis(
            SAMPLE_POINT_TABLE,
            connection,
            index=True,
            if_exists='replace',
        )
    print(f'  Wrote {SAMPLE_POINT_TABLE} ({len(sample_points)} points).')
    for column in scores.columns:
        print(
            f'    {column}: {100 * scores[column].mean():.1f}% of sample points',
        )
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    euclidean_accessibility(codename)


if __name__ == '__main__':
    main()
