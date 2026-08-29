"""Export indicator-dashboard layers from a region database.

Produces the per-layer newline-delimited GeoJSON inputs for building PMTiles
vector-tile archives (via tippecanoe, run separately by ``build_tiles.sh``),
together with the three JSON files the dashboard reads:

    manifest.json     scales, layers, bounding box, region-level values
    stats.json        per (scale, column) weighted summaries, and the share of
                      population in each colour class
    indicators.json   the faceted indicator vocabulary and its prose, plus the
                      colour classes and targets every column is drawn with

This generalises ``_export_validation_tiles.py`` (the cycling validation site's
exporter) in three ways: every aggregation scale is exported rather than only
the population grid; the indicator vocabulary is derived from the region's own
accessibility configuration and data dictionary rather than a hardcoded cycling
cross product; and the explanatory text the viewer needs is emitted as data
instead of being hardcoded in its JavaScript.

Usage (inside the ghsci container), either from the region object:

    r.export_dashboard()
    r.export_dashboard(outdir=..., scales=['grid'], layers=False)

or on the commandline, from the process folder:

    /env/bin/python subprocesses/_export_dashboard.py <config.yml> [outdir] [--scales a,b,c]

Default outdir is /tmp/dashboard_export/<slug>/ (copy out with docker cp).
"""

import csv
import json
import math
import os
import re
import shutil
import sys

if __name__ == '__main__':
    # usage examples give configuration paths relative to the process
    # folder; as a module this leaves the caller's directory alone
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ghsci  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from _accessibility_spec import (  # noqa: E402
    AVOID,
    DEFAULT_DESTINATIONS,
    STANDARD_SET,
    accessibility_config,
    activity_centre_definitions,
    combined_access_sets,
    diversity_sets,
    effective_config,
    spec_thresholds,
)
from _cycling_accessibility import (  # noqa: E402
    DMGAP_INFIX,
    MEASURE_ORDER,
    MEASURES,
)
from _cycling_lts_network import _data_path  # noqa: E402
from _utils import slugify  # noqa: E402
from data_dictionary import (  # noqa: E402
    URBAN_HEAT_STRUCTURE,
    describe_units,
    describe_variable,
)

# (parent index, sub-indicator names) for the urban heat composite, so the
# picker lists each sub-index ahead of the sub-indicators feeding it.
URBAN_HEAT_STRUCTURE_PARENTS = URBAN_HEAT_STRUCTURE

# ---------------------------------------------------------------------------
# Networks.  Walking is the implicit base network -- it has no infix because its
# columns carry their own 'walk' word -- and every cycling measure contributes a
# network whose column infix is defined once, in _cycling_accessibility.MEASURES.
# 'dmgap' is not a routable network but the paired contrast between two of them;
# it is offered as a network so the viewer can present it in the same control.
WALK = 'walk'
# A network has two names: the one a dropdown shows ("Caminando"), and the one
# a sentence needs ("using the *pedestrian* network").  The second is the
# `phrase`; without it every composed sentence reads "using the Walking
# network", which is why they used to be written as "red: caminando" instead.
NETWORKS = {
    WALK: {
        'infix': None,
        'mode': 'walk',
        'label': {'es': 'Caminando', 'en': 'Walking'},
        'phrase': {'es': 'peatonal', 'en': 'pedestrian'},
        'description': {
            'es': 'Red peatonal completa, sin restricción de tráfico.',
            'en': 'The full pedestrian network, with no traffic restriction.',
        },
    },
}
# Spanish for the cycling measures.  MEASURES is shared with the analysis and
# the reports, which are English, so the translation lives here rather than
# being pushed back into the pipeline's own vocabulary.
NETWORK_ES = {
    'lts1': {
        'label': 'Ruta de bajo estrés (sólo LTS 1)',
        'phrase': 'ciclista de muy bajo estrés',
        'description': 'geométrica, totalmente LTS 1, permite desmontar',
    },
    'low_stress_ride': {
        'label': 'Pedaleo de bajo estrés, sin desmontar (LTS 1–2)',
        'phrase': 'ciclista de bajo estrés, sin desmontar',
        'description': 'geométrica, totalmente LTS ≤ 2, pedaleada de principio a fin',
    },
    'low_stress': {
        'label': 'Ruta de bajo estrés (LTS 1–2)',
        'phrase': 'ciclista de bajo estrés',
        'description': 'geométrica, totalmente LTS ≤ 2, permite empujar la bicicleta',
    },
    'danger_weighted': {
        'label': 'Ruta con penalización por estrés',
        'phrase': 'ciclista con penalización por estrés',
        'description': 'red ciclable completa, penalizando los tramos de mayor estrés',
    },
}
# English phrases for the same, since MEASURES supplies only the long label
NETWORK_EN_PHRASE = {
    'lts1': 'very low stress cycling',
    'low_stress_ride': 'low-stress riding',
    'low_stress': 'low-stress cycling',
    'danger_weighted': 'stress-weighted cycling',
}
for _key in MEASURE_ORDER:
    _m = MEASURES[_key]
    _es = NETWORK_ES.get(_key, {})
    NETWORKS[_key] = {
        'infix': _m['infix'],
        'mode': 'cycle',
        'label': {'en': _m['label'], **({'es': _es['label']} if _es else {})},
        'phrase': {
            'en': NETWORK_EN_PHRASE.get(_key, _m['label'].lower()),
            **({'es': _es['phrase']} if _es.get('phrase') else {}),
        },
        'description': {
            'en': _m['description'],
            **({'es': _es['description']} if _es else {}),
        },
    }
NETWORKS['dmgap'] = {
    'infix': DMGAP_INFIX,
    'mode': 'cycle',
    'label': {
        'es': 'Dependencia de desmontar',
        'en': 'Dismount dependence',
    },
    'phrase': {
        'es': 'que depende de desmontar',
        'en': 'dismount-dependent',
    },
    'description': {
        'en': (
            'The share of access that exists only because the rider may get '
            'off and walk the bike.'
        ),
    },
}
CYCLE_NETWORKS = [k for k in NETWORKS if k not in (WALK, 'dmgap')]

# Spanish labels for the fixed vocabulary.  Indicator descriptions themselves
# come from the generated data dictionary (English); where no Spanish string is
# supplied the viewer falls back to English, so the gap stays visible.
ES = {
    'Daily essential services': 'Servicios esenciales cotidianos',
    'Health, education and care': 'Salud, educación y cuidados',
    'Community, culture and recreation': 'Comunidad, cultura y recreación',
    'Employment': 'Empleo',
    'Transport': 'Transporte',
    'Open space': 'Espacio abierto',
    'Other': 'Otros',
}


# ---------------------------------------------------------------------------
# Configuration


def dashboard_config(r):
    """The region's ``dashboard`` block, with defaults filled in."""
    config = dict((r.config or {}).get('dashboard') or {})
    config.setdefault('slug', slugify(r.name))
    label = config.get('label') or r.name
    config['label'] = label if isinstance(label, dict) else {'en': label}
    # the application's own title, distinct from the dataset's label
    title = config.get('title') or config['label']
    config['title'] = title if isinstance(title, dict) else {'en': title}
    config.setdefault('regions', {})
    config.setdefault('scale_labels', {})
    return config


def _labels(value, fallback):
    """Normalise a label to an ``{es, en}`` mapping."""
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if v}
    return {'en': value or fallback}


# ---------------------------------------------------------------------------
# Scales
#
# A "scale" is one set of areas the indicators have been aggregated to: the
# population grid, each configured custom aggregation, and the study region as a
# whole.  _12_aggregation writes each to ``indicators_<key>`` and keeps the
# imported source boundaries in ``agg_<key>``; the two differ, because areas that
# received no source units are deleted from the indicator table
# (_12_aggregation.py:570).  Exporting from a LEFT JOIN of the boundaries onto the
# indicators is what keeps those areas visible as "no data" rather than as holes.

GRID_SCALE = 'grid'


def _sql_key(name):
    return name.replace(' ', '_').lower()


def discover_scales(r, config):
    """Ordered scale definitions available in this region's database."""
    tables = set(r.get_tables())
    scales = {}

    grid_table = r.config.get('grid_summary')
    if grid_table in tables:
        resolution = r.config['population']['resolution']
        scales[GRID_SCALE] = {
            'key': GRID_SCALE,
            'table': grid_table,
            'boundaries': grid_table,
            'id': 'grid_id',
            'weight': 'pop_est',
            'source': 'grid',
            # the configured label wins here as it does for every custom
            # aggregation; the derived one is only a fallback
            'label': (
                _labels(
                    config['scale_labels'].get(GRID_SCALE),
                    f'{resolution} grid',
                )
                if config['scale_labels'].get(GRID_SCALE)
                else {
                    'es': f'Cuadrícula de {resolution}',
                    'en': f'{resolution} grid',
                }
            ),
        }

    for agg, spec in (r.config.get('custom_aggregations') or {}).items():
        key = _sql_key(agg)
        table, boundaries = f'indicators_{key}', f'agg_{key}'
        if table not in tables:
            continue
        scales[key] = {
            'key': key,
            'table': table,
            'boundaries': boundaries if boundaries in tables else table,
            'id': _sql_key(spec.get('id') or 'ogc_fid'),
            'weight': spec.get('weight'),
            'source': spec.get('aggregation_source'),
            'keep_columns': [
                _sql_key(c)
                for c in str(spec.get('keep_columns') or '').split(',')
                if c.strip()
            ],
            'label': _labels(config['scale_labels'].get(agg), agg),
        }

    requested = config.get('scales')
    if requested:
        missing = [s for s in requested if s not in scales]
        if missing:
            print(f'  ! configured scales not found, skipping: {missing}')
        return [scales[s] for s in requested if s in scales]
    return list(scales.values())


# ---------------------------------------------------------------------------
# Column canonicalisation
#
# The same indicator does not always carry the same column name at every scale.
# The columns propagated from the sample points (pct_access_walk_*,
# avg_cycle_dist_*, urban_heat_*, local_*) do -- they are added to every scale by
# the same pass -- but the columns produced by the weighted aggregation itself
# take a prefix that depends on how the area was weighted: 'pop_' where it was
# weighted by population estimate, none where it was not.  So an AGEB carries
# pop_pct_access_500m_fresh_food_market_score and a Condesa lot carries
# pct_access_500m_fresh_food_market_score for the same quantity.
#
# The exporter resolves each to one canonical (unprefixed) name and renames on
# the way out, so the viewer's paint expressions are scale-independent.  Which
# physical column supplied it is recorded per scale, because it changes what the
# number means and the info panel has to say so.
WEIGHTED_PREFIXES = ('pop_est_', 'pop_')
# canonical name -> the population-weighted variants that may stand in for it
CANONICAL_ALIASES = {
    'local_walkability': ('pop_walkability',),
    'local_daily_living': ('pop_daily_living',),
    'local_nh_population_density': ('pop_nh_pop_density',),
    'local_nh_intersection_density': ('pop_nh_intersection_density',),
}


def table_columns(r, table):
    """Ordered column names of a table."""
    return list(
        r.get_df(
            f"""SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{table}'
                ORDER BY ordinal_position""",
        )['column_name'],
    )


def canonical_columns(r, table):
    """Map canonical indicator names to the physical column carrying them.

    Returns ``{canonical: (physical, weighting)}`` where weighting is 'weighted'
    when the value came from a population-weighted aggregation column, 'direct'
    when the column already carries the canonical name.
    """
    present = table_columns(r, table)
    resolved = {}
    for column in present:
        resolved.setdefault(column, (column, 'direct'))
    for column in present:
        for prefix in WEIGHTED_PREFIXES:
            if column.startswith(prefix):
                canonical = column[len(prefix) :]
                if canonical not in resolved:
                    resolved[canonical] = (column, 'weighted')
                break
    for canonical, aliases in CANONICAL_ALIASES.items():
        if canonical in resolved:
            continue
        for alias in aliases:
            if alias in present:
                resolved[canonical] = (alias, 'weighted')
                break
    return resolved


# ---------------------------------------------------------------------------
# Column algebra
#
# One place where the naming conventions of _pedestrian_accessibility and
# _cycling_accessibility (as carried through to the aggregated scales by
# _12_aggregation) are expressed.  The viewer never rebuilds a column name: it
# reads the ones emitted here, so a convention can change in one place.


def access_column(network, name, distance):
    if network == WALK:
        return f'pct_access_walk_{name}_{distance}m'
    return f'pct_access_cycle_{NETWORKS[network]["infix"]}{name}_{distance}m'


def beyond_column(name, distance):
    """Disamenity polarity: the share living beyond the threshold."""
    return f'pct_beyond_walk_{name}_{distance}m'


def distance_column(network, name):
    if network == WALK:
        return f'avg_walk_dist_{name}'
    if network == 'dmgap':
        # not a distance to the destination but the extra riding needed to
        # avoid the links a rider would otherwise have to walk
        return f'avg_cycle_extra_{DMGAP_INFIX}{name}'
    return f'avg_cycle_dist_{NETWORKS[network]["infix"]}{name}'


def count_column(set_name, group, distance):
    return f'avg_count_walk_{set_name}__{group}_{distance}m'


def diversity_column(set_name, distance):
    return f'avg_diversity_walk_{set_name}_{distance}m'


def richness_column(set_name, distance):
    return f'avg_richness_walk_{set_name}_{distance}m'


# ---------------------------------------------------------------------------
# Indicator vocabulary

HIGHER, LOWER = 'higher_is_better', 'lower_is_better'

# Measure kinds.  'banded' indicators exist at several distance thresholds at
# once and are drawn with the nested-isochrone colour scheme and its clickable
# distance-band legend; 'continuous' indicators take a single value per area and
# are drawn with a class-banded sequential ramp.
BANDED, CONTINUOUS = 'banded', 'continuous'

MEASURE_META = {
    'access': {
        'kind': BANDED,
        'direction': HIGHER,
        'units': 'percent',
        'label': {'es': 'Acceso (%)', 'en': 'Access (%)'},
    },
    'beyond': {
        'kind': BANDED,
        'direction': HIGHER,
        'units': 'percent',
        'label': {'es': 'Más allá de (%)', 'en': 'Beyond (%)'},
    },
    'distance': {
        'kind': CONTINUOUS,
        'direction': LOWER,
        'units': 'metres',
        'label': {
            'es': 'Distancia promedio a lo más cercano (m)',
            'en': 'Average distance to closest (m)',
        },
    },
    'dmextra': {
        'kind': CONTINUOUS,
        'direction': LOWER,
        'units': 'metres',
        'label': {
            'es': 'Desvío adicional para evitar desmontar (m)',
            'en': 'Extra riding to avoid dismounting (m)',
        },
    },
    'count': {
        'kind': CONTINUOUS,
        'direction': HIGHER,
        'units': 'count',
        'label': {
            'es': 'Número promedio alcanzable',
            'en': 'Average number reachable',
        },
    },
    'diversity': {
        'kind': CONTINUOUS,
        'direction': HIGHER,
        'units': 'index 0-1',
        'label': {'es': 'Diversidad', 'en': 'Diversity'},
    },
    'richness': {
        'kind': CONTINUOUS,
        'direction': HIGHER,
        'units': 'index 0-1',
        'label': {'es': 'Riqueza', 'en': 'Richness'},
    },
    'value': {
        'kind': CONTINUOUS,
        'direction': HIGHER,
        'units': '',
        'label': {'es': 'Valor', 'en': 'Value'},
    },
}

# ---------------------------------------------------------------------------
# The sentences the viewer composes.
#
# These are emitted as data rather than written into the viewer's JavaScript, so
# that the wording can be revised in the site's own ``data/<slug>/text.json``
# -- edit, refresh, done -- without a code change, a re-export or a rebuild.
# Anything set there overrides what is here.
#
# Placeholders, substituted from the current selection:
#
#   {network}       the network as a sentence names it ("pedestrian")
#   {networkLabel}  the network as the dropdown names it ("Walking")
#   {distance}      the selected distance, e.g. "500 m"
#   {bands}         every distance offered, "500 m / 1000 m / 1500 m"
#   {indicator}     the indicator's own name
#   {description}   its data-dictionary description
#
# ``showing`` is the plain sentence under the indicator name in the sidebar;
# ``notes`` is the "how to read this" paragraph in the info panel, which is
# about how to read a *kind* of number rather than any one variable.
DEFAULT_TEXT = {
    'showing': {
        'access': {
            'es': (
                'Porcentaje de la población con acceso dentro de {distance}, '
                'usando la red {network}.'
            ),
            'en': (
                'Percentage of the population with access within {distance}, '
                'using the {network} network.'
            ),
        },
        'beyond': {
            'es': (
                'Porcentaje de la población que vive más allá de {distance} '
                'del destino, usando la red {network}. Aquí estar lejos es lo '
                'deseable.'
            ),
            'en': (
                'Percentage of the population living beyond {distance} of the '
                'destination, using the {network} network. Here, being far '
                'away is the good outcome.'
            ),
        },
        'distance': {
            'es': (
                'Distancia promedio a lo más cercano, usando la red {network}.'
            ),
            'en': (
                'Average distance to the closest, using the {network} network.'
            ),
        },
        'dmextra': {
            'es': (
                'Metros adicionales de pedaleo necesarios para evitar los '
                'tramos que de otro modo habría que caminar empujando la '
                'bicicleta.'
            ),
            'en': (
                'Extra metres of riding needed to avoid the links a rider '
                'would otherwise have to walk the bike along.'
            ),
        },
        'count': {
            'es': (
                'Número promedio de establecimientos de este subtipo '
                'alcanzables dentro de {distance}.'
            ),
            'en': (
                'Average number of establishments of this sub-type reachable '
                'within {distance}.'
            ),
        },
        'diversity': {
            'es': (
                'Qué tan uniformemente se reparte entre subtipos lo que es '
                'alcanzable dentro de {distance}: 1 es un reparto '
                'perfectamente uniforme.'
            ),
            'en': (
                'How evenly what is reachable within {distance} is spread '
                'across sub-types: 1 is a perfectly even spread.'
            ),
        },
        'richness': {
            'es': (
                'Proporción de los subtipos configurados que son alcanzables '
                'dentro de {distance} — cuántas clases distintas, no cuántos '
                'establecimientos.'
            ),
            'en': (
                'The share of configured sub-types reachable within '
                '{distance} — how many distinct kinds, not how many '
                'establishments.'
            ),
        },
        'value': {
            'es': '{description}',
            'en': '{description}',
        },
    },
    'notes': {
        'access': {
            'es': (
                'El valor es el porcentaje de los puntos de muestreo de un '
                'área que alcanzan el destino dentro de la distancia '
                'seleccionada, ponderado por población. Cada distancia se '
                'mide por separado, y el acceso a una distancia corta implica '
                'acceso a una más larga: por eso las tres cifras de la tabla '
                'crecen de izquierda a derecha.'
            ),
            'en': (
                'The value is the percentage of an area’s sample points that '
                'reach the destination within the selected distance, weighted '
                'by population. Each distance is measured separately, and '
                'access within a shorter distance implies access within a '
                'longer one — which is why the three figures in the table '
                'rise from left to right.'
            ),
        },
        'beyond': {
            'es': (
                'Este destino se mide con polaridad inversa: es una '
                'desamenidad, y lo que se reporta es la proporción que vive '
                'más allá de la distancia. Un valor más alto es mejor.'
            ),
            'en': (
                'This destination is measured with the opposite polarity: it '
                'is a disamenity, and what is reported is the share living '
                'beyond the distance. A higher value is better.'
            ),
        },
        'distance': {
            'es': (
                'Distancia promedio por la red hasta el destino más cercano. '
                'Se censura en la distancia configurada más amplia, por lo '
                'que un área sin nada dentro de ella no tiene valor en lugar '
                'de una distancia inventada.'
            ),
            'en': (
                'Average network distance to the nearest destination. It is '
                'censored at the largest configured distance, so an area with '
                'nothing within that distance has no value rather than an '
                'invented one.'
            ),
        },
        'dmextra': {
            'es': (
                'Metros adicionales de pedaleo necesarios para evitar los '
                'tramos que de otro modo habría que caminar empujando la '
                'bicicleta. Se promedia sólo donde ese rodeo tiene un costo.'
            ),
            'en': (
                'Extra metres of riding needed to avoid the links a rider '
                'would otherwise have to walk the bike along. Averaged only '
                'where that detour costs anything.'
            ),
        },
        'count': {
            'es': (
                'Número promedio de establecimientos de este subtipo '
                'alcanzables dentro de la distancia. Un conteo no es una '
                'proporción de la población: no está escalado a porcentaje.'
            ),
            'en': (
                'Average number of establishments of this sub-type reachable '
                'within the distance. A count is not a share of a population, '
                'so it is not scaled to a percentage.'
            ),
        },
        'diversity': {
            'es': (
                'Entropía de Shannon normalizada de los subtipos alcanzables: '
                'qué tan uniformemente se reparte lo alcanzable entre los '
                'subtipos configurados. Cinco panaderías y cinco '
                'establecimientos distintos puntúan igual en acceso, y no '
                'deberían.'
            ),
            'en': (
                'Normalised Shannon entropy of the reachable sub-types: how '
                'evenly what is reachable is spread across the configured '
                'sub-types. Five bakeries and five different kinds of shop '
                'score the same for access, and should not.'
            ),
        },
        'richness': {
            'es': (
                'Proporción de los subtipos configurados de un conjunto que '
                'son alcanzables — cuántas clases distintas, no cuántos '
                'establecimientos.'
            ),
            'en': (
                'The share of a set’s configured sub-types that are reachable '
                '— how many distinct kinds, not how many establishments.'
            ),
        },
        'value': {
            'es': (
                'Un único valor por área. Consulte el diccionario de datos '
                'para su definición completa y sus unidades.'
            ),
            'en': (
                'A single value per area. See the data dictionary for its '
                'full definition and units.'
            ),
        },
    },
    'scale_note': {
        'es': (
            'La escala de agregación cambia el resultado: no todas cubren el '
            'mismo terreno. Sólo la cuadrícula y la región cubren toda el '
            'área de estudio.'
        ),
        'en': (
            'The aggregation scale changes the result: they do not all cover '
            'the same ground. Only the grid and the region cover the whole '
            'study area.'
        ),
    },
}


# Domains for destination layers that are not DENUE points_of_interest entries
# (which declare their own ``domain``).
# Domains for the global default destination categories, which are declared in
# the accessibility config rather than in points_of_interest and so carry no
# domain of their own.
CATEGORY_DOMAINS = {
    'food': 'Daily essential services',
    'pos': 'Open space',
    'blue_space': 'Open space',
    'public_open_space_with_water': 'Open space',
    'pt': 'Transport',
}
LAYER_DOMAINS = {
    'aos_public_large_nodes_30m_line': 'Open space',
    'aos_public_any_nodes_30m_line': 'Open space',
    'aos_public_water_nodes_30m_line': 'Open space',
    'blue_space_nodes_30m_line': 'Open space',
    'lpugs_nodes_30m_line': 'Open space',
    'pt_stops_headway': 'Transport',
}
DEFAULT_DOMAIN = 'Other'

_QUOTED = re.compile(r"'([^']*)'")


def destination_names(spec):
    """The ``dest_name`` values a spec selects from the destinations layer."""
    if spec.get('layer') != 'destinations':
        return []
    return _QUOTED.findall(spec.get('where') or '')


def spec_domain(r, spec):
    """The reporting domain a destination spec belongs to."""
    poi = (r.config or {}).get('points_of_interest') or {}
    for name in destination_names(spec):
        domain = (poi.get(name) or {}).get('domain')
        if domain:
            return domain
    domain = spec.get('domain') or CATEGORY_DOMAINS.get(spec.get('category'))
    if domain:
        return domain
    return LAYER_DOMAINS.get(spec.get('layer'), DEFAULT_DOMAIN)


def spec_overlay(spec):
    """Where the viewer finds the points this indicator was measured to."""
    names = destination_names(spec)
    if names:
        return {'layer': 'destinations', 'dest_names': names}
    return {'layer': spec.get('layer')}


def humanise(name):
    return name.replace('_', ' ').strip().capitalize()


def _mode_configs(r):
    """Effective pedestrian and cycling accessibility configurations."""
    from _cycling_lts_network import cycling_config
    from _pedestrian_accessibility import pedestrian_config, resolve_thresholds

    shared = accessibility_config(r)
    pedestrian = pedestrian_config(r)
    ped = None
    if pedestrian is not None:
        ped = {
            'config': pedestrian,
            'thresholds': list(resolve_thresholds(pedestrian)),
            'specs': list(
                pedestrian.get('destinations') or DEFAULT_DESTINATIONS,
            ),
        }
    cycling = cycling_config(r)
    cyc = None
    if cycling is not None:
        merged = effective_config(shared, cycling)
        cyc = {
            'config': merged,
            'thresholds': sorted(
                {
                    int(d)
                    for d in (
                        merged.get('distances') or (500, 1000, 2000, 5000)
                    )
                },
            ),
            'specs': list(merged.get('destinations') or DEFAULT_DESTINATIONS),
            'networks': [k for k in CYCLE_NETWORKS],
        }
    return ped, cyc


def _banded_measure(available, name, networks, thresholds, builder, meta_key):
    """A banded measure as ``{network: {distance: column}}``."""
    out = {}
    for network in networks:
        bands = {
            str(d): builder(network, name, d)
            for d in thresholds
            if builder(network, name, d) in available
        }
        if bands:
            out[network] = bands
    if not out:
        return None
    entry = dict(MEASURE_META[meta_key])
    entry['networks'] = out
    return entry


def destination_families(r, ped, cyc, available):
    """One family per destination spec, merging its walking and cycling measures."""
    families = {}
    for mode, resolved, networks in (
        ('walk', ped, [WALK]),
        ('cycle', cyc, (cyc or {}).get('networks', [])),
    ):
        if resolved is None:
            continue
        thresholds = spec_thresholds(resolved['specs'], resolved['thresholds'])
        for spec in resolved['specs']:
            name = spec['name']
            bands = list(thresholds.get(name, resolved['thresholds']))
            family = families.setdefault(
                name,
                {
                    'id': name,
                    'group': 'destination',
                    'domain': spec_domain(r, spec),
                    'category': spec.get('category'),
                    'variant': spec.get('variant'),
                    'label': {'en': humanise(name)},
                    'overlay': spec_overlay(spec),
                    'measures': {},
                },
            )
            avoid = str(spec.get('direction') or '').lower() == AVOID
            key = 'beyond' if avoid else 'access'
            builder = (
                (lambda n, s, d: beyond_column(s, d))
                if avoid
                else access_column
            )
            measure = _banded_measure(
                available,
                name,
                networks,
                bands,
                builder,
                key,
            )
            if measure:
                existing = family['measures'].get(key)
                if existing:
                    existing['networks'].update(measure['networks'])
                else:
                    family['measures'][key] = measure
            for network in networks:
                column = distance_column(network, name)
                if column not in available:
                    continue
                meta_key = 'dmextra' if network == 'dmgap' else 'distance'
                entry = family['measures'].setdefault(
                    meta_key,
                    dict(MEASURE_META[meta_key], networks={}),
                )
                entry['networks'][network] = column
    # the dismount-dependence contrast is a network of the access measure, but
    # its polarity is the opposite of the access it is derived from
    for family in families.values():
        access = family['measures'].get('access')
        if access and 'dmgap' in access.get('networks', {}):
            access.setdefault('network_direction', {})['dmgap'] = LOWER
    return [f for f in families.values() if f['measures']]


def _derived_families(
    resolved,
    networks,
    available,
    names,
    group,
    domain,
    overlay_for=None,
    labels=None,
):
    """Families for derived destinations (activity centres, composites).

    These are measured exactly like any other destination -- banded access and
    mean distance -- so they differ from ``destination_families`` only in where
    their names come from and that they have no configured spec.
    """
    families = {}
    for name in names:
        family = {
            'id': name,
            'group': group,
            'domain': domain,
            'label': (labels or {}).get(name) or {'en': humanise(name)},
            'measures': {},
        }
        if overlay_for:
            overlay = overlay_for(name)
            if overlay:
                family['overlay'] = overlay
        measure = _banded_measure(
            available,
            name,
            networks,
            resolved['thresholds'],
            access_column,
            'access',
        )
        if measure:
            family['measures']['access'] = measure
        distances = {
            network: distance_column(network, name)
            for network in networks
            if distance_column(network, name) in available
        }
        if distances:
            family['measures']['distance'] = dict(
                MEASURE_META['distance'],
                networks=distances,
            )
        if family['measures']:
            families[name] = family
    return families


def _merge_families(into, more):
    for name, family in more.items():
        existing = into.get(name)
        if not existing:
            into[name] = family
            continue
        for key, measure in family['measures'].items():
            current = existing['measures'].get(key)
            if current:
                current['networks'].update(measure['networks'])
            else:
                existing['measures'][key] = measure


def activity_centre_names(config):
    """The derived activity-centre destination names, per definition and tier."""
    names, labels = [], {}
    for set_name, definition in activity_centre_definitions(config).items():
        for tier in definition['tiers']:
            name = (
                f'activity_centre_{tier}'
                if set_name == STANDARD_SET
                else f'activity_centre_{set_name}_{tier}'
            )
            names.append(name)
            categories = ', '.join(definition['categories'])
            labels[name] = {
                'en': (
                    f'{humanise(set_name)} activity centre ({tier}), '
                    f'{definition["walk_threshold"]} m: {categories}'
                ),
            }
    return names, labels


def combined_access_names(config, specs):
    """The composite 'everything reachable' destination names."""
    names, labels = [], {}
    for set_name, categories in combined_access_sets(config, specs).items():
        for variant in ('strict', 'lenient'):
            name = (
                f'all_{variant}'
                if set_name == STANDARD_SET
                else f'all_{set_name}_{variant}'
            )
            names.append(name)
            labels[name] = {
                'en': (f'All of {", ".join(categories)} ({variant} variant)'),
            }
    return names, labels


def diversity_families(r, ped, available):
    """Diversity, richness and per-sub-type count families."""
    if ped is None:
        return []
    sets = diversity_sets(ped['config'])
    families = []
    for set_name, spec in sets.items():
        bands = sorted(
            {int(d) for d in (spec['distances'] or ped['thresholds'])},
        )
        family = {
            'id': f'diversity_{set_name}',
            'group': 'diversity',
            'domain': 'Diversity',
            'label': {'en': f'{humanise(set_name)} diversity'},
            'measures': {},
            'groups': list(spec['groups']),
        }
        for key, builder in (
            ('diversity', diversity_column),
            ('richness', richness_column),
        ):
            columns = {
                str(d): builder(set_name, d)
                for d in bands
                if builder(set_name, d) in available
            }
            if columns:
                family['measures'][key] = dict(
                    MEASURE_META[key],
                    networks={WALK: columns},
                )
        for group in spec['groups']:
            columns = {
                str(d): count_column(set_name, group, d)
                for d in bands
                if count_column(set_name, group, d) in available
            }
            if columns:
                family['measures'].setdefault(
                    'count',
                    dict(MEASURE_META['count'], groups={}),
                )['groups'][group] = {WALK: columns}
        if family['measures']:
            families.append(family)
    return families


NEUTRAL = 'neutral'

# Standalone indicators: one column each, grouped for the picker.  Direction is
# stated per variable because it is not derivable from the name -- a higher
# albedo is better and a higher land surface temperature is worse, and both are
# urban_heat_ columns.
URBAN_HEAT_DIRECTION = {
    'urban_heat_land_surface_albedo': HIGHER,
    'urban_heat_ndvi': HIGHER,
    'urban_heat_subnational_hdi': HIGHER,
    'urban_heat_adaptive_capability_index': HIGHER,
}
STANDALONE_GROUPS = [
    {
        'id': 'walkability',
        'domain': 'Walkability',
        'label': {'es': 'Caminabilidad', 'en': 'Walkability'},
        'columns': [
            'local_walkability',
            'local_daily_living',
            'local_nh_population_density',
            'local_nh_intersection_density',
        ],
        'direction': HIGHER,
    },
    {
        'id': 'urban_heat',
        'domain': 'Urban heat',
        'label': {
            'es': 'Vulnerabilidad al calor urbano',
            'en': 'Urban heat vulnerability',
        },
        'columns': (
            ['urban_heat_guhvi', 'urban_heat_guhvi_class']
            + [
                f'urban_heat_{parent}'
                for parent, _ in URBAN_HEAT_STRUCTURE_PARENTS
            ]
            + [
                f'urban_heat_{sub}'
                for _, subs in URBAN_HEAT_STRUCTURE_PARENTS
                for sub in subs
            ]
            + ['pct_urban_heat_guhvi_class_5_most_vulnerable']
        ),
        'direction': LOWER,
        'direction_overrides': URBAN_HEAT_DIRECTION,
    },
    {
        'id': 'context',
        'domain': 'Context',
        'label': {'es': 'Contexto', 'en': 'Context'},
        'columns': [
            'pop_est',
            'pop_per_sqkm',
            'area_sqkm',
            'intersection_count',
            'intersections_per_sqkm',
        ],
        'direction': NEUTRAL,
    },
]


def core_access_family(available):
    """The fixed indicators.yml 500 m access scores, kept as their own group.

    These are the globally comparable core measures; they are not part of the
    configurable banded vocabulary and always sit at 500 m.
    """
    columns = sorted(
        c
        for c in available
        if c.startswith('pct_access_500m_') and c.endswith('_score')
    )
    if not columns:
        return None
    return {
        'id': 'core_access',
        'group': 'standalone',
        'domain': 'Core access (500 m)',
        'label': {
            'es': 'Acceso central a 500 m',
            'en': 'Core access within 500 m',
        },
        'direction': HIGHER,
        'measures': {
            'value': dict(
                MEASURE_META['value'],
                direction=HIGHER,
                units='percent',
                variables={c: {WALK: c} for c in columns},
            ),
        },
    }


def standalone_families(available):
    families = []
    for group in STANDALONE_GROUPS:
        columns = [c for c in group['columns'] if c in available]
        if not columns:
            continue
        overrides = group.get('direction_overrides') or {}
        families.append(
            {
                'id': group['id'],
                'group': 'standalone',
                'domain': group['domain'],
                'label': group['label'],
                'direction': group['direction'],
                'measures': {
                    'value': dict(
                        MEASURE_META['value'],
                        direction=group['direction'],
                        variables={c: {WALK: c} for c in columns},
                        variable_direction={
                            c: overrides[c] for c in columns if c in overrides
                        },
                    ),
                },
            },
        )
    return families


def _normalise(text):
    """Fold a label to a comparison key: case, accents and spacing all vary."""
    import unicodedata

    folded = unicodedata.normalize('NFKD', str(text or ''))
    folded = ''.join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(r'[^a-z0-9]+', ' ', folded.lower())
    return folded.strip()


# Spellings in the source material that must not become a second theme: the
# intervention sheet writes one theme both with and without a space before its
# bracket, and spells "transporte" as "transprote" in one place.
_SPELLING = {'transprote': 'transporte'}


def _theme_key(text):
    return ' '.join(_SPELLING.get(w, w) for w in _normalise(text).split())


def resolve_themes(config):
    """The workshop's themes: ``{id: {label, color, families, keys}}``.

    Themes are the vocabulary the workshop itself uses -- its printed materials
    are organised and coloured by them -- so they are declared in the region
    config rather than derived from the analysis, which knows only its own
    reporting domains.
    """
    themes = {}
    for key, spec in (config.get('themes') or {}).items():
        spec = spec or {}
        label = _labels(spec.get('label'), key)
        matches = spec.get('match') or [label.get('es'), label.get('en'), key]
        themes[key] = {
            'id': key,
            'label': label,
            'color': spec.get('color'),
            'families': list(spec.get('families') or []),
            # every spelling this theme should be recognised by when the
            # intervention sheet is matched against it
            'keys': sorted({_theme_key(m) for m in matches if m}),
        }
    return themes


def apply_labels(config, families, descriptions):
    """Overlay configured ``{es, en}`` labels onto the derived ones.

    A family name is otherwise a humanised column name -- "Denue pharmacy" --
    which is neither Spanish nor what anyone calls the thing.
    """
    labels = config.get('labels') or {}
    family_labels = labels.get('families') or {}
    variable_labels = labels.get('variables') or {}
    missing = []
    for family in families:
        configured = family_labels.get(family['id'])
        if configured:
            family['label'] = _labels(configured, family['id'])
        elif 'es' not in (family.get('label') or {}):
            missing.append(family['id'])
    for variable, configured in variable_labels.items():
        if variable in descriptions:
            descriptions[variable]['label'] = _labels(configured, variable)
    if missing:
        print(
            f'  ! {len(missing)} families have no Spanish label: '
            f'{", ".join(missing[:6])}' + (' ...' if len(missing) > 6 else ''),
        )
    return families


def assign_themes(themes, families):
    """Tag each family with its theme, and each theme with its families.

    An unthemed family is reported rather than silently dropped: with themes as
    the primary grouping, an indicator that cannot be navigated to may as well
    not have been produced.
    """
    by_family = {}
    for theme in themes.values():
        for family_id in theme['families']:
            by_family[family_id] = theme['id']
    unthemed = []
    for family in families:
        theme = by_family.get(family['id'])
        if theme:
            family['theme'] = theme
        else:
            unthemed.append(family['id'])
    if unthemed:
        print(
            f'  ! {len(unthemed)} families have no theme: '
            f'{", ".join(unthemed[:6])}'
            + (' ...' if len(unthemed) > 6 else ''),
        )
    known = {f['id'] for f in families}
    for theme in themes.values():
        unknown = [f for f in theme['families'] if f not in known]
        if unknown:
            print(
                f'  ! theme "{theme["id"]}" lists families not produced here: '
                f'{", ".join(unknown)}',
            )
        theme['families'] = [f for f in theme['families'] if f in known]
    return families


def load_interventions(path, themes):
    """Interventions and their impacts, from the workshop's matching sheet.

    Columns: TEMA | number | intervention | core measure | Reimagina | impact.
    TEMA and the intervention columns are merged down in the source, so they
    are carried forward; an intervention appears once per core measure it
    touches and is folded back into a single entry here.
    """
    if not path:
        return []
    resolved = path
    if not os.path.isabs(resolved):
        resolved = _data_path(path)
    if not os.path.exists(resolved):
        print(f'  ! interventions sheet not found, skipping: {resolved}')
        return []
    import openpyxl

    workbook = openpyxl.load_workbook(resolved, data_only=True)
    sheet = workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    by_key = {
        k: theme['id'] for theme in themes.values() for k in theme['keys']
    }
    unmatched = set()
    entries = {}
    carried = ['', '', '', '']
    splitter = re.compile(r':|\s{2,}')
    for row in rows[1:]:
        cells = [
            '' if c is None else str(c).replace('\n', ' ').strip() for c in row
        ]
        cells += [''] * (6 - len(cells))
        tema, number, name, measure, reimagina, impact = cells[:6]
        for i, value in enumerate((tema, number, name, reimagina)):
            if value:
                carried[i] = value
        tema, number, name, reimagina = carried
        if not number or not name:
            continue
        parts = splitter.split(name, maxsplit=1)
        entry = entries.setdefault(
            number,
            {
                'n': number,
                # the sheet packs a title and its description into one cell,
                # separated by a colon or a run of spaces
                'name': parts[0].strip(),
                'description': parts[1].strip() if len(parts) > 1 else '',
                'reimagina': reimagina,
                'themes': {},
                'core_measures': [],
            },
        )
        theme_id = by_key.get(_theme_key(tema))
        if not theme_id and tema:
            unmatched.add(tema)
        if measure and measure not in entry['core_measures']:
            entry['core_measures'].append(measure)
        # Impacts are recorded per theme, not pooled.  An intervention is only
        # offered for a theme where the sheet actually states what it would do
        # there: "Ciclovía" is tagged to six themes but carries no impact under
        # Essential services, and showing it against fresh food -- as the only
        # entry -- read as noise.
        if theme_id and impact:
            impacts = entry['themes'].setdefault(theme_id, [])
            if impact not in impacts:
                impacts.append(impact)
    if unmatched:
        print(
            '  ! intervention themes not matched to a configured theme: '
            f'{"; ".join(sorted(unmatched))}',
        )
    kept = [e for e in entries.values() if e['themes']]
    dropped = len(entries) - len(kept)
    print(
        f'  Interventions: {len(kept)} from {os.path.basename(resolved)}'
        + (f' ({dropped} with no stated impact, omitted)' if dropped else ''),
    )
    return kept


def load_crosswalk(path):
    """ULI core-measure crosswalk as ``{variable: {...}}``, or {}.

    The crosswalk states which project measure each GHSCI variable answers and
    with what relation and direction.  It is optional: without it the dashboard
    still works, it just has no core-measure view.
    """
    if not path:
        return {}
    resolved = path
    if not os.path.isabs(resolved):
        resolved = _data_path(path)
    if not os.path.exists(resolved):
        print(f'  ! crosswalk not found, skipping: {resolved}')
        return {}
    import yaml

    with open(resolved, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    out = {}
    for measure, entry in (data.get('core_measures') or {}).items():
        for sub in entry.get('sub_variables') or []:
            for variable in sub.get('variables') or []:
                out[variable] = {
                    'measure': measure,
                    'core_measure': entry.get('core_measure'),
                    'domains': entry.get('domains'),
                    'sub_variable': sub.get('name'),
                    'relation': sub.get('relation'),
                    'direction': sub.get('direction'),
                }
    print(f'  Crosswalk: {len(out)} variables mapped to core measures')
    return out


# How each measure reads in Spanish, given the indicator, the network and the
# band.  Composed rather than translated: every part is already in Spanish, so
# this gives a real Spanish description for the ~310 configurable columns
# without inventing prose for any of them.
SPANISH_DESCRIPTION = {
    'access': lambda f, net, band: (
        f'Proporción de puntos de muestreo con acceso a {band} m de: {f} '
        f'— red: {net}'
    ),
    'beyond': lambda f, net, band: (
        f'Proporción de puntos de muestreo a más de {band} m de: {f} '
        f'— red: {net}'
    ),
    'distance': lambda f, net, band: (
        f'Distancia media por la red hasta lo más cercano: {f} — red: {net}'
    ),
    'dmextra': lambda f, net, band: (
        f'Metros adicionales de pedaleo para evitar desmontar: {f}'
    ),
    'count': lambda f, net, band: (
        f'Número medio alcanzable a {band} m: {f} — red: {net}'
    ),
    # the family label already begins "Diversidad de ..." / "Riqueza de ...",
    # so these say the band and the network and let it speak for itself
    'diversity': lambda f, net, band: f'{f}, a {band} m — red: {net}',
    'richness': lambda f, net, band: f'{f}, a {band} m — red: {net}',
}


def compose_spanish_descriptions(families, descriptions):
    """Give every column a Spanish description built from translated parts.

    The generated data dictionary is English only, and translating its ~1,000
    sentences is not something to invent.  But the columns this dashboard
    exposes are almost all of the form "measure X of destination Y over network
    Z at band B", and every one of those parts already has a Spanish label -- so
    the sentence can be composed rather than translated.  Standalone variables
    (urban heat, walkability, context) carry a configured Spanish label instead.
    """
    composed = 0
    for family in families:
        spanish = (family.get('label') or {}).get('es')
        if not spanish:
            continue
        for key, measure in family['measures'].items():
            write = SPANISH_DESCRIPTION.get(key)
            if not write:
                continue
            for network, value in (measure.get('networks') or {}).items():
                network_es = (
                    (NETWORKS.get(network) or {}).get('label') or {}
                ).get('es') or network
                bands = {None: value} if isinstance(value, str) else value
                for band, column in bands.items():
                    entry = descriptions.setdefault(column, {})
                    entry['es'] = write(spanish, network_es, band)
                    composed += 1
            for by_network in (measure.get('groups') or {}).values():
                for network, bands in by_network.items():
                    network_es = (
                        (NETWORKS.get(network) or {}).get('label') or {}
                    ).get('es') or network
                    for band, column in bands.items():
                        entry = descriptions.setdefault(column, {})
                        entry['es'] = write(spanish, network_es, band)
                        composed += 1
    # standalone variables: the configured label is the description
    for column, entry in descriptions.items():
        if 'es' not in entry and entry.get('label', {}).get('es'):
            entry['es'] = entry['label']['es']
            composed += 1
    print(f'  Spanish descriptions composed for {composed} columns')
    return descriptions


_CODES = re.compile(r'codigo_act\s+IN\s*\(([^)]*)\)', re.IGNORECASE)


def destination_provenance(r, spec):
    """Where the points an indicator measured to actually came from.

    Read from the region's own ``points_of_interest`` entries, including the
    SCIAN activity codes the DENUE filter selects -- which is the level of
    detail somebody checking a Mexicali result will want, and which is
    otherwise buried in an ogr2ogr ``-where`` clause.
    """
    poi = (r.config or {}).get('points_of_interest') or {}
    sources = []
    for name in destination_names(spec):
        entry = poi.get(name)
        if not entry:
            continue
        codes = _CODES.search(str(entry.get('data') or ''))
        sources.append(
            {
                'dest_name': name,
                'name': entry.get('dest_name_full') or name,
                'codes': (
                    [c.strip().strip("'\"") for c in codes.group(1).split(',')]
                    if codes
                    else []
                ),
                'source': entry.get('source') or '',
                'publication_date': str(entry.get('publication_date') or ''),
                'url': entry.get('url') or '',
                'licence': entry.get('licence') or '',
                'citation': entry.get('citation') or '',
            },
        )
    return sources


def analysis_rules(r):
    """The rules the analysis applied, for the info panel's method section.

    Emitted once rather than per family: the pedestrian filter and the traffic
    stress thresholds are properties of the region's analysis, not of any one
    indicator.
    """
    from _cycling_lts_network import ADT_BY_GROUP, LTS_IMPED, cycling_config

    network = (r.config or {}).get('network') or {}
    # 'openstreetmap_query' is the current name for the OSMnx custom filter.
    # 'network' (active travel branch) and 'pedestrian' are its earlier
    # names, still read so this exporter works whichever way a region was
    # configured.  The emitted key is left as 'pedestrian_filter', which the
    # site consumes.
    openstreetmap_query = str(
        network.get('openstreetmap_query')
        or network.get('network')
        or network.get('pedestrian')
        or '',
    ).strip()
    rules = {
        'pedestrian_filter': openstreetmap_query,
        'retains_private_access': 'access' in openstreetmap_query,
        'osmnx_retain_all': bool(network.get('osmnx_retain_all')),
    }
    cycling = cycling_config(r)
    if cycling is not None:
        rules['cycling'] = {
            'adt_by_group': dict(ADT_BY_GROUP),
            'lts_impedance': {str(k): v for k, v in LTS_IMPED.items()},
            'danger_weight': (cycling or {}).get('danger_weight'),
            'dismount_weight': (cycling or {}).get('dismount_weight'),
        }
    return rules


def _family_columns(family):
    """Every physical column any measure of a family refers to."""
    columns = set()
    for measure in family['measures'].values():
        for holder in ('networks', 'variables'):
            for value in (measure.get(holder) or {}).values():
                if isinstance(value, dict):
                    columns.update(value.values())
                else:
                    columns.add(value)
        for by_network in (measure.get('groups') or {}).values():
            for bands in by_network.values():
                columns.update(bands.values())
    return columns


def build_indicators(r, config, available):
    """The faceted indicator vocabulary the dashboard navigates."""
    # Applied here rather than family by family: everything below is built from
    # `available`, so a hidden column simply never enters the vocabulary and
    # cannot reappear as a variable, a band or a dictionary entry.  Used for
    # outputs that are real but not worth navigating -- the GUHVI sub-indicators
    # include a subnational HDI and an infant mortality rate that are constant
    # across a single city and map as one flat colour.
    hidden = set(config.get('hide') or [])
    if hidden:
        available = {c for c in available if c not in hidden}
    ped, cyc = _mode_configs(r)
    families = {}
    for family in destination_families(r, ped, cyc, available):
        families[family['id']] = family

    for resolved, networks in (
        (ped, [WALK]),
        (cyc, (cyc or {}).get('networks', [])),
    ):
        if resolved is None or not networks:
            continue
        ac_names, ac_labels = activity_centre_names(resolved['config'])
        _merge_families(
            families,
            _derived_families(
                resolved,
                networks,
                available,
                ac_names,
                'activity_centre',
                'Activity centres',
                overlay_for=lambda n: {'layer': n},
                labels=ac_labels,
            ),
        )
        all_names, all_labels = combined_access_names(
            resolved['config'],
            resolved['specs'],
        )
        _merge_families(
            families,
            _derived_families(
                resolved,
                networks,
                available,
                all_names,
                'combined',
                'Combined access',
                labels=all_labels,
            ),
        )

    ordered = list(families.values())
    ordered += diversity_families(r, ped, available)
    core = core_access_family(available)
    if core:
        ordered.append(core)
    ordered += standalone_families(available)

    themes = resolve_themes(config)
    assign_themes(themes, ordered)
    # provenance, from the region's own configuration
    notes = config.get('notes') or {}
    ped, _cyc = _mode_configs(r)
    specs = {s['name']: s for s in (ped or {}).get('specs', [])}
    for family in ordered:
        spec = specs.get(family['id'])
        if spec:
            sources = destination_provenance(r, spec)
            if sources:
                family['sources'] = sources
        note = notes.get(family['id']) or (
            notes.get((family.get('overlay') or {}).get('layer'))
        )
        if note:
            family['note'] = _labels(note, '')
    crosswalk = load_crosswalk(config.get('crosswalk'))
    descriptions = {}
    for family in ordered:
        family.setdefault('group', 'destination')
        family.setdefault('direction', HIGHER)
        columns = _family_columns(family)
        uli = {}
        for column in sorted(columns):
            category, text = describe_variable(column)
            # units come from describe_units() rather than the region's
            # generated dictionary CSV: that file was written whenever
            # generate() last ran, so a correction to the units would not reach
            # the dashboard until the whole region was regenerated
            units, statistic = describe_units(column)
            descriptions[column] = {
                'category': category,
                'en': text,
                'units': units,
                'statistic': statistic,
            }
            entry = crosswalk.get(column)
            if entry:
                uli.setdefault(entry['measure'], entry)
                if entry.get('direction'):
                    descriptions[column]['direction'] = entry['direction']
        if uli:
            family['uli'] = list(uli.values())
        family['columns'] = sorted(columns)

    apply_labels(config, ordered, descriptions)
    compose_spanish_descriptions(ordered, descriptions)
    interventions = load_interventions(config.get('interventions'), themes)

    domains = []
    for family in ordered:
        if family['domain'] not in domains:
            domains.append(family['domain'])
    # only the networks something was actually measured over: a region that ran
    # two of the four cycling measures should not offer the other two at all
    used = {
        network
        for family in ordered
        for measure in family['measures'].values()
        for network in (measure.get('networks') or {})
    }
    return {
        # the sentences the viewer composes, as templates.  Emitted rather than
        # written into the JavaScript so that the wording can be revised in the
        # site's own text.json without a code change or a re-export; see
        # DEFAULT_TEXT for the placeholders each one may use.
        'text': DEFAULT_TEXT,
        # the workshop's own typology, and the primary grouping in the viewer;
        # the analysis-derived domains remain as a secondary one
        'themes': [
            {k: v for k, v in theme.items() if k != 'keys'}
            for theme in themes.values()
        ],
        'interventions': interventions,
        'rules': analysis_rules(r),
        'domains': [
            {'id': d, 'label': {'es': ES.get(d, d), 'en': d}} for d in domains
        ],
        'networks': {k: v for k, v in NETWORKS.items() if k in used},
        'measures': {k: v for k, v in MEASURE_META.items()},
        'families': ordered,
        'descriptions': descriptions,
    }


# ---------------------------------------------------------------------------
# Layer export

# Rounding, chosen per column so that tiles dedup well without losing meaning:
# percentages and metres are integers, indices on 0-1 keep three decimals, and
# anything else keeps two.
INTEGER_PREFIXES = (
    'pct_',
    'avg_walk_dist_',
    'avg_cycle_dist_',
    'avg_cycle_extra_',
    'intersection_count',
)
# pop_est is deliberately not an integer: where a scale's population is an
# assumed figure per unit rather than a count -- 3.2 residents per Condesa lot
# -- rounding is the difference between reporting the assumption and losing it,
# and it made the lot popup contradict the note printed beside it.  Whole
# numbers are unaffected: a grid cell of 47 people rounds to 47.0 and tiles
# dedup on it just the same.
INDEX_PREFIXES = (
    'avg_diversity_walk_',
    'avg_richness_walk_',
    'urban_heat_',
)


def round_expression(column, source='i'):
    """SQL that rounds a column to a sensible precision, aliased to itself."""
    qualified = f'{source}."{column}"'
    if column.startswith(INTEGER_PREFIXES):
        return f'ROUND({qualified}::numeric)::int AS "{column}"'
    if column.startswith(INDEX_PREFIXES):
        return f'ROUND({qualified}::numeric, 3)::float8 AS "{column}"'
    return f'ROUND({qualified}::numeric, 2)::float8 AS "{column}"'


def write_layer(gdf, path):
    """Write a layer as newline-delimited GeoJSON in EPSG:4326."""
    gdf = gdf.to_crs(4326)
    try:
        gdf.to_file(path, driver='GeoJSONSeq', COORDINATE_PRECISION=6)
    except Exception:
        gdf.to_file(path, driver='GeoJSONSeq')
    return len(gdf)


CONTEXT_COLUMNS = [
    'pop_est',
    'area_sqkm',
    'pop_per_sqkm',
    'intersection_count',
    'intersections_per_sqkm',
]


def scale_query(scale, resolved, wanted, with_geom=True):
    """SQL selecting one scale's areas, with every area kept.

    Areas that received no source units are deleted from the indicator table by
    _12_aggregation, so the boundaries are the left side of the join: an area
    with no result is exported with null values and drawn as 'no data' rather
    than silently missing from the map.
    """
    id_column = scale['id']
    joined = scale['boundaries'] != scale['table']
    source = 'i' if joined else 'b'
    select = [f'b."{id_column}"::text AS area_id']
    for column in scale.get('keep_columns') or []:
        select.append(f'b."{column}"')
    for canonical in wanted:
        physical, _ = resolved[canonical]
        expression = round_expression(physical, source)
        if physical != canonical:
            expression = f'{expression.rsplit(" AS ", 1)[0]} AS "{canonical}"'
        select.append(expression)
    if with_geom:
        select.append('b.geom')
    # ordered so that repeated exports are byte-reproducible: without it the
    # row order is whatever the planner returns, which changes both the feature
    # order in the layer and the weighted quantiles computed from it
    order_by = f'ORDER BY b."{id_column}"'
    if not joined:
        return f'SELECT {", ".join(select)} FROM {scale["table"]} b {order_by}'
    return (
        f'SELECT {", ".join(select)} FROM {scale["boundaries"]} b '
        f'LEFT JOIN {scale["table"]} i '
        f'ON i."{id_column}"::text = b."{id_column}"::text '
        f'{order_by}'
    )


def export_scale(r, scale, vocabulary_columns, outdir, write=True):
    """Write one scale's layer; returns its manifest entry."""
    resolved = canonical_columns(r, scale['table'])
    # de-duplicated: the context variables are also offered as a family, so
    # they appear in the vocabulary as well as in CONTEXT_COLUMNS
    wanted = [
        c
        for c in dict.fromkeys(list(vocabulary_columns) + CONTEXT_COLUMNS)
        if c in resolved
    ]
    # keep_columns are read from the boundaries, so only those actually there
    boundary_columns = set(table_columns(r, scale['boundaries']))
    scale = dict(
        scale,
        keep_columns=[
            c
            for c in (scale.get('keep_columns') or [])
            if c in boundary_columns
        ],
    )
    if scale['id'] not in boundary_columns:
        print(
            f'  ! {scale["key"]}: id column "{scale["id"]}" not on '
            f'{scale["boundaries"]}; falling back to ogc_fid',
        )
        scale['id'] = 'ogc_fid' if 'ogc_fid' in boundary_columns else 'fid'
    layer = f'scale_{scale["key"]}'
    if not write:
        # the geometry is unchanged, so only the feature count is needed and it
        # can be counted in the database instead of serialised out again
        features = int(
            r.get_df(
                f'SELECT count(*) AS n FROM {scale["boundaries"]}',
            )[
                'n'
            ].iloc[0],
        )
    else:
        gdf = r.get_gdf(scale_query(scale, resolved, wanted))
        if gdf is None:
            print(f'  ! {scale["key"]}: query failed, skipping')
            return None, None
        features = write_layer(gdf, f'{outdir}/{layer}.geojsonl')
    weighted = sorted(c for c in wanted if resolved[c][1] == 'weighted')
    print(f'  {layer}: {features} areas, {len(wanted)} indicators', flush=True)
    return scale, {
        'key': scale['key'],
        'layer': layer,
        'file': f'{layer}.geojsonl',
        'features': features,
        'label': scale['label'],
        'id': scale['id'],
        'weight': scale.get('weight'),
        'source': scale.get('source'),
        'keep_columns': scale['keep_columns'],
        'columns': wanted,
        # columns whose value came from a population-weighted aggregation
        # column rather than one carrying the canonical name: the same
        # quantity, differently derived, and the info panel says so
        'weighted_columns': weighted,
    }


# Edge attributes worth carrying into the network overlay's popups.
EDGE_COLUMNS = [
    'osmid',
    'name',
    'highway',
    'maxspeed_kmh',
    'adt',
    'bike_facility',
    'lvl_traf_stress',
    'bike_permitted',
    'foot_dismount',
]


def _previous_layers(outdir):
    """The layer index recorded by the last full export, for --no-layers."""
    path = f'{outdir}/manifest.json'
    if not os.path.exists(path):
        print(
            '  ! --no-layers with no previous manifest; layers will be empty',
        )
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('layers') or {}


def export_context_layers(r, indicators, outdir):
    """Write the overlay layers that explain a result.

    The points an indicator was measured to, the network it was measured over,
    and the region boundaries.
    """
    tables = set(r.get_tables())
    layers = {}

    def record(name, gdf, **extra):
        if gdf is None or len(gdf) == 0:
            return
        features = write_layer(gdf, f'{outdir}/{name}.geojsonl')
        # geometry type is recorded rather than inferred from the layer name:
        # the viewer needs to know whether to draw circles or lines, and open
        # space "entry point" layers are lines despite being conceptually points
        kinds = set(gdf.geom_type.dropna().unique())
        geometry = (
            'line'
            if any('Line' in k for k in kinds)
            else 'polygon' if any('Polygon' in k for k in kinds) else 'point'
        )
        layers[name] = dict(
            {
                'file': f'{name}.geojsonl',
                'features': features,
                'geometry': geometry,
            },
            **extra,
        )
        print(f'  {name}: {features} {geometry} features', flush=True)

    # every point layer any indicator refers to
    referenced = {}
    for family in indicators['families']:
        overlay = family.get('overlay')
        if overlay and overlay.get('layer'):
            referenced.setdefault(overlay['layer'], set()).update(
                overlay.get('dest_names') or [],
            )

    if 'destinations' in referenced and 'destinations' in tables:
        names = sorted(referenced.pop('destinations'))
        record(
            'destinations',
            r.get_gdf(
                'SELECT dest_name, dest_name_full, geom FROM destinations'
                f" WHERE dest_name IN ({', '.join(repr(n) for n in names)})",
            ),
            dest_names=names,
        )
    for layer in sorted(referenced):
        if layer not in tables:
            continue
        record(layer, r.get_gdf(f'SELECT geom FROM {layer}'))

    columns = [c for c in EDGE_COLUMNS if c in set(table_columns(r, 'edges'))]
    record(
        'network',
        r.get_gdf(
            f'SELECT {", ".join(columns)}, '
            'ROUND(length::numeric)::int AS length_m, geom FROM edges',
        ),
    )
    record(
        'boundary',
        r.get_gdf(
            'SELECT study_region, area_sqkm, pop_est, geom '
            'FROM urban_study_region',
        ),
    )
    buffer_table = r.config.get('buffered_urban_study_region')
    if buffer_table in tables:
        record('buffer', r.get_gdf(f'SELECT geom FROM {buffer_table}'))
    return layers


# ---------------------------------------------------------------------------
# Distributions
#
# The viewer never reads tile attributes to decide a colour scale or draw a
# histogram: both come from these summaries, so a shared classification across
# two panes showing different scales costs one small fetch instead of a scan of
# every rendered feature.

HISTOGRAM_BINS = 12
# a cell/area counts as having access at a band when at least half its sample
# points do -- the same rule the choropleth colours by
BAND_THRESHOLD = 50


def weighted_quantile(values, weights, q):
    # lexsort, not argsort: rows arrive in whatever order the database returned
    # them, and an unstable sort permutes tied values among themselves.  The
    # tied values are identical, but their weights are not, so the cumulative
    # weight at the start of a run of ties -- and hence the interpolation from
    # the value before it -- would otherwise vary between runs.  Sorting on
    # (value, weight) fixes the result to the rows themselves.
    order = np.lexsort((weights, values))
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return None
    return float(np.interp(q * cw[-1], cw, v))


def _number(value):
    if value is None or pd.isna(value):
        return None
    value = float(value)
    if value != value or value in (float('inf'), float('-inf')):
        return None
    return round(value, 4)


def column_ranges(r, exported):
    """The min and max of every exported column, across every scale.

    Histograms are binned on these shared edges rather than on each scale's own
    range, so that two panes showing different scales can be drawn as grouped
    bars: bars that do not share their bins cannot be compared side by side.
    """
    ranges = {}
    for entry, scale in exported:
        columns = entry['columns']
        if not columns:
            continue
        resolved = canonical_columns(r, scale['table'])
        select = ', '.join(
            f'min("{resolved[c][0]}") AS "min_{i}", '
            f'max("{resolved[c][0]}") AS "max_{i}"'
            for i, c in enumerate(columns)
        )
        row = r.get_df(f'SELECT {select} FROM {scale["table"]}').iloc[0]
        for i, column in enumerate(columns):
            low, high = row[f'min_{i}'], row[f'max_{i}']
            if low is None or pd.isna(low):
                continue
            previous = ranges.get(column)
            low, high = float(low), float(high)
            ranges[column] = (
                (low, high)
                if previous is None
                else (min(previous[0], low), max(previous[1], high))
            )
    return ranges


def histogram_edges(span):
    """Bin edges for a column, from its range across every scale."""
    low, high = span
    if high > low:
        return np.linspace(low, high, HISTOGRAM_BINS + 1)
    return np.array([low, low + 1.0])


# ---------------------------------------------------------------------------
# Classification
#
# Where the map's colour classes come from.  This used to live in the viewer,
# which meant the histogram could only be binned on its own uniform edges and
# the swatches beneath it never lined up with the bars.  Here the classes and
# the population share falling in each are computed together, from the same
# data, so the legend *is* the chart's axis.
#
# A column's classes come from, in order of precedence:
#
#   1. the region's ``dashboard.breaks`` entry for that column;
#   2. its declared units, where the data actually occupies them;
#   3. its range, cut into round numbers.

# How much of a declared range the data must occupy for that range to be worth
# classifying over.  NDVI is declared "-1 to 1" and holds 0.03 to 0.35:
# legitimate, but classifying over the declared range puts every area in one
# class and draws the same flat map as an outright wrong unit would.
MIN_OCCUPANCY = 0.25
DEFAULT_LOG2_CLASSES = 7
# Default classes for a whole measure, where its range says less about it than
# its meaning does.  A mean count of reachable establishments runs from 0 to 64
# for produce within a kilometre, so classifying from the range puts nearly
# every area in the bottom class; what a reader wants to know is whether there
# are none, one, a couple, or plenty.  Keyed by measure rather than by units
# because `intersection_count` is also a count and is nothing like this.
MEASURE_BREAKS = {
    # closed at the bottom -- a count of reachable places cannot be negative,
    # and an empty "< 0" class would take a column of the legend to say so
    'count': {
        'edges': [0, 1, 2, 3, 4, 5],
        'open_low': False,
        'open_high': True,
    },
}
# A units string may state its own range -- "index 0-1", "index -1 to 1",
# "class 1-5".  Anything else ("index (sum of z-scores)") states nothing.
_DECLARED_RANGE = re.compile(
    r'(-?\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(-?\d+(?:\.\d+)?)',
)
# round distances to step up through until the data fits
_METRE_LADDERS = [
    [0, 100, 250, 500, 750, 1000],
    [0, 250, 500, 1000, 1500, 2000],
    [0, 500, 1000, 2000, 3000, 5000],
    [0, 1000, 2000, 5000, 10000, 20000],
]


def declared_range(units):
    """The range a units string states, or None if it states none."""
    text = str(units or '').lower()
    if 'percent' in text:
        return (0.0, 100.0)
    match = _DECLARED_RANGE.search(text)
    if not match:
        return None
    low, high = float(match.group(1)), float(match.group(2))
    return (low, high) if high > low else None


def _nice_step(rough):
    """A round step at roughly the requested size: 1, 2, 2.5 or 5 x 10^n."""
    if not rough > 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(rough))
    normalised = rough / magnitude
    for limit, step in ((1, 1), (2, 2), (2.5, 2.5), (5, 5)):
        if normalised <= limit:
            return step * magnitude
    return 10 * magnitude


def nice_breaks(span, n=5):
    """Round edges spanning a range, so the legend reads in whole numbers."""
    low, high = span
    if not high > low:
        return [low, low + 1.0]
    step = _nice_step((high - low) / n)
    start = math.floor(low / step) * step
    edges = []
    while start + step * len(edges) <= high + step * 1e-9:
        edges.append(round(start + step * len(edges), 10))
    edges.append(round(start + step * len(edges), 10))
    return edges


def _equal_interval(span, n=5):
    low, high = span
    if not high > low:
        return [low, low + 1.0]
    step = (high - low) / n
    return [round(low + step * i, 10) for i in range(n + 1)]


def resolve_targets(r, config):
    """Targets a column can be measured against, keyed by column.

    Seeded from the GHSCI reference configuration's own ``thresholds`` block
    (``indicators.yml``), which already records exactly this -- a field, a
    criteria and a relationship -- so the neighbourhood density targets are
    present in every region without configuring anything.  The region's
    ``dashboard.thresholds`` block overrides and extends it, which is how a
    target agreed after the workshop gets added without touching code.
    """
    targets = {}
    try:
        declared = (r.indicators or {}).get('report', {}).get('thresholds', {})
    except AttributeError:
        declared = {}
    for title, spec in (declared or {}).items():
        field = (spec or {}).get('field')
        criteria = (spec or {}).get('criteria')
        if not field or criteria is None:
            continue
        targets[field] = {
            'criteria': float(criteria),
            'relationship': str(spec.get('relationship') or '>='),
            'title': _labels(spec.get('title') or title, field),
        }
    for column, spec in (config.get('thresholds') or {}).items():
        spec = spec if isinstance(spec, dict) else {'criteria': spec}
        criteria = spec.get('criteria')
        if criteria is None:
            targets.pop(column, None)
            continue
        entry = dict(targets.get(column) or {})
        entry['criteria'] = float(criteria)
        entry['relationship'] = str(
            spec.get('relationship') or entry.get('relationship') or '>=',
        )
        if spec.get('title') or not entry.get('title'):
            entry['title'] = _labels(spec.get('title'), column)
        targets[column] = entry
    return targets


def _log2_edges(anchor, span, classes):
    """Edges at ``anchor x 2^k``, covering the data, anchored on the target.

    A doubling ladder is how an unbounded, heavily skewed density reads: drawn
    as equal-width classes it *is* a log axis, without transforming any value.
    The ladder is hung off the target so that the target is always an edge and
    the top class means exactly "meets it".  The lowest class stays open, which
    is what lets a column holding genuine zeros -- both neighbourhood densities
    do -- be shown on a log scale at all.
    """
    if not anchor > 0:
        return None
    low, high = span
    steps = max(2, int(classes) - 1)
    # the highest edge still below the observed maximum, so the top class is
    # populated rather than an empty "beyond everything"
    top = 0
    while anchor * (2 ** (top + 1)) < high:
        top += 1
        if top > 8:
            break
    edges = [anchor * (2 ** (top - i)) for i in range(steps)][::-1]
    # trim edges the data never reaches down to, but keep one below the minimum
    while len(edges) > 2 and edges[1] <= low:
        edges.pop(0)
    # halving a target like 5700 lands on 178.125, and a legend does not want
    # three decimal places of people per square kilometre
    return [round(e) if abs(e) >= 100 else round(e, 2) for e in edges]


def _configured_breaks(spec, span, target):
    """Classes from a ``dashboard.breaks`` entry, or None if it defines none."""
    if isinstance(spec, (list, tuple)):
        # a bare list is interior breaks: the tails are grouped
        return {
            'kind': 'classes',
            'edges': [float(v) for v in spec],
            'open_low': True,
            'open_high': True,
        }
    if not isinstance(spec, dict):
        return None
    if spec.get('categories'):
        return {
            'kind': 'categories',
            'values': [float(v) for v in spec['categories']],
        }
    if str(spec.get('scale') or '').lower() in ('log2', 'log'):
        anchor = spec.get('anchor')
        if anchor is None and target:
            anchor = target.get('criteria')
        edges = _log2_edges(
            float(anchor or 0),
            span,
            spec.get('classes') or DEFAULT_LOG2_CLASSES,
        )
        if not edges:
            return None
        return {
            'kind': 'classes',
            'edges': edges,
            'open_low': True,
            'open_high': True,
            'scale': 'log2',
        }
    if spec.get('edges'):
        closed = bool(spec.get('closed'))
        return {
            'kind': 'classes',
            'edges': [float(v) for v in spec['edges']],
            'open_low': not closed and bool(spec.get('open_low', True)),
            'open_high': not closed and bool(spec.get('open_high', True)),
        }
    return None


def class_breaks(units, span, spec=None, target=None):
    """The colour classes for one column.

    ``span`` is its (min, max) across every exported scale, so one colour means
    one thing on both panes however they differ in scale.
    """
    configured = _configured_breaks(spec, span, target)
    if configured:
        return configured
    text = str(units or '').lower()
    if 'metre' in text:
        high = span[1]
        ladder = next(
            (rungs for rungs in _METRE_LADDERS if high <= rungs[-1]),
            _METRE_LADDERS[-1],
        )
        # closed: the ladder was chosen so the data fits under its top edge,
        # and an open class above it would always be empty
        return {
            'kind': 'classes',
            'edges': [float(v) for v in ladder],
            'open_low': False,
            'open_high': False,
        }
    declared = declared_range(text)
    if declared:
        fits = span[0] >= declared[0] - 1e-9 and span[1] <= declared[1] + 1e-9
        if fits and 'percent' in text:
            # a percentage is always classified 0-100, however narrow the data:
            # it is the one scale every reader already knows, and holding it
            # fixed keeps colours comparable from one indicator to the next
            return {
                'kind': 'classes',
                'edges': [0.0, 20.0, 40.0, 60.0, 80.0, 100.0],
                'open_low': False,
                'open_high': False,
            }
        if fits:
            occupancy = (span[1] - span[0]) / (declared[1] - declared[0])
            if occupancy >= MIN_OCCUPANCY:
                return {
                    'kind': 'classes',
                    'edges': _equal_interval(declared, 5),
                    'open_low': False,
                    'open_high': False,
                }
        elif not fits:
            # the data escapes its declared units: say so, then classify honestly
            print(
                f'    values {span[0]}-{span[1]} fall outside the declared '
                f'units "{units}"; classifying from the data instead',
            )
    # closed for the same reason: nice_breaks() spans the data by construction
    return {
        'kind': 'classes',
        'edges': nice_breaks(span, 5),
        'open_low': False,
        'open_high': False,
    }


def class_count(breaks):
    """How many classes a break definition describes."""
    if not breaks:
        return 0
    if breaks['kind'] == 'categories':
        return len(breaks['values'])
    return (
        len(breaks['edges'])
        - 1
        + int(breaks.get('open_low', False))
        + int(breaks.get('open_high', False))
    )


def class_index(values, breaks):
    """The class each value falls in, as an integer array."""
    if breaks['kind'] == 'categories':
        wanted = np.asarray(breaks['values'], dtype=float)
        idx = np.full(len(values), -1, dtype=int)
        for i, value in enumerate(wanted):
            idx[np.isclose(values, value)] = i
        return idx
    edges = np.asarray(breaks['edges'], dtype=float)
    raw = np.digitize(values, edges, right=False)
    low = bool(breaks.get('open_low', False))
    high = bool(breaks.get('open_high', False))
    if low and high:
        return raw
    if low:
        return np.clip(raw, 0, len(edges) - 1)
    if high:
        return np.clip(raw - 1, 0, len(edges) - 1)
    return np.clip(raw - 1, 0, len(edges) - 2)


def measure_of_column(indicators):
    """``{column: measure key}``, for measure-wide classification defaults."""
    by_column = {}
    for family in indicators['families']:
        for key, measure in family['measures'].items():
            for column in _measure_columns(measure):
                by_column.setdefault(column, key)
    return by_column


def _measure_columns(measure):
    """Every column one measure entry names, however it is nested."""
    found = []

    def walk(node):
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    for key in ('networks', 'groups', 'variables'):
        walk(measure.get(key))
    return found


def all_class_breaks(indicators, ranges, targets, configured):
    """Break definitions for every column that has a range, keyed by column.

    Precedence: the region's own ``dashboard.breaks`` entry, then a default for
    the whole measure, then the column's declared units, then its range.
    """
    configured = configured or {}
    descriptions = indicators['descriptions']
    by_measure = measure_of_column(indicators)
    breaks = {}
    for column, span in ranges.items():
        described = descriptions.get(column) or {}
        spec = configured.get(column)
        if spec is None:
            spec = MEASURE_BREAKS.get(by_measure.get(column))
        breaks[column] = class_breaks(
            described.get('units'),
            span,
            spec,
            targets.get(column),
        )
    return breaks


def column_stats(values, weights, edges=None, breaks=None):
    """Weighted summary and histogram for one column, or None if all missing."""
    v = pd.to_numeric(values, errors='coerce').to_numpy(dtype=float)
    mask = ~np.isnan(v)
    n = int(mask.sum())
    if n == 0:
        return None
    w = weights[mask]
    if w.sum() <= 0:  # unpopulated areas (Condesa): fall back to equal weight
        w = np.ones(n)
    vv = v[mask]
    low, high = float(vv.min()), float(vv.max())
    if edges is None:
        edges = (
            np.linspace(low, high, HISTOGRAM_BINS + 1)
            if high > low
            else np.array([low, low + 1.0])
        )
    idx = np.clip(np.digitize(vv, edges[1:-1]), 0, len(edges) - 2)
    total = w.sum()
    shares = [
        round(float(w[idx == i].sum() / total * 100), 1)
        for i in range(len(edges) - 1)
    ]
    summary = {
        'n': n,
        'n_missing': int(len(v) - n),
        'min': _number(low),
        'max': _number(high),
        'mean': _number(float((w * vv).sum() / total)),
        'p25': _number(weighted_quantile(vv, w, 0.25)),
        'p50': _number(weighted_quantile(vv, w, 0.50)),
        'p75': _number(weighted_quantile(vv, w, 0.75)),
        'bins': [_number(e) for e in edges],
        'shares': shares,
    }
    if breaks:
        # the share of population in each *map class*, exactly.  This is what
        # the dashboard's histogram draws, so that its bars stand over the
        # legend's swatches: a class edge falling inside a uniform bin cannot be
        # recovered from `shares` afterwards.
        classes = class_index(vv, breaks)
        summary['class_shares'] = [
            round(float(w[classes == i].sum() / total * 100), 1)
            for i in range(class_count(breaks))
        ]
        unclassed = float(w[classes < 0].sum() / total * 100)
        if unclassed > 0.05:
            summary['unclassed'] = round(unclassed, 1)
    return summary


def band_distribution(frame, weights, columns):
    """Weighted share of each nested access band, plus a final 'none' class.

    Bands are nested -- access within 500 m implies access within 1000 m -- so
    an area is classed by the smallest band it reaches, and the remainder have
    access at none of them.
    """
    present = [c for c in columns if c in frame.columns]
    if not present:
        return None
    band = np.full(len(frame), len(present))
    for i, column in reversed(list(enumerate(present))):
        values = pd.to_numeric(frame[column], errors='coerce').fillna(-1)
        band[values.to_numpy(dtype=float) >= BAND_THRESHOLD] = i
    w = weights if weights.sum() > 0 else np.ones(len(frame))
    total = w.sum()
    return [
        round(float(w[band == i].sum() / total * 100), 1)
        for i in range(len(present) + 1)
    ]


def _banded_column_sets(indicators):
    """``{'<family>|<network>': [band columns, ascending]}`` for every banded measure."""
    sets = {}
    for family in indicators['families']:
        for key, measure in family['measures'].items():
            if measure.get('kind') != BANDED:
                continue
            for network, bands in (measure.get('networks') or {}).items():
                ordered = [
                    bands[d] for d in sorted(bands, key=lambda x: int(x))
                ]
                sets[f'{family["id"]}|{key}|{network}'] = ordered
    return sets


def scale_stats(
    r,
    entry,
    scale,
    indicators,
    band_sets,
    edges_by_column=None,
    breaks_by_column=None,
):
    """Weighted summaries for every column exported at one scale.

    Read through the same left join the layer was exported with, so the counts
    describe the areas actually on the map: an area that received no source
    units is one without a value, not one that does not exist.
    """
    resolved = canonical_columns(r, scale['table'])
    frame = r.get_df(
        scale_query(scale, resolved, entry['columns'], with_geom=False),
    )
    weights = (
        pd.to_numeric(frame['pop_est'], errors='coerce')
        .fillna(0)
        .to_numpy(
            dtype=float,
        )
        if 'pop_est' in frame.columns
        else np.ones(len(frame))
    )
    columns = {}
    for column in entry['columns']:
        edges = (edges_by_column or {}).get(column)
        stats = column_stats(
            frame[column],
            weights,
            edges,
            (breaks_by_column or {}).get(column),
        )
        if stats:
            columns[column] = stats
    bands = {}
    for key, ordered in band_sets.items():
        distribution = band_distribution(frame, weights, ordered)
        if distribution:
            bands[key] = distribution
    return {
        'weighted_by': 'pop_est' if weights.sum() > 0 else None,
        'areas': int(len(frame)),
        'columns': columns,
        'bands': bands,
    }


# ---------------------------------------------------------------------------
# Manifest


def region_definitions(r, config, scale_entries):
    """The regions of interest a pane can be set to.

    Declared in the ``dashboard.regions`` block, because which custom
    aggregation summarises a region -- and which scales belong to it -- is a
    reporting decision, not something the aggregation config records.  With none
    declared the whole study region is the single region, at every scale.
    """
    available = {e['key'] for e in scale_entries}
    declared = config.get('regions') or {}
    if not declared:
        return {
            'study_region': {
                'label': _labels(config['label'], r.name),
                'summary_scale': None,
                'summary_table': 'indicators_region',
                'scales': [e['key'] for e in scale_entries],
            },
        }
    regions = {}
    for key, spec in declared.items():
        spec = spec or {}
        summary = spec.get('summary_scale')
        regions[key] = {
            'label': _labels(spec.get('label'), key),
            'summary_scale': summary,
            'summary_table': (
                f'indicators_{_sql_key(summary)}'
                if summary
                else 'indicators_region'
            ),
            'scales': [
                s
                for s in (spec.get('scales') or sorted(available))
                if s in available
            ],
        }
    return regions


def region_bounds(r, regions):
    """Each region's bounding box in EPSG:4326, for framing a pane.

    Condesa is a small part of the study area, so a pane showing it should not
    open on the whole of Mexicali.
    """
    tables = set(r.get_tables())
    for region in regions.values():
        scale = region.get('summary_scale')
        table = f'agg_{_sql_key(scale)}' if scale else 'urban_study_region'
        if table not in tables:
            continue
        gdf = r.get_gdf(f'SELECT geom FROM {table}')
        if gdf is None or len(gdf) == 0:
            continue
        region['bbox'] = [
            round(float(v), 5) for v in gdf.to_crs(4326).total_bounds
        ]
    return regions


def region_values(r, regions, columns):
    """The authoritative region-wide value of each indicator, per region.

    Only the region layer tiles the whole study area, so this -- not an average
    over the areas of whatever scale happens to be displayed -- is the figure
    the dashboard reports as the region's own.
    """
    values = {}
    tables = set(r.get_tables())
    for key, region in regions.items():
        table = region['summary_table']
        if table not in tables:
            continue
        resolved = canonical_columns(r, table)
        wanted = [c for c in columns if c in resolved]
        if not wanted:
            continue
        select = ', '.join(
            f'ROUND("{resolved[c][0]}"::numeric, 2)::float8 AS "{c}"'
            for c in wanted
        )
        frame = r.get_df(f'SELECT {select} FROM {table}')
        if len(frame) == 0:
            continue
        row = frame.iloc[0]
        values[key] = {c: _number(row[c]) for c in wanted}
    return values


def data_sources(r):
    """Attribution for the map image export and the info panel."""
    sources = []
    osm = r.config.get('OpenStreetMap') or {}
    if osm:
        sources.append(
            {
                'name': 'OpenStreetMap',
                'source': osm.get('source') or 'OpenStreetMap contributors',
                'publication_date': str(osm.get('publication_date') or ''),
                'url': osm.get('url') or 'https://www.openstreetmap.org',
                'licence': osm.get('licence') or 'ODbL',
            },
        )
    population = r.config.get('population') or {}
    if population:
        sources.append(
            {
                'name': population.get('name') or 'Population',
                'source': population.get('source') or '',
                'publication_date': str(
                    population.get('publication_date') or '',
                ),
                'url': population.get('url') or '',
                'licence': population.get('licence') or '',
                'citation': population.get('citation') or '',
            },
        )
    seen = set()
    for name, spec in (r.config.get('points_of_interest') or {}).items():
        citation = (spec or {}).get('citation') or (spec or {}).get('source')
        if not citation or citation in seen:
            continue
        seen.add(citation)
        sources.append(
            {
                'name': (spec or {}).get('dest_name_full') or name,
                'source': (spec or {}).get('source') or '',
                'publication_date': str(
                    (spec or {}).get('publication_date') or '',
                ),
                'url': (spec or {}).get('url') or '',
                'licence': (spec or {}).get('licence') or '',
                'citation': citation,
            },
        )
    return sources


def copy_data_dictionary(r, outdir):
    """Copy the region's generated data dictionary alongside the layers."""
    region_dir = r.config['region_dir']
    copied = {}
    for extension in ('csv', 'xlsx', 'pdf'):
        source = f'{region_dir}/{r.codename}_data_dictionary.{extension}'
        if os.path.exists(source):
            target = f'data_dictionary.{extension}'
            shutil.copyfile(source, f'{outdir}/{target}')
            copied[extension] = target
    if not copied:
        print(
            '  ! no data dictionary found; run generate() for this region '
            'to produce one',
        )
    return copied


def dictionary_descriptions(outdir, dictionary):
    """Descriptions from the generated data dictionary, keyed by variable.

    Preferred over ``describe_variable`` where present, because it is the text
    the region's own published dictionary uses, and it carries units and the
    statistic alongside.
    """
    if 'csv' not in dictionary:
        return {}
    out = {}
    with open(f'{outdir}/{dictionary["csv"]}', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            variable = (row.get('Variable') or '').strip()
            if not variable:
                continue
            out[variable] = {
                'category': (row.get('Category') or '').strip(),
                'en': (row.get('Indicator') or '').strip(),
                'units': (row.get('Units') or '').strip(),
                'statistic': (row.get('Statistic') or '').strip(),
            }
    return out


def export(r, outdir=None, only_scales=None, layers=True):
    """Export dashboard layers, vocabulary and statistics for a region.

    Takes a loaded Region, or the codename or configuration path of one.
    """
    if type(r) is str:
        r = ghsci.Region(r)
    config = dashboard_config(r)
    slug = config['slug']
    outdir = outdir or f'/tmp/dashboard_export/{slug}'
    os.makedirs(outdir, exist_ok=True)
    print(f'{r.name} ({r.codename}) -> {outdir}', flush=True)

    scales = discover_scales(r, config)
    if only_scales:
        scales = [s for s in scales if s['key'] in only_scales]
    if not scales:
        sys.exit('No aggregation scales found for this region.')
    print(f'  Scales: {", ".join(s["key"] for s in scales)}')

    # the vocabulary is derived once, from the union of every scale's columns,
    # so a permutation missing at one scale is still offered where it exists
    available = set()
    for scale in scales:
        available.update(canonical_columns(r, scale['table']))
    indicators = build_indicators(r, config, available)
    print(
        f'  Vocabulary: {len(indicators["families"])} families over '
        f'{len(indicators["descriptions"])} variables',
    )

    vocabulary_columns = sorted(
        {c for f in indicators['families'] for c in f['columns']},
    )
    # exported scales are kept paired with their definition: a scale that fails
    # to export is dropped from both, so the stats pass below cannot silently
    # pair one scale's columns with another scale's table
    exported = []
    for scale in scales:
        resolved_scale, entry = export_scale(
            r,
            scale,
            vocabulary_columns,
            outdir,
            write=layers,
        )
        if entry:
            exported.append((entry, resolved_scale))
    entries = [entry for entry, _ in exported]

    if layers:
        layer_index = export_context_layers(r, indicators, outdir)
    else:
        # --no-layers regenerates only the JSON, so keep the layer index that
        # the previous full export recorded rather than dropping it
        layer_index = _previous_layers(outdir)
    dictionary = copy_data_dictionary(r, outdir)
    published = dictionary_descriptions(outdir, dictionary)
    for variable, entry in published.items():
        current = indicators['descriptions'].get(variable)
        if not current:
            continue
        # the published text is the region's own wording, so it wins for prose;
        # units and statistic stay as describe_units() resolves them now
        for key, value in entry.items():
            if value and key not in ('units', 'statistic'):
                current[key] = value

    regions = region_bounds(r, region_definitions(r, config, entries))
    boundary = r.get_gdf(
        'SELECT geom FROM urban_study_region',
    ).to_crs(4326)
    manifest = {
        'slug': slug,
        'label': config['label'],
        'title': config['title'],
        'codename': r.codename,
        'name': r.name,
        'year': r.config.get('year'),
        'crs': r.config['crs']['srid'],
        'bbox': [round(float(v), 5) for v in boundary.total_bounds],
        'scales': {e['key']: e for e in entries},
        'layers': layer_index,
        # optional design tokens, applied by the viewer as CSS variables so a
        # region can be restyled without touching the site's code
        'style': config.get('style') or {},
        'regions': regions,
        'region_values': region_values(r, regions, vocabulary_columns),
        'data_dictionary': dictionary,
        'sources': data_sources(r),
    }

    band_sets = _banded_column_sets(indicators)
    ranges = column_ranges(r, exported)
    # one set of bin edges per column, shared by every scale
    edges_by_column = {
        column: histogram_edges(span) for column, span in ranges.items()
    }
    # ...and one set of colour classes, so that a class means the same thing on
    # both panes and the share of population in each can be counted exactly
    targets = resolve_targets(r, config)
    breaks_by_column = all_class_breaks(
        indicators,
        ranges,
        targets,
        config.get('breaks'),
    )
    indicators['breaks'] = breaks_by_column
    indicators['targets'] = {
        column: target
        for column, target in targets.items()
        if column in breaks_by_column
    }
    print(
        f'  Classification: {len(breaks_by_column)} columns, '
        f'{len(indicators["targets"])} with a target',
    )
    stats = {}
    for entry, scale in exported:
        print(f'  distributions: {entry["key"]}', flush=True)
        stats[entry['key']] = scale_stats(
            r,
            entry,
            scale,
            indicators,
            band_sets,
            edges_by_column,
            breaks_by_column,
        )

    for name, payload in (
        ('manifest.json', manifest),
        ('indicators.json', indicators),
        ('stats.json', stats),
    ):
        with open(f'{outdir}/{name}', 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        size = os.path.getsize(f'{outdir}/{name}') / 1024
        print(f'  {name}: {size:,.0f} KB')
    print(f'  bbox {manifest["bbox"]}', flush=True)
    return manifest


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    only = None
    for flag in flags:
        if flag.startswith('--scales='):
            only = [s.strip() for s in flag.split('=', 1)[1].split(',')]
    # --no-layers regenerates the manifest, vocabulary and statistics without
    # rewriting a gigabyte of GeoJSONSeq: revising labels, themes or
    # interventions should not cost a full re-export and re-tile
    export(
        args[0],
        args[1] if len(args) > 1 else None,
        only,
        layers='--no-layers' not in flags,
    )
