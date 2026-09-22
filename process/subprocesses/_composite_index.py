"""
Composite indices: the Mazziotta-Pareto Index family.

Optional GHSCI step, configured by a region's ``composite_indices`` block, that
summarises a set of sample point indicators as a non-compensatory composite
index: the mean of the normalised indicators, penalised for how unbalanced
they are, so that doing well on some cannot wholly make up for doing badly on
the rest.  This is the approach of the Urban Liveability Index (Higgs et al.
2019, International Journal of Health Geographics 18:14), which applied the
Mazziotta-Pareto Index (MPI; De Muro, Mazziotta & Pareto 2011).

Two normalisations are offered.

``ampi`` (default)
    The Adjusted MPI (Mazziotta & Pareto 2018, Social Indicators Research
    136:967-976).  Each indicator is re-scaled against two goalposts::

        r = 100 +/- 60 (x - Ref) / (Max - Min)

    By default the goalposts span the observed range of the indicator across
    every unit (and, for a series, every timepoint), centred on a reference
    value (the mean) so that 100 reads as 'the reference'.  Once goalposts are
    fixed, a unit's score depends only on its own values, which is what makes
    scores comparable in absolute terms over time.  Every run records the
    goalposts it used, so they can be frozen for later timepoints.

``mpi``
    The classic MPI, standardising each indicator as z-scores::

        z = 100 +/- 10 (x - M) / S

    Comparisons over time are relative only.  The conditional scaling of
    outliers used for the Urban Liveability Index is applied by default.

Scores are aggregated using the weighted form of Mazziotta & Pareto (2022,
Rivista Italiana di Economia Demografia e Statistica 76(4):17-26), which
reduces to the classic indices when weights are equal::

    M = sum(w r);  S = sqrt(sum(w (r - M)^2));  cv = S / M
    index = M - S cv   (a 'positive' phenomenon such as liveability)
    index = M + S cv   (a 'negative' phenomenon such as deprivation)

An index may group its indicators into domains: each domain is scored as a
composite of its indicators, and the index as a composite of the domain
scores.  Domain scores are already on the common scale centred at 100, so they
are not normalised a second time.

The index is computed for each sample point and then averaged to the grid,
custom areas and the city like any other sample point indicator (``sp_index_``
to ``index_`` and ``pop_index_``).  Access to a destination is better
represented for this purpose by a distance passed through a soft threshold
than by binary access, which is either 0 or 1 at a single point.

Configuration::

    composite_indices:
      uli:
        label: Urban Liveability Index
        method: ampi            # ampi (default) | mpi
        phenomenon: positive    # positive (default) | negative
        reference: mean         # mean (default) | median
        outliers: none          # none (ampi default) | compress (mpi default)
        min_indicators: all     # all (default) | minimum valid per domain
        colour: '#4E8EF7'       # optional presentation colour of the index
        domains:                # or a flat 'indicators' list
          daily_living:
            weight: 1
            colour: {fill: '#FFE7C2', stroke: '#FFBD59'}   # optional
            indicators:
              - variable: sp_walk_nearest_node_denue_fresh_food
                transform: {soft_threshold: 300}
                subdomain: {en: Food environment, es: Alimentación}
              - {variable: sp_urban_heat_guhvi, polarity: negative,
                 goalposts: {min: 0, max: 100}, lens: quality}

An indicator's ``lens`` (one of ``LENSES``: the way it looks at what it
measures, after the Adapted Urban Liveability Framework) is inferred from its
name where it can be; ``lens``, ``subdomain`` and ``colour`` are presentation
metadata carried to the dashboard, and do not alter the score.

To run independently:  python subprocesses/_composite_index.py <codename>
"""

import json
import os
import re
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import yaml

METHODS = ('ampi', 'mpi')
POSITIVE, NEGATIVE = 'positive', 'negative'
POLARITY_ALIASES = {
    'positive': POSITIVE,
    '+': POSITIVE,
    'higher_is_better': POSITIVE,
    'negative': NEGATIVE,
    '-': NEGATIVE,
    'lower_is_better': NEGATIVE,
}
REFERENCE_STATISTICS = ('mean', 'median')
OUTLIER_TREATMENTS = ('none', 'compress')
# the half-width of the AMPI range and the MPI standard deviation, giving
# normalised values usually within 70-130 about a reference of 100
AMPI_RANGE = 60
MPI_SD = 10
# decay slope of the soft threshold (Higgs et al. 2019; setup_sp.soft_access_score)
SOFT_THRESHOLD_K = 5

SAMPLE_POINT_PREFIX = 'sp_index_'
OUTPUT_PREFIX = 'index_'
SAMPLE_POINT_TABLE = 'sample_points_composite'
POINT_KEY = 'point_id'
# sample point tables an index may draw indicators from, besides the region's
# own point summary (indicators_sample_points)
SOURCE_TABLES = (
    'sample_points_pedestrian',
    'sample_points_cycling',
    'sample_points_euclidean',
)
# lower-case words joined by single underscores: a double underscore separates
# an index from its domain in output column names
NAME_PATTERN = re.compile(r'^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$')
# PostgreSQL truncates identifiers beyond 63 bytes
MAX_IDENTIFIER = 63


# ---------------------------------------------------------------------------
# Configuration


def _check_name(name, what):
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid {what} name '{name}': use lower-case letters, digits "
            'and single underscores, starting with a letter.',
        )


def _polarity(value, what):
    polarity = POLARITY_ALIASES.get(str(value).strip().lower())
    if polarity is None:
        raise ValueError(
            f"Unrecognised polarity '{value}' for {what} (expected "
            f"'positive' or 'negative').",
        )
    return polarity


def _weight(value, what):
    try:
        weight = float(value)
    except (TypeError, ValueError):
        weight = float('nan')
    if not weight > 0:
        raise ValueError(f"The weight for {what} must be a positive number.")
    return weight


def infer_polarity(variable, transformed=False):
    """The polarity of an indicator, where it can be read from its name.

    Access, diversity and count measures are positive; distances are negative,
    unless passed through a soft threshold, which turns a distance into an
    access score.  Avoided destinations are named for the share living beyond
    them, so they too are positive.  Returns None where the name does not say.
    """
    if transformed:
        return POSITIVE
    name = str(variable)
    if 'nearest_node' in name or '_dist_' in name:
        return NEGATIVE
    if name.endswith('_score') or any(
        token in name
        for token in (
            'access_',
            'beyond_',
            'diversity_',
            'richness_',
            'count_',
            'walkability',
            'daily_living',
            'intersection_density',
            'pop_density',
        )
    ):
        return POSITIVE
    return None


# The lenses of the Adapted Urban Liveability Framework: the way an indicator
# looks at the place or aspect it measures ('Healthcare access through a
# proximity lens').  An indicator's lens is presentation metadata, carried with
# the index structure to the dashboard; it does not alter the score.
LENSES = {
    'quality': {'en': 'Quality', 'es': 'Calidad'},
    'density': {'en': 'Density', 'es': 'Densidad'},
    'proximity': {'en': 'Proximity', 'es': 'Proximidad'},
    'equity': {'en': 'Equity', 'es': 'Equidad espacial'},
    'quantity': {'en': 'Quantity', 'es': 'Cantidad'},
    'diversity': {'en': 'Diversity', 'es': 'Diversidad'},
    'accessibility': {'en': 'Accessibility', 'es': 'Accesibilidad'},
    'presence': {'en': 'Presence', 'es': 'Presencia'},
}
COLOUR_PATTERN = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def infer_lens(variable, transformed=False):
    """The lens of an indicator, where it can be read from its name.

    A distance, or a distance passed through a soft threshold, looks through
    proximity; access within a distance through accessibility; densities,
    diversity and counts through their namesakes.  Returns None where the name
    does not say, in which case the lens is simply not shown unless set.
    """
    name = str(variable)
    if transformed or 'nearest_node' in name or '_dist_' in name:
        return 'proximity'
    if 'access_' in name:
        return 'accessibility'
    if 'density' in name:
        return 'density'
    if 'diversity_' in name or 'richness_' in name:
        return 'diversity'
    if 'count_' in name:
        return 'quantity'
    return None


def _lens(value, what):
    lens = str(value).strip().lower()
    if lens not in LENSES:
        raise ValueError(
            f"Unknown lens '{value}' for {what} (expected one of "
            f'{list(LENSES)}).',
        )
    return lens


def _colour(value, what):
    """A presentation colour: '#rrggbb', or {fill, stroke} of such."""
    if value is None:
        return None
    if isinstance(value, str):
        value = {'fill': value}
    if not isinstance(value, dict) or set(value) - {'fill', 'stroke'}:
        raise ValueError(
            f"The colour of {what} must be '#rrggbb' or "
            '{fill: #rrggbb, stroke: #rrggbb}.',
        )
    for key, colour in value.items():
        if not COLOUR_PATTERN.match(str(colour)):
            raise ValueError(
                f"Invalid {key} colour '{colour}' for {what}: use '#rrggbb'.",
            )
    return {k: str(v) for k, v in value.items()}


# Prefixes stripped from a variable to name it within an index: what is left
# is the destination or measure, which is what the column is about.
SHORT_NAME_PREFIXES = (
    'sp_walk_nearest_node_',
    'sp_walk_access_',
    'sp_walk_beyond_',
    'sp_euclid_dist_',
    'sp_euclid_access_',
    'sp_euclid_beyond_',
    'sp_local_nh_avg_',
    'sp_',
)
# an indicator's identifier: single underscores, so that '__' can separate an
# index from its domain and a domain from its indicator in column names
ID_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*$')


def short_name(variable):
    """A short identifier for an indicator within its index.

    Each indicator's normalised score is written as a column of its own
    (``index_<name>__<domain>__<id>``), and PostgreSQL truncates identifiers
    beyond 63 bytes, so the identifier is the variable less the prefix that
    says where it was measured: ``sp_walk_nearest_node_denue_pharmacy`` is
    ``denue_pharmacy``.
    """
    name = str(variable)
    for prefix in SHORT_NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def component_column(index, domain=None, indicator=None, prefix=OUTPUT_PREFIX):
    """The column holding a domain's score, or an indicator's normalised score."""
    parts = [f'{prefix}{index}']
    if domain is not None:
        parts.append(domain)
    if indicator is not None:
        parts.append(indicator)
    return '__'.join(parts)


def normalise_indicator(item, index_name):
    """Resolve one configured indicator to a complete specification."""
    if isinstance(item, str):
        item = {'variable': item}
    if not isinstance(item, dict) or not item.get('variable'):
        raise ValueError(
            f"Each indicator of composite index '{index_name}' needs a "
            "'variable'.",
        )
    variable = str(item['variable'])
    transform = item.get('transform')
    soft = None
    if transform:
        if (
            not isinstance(transform, dict)
            or 'soft_threshold' not in transform
            or set(transform) - {'soft_threshold', 'k'}
        ):
            raise ValueError(
                f"Unsupported transform for '{variable}': expected "
                '{soft_threshold: <metres>, k: <slope, default 5>}.',
            )
        threshold = float(transform['soft_threshold'])
        if not threshold > 0:
            raise ValueError(
                f"The soft threshold for '{variable}' must be positive.",
            )
        if infer_polarity(variable) == POSITIVE:
            raise ValueError(
                f"A soft threshold applies to a distance; '{variable}' "
                'appears to be a score already.',
            )
        soft = {
            'soft_threshold': threshold,
            'k': float(transform.get('k', SOFT_THRESHOLD_K)),
        }
    if item.get('polarity') is not None:
        polarity = _polarity(item['polarity'], f"'{variable}'")
    else:
        polarity = infer_polarity(variable, soft is not None)
        if polarity is None:
            raise ValueError(
                f"The polarity of '{variable}' cannot be inferred from its "
                "name; set 'polarity: positive' (higher is better) or "
                "'polarity: negative' (lower is better).",
            )
    indicator_id = str(item.get('name') or short_name(variable))
    if not ID_PATTERN.match(indicator_id):
        raise ValueError(
            f"Invalid indicator name '{indicator_id}' in composite index "
            f"'{index_name}': use letters, digits and single underscores, "
            "starting with a letter (set 'name' to give one explicitly).",
        )
    goalposts = item.get('goalposts')
    if goalposts is not None:
        try:
            goalposts = {
                'min': float(goalposts['min']),
                'max': float(goalposts['max']),
            }
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"Goalposts for '{variable}' must give numeric min and max.",
            )
        if not goalposts['max'] > goalposts['min']:
            raise ValueError(
                f"Goalposts for '{variable}' must have max greater than min.",
            )
    reference = item.get('reference')
    if reference is not None:
        reference = float(reference)
    lens = (
        _lens(item['lens'], f"'{variable}'")
        if item.get('lens') is not None
        else infer_lens(variable, soft is not None)
    )
    return {
        'id': str(indicator_id),
        'variable': variable,
        'label': item.get('label'),
        'lens': lens,
        'subdomain': item.get('subdomain'),
        'polarity': polarity,
        'transform': soft,
        'goalposts': goalposts,
        'reference': reference,
        'weight': _weight(item.get('weight', 1), f"'{variable}'"),
    }


def normalise_index_spec(name, spec):
    """Resolve a configured composite index, filling every default."""
    _check_name(name, 'composite index')
    spec = dict(spec or {})
    method = str(spec.get('method') or 'ampi').lower()
    if method not in METHODS:
        raise ValueError(
            f"Unknown method '{method}' for composite index '{name}' "
            f'(expected one of {METHODS}).',
        )
    phenomenon = _polarity(
        spec.get('phenomenon') or POSITIVE,
        f"composite index '{name}'",
    )
    reference = str(spec.get('reference') or 'mean').lower()
    if reference not in REFERENCE_STATISTICS:
        raise ValueError(
            f"Unknown reference '{reference}' for composite index '{name}' "
            f'(expected one of {REFERENCE_STATISTICS}).',
        )
    outliers = str(
        spec.get('outliers') or ('compress' if method == 'mpi' else 'none'),
    ).lower()
    if outliers not in OUTLIER_TREATMENTS:
        raise ValueError(
            f"Unknown outlier treatment '{outliers}' for composite index "
            f"'{name}' (expected one of {OUTLIER_TREATMENTS}).",
        )
    min_indicators = spec.get('min_indicators', 'all')
    if min_indicators != 'all':
        try:
            min_indicators = int(min_indicators)
        except (TypeError, ValueError):
            min_indicators = 0
        if min_indicators < 1:
            raise ValueError(
                f"min_indicators for composite index '{name}' must be 'all' "
                'or a positive whole number.',
            )
    domains_config = spec.get('domains')
    indicators_config = spec.get('indicators')
    if bool(domains_config) == bool(indicators_config):
        raise ValueError(
            f"Composite index '{name}' needs either 'domains' or a flat "
            "'indicators' list (not both).",
        )
    flat = not domains_config
    raw_domains = (
        {None: {'indicators': indicators_config}} if flat else domains_config
    )
    if not isinstance(raw_domains, dict):
        raise ValueError(
            f"The domains of composite index '{name}' must be a mapping of "
            'domain names to their indicators.',
        )
    domains = []
    seen = set()
    for domain_name, domain in raw_domains.items():
        if domain_name is not None:
            _check_name(domain_name, f"domain of composite index '{name}'")
        if isinstance(domain, list):
            domain = {'indicators': domain}
        domain = dict(domain or {})
        items = domain.get('indicators') or []
        if not items:
            raise ValueError(
                f"Domain '{domain_name}' of composite index '{name}' has no "
                'indicators.',
            )
        indicators = []
        for item in items:
            indicator = normalise_indicator(item, name)
            if indicator['id'] in seen:
                raise ValueError(
                    f"Indicator '{indicator['id']}' appears more than once in "
                    f"composite index '{name}'; give one a distinct 'name'.",
                )
            seen.add(indicator['id'])
            indicator['domain'] = domain_name
            indicators.append(indicator)
        domains.append(
            {
                'name': domain_name,
                'label': domain.get('label'),
                'colour': _colour(
                    domain.get('colour'),
                    f"domain '{domain_name}'",
                ),
                'weight': _weight(
                    domain.get('weight', 1),
                    f"domain '{domain_name}'",
                ),
                'indicators': indicators,
            },
        )
    write_indicators = bool(spec.get('write_indicators', True))
    city = f'pop_{OUTPUT_PREFIX}'
    candidates = [f'{city}{name}_penalty']
    for d in domains:
        if d['name'] is not None:
            candidates.append(component_column(name, d['name'], prefix=city))
        if write_indicators:
            candidates += [
                component_column(name, d['name'], i['id'], prefix=city)
                for i in d['indicators']
            ]
    longest = max(candidates, key=len)
    if len(longest) > MAX_IDENTIFIER:
        raise ValueError(
            f"Output column '{longest}' exceeds PostgreSQL's "
            f'{MAX_IDENTIFIER} character limit; shorten the index, domain or '
            "indicator name (an indicator's 'name' may be set explicitly).",
        )
    return {
        'name': name,
        'label': spec.get('label'),
        'colour': _colour(spec.get('colour'), f"composite index '{name}'"),
        'method': method,
        'phenomenon': phenomenon,
        'reference': reference,
        'outliers': outliers,
        'min_indicators': min_indicators,
        'flat': flat,
        'domains': domains,
        'parameters': spec.get('parameters'),
        'write_indicators': write_indicators,
    }


def _parameters_source(spec):
    """An index's configured parameters file, relative to the data folder."""
    source = str(spec['parameters'])
    if os.path.isabs(source) or os.path.exists(source):
        return source
    try:
        import ghsci
    except ImportError:
        from subprocesses import ghsci
    return f'{ghsci.data_path}/{source}'


def normalise_config(block):
    """Resolve a whole ``composite_indices`` block to ``{name: spec}``."""
    if not block:
        return {}
    if not isinstance(block, dict):
        raise ValueError(
            'composite_indices must be a mapping of index names to their '
            'definitions.',
        )
    return {
        name: normalise_index_spec(name, spec)
        for name, spec in block.items()
        if spec is not False
    }


def composite_index_config(r):
    """The region's resolved composite indices, or None if none configured."""
    block = (getattr(r, 'config', None) or {}).get('composite_indices')
    return normalise_config(block) or None


def iter_indicators(spec):
    for domain in spec['domains']:
        yield from domain['indicators']


def index_columns(spec, prefix=OUTPUT_PREFIX, indicators=True):
    """The output columns an index writes.

    The index, its mean level, penalty and count, then each domain followed by
    its indicators' normalised scores (where written).
    """
    base = f'{prefix}{spec["name"]}'
    columns = [base, f'{base}_mean', f'{base}_penalty', f'{base}_n']
    for domain in spec['domains']:
        if domain['name'] is not None:
            columns.append(
                component_column(spec['name'], domain['name'], prefix=prefix),
            )
        if indicators and spec.get('write_indicators', True):
            columns += [
                component_column(
                    spec['name'],
                    domain['name'],
                    indicator['id'],
                    prefix=prefix,
                )
                for indicator in domain['indicators']
            ]
    return columns


def index_structure(spec, params=None, prefix=OUTPUT_PREFIX):
    """The structure of an index, for presenting it.

    Its domains, the indicators each is built from, and the column holding
    every score, as plain values that can be written to JSON as they are.
    Where the parameters an index was scored with are given, each indicator
    carries what it was normalised against, and indicators left out as not
    varying are marked.
    """
    params = params or {}
    resolved = params.get('indicators') or {}
    dropped = params.get('dropped') or {}
    name = spec['name']
    base = f'{prefix}{name}'
    written = spec.get('write_indicators', True)
    domains = []
    for domain in spec['domains']:
        indicators = []
        for indicator in domain['indicators']:
            entry = resolved.get(indicator['id']) or {}
            transform = indicator['transform'] or {}
            indicators.append(
                {
                    'id': indicator['id'],
                    'variable': indicator['variable'],
                    'label': indicator['label'],
                    'column': (
                        component_column(
                            name,
                            domain['name'],
                            indicator['id'],
                            prefix=prefix,
                        )
                        if written
                        else None
                    ),
                    'polarity': indicator['polarity'],
                    'lens': indicator.get('lens'),
                    'subdomain': indicator.get('subdomain'),
                    'weight': indicator['weight'],
                    'soft_threshold': transform.get('soft_threshold'),
                    'k': transform.get('k'),
                    'normalisation': {
                        k: entry[k]
                        for k in ('min', 'max', 'reference', 'mean', 'sd')
                        if k in entry
                    }
                    or indicator['goalposts'],
                    'dropped': dropped.get(indicator['id']),
                },
            )
        domains.append(
            {
                'name': domain['name'],
                'label': domain['label'],
                'colour': domain.get('colour'),
                'weight': domain['weight'],
                'column': (
                    component_column(name, domain['name'], prefix=prefix)
                    if domain['name'] is not None
                    else None
                ),
                'indicators': indicators,
            },
        )
    return _plain(
        {
            'name': name,
            'label': spec.get('label'),
            'colour': spec.get('colour'),
            'method': spec['method'],
            'phenomenon': spec['phenomenon'],
            'reference': spec.get('reference'),
            'reference_value': 100,
            'flat': spec['flat'],
            'columns': {
                'index': base,
                'mean': f'{base}_mean',
                'penalty': f'{base}_penalty',
                'n': f'{base}_n',
            },
            'domains': domains,
            # the labels of the lenses its indicators are seen through, in the
            # framework's order
            'lenses': {
                lens: labels
                for lens, labels in LENSES.items()
                if any(
                    i['lens'] == lens for d in domains for i in d['indicators']
                )
            },
            'parameters': (
                {
                    'created': params.get('created'),
                    'units': params.get('units'),
                    'dropped': dropped,
                }
                if params
                else None
            ),
        },
    )


# Steps a composite index's colour classes may take: each gives whole-number
# edges either side of a reference of 100.
CLASS_STEPS = (1, 2, 4, 10, 20, 40, 100)


def composite_classes(structure, ranges, classes=7, spreads=None):
    """Shared, diverging colour classes for the scores of one composite index.

    An index, its domains and its indicators are normalised onto one scale on
    which 100 is the reference, and are read against one another, so they
    share one set of classes: symmetric about the reference, with the
    reference at the centre of the middle class, on a diverging ramp -- whether
    a score is above or below the reference is the first thing to see.

    The step is sized from the index itself.  Its domains and indicators are
    each normalised over their own full observed range, and a domain holding a
    single indicator -- binary access, say -- spans most of that range, so
    classes sized to reach it put nearly every index value in the middle class
    (the first Mexicali export came out 0 / 40 / 80 / ...).  Wider domain and
    indicator values fall into the open classes at either end instead.
    ``ranges`` maps a column to its ``(min, max)``; only columns with a range
    are classified.  ``_penalty`` and ``_n`` are not scores, and are left to
    the ordinary rules.

    ``spreads`` optionally maps a column to a robust ``(low, high)`` span --
    the middle 90% of its values, say -- used in place of its range to size
    the step.  An index's extremes are a handful of sample points; sized to
    reach them, the classes put most areas in the middle class (three
    quarters of Mexicali's grid cells, in the first export).  Values beyond
    the span fall in the open end classes, which is what they are for.
    """
    reference = float(structure.get('reference_value') or 100)
    columns = structure['columns']
    headline = [columns['index']] + [
        d['column'] for d in structure['domains'] if d.get('column')
    ]
    sizing = dict(ranges)
    sizing.update(
        {c: tuple(s) for c, s in (spreads or {}).items() if c in ranges},
    )
    # the index where it has a range; its domains only if it has none
    spans = (
        [sizing[columns['index']]]
        if columns['index'] in sizing
        else [sizing[c] for c in headline if c in sizing]
    )
    if not spans:
        return {}
    half = max(
        max(abs(low - reference), abs(high - reference)) for low, high in spans
    )
    reach = (classes - 2) / 2
    step = next(
        (s for s in CLASS_STEPS if reach * s >= 0.9 * half),
        CLASS_STEPS[-1],
    )
    spec = {
        'kind': 'classes',
        'edges': [
            round(reference + (k - reach) * step, 6)
            for k in range(classes - 1)
        ],
        'open_low': True,
        'open_high': True,
        'ramp': 'vik',
        'centre': reference,
        'step': step,
    }
    scores = (
        headline
        + [
            i['column']
            for d in structure['domains']
            for i in d['indicators']
            if i.get('column')
        ]
        + [columns['mean']]
    )
    return {c: dict(spec) for c in scores if c in ranges}


# ---------------------------------------------------------------------------
# Transformations


def soft_threshold(distance, threshold, k=SOFT_THRESHOLD_K):
    """Soft access score (0-1) for a distance: 0.5 at the threshold.

    ``1 / (1 + exp(k (d - t) / t))``, as for the Urban Liveability Index (and
    ``setup_sp.soft_access_score``).  A missing distance -- a destination not
    found within the distance the analysis searched to -- scores 0.
    """
    d = pd.to_numeric(distance, errors='coerce').astype('float64')
    with np.errstate(over='ignore'):
        score = 1.0 / (1.0 + np.exp(k * (d - threshold) / threshold))
    return score.fillna(0.0)


def compression_parameters(values):
    """Mean, population SD and range used to compress outliers."""
    observed = pd.to_numeric(values, errors='coerce').dropna()
    return {
        'mean': float(observed.mean()),
        'sd': float(observed.std(ddof=0)),
        'minimum': float(observed.min()),
        'maximum': float(observed.max()),
    }


def compress_outliers(values, mean, sd, minimum, maximum):
    """Conditionally scale outliers towards the usual range.

    The approach of the Urban Liveability Index (Higgs et al. 2019): where an
    indicator's range extends beyond three standard deviations of its mean,
    values more than two standard deviations from the mean are linearly
    re-scaled to lie between two and three, limiting the penalty an isolated
    extreme value can impose on an otherwise balanced set.
    """
    x = pd.to_numeric(values, errors='coerce').astype('float64')
    out = x.copy()
    if not sd > 0:
        return out
    lower, upper = mean - 2 * sd, mean + 2 * sd
    if minimum < lower - sd:
        low = x < lower
        out[low] = lower - sd + sd * (x[low] - minimum) / (lower - minimum)
    if maximum > upper + sd:
        high = x > upper
        out[high] = upper + sd * (x[high] - upper) / (maximum - upper)
    return out


def prepare(frame, spec):
    """The indicator values an index is built from, transformed as configured.

    Returns a float frame with one column per indicator id.
    """
    columns = {}
    for indicator in iter_indicators(spec):
        values = pd.to_numeric(
            frame[indicator['variable']],
            errors='coerce',
        ).astype('float64')
        transform = indicator['transform']
        if transform:
            threshold = transform['soft_threshold']
            observed = values.dropna()
            if (
                values.isna().any()
                and len(observed)
                and observed.max() < 2 * threshold
            ):
                warnings.warn(
                    f"'{indicator['variable']}' appears to be censored at "
                    f'{observed.max():.0f} m, less than twice its soft '
                    f'threshold of {threshold:.0f} m; points beyond it score '
                    '0 although their soft access score would not be '
                    'negligible there.  Consider measuring distance further.',
                    stacklevel=2,
                )
            values = soft_threshold(values, threshold, transform['k'])
        columns[indicator['id']] = values
    return pd.DataFrame(columns, index=frame.index)


# ---------------------------------------------------------------------------
# Parameters: goalposts, references and standardisation statistics


def _plain(value):
    """Convert numpy scalars and containers to plain, YAML-safe values."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


# Rule of thumb for when an indicator's distribution warrants treatment before
# aggregation: absolute skewness above 2 together with (excess) kurtosis above
# 3.5 (JRC Competence Centre on Composite Indicators; OECD/JRC 2008 Handbook
# on Constructing Composite Indicators).
SKEWNESS_LIMIT = 2.0
KURTOSIS_LIMIT = 3.5
# an indicator with this share of its values tied at one value hardly varies,
# and no transformation will spread it: the few units away from that value
# carry all of its variation, and much of the index's penalty
TIED_LIMIT = 0.9


def distribution_diagnostics(values):
    """Describe the shape of an indicator's values; flag what may need care.

    Returns skewness and excess kurtosis (as pandas reports them), the share of
    values tied at the most common value, and ``flags``: ``skewed`` where the
    skewness and kurtosis rule of thumb is met, and ``tied`` where most values
    share one value.  These inform the choice of ``outliers: compress`` or
    explicit ``goalposts``; nothing is changed here.
    """
    observed = pd.to_numeric(values, errors='coerce').dropna()
    if observed.empty:
        return {}
    skewness = float(observed.skew()) if len(observed) > 2 else 0.0
    kurtosis = float(observed.kurt()) if len(observed) > 3 else 0.0
    skewness = 0.0 if skewness != skewness else skewness
    kurtosis = 0.0 if kurtosis != kurtosis else kurtosis
    tied = float(observed.round(9).value_counts(normalize=True).iloc[0])
    flags = []
    if abs(skewness) > SKEWNESS_LIMIT and kurtosis > KURTOSIS_LIMIT:
        flags.append('skewed')
    if tied >= TIED_LIMIT:
        flags.append('tied')
    return {
        'skewness': round(skewness, 4),
        'kurtosis': round(kurtosis, 4),
        'tied_share': round(tied, 4),
        'flags': flags,
    }


def resolve_parameters(frames, spec, reference_frame=None):
    """Resolve the normalisation parameters of an index from observed data.

    ``frames`` are prepared frames (see :func:`prepare`): one for a single
    region, or one per timepoint for a series, in which case the goalposts
    span every timepoint.  The reference value (AMPI) or the standardisation
    statistics (MPI) are taken from ``reference_frame`` where given -- the
    baseline of a series -- and otherwise from all frames.

    Indicators that do not vary are dropped, and recorded as such: an
    indicator that is the same everywhere adds nothing to a comparison but
    would still dilute every other indicator's weight.

    Returns a plain dictionary, safe to write as YAML, which can be supplied
    again as frozen goalposts.
    """
    if isinstance(frames, pd.DataFrame):
        frames = [frames]
    frames = list(frames)
    pooled = pd.concat(frames, ignore_index=True)
    reference = pooled if reference_frame is None else reference_frame
    params = {
        'index': spec['name'],
        'method': spec['method'],
        'phenomenon': spec['phenomenon'],
        'reference': spec['reference'],
        'outliers': spec['outliers'],
        'units': int(len(pooled)),
        'frames': len(frames),
        'created': datetime.now().isoformat(timespec='seconds'),
        'indicators': {},
        'domains': {},
        'dropped': {},
    }
    for indicator in iter_indicators(spec):
        key = indicator['id']
        values = pooled[key]
        reference_values = reference[key]
        entry = {
            'variable': indicator['variable'],
            'domain': indicator['domain'],
            'polarity': indicator['polarity'],
            'weight': indicator['weight'],
            'transform': indicator['transform'],
        }
        if values.dropna().empty or reference_values.dropna().empty:
            params['dropped'][key] = 'no values'
            continue
        # described as prepared, before any outliers are compressed
        entry['distribution'] = distribution_diagnostics(values)
        if spec['outliers'] == 'compress':
            stats = compression_parameters(values)
            entry['compress'] = stats
            values = compress_outliers(values, **stats)
            reference_values = compress_outliers(reference_values, **stats)
        inf, sup = float(values.min()), float(values.max())
        entry['inf'], entry['sup'] = inf, sup
        if indicator['reference'] is not None:
            centre = indicator['reference']
        else:
            centre = float(
                getattr(reference_values.dropna(), spec['reference'])(),
            )
        if spec['method'] == 'ampi':
            if indicator['goalposts'] is not None:
                minimum = indicator['goalposts']['min']
                maximum = indicator['goalposts']['max']
            else:
                half_range = (sup - inf) / 2
                minimum, maximum = centre - half_range, centre + half_range
            if not maximum > minimum:
                params['dropped'][key] = 'does not vary'
                continue
            entry.update(reference=centre, min=minimum, max=maximum)
        else:
            sd = float(reference_values.dropna().std(ddof=0))
            if not sd > 0:
                params['dropped'][key] = 'does not vary'
                continue
            entry.update(mean=centre, sd=sd)
        params['indicators'][key] = entry
    for domain in spec['domains']:
        kept = [
            i['id']
            for i in domain['indicators']
            if i['id'] in params['indicators']
        ]
        if domain['name'] is None:
            continue
        if kept:
            params['domains'][domain['name']] = domain['weight']
        else:
            params['dropped'][
                f"domain {domain['name']}"
            ] = 'no usable indicators'
    if not params['indicators']:
        raise ValueError(
            f"No indicator of composite index '{spec['name']}' has values "
            'that vary; the index cannot be computed.',
        )
    for key, reason in params['dropped'].items():
        warnings.warn(
            f"Composite index '{spec['name']}': '{key}' was left out "
            f'({reason}).',
            stacklevel=2,
        )
    # indicators whose shape may call for treatment, where none was configured
    fixed = {
        i['id'] for i in iter_indicators(spec) if i['goalposts'] is not None
    }
    untreated = [
        f"{key} ({', '.join(entry['distribution']['flags'])})"
        for key, entry in params['indicators'].items()
        if entry.get('distribution', {}).get('flags')
        and spec['outliers'] == 'none'
        and key not in fixed
    ]
    if untreated:
        warnings.warn(
            f"Composite index '{spec['name']}': the distributions of "
            f"{', '.join(untreated)} may warrant 'outliers: compress' or "
            'explicit goalposts; see the distribution entries in the '
            'parameters file.',
            stacklevel=2,
        )
    return _plain(params)


def series_parameters(frames, spec, reference=0, goalposts='pooled'):
    """Parameters shared by every timepoint of a series.

    ``pooled`` (default): goalposts span every timepoint, centred on the
    reference timepoint.  ``reference``: goalposts and centre are both taken
    from the reference timepoint alone, so later values may fall outside the
    usual 70-130 range -- which is itself informative about change.
    """
    frames = list(frames)
    if goalposts == 'pooled':
        return resolve_parameters(
            frames,
            spec,
            reference_frame=frames[reference],
        )
    if goalposts == 'reference':
        return resolve_parameters([frames[reference]], spec)
    raise ValueError(
        f"Unknown series goalposts '{goalposts}' (expected 'pooled' or "
        "'reference').",
    )


def check_parameters(spec, params):
    """Confirm frozen parameters describe this index."""
    if params.get('method') != spec['method']:
        raise ValueError(
            f"Goalposts for '{spec['name']}' were resolved for method "
            f"'{params.get('method')}', not '{spec['method']}'.",
        )
    covered = set(params.get('indicators', {})) | set(
        params.get('dropped', {}),
    )
    missing = [
        i['id'] for i in iter_indicators(spec) if i['id'] not in covered
    ]
    if missing:
        raise ValueError(
            f"Goalposts for '{spec['name']}' do not cover {missing}; resolve "
            'them again for the indicators now configured.',
        )


def load_goalposts(goalposts):
    """Normalise frozen goalposts to ``{index name: parameters}``.

    Accepts a path to a YAML file written by a previous run, a single index's
    parameters, a mapping of index names to parameters (or to paths), or a
    series goalposts file with an ``indices`` mapping.
    """
    if goalposts is None:
        return {}
    if isinstance(goalposts, (str, os.PathLike)):
        with open(goalposts, encoding='utf-8') as f:
            return load_goalposts(yaml.safe_load(f))
    if not isinstance(goalposts, dict):
        raise ValueError('Goalposts must be a mapping or a path to YAML.')
    if 'indices' in goalposts:
        return load_goalposts(goalposts['indices'])
    if 'indicators' in goalposts and 'index' in goalposts:
        return {goalposts['index']: goalposts}
    resolved = {}
    for name, value in goalposts.items():
        resolved.update(
            (
                load_goalposts(value)
                if isinstance(value, (str, os.PathLike))
                else {name: value}
            ),
        )
    return resolved


# ---------------------------------------------------------------------------
# Normalisation and aggregation


def normalise(prepared, params):
    """Normalise prepared indicator values using resolved parameters."""
    columns = {}
    for key, entry in params['indicators'].items():
        x = prepared[key].astype('float64')
        if entry.get('compress'):
            x = compress_outliers(x, **entry['compress'])
        sign = 1.0 if entry['polarity'] == POSITIVE else -1.0
        if params['method'] == 'ampi':
            columns[key] = 100 + sign * AMPI_RANGE * (
                x - entry['reference']
            ) / (entry['max'] - entry['min'])
        else:
            columns[key] = (
                100 + sign * MPI_SD * (x - entry['mean']) / entry['sd']
            )
    return pd.DataFrame(columns, index=prepared.index)


def mpi_aggregate(values, weights, phenomenon=POSITIVE, min_valid=None):
    """Weighted Mazziotta-Pareto aggregation of normalised values by row.

    Weights are shares of the indicators present in each row, so a missing
    indicator does not shrink the mean.  Rows with fewer than ``min_valid``
    values (default: all) are left missing.  Returns ``index``, ``mean``,
    ``penalty`` and ``n`` (the number of values used).
    """
    v = values.to_numpy(dtype='float64')
    w = np.asarray(weights, dtype='float64')
    valid = ~np.isnan(v)
    n = valid.sum(axis=1)
    raw = np.where(valid, w[None, :], 0.0)
    total = raw.sum(axis=1)
    filled = np.where(valid, v, 0.0)
    with np.errstate(invalid='ignore', divide='ignore'):
        shares = raw / total[:, None]
        mean = (shares * filled).sum(axis=1)
        sd = np.sqrt((shares * (filled - mean[:, None]) ** 2).sum(axis=1))
        penalty = sd * (sd / mean)
    index = mean - penalty if phenomenon == POSITIVE else mean + penalty
    required = v.shape[1] if min_valid is None else min_valid
    missing = (n < required) | ~(total > 0)
    mean[missing] = np.nan
    penalty[missing] = np.nan
    index[missing] = np.nan
    return pd.DataFrame(
        {'index': index, 'mean': mean, 'penalty': penalty, 'n': n},
        index=values.index,
    )


def _min_valid(min_indicators, size):
    return size if min_indicators == 'all' else min(int(min_indicators), size)


def score(prepared, spec, params, prefix=SAMPLE_POINT_PREFIX):
    """Score prepared indicator values as a composite index.

    Returns the index, its mean level and penalty, the number of indicators
    contributing, and a score for each domain.
    """
    normalised = normalise(prepared, params)
    weights = {k: e['weight'] for k, e in params['indicators'].items()}
    phenomenon = spec['phenomenon']
    base = f'{prefix}{spec["name"]}'
    domain_columns = {}
    if spec['flat']:
        columns = list(normalised.columns)
        result = mpi_aggregate(
            normalised[columns],
            [weights[c] for c in columns],
            phenomenon,
            _min_valid(spec['min_indicators'], len(columns)),
        )
        count = result['n']
    else:
        scores, domain_weights = {}, []
        count = pd.Series(0, index=prepared.index)
        for domain in spec['domains']:
            columns = [
                i['id'] for i in domain['indicators'] if i['id'] in weights
            ]
            if not columns:
                continue
            domain_result = mpi_aggregate(
                normalised[columns],
                [weights[c] for c in columns],
                phenomenon,
                _min_valid(spec['min_indicators'], len(columns)),
            )
            scores[domain['name']] = domain_result['index']
            domain_weights.append(domain['weight'])
            count = count + domain_result['n']
            domain_columns[f'{base}__{domain["name"]}'] = domain_result[
                'index'
            ]
        # every domain is required: an index missing a whole domain would
        # silently mean something narrower than its name
        result = mpi_aggregate(
            pd.DataFrame(scores, index=prepared.index),
            domain_weights,
            phenomenon,
        )
    out = {
        base: result['index'],
        f'{base}_mean': result['mean'],
        f'{base}_penalty': result['penalty'],
        f'{base}_n': count.astype('float64'),
    }
    out.update(domain_columns)
    # each indicator's normalised score, so that a domain's score can be
    # explained by what it is made of; already oriented so higher is better
    if spec.get('write_indicators', True):
        for domain in spec['domains']:
            for indicator in domain['indicators']:
                if indicator['id'] in normalised:
                    column = component_column(
                        spec['name'],
                        domain['name'],
                        indicator['id'],
                        prefix=prefix,
                    )
                    out[column] = normalised[indicator['id']]
    return pd.DataFrame(out, index=prepared.index)


# ---------------------------------------------------------------------------
# Database


def indicator_tables(r):
    """Sample point tables an index may draw indicators from, in order."""
    return [r.config['point_summary'], *SOURCE_TABLES]


def load_indicator_frame(r, specs):
    """Sample points with every indicator the given indices use.

    Each variable is read from the first sample point table that has it,
    joined on the sample point identifier.
    """
    variables = list(
        dict.fromkeys(
            i['variable'] for spec in specs for i in iter_indicators(spec)
        ),
    )
    available = set(r.get_tables())
    located = {}
    for table in indicator_tables(r):
        if table not in available:
            continue
        columns = set(
            r.get_df(
                'SELECT column_name FROM information_schema.columns '
                f"WHERE table_schema = 'public' AND table_name = '{table}'",
            )['column_name'],
        )
        for variable in variables:
            if variable not in located and variable in columns:
                located[variable] = table
    missing = [v for v in variables if v not in located]
    if missing:
        raise ValueError(
            f'Composite index variables not found in any sample point table '
            f'({", ".join(indicator_tables(r))}): {missing}.  Check the '
            'variable names, and that the analyses producing them have run.',
        )
    aliases = {
        table: f't{i}'
        for i, table in enumerate(dict.fromkeys(located.values()))
    }
    select = ', '.join(
        f'{aliases[table]}."{variable}"' for variable, table in located.items()
    )
    joins = ' '.join(
        f'LEFT JOIN "{table}" {alias} '
        f'ON {alias}.{POINT_KEY} = u.{POINT_KEY}'
        for table, alias in aliases.items()
    )
    frame = r.get_gdf(
        f'SELECT u.{POINT_KEY}, u.grid_id, u.geom, {select} '
        f'FROM urban_sample_points u {joins}',
        index_col=POINT_KEY,
    )
    if frame is None:
        raise ValueError('Sample point indicators could not be read.')
    return frame


def parameters_path(r, name):
    return os.path.join(
        r.config['region_dir'],
        f'{r.codename}_composite_{name}_parameters.yml',
    )


def save_parameters(path, params):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(
            '# Composite index parameters: the goalposts, references and '
            'weights used.\n'
            '# Supply this file as goalposts to reproduce these scores, or '
            'to score\n# another timepoint against the same goalposts.\n',
        )
        yaml.safe_dump(
            _plain(params),
            f,
            sort_keys=False,
            allow_unicode=True,
        )
    return path


def _aggregation():
    try:
        import _12_aggregation as aggregation
    except ImportError:
        from subprocesses import _12_aggregation as aggregation
    return aggregation


def propagate(r, plans=None):
    """Average sample point scores to the grid, city and custom areas."""
    aggregation = _aggregation()
    if plans is None:
        plans = aggregation.load_aggregation_plans(r)
    aggregation._propagate_sample_point_columns(
        r,
        SAMPLE_POINT_TABLE,
        [(SAMPLE_POINT_PREFIX, OUTPUT_PREFIX, False)],
        'composite',
        plans,
    )


def stale_columns(spec, columns):
    """An index's domain and indicator columns it no longer writes.

    Scores are averaged to every scale by adding columns, never replacing
    them, so a domain renamed or regrouped leaves its old columns behind on
    the grid, city and custom area tables -- where they would be read as
    current.  Of ``columns``, returns those named for this index's domains or
    indicators (``<prefix>index_<name>__...``, under any scale's prefix) that
    the index as now configured does not write.
    """
    name = spec['name']
    current = {column[len(OUTPUT_PREFIX) :] for column in index_columns(spec)}
    pattern = re.compile(rf'^(?:\w*_)?{OUTPUT_PREFIX}({name}__\w+)$')
    stale = []
    for column in columns:
        match = pattern.match(column)
        if match and match.group(1) not in current:
            stale.append(column)
    return stale


def drop_stale_columns(r, specs):
    """Drop the columns of domains and indicators no longer configured."""
    from sqlalchemy import text

    dropped = {}
    for spec in specs.values():
        like = f'%index\\_{spec["name"]}\\_\\_%'
        found = r.get_df(
            'SELECT table_name, column_name FROM information_schema.columns '
            "WHERE table_schema = 'public' "
            f"AND column_name LIKE '{like}'",
        )
        for table, group in found.groupby('table_name'):
            stale = stale_columns(spec, group['column_name'].tolist())
            if not stale:
                continue
            with r.engine.begin() as connection:
                for column in stale:
                    connection.execute(
                        text(
                            f'ALTER TABLE "{table}" '
                            f'DROP COLUMN IF EXISTS "{column}"',
                        ),
                    )
            dropped[table] = stale
    if dropped:
        total = sum(len(v) for v in dropped.values())
        print(
            f'  Dropped {total} columns of domains or indicators no longer '
            f'configured, from {len(dropped)} tables',
        )
    return dropped


def compute(r, goalposts=None, write=True, plans=None):
    """Compute a region's configured composite indices.

    Parameters are resolved from the region's own data unless frozen
    ``goalposts`` are given for an index (see :func:`load_goalposts`).  With
    ``write``, scores are saved to ``sample_points_composite``, averaged to
    every scale, and the parameters used are written beside the region's
    outputs.  Returns ``(scores, parameters)``.
    """
    from sqlalchemy import text

    specs = composite_index_config(r)
    if specs is None:
        print('No composite indices are configured for this region.')
        return None, {}
    frozen = load_goalposts(goalposts)
    # an index may name a parameters file of its own in configuration, so that
    # the analysis itself scores against frozen goalposts
    for name, spec in specs.items():
        if name not in frozen and spec.get('parameters'):
            frozen.update(load_goalposts(_parameters_source(spec)))
    unknown = set(frozen) - set(specs)
    if unknown:
        warnings.warn(
            f'Goalposts given for indices not configured: {sorted(unknown)}',
            stacklevel=2,
        )
    frame = load_indicator_frame(r, specs.values())
    parts = [frame[['grid_id', 'geom']]]
    parameters = {}
    for name, spec in specs.items():
        prepared = prepare(frame, spec)
        if name in frozen:
            params = frozen[name]
            check_parameters(spec, params)
            source = 'frozen goalposts'
        else:
            params = resolve_parameters([prepared], spec)
            source = 'goalposts from this region'
        scores = score(prepared, spec, params)
        parts.append(scores)
        parameters[name] = params
        column = f'{SAMPLE_POINT_PREFIX}{name}'
        print(
            f"  {name} ({spec['method'].upper()}, {source}): "
            f"{int(scores[column].notna().sum())} of {len(scores)} sample "
            f"points scored; mean {scores[column].mean():.2f}, mean penalty "
            f"{scores[f'{column}_penalty'].mean():.2f}",
        )
    result = pd.concat(parts, axis=1)
    if not write:
        return result, parameters
    result = result.set_geometry('geom')
    result.index.name = POINT_KEY
    with r.engine.connect() as connection:
        result.to_postgis(
            SAMPLE_POINT_TABLE,
            connection,
            index=True,
            if_exists='replace',
        )
    # the parameters used travel with the scores, so that a table can always
    # be traced to the goalposts it was scored against
    comment = (
        json.dumps(_plain(parameters)).replace("'", "''").replace(':', r'\:')
    )
    with r.engine.begin() as connection:
        connection.execute(
            text(f"COMMENT ON TABLE {SAMPLE_POINT_TABLE} IS '{comment}'"),
        )
    for name, params in parameters.items():
        # The parameters are already recorded in the table comment above, so a
        # file that cannot be written -- locked by a sync client, or left
        # read-only by another container user -- is reported, and must not stop
        # the scores reaching every scale.
        try:
            path = save_parameters(parameters_path(r, name), params)
            print(f'  Parameters: {os.path.basename(path)}')
        except OSError as e:
            warnings.warn(
                f"Composite index '{name}': parameters file not written ({e}); "
                f'they remain recorded as the comment on {SAMPLE_POINT_TABLE}, '
                'readable with recorded_parameters(r).',
                stacklevel=2,
            )
    drop_stale_columns(r, specs)
    propagate(r, plans)
    return result, parameters


def recorded_parameters(r):
    """The parameters recorded with a region's composite index scores."""
    if SAMPLE_POINT_TABLE not in r.get_tables():
        return {}
    comment = r.get_df(
        f"SELECT obj_description('{SAMPLE_POINT_TABLE}'::regclass) AS c",
    )['c'].iloc[0]
    return json.loads(comment) if comment else {}


def main():
    import time

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
        '_composite_index',
        'Composite indices',
        start,
    )
    r.engine.dispose()


if __name__ == '__main__':
    main()
