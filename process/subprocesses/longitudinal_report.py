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
        'distribution': 8,
        'equity': 9,
        'back': 10,
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
        'distribution': 10,
        'equity': 11,
        'back': 12,
    },
}

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
    """Select the public transport and open space indicators to map."""
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
            width=mm(182),
            height=mm(70),
            path=f'{figure_dir}/{prefix}_small_multiples_{language}.png',
        )
        resources[f'{prefix}_change_map'] = plots.change_map(
            series,
            indicator,
            panel=panel,
            phrases=phrases,
            locale=phrases['locale'],
            width=mm(88),
            height=mm(80),
            path=f'{figure_dir}/{prefix}_change_map_{language}.png',
        )
    # distributional figures (headline: public transport access)
    quantile_df = longitudinal.weighted_quantiles(panel)
    region = series.reference.region
    resources['quantile_bands'] = plots.quantile_band_plot(
        quantile_df,
        resources['indicators']['pt'],
        cmap=cmap,
        width=mm(88),
        height=mm(60),
        region=region,
        phrases=phrases,
        path=f'{figure_dir}/quantile_bands_{language}.png',
    )
    thresholds = series._default_thresholds(panel)
    if thresholds:
        threshold_df = longitudinal.population_below_threshold(
            panel,
            thresholds,
        )
        resources['threshold_trends'] = plots.threshold_trend_plot(
            threshold_df,
            cmap=cmap,
            width=mm(124),
            height=mm(79),
            region=region,
            phrases=phrases,
            path=f'{figure_dir}/threshold_trends_{language}.png',
        )
    # access profile radar
    try:
        resources['access_profile'] = plots.access_profile_longitudinal(
            series,
            language=language,
            phrases=phrases,
            cmap=cmap,
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
        stratification = stratifications[0]
        try:
            area_panel = series.get_area_panel(
                stratification['aggregation'],
                indicators=indicators,
            )
            stratifier = series._load_stratifier(stratification)
            stratified = longitudinal.stratified_summary(
                area_panel,
                stratifier,
                stratification['stratifier_column'],
            )
            resources['equity_stratified'] = plots.slope_chart(
                stratified.query("statistic == 'weighted_mean'").query(
                    f"indicator == '{resources['indicators']['pt']}'",
                ),
                group='stratum',
                group_label=stratification.get(
                    'name',
                    stratification['aggregation'],
                ),
                cmap=cmap,
                width=mm(88),
                height=mm(70),
                path=f'{figure_dir}/equity_stratified_{language}.png',
            )
            area_change = longitudinal.compute_change(area_panel)
            resources['equity_dumbbell'] = plots.dumbbell_chart(
                area_change,
                resources['indicators']['pt'],
                top_n=25,
                width=mm(88),
                height=mm(120),
                region=region,
                phrases=phrases,
                path=f'{figure_dir}/equity_dumbbell_{language}.png',
            )
        except Exception as e:
            print(f'  Equity figures skipped: {e}')
    return resources


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
    for prefix in ('pt', 'pos'):
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
