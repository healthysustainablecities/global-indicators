"""
Longitudinal report generation for a series of study region timepoints.

Generates PDF reports from the longitudinal report templates
(spatial_longitudinal, policy_longitudinal, policy_spatial_longitudinal
worksheets of configuration/_report_configuration.xlsx) for a
longitudinal Series (see subprocesses/longitudinal.py).

This pipeline is deliberately separate from the single-region report
generation in _utils.generate_report_for_language: longitudinal
templates are dispatched by exact name using LONGITUDINAL_TEMPLATE_PAGES
(no template-name substring tests), while reusing the proven low-level
machinery (pdf_template_setup, FlexTemplate page rendering, fonts,
citation/cover/context page inserters) unchanged.
"""

import os
import re

import numpy as np
import pandas as pd

# Exact-name mapping of logical report sections to the physical page
# numbers of each template worksheet.  This is the single source of
# truth for longitudinal template pagination.
LONGITUDINAL_TEMPLATE_PAGES = {
    'spatial_longitudinal': {
        'cover': 1,
        'citation': 2,
        'introduction': 3,
        'context': 4,
        'access_profile': 5,
        'pt': 6,
        'pos': 7,
        'walk': 8,
        'distribution': 9,
        'equity': 10,
        'back': 11,
    },
    'policy_longitudinal': {
        'cover': 1,
        'citation': 2,
        'introduction': 3,
        'policy_trend': 4,
        'policy_comparison': 5,
        'back': 6,
    },
    'policy_spatial_longitudinal': {
        'cover': 1,
        'citation': 2,
        'introduction': 3,
        'context': 4,
        'policy_trend': 5,
        'policy_comparison': 6,
        'access_profile': 7,
        'pt': 8,
        'pos': 9,
        'walk': 10,
        'distribution': 11,
        'equity': 12,
        'back': 13,
    },
}

# Physical sizes (mm, width by height) of the template image elements that
# the longitudinal figures fill.  Figures are generated at these sizes, so
# that they are not distorted and their text renders at the intended size;
# the template boxes must match (see test_10_6).
FIGURE_SIZES_MM = {
    'small_multiples': (182, 70),
    'change_map': (140, 127),
    'quantile_bands': (182, 100),
    'threshold_trends': (150, 100),
    'equity_stratified': (160, 88),
    'equity_dumbbell': (160, 100),
}
# font size (points, before scaling to the page) for chart text
FIGURE_FONT_SIZE = 13

# phrase keys introduced for longitudinal reporting; these are filled
# from the English column when untranslated so reports remain
# generatable in all languages (with a printed warning)
LONGITUDINAL_PHRASES = [
    'spatial indicators over time',
    'policy indicators over time',
    'policy and spatial indicators over time',
    'spatial_longitudinal_intro',
    'policy_longitudinal_intro',
    'policy_spatial_longitudinal_intro',
    'longitudinal_series_text',
    'access_profile_longitudinal_text',
    'pt_longitudinal_description',
    'pos_longitudinal_description',
    'walk_header',
    'walk_longitudinal_description',
    'walk_change_map_caption',
    'walkability_above_reference_label',
    'threshold_trends_ylabel',
    'pt_longitudinal_summary',
    'pos_longitudinal_summary',
    'walk_longitudinal_summary',
    'distribution_summary',
    'equity_summary',
    'access_profile_grouped_summary',
    'trend_rose',
    'trend_fell',
    'trend_unchanged',
    'gradient_unchanged',
    'distribution_header',
    'distribution_description',
    'equity_header',
    'equity_description',
    'policy_coverage_text',
    'Not assessed at this timepoint',
    'policy_comparison_header',
    'policy_comparison_text',
    'change_map_caption',
]


def _ghsci():
    """Return the ghsci module, however it has been imported."""
    try:
        import subprocesses.ghsci as ghsci
    except ImportError:
        import ghsci
    return ghsci


def _utils():
    """Return the _utils module, however it has been imported."""
    try:
        import subprocesses._utils as utils
    except ImportError:
        import _utils as utils
    return utils


def _longitudinal():
    """Return the longitudinal module, however it has been imported."""
    try:
        import subprocesses.longitudinal as longitudinal
    except ImportError:
        import longitudinal
    return longitudinal


def _plots():
    """Return the longitudinal_plots module."""
    try:
        import subprocesses.longitudinal_plots as plots
    except ImportError:
        import longitudinal_plots as plots
    return plots


def _policy_report():
    """Return the policy_report module, however it has been imported."""
    try:
        import subprocesses.policy_report as policy_report
    except ImportError:
        import policy_report
    return policy_report


def get_series_phrases(series, language, reporting_template):
    """
    Prepare the report phrase dictionary for a series.

    Uses the latest timepoint's region phrases as the base (fonts,
    locale, citations, template phrases), then overlays series-level
    language settings (name, country, longitudinal summaries), the
    series year range and timepoint labels.  Longitudinal phrase keys
    lacking a translation fall back to English with a printed note, so
    reports remain generatable in all validated languages.
    """
    latest = series.timepoints[-1].region
    phrases = latest.get_phrases(
        language,
        reporting_template=reporting_template,
    )
    if phrases is None:
        return None
    # series-level language overlays
    series_languages = (series.config.get('reporting') or {}).get(
        'languages',
    ) or {}
    block = series_languages.get(language) or {}
    if block.get('name'):
        phrases['city_name'] = block['name']
    if block.get('country'):
        phrases['country'] = block['country']
    summary_key = f'summary_{reporting_template}'
    phrases[summary_key] = block.get(summary_key, '') or ''
    # series year range and timepoint labels
    years = [tp.year for tp in series.timepoints if tp.year is not None]
    if years:
        phrases['year'] = f'{min(years)}–{max(years)}'
    phrases['timepoint_labels'] = ', '.join(series.labels)
    policy_labels = [tp.label for tp in series.timepoints if tp.has_policy]
    phrases['policy_timepoints'] = ', '.join(policy_labels)
    # English fallback for untranslated longitudinal phrases
    if language != 'English':
        languages = pd.read_excel(
            latest.config['reporting']['configuration'],
            sheet_name='languages',
        ).fillna('')
        english = languages.set_index('name')['English']
        untranslated = []
        for key in LONGITUDINAL_PHRASES:
            if (
                str(phrases.get(key, '')).strip() == ''
                and key in english.index
                and str(english[key]).strip() != ''
            ):
                phrases[key] = english[key]
                untranslated.append(key)
        if untranslated:
            print(
                f'  Note: the following phrases are not yet translated '
                f'for {language} and are shown in English: '
                f'{untranslated}',
            )
        ghsci = _ghsci()
        title_key = ghsci.reports.get(reporting_template)
        if title_key and str(phrases.get(title_key, '')).strip() == '':
            phrases[title_key] = english.get(title_key, title_key)
        phrases['title_series_line2'] = phrases[title_key]
    return phrases


def build_policy_comparison(series, phrases: dict = None) -> pd.DataFrame:
    """
    Assemble the policy checklist comparison across timepoints.

    Returns a DataFrame indexed by (topic, measure) with one column per
    reviewed timepoint holding policy identification marks.  Checklist
    parsing normalises measures to the current policy taxonomy (legacy
    checklist versions are mapped by policy_report); measures present
    at only one timepoint appear with missing values elsewhere rather
    than being dropped.  Labels are translated using phrases when
    supplied.
    """
    policy_report = _policy_report()
    frames = {}
    for tp in series.timepoints:
        if not tp.has_policy:
            continue
        review = policy_report.policy_data_setup(
            tp.region.config['policy_review'],
        )
        if review is None:
            continue
        marks = {}
        for topic, checklist in review.items():
            for measure in checklist.index:
                marks[(str(topic), str(measure))] = checklist.loc[
                    measure,
                    'identified',
                ]
        frames[tp.label] = pd.Series(marks)
    if not frames:
        return pd.DataFrame()
    comparison = pd.DataFrame(frames)
    comparison.index = pd.MultiIndex.from_tuples(comparison.index)
    if phrases:
        comparison.index = pd.MultiIndex.from_tuples(
            [
                (
                    str(phrases.get(topic, topic)),
                    str(phrases.get(measure, measure)),
                )
                for topic, measure in comparison.index
            ],
        )
    return comparison


def _select_report_indicators(series) -> dict:
    """
    Select the public transport, open space and walkability indicators to map.

    Walkability (the derived all_cities_walkability, comparable over time)
    is mapped where its components are available at every timepoint.
    """
    candidates = {
        'pt': [
            'pct_access_500m_pt_gtfs_freq_20_score',
            'pct_access_500m_pt_any_score',
        ],
        'pos': [
            'pct_access_500m_public_open_space_large_score',
            'pct_access_500m_public_open_space_any_score',
        ],
    }
    selected = {}
    available = {}
    for tp in series.timepoints:
        table = tp.region.config['grid_summary']
        available[tp.label] = set(series._get_columns(tp.region, table))
    for prefix, options in candidates.items():
        for option in options:
            if all(option in cols for cols in available.values()):
                selected[prefix] = option
                break
        else:
            selected[prefix] = options[-1]
    derived = series._derived_indicators()
    walkability = derived.get('all_cities_walkability')
    if walkability and all(
        set(walkability['components']) <= cols for cols in available.values()
    ):
        selected['walk'] = 'all_cities_walkability'
    return selected


def generate_longitudinal_resources(
    series,
    phrases,
    language: str = 'English',
    cmap=None,
) -> dict:
    """
    Generate the figures required by the longitudinal report templates.

    Figures are saved under {series.output_dir}/figures with sizes
    matched to the template element boxes.  Returns a dictionary of
    figure paths and selections used by the PDF inserters.
    """
    longitudinal = _longitudinal()
    plots = _plots()
    mm = plots._mm_scale
    figure_dir = f'{series._ensure_output_dir()}/figures'
    os.makedirs(figure_dir, exist_ok=True)
    resources = {'indicators': _select_report_indicators(series)}
    indicators = list(resources['indicators'].values())
    panel = series.get_grid_panel(indicators=indicators)
    for prefix, indicator in resources['indicators'].items():
        resources[f'{prefix}_small_multiples'] = plots.small_multiple_maps(
            series,
            indicator,
            panel=panel,
            cmap=cmap,
            phrases=phrases,
            locale=phrases['locale'],
            width=mm(FIGURE_SIZES_MM['small_multiples'][0]),
            height=mm(FIGURE_SIZES_MM['small_multiples'][1]),
            path=f'{figure_dir}/{prefix}_small_multiples_{language}.png',
        )
        resources[f'{prefix}_change_map'] = plots.change_map(
            series,
            indicator,
            panel=panel,
            phrases=phrases,
            locale=phrases['locale'],
            width=mm(FIGURE_SIZES_MM['change_map'][0]),
            height=mm(FIGURE_SIZES_MM['change_map'][1]),
            path=f'{figure_dir}/{prefix}_change_map_{language}.png',
        )
    # distributional figures: population-weighted box plots, and the
    # population share with access (or above the walkability reference)
    # over time, for public transport, open space, food and walkability
    distribution_indicators = [
        indicator
        for indicator in [
            resources['indicators'].get('pt'),
            resources['indicators'].get('pos'),
            'pct_access_500m_fresh_food_market_score',
            resources['indicators'].get('walk'),
        ]
        if indicator
    ]
    try:
        distribution_panel = series.get_grid_panel(
            indicators=distribution_indicators,
        )
    except ValueError:
        distribution_panel = panel
    quantile_df = longitudinal.weighted_quantiles(distribution_panel)
    region = series.reference.region
    resources['quantile_bands'] = plots.distribution_box_panels(
        quantile_df,
        distribution_indicators,
        cmap=cmap,
        width=mm(FIGURE_SIZES_MM['quantile_bands'][0]),
        height=mm(FIGURE_SIZES_MM['quantile_bands'][1]),
        region=region,
        phrases=phrases,
        font_size=FIGURE_FONT_SIZE,
        path=f'{figure_dir}/quantile_bands_{language}.png',
    )
    city = series.get_city_panel()
    resources['_data'] = {
        'panel': panel,
        'quantiles': quantile_df,
        'city': city,
        'distribution_indicators': distribution_indicators,
    }
    city_columns = {
        indicator: (
            f'pop_pct_{indicator}_above_reference'
            if indicator in series._derived_indicators()
            else f'pop_{indicator}'
        )
        for indicator in distribution_indicators
    }
    trends = pd.DataFrame(
        [
            {
                'indicator': indicator,
                'timepoint': timepoint,
                'statistic': 'pop_share_pct',
                'value': city.loc[timepoint, column],
            }
            for indicator, column in city_columns.items()
            if column in city.columns
            for timepoint in city.index
        ],
    )
    if len(trends) > 0:
        trends.attrs['timepoints'] = list(city.index)
        labels = {
            indicator: phrases.get(
                'walkability_above_reference_label',
                'Population in neighbourhoods with walkability above the '
                'median of 25 cities internationally',
            )
            for indicator in distribution_indicators
            if indicator in series._derived_indicators()
        }
        resources['threshold_trends'] = plots.threshold_trend_plot(
            trends,
            labels={
                indicator: labels.get(indicator)
                or plots._indicator_label(indicator, region, phrases)
                for indicator in distribution_indicators
            },
            ylabel=phrases.get('threshold_trends_ylabel', 'Population (%)'),
            cmap=cmap,
            width=mm(FIGURE_SIZES_MM['threshold_trends'][0]),
            height=mm(FIGURE_SIZES_MM['threshold_trends'][1]),
            region=region,
            phrases=phrases,
            font_size=FIGURE_FONT_SIZE,
            path=f'{figure_dir}/threshold_trends_{language}.png',
        )
    # access profile radar
    style = (series.config.get('reporting') or {}).get('access_profile', 'auto')
    if style == 'auto':
        style = 'change' if len(series.timepoints) == 2 else 'grouped'
    resources['access_profile_style'] = style
    try:
        resources['access_profile'] = plots.access_profile_longitudinal(
            series,
            language=language,
            phrases=phrases,
            cmap=cmap,
            style=style,
            path=f'{figure_dir}/access_profile_longitudinal_{language}.png',
        )
    except Exception as e:
        print(f'  Access profile figure skipped: {e}')
    # policy figures
    if any(tp.has_policy for tp in series.timepoints):
        policy_panel = series.get_policy_panel()
        resources['policy_panel'] = policy_panel
        for measure in ('presence', 'quality'):
            try:
                resources[f'policy_{measure}'] = (
                    plots.policy_rating_longitudinal(
                        policy_panel,
                        measure=measure,
                        cmap=cmap,
                        path=(
                            f'{figure_dir}/policy_{measure}_'
                            'longitudinal.png'
                        ),
                    )
                )
            except ValueError as e:
                print(f'  Policy {measure} gauge skipped: {e}')
        comparison = build_policy_comparison(series, phrases)
        if len(comparison) > 0:
            resources['policy_comparison'] = plots.policy_comparison_table(
                comparison,
                path=f'{figure_dir}/policy_comparison_{language}.png',
            )
    # equity figures (only when an external stratification is configured)
    stratifications = series._equity_settings()['stratification']
    if stratifications:
        # prefer a fixed stratification, whose areas are comparable over time
        fixed = [s for s in stratifications if not s.get('by_timepoint')]
        stratification = (fixed or stratifications)[0]
        try:
            aggregation = stratification.get('aggregation') or (
                series._stratification_for_timepoint(
                    stratification,
                    series.reference.label,
                )
                or {}
            ).get('aggregation')
            stratified = series.stratified_equity(
                stratification,
                indicators=indicators,
            )
            resources['equity_stratified'] = plots.slope_chart(
                stratified.query("statistic == 'weighted_mean'").query(
                    f"indicator == '{resources['indicators']['pt']}'",
                ),
                group='stratum',
                label=plots._indicator_label(
                    resources['indicators']['pt'],
                    region,
                    phrases,
                ),
                group_label=stratification.get('label')
                or stratification.get('name')
                or aggregation,
                low_label=stratification.get('low_label'),
                high_label=stratification.get('high_label'),
                cmap=cmap,
                width=mm(FIGURE_SIZES_MM['equity_stratified'][0]),
                height=mm(FIGURE_SIZES_MM['equity_stratified'][1]),
                font_size=FIGURE_FONT_SIZE,
                path=f'{figure_dir}/equity_stratified_{language}.png',
            )
            resources['_data']['stratified'] = stratified
            resources['_data']['stratification'] = stratification
            # change by stratum, from the first to the latest timepoint
            resources['equity_dumbbell'] = plots.decile_dumbbell_chart(
                stratified,
                resources['indicators']['pt'],
                stratum_label=stratification.get('label')
                or stratification.get('name')
                or aggregation,
                low_label=stratification.get('low_label'),
                high_label=stratification.get('high_label'),
                cmap=cmap,
                width=mm(FIGURE_SIZES_MM['equity_dumbbell'][0]),
                height=mm(FIGURE_SIZES_MM['equity_dumbbell'][1]),
                region=region,
                phrases=phrases,
                font_size=FIGURE_FONT_SIZE,
                path=f'{figure_dir}/equity_dumbbell_{language}.png',
            )
        except Exception as e:
            print(f'  Equity figures skipped: {e}')
    return resources


def _access_subject(label: str) -> str:
    """
    Phrase an access indicator's label for use within a sentence.

    For example, 'Percentage of population with access to public open
    space of area 1.5 hectares or larger' becomes 'to public open space of
    area 1.5 hectares or larger', and a trailing data source note in
    parentheses is dropped.
    """
    subject = re.sub(r'\s*\(source:[^)]*\)\s*$', '', label).strip()
    subject = re.sub(
        r'^percentage of (the )?population with access\s*',
        '',
        subject,
        flags=re.IGNORECASE,
    )
    return subject


def section_summaries(series, resources: dict, phrases: dict) -> dict:
    """
    Data-driven summaries for the report sections.

    Each section's description is replaced by its summary template
    (pt_longitudinal_summary, pos_longitudinal_summary,
    walk_longitudinal_summary, distribution_summary, equity_summary),
    filled with statistics of change between the first and most recent
    timepoints: population access, the share of residents whose
    neighbourhood access improved or declined, median neighbourhood
    access, and change by socio-economic stratum with the slope index of
    inequality.  Where a summary cannot be computed (e.g. without a
    stratification), the section's existing description is kept.
    Returns the phrases to update.
    """
    data = resources.get('_data') or {}
    longitudinal = _longitudinal()
    plots = _plots()
    region = series.reference.region
    timepoints = series.labels
    first, last = timepoints[0], timepoints[-1]
    derived = series._derived_indicators()
    words = {
        'rose': phrases.get('trend_rose') or 'rose',
        'fell': phrases.get('trend_fell') or 'fell',
        'unchanged': phrases.get('trend_unchanged') or 'was unchanged',
    }

    def trend(v0, v1, tolerance=0.05):
        if pd.isna(v0) or pd.isna(v1) or abs(v1 - v0) < tolerance:
            return words['unchanged']
        return words['rose'] if v1 > v0 else words['fell']

    def pct(value):
        return f'{value:.1f}%'

    values = {'first': first, 'last': last}
    updates = {}
    city = data.get('city')
    panel = data.get('panel')
    indicators = resources.get('indicators', {})
    change = None
    if panel is not None:
        change = longitudinal.compute_change(panel)
        change = change[(change['t0'] == first) & (change['t1'] == last)]
        weights = panel[panel['timepoint'] == last].drop_duplicates('grid_id')
        change = change.merge(
            weights[['grid_id', 'pop_est']],
            on='grid_id',
            how='left',
        )
    for prefix, indicator in indicators.items():
        label = plots._indicator_label(indicator, region, phrases)
        values[f'{prefix}_subject'] = _access_subject(label)
        column = (
            f'pop_pct_{indicator}_above_reference'
            if indicator in derived
            else f'pop_{indicator}'
        )
        if city is not None and column in city.columns:
            v0, v1 = city.loc[first, column], city.loc[last, column]
            values[f'{prefix}_first'] = pct(v0)
            values[f'{prefix}_last'] = pct(v1)
            values[f'{prefix}_trend'] = trend(v0, v1)
        if change is not None:
            rows = change[
                (change['indicator'] == indicator) & change['pop_est'].notna()
            ]
            if len(rows) > 0:
                tolerance = 0.05 if indicator in derived else 1
                total = rows['pop_est'].sum()
                values[f'{prefix}_improved'] = pct(
                    100 * rows.loc[rows['change'] > tolerance, 'pop_est'].sum()
                    / total,
                )
                values[f'{prefix}_declined'] = pct(
                    100
                    * rows.loc[rows['change'] < -tolerance, 'pop_est'].sum()
                    / total,
                )
    for prefix in ('pt', 'pos', 'walk'):
        key = f'{prefix}_longitudinal_summary'
        template = phrases.get(key)
        if template and prefix in indicators:
            try:
                updates[f'{prefix}_longitudinal_description'] = (
                    template.format(**{**phrases, **values})
                )
            except (KeyError, IndexError, ValueError):
                pass
    # access profile: change in access to each amenity, from city statistics
    if (
        resources.get('access_profile_style') == 'grouped'
        and phrases.get('access_profile_grouped_summary')
    ):
        try:
            access = {
                tp.label: pd.to_numeric(
                    tp.region.get_city_stats(phrases=phrases)['access'],
                    errors='coerce',
                )
                for tp in (series.timepoints[0], series.timepoints[-1])
            }
            difference = (access[last] - access[first]).dropna()
        except Exception:
            difference = pd.Series(dtype=float)
        if len(difference) > 0:
            names = [str(name).replace('\n', ' ') for name in difference.index]
            difference.index = names
            largest = difference.abs().idxmax()
            declined = [n for n, d in difference.items() if d < -0.05]
            profile = {
                'profile_count': len(difference),
                'profile_increased': int((difference > 0.05).sum()),
                'profile_max_name': largest.lower(),
                'profile_max_change': f'{difference[largest]:+.1f}',
                'profile_declined': (
                    f"; access declined for {', '.join(n.lower() for n in declined)}"
                    if declined
                    else ''
                ),
            }
            try:
                updates['longitudinal_series_text'] = phrases[
                    'access_profile_grouped_summary'
                ].format(**{**phrases, **values, **profile})
            except (KeyError, IndexError, ValueError):
                pass
    # distribution: median neighbourhood access at first and last timepoints
    quantiles = data.get('quantiles')
    if quantiles is not None and phrases.get('distribution_summary'):
        medians = quantiles[quantiles['q'] == 0.5]
        parts = []
        for indicator in data.get('distribution_indicators', []):
            if indicator in derived:
                continue
            rows = medians[medians['indicator'] == indicator].set_index(
                'timepoint',
            )['value']
            if first in rows and last in rows:
                subject = _access_subject(
                    plots._indicator_label(indicator, region, phrases),
                )
                parts.append(
                    f'{subject} {trend(rows[first], rows[last])} from '
                    f'{pct(rows[first])} to {pct(rows[last])}',
                )
        if parts:
            listed = (
                parts[0]
                if len(parts) == 1
                else ', '.join(parts[:-1]) + ', and ' + parts[-1]
            )
            try:
                updates['distribution_description'] = phrases[
                    'distribution_summary'
                ].format(**{**phrases, **values, 'distribution_medians': listed})
            except (KeyError, IndexError, ValueError):
                pass
    # equity: change by stratum and in the slope index of inequality
    stratified = data.get('stratified')
    stratification = data.get('stratification') or {}
    pt = indicators.get('pt')
    if stratified is not None and pt and phrases.get('equity_summary'):
        rows = stratified[stratified['indicator'] == pt]
        means = rows[rows['statistic'] == 'weighted_mean'].pivot_table(
            index='stratum',
            columns='timepoint',
            values='value',
        )
        strata = plots.stratum_order(means.index)
        sii = rows[rows['statistic'] == 'sii'].set_index('timepoint')['value']
        if len(strata) > 1 and first in means and last in means:
            low, high = strata[0], strata[-1]
            names = plots.stratum_names(strata)
            delta = (means[last] - means[first]).reindex(strata)
            largest = delta.abs().idxmax()
            noun = {10: 'decile', 5: 'quintile', 4: 'quartile'}.get(
                len(strata),
                'group',
            )
            # describe the gradient by the areas it favours (a positive slope
            # index of inequality favours the highest strata), and whether
            # that advantage narrowed, widened or reversed
            s0, s1 = sii.get(first, np.nan), sii.get(last, np.nan)
            low_name = stratification.get('low_label') or 'lowest'
            high_name = stratification.get('high_label') or 'highest'

            def favoured(value):
                return high_name if value > 0 else low_name

            if pd.isna(s0) or pd.isna(s1):
                shift = phrases.get('gradient_unchanged') or 'was little changed'
            elif abs(s1 - s0) < 0.1:
                shift = (
                    f"{phrases.get('gradient_unchanged') or 'was little changed'}"
                    f', favouring the {favoured(s1)} areas'
                )
            elif s0 * s1 < 0:
                shift = (
                    f'reversed, from favouring the {favoured(s0)} areas to '
                    f'favouring the {favoured(s1)} areas'
                )
            elif abs(s1) < abs(s0):
                shift = f'in favour of the {favoured(s1)} areas narrowed'
            else:
                shift = f'in favour of the {favoured(s1)} areas widened'
            equity = {
                'stratum_noun': noun,
                'low_label': stratification.get('low_label') or 'lowest',
                'high_label': stratification.get('high_label') or 'highest',
                'low_stratum': names[0],
                'high_stratum': names[-1],
                'equity_low_first': pct(means.loc[low, first]),
                'equity_high_first': pct(means.loc[high, first]),
                'equity_low_last': pct(means.loc[low, last]),
                'equity_high_last': pct(means.loc[high, last]),
                'equity_low_change': f'{delta[low]:+.1f}',
                'equity_high_change': f'{delta[high]:+.1f}',
                'equity_max_stratum': names[strata.index(largest)],
                'equity_max_change': f'{delta[largest]:+.1f}',
                'sii_first': f'{sii.get(first, np.nan):+.1f}',
                'sii_last': f'{sii.get(last, np.nan):+.1f}',
                'sii_shift': shift,
            }
            try:
                updates['equity_description'] = phrases['equity_summary'].format(
                    **{**phrases, **values, **equity},
                )
            except (KeyError, IndexError, ValueError):
                pass
    return updates


def _flex_template(pdf, pages, page):
    """Instantiate a FlexTemplate for a physical page's elements."""
    from fpdf import FlexTemplate

    return FlexTemplate(pdf, elements=pages[str(page)])


def _pdf_insert_long_introduction(
    pdf,
    pages,
    phrases,
    r,
    series,
    report_template,
    page,
):
    """Introduction page with series context."""
    utils = _utils()
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template['introduction'] = phrases[f'{report_template}_intro'].format(
        **phrases,
    )
    language = r.config['pdf']['language']
    context = (
        r.config['reporting']['languages'].get(language, {}).get('context')
    )
    if context:
        template = utils.format_template_context(
            template,
            r,
            language,
            phrases,
        )
    if 'hero_image_2' in template:
        utils._insert_report_image(
            template,
            r,
            phrases,
            2,
            alternate_text='hero_alt',
        )
    template.render()
    return pdf


def _pdf_insert_long_policy_trend(
    pdf,
    pages,
    phrases,
    r,
    resources,
    page,
):
    """Policy presence/quality trend page with per-timepoint gauges."""
    utils = _utils()
    policy_panel = resources.get('policy_panel')
    if policy_panel is None or not policy_panel['assessed'].any():
        return pdf
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    assessed = policy_panel.loc[policy_panel['assessed'].astype(bool)]
    latest = assessed.iloc[-1]
    locale = r.config['pdf']['locale']
    for measure, template_key in [
        ('presence', 'presence_rating'),
        ('quality', 'quality_rating'),
    ]:
        numerator = latest[f'{measure}_numerator']
        denominator = latest[f'{measure}_denominator']
        if template_key in template and not pd.isna(numerator) and denominator:
            template[template_key] = template[template_key].format(
                presence=round(numerator, 1),
                quality=round(numerator, 1),
                n=round(denominator, 1),
                percent=utils._pct(
                    utils.fnum(
                        100 * numerator / denominator,
                        '0.0',
                        locale,
                    ),
                    locale,
                ),
            )
        gauge = resources.get(f'policy_{measure}')
        if gauge and f'{template_key}_longitudinal' in template:
            template[f'{template_key}_longitudinal'] = gauge
    template.render()
    return pdf


def _pdf_insert_long_policy_comparison(
    pdf,
    pages,
    phrases,
    resources,
    page,
):
    """Policy checklist comparison table page."""
    if not resources.get('policy_comparison'):
        return pdf
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template['policy_comparison_table'] = resources['policy_comparison']
    template.render()
    return pdf


def _pdf_insert_long_access_profile(pdf, pages, phrases, resources, page):
    """Multi-timepoint access profile page."""
    if not resources.get('access_profile'):
        return pdf
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template['access_profile'] = resources['access_profile']
    if 'access_profile_text' in template:
        template['access_profile_text'] = phrases[
            'access_profile_longitudinal_text'
        ].format(**phrases)
    template.render()
    return pdf


def _pdf_insert_long_maps(pdf, pages, phrases, resources, prefix, page):
    """Small multiples and change map page for an indicator."""
    small_multiples = resources.get(f'{prefix}_small_multiples')
    if not small_multiples:
        return pdf
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template[f'{prefix}_small_multiples'] = small_multiples
    change_map = resources.get(f'{prefix}_change_map')
    if change_map and f'{prefix}_change_map' in template:
        template[f'{prefix}_change_map'] = change_map
    template.render()
    return pdf


def _pdf_insert_long_distribution(pdf, pages, phrases, resources, page):
    """Distributional change page (quantile bands, threshold trends)."""
    if not resources.get('quantile_bands'):
        return pdf
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template['quantile_bands'] = resources['quantile_bands']
    if resources.get('threshold_trends') and 'threshold_trends' in template:
        template['threshold_trends'] = resources['threshold_trends']
    template.render()
    return pdf


def _pdf_insert_long_equity(pdf, pages, phrases, resources, page):
    """Stratified equity page (only when stratification is configured)."""
    if not resources.get('equity_stratified'):
        return pdf
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template['equity_stratified'] = resources['equity_stratified']
    if resources.get('equity_dumbbell') and 'equity_dumbbell' in template:
        template['equity_dumbbell'] = resources['equity_dumbbell']
    template.render()
    return pdf


def _pdf_insert_long_back(pdf, pages, phrases, page):
    """Back page with executive summary."""
    pdf.add_page()
    template = _flex_template(pdf, pages, page)
    template.render()
    return pdf


def generate_longitudinal_pdf(
    series,
    font,
    report_template,
    language,
    phrases,
    resources,
) -> str:
    """
    Assemble and save a longitudinal report PDF.

    Reuses the low-level single-region machinery (template setup, fonts,
    cover/citation/context pages) with the latest timepoint's region as
    the configuration carrier, and dedicated longitudinal inserters for
    the remaining pages.  Returns the saved report path.
    """
    import re

    utils = _utils()
    policy_report = _policy_report()
    if report_template not in LONGITUDINAL_TEMPLATE_PAGES:
        raise ValueError(
            f"Unknown longitudinal template '{report_template}'; "
            f'expected one of {list(LONGITUDINAL_TEMPLATE_PAGES)}.',
        )
    page_map = LONGITUDINAL_TEMPLATE_PAGES[report_template]
    latest = series.timepoints[-1]
    r = latest.region
    # policy review setting for the citation page credit
    policy_panel = resources.get('policy_panel')
    policy_review_setting = None
    if policy_panel is not None and policy_panel['assessed'].any():
        assessed = [tp for tp in series.timepoints if tp.has_policy]
        policy_review_setting = policy_report.get_policy_setting(
            assessed[-1].region.config['policy_review'],
        )
    r.config['pdf'] = {
        'font': font,
        'language': language,
        'locale': phrases['locale'],
        'report_template': report_template,
        'figure_path': f'{series.output_dir}/figures',
        'indicators': r.indicators,
        'policy_review': policy_panel,
        'policy_review_setting': policy_review_setting,
        'indicators_region': r.get_df('indicators_region'),
    }
    pages = utils.pdf_template_setup(
        r.config,
        report_template,
        font,
        language,
        phrases,
    )
    pdf = utils._pdf_initialise_document(phrases, r.config)
    pdf = utils._pdf_insert_cover_page(pdf, pages, phrases, r)
    pdf = utils._pdf_insert_citation_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_long_introduction(
        pdf,
        pages,
        phrases,
        r,
        series,
        report_template,
        page_map['introduction'],
    )
    if 'context' in page_map:
        # renders only for spatial-inclusive templates (its own gate)
        pdf = utils._pdf_insert_context_page(pdf, pages, phrases, r)
    if 'policy_trend' in page_map:
        pdf = _pdf_insert_long_policy_trend(
            pdf,
            pages,
            phrases,
            r,
            resources,
            page_map['policy_trend'],
        )
    if 'policy_comparison' in page_map:
        pdf = _pdf_insert_long_policy_comparison(
            pdf,
            pages,
            phrases,
            resources,
            page_map['policy_comparison'],
        )
    if 'access_profile' in page_map:
        pdf = _pdf_insert_long_access_profile(
            pdf,
            pages,
            phrases,
            resources,
            page_map['access_profile'],
        )
    for prefix in ('pt', 'pos', 'walk'):
        if prefix in page_map:
            pdf = _pdf_insert_long_maps(
                pdf,
                pages,
                phrases,
                resources,
                prefix,
                page_map[prefix],
            )
    if 'distribution' in page_map:
        pdf = _pdf_insert_long_distribution(
            pdf,
            pages,
            phrases,
            resources,
            page_map['distribution'],
        )
    if 'equity' in page_map:
        pdf = _pdf_insert_long_equity(
            pdf,
            pages,
            phrases,
            resources,
            page_map['equity'],
        )
    pdf = _pdf_insert_long_back(pdf, pages, phrases, page_map['back'])
    filename = (
        f"GOHSC {phrases['current_year']} - "
        f"{phrases['title_series_line2'].capitalize()} - "
        f"{phrases['city_name']} {phrases['country']} {phrases['year']} - "
        f"{phrases['vernacular']}{phrases['filename_publication_check']}"
        '.pdf'
    )
    filename = re.sub(r'\s+', ' ', filename)
    result = utils.save_pdf_layout(
        pdf,
        folder=series._ensure_output_dir(),
        filename=filename,
        short_filename=utils.compact_report_filename(
            phrases,
            report_template,
            getattr(series, 'codename', r.codename),
            r.config['country_code'],
        ),
    )
    return result


def generate_longitudinal_report(
    series,
    language: str = 'English',
    template=None,
    validate_language: bool = True,
    cmap=None,
):
    """
    Generate longitudinal report(s) for a series in a given language.

    Templates default to the series reporting configuration, or to
    policy_spatial_longitudinal / spatial_longitudinal depending on
    policy review coverage.  Reports and figures are written to the
    series output directory.
    """
    utils = _utils()
    if template is None:
        configured = (series.config.get('reporting') or {}).get(
            'templates',
        )
        if configured:
            templates = configured
        elif any(tp.has_policy for tp in series.timepoints):
            templates = ['policy_spatial_longitudinal']
        else:
            templates = ['spatial_longitudinal']
    else:
        templates = template if isinstance(template, list) else [template]
    unknown = [t for t in templates if t not in LONGITUDINAL_TEMPLATE_PAGES]
    if unknown:
        raise ValueError(
            f'Unknown longitudinal template(s) {unknown}; expected '
            f'a selection from {list(LONGITUDINAL_TEMPLATE_PAGES)}.',
        )
    latest = series.timepoints[-1].region
    font = utils.get_and_setup_font(language, latest.config)
    print(f'\n{language}')
    results = []
    for report_template in templates:
        phrases = get_series_phrases(series, language, report_template)
        if phrases is None:
            return None
        if validate_language and phrases['validated'] != 1:
            print(
                f'  - Skipped {report_template}: the {language} '
                'translation has not yet been validated for '
                'publication (validated = 0 in '
                '_report_configuration.xlsx).  Set '
                'validate_language=False to generate a draft.',
            )
            continue
        print(
            f'\nFigures and maps ({report_template} PDF template; '
            f'{language})',
        )
        resources = generate_longitudinal_resources(
            series,
            phrases,
            language,
            cmap,
        )
        phrases.update(section_summaries(series, resources, phrases))
        print(f'\nReport ({report_template} PDF template; {language})')
        result = generate_longitudinal_pdf(
            series,
            font,
            report_template,
            language,
            phrases,
            resources,
        )
        print(result)
        results.append(result)
    return results
