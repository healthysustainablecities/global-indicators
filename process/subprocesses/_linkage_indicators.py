"""
Linkage indicators: externally prepared, pre-aggregated area indicators.

Optional GHSCI step, gated by a region's ``linkage_indicators`` block.  Some
indicators are prepared outside GHSCI and delivered already summarised for a
set of reporting areas -- the modelled outdoor thermal comfort of each grid
cell, block and lot, say, or a colleague's land use entropy by grid cell.  They
cannot be re-derived from sample points, and averaging them again would change
what they mean.  This step links them, as delivered, onto the matching
aggregation tables, and also brings them down to sample points so that a
composite index scored at sample points can use them.

Areas are matched by identifier where the source carries one (``match: id``),
or by geometry against a reference layer that does (``match: geometry``):
features identical to a reference feature take its identifier, and the rest
the identifier of the reference feature holding the largest share of their
area.  Several source features matched to one reference feature -- the parts
of a multipart block delivered separately -- are combined as an area weighted
mean.  Match statistics are printed and recorded.

Values are linked to:

``areas``          each aggregation named (the population ``grid``, or a
                   ``custom_aggregations`` key) from the source layer named
                   for it, joined on the aggregation's identifier (its first
                   column, or ``boundary_id``).  Aggregations not named are
                   summarised from linked ones along their own configured
                   aggregation path, and the region summary from the grid,
                   weighted by population.
sample points      from the first of the ``sample_points`` layers holding a
                   value for the point, by containment or, with ``within``,
                   the nearest feature within that many metres.  A value
                   brought down from an area is *replicated*: it describes the
                   area, not the point, and is recorded as such.

Outputs are named ``<prefix><column>`` on the area tables and
``sp_<prefix><column>`` in ``sample_points_linkage``.  Each column may be
given a ``label``, ``units``, ``statistic`` (one of the data dictionary's
``STATISTICS``), ``direction`` and ``description``; these are what the data
dictionary and the dashboard report for it (:func:`linked_variables`), and
nothing is inferred where they are not given.

Configuration::

    linkage_indicators:
      utci:
        data: MX/UTCI/mexicali_utci.gpkg
        match: id                  # id (default) | geometry
        id: area_id                # the source layers' identifier
        mask: reliable             # values set missing where this is false
        columns:
          utci_day_mean: {label: {en: ..., es: ...}, units: degC,
                          statistic: mean, direction: lower_is_better}
        areas:
          grid: grid_100m
          condesa_lotes: {layer: condesa_lotes, boundary_id: id}
        sample_points: [{layer: grid_100m}]
      external:
        data: MX/final_indicators.gpkg
        match: geometry
        reference: MX/reference_areas.gpkg   # layers named as the source's
        reference_layers: {grid: grid_100m}  # where a name differs
        prefix: ext_
        null_as: {pop_affected_flood: 0}
        columns: [ndvi, major_road_length_300m]
        ...

To run independently:  python subprocesses/_linkage_indicators.py <codename>
"""

import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd

CONFIG_KEY = 'linkage_indicators'
SAMPLE_POINT_TABLE = 'sample_points_linkage'
SAMPLE_POINT_PREFIX = 'sp_'
POINT_KEY = 'point_id'
AREA_KEY = 'area_id'
MATCHES = ('id', 'geometry')
# a source feature is matched by overlap only where at least this share of
# its area lies in one reference feature
MIN_SHARE = 0.5
NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
# the dashboard exporter reads meaning into these prefixes
RESERVED_PREFIXES = ('pop_', 'pct_', 'sp_', 'index_', 'avg_walk_', 'avg_')
SPEC_KEYS = {
    'data',
    'match',
    'id',
    'reference',
    'reference_layers',
    'reference_id',
    'prefix',
    'mask',
    'null_as',
    'columns',
    'areas',
    'sample_points',
    'min_share',
    'label',
    'source',
    'licence',
    'citation',
    'notes',
}
COLUMN_KEYS = {
    'label',
    'units',
    'statistic',
    'direction',
    'description',
    'breaks',
}
# as data_dictionary.STATISTICS, which a linked column's 'statistic' must be
STATISTICS = (
    'value',
    'mean',
    'median',
    'percentage',
    'count',
    'sum',
    'rate',
    'index',
    'category',
)


# ---------------------------------------------------------------------------
# Configuration


def _columns(value, name):
    """``columns`` as ``{column: metadata}``, from a list or a mapping."""
    if isinstance(value, str):
        value = [c.strip() for c in value.split(',') if c.strip()]
    if isinstance(value, list):
        value = {str(c): {} for c in value}
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"Linkage indicators '{name}' need 'columns': a list of column "
            'names, or a mapping of them to their labels and units.',
        )
    resolved = {}
    for column, meta in value.items():
        meta = dict(meta or {})
        unknown = set(meta) - COLUMN_KEYS
        if unknown:
            raise ValueError(
                f"Unknown settings {sorted(unknown)} for column '{column}' of "
                f"linkage indicators '{name}'.",
            )
        statistic = meta.get('statistic')
        if statistic is not None and statistic not in STATISTICS:
            raise ValueError(
                f"Unknown statistic '{statistic}' for column '{column}' of "
                f'linkage indicators \'{name}\' (expected one of '
                f'{", ".join(STATISTICS)}).',
            )
        resolved[str(column)] = meta
    return resolved


def _area(value, key, name):
    """An ``areas`` entry as ``{layer, boundary_id}``."""
    if isinstance(value, str):
        value = {'layer': value}
    if not isinstance(value, dict) or not value.get('layer'):
        raise ValueError(
            f"Area '{key}' of linkage indicators '{name}' needs a source "
            "'layer'.",
        )
    return {
        'layer': str(value['layer']),
        'boundary_id': value.get('boundary_id'),
    }


def _sample_point_layers(value, name):
    if value in (None, False):
        return []
    if isinstance(value, (str, dict)):
        value = [value]
    layers = []
    for item in value:
        if isinstance(item, str):
            item = {'layer': item}
        if not isinstance(item, dict) or not item.get('layer'):
            raise ValueError(
                f"Each sample_points entry of linkage indicators '{name}' "
                "needs a 'layer'.",
            )
        within = item.get('within')
        layers.append(
            {
                'layer': str(item['layer']),
                'within': None if within is None else float(within),
            },
        )
    return layers


def normalise_spec(name, spec):
    """Resolve one source of linkage indicators, filling defaults."""
    if not NAME_PATTERN.match(str(name)):
        raise ValueError(
            f"Invalid linkage indicators name '{name}': use lower-case "
            'letters, digits and underscores, starting with a letter.',
        )
    if not isinstance(spec, dict) or not spec.get('data'):
        raise ValueError(f"Linkage indicators '{name}' need 'data'.")
    unknown = set(spec) - SPEC_KEYS
    if unknown:
        raise ValueError(
            f"Unknown settings {sorted(unknown)} for linkage indicators "
            f"'{name}'.",
        )
    match = str(spec.get('match') or 'id').lower()
    if match not in MATCHES:
        raise ValueError(
            f"Unknown match '{match}' for linkage indicators '{name}' "
            f'(expected one of {MATCHES}).',
        )
    if match == 'geometry' and not spec.get('reference'):
        raise ValueError(
            f"Linkage indicators '{name}' are matched by geometry, and need "
            "a 'reference' file whose layers carry the identifiers.",
        )
    prefix = str(spec.get('prefix') or '')
    columns = _columns(spec.get('columns'), name)
    outputs = {}
    for column in columns:
        output = f'{prefix}{column}'.lower()
        if not NAME_PATTERN.match(output):
            raise ValueError(
                f"Linked column '{output}' is not a valid name: use "
                'lower-case letters, digits and underscores.',
            )
        if output.startswith(RESERVED_PREFIXES):
            raise ValueError(
                f"Linked column '{output}' begins with a prefix GHSCI gives a "
                "meaning to; set a 'prefix' for these indicators.",
            )
        if len(f'pop_{SAMPLE_POINT_PREFIX}{output}') > 63:
            raise ValueError(
                f"Linked column '{output}' is too long for PostgreSQL.",
            )
        outputs[column] = output
    null_as = dict(spec.get('null_as') or {})
    unknown = set(null_as) - set(columns)
    if unknown:
        raise ValueError(
            f"null_as names columns not linked: {sorted(unknown)}.",
        )
    areas = {
        str(key): _area(value, key, name)
        for key, value in (spec.get('areas') or {}).items()
    }
    return {
        'name': str(name),
        'data': str(spec['data']),
        'match': match,
        'id': str(spec.get('id') or AREA_KEY),
        'reference': spec.get('reference'),
        'reference_layers': dict(spec.get('reference_layers') or {}),
        'reference_id': str(spec.get('reference_id') or AREA_KEY),
        'min_share': float(spec.get('min_share', MIN_SHARE)),
        'prefix': prefix,
        'mask': spec.get('mask'),
        'null_as': null_as,
        'columns': columns,
        'outputs': outputs,
        'areas': areas,
        'sample_points': _sample_point_layers(spec.get('sample_points'), name),
        'label': spec.get('label'),
        'source': spec.get('source'),
        'licence': spec.get('licence'),
        'citation': spec.get('citation'),
        'notes': spec.get('notes'),
    }


def normalise_config(block):
    """Resolve a whole ``linkage_indicators`` block to ``{name: spec}``."""
    if not block:
        return {}
    if not isinstance(block, dict):
        raise ValueError(
            'linkage_indicators must be a mapping of names to linked sources.',
        )
    specs = {
        name: normalise_spec(name, spec)
        for name, spec in block.items()
        if spec is not False
    }
    seen = {}
    for name, spec in specs.items():
        for output in spec['outputs'].values():
            if output in seen:
                raise ValueError(
                    f"Linked column '{output}' is given by both "
                    f"'{seen[output]}' and '{name}'; set a 'prefix'.",
                )
            seen[output] = name
    return specs


def linkage_config(r):
    """The region's resolved linkage indicators, or None if none configured."""
    block = (getattr(r, 'config', None) or {}).get(CONFIG_KEY)
    return normalise_config(block) or None


def output_columns(specs):
    """Every linked column, as named on the area tables."""
    return [o for spec in specs.values() for o in spec['outputs'].values()]


def _english(value):
    if isinstance(value, dict):
        return value.get('en') or next(iter(value.values()), '')
    return value or ''


def linked_variables(specs):
    """Describe every linked output variable, from its configuration alone.

    Returns ``{variable: {...}}`` for each form a linked column takes: the
    area column (``<prefix><column>``, as delivered or, for aggregations not
    delivered, summarised along their own aggregation), the sample point
    column (``sp_<prefix><column>``, replicated from the area containing the
    point) and the city summary (``pop_<prefix><column>``, the population
    weighted mean of the grid's values; see :func:`summarise_city`).

    Each carries its ``description`` (the configured description, else its
    label, else its name), ``label``, ``units``, ``statistic`` and
    ``direction`` as configured -- left empty where not configured, never
    inferred -- and the linked source's ``source``, ``licence``,
    ``citation`` and ``data``.  The city summary's statistic is 'mean', as
    that is how it is calculated.
    """
    variables = {}
    for name, spec in (specs or {}).items():
        provenance = {
            'linked': name,
            'source': spec.get('source') or '',
            'licence': spec.get('licence') or '',
            'citation': spec.get('citation') or '',
            'data': spec.get('data') or '',
        }
        for column, meta in spec['columns'].items():
            output = spec['outputs'][column]
            description = (
                _english(meta.get('description'))
                or _english(meta.get('label'))
                or column.replace('_', ' ')
            )
            base = {
                'label': meta.get('label'),
                'units': str(meta.get('units') or ''),
                'statistic': meta.get('statistic') or '',
                'direction': meta.get('direction') or '',
                **provenance,
            }
            variables[output] = {
                **base,
                'form': 'area',
                'description': description,
            }
            variables[f'{SAMPLE_POINT_PREFIX}{output}'] = {
                **base,
                'form': 'sample point',
                'description': (
                    f'{description} (replicated at the sample point from the '
                    'linked area containing it)'
                ),
            }
            variables[f'pop_{output}'] = {
                **base,
                'statistic': 'mean',
                'form': 'city',
                'description': (
                    f'{description} (population weighted mean of the linked '
                    'grid values)'
                ),
            }
    return variables


# ---------------------------------------------------------------------------
# Matching and preparing source layers (no database needed)


def _normalised_wkb(geometries):
    return geometries.normalize().to_wkb()


def match_by_geometry(
    source,
    reference,
    reference_id=AREA_KEY,
    min_share=MIN_SHARE,
):
    """Identify source features with reference features by their geometry.

    A source feature identical to a reference feature (once both are
    normalised) takes its identifier.  Any other takes the identifier of the
    reference feature holding the largest share of its area, where that share
    is at least ``min_share``; otherwise it is left unmatched.

    Returns ``(ids, shares, report)``: identifiers and matched shares indexed
    like ``source`` (missing where unmatched), and counts of features matched
    exactly, by overlap and not at all, and of reference identifiers matched
    more than once.
    """
    import geopandas as gpd

    if reference.crs is not None and source.crs != reference.crs:
        source = source.to_crs(reference.crs)
    ids = pd.Series(pd.NA, index=source.index, dtype='object')
    shares = pd.Series(np.nan, index=source.index, dtype='float64')
    keys = pd.Series(
        reference[reference_id].astype(str).values,
        index=_normalised_wkb(reference.geometry),
    )
    keys = keys[~keys.index.duplicated()]
    exact = pd.Series(
        _normalised_wkb(source.geometry),
        index=source.index,
    ).map(keys)
    found = exact.notna()
    ids[found] = exact[found]
    shares[found] = 1.0
    rest = source.loc[~found]
    overlap = 0
    if len(rest):
        left = gpd.GeoDataFrame(
            {'_row': rest.index},
            geometry=rest.geometry.values,
            crs=source.crs,
        )
        left['_area'] = left.geometry.area
        right = gpd.GeoDataFrame(
            {'_id': reference[reference_id].astype(str).values},
            geometry=reference.geometry.values,
            crs=reference.crs,
        )
        pieces = gpd.overlay(
            left,
            right,
            how='intersection',
            keep_geom_type=True,
        )
        if len(pieces):
            pieces['_share'] = pieces.geometry.area / pieces['_area']
            best = pieces.sort_values('_share').groupby('_row').tail(1)
            best = best[best['_share'] >= min_share].set_index('_row')
            ids[best.index] = best['_id']
            shares[best.index] = best['_share']
            overlap = len(best)
    matched = ids.dropna()
    report = {
        'features': int(len(source)),
        'exact': int(found.sum()),
        'overlap': int(overlap),
        'unmatched': int(len(source) - found.sum() - overlap),
        'shared_ids': int(
            matched.duplicated(keep=False).groupby(matched).any().sum(),
        ),
    }
    return ids, shares, report


def combine_matched(frame, ids, columns):
    """One row per identifier: several features matched to one are combined.

    Parts of one reference feature delivered as separate features are
    combined as a mean weighted by their area, since each describes its own
    part of the whole.
    """
    frame = frame.assign(**{AREA_KEY: ids}).dropna(subset=[AREA_KEY])
    if not frame[AREA_KEY].duplicated().any():
        return frame
    weight = frame.geometry.area
    parts = []
    for column in columns:
        values = pd.to_numeric(frame[column], errors='coerce')
        valid = values.notna()
        numerator = (
            (values.fillna(0) * weight * valid).groupby(frame[AREA_KEY]).sum()
        )
        denominator = (weight * valid).groupby(frame[AREA_KEY]).sum()
        parts.append(
            (numerator / denominator.replace(0, np.nan)).rename(column),
        )
    combined = pd.concat(parts, axis=1)
    geometry = frame.dissolve(by=AREA_KEY).geometry
    import geopandas as gpd

    return gpd.GeoDataFrame(
        combined.join(geometry).reset_index(),
        geometry='geometry',
        crs=frame.crs,
    )


def apply_rules(frame, spec):
    """Mask unreliable values and fill missing values as configured."""
    columns = [c for c in spec['columns'] if c in frame.columns]
    frame = frame.copy()
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    # Filled before masking, so that an unreliable value stays missing rather
    # than reading as 'none'.  A layer in which a column is entirely missing
    # does not measure it at all, and filling it there would hide the layers
    # that do: a grid with no flood values would give every sample point "no
    # exposure" before the blocks that record flooding were ever consulted.
    for column, value in spec['null_as'].items():
        if column in frame.columns and frame[column].notna().any():
            frame[column] = frame[column].fillna(value)
    if spec['mask']:
        if spec['mask'] not in frame.columns:
            raise ValueError(
                f"Mask column '{spec['mask']}' not found in linkage "
                f"indicators '{spec['name']}'.",
            )
        keep = frame[spec['mask']].fillna(False).astype(bool)
        frame.loc[~keep, columns] = np.nan
    return frame


def sample_point_values(points, layers):
    """Values for sample points from an ordered list of area layers.

    ``layers`` is a list of ``(frame, within)`` pairs: each frame holds a
    geometry and value columns, and ``within`` is None to match points the
    feature contains, or a distance to match the nearest feature within it.
    A point takes each column's value from the first layer holding one for
    it.  Returns a frame indexed like ``points``.
    """
    import geopandas as gpd

    out = pd.DataFrame(index=points.index)
    for frame, within in layers:
        columns = [c for c in frame.columns if c not in ('geometry', AREA_KEY)]
        if frame.crs is not None and points.crs != frame.crs:
            frame = frame.to_crs(points.crs)
        left = gpd.GeoDataFrame(geometry=points.geometry, crs=points.crs)
        right = frame[columns + ['geometry']]
        if within is None:
            joined = gpd.sjoin(left, right, how='left', predicate='within')
        else:
            joined = gpd.sjoin_nearest(
                left,
                right,
                how='left',
                max_distance=within,
            )
        # a point on a shared edge may meet two features: take the first
        joined = joined[~joined.index.duplicated(keep='first')]
        for column in columns:
            values = joined[column].reindex(points.index)
            if column in out:
                out[column] = out[column].fillna(values)
            else:
                out[column] = values
    return out


# ---------------------------------------------------------------------------
# Database


def _data_source(path):
    if os.path.isabs(path) or os.path.exists(path):
        return path
    import ghsci

    return f'{ghsci.data_path}/{path}'


def read_layer(spec, layer, srid):
    """A source layer, with identifiers, rules applied, in the project CRS.

    Returns ``(frame, report)``; the frame holds ``area_id``, the linked
    columns present in the layer and the geometry.
    """
    import geopandas as gpd

    frame = gpd.read_file(_data_source(spec['data']), layer=layer)
    if frame.crs is None or frame.crs.to_epsg() != int(srid):
        frame = frame.to_crs(int(srid))
    frame = apply_rules(frame, spec)
    columns = [c for c in spec['columns'] if c in frame.columns]
    report = {'layer': layer, 'columns': columns}
    if spec['match'] == 'geometry':
        reference_layer = spec['reference_layers'].get(layer, layer)
        reference = gpd.read_file(
            _data_source(spec['reference']),
            layer=reference_layer,
        )
        if reference.crs is None or reference.crs.to_epsg() != int(srid):
            reference = reference.to_crs(int(srid))
        ids, _, matched = match_by_geometry(
            frame,
            reference,
            spec['reference_id'],
            spec['min_share'],
        )
        report.update(matched)
        frame = combine_matched(frame[columns + ['geometry']], ids, columns)
    else:
        if spec['id'] not in frame.columns:
            raise ValueError(
                f"Identifier '{spec['id']}' not found in layer '{layer}' of "
                f"linkage indicators '{spec['name']}'.",
            )
        frame = frame.rename(columns={spec['id']: AREA_KEY})
        frame[AREA_KEY] = frame[AREA_KEY].astype(str).str.strip()
        report.update(
            features=int(len(frame)),
            shared_ids=int(frame[AREA_KEY].duplicated().sum()),
        )
    frame = frame[[AREA_KEY] + columns + ['geometry']]
    return frame.rename(columns=spec['outputs']), report


def _table_columns(r, table):
    found = r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_schema = 'public' AND table_name = '{table}' "
        'ORDER BY ordinal_position',
    )['column_name'].tolist()
    return found


def area_table(r, key):
    """The summary table of an aggregation key and its identifier column."""
    if key == 'grid':
        return r.config['grid_summary'], 'grid_id'
    table = f'indicators_{str(key).lower()}'
    columns = _table_columns(r, table)
    if not columns:
        return None, None
    return table, columns[0]


def write_area_values(r, table, boundary_id, frame, columns):
    """Add linked columns to an area table and fill them by identifier.

    Returns ``(areas, matched)``: the number of areas and of those linked.
    """
    from sqlalchemy import text

    staging = f'_linkage_{table}'[:63]
    frame[[AREA_KEY] + columns].to_sql(
        staging,
        r.engine,
        if_exists='replace',
        index=False,
    )
    key = f'trim(b."{boundary_id}"::text)'
    with r.engine.begin() as connection:
        for column in columns:
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS '
                    f'"{column}" double precision',
                ),
            )
        # refreshed, not merged: values from a previous linkage do not linger
        connection.execute(
            text(
                f'UPDATE "{table}" SET '
                + ', '.join(f'"{c}" = NULL' for c in columns),
            ),
        )
        connection.execute(
            text(
                f'UPDATE "{table}" b SET '
                + ', '.join(f'"{c}" = t."{c}"' for c in columns)
                + f' FROM "{staging}" t WHERE {key} = t."{AREA_KEY}"',
            ),
        )
        areas, matched = connection.execute(
            text(
                f'SELECT COUNT(*), COUNT(t."{AREA_KEY}") FROM "{table}" b '
                f'LEFT JOIN "{staging}" t ON {key} = t."{AREA_KEY}"',
            ),
        ).fetchone()
        connection.execute(text(f'DROP TABLE IF EXISTS "{staging}"'))
    return int(areas), int(matched)


def summarise_missing_areas(r, columns, linked, plans):
    """Summarise linked columns for aggregations without a source layer.

    Each is summarised from its own configured source -- the grid, another
    area, or sample points -- by the same rule as every other indicator, in
    the order the areas were built, so an area sourced from another reads
    values already linked.
    """
    from _12_aggregation import _custom_area_query
    from sqlalchemy import text

    summarised = []
    for plan in plans or []:
        if plan['name'] in linked or plan['table'] not in r.get_tables():
            continue
        area_id = _table_columns(r, plan['table'])[0]
        if plan['agg_kind'] == 'point':
            source = SAMPLE_POINT_TABLE
            source_columns = [f'{SAMPLE_POINT_PREFIX}{c}' for c in columns]
            predicate = (
                f'ST_DWithin(b.geom, s.geom, {int(plan["agg_distance"])})'
                if plan['agg_distance'] is not None
                else 'ST_Intersects(b.geom, s.geom)'
            )
        else:
            source = (
                r.config['grid_summary']
                if plan['agg_kind'] == 'grid'
                else plan['source_table']
            )
            source_columns = columns
            predicate = 'ST_Intersects(b.geom, s.geom)'
        present = set(_table_columns(r, source))
        usable = [
            (c, s) for c, s in zip(columns, source_columns) if s in present
        ]
        if not usable:
            continue
        query = _custom_area_query(
            plan,
            plan['table'],
            area_id,
            source,
            predicate,
            [c for c, _ in usable],
            [s for _, s in usable],
            lambda column: 1.0,
        )
        with r.engine.begin() as connection:
            for column, _ in usable:
                connection.execute(
                    text(
                        f'ALTER TABLE "{plan["table"]}" ADD COLUMN IF NOT '
                        f'EXISTS "{column}" double precision',
                    ),
                )
            connection.execute(
                text(
                    f'UPDATE "{plan["table"]}" a SET '
                    + ', '.join(f'"{c}" = t."{c}"' for c, _ in usable)
                    + f' FROM ({query}) t WHERE a."{area_id}" = t.area_key',
                ),
            )
        linked.add(plan['name'])
        summarised.append(f'{plan["name"]} (from {plan["agg_kind"]})')
    return summarised


def summarise_city(r, columns):
    """Population weighted city summaries of linked grid values."""
    from sqlalchemy import text

    grid = r.config['grid_summary']
    present = [c for c in columns if c in set(_table_columns(r, grid))]
    if not present:
        return
    frame = r.get_df(
        'SELECT pop_est, '
        + ', '.join(f'"{c}"' for c in present)
        + f' FROM "{grid}"',
    )
    city = {}
    for column in present:
        valid = frame[column].notna()
        weight = frame.loc[valid, 'pop_est']
        city[f'pop_{column}'] = (
            float((weight * frame.loc[valid, column]).sum() / weight.sum())
            if weight.sum() > 0
            else None
        )
    summary = r.config['city_summary']
    with r.engine.begin() as connection:
        for column in city:
            connection.execute(
                text(
                    f'ALTER TABLE "{summary}" ADD COLUMN IF NOT EXISTS '
                    f'"{column}" double precision',
                ),
            )
        connection.execute(
            text(
                f'UPDATE "{summary}" SET '
                + ', '.join(
                    f'"{c}" = ' + ('NULL' if v is None else repr(v))
                    for c, v in city.items()
                ),
            ),
        )


def link_indicators(r, plans=None):
    """Link the region's configured linkage indicators to every scale.

    Returns a report of how each source layer matched and where its values
    were written, which is also recorded as the comment on the
    ``sample_points_linkage`` table.
    """
    import geopandas as gpd
    from sqlalchemy import text

    specs = linkage_config(r)
    if specs is None:
        print('No linkage indicators are configured for this region.')
        return {}
    if plans is None:
        from _12_aggregation import load_aggregation_plans

        plans = load_aggregation_plans(r)
    srid = r.config['crs']['srid']
    points = r.get_gdf(
        f'SELECT {POINT_KEY}, grid_id, geom FROM urban_sample_points',
        index_col=POINT_KEY,
    )
    point_values = []
    report = {}
    for name, spec in specs.items():
        print(f"\n  - {name}: {spec['data']}")
        layers, entry = {}, {'areas': {}, 'layers': {}}

        def layer(source_layer):
            if source_layer not in layers:
                frame, matched = read_layer(spec, source_layer, srid)
                layers[source_layer] = frame
                entry['layers'][source_layer] = matched
                if spec['match'] == 'geometry':
                    print(
                        f"      {source_layer}: {matched['exact']:,} matched "
                        f"exactly, {matched['overlap']:,} by overlap, "
                        f"{matched['unmatched']:,} unmatched of "
                        f"{matched['features']:,}"
                        + (
                            f"; {matched['shared_ids']:,} identifiers shared "
                            'by several features (combined)'
                            if matched['shared_ids']
                            else ''
                        ),
                    )
            return layers[source_layer]

        columns = list(spec['outputs'].values())
        linked = set()
        for key, area in spec['areas'].items():
            table, boundary_id = area_table(r, key)
            if table is None:
                print(f'      {key}: no summary table; skipped')
                continue
            frame = layer(area['layer'])
            present = [c for c in columns if c in frame.columns]
            areas, matched = write_area_values(
                r,
                table,
                area['boundary_id'] or boundary_id,
                frame,
                present,
            )
            linked.add(key)
            entry['areas'][key] = {
                'layer': area['layer'],
                'areas': areas,
                'linked': matched,
            }
            print(
                f"      {key} <- {area['layer']}: {matched:,} of {areas:,} "
                f'areas linked ({len(present)} columns)',
            )
        # sample points first: an area summarised from sample points reads them
        sp_layers = [
            (layer(item['layer']), item['within'])
            for item in spec['sample_points']
        ]
        if sp_layers:
            values = sample_point_values(points, sp_layers)
            values = values[[c for c in columns if c in values]]
            # missing values are filled once every layer has been consulted
            for column, value in spec['null_as'].items():
                output = spec['outputs'][column]
                if output in values:
                    values[output] = values[output].fillna(value)
            point_values.append(
                values.add_prefix(SAMPLE_POINT_PREFIX),
            )
            entry['sample_points'] = {
                'layers': spec['sample_points'],
                'replicated': True,
                'valued': {
                    c: int(values[c].notna().sum()) for c in values.columns
                },
            }
        report[name] = entry
    if point_values:
        table = gpd.GeoDataFrame(
            pd.concat([points[['grid_id']], *point_values], axis=1),
            geometry=points.geometry,
            crs=points.crs,
        ).rename_geometry('geom')
        table.index.name = POINT_KEY
        with r.engine.connect() as connection:
            table.to_postgis(
                SAMPLE_POINT_TABLE,
                connection,
                index=True,
                if_exists='replace',
            )
        print(
            f'\n  Sample points: {len(table):,} valued for '
            f'{len(table.columns) - 2} linked indicators (replicated from '
            'the areas containing them)',
        )
    for name, spec in specs.items():
        columns = list(spec['outputs'].values())
        linked = set(report[name]['areas'])
        summarised = summarise_missing_areas(r, columns, linked, plans)
        if summarised:
            print(f'  - {name}: summarised for ' + ', '.join(summarised))
        report[name]['summarised'] = summarised
        summarise_city(r, columns)
    if point_values:
        comment = json.dumps(report).replace("'", "''").replace(':', r'\:')
        with r.engine.begin() as connection:
            connection.execute(
                text(f"COMMENT ON TABLE {SAMPLE_POINT_TABLE} IS '{comment}'"),
            )
    return report


def main():
    import ghsci
    from script_running_log import script_running_log

    start = time.time()
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    r = ghsci.Region(codename)
    link_indicators(r)
    script_running_log(
        r.config,
        '_linkage_indicators',
        'Linkage indicators',
        start,
    )
    r.engine.dispose()


if __name__ == '__main__':
    main()
