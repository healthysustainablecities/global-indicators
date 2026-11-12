"""
Walkability at chosen distances, and variants that account for heat.

Optional GHSCI step, gated by a region's ``walkability_variants`` block.  The
GHSCI walkability index (``sp_walkability_index``) is the sum of the z-scores
of a daily living score -- access within 500 m to a fresh food market, a
convenience store and public transport -- local population density and street
intersection density (after Frank et al. 2010).  Where the distance people will
walk is shorter, as it is in a hot, arid city, the daily living score can be
judged at other distances; and where heat bears on walking, walkability can be
read together with it.  Both are configured here, so that each is a named,
reproducible variable rather than an ad hoc recalculation.

For each distance ``d``::

    W_d = z(daily living within d) + z(population density)
          + z(intersection density)

z-scores are taken across every sample point with a value, as they are for the
GHSCI index itself (_11_neighbourhood_analysis).  Each set of heat measures
``h`` (lower is better: heat vulnerability, or thermal stress) then adjusts it
in one of two forms:

``additive``
    ``W_d + sum(z(-h))``: heat enters as a further component of the index, on
    the same footing as the others.  It is compensatory -- a cooler street
    makes up for fewer destinations -- which is the form of the walkability
    index itself.
``multiplicative`` (attenuation)
    ``F(W_d) * prod(1 - lambda * h')``, where ``F`` is the percentile rank of
    ``W_d`` (0-1], ``h'`` heat re-scaled to 0-1 between the city's 5th and
    95th percentiles -- or between a fixed ``range`` given for the measure,
    in its own units -- and ``lambda`` the attenuation at the hottest
    (default 0.5: the hottest location keeps half its walkability).  A fixed
    range judges heat absolutely: where every place is hot, as on a 48 °C
    day, the percentiles would spread a degree or two across the whole scale
    and treat the least hot as if it were comfortable.  Heat reduces how
    walkable a place is rather than adding to it, so no amount of shade makes
    up for having nothing to walk to -- after measures of accessibility in
    which heat stress shortens the distance people will walk.

Writes ``sample_points_walkability``:

    sp_walk_dl_<d>              daily living score within d (0-n destinations)
    sp_walk_idx_<d>             walkability at d
    sp_walk_idx_<d>_<set><form> heat adjusted, e.g. sp_walk_idx_300_ga for
                                GUHVI (g), additive (a)

aggregated to ``walk_dl_<d>`` and ``walk_idx_<...>`` on every scale.  The
bounds each heat measure was re-scaled between (in its own units, e.g. degrees
C for UTCI), and its observed 5th and 95th percentiles, are recorded in the
table's comment with the attenuation, so that what attenuation means can be
shown (:func:`recorded_bounds`).

Configuration::

    walkability_variants:
      distances: [300, 500]
      daily_living: [fresh_food_market, convenience, pt_any]
      heat:
        g: {variable: sp_urban_heat_guhvi, label: {en: GUHVI, es: GUHVI}}
        t: {variable: sp_utci_day_mean, range: [30, 50]}
      sets: [g, t, gt]           # letters of the heat measures combined
      forms: [additive, multiplicative]
      attenuation: 0.5
      percentiles: [5, 95]

To run independently:  python subprocesses/_walkability_variants.py <codename>
"""

import json
import sys
import time

import numpy as np
import pandas as pd

CONFIG_KEY = 'walkability_variants'
SAMPLE_POINT_TABLE = 'sample_points_walkability'
POINT_KEY = 'point_id'
INDEX_PREFIX = 'sp_walk_idx_'
DAILY_LIVING_PREFIX = 'sp_walk_dl_'
ACCESS_PREFIX = 'sp_walk_access_'
DENSITIES = (
    'sp_local_nh_avg_pop_density',
    'sp_local_nh_avg_intersection_density',
)
DAILY_LIVING = ('fresh_food_market', 'convenience', 'pt_any')
FORMS = {'additive': 'a', 'multiplicative': 'm'}
ATTENUATION = 0.5
PERCENTILES = (5, 95)
KEYS = {
    'distances',
    'daily_living',
    'densities',
    'heat',
    'sets',
    'forms',
    'attenuation',
    'percentiles',
}


def normalise_config(block):
    """Resolve a ``walkability_variants`` block, filling defaults."""
    if not block:
        return None
    if block is True:
        block = {}
    if not isinstance(block, dict):
        raise ValueError('walkability_variants must be a mapping.')
    unknown = set(block) - KEYS
    if unknown:
        raise ValueError(
            f'Unknown walkability_variants settings: {sorted(unknown)}.',
        )
    distances = [int(d) for d in block.get('distances') or [500]]
    if any(d <= 0 for d in distances) or len(set(distances)) != len(distances):
        raise ValueError(
            'walkability_variants distances must be distinct positive metres.',
        )
    heat = {}
    for letter, measure in (block.get('heat') or {}).items():
        letter = str(letter)
        if len(letter) != 1 or not letter.isalpha() or letter in 'am':
            raise ValueError(
                f"Heat measure key '{letter}' must be a single letter other "
                "than 'a' and 'm', which name the forms.",
            )
        if isinstance(measure, str):
            measure = {'variable': measure}
        if not isinstance(measure, dict) or not measure.get('variable'):
            raise ValueError(f"Heat measure '{letter}' needs a 'variable'.")
        fixed = measure.get('range')
        if fixed is not None:
            try:
                fixed = [float(fixed[0]), float(fixed[1])]
            except (TypeError, ValueError, IndexError, KeyError):
                fixed = None
            if not fixed or not fixed[1] > fixed[0]:
                raise ValueError(
                    f"Heat measure '{letter}' range must be [low, high], "
                    'low below high.',
                )
        heat[letter] = {
            'variable': str(measure['variable']),
            'label': measure.get('label'),
            'range': fixed,
        }
    sets = [str(s) for s in block.get('sets') or []]
    for combination in sets:
        if not combination or any(c not in heat for c in combination):
            raise ValueError(
                f"Heat set '{combination}' names a measure not configured "
                f'(configured: {sorted(heat)}).',
            )
    forms = [str(f).lower() for f in block.get('forms') or list(FORMS)]
    unknown = set(forms) - set(FORMS)
    if unknown:
        raise ValueError(
            f'Unknown walkability forms {sorted(unknown)} (expected '
            f'{list(FORMS)}).',
        )
    attenuation = float(block.get('attenuation', ATTENUATION))
    if not 0 < attenuation <= 1:
        raise ValueError('walkability_variants attenuation must be in (0, 1].')
    percentiles = tuple(
        float(p) for p in block.get('percentiles', PERCENTILES)
    )
    if (
        len(percentiles) != 2
        or not 0 <= percentiles[0] < percentiles[1] <= 100
    ):
        raise ValueError(
            'walkability_variants percentiles must be [low, high] in 0-100.',
        )
    return {
        'distances': distances,
        'daily_living': [
            str(n) for n in block.get('daily_living') or DAILY_LIVING
        ],
        'densities': [str(v) for v in block.get('densities') or DENSITIES],
        'heat': heat,
        'sets': sets,
        'forms': forms,
        'attenuation': attenuation,
        'percentiles': percentiles,
    }


def walkability_config(r):
    return normalise_config((getattr(r, 'config', None) or {}).get(CONFIG_KEY))


def variant_column(distance, combination=None, form=None):
    """The sample point column of walkability at a distance, or a variant."""
    column = f'{INDEX_PREFIX}{int(distance)}'
    if combination:
        column += f'_{combination}{FORMS[form]}'
    return column


def variants(config):
    """Every variant configured, as plain descriptions.

    ``{column, distance, heat: [letters], form}``, the unadjusted index at
    each distance first.
    """
    out = []
    for distance in config['distances']:
        out.append(
            {
                'column': variant_column(distance),
                'distance': distance,
                'heat': [],
                'form': None,
            },
        )
        for combination in config['sets']:
            for form in config['forms']:
                out.append(
                    {
                        'column': variant_column(distance, combination, form),
                        'distance': distance,
                        'heat': list(combination),
                        'form': form,
                    },
                )
    return out


def input_variables(config):
    """Every sample point variable the configured variants read."""
    access = [
        f'{ACCESS_PREFIX}{name}_{distance}m'
        for distance in config['distances']
        for name in config['daily_living']
    ]
    heat = [m['variable'] for m in config['heat'].values()]
    return access + config['densities'] + heat


def zscore(values):
    """z-scores as the GHSCI walkability index takes them (sample SD)."""
    values = pd.to_numeric(values, errors='coerce').astype('float64')
    sd = values.std()
    if not sd > 0:
        return values * np.nan
    return (values - values.mean()) / sd


def percentile_bounds(values, percentiles=PERCENTILES):
    """The values at two percentiles, between which heat is re-scaled."""
    values = pd.to_numeric(values, errors='coerce').astype('float64')
    if not values.notna().any():
        return (np.nan, np.nan)
    low, high = np.nanpercentile(values, percentiles)
    return (float(low), float(high))


def rescale(values, percentiles=PERCENTILES, fixed=None):
    """Re-scale to 0-1 between two percentiles (or ``fixed`` bounds), clipped."""
    values = pd.to_numeric(values, errors='coerce').astype('float64')
    low, high = fixed or percentile_bounds(values, percentiles)
    if not high > low:
        return values * 0.0
    return ((values - low) / (high - low)).clip(0, 1)


def percentile_rank(values):
    """Percentile rank on (0, 1], ties sharing their average rank."""
    return pd.to_numeric(values, errors='coerce').rank(pct=True)


def compute_variants(frame, config):
    """Walkability and its heat adjusted variants for each sample point.

    ``frame`` holds the variables of :func:`input_variables`.  Returns a frame
    with a daily living score and a walkability index per distance, and each
    configured variant.  The frame's ``attrs['heat_bounds']`` records, for
    each heat measure, the percentile values it was re-scaled between.
    """
    out = {}
    density = sum(zscore(frame[v]) for v in config['densities'])
    heat = {
        letter: pd.to_numeric(frame[m['variable']], errors='coerce')
        for letter, m in config['heat'].items()
    }
    heat_z = {letter: zscore(values) for letter, values in heat.items()}
    heat_scaled = {
        letter: rescale(
            values,
            config['percentiles'],
            config['heat'][letter].get('range'),
        )
        for letter, values in heat.items()
    }
    for distance in config['distances']:
        access = pd.concat(
            [
                pd.to_numeric(
                    frame[f'{ACCESS_PREFIX}{name}_{distance}m'],
                    errors='coerce',
                )
                for name in config['daily_living']
            ],
            axis=1,
        )
        # a point with no access value for a destination has none recorded:
        # missing, not zero, as for the GHSCI daily living score
        daily_living = access.sum(axis=1, min_count=access.shape[1])
        out[f'{DAILY_LIVING_PREFIX}{distance}'] = daily_living
        walkability = zscore(daily_living) + density
        out[variant_column(distance)] = walkability
        rank = percentile_rank(walkability)
        for combination in config['sets']:
            for form in config['forms']:
                if form == 'additive':
                    # lower heat is better, so its z-score counts against
                    value = walkability - sum(heat_z[c] for c in combination)
                else:
                    value = rank
                    for c in combination:
                        value = value * (
                            1 - config['attenuation'] * heat_scaled[c]
                        )
                out[variant_column(distance, combination, form)] = value
    result = pd.DataFrame(out, index=frame.index)
    result.attrs['heat_bounds'] = {}
    for letter, values in heat.items():
        observed = list(percentile_bounds(values, config['percentiles']))
        fixed = config['heat'][letter].get('range')
        result.attrs['heat_bounds'][letter] = {
            'variable': config['heat'][letter]['variable'],
            'bounds': list(fixed) if fixed else observed,
            'basis': 'range' if fixed else 'percentiles',
            'observed': observed,
        }
    return result


def parameters(config, heat_bounds):
    """What the variants were computed with, as recorded with them."""
    return {
        'attenuation': config['attenuation'],
        'percentiles': list(config['percentiles']),
        'heat': {
            letter: {
                'variable': measure['variable'],
                'label': measure.get('label'),
                'bounds': (heat_bounds.get(letter) or {}).get('bounds'),
                'basis': (heat_bounds.get(letter) or {}).get('basis'),
                'observed': (heat_bounds.get(letter) or {}).get('observed'),
            }
            for letter, measure in config['heat'].items()
        },
    }


def recorded_bounds(r):
    """The parameters recorded with a region's walkability variants, or {}."""
    if SAMPLE_POINT_TABLE not in r.get_tables():
        return {}
    comment = r.get_df(
        f"SELECT obj_description('{SAMPLE_POINT_TABLE}'::regclass) AS c",
    )['c'].iloc[0]
    try:
        return json.loads(comment) if comment else {}
    except ValueError:
        return {}


def compute(r, plans=None, write=True):
    """Compute a region's walkability variants and summarise them."""
    from _composite_index import load_variables

    config = walkability_config(r)
    if config is None:
        print('No walkability variants are configured for this region.')
        return None
    frame = load_variables(
        r,
        input_variables(config),
        what='Walkability variant inputs',
    )
    result = compute_variants(frame, config)
    for column in result.columns:
        if column.startswith(INDEX_PREFIX):
            print(
                f'  {column}: {int(result[column].notna().sum()):,} of '
                f'{len(result):,} sample points',
            )
    recorded = parameters(config, result.attrs.get('heat_bounds') or {})
    for letter, measure in recorded['heat'].items():
        if measure['bounds']:
            low, high = measure['bounds']
            basis = (
                'a fixed range'
                if measure['basis'] == 'range'
                else f'P{config["percentiles"][0]:g}-'
                f'P{config["percentiles"][1]:g}'
            )
            print(
                f"  heat '{letter}' ({measure['variable']}) re-scaled between "
                f'{low:.2f} and {high:.2f} ({basis})',
            )
    if not write:
        return result
    table = pd.concat([frame[['grid_id', 'geom']], result], axis=1)
    table = table.set_geometry('geom')
    table.index.name = POINT_KEY
    with r.engine.connect() as connection:
        table.to_postgis(
            SAMPLE_POINT_TABLE,
            connection,
            index=True,
            if_exists='replace',
        )
    from sqlalchemy import text

    comment = json.dumps(recorded).replace("'", "''").replace(':', r'\:')
    with r.engine.begin() as connection:
        connection.execute(
            text(f"COMMENT ON TABLE {SAMPLE_POINT_TABLE} IS '{comment}'"),
        )
    from _12_aggregation import (
        _propagate_sample_point_columns,
        load_aggregation_plans,
    )

    if plans is None:
        plans = load_aggregation_plans(r)
    _propagate_sample_point_columns(
        r,
        SAMPLE_POINT_TABLE,
        [
            (INDEX_PREFIX, 'walk_idx_', False),
            (DAILY_LIVING_PREFIX, 'walk_dl_', False),
        ],
        'walkability',
        plans,
    )
    return result


def main():
    import ghsci
    from script_running_log import script_running_log

    start = time.time()
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    r = ghsci.Region(codename)
    compute(r)
    script_running_log(
        r.config,
        '_walkability_variants',
        'Walkability variants',
        start,
    )
    r.engine.dispose()


if __name__ == '__main__':
    main()
