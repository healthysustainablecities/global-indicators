"""Data dictionary generation for GHSCI study region outputs.

Generates plain-language descriptions for output variable names across
the scales of calculation (sample point, grid/area, city, custom
aggregation areas, and longitudinal series panels), replacing the
previous fixed ``output_data_dictionary`` asset with documents matching
what has actually been configured and calculated.

Variable names are resolved to descriptions by a rule-based resolver
(:func:`describe_variable`) covering the core walkability and access
indicators, optional Earth Engine urban heat and green space
indicators, cycling accessibility indicators (measures x destinations x
distance thresholds, including activity centres and combined-access
composites), custom aggregation naming conventions, and longitudinal
panel schema fields.  Because resolution is pattern-based, regionally
customised variants (custom destinations, distances, combined-access
sets or activity-centre tiers) resolve without requiring a curated
entry.

Entry points
------------
- ``generate_data_dictionary(r)``: compile and save a dictionary of the
  variables present in a processed region's output tables (used by the
  generate step); writes CSV, XLSX and PDF to the region output folder.
- ``reference_data_dictionary()``: enumerate all potential indicators
  given default settings, for high-level documentation (used to
  regenerate the ``configuration/assets/output_data_dictionary.*``
  reference documents).
- ``save_series_dictionary(series, indicators)``: dictionary for a
  longitudinal series' tidy panel outputs (see ``longitudinal.py``).
"""

import os
import re
import sys
from datetime import datetime

import pandas as pd

DICTIONARY_COLUMNS = ['Category', 'Indicator', 'Variable', 'Scale']

# presentation order of categories in outputs
CATEGORY_ORDER = [
    'Study region information',
    'Derived study region statistics',
    'Linked covariates',
    'Analytical statistics',
    'Naming conventions and parameters',
    'Indicator estimates: access (walking)',
    'Indicator estimates: walkability',
    'Indicator estimates: cycling accessibility',
    'Indicator estimates: urban heat vulnerability',
    'Custom aggregation statistics',
    'Longitudinal series outputs',
    'Other fields',
]

PARAMETERS = 'Naming conventions and parameters'
ACCESS = 'Indicator estimates: access (walking)'
WALKABILITY = 'Indicator estimates: walkability'
CYCLING = 'Indicator estimates: cycling accessibility'
URBAN_HEAT = 'Indicator estimates: urban heat vulnerability'
LONGITUDINAL = 'Longitudinal series outputs'

# Exact variable names: {variable: (category, description)}.  Includes both the
# quoted display-style column names used in the city summary and the
# lower-case names used in the grid and sample point outputs.
BASE_VOCABULARY = {
    'Continent': ('Study region information', 'Continent'),
    'Country': ('Study region information', 'Country'),
    'ISO 3166-1 alpha-2': (
        'Study region information',
        '2-letter country code',
    ),
    'study_region': ('Study region information', 'Study region'),
    'City': ('Study region information', 'Study region'),
    'codename': (
        'Study region information',
        'Study region codename (used for configuration, database and '
        'output files)',
    ),
    'year': (
        'Study region information',
        'Year the study region represents',
    ),
    'Area (sqkm)': (
        'Derived study region statistics',
        'Area (km²; accounting for urban restrictions, if applied)',
    ),
    'area_sqkm': ('Derived study region statistics', 'Area (km²)'),
    'Population estimate': (
        'Derived study region statistics',
        'Population estimate, as per configured population data source',
    ),
    'pop_est': (
        'Derived study region statistics',
        'Population estimate, as per configured population data source',
    ),
    'Population per sqkm': (
        'Derived study region statistics',
        'Population per km²',
    ),
    'pop_per_sqkm': (
        'Derived study region statistics',
        'Population per km²',
    ),
    'Intersections': (
        'Derived study region statistics',
        'Intersection count (following consolidation based on '
        'intersection tolerance parameter in region configuration)',
    ),
    'intersection_count': (
        'Derived study region statistics',
        'Intersection count (following consolidation based on '
        'intersection tolerance parameter in region configuration)',
    ),
    'Intersections per sqkm': (
        'Derived study region statistics',
        'Intersections per km²',
    ),
    'intersections_per_sqkm': (
        'Derived study region statistics',
        'Intersections per km²',
    ),
    'E_EC2E_T15': (
        'Linked covariates',
        'Total emission of CO 2 from the transport sector, using '
        'non-short-cycle-organic fuels in 2015',
    ),
    'E_EC2O_T15': (
        'Linked covariates',
        'Total emission of CO 2 from the energy sector, using '
        'short-cycle-organic fuels in 2015',
    ),
    'E_EPM2_T15': (
        'Linked covariates',
        'Total emission of PM 2.5 from the transport sector in 2015',
    ),
    'E_CPM2_T14': (
        'Linked covariates',
        'Total concentration of PM 2.5 for reference epoch 2014',
    ),
    'EL_AV_ALS': (
        'Linked covariates',
        'The average elevation estimated within the spatial domain of '
        'the Urban Centre, and expressed in metres above sea level '
        '(MASL) (EORC & JAXA, 2017).',
    ),
    'E_KG_NM_LST': (
        'Linked covariates',
        'Semi-colon separated list of names of Köppen-Geiger climate '
        'classes, intersecting with the spatial domain of the Urban '
        'Centre (1986-2010) (Rubel et al., 2017).',
    ),
    'E_WR_T_14': (
        'Linked covariates',
        'Average temperature calculated from annual average estimates '
        'for time interval centred on the year 2015 (the interval spans '
        'from 2012 to 2015) within the spatial domain of the Urban '
        'Centre, and expressed in Celsius degrees (°C) (Harris et al., '
        '2014).',
    ),
    'E_WR_P_14': (
        'Linked covariates',
        'Average precipitations calculated from annual average '
        'estimates for time interval centred on the year 2015 (the '
        'interval spans from 2012 to 2015) within the spatial domain '
        'of the Urban Centre; and expressed in millimetres (mm), the '
        'amount of rain per square meter in one hour) (Harris et al., '
        '2014).',
    ),
    'urban_sample_point_count': (
        'Analytical statistics',
        'Sample points used in this analysis (generated along '
        'pedestrian network for populated grid areas)',
    ),
    'grid_count': (
        'Analytical statistics',
        'Count of population grid cells associated with this area',
    ),
    'grid_id': (
        'Analytical statistics',
        'Population grid cell identifier',
    ),
    'point_id': ('Analytical statistics', 'Sample point identifier'),
    'edge_ogc_fid': (
        'Analytical statistics',
        'Identifier of the network edge the sample point was generated '
        'along',
    ),
    'ogc_fid': ('Analytical statistics', 'Feature identifier'),
    'osm_id': (
        'Analytical statistics',
        'OpenStreetMap feature identifier',
    ),
    'db': (
        'Study region information',
        'Study region database name',
    ),
    # sample point walkability components
    'sp_local_nh_avg_pop_density': (
        WALKABILITY,
        'Average population density of the local walkable '
        'neighbourhood (population per km², based on the population '
        'grid cells intersecting the sample point neighbourhood)',
    ),
    'sp_local_nh_avg_intersection_density': (
        WALKABILITY,
        'Average street intersection density of the local walkable '
        'neighbourhood (intersections per km²)',
    ),
    'sp_daily_living_score': (
        WALKABILITY,
        'Daily living score (/3): sum of access scores for fresh food, '
        'convenience and public transport destinations',
    ),
    'sp_walkability_index': (
        WALKABILITY,
        'Walkability index: sum of z-scores of the daily living score, '
        'neighbourhood population density and neighbourhood '
        'intersection density',
    ),
    # neighbourhood (grid/area) walkability
    'local_nh_population_density': (
        WALKABILITY,
        'Average walkable neighbourhood population density (population '
        'per km²) of sample points in this area',
    ),
    'local_nh_intersection_density': (
        WALKABILITY,
        'Average walkable neighbourhood intersection density '
        '(intersections per km²) of sample points in this area',
    ),
    'local_daily_living': (
        WALKABILITY,
        'Average daily living score (/3) of sample points in this area',
    ),
    'local_walkability': (
        WALKABILITY,
        'Average walkability index of sample points in this area',
    ),
    'all_cities_walkability': (
        WALKABILITY,
        'Walkability index relative to the 25-city GHSCIC reference '
        '(sum of z-scores of daily living score, population density '
        'and intersection density, standardised using reference means '
        'and standard deviations)',
    ),
    # city (population-weighted) walkability
    'pop_nh_pop_density': (
        WALKABILITY,
        'Average walkable neighbourhood population density (population '
        'per km²; population weighted)',
    ),
    'pop_nh_intersection_density': (
        WALKABILITY,
        'Average walkable neighbourhood intersection density '
        '(intersections per km²; population weighted)',
    ),
    'pop_daily_living': (
        WALKABILITY,
        'Average daily living score (/3; population weighted)',
    ),
    'pop_walkability': (
        WALKABILITY,
        'Average walkability index (population weighted)',
    ),
}

# Longitudinal series tidy panel schema: {variable: description}
LONGITUDINAL_SCHEMA = {
    'timepoint': 'Timepoint label of the observation (e.g. year)',
    'indicator': (
        'Output variable name of the indicator observed (see the '
        'indicator entries of this data dictionary)'
    ),
    'value': 'Value of the indicator at this timepoint for this unit',
    'area_id': 'Custom area identifier (area panels)',
    'unit_id': 'Unit identifier (generic panels)',
    't0': 'Baseline timepoint label of the comparison pair',
    't1': 'Follow-up timepoint label of the comparison pair',
    'value_t0': 'Indicator value at the baseline timepoint',
    'value_t1': 'Indicator value at the follow-up timepoint',
    'metric': (
        "Change metric: 'pp_change' (percentage point change; used for "
        "bounded percentage indicators), 'diff' (absolute difference) "
        "or 'pct_change' (relative change, %, masked where the "
        'baseline is zero)'
    ),
    'change': (
        'Change in the indicator between t0 and t1, as per the change '
        'metric'
    ),
    'assessed': (
        'Whether a policy review checklist was configured and scored '
        'for this timepoint'
    ),
    'checklist_version': 'Policy review checklist version',
    'presence_numerator': (
        'Count of policies identified as present in the policy review'
    ),
    'presence_denominator': (
        'Number of policies assessed for presence in the policy review'
    ),
    'presence_pct': 'Policy presence score (%)',
    'quality_numerator': ('Sum of policy quality scores in the policy review'),
    'quality_denominator': (
        'Maximum possible sum of policy quality scores in the policy ' 'review'
    ),
    'quality_pct': 'Policy quality score (%)',
}

# Destination phrases used in access indicator descriptions
DESTINATION_PHRASES = {
    'fresh_food_market': (
        'a fresh food market / supermarket (source: OpenStreetMap or '
        'custom data)'
    ),
    'convenience': (
        'a convenience store (source: OpenStreetMap or custom data)'
    ),
    'pt_osm_any': (
        'any public transport stop (source: OpenStreetMap or custom ' 'data)'
    ),
    'public_open_space_any': ('any public open space (source: OpenStreetMap)'),
    'public_open_space_large': (
        'a public open space larger than 1.5 hectares (source: '
        'OpenStreetMap)'
    ),
    'large_public_green_space': (
        'a large public green space of at least 1 hectare (source: '
        'OpenStreetMap, Google Earth Engine)'
    ),
    'pt_gtfs_any': 'any public transport stop (source: GTFS)',
    'pt_gtfs_freq_30': (
        'a public transport stop with average daytime weekday service '
        'frequency of 30 minutes or better (source: GTFS)'
    ),
    'pt_gtfs_freq_20': (
        'a public transport stop with average daytime weekday service '
        'frequency of 20 minutes or better (source: GTFS)'
    ),
    'pt_any': (
        'any public transport stop (best result of GTFS and '
        'OpenStreetMap/custom sources)'
    ),
    'fresh_food_pooled': (
        'a fresh food market, supermarket or convenience store (pooled '
        'fresh food destinations)'
    ),
    'pt_frequent': (
        'a public transport stop with average daytime weekday service '
        'frequency of 20 minutes or better (source: GTFS)'
    ),
    'all_strict': (
        'all core destination categories at their strict variant (fresh '
        'food market, large public open space, frequent public '
        'transport)'
    ),
    'all_lenient': (
        'all core destination categories at their lenient variant '
        '(pooled fresh food, any public open space, any public '
        'transport)'
    ),
    'activity_centre_local': (
        "a 'local' activity centre: a network location whose walkable "
        'catchment (default 400 m) contains at least one everyday '
        '(lenient) destination of each category (food, public open '
        'space, public transport)'
    ),
    'activity_centre_complete': (
        "a 'complete' activity centre: a network location whose "
        'walkable catchment (default 400 m) contains at least one '
        'high-amenity (strict) destination of each category (food, '
        'public open space, public transport)'
    ),
}

# Cycling accessibility measure phrases, keyed by column infix
MEASURE_PHRASES = {
    'lts1_': (
        'a route composed entirely of lowest-stress links (Level of '
        'Traffic Stress 1, suitable for all ages and abilities)'
    ),
    'safe_': ('a fully low-stress route (Level of Traffic Stress 1–2)'),
    '': (
        'a danger-weighted route over the full cycling network '
        '(higher-stress links usable at a proportionate distance '
        'penalty)'
    ),
}

# Urban heat vulnerability (Earth Engine) indicator phrases, after
# Turner et al. (2025), 'Development and validation of the Global Urban
# Heat Vulnerability Index (GUHVI)', Urban Climate 64: 102716.  Ten
# inputs feed three equally weighted sub-indexes (Heat Exposure, Heat
# Sensitivity and Adaptive Capability), composited into the GUHVI.
URBAN_HEAT_PHRASES = {
    'exposure_index': (
        'Heat Exposure Index (HEI): the heat exposure sub-index, '
        'derived from land surface temperature'
    ),
    'land_surface_temp_c': (
        'Land surface temperature (°C): the temperature of the Earth’s '
        'surface, indicating the lived experience of heat (Landsat 8 '
        'surface reflectance, hottest third of the year)'
    ),
    'sensitivity_index': (
        'Heat Sensitivity Index (HSI): the equally weighted heat '
        'sensitivity sub-index of land surface albedo, NDVI, NDBI, '
        'local climate zone, population density and vulnerable '
        'population'
    ),
    'land_surface_albedo': (
        'Land surface albedo: solar reflectance, where higher '
        'reflectance implies less surface heat retention (inverted, so '
        'that higher values indicate greater heat vulnerability)'
    ),
    'ndvi': (
        'Normalised Difference Vegetation Index (NDVI): a spectral '
        'index of vegetation health and greenness (inverted, so that '
        'higher values indicate greater heat vulnerability)'
    ),
    'ndbi': (
        'Normalised Difference Built-up Index (NDBI): a spectral index '
        'of impervious surfaces such as concrete and asphalt'
    ),
    'local_climate_zone_ordered': (
        'Local Climate Zone: a standardised classification of land '
        'cover typologies for urban heat island studies, ordered from '
        'least heat retaining (water) to most heat retaining (bare '
        'rock or paved)'
    ),
    'population_density_per_sqkm': (
        'Population density (persons per km²), from the GHS-POP global '
        'human settlement population grid'
    ),
    'vulnerable_pop_pct': (
        'Vulnerable population (%): those most at risk from heat on '
        'the basis of age, being the combined proportion of the '
        'population aged 0–4 and 65+ years'
    ),
    'adaptive_capability_index': (
        'Adaptive Capability Index (ACI): the equally weighted '
        'adaptive capability sub-index of child dependency ratio, '
        'subnational Human Development Index and infant mortality '
        'rate; higher values indicate lower adaptive capability'
    ),
    'child_dependency_ratio': (
        'Child dependency ratio: children (aged 0–14 years) relative '
        'to the working age population (15–64 years), indicating '
        'economic reliance'
    ),
    'subnational_hdi': (
        'Subnational Human Development Index: human well-being '
        'assessed through education, health and standard of living'
    ),
    'infant_mortality_rate': (
        'Infant mortality rate: deaths of children under 1 year of age '
        'per 1000 live births, a key indicator of population health'
    ),
    'guhvi': (
        'Global Urban Heat Vulnerability Index (GUHVI): the equally '
        'weighted composite of the Heat Exposure, Heat Sensitivity and '
        'Adaptive Capability indices, (HEI + HSI + ACI) / 3'
    ),
    'guhvi_class': (
        'Global Urban Heat Vulnerability Index (GUHVI) class, from 1 '
        '(least vulnerable) to 5 (most vulnerable)'
    ),
    'guhvi_class_5_most_vulnerable': (
        'Global Urban Heat Vulnerability Index (GUHVI) class 5, the '
        'most vulnerable class'
    ),
}

# GUHVI composite structure: each parent composite index followed by the
# sub-indicators it is derived from, with the overall GUHVI last.
URBAN_HEAT_STRUCTURE = [
    ('exposure_index', ['land_surface_temp_c']),
    (
        'sensitivity_index',
        [
            'land_surface_albedo',
            'ndvi',
            'ndbi',
            'local_climate_zone_ordered',
            'population_density_per_sqkm',
            'vulnerable_pop_pct',
        ],
    ),
    (
        'adaptive_capability_index',
        [
            'child_dependency_ratio',
            'subnational_hdi',
            'infant_mortality_rate',
        ],
    ),
    ('guhvi', ['guhvi_class', 'guhvi_class_5_most_vulnerable']),
]

SKIP_COLUMNS = {'geom', 'geometry', 'index', 'gtfs_20mins_dist_m'}


def destination_phrase(name):
    """Plain-language phrase for a destination name."""
    if name in DESTINATION_PHRASES:
        return DESTINATION_PHRASES[name]
    match = re.fullmatch(r'all_(\w+?)_(strict|lenient)', name)
    if match:
        return (
            f"all destination categories of the '{match.group(1)}' "
            f'combined-access set ({match.group(2)} variants)'
        )
    match = re.fullmatch(r'activity_centre_(\w+?)_(\w+)', name)
    if match:
        return (
            f"an activity centre of the '{match.group(1)}' definition "
            f"('{match.group(2)}' tier): a network location whose "
            'walkable catchment contains at least one destination of '
            'each required category'
        )
    return f"'{name.replace('_', ' ')}' (custom destination)"


def _nearest_phrase(name):
    """Destination phrase with any leading article stripped, for use
    after 'the nearest'."""
    phrase = destination_phrase(name)
    for article in ('a ', 'an ', 'any '):
        if phrase.startswith(article):
            return phrase[len(article) :]
    return phrase


def _describe_cycling(variable):
    """Describe cycling accessibility variables, or return None."""
    match = re.fullmatch(
        r'sp_cycle_(lts1_|safe_)?access_(.+)_(\d+)m',
        variable,
    )
    if match:
        measure = MEASURE_PHRASES[match.group(1) or '']
        return (
            f'Score (0/1): {destination_phrase(match.group(2))} is '
            f'reachable within {match.group(3)} m by cycling, using '
            f'{measure}'
        )
    match = re.fullmatch(
        r'sp_cycle_(lts1_|safe_)?nearest_node_(.+)',
        variable,
    )
    if match:
        measure = MEASURE_PHRASES[match.group(1) or '']
        return (
            f'Distance (m) by cycling to the nearest '
            f'{_nearest_phrase(match.group(2))}, using {measure}'
        )
    match = re.fullmatch(
        r'(pop_)?pct_access_cycle_(lts1_|safe_)?(.+)_(\d+)m',
        variable,
    )
    if match:
        measure = MEASURE_PHRASES[match.group(2) or '']
        description = (
            f'Percentage of population with cycling access within '
            f'{match.group(4)} m to {destination_phrase(match.group(3))}, '
            f'using {measure}'
        )
        if match.group(1):
            description += ' (population weighted)'
        return description
    match = re.fullmatch(
        r'(pop_)?avg_cycle_dist_(lts1_|safe_)?(.+)',
        variable,
    )
    if match:
        measure = MEASURE_PHRASES[match.group(2) or '']
        description = (
            f'Average distance (m) by cycling to the nearest '
            f'{_nearest_phrase(match.group(3))}, using {measure}'
        )
        if match.group(1):
            description += ' (population weighted)'
        return description
    return None


def _describe_urban_heat(variable):
    """Describe urban heat vulnerability variables, or return None.

    The measure itself is described by its phrase (see
    URBAN_HEAT_PHRASES); the scale at which it is summarised is carried
    by the Scale column, and the shared derivation (Earth Engine raster
    analyses on a 1 km grid by default) by the category note.
    """
    match = re.fullmatch(
        r'(pop_)?(pct_)?(sp_)?urban_heat_(.+)',
        variable,
    )
    if not match:
        return None
    pop, pct, sp, key = match.groups()
    phrase = URBAN_HEAT_PHRASES.get(
        key,
        key.replace('_', ' ').capitalize(),
    )
    if key.endswith('_5_most_vulnerable'):
        # the phrase names an index class, so reads as a proper noun
        description = (
            f'Percentage of population in {phrase}'
            if pct
            else f'Score (0/1) for classification in {phrase}'
        )
    elif pct:
        description = (
            f'Percentage of population subject to '
            f'{phrase[0].lower()}{phrase[1:]}'
        )
    else:
        description = phrase
    if pop:
        description += ' (population weighted)'
    return description


def _describe_walking_access(variable):
    """Describe pedestrian access score variables, or return None."""
    match = re.fullmatch(r'sp_nearest_node_(.+)', variable)
    if match:
        return (
            'Distance (m) along the pedestrian network to the nearest '
            f'{_nearest_phrase(match.group(1))}'
        )
    match = re.fullmatch(r'sp_access_(.+?)_score', variable)
    if match:
        return (
            'Score (0-1) for access within the configured walking '
            'accessibility threshold distance (default 500 m) to '
            f'{destination_phrase(match.group(1))}'
        )
    match = re.fullmatch(
        r'(pop_)?(?:pct_)?access_(\d+)m_(.+?)_score',
        variable,
    )
    if match:
        description = (
            f'Percentage of population with access within '
            f'{match.group(2)} m of {destination_phrase(match.group(3))}'
        )
        if match.group(1):
            description += ' (population weighted)'
        return description
    return None


def describe_variable(variable):
    """Resolve a variable name to a (category, description) tuple.

    Resolution is rule-based so regionally customised variants resolve
    without requiring curated entries; unknown variables fall back to a
    humanised version of their name under the 'Other fields' category.
    """
    if variable in BASE_VOCABULARY:
        return BASE_VOCABULARY[variable]
    description = _describe_cycling(variable)
    if description:
        return (CYCLING, description)
    description = _describe_urban_heat(variable)
    if description:
        return (URBAN_HEAT, description)
    description = _describe_walking_access(variable)
    if description:
        return (ACCESS, description)
    if variable in LONGITUDINAL_SCHEMA:
        return (LONGITUDINAL, LONGITUDINAL_SCHEMA[variable])
    # custom aggregation naming conventions, resolved recursively
    if variable.startswith('pop_est_'):
        category, description = describe_variable(
            variable[len('pop_est_') :],
        )
        if category != 'Other fields':
            return (
                category,
                f'{description} (weighted by population estimate)',
            )
    if variable.startswith('avg_'):
        category, description = describe_variable(variable[len('avg_') :])
        if category != 'Other fields':
            return (
                category,
                f'Average across sample points in this area of: '
                f'{description[0].lower()}{description[1:]}',
            )
    return (
        'Other fields',
        variable.replace('_', ' ').strip().capitalize(),
    )


def _merge_scale(scales, addition):
    """Append a scale label to an ordered, comma-separated scale list."""
    labels = [s for s in scales.split(', ') if s] if scales else []
    if addition not in labels:
        labels.append(addition)
    return ', '.join(labels)


def _finalise(rows):
    """Order rows by category and first appearance; return a DataFrame.

    The plain-language description is presented under the 'Indicator'
    heading, ahead of the corresponding 'Variable' name.
    """
    rank = {category: i for i, category in enumerate(CATEGORY_ORDER)}
    ordered = sorted(
        rows,
        key=lambda row: (
            rank.get(row['Category'], len(CATEGORY_ORDER)),
            row['order'],
        ),
    )
    df = pd.DataFrame(ordered).rename(columns={'Description': 'Indicator'})
    return df[DICTIONARY_COLUMNS]


def compile_data_dictionary(r):
    """Compile a data dictionary for a processed region's output layers.

    Introspects the layers exported for the region (city, grid and
    sample point summaries, cycling sample points, and any custom
    aggregation tables) and returns a DataFrame of Category,
    Description, Variable and Scale (the output layers the variable
    appears in).
    """
    tables = r.get_tables()
    scale_tables = [
        (r.config['city_summary'], 'city'),
        (r.config['grid_summary'], 'grid'),
        (r.config['point_summary'], 'sample point'),
        ('sample_points_cycling', 'sample point (cycling)'),
    ]
    for agg in r.config.get('custom_aggregations') or {}:
        scale_tables.append(
            (
                f"indicators_{agg.replace(' ', '_').lower()}",
                f'custom: {agg}',
            ),
        )
    entries = {}
    order = 0
    for table, scale in scale_tables:
        if table not in tables:
            continue
        columns = r.get_df(
            'SELECT column_name FROM information_schema.columns '
            f"WHERE table_name = '{table}' ORDER BY ordinal_position",
        )['column_name'].tolist()
        for column in columns:
            if column in SKIP_COLUMNS or column.startswith('_'):
                continue
            if column not in entries:
                category, description = describe_variable(column)
                entries[column] = {
                    'Category': category,
                    'Description': description,
                    'Variable': column,
                    'Scale': '',
                    'order': order,
                }
                order += 1
            entries[column]['Scale'] = _merge_scale(
                entries[column]['Scale'],
                scale,
            )
    if not entries:
        sys.exit(
            f'\nNo output tables were found for {r.codename}; please '
            'ensure analysis has been completed before generating a '
            'data dictionary.',
        )
    return _finalise(entries.values())


# Reference catalogue parameters: the permutable elements of indicator
# variable names, described once (with their possible values and
# defaults) rather than by exhaustively enumerating every permutation.
# Ordered destination, distance, then network.
_REFERENCE_PARAMETER_INTRO = (
    'Many indicator variable names are assembled from a fixed stem '
    '(identifying the measure) and one or more of the permutable '
    'elements below, shown here as placeholders.  For example, '
    'pop_pct_access_[x]m_[destination]_score and '
    'sp_cycle_[network]access_[destination]_[x]m.  Each placeholder, '
    'its possible values and defaults are described below; regionally '
    'configured values follow the same naming patterns.'
)


def _reference_parameter_sections():
    """Structured definitions of the reference catalogue parameters.

    Each section has a ``placeholder``, a plain-language ``description``
    and, for ``[destination]``, a lookup ``table`` of plain-language
    names to variable stubs plus a customisation ``note``.  Ordered
    destination, distance, then network.
    """
    return [
        {
            'placeholder': '[destination]',
            'description': (
                'The destination whose access is measured.  The default '
                'destinations are listed below.  Walking and cycling '
                'access draw on the same destination definitions; '
                'cycling additionally pairs a strict and a lenient '
                'variant of each core category (food, public open '
                'space, public transport) so that composite '
                '"all categories reachable" indicators can be derived '
                'per variant.'
            ),
            'table_columns': ('Destination', 'Variable stub', 'Category'),
            'table': [
                (
                    'Fresh food market / supermarket',
                    'fresh_food_market',
                    'Food (strict)',
                ),
                (
                    'Fresh food, pooled (market, supermarket or '
                    'convenience store)',
                    'fresh_food_pooled',
                    'Food (lenient)',
                ),
                ('Convenience store', 'convenience', 'Food'),
                (
                    'Large public open space (≥ 1.5 ha)',
                    'public_open_space_large',
                    'Open space (strict)',
                ),
                (
                    'Any public open space',
                    'public_open_space_any',
                    'Open space (lenient)',
                ),
                (
                    'Large public green space (≥ 1 ha; OpenStreetMap '
                    'and Earth Engine)',
                    'large_public_green_space',
                    'Open space',
                ),
                (
                    'Frequent public transport (≤ 20 min daytime '
                    'service; GTFS)',
                    'pt_frequent',
                    'Transport (strict, cycling)',
                ),
                (
                    'Public transport, ≤ 20 min daytime service (GTFS)',
                    'pt_gtfs_freq_20',
                    'Transport (walking)',
                ),
                (
                    'Public transport, ≤ 30 min daytime service (GTFS)',
                    'pt_gtfs_freq_30',
                    'Transport (walking)',
                ),
                (
                    'Any public transport stop (GTFS)',
                    'pt_gtfs_any',
                    'Transport',
                ),
                (
                    'Any public transport stop (OpenStreetMap or custom)',
                    'pt_osm_any',
                    'Transport',
                ),
                (
                    'Any public transport stop (best of GTFS and '
                    'OpenStreetMap/custom)',
                    'pt_any',
                    'Transport (lenient)',
                ),
                (
                    'All categories reachable, strict variants',
                    'all_strict',
                    'Combined',
                ),
                (
                    'All categories reachable, lenient variants',
                    'all_lenient',
                    'Combined',
                ),
                (
                    'Local activity centre (everyday destinations '
                    'co-located)',
                    'activity_centre_local',
                    'Derived',
                ),
                (
                    'Complete activity centre (high-amenity destinations '
                    'co-located)',
                    'activity_centre_complete',
                    'Derived',
                ),
            ],
            'note': (
                'Regions can define their own destinations (custom '
                'OpenStreetMap tags or supplied datasets), pool '
                'categories, and configure additional combined-access '
                'sets and activity-centre definitions (a network '
                'location whose walkable catchment, default 400 m, '
                'contains at least one destination of every required '
                'category).  These follow the same naming patterns, '
                'e.g. all_<set>_<variant> for a named combined-access '
                'set and activity_centre_<definition>_<tier> for a '
                'named activity centre.  Combined-access composites '
                'have access indicators only (no nearest-distance '
                'variables).'
            ),
        },
        {
            'placeholder': '[x]',
            'description': (
                'Distance threshold (m).  Distances can be customised '
                'to locally policy-relevant values.  Walking access '
                'uses the configured neighbourhood accessibility '
                'threshold (default 500 m); cycling access is evaluated '
                'at each configured cycling distance (defaults: 500 m, '
                '1000 m, 2000 m and 5000 m), so a cycling access '
                'variable exists for each distance.'
            ),
        },
        {
            'placeholder': '[network]',
            'description': (
                'Cycling route stress measure, appearing as an optional '
                'prefix on cycling variable names: "lts1_" for routes '
                'composed entirely of lowest-stress Level of Traffic '
                'Stress (LTS) 1 links (suitable for all ages and '
                'abilities); "safe_" for fully low-stress routes on LTS '
                '1–2 links (the default headline measure); or no prefix '
                'for danger-weighted routing over the full cycling '
                'network (higher-stress links usable at a proportionate '
                'distance penalty).  Which measures are computed is '
                'configurable (cycling_indicators contrasts and '
                'measures settings).'
            ),
        },
    ]


# Reference catalogue indicator patterns: (variable pattern, plain
# language description, scale), grouped by category.
REFERENCE_PATTERNS = {
    ACCESS: [
        (
            'sp_access_[destination]_score',
            'Score (0-1) for walking access within the configured '
            'accessibility threshold distance (default 500 m) to the '
            'destination',
            'sample point',
        ),
        (
            'sp_nearest_node_[destination]',
            'Distance (m) along the pedestrian network to the nearest '
            'destination',
            'sample point',
        ),
        (
            'pct_access_[x]m_[destination]_score',
            'Percentage of population with walking access within [x] m '
            'of the destination',
            'grid, custom areas',
        ),
        (
            'pop_pct_access_[x]m_[destination]_score',
            'Percentage of population with walking access within [x] m '
            'of the destination (population weighted)',
            'city, custom areas',
        ),
    ],
    CYCLING: [
        (
            'sp_cycle_[network]access_[destination]_[x]m',
            'Score (0/1): the destination is reachable within [x] m by '
            'cycling, routed using the [network] measure',
            'sample point',
        ),
        (
            'sp_cycle_[network]nearest_node_[destination]',
            'Distance (m) by cycling to the nearest destination, routed '
            'using the [network] measure',
            'sample point',
        ),
        (
            'pct_access_cycle_[network][destination]_[x]m',
            'Percentage of population with cycling access within [x] m '
            'to the destination, routed using the [network] measure',
            'grid, custom areas',
        ),
        (
            'pop_pct_access_cycle_[network][destination]_[x]m',
            'Percentage of population with cycling access within [x] m '
            'to the destination, routed using the [network] measure '
            '(population weighted)',
            'city, custom areas',
        ),
        (
            'avg_cycle_dist_[network][destination]',
            'Average distance (m) by cycling to the nearest '
            'destination, routed using the [network] measure',
            'grid, custom areas',
        ),
        (
            'pop_avg_cycle_dist_[network][destination]',
            'Average distance (m) by cycling to the nearest '
            'destination, routed using the [network] measure '
            '(population weighted)',
            'city, custom areas',
        ),
    ],
}

# Italic notes rendered beneath a category heading in the PDF.
CATEGORY_NOTES = {
    URBAN_HEAT: (
        'Derived from Earth Engine raster analyses on a 1 km grid by '
        'default, following Turner et al. (2025), "Development and '
        'validation of the Global Urban Heat Vulnerability Index '
        '(GUHVI)", Urban Climate 64: 102716.  Inputs are aligned so '
        'that higher values indicate greater heat vulnerability.  Each '
        'measure below is sampled at sample points (sp_ prefix), '
        'averaged for each grid cell or custom area (no prefix), and '
        'population weighted for the city and custom areas (pop_ '
        'prefix).  Sub-indicators are listed beneath the composite '
        'index they contribute to.'
    ),
    LONGITUDINAL: 'Work in progress (July 2026)',
}

# Categories presented as sub-headings beneath a shared top-level
# 'Indicator estimates' heading in the PDF.
INDICATOR_PREFIX = 'Indicator estimates: '

# concrete walkability variables and the scales they are derived at
REFERENCE_WALKABILITY = [
    ('sp_local_nh_avg_pop_density', 'sample point'),
    ('sp_local_nh_avg_intersection_density', 'sample point'),
    ('sp_daily_living_score', 'sample point'),
    ('sp_walkability_index', 'sample point'),
    ('local_nh_population_density', 'grid, city, custom areas'),
    ('local_nh_intersection_density', 'grid, city, custom areas'),
    ('local_daily_living', 'grid, city, custom areas'),
    ('local_walkability', 'grid, city, custom areas'),
    ('pop_nh_pop_density', 'city, custom areas'),
    ('pop_nh_intersection_density', 'city, custom areas'),
    ('pop_daily_living', 'city, custom areas'),
    ('pop_walkability', 'city, custom areas'),
]


def reference_data_dictionary():
    """Compile a concise reference catalogue of potential indicators.

    Rather than exhaustively enumerating every permutation of the
    indicator variables (destinations x distances x network measures x
    scales), permutable elements are represented once as parameter
    placeholders ([x], [network], [destination]) with descriptions of
    the possible values and defaults, keeping the catalogue readable.
    Regional customisation yields analogous variables following the
    same naming patterns; the data dictionary generated alongside each
    processed study region enumerates the variables actually
    calculated.
    """
    rows = []
    order = 0

    def add(category, description, variable, scale):
        nonlocal order
        rows.append(
            {
                'Category': category,
                'Description': description,
                'Variable': variable,
                'Scale': scale,
                'order': order,
            },
        )
        order += 1

    def add_concrete(variable, scale):
        category, description = describe_variable(variable)
        add(category, description, variable, scale)

    for variable, scale in [
        ('Continent', 'city'),
        ('Country', 'city'),
        ('ISO 3166-1 alpha-2', 'city'),
        ('study_region', 'city, grid'),
        ('Area (sqkm)', 'city'),
        ('Population estimate', 'city'),
        ('Population per sqkm', 'city'),
        ('Intersections', 'city'),
        ('Intersections per sqkm', 'city'),
        ('area_sqkm', 'grid, custom areas'),
        ('pop_est', 'grid, custom areas'),
        ('pop_per_sqkm', 'grid, custom areas'),
        ('intersection_count', 'grid, custom areas'),
        ('intersections_per_sqkm', 'grid, custom areas'),
        ('urban_sample_point_count', 'city, grid'),
        ('grid_id', 'grid, sample point'),
        ('point_id', 'sample point'),
        ('grid_count', 'custom areas'),
    ]:
        add_concrete(variable, scale)
    # parameters: placeholder + description, then (for [destination]) the
    # lookup table rows and a customisation note, flattened for the
    # tabular formats; the PDF renders these from the structured sections
    for section in _reference_parameter_sections():
        add(PARAMETERS, section['description'], section['placeholder'], '')
        for name, stub, category in section.get('table', []):
            add(PARAMETERS, name, stub, category)
        if section.get('note'):
            add(PARAMETERS, section['note'], '', '')
    for category, patterns in REFERENCE_PATTERNS.items():
        for variable, description, scale in patterns:
            add(category, description, variable, scale)
    for variable, scale in REFERENCE_WALKABILITY:
        add_concrete(variable, scale)
    # urban heat vulnerability: each composite sub-index followed by the
    # sub-indicators it is derived from, with the overall GUHVI last
    for parent, sub_indicators in URBAN_HEAT_STRUCTURE:
        for key in [parent] + sub_indicators:
            if key == 'guhvi_class_5_most_vulnerable':
                add_concrete(
                    'pct_urban_heat_guhvi_class_5_most_vulnerable',
                    'grid, city, custom areas',
                )
            else:
                add_concrete(
                    f'urban_heat_{key}',
                    'sample point, grid, city, custom areas',
                )
    for variable, description in LONGITUDINAL_SCHEMA.items():
        add(LONGITUDINAL, description, variable, 'longitudinal series')
    return _finalise(rows)


def generate_reference_data_dictionary(stem=None):
    """Generate the reference catalogue assets (all potential indicators).

    Writes ``configuration/assets/output_data_dictionary.csv/.xlsx/.pdf``
    by default.  Run this (in the container) whenever indicator naming
    conventions change.  Returns the saved paths keyed by format.
    """
    if stem is None:
        configuration = (
            f'{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}'
            '/configuration'
        )
        stem = f'{configuration}/assets/output_data_dictionary'
    return save_data_dictionary(
        reference_data_dictionary(),
        stem,
        title='GHSCI output data dictionary',
        subtitle='All potential indicators and output variables',
        notes=(
            'This reference describes the output variables that can be '
            'produced through the combined GHSCI workflow, including '
            'optional GTFS public transport, Earth Engine (large public '
            'green space and urban heat vulnerability), cycling '
            'accessibility and longitudinal series analyses, across the '
            'scales of calculation (sample point, grid, city, custom '
            'aggregation areas, and longitudinal series panels).  '
            'Permutable elements of variable names are represented by '
            'parameter placeholders — [destination], [x] (distance '
            'threshold) and [network] (cycling route stress measure) — '
            'described under Naming conventions and parameters, rather '
            'than exhaustively listing every permutation.  Regional '
            'customisation (e.g. custom destinations, distance '
            'thresholds or aggregation areas) yields analogous '
            'variables following the same naming patterns; the data '
            'dictionary generated alongside each processed study region '
            'enumerates the variables actually calculated for that '
            'region.'
        ),
        parameter_sections=_reference_parameter_sections(),
    )


def _paragraph(pdf, text):
    """Write a full-width paragraph, returning to the left margin."""
    pdf.multi_cell(0, text=text, new_x='LMARGIN', new_y='NEXT')


def _ensure_space(pdf, needed=45):
    """Start a new page unless ``needed`` mm remains on the current one.

    Prevents a heading being stranded at the foot of a page, separated
    from the content it introduces.
    """
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()


def _heading(pdf, text, level=1, note=None):
    """Write a section heading, optionally followed by an italic note."""
    _ensure_space(pdf, 45 if level == 1 else 35)
    pdf.set_font('dejavu', 'b', 12 if level == 1 else 10)
    pdf.set_text_color(89, 39, 226)
    _paragraph(pdf, text)
    pdf.set_text_color(0, 0, 0)
    if note:
        pdf.set_font('dejavu', 'i', 8)
        _paragraph(pdf, note)
    pdf.ln(1)


def _render_parameter_sections(pdf, sections):
    """Render the reference catalogue parameters section.

    Each parameter is presented as its placeholder followed by a
    full-width description; ``[destination]`` additionally gets a lookup
    table of plain-language names to variable stubs and a note on
    customisation.  This purpose-built layout replaces the generic
    Indicator/Variable/Scale table, which wastes horizontal space on
    long parameter descriptions.
    """
    pdf.set_font('dejavu', '', 9)
    _paragraph(pdf, _REFERENCE_PARAMETER_INTRO)
    pdf.ln(2)
    for section in sections:
        pdf.set_font('dejavu', 'b', 11)
        _paragraph(pdf, section['placeholder'])
        pdf.set_font('dejavu', '', 9)
        _paragraph(pdf, section['description'])
        if section.get('table'):
            pdf.ln(1)
            pdf.set_font('dejavu', '', 8)
            with pdf.table(
                col_widths=(94, 44, 34),
                borders_layout='HORIZONTAL_LINES',
                line_height=4,
                text_align=('LEFT', 'LEFT', 'LEFT'),
                padding=1,
            ) as table:
                header = table.row()
                for heading in section['table_columns']:
                    header.cell(heading)
                for name, stub, category in section['table']:
                    row = table.row()
                    row.cell(str(name))
                    # zero-width spaces let long stubs wrap
                    row.cell(str(stub).replace('_', '_' + chr(0x200B)))
                    row.cell(str(category))
        if section.get('note'):
            pdf.ln(1)
            pdf.set_font('dejavu', 'i', 8)
            _paragraph(pdf, section['note'])
        pdf.set_font('dejavu', '', 9)
        pdf.ln(3)


def _dictionary_pdf(
    df,
    path,
    title,
    subtitle=None,
    notes=None,
    parameter_sections=None,
):
    """Render a data dictionary DataFrame as a PDF document.

    When ``parameter_sections`` is supplied, the 'Naming conventions and
    parameters' category is rendered from those structured sections
    rather than as a generic table.
    """
    from fpdf import FPDF

    configuration = (
        f'{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}'
        '/configuration'
    )
    fonts = f'{configuration}/fonts/dejavu-fonts-ttf-2.37/ttf'
    pdf = FPDF(orientation='portrait', format='A4', unit='mm')
    pdf.set_margins(19, 20, 19)
    pdf.set_auto_page_break(True, margin=20)
    for style, file in (
        ('', 'DejaVuSansCondensed.ttf'),
        ('b', 'DejaVuSansCondensed-Bold.ttf'),
        ('i', 'DejaVuSansCondensed-Oblique.ttf'),
    ):
        pdf.add_font('dejavu', style=style, fname=f'{fonts}/{file}')
    pdf.add_page()
    logo = f'{configuration}/assets/GOHSC - white logo transparent.svg'
    if os.path.exists(logo):
        pdf.image(logo, 19, 19, 42)
        pdf.ln(12)
    pdf.set_font('dejavu', 'b', 18)
    pdf.set_text_color(89, 39, 226)
    _paragraph(pdf, title)
    pdf.set_text_color(0, 0, 0)
    if subtitle:
        pdf.set_font('dejavu', 'b', 12)
        _paragraph(pdf, subtitle)
    pdf.set_font('dejavu', '', 9)
    pdf.ln(2)
    _paragraph(
        pdf,
        f'Generated {datetime.now().strftime("%d %B %Y")} using the '
        'Global Healthy and Sustainable City Indicators (GHSCI) tool '
        '(https://healthysustainablecities.github.io/).',
    )
    if notes:
        pdf.ln(2)
        _paragraph(pdf, notes)
    pdf.ln(4)
    indicator_heading_rendered = False
    for category in df['Category'].unique():
        group = df.loc[df['Category'] == category]
        if category.startswith(INDICATOR_PREFIX):
            # the indicator estimate categories share a top-level
            # 'Indicator estimates' heading, starting a new page, and
            # are presented beneath it as sub-headings
            if not indicator_heading_rendered:
                pdf.add_page()
                _heading(pdf, INDICATOR_PREFIX.rstrip(': '), level=1)
                indicator_heading_rendered = True
            subheading = category[len(INDICATOR_PREFIX) :]
            _heading(
                pdf,
                subheading[0].upper() + subheading[1:],
                level=2,
                note=CATEGORY_NOTES.get(category),
            )
        else:
            _heading(
                pdf,
                category,
                level=1,
                note=CATEGORY_NOTES.get(category),
            )
        if category == PARAMETERS and parameter_sections:
            _render_parameter_sections(pdf, parameter_sections)
            continue
        pdf.set_font('dejavu', '', 8)
        with pdf.table(
            col_widths=(87, 60, 25),
            borders_layout='HORIZONTAL_LINES',
            line_height=4,
            text_align=('LEFT', 'LEFT', 'LEFT'),
            padding=1,
        ) as table:
            header = table.row()
            for heading in ('Indicator', 'Variable', 'Scale'):
                header.cell(heading)
            for _, entry in group.iterrows():
                row = table.row()
                row.cell(str(entry['Indicator']))
                # zero-width spaces allow long variable names to wrap
                row.cell(
                    str(entry['Variable']).replace('_', '_' + chr(0x200B)),
                )
                row.cell(str(entry['Scale']).replace('_', '_' + chr(0x200B)))
        pdf.ln(4)
    pdf.output(path)
    return path


def save_data_dictionary(
    df,
    stem,
    title,
    subtitle=None,
    notes=None,
    formats=('csv', 'xlsx', 'pdf'),
    parameter_sections=None,
):
    """Save a data dictionary DataFrame as CSV, XLSX and/or PDF.

    ``stem`` is the output path without extension; returns a dictionary
    of the saved paths, keyed by format.  ``parameter_sections`` (used
    by the reference catalogue) drives special rendering of the naming
    conventions and parameters section in the PDF.
    """
    paths = {}
    if 'csv' in formats:
        paths['csv'] = f'{stem}.csv'
        df.to_csv(paths['csv'], index=False)
    if 'xlsx' in formats:
        paths['xlsx'] = f'{stem}.xlsx'
        with pd.ExcelWriter(paths['xlsx'], engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='data dictionary')
            worksheet = writer.sheets['data dictionary']
            for width, column in zip((32, 92, 52, 28), 'ABCD'):
                worksheet.column_dimensions[column].width = width
            worksheet.freeze_panes = 'A2'
    if 'pdf' in formats:
        paths['pdf'] = f'{stem}.pdf'
        _dictionary_pdf(
            df,
            paths['pdf'],
            title,
            subtitle=subtitle,
            notes=notes,
            parameter_sections=parameter_sections,
        )
    return paths


def generate_data_dictionary(r, formats=('csv', 'xlsx', 'pdf')):
    """Generate data dictionary files for a processed region.

    Compiles a dictionary matching the region's configured and
    calculated output layers and writes it to the region output folder
    as CSV, XLSX and PDF.  Returns the saved paths keyed by format.
    """
    df = compile_data_dictionary(r)
    return save_data_dictionary(
        df,
        f"{r.config['region_dir']}/{r.codename}_data_dictionary",
        title='Data dictionary',
        subtitle=f"{r.config['name']} ({r.codename})",
        notes=(
            'This data dictionary describes the variables included in '
            'the output data layers generated for this study region, '
            'across the scales of calculation (sample point, grid, '
            'city, and any custom aggregation areas), as a guide to '
            'interpretation and re-use of the data.'
        ),
        formats=formats,
    )


def save_series_dictionary(series, indicators):
    """Save a data dictionary for a longitudinal series' panel outputs.

    Describes the tidy panel schema fields alongside the indicators
    observed across the series' timepoints.  Returns the saved paths
    keyed by format.
    """
    rows = []
    order = 0
    for variable, description in LONGITUDINAL_SCHEMA.items():
        rows.append(
            {
                'Category': LONGITUDINAL,
                'Description': description,
                'Variable': variable,
                'Scale': 'longitudinal series',
                'order': order,
            },
        )
        order += 1
    for variable in indicators:
        category, description = describe_variable(str(variable))
        rows.append(
            {
                'Category': category,
                'Description': description,
                'Variable': variable,
                'Scale': 'longitudinal series',
                'order': order,
            },
        )
        order += 1
    return save_data_dictionary(
        _finalise(rows),
        f'{series.output_dir}/{series.codename}_data_dictionary',
        title='Data dictionary (longitudinal series)',
        subtitle=series.codename,
        notes=(
            'This data dictionary describes the fields of the tidy '
            'longitudinal panel outputs for this series, along with '
            'plain language descriptions of the indicators observed '
            'across its timepoints.'
        ),
    )
