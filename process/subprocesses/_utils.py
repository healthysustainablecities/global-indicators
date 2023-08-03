"""
Report functions.

Define functions used for formatting and saving indicator reports.
"""
import json
import os
import re
import subprocess as sp
import time
from textwrap import wrap

# import contextily as ctx
# import fiona
import geopandas as gpd
import matplotlib as mpl
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from babel.numbers import format_decimal as fnum
from babel.units import format_unit
from fpdf import FPDF, FlexTemplate
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar

# from mpl_toolkits.axes_grid1.inset_locator import inset_axes


# 'pretty' text wrapping as per https://stackoverflow.com/questions/37572837/how-can-i-make-python-3s-print-fit-the-size-of-the-command-prompt
def get_terminal_columns():
    import shutil

    return shutil.get_terminal_size().columns


def print_autobreak(*args, sep=' '):
    import textwrap

    width = (
        get_terminal_columns()
    )  # Check size once to avoid rechecks per "paragraph"
    # Convert all args to strings, join with separator, then split on any newlines,
    # preserving line endings, so each "paragraph" wrapped separately
    for line in sep.join(map(str, args)).splitlines(True):
        # Py3's print function makes it easy to print textwrap.wrap's result as one-liner
        print(*textwrap.wrap(line, width), sep='\n')


def wrap_autobreak(*args, sep=' '):
    width = (
        get_terminal_columns()
    )  # Check size once to avoid rechecks per "paragraph"
    # Convert all args to strings, join with separator, then split on any newlines,
    # preserving line endings, so each "paragraph" wrapped separately
    for line in sep.join(map(str, args)).splitlines(True):
        # Py3's print function makes it easy to print textwrap.wrap's result as one-liner
        return '\n'.join(textwrap.wrap(line, width))


def generate_metadata_yml(
    engine, folder_path, region_config, settings,
):
    """Generate YAML metadata control file."""
    sql = """SELECT ST_Extent(ST_Transform(geom,4326)) FROM urban_study_region;"""
    from sqlalchemy import text

    with engine.begin() as connection:
        bbox = (
            connection.execute(text(sql))
            .fetchone()[0]
            .replace(' ', ',')
            .replace('(', '[')
            .replace(')', ']')[3:]
        )

    yml = f'{folder_path}/process/configuration/assets/metadata_template.yml'

    with open(yml) as f:
        metadata = f.read()

    metadata = metadata.format(
        name=region_config['name'],
        year=region_config['year'],
        authors=settings['documentation']['authors'],
        url=settings['documentation']['url'],
        individualname=settings['documentation']['individualname'],
        positionname=settings['documentation']['positionname'],
        email=settings['documentation']['email'],
        datestamp=time.strftime('%Y-%m-%d'),
        dateyear=time.strftime('%Y'),
        spatial_bbox=bbox,
        spatial_crs='WGS84',
        region_config=region_config['parameters'],
    )
    metadata = (
        f'# {region_config["name"]} ({region_config["codename"]})\n'
        f'# YAML metadata control file (MCF) template for pygeometa\n{metadata}'
    )
    metadata_yml = f'{region_config["region_dir"]}/{region_config["codename"]}_metadata.yml'
    with open(metadata_yml, 'w') as f:
        f.write(metadata)
    return os.path.basename(metadata_yml)


def generate_metadata_xml(region_dir, codename):
    """Generate xml metadata given a yml metadata control file as per the specification required by pygeometa."""
    yml_in = f'{region_dir}/{codename}_metadata.yml'
    xml_out = f'{region_dir}/{codename}_metadata.xml'
    command = f'pygeometa metadata generate "{yml_in}" --output "{xml_out}" --schema iso19139-2'
    sp.call(command, shell=True)
    return os.path.basename(xml_out)


def postgis_to_csv(file, db_host, db_user, db, db_pwd, table):
    """Export table from PostGIS database to CSV."""
    command = (
        f'ogr2ogr -f "CSV" {file} '
        f'PG:"host={db_host} user={db_user} dbname={db} password={db_pwd}" '
        f'  {table} '
    )
    sp.call(command, shell=True)
    return os.path.basename(file)


def postgis_to_geopackage(gpkg, db_host, db_user, db, db_pwd, tables):
    """Export selection of tables from PostGIS database to geopackage."""
    try:
        os.remove(gpkg)
    except FileNotFoundError:
        pass

    for table in tables:
        print(f'    - {table}')
        command = (
            f'ogr2ogr -update -overwrite -lco overwrite=yes -f GPKG {gpkg} '
            f'PG:"host={db_host} user={db_user} dbname={db} password={db_pwd}" '
            f'  {table} '
        )
        sp.call(command, shell=True)


def get_valid_languages(config):
    """Check if language is valid for given configuration."""
    no_language_warning = "No valid languages found in region configuration.  This is required for report generation.  A default parameterisation will be used for reporting in English.  To further customise for your region and requirements, please add and update the reporting section in your region's configuration file."
    default_language = setup_default_language(config)
    configured_languages = pd.read_excel(
        config['reporting']['configuration'], sheet_name='languages',
    ).columns[2:]
    configured_fonts = pd.read_excel(
        config['reporting']['configuration'], sheet_name='fonts',
    )
    if config['reporting']['languages'] is None:
        print_autobreak(f'\nNote: {no_language_warning}')
        languages = default_language
    else:
        languages = config['reporting']['languages']

    languages_configured = [x for x in languages if x in configured_languages]
    if len(languages_configured) == 0:
        print_autobreak(f'\nNote: {no_language_warning}')
        languages = default_language
    else:
        if len(languages_configured) < len(languages):
            languages_not_configured = [
                x for x in languages if x not in configured_languages
            ]
            print_autobreak(
                f"\nNote: Some languages specified in this region's configuration file ({', '.join(languages_not_configured)}) have not been set up with translations in the report configuration 'languages' worksheet.  Reports will only be generated for those languages that have had prose translations set up ({', '.join(configured_languages)}).",
            )
    required_keys = {'country', 'summary', 'name', 'context'}
    languages_configured_have_required_keys = [
        x for x in languages_configured if languages[x].keys() == required_keys
    ]
    if len(languages_configured_have_required_keys) < len(
        languages_configured,
    ):
        languages_configured_without_required_keys = [
            x
            for x in languages_configured
            if x not in languages_configured_have_required_keys
        ]
        missing_keys = {
            m: [x for x in required_keys if x not in languages[m].keys()]
            for m in languages_configured_without_required_keys
        }
        print_autobreak(
            f"""\nNote: Some configured languages ({languages_configured_without_required_keys}) do not have all the required keys (missing or mis-spelt keys: {missing_keys}).  These will be set up to use default values.""",
        )
        for language in languages_configured_without_required_keys:
            for key in required_keys:
                if key not in languages[language].keys():
                    languages[language][key] = default_language['English'][key]
    languages = {
        cl: languages[cl] for cl in languages if cl in configured_languages
    }
    for font_language in set(
        configured_fonts.loc[configured_fonts['Language'].isin(languages)][
            'Language'
        ],
    ):
        language_fonts_list = (
            configured_fonts.loc[
                configured_fonts['Language'] == font_language
            ]['File']
            .unique()
            .tolist()
        )
        if not all([os.path.exists(x) for x in language_fonts_list]):
            print_autobreak(
                f"\nNote: One or more fonts specified in this region's configuration file for the language {font_language} ({', '.join(language_fonts_list)}) do not exist.  This language will be skipped when generating maps, figures and reports until configured fonts can be located.  These may have to be downloaded and stored in the configured location.",
            )
            languages = {
                f: languages[f] for f in languages if f != font_language
            }
    return languages


def setup_default_language(config):
    """Setup and return languages for given configuration."""
    languages = {
        'English': {
            'name': config['name'],
            'country': config['country'],
            'summary': 'After reviewing the results, update this summary text to contextualise your findings, and relate to external text and documents (e.g. using website hyperlinks).',
            'context': [
                {
                    'Regional characterisation': [
                        {'summary': None},
                        {'source': None},
                    ],
                },
                {
                    'City founding context': [
                        {'summary': None},
                        {'source': None},
                    ],
                },
                {
                    'Socio-economic conditions': [
                        {'summary': None},
                        {'source': None},
                    ],
                },
                {'Weather': [{'summary': None}, {'source': None}]},
                {'Topography': [{'summary': None}, {'source': None}]},
                {
                    'Anticipated environmental disaster risks': [
                        {'summary': None},
                        {'source': None},
                    ],
                },
                {
                    'Additional contextual information': [
                        {'summary': None},
                        {'source': None},
                    ],
                },
            ],
        },
    }
    return languages


def check_and_update_config_reporting_parameters(config):
    """Checks config reporting parameters and updates these if necessary."""
    reporting_default = {
        'configuration': './configuration/_report_configuration.xlsx',
        'templates': ['policy_spatial'],
        'publication_ready': False,
        'doi': None,
        'images': {
            1: {
                'file': 'Example image of a vibrant, walkable, urban neighbourhood - landscape.jpg',
                'description': 'Example image of a vibrant, walkable, urban neighbourhood with diverse people using active modes of transport and a tram (replace with a photograph, customised in region configuration)',
                'credit': 'Carl Higgs, Bing Image Creator, 2023',
            },
            2: {
                'file': 'Example image of a vibrant, walkable, urban neighbourhood - square.jpg',
                'description': 'Example image of a vibrant, walkable, urban neighbourhood with diverse people using active modes of transport and a tram (replace with a photograph, customised in region configuration)',
                'credit': 'Carl Higgs, Bing Image Creator, 2023',
            },
        },
        'languages': setup_default_language(config),
        'exceptions': {},
    }
    if 'reporting' not in config:
        print_autobreak(
            "\nNote: No 'reporting' section found in region configuration.  This is required for report generation.  A default parameterisation will be used for reporting in English.  To further customise for your region and requirements, please add and update the reporting section in your region's configuration file.",
        )
        reporting = reporting_default.copy()
    else:
        reporting = config['reporting'].copy()
    for key in reporting_default.keys():
        if key not in reporting.keys():
            reporting[key] = reporting_default[key]
            print_autobreak(
                f"\nNote: Reporting parameter '{key}' not found in region configuration.  Using default value of '{reporting_default[key]}'.  To further customise for your region and requirements, please add and update the reporting section in your region's configuration file.",
            )
    config['reporting'] = reporting
    reporting['languages'] = get_valid_languages(config)
    return reporting


def generate_report_for_language(
    r, language, indicators, policies,
):
    from subprocesses.batlow import batlow_map as cmap

    """Generate report for a processed city in a given language."""
    font = get_and_setup_font(language, r.config)
    # set up policies
    city_policy = policy_data_setup(policies, r.config['policy_review'])
    # get city and grid summary data
    gdfs = {}
    for gdf in ['city', 'grid']:
        gdfs[gdf] = r.get_gdf(r.config[f'{gdf}_summary'])
    # The below currently relates walkability to specified reference
    # (e.g. the GHSCIC 25 city median, following standardisation using
    # 25-city mean and standard deviation for sub-indicators)
    gdfs['grid'] = evaluate_comparative_walkability(
        gdfs['grid'], indicators['report']['walkability']['ghscic_reference'],
    )
    indicators['report']['walkability'][
        'walkability_above_median_pct'
    ] = evaluate_threshold_pct(
        gdfs['grid'],
        'all_cities_walkability',
        '>',
        indicators['report']['walkability']['ghscic_walkability_reference'],
    )
    for i in indicators['report']['thresholds']:
        indicators['report']['thresholds'][i]['pct'] = evaluate_threshold_pct(
            gdfs['grid'],
            indicators['report']['thresholds'][i]['field'],
            indicators['report']['thresholds'][i]['relationship'],
            indicators['report']['thresholds'][i]['criteria'],
        )
    # set up phrases
    phrases = prepare_phrases(r.config, language)
    # Generate resources
    print(f'\nFigures and maps ({language})')
    if phrases['_export'] == 1:
        capture_return = generate_resources(
            r.config,
            gdfs['city'],
            gdfs['grid'],
            phrases,
            indicators,
            city_policy,
            language,
            cmap,
        )
        # instantiate template
        for template in r.config['reporting']['templates']:
            print(f'\nReport ({template} PDF template; {language})')
            capture_return = generate_scorecard(
                r.config,
                phrases,
                indicators,
                city_policy,
                language,
                template,
                font,
            )
            print(capture_return)
    else:
        print(
            '  - Skipped: This language has not been flagged for export in _report_configuration.xlsx (some languages such as Tamil may have features to their writing that currently are not supported, such as Devaganari conjuncts; perhaps for this reason it has not been flagged for export, or otherwise it has not been fully configured).',
        )


def get_and_setup_font(language, config):
    """Setup and return font for given language configuration."""
    fonts = pd.read_excel(
        config['reporting']['configuration'], sheet_name='fonts',
    )
    if language.replace(' (Auto-translation)', '') in fonts.Language.unique():
        fonts = fonts.loc[
            fonts['Language'] == language.replace(' (Auto-translation)', '')
        ].fillna('')
    else:
        fonts = fonts.loc[fonts['Language'] == 'default'].fillna('')
    main_font = fonts.File.values[0].strip()
    fm.fontManager.addfont(main_font)
    prop = fm.FontProperties(fname=main_font)
    fm.findfont(
        prop=prop, directory=main_font, rebuild_if_missing=True,
    )
    plt.rcParams['font.family'] = prop.get_name()
    font = fonts.Font.values[0]
    return font


def policy_data_setup(policies, policy_review):
    """Returns a dictionary of policy data."""
    review = pd.read_excel(policy_review, index_col=0)
    df_policy = {}
    # Presence score
    df_policy['Presence_rating'] = review.loc['Score']['Policy identified']
    # Quality score
    df_policy['Checklist_rating'] = review.loc['Score']['Quality']
    # Presence
    df_policy['Presence'] = review.loc[
        [p['Policy'] for p in policies if p['Display'] == 'Presence']
    ].apply(lambda x: x['Weight'] * x['Policy identified'], axis=1)
    # GDP
    df_policy['Presence_gdp'] = pd.DataFrame(
        [
            {
                c: p[c]
                for c in p
                if c
                in ['Label', 'gdp_comparison_middle', 'gdp_comparison_upper']
            }
            for p in policies
            if p['Display'] == 'Presence'
        ],
    )
    df_policy['Presence_gdp'].columns = ['Policy', 'middle', 'upper']
    df_policy['Presence_gdp'].set_index('Policy', inplace=True)
    # Urban Checklist
    df_policy['Checklist'] = review.loc[
        [p['Policy'] for p in policies if p['Display'] == 'Checklist']
    ]['Checklist']
    # Public open space checklist
    df_policy['POS'] = review.loc[
        [p['Policy'] for p in policies if p['Display'] == 'POS']
    ]['Checklist']
    # Public transport checklist
    df_policy['PT'] = review.loc[
        [p['Policy'] for p in policies if p['Display'] == 'PT']
    ]['Checklist']
    return df_policy


def evaluate_comparative_walkability(gdf_grid, reference):
    """Evaluate walkability relative to 25-city study reference."""
    for x in reference:
        gdf_grid[f'z_{x}'] = (gdf_grid[x] - reference[x]['mean']) / reference[
            x
        ]['sd']
    gdf_grid['all_cities_walkability'] = sum(
        [gdf_grid[f'z_{x}'] for x in reference],
    )
    return gdf_grid


def evaluate_threshold_pct(
    gdf_grid, indicator, relationship, reference, population='pop_est',
):
    """Evaluate whether a pandas series meets a threshold criteria (eg. '<' or '>'."""
    percentage = round(
        100
        * gdf_grid.query(f'{indicator} {relationship} {reference}')[
            population
        ].sum()
        / gdf_grid[population].sum(),
        1,
    )
    return percentage


def generate_resources(
    config,
    gdf_city,
    gdf_grid,
    phrases,
    indicators,
    city_policy,
    language,
    cmap,
):
    """
    The function prepares a series of image resources required for the global indicator score cards.

    The city_path string variable is returned, where generated resources will be stored upon successful execution.
    """
    figure_path = f'{config["region_dir"]}/figures'
    locale = phrases['locale']
    city_stats = compile_city_stats(gdf_city, indicators, phrases)
    if not os.path.exists(figure_path):
        os.mkdir(figure_path)
    # Access profile
    file = f'{figure_path}/access_profile_{language}.jpg'
    if os.path.exists(file):
        print(
            f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
        )
    else:
        li_profile(
            city_stats=city_stats,
            title=phrases['Population % with access within 500m to...'],
            cmap=cmap,
            phrases=phrases,
            path=file,
        )
        print(f'  figures/access_profile_{language}.jpg')
    # Spatial distribution maps
    spatial_maps = compile_spatial_map_info(
        indicators['report']['spatial_distribution_figures'],
        gdf_city,
        phrases,
        locale,
        language=language,
    )
    ## constrain extreme outlying walkability for representation
    gdf_grid['all_cities_walkability'] = gdf_grid[
        'all_cities_walkability'
    ].apply(lambda x: -6 if x < -6 else (6 if x > 6 else x))
    for f in spatial_maps:
        file = f'{figure_path}/{spatial_maps[f]["outfile"]}'
        if os.path.exists(file):
            print(
                f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
            )
        else:
            spatial_dist_map(
                gdf_grid,
                column=f,
                range=spatial_maps[f]['range'],
                label=spatial_maps[f]['label'],
                tick_labels=spatial_maps[f]['tick_labels'],
                cmap=cmap,
                path=file,
                phrases=phrases,
                locale=locale,
            )
            print(f"  figures/{spatial_maps[f]['outfile']}")
    # Threshold maps
    for scenario in indicators['report']['thresholds']:
        file = f"{figure_path}/{indicators['report']['thresholds'][scenario]['field']}_{language}.jpg"
        if os.path.exists(file):
            print(
                f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
            )
        else:
            threshold_map(
                gdf_grid,
                column=indicators['report']['thresholds'][scenario]['field'],
                scale=indicators['report']['thresholds'][scenario]['scale'],
                comparison=indicators['report']['thresholds'][scenario][
                    'criteria'
                ],
                label=(
                    f"{phrases[indicators['report']['thresholds'][scenario]['title']]} ({phrases['density_units']})"
                ),
                cmap=cmap,
                path=file,
                phrases=phrases,
                locale=locale,
            )
            print(
                f"  figures/{indicators['report']['thresholds'][scenario]['field']}_{language}.jpg",
            )
    if any(['policy' in x for x in config['reporting']['templates']]):
        # Policy ratings
        file = f'{figure_path}/policy_presence_rating_{language}.jpg'
        if os.path.exists(file):
            print(
                f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
            )
        else:
            policy_rating(
                range=[0, 24],
                score=city_policy['Presence_rating'],
                comparison=indicators['report']['policy']['comparisons'][
                    'presence'
                ],
                label='',
                comparison_label=phrases['25 city comparison'],
                cmap=cmap,
                locale=locale,
                path=file,
            )
            print(f'  figures/policy_presence_rating_{language}.jpg')
        file = f'{figure_path}/policy_checklist_rating_{language}.jpg'
        if os.path.exists(file):
            print(
                f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
            )
        else:
            policy_rating(
                range=[0, 57],
                score=city_policy['Checklist_rating'],
                comparison=indicators['report']['policy']['comparisons'][
                    'quality'
                ],
                label='',
                comparison_label=phrases['25 city comparison'],
                cmap=cmap,
                locale=locale,
                path=file,
            )
            print(f'  figures/policy_checklist_rating_{language}.jpg')
    return figure_path


def fpdf2_mm_scale(mm):
    """Returns a width double that of the conversion of mm to inches.

    This has been found, via trial and error, to be useful when preparing images for display in generated PDFs using fpdf2.
    """
    return 2 * mm / 25.4


def _pct(value, locale, length='short'):
    """Formats a percentage sign according to a given locale."""
    return format_unit(value, 'percent', locale=locale, length=length)


def compile_city_stats(gdf_city, indicators, phrases):
    """Compile a set of city statistics with comparisons, given a processed geodataframe of city summary statistics and a dictionary of indicators including reference percentiles."""
    city_stats = {}
    city_stats['access'] = gdf_city[
        indicators['report']['accessibility'].keys()
    ].transpose()[0]
    city_stats['access'].index = [
        indicators['report']['accessibility'][x]['title']
        if city_stats['access'][x] is not None
        else f"{indicators['report']['accessibility'][x]['title']} (not evaluated)"
        for x in city_stats['access'].index
    ]
    city_stats['access'] = city_stats['access'].fillna(
        0,
    )  # for display purposes
    city_stats['comparisons'] = {
        indicators['report']['accessibility'][x]['title']: indicators[
            'report'
        ]['accessibility'][x]['ghscic_reference']
        for x in indicators['report']['accessibility']
    }
    city_stats['percentiles'] = {}
    for percentile in ['p25', 'p50', 'p75']:
        city_stats['percentiles'][percentile] = [
            city_stats['comparisons'][x][percentile]
            for x in city_stats['comparisons'].keys()
        ]
    city_stats['access'].index = [
        phrases[x] for x in city_stats['access'].index
    ]
    return city_stats


def compile_spatial_map_info(
    spatial_distribution_figures, gdf_city, phrases, locale, language,
):
    """
    Compile required information to produce spatial distribution figures.

    This is done using the information recorded in configuration/indicators.yml; specifically, indicators['report']['spatial_distribution_figures']
    """
    # effectively deep copy the supplied dictionary so its not mutable
    spatial_maps = json.loads(json.dumps(spatial_distribution_figures))
    for i in spatial_maps:
        for text in ['label', 'outfile']:
            spatial_maps[i][text] = spatial_maps[i][text].format(**locals())
        if spatial_maps[i]['tick_labels'] is not None:
            spatial_maps[i]['tick_labels'] = [
                x.format(**{'phrases': phrases})
                for x in spatial_maps[i]['tick_labels']
            ]
        if i.startswith('pct_'):
            city_summary_percent = _pct(
                fnum(gdf_city[f'pop_{i}'].fillna(0)[0], '0.0', locale), locale,
            )
            spatial_maps[i][
                'label'
            ] = f'{spatial_maps[i]["label"]} ({city_summary_percent})'
    if gdf_city['pop_pct_access_500m_pt_gtfs_freq_20_score'][
        0
    ] is None or pd.isna(
        gdf_city['pop_pct_access_500m_pt_gtfs_freq_20_score'][0],
    ):
        spatial_maps['pct_access_500m_pt_any_score'] = spatial_maps.pop(
            'pct_access_500m_pt_gtfs_freq_20_score',
        )
        spatial_maps['pct_access_500m_pt_any_score']['label'] = (
            f'{phrases["Percentage of population with access to public transport"]}\n'
            f'({_pct(fnum(gdf_city["pop_pct_access_500m_pt_any_score"][0],"0.0",locale),locale)})'
        )
    return spatial_maps


def add_scalebar(
    ax,
    length,
    multiplier,
    units,
    fontproperties,
    loc='upper left',
    pad=0,
    color='black',
    frameon=False,
    size_vertical=2,
    locale='en',
):
    """
    Adds a scalebar to matplotlib map.

    Requires import of: from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
    As a rule of thumb, a scalebar of 1/3 of feature size seems appropriate.
    For example, to achieve this, calculate the variable 'length' as

        gdf_width = gdf.geometry.total_bounds[2] - gdf.geometry.total_bounds[0]
        scalebar_length = int(gdf_width / (3000))
    """
    scalebar = AnchoredSizeBar(
        ax.transData,
        length * multiplier,
        format_unit(length, units, locale=locale, length='short'),
        loc=loc,
        pad=pad,
        color=color,
        frameon=frameon,
        size_vertical=size_vertical,
        fontproperties=fontproperties,
    )
    ax.add_artist(scalebar)


def add_localised_north_arrow(
    ax,
    text='N',
    xy=(1, 0.96),
    textsize=14,
    arrowprops=dict(facecolor='black', width=4, headwidth=8),
    textcolor='black',
):
    """
    Add a minimal north arrow with custom text label above it to a matplotlib map.

    This can be used to add, for example, 'N' or other language equivalent.  Default placement is in upper right corner of map.
    """
    arrow = ax.annotate(
        '',
        xy=xy,
        xycoords=ax.transAxes,
        xytext=(0, -0.5),
        textcoords='offset pixels',
        va='center',
        ha='center',
        arrowprops=arrowprops,
    )
    ax.annotate(
        text,
        xy=(0.5, 1.5),
        xycoords=arrow,
        va='center',
        ha='center',
        fontsize=textsize,
        color=textcolor,
    )


## radar chart
def li_profile(
    city_stats,
    title,
    cmap,
    path,
    phrases,
    width=fpdf2_mm_scale(80),
    height=fpdf2_mm_scale(80),
    dpi=300,
):
    """
    Generates a radar chart for city liveability profiles.

    Expands on https://www.python-graph-gallery.com/web-circular-barplot-with-matplotlib
    -- A python code blog post by Yan Holtz, in turn expanding on work of Tomás Capretto and Tobias Stadler.
    """
    import matplotlib.colors as mpl_colors

    figsize = (width, height)
    # Values for the x axis
    ANGLES = np.linspace(
        0.15, 2 * np.pi - 0.05, len(city_stats['access']), endpoint=False,
    )
    VALUES = city_stats['access'].values
    COMPARISON = city_stats['percentiles']['p50']
    INDICATORS = city_stats['access'].index
    # Colours
    GREY12 = '#1f1f1f'
    norm = mpl_colors.Normalize(vmin=0, vmax=100)
    COLORS = cmap(list(norm(VALUES)))
    # Initialize layout in polar coordinates
    textsize = 11
    fig, ax = plt.subplots(
        figsize=figsize, subplot_kw={'projection': 'polar'},
    )
    # Set background color to white, both axis and figure.
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_theta_offset(1.2 * np.pi / 2)
    ax.set_ylim(-50, 125)
    # Add geometries to the plot -------------------------------------
    # Add bars to represent the cumulative track lengths
    ax.bar(ANGLES, VALUES, color=COLORS, alpha=0.9, width=0.52, zorder=10)
    # Add interquartile comparison reference lines
    ax.vlines(
        ANGLES,
        city_stats['percentiles']['p25'],
        city_stats['percentiles']['p75'],
        color=GREY12,
        zorder=11,
    )
    # Add dots to represent the mean gain
    comparison_text = '\n'.join(
        wrap(phrases['25 city comparison'], 17, break_long_words=False),
    )
    ax.scatter(
        ANGLES,
        COMPARISON,
        s=60,
        color=GREY12,
        zorder=11,
        label=comparison_text,
    )
    # Add labels for the indicators
    try:
        LABELS = [
            '\n'.join(wrap(r, 12, break_long_words=False)) for r in INDICATORS
        ]
    except Exception:
        LABELS = INDICATORS
    # Set the labels
    ax.set_xticks(ANGLES)
    ax.set_xticklabels(LABELS, size=textsize)
    # Remove lines for polar axis (x)
    ax.xaxis.grid(False)
    # Put grid lines for radial axis (y) at 0, 1000, 2000, and 3000
    ax.set_yticklabels([])
    ax.set_yticks([0, 25, 50, 75, 100])
    # Remove spines
    ax.spines['start'].set_color('none')
    ax.spines['polar'].set_color('none')
    # Adjust padding of the x axis labels ----------------------------
    # This is going to add extra space around the labels for the
    # ticks of the x axis.
    XTICKS = ax.xaxis.get_major_ticks()
    for tick in XTICKS:
        tick.set_pad(10)
    # Add custom annotations -----------------------------------------
    # The following represent the heights in the values of the y axis
    PAD = 0
    for num in [0, 50, 100]:
        ax.text(
            -0.2 * np.pi / 2,
            num + PAD,
            f'{num}%',
            ha='center',
            va='center',
            backgroundcolor='white',
            size=textsize,
        )
    # Add text to explain the meaning of the height of the bar and the
    # height of the dot
    ax.text(
        ANGLES[0],
        -50,
        '\n'.join(wrap(title, 13, break_long_words=False)),
        rotation=0,
        ha='center',
        va='center',
        size=textsize,
        zorder=12,
    )
    angle = np.deg2rad(130)
    ax.legend(
        loc='lower right',
        bbox_to_anchor=(0.58 + np.cos(angle) / 2, 0.46 + np.sin(angle) / 2),
    )
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


## Spatial distribution mapping
def spatial_dist_map(
    gdf,
    column,
    range,
    label,
    tick_labels,
    cmap,
    path,
    width=fpdf2_mm_scale(88),
    height=fpdf2_mm_scale(80),
    dpi=300,
    phrases={'north arrow': 'N', 'km': 'km'},
    locale='en',
):
    """Spatial distribution maps using geopandas geodataframe."""
    figsize = (width, height)
    textsize = 14
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_axis_off()
    divider = make_axes_locatable(ax)  # Define 'divider' for the axes
    # Legend axes will be located at the 'bottom' of figure, with width '5%' of ax and
    # a padding between them equal to '0.1' inches
    cax = divider.append_axes('bottom', size='5%', pad=0.1)
    gdf.plot(
        column=column,
        ax=ax,
        legend=True,
        vmin=range[0],
        vmax=range[1],
        legend_kwds={
            'label': '\n'.join(wrap(label, 60, break_long_words=False))
            if label.find('\n') < 0
            else label,
            'orientation': 'horizontal',
        },
        cax=cax,
        cmap=cmap,
    )
    # scalebar
    add_scalebar(
        ax,
        length=int(
            (gdf.geometry.total_bounds[2] - gdf.geometry.total_bounds[0])
            / (3000),
        ),
        multiplier=1000,
        units='kilometer',
        locale=locale,
        fontproperties=fm.FontProperties(size=textsize),
    )
    # north arrow
    add_localised_north_arrow(ax, text=phrases['north arrow'])
    # axis formatting
    cax.tick_params(labelsize=textsize)
    cax.xaxis.label.set_size(textsize)
    if tick_labels is not None:
        # cax.set_xticks(cax.get_xticks().tolist())
        # cax.set_xticklabels(tick_labels)
        cax.xaxis.set_major_locator(ticker.MaxNLocator(len(tick_labels)))
        ticks_loc = cax.get_xticks().tolist()
        cax.xaxis.set_major_locator(ticker.FixedLocator(ticks_loc))
        cax.set_xticklabels(tick_labels)
    plt.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def threshold_map(
    gdf,
    column,
    comparison,
    scale,
    label,
    cmap,
    path,
    width=fpdf2_mm_scale(88),
    height=fpdf2_mm_scale(80),
    dpi=300,
    phrases={'north arrow': 'N', 'km': 'km'},
    locale='en',
):
    """Create threshold indicator map."""
    figsize = (width, height)
    textsize = 14
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_axis_off()
    divider = make_axes_locatable(ax)  # Define 'divider' for the axes
    # Legend axes will be located at the 'bottom' of figure, with width '5%' of ax and
    # a padding between them equal to '0.1' inches
    cax = divider.append_axes('bottom', size='5%', pad=0.1)
    gdf.plot(
        column=column,
        ax=ax,
        legend=True,
        legend_kwds={
            'label': '\n'.join(wrap(label, 60, break_long_words=False))
            if label.find('\n') < 0
            else label,
            'orientation': 'horizontal',
        },
        cax=cax,
        cmap=cmap,
    )
    # scalebar
    add_scalebar(
        ax,
        length=int(
            (gdf.geometry.total_bounds[2] - gdf.geometry.total_bounds[0])
            / (3000),
        ),
        multiplier=1000,
        units='kilometer',
        locale=locale,
        fontproperties=fm.FontProperties(size=textsize),
    )
    # north arrow
    add_localised_north_arrow(ax, text=phrases['north arrow'])
    # axis formatting
    cax.xaxis.set_major_formatter(ticker.EngFormatter())
    cax.tick_params(labelsize=textsize)
    cax.xaxis.label.set_size(textsize)
    plt.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def policy_rating(
    range,
    score,
    cmap,
    comparison=None,
    width=fpdf2_mm_scale(70),
    height=fpdf2_mm_scale(12),
    label='Policies identified',
    comparison_label='25 city median',
    locale='en',
    path='policy_rating_test.jpg',
    dpi=300,
):
    """
    Plot a score (policy rating) and optional comparison (e.g. 25 cities median score) on a colour bar.

    Applied in this context for policy presence and policy quality scores.
    """
    import matplotlib.cm as mpl_cm
    import matplotlib.colors as mpl_colors

    textsize = 14
    fig, ax = plt.subplots(figsize=(width, height))
    fig.subplots_adjust(bottom=0)
    cmap = cmap
    norm = mpl_colors.Normalize(vmin=range[0], vmax=range[1])
    fig.colorbar(
        mpl_cm.ScalarMappable(norm=norm, cmap=cmap),
        cax=ax,
        orientation='horizontal',
        # shrink=0.9, pad=0, aspect=90
    )
    # Format Global ticks
    if comparison is None:
        ax.xaxis.set_ticks([])
    else:
        ax.xaxis.set_major_locator(ticker.FixedLocator([comparison]))
        # ax.set_xticklabels([comparison_label])
        ax.set_xticklabels([''])
        ax.tick_params(labelsize=textsize)
        ax.plot(
            comparison,
            0,
            marker='v',
            color='black',
            markersize=9,
            zorder=10,
            clip_on=False,
        )
        if comparison < 7:
            for t in ax.get_yticklabels():
                t.set_horizontalalignment('left')
        if comparison > 18:
            for t in ax.get_yticklabels():
                t.set_horizontalalignment('right')
    # Format City ticks
    ax_city = ax.twiny()
    ax_city.set_xlim(range)
    ax_city.xaxis.set_major_locator(ticker.FixedLocator([score]))
    ax_city.plot(
        score,
        1,
        marker='^',
        color='black',
        markersize=9,
        zorder=10,
        clip_on=False,
    )
    sep = ''
    # if comparison is not None and label=='':
    ax_city.set_xticklabels(
        [f"{sep}{str(score).rstrip('0').rstrip('.')}/{range[1]}{label}"],
    )
    ax_city.tick_params(labelsize=textsize)
    if comparison is not None:
        # return figure with final styling
        xlabel = f"{comparison_label} ({fnum(comparison,'0.0',locale)})"
        ax.set_xlabel(
            xlabel, labelpad=0.5, fontsize=textsize,
        )
    plt.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def pdf_template_setup(
    config, template, font=None, language='English',
):
    """
    Takes a template xlsx sheet defining elements for use in fpdf2's FlexTemplate function.

    This is loosely based on the specification at https://pyfpdf.github.io/fpdf2/Templates.html
    However, it has been modified to allow additional definitions which are parsed
    by this function
      - can define the page for which template elements are to be applied
      - colours are specified using standard hexadecimal codes
    Any blank cells are set to represent "None".
    The function returns a dictionary of elements, indexed by page number strings.
    """
    # read in elements
    elements = pd.read_excel(
        config['reporting']['configuration'], sheet_name=template,
    )
    document_pages = elements.page.unique()
    # Conditional formatting to help avoid inappropriate line breaks and gaps in Tamil and Thai
    if language in ['Tamil', 'Thai']:
        elements['align'] = elements['align'].replace('J', 'L')
        elements.loc[
            (elements['type'] == 'T') & (elements['size'] < 12), 'size',
        ] = (
            elements.loc[
                (elements['type'] == 'T') & (elements['size'] < 12), 'size',
            ]
            - 1
        )
    if font is not None:
        elements.loc[elements.font == 'custom', 'font'] = font
    elements = elements.to_dict(orient='records')
    elements = [
        {k: v if not str(v) == 'nan' else None for k, v in x.items()}
        for x in elements
    ]
    # Need to convert hexadecimal colours (eg FFFFFF is white) to
    # decimal colours for the fpdf Template class to work
    # We'll establish default hex colours for foreground and background
    planes = {'foreground': '000000', 'background': None}
    for i, element in enumerate(elements):
        for plane in planes:
            if elements[i][plane] not in [None, 'None', 0]:
                # this assumes a hexadecimal string without the 0x prefix
                elements[i][plane] = int(elements[i][plane], 16)
            elif plane == 'foreground':
                elements[i][plane] = int(planes[plane], 16)
            else:
                elements[i][plane] = None
    pages = {}
    for page in document_pages:
        pages[f'{page}'] = [x for x in elements if x['page'] == page]
    return pages


def format_pages(pages, phrases):
    """Format pages with phrases."""
    for page in pages:
        for i, item in enumerate(pages[page]):
            if item['name'] in phrases:
                try:
                    pages[page][i]['text'] = phrases[item['name']].format(
                        **phrases,
                    )
                except Exception:
                    pages[f'{page}'][i]['text'] = phrases[item['name']]
    return pages


def prepare_phrases(config, language):
    """Prepare dictionary for specific language translation given English phrase."""
    import babel

    languages = pd.read_excel(
        config['reporting']['configuration'], sheet_name='languages',
    )
    phrases = json.loads(languages.set_index('name').to_json())[language]
    city_details = config['reporting']
    phrases['city'] = config['name']
    phrases['city_name'] = city_details['languages'][language]['name']
    phrases['country'] = city_details['languages'][language]['country']
    phrases['study_doi'] = 'https://healthysustainablecities.org'
    phrases['summary'] = city_details['languages'][language]['summary']
    phrases['title_city'] = phrases['title_city'].format(
        city_name=phrases['city_name'], country=phrases['country'],
    )
    phrases['year'] = config['year']
    country_code = config['country_code']
    # set default English country code
    if language == 'English' and country_code not in ['AU', 'GB', 'US']:
        country_code = 'AU'
    phrases['locale'] = f'{phrases["language_code"]}_{country_code}'
    try:
        babel.Locale.parse(phrases['locale'])
    except babel.core.UnknownLocaleError:
        phrases['locale'] = f'{phrases["language_code"]}'
        babel.Locale.parse(phrases['locale'])
    # extract English language variables
    phrases['metadata_author'] = languages.loc[
        languages['name'] == 'title_author', 'English',
    ].values[0]
    phrases['metadata_title1'] = languages.loc[
        languages['name'] == 'title_series_line1', 'English',
    ].values[0]
    phrases['metadata_title2'] = languages.loc[
        languages['name'] == 'title_series_line2', 'English',
    ].values[0]
    # restrict to specific language
    languages = languages.loc[
        languages['role'] == 'template', ['name', language],
    ]
    phrases['vernacular'] = languages.loc[
        languages['name'] == 'language', language,
    ].values[0]
    if city_details['doi'] is not None:
        phrases['city_doi'] = f'https://doi.org/{city_details["doi"]}'
    else:
        phrases['city_doi'] = ''
    phrases['local_collaborators_names'] = config['authors']
    phrases['Image 1 file'] = city_details['images'][1]['file']
    phrases['Image 2 file'] = city_details['images'][2]['file']
    phrases['Image 1 credit'] = city_details['images'][1]['credit']
    phrases['Image 2 credit'] = city_details['images'][2]['credit']
    phrases['region_population_citation'] = config['population']['citation']
    phrases['region_urban_region_citation'] = config['urban_region'][
        'citation'
    ]
    phrases['region_OpenStreetMap_citation'] = config['OpenStreetMap'][
        'citation'
    ]
    # incoporating study citations
    citations = {
        'study_citations': '\n\nThe Lancet Global Health Series on urban design, transport, and health. 2022. https://www.thelancet.com/series/urban-design-2022 \n\nGlobal Observatory of Healthy & Sustainable Cities. {year}. https://www.healthysustainablecities.org',
        'citation_doi': '{local_collaborators_names}. {year}. {title_city}, {country}—Healthy and Sustainable City Indicators Report ({vernacular}). {city_doi}',
        'citations': '{citation_series}: {study_citations}\n\n{citation_population}: {region_population_citation} \n{citation_boundaries}: {region_urban_region_citation} \n{citation_features}: {region_OpenStreetMap_citation} \n{citation_colour}: Crameri, F. (2018). Scientific colour-maps (3.0.4). Zenodo. https://doi.org/10.5281/zenodo.1287763',
    }
    # handle city-specific exceptions
    language_exceptions = city_details['exceptions']
    if (language_exceptions is not None) and (language in language_exceptions):
        for e in language_exceptions[language]:
            phrases[e] = language_exceptions[language][e]
    for citation in citations:
        if citation != 'citation_doi' or 'citation_doi' not in phrases:
            phrases[citation] = citations[citation].format(**phrases)
    phrases['citation_doi'] = phrases['citation_doi'].format(**phrases)
    # Conditional draft marking if not flagged as publication ready
    if config['reporting']['publication_ready']:
        phrases['metadata_title2'] = ''
        phrases['title_series_line2'] = ''
        phrases['filename_publication_check'] = ''
    else:
        phrases['citation_doi'] = phrases['citation_doi'] + ' (DRAFT)'
        phrases['title_city'] = phrases['title_city'] + ' (DRAFT)'
        phrases['filename_publication_check'] = ' (DRAFT)'
    return phrases


def wrap_sentences(words, limit=50, delimiter=''):
    """Wrap sentences if exceeding limit."""
    sentences = []
    sentence = ''
    gap = len(delimiter)
    for i, word in enumerate(words):
        if i == 0:
            sentence = word
            continue
        # combine word to sentence if under limit
        if len(sentence) + gap + len(word) <= limit:
            sentence = sentence + delimiter + word
        else:
            sentences.append(sentence)
            sentence = word
            # append the final word if not yet appended
            if i == len(words) - 1:
                sentences.append(sentence)
        # finally, append sentence of all words if still below limit
        if (i == len(words) - 1) and (sentences == []):
            sentences.append(sentence)
    return sentences


def prepare_pdf_fonts(pdf, config, language):
    """Prepare PDF fonts."""
    fonts = pd.read_excel(
        config['reporting']['configuration'], sheet_name='fonts',
    )
    fonts = (
        fonts.loc[
            fonts['Language'].isin(
                ['default', language.replace(' (Auto-translation)', '')],
            )
        ]
        .fillna('')
        .drop_duplicates()
    )
    for s in ['', 'B', 'I', 'BI']:
        for langue in ['default', language]:
            if (
                langue.replace(' (Auto-translation)', '')
                in fonts.Language.unique()
            ):
                f = fonts.loc[
                    (
                        fonts['Language']
                        == langue.replace(' (Auto-translation)', '')
                    )
                    & (fonts['Style'] == s)
                ]
                if f'{f.Font.values[0]}{s}' not in pdf.fonts.keys():
                    pdf.add_font(
                        f.Font.values[0], style=s, fname=f.File.values[0],
                    )


def save_pdf_layout(pdf, folder, filename):
    """Save a PDF report in template subfolder in specified location."""
    if not os.path.exists(folder):
        os.mkdir(folder)
    template_folder = f'{folder}/reports'
    if not os.path.exists(template_folder):
        os.mkdir(template_folder)
    pdf.output(f'{template_folder}/{filename}')
    return f'  reports/{filename}'.replace('/home/ghsci/', '')


def generate_scorecard(
    config,
    phrases,
    indicators,
    city_policy,
    language='English',
    template='policy_spatial',
    font=None,
):
    """
    Format a PDF using the pyfpdf FPDF2 library, and drawing on definitions from a UTF-8 CSV file.

    Included in this function is the marking of a policy 'scorecard', with ticks, crosses, etc.
    """
    from ghsci import Region, date

    r = Region(config['codename'])
    r.config = config
    locale = phrases['locale']
    pages = pdf_template_setup(config, template, font, language)
    pages = format_pages(pages, phrases)
    # initialise PDF
    pdf = FPDF(orientation='portrait', format='A4', unit='mm')
    # set up fonts
    prepare_pdf_fonts(pdf, config, language)
    pdf.set_author(phrases['metadata_author'])
    pdf.set_title(f"{phrases['metadata_title1']} {phrases['metadata_title2']}")
    pdf.set_auto_page_break(False)
    pdf = generate_pdf(
        pdf,
        pages,
        r,
        template,
        language,
        locale,
        phrases,
        indicators,
        city_policy,
    )
    # Output report pdf
    filename = f"GOHSC {date[:4]} - {template} report - {phrases['city_name']} - {phrases['vernacular']}{phrases['filename_publication_check']}.pdf"
    capture_result = save_pdf_layout(
        pdf, folder=config['region_dir'], filename=filename,
    )
    return capture_result


def generate_pdf(
    pdf,
    pages,
    r,
    report_template,
    language,
    locale,
    phrases,
    indicators,
    city_policy,
):
    """
    Generate a PDF based on a template for web distribution.

    This template includes reporting on both policy and spatial indicators.
    """
    config = r.config
    city_path = config['region_dir']
    figure_path = f'{city_path}/figures'
    # Set up Cover page
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['1'])
    template['title_author'] = template['title_author'].format(
        template=report_template.replace('_', '/'),
    )
    if os.path.exists(
        f'{config["folder_path"]}/process/configuration/assets/{phrases["Image 1 file"]}',
    ):
        template[
            'hero_image'
        ] = f'{config["folder_path"]}/process/configuration/assets/{phrases["Image 1 file"]}'
        template['hero_alt'] = ''
        template['Image 1 credit'] = phrases['Image 1 credit']
    template.render()
    # Set up next page
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['2'])
    template['citations'] = phrases['citations']
    template['local_collaborators'] = template['local_collaborators'].format(
        city=phrases['title_city'],
    )
    template['local_collaborators_names'] = phrases[
        'local_collaborators_names'
    ]
    if phrases['translation_names'] is None:
        template['translation'] = ''
        template['translation_names'] = ''
    template.render()
    # Set up next page
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['3'])
    template[
        'introduction'
    ] = f"{phrases['series_intro']}\n\n{phrases['series_interpretation']}".format(
        **phrases,
    )
    if report_template == 'spatial':
        study_region_context_file = study_region_map(
            r.get_engine(),
            config,
            urban_shading=True,
            basemap='satellite',
            arrow_colour='white',
            scale_box=True,
            file_name='study_region_boundary',
        )
        template['study_region_context'] = study_region_context_file
    ## Access profile plot
    template['access_profile'] = f'{figure_path}/access_profile_{language}.jpg'
    ## Walkability plot
    template[
        'all_cities_walkability'
    ] = f'{figure_path}/all_cities_walkability_{language}.jpg'
    template['walkability_above_median_pct'] = phrases[
        'walkability_above_median_pct'
    ].format(
        _pct(
            fnum(
                indicators['report']['walkability'][
                    'walkability_above_median_pct'
                ],
                '0.0',
                locale,
            ),
            locale,
        ),
    )
    if 'policy' in report_template:
        ## Policy ratings
        template[
            'presence_rating'
        ] = f'{figure_path}/policy_presence_rating_{language}.jpg'
        template[
            'quality_rating'
        ] = f'{figure_path}/policy_checklist_rating_{language}.jpg'
        ## City planning requirement presence (round 0.5 up to 1)
        template['city_header'] = phrases['city_name']
        policy_indicators = {0: '✗', 0.5: '~', 1: '✓'}
        for x in range(1, 7):
            # check presence
            template[f'policy_urban_text{x}_response'] = policy_indicators[
                city_policy['Presence'][x - 1]
            ]
            # format percentage units according to locale
            for gdp in ['middle', 'upper']:
                template[f'policy_urban_text{x}_{gdp}'] = _pct(
                    float(city_policy['Presence_gdp'].iloc[x - 1][gdp]),
                    locale,
                    length='short',
                )
        ## Walkable neighbourhood policy checklist
        for i, policy in enumerate(city_policy['Checklist'].index):
            row = i + 1
            for j, item in enumerate([x for x in city_policy['Checklist'][i]]):
                col = j + 1
                template[
                    f"policy_{'Checklist'}_text{row}_response{col}"
                ] = item
    elif 'spatial' in report_template:
        context = config['reporting']['languages']['English']['context']
        keys = [
            ''.join(x)
            for x in config['reporting']['languages']['English']['context']
        ]
        # blurb = '\n\n'.join([f"{k}\n{d[k][0]['summary'] if d[k][0]['summary'] is not None else 'None specified'}" for k,d in zip(keys,context)])
        blurb = [
            (
                k,
                d[k][0]['summary']
                if d[k][0]['summary'] is not None
                else 'None specified',
            )
            for k, d in zip(keys, context)
        ]
        for i, item in enumerate(blurb):
            template[f'region_context_header{i+1}'] = item[0]
            template[f'region_context_text{i+1}'] = item[1]
    template.render()
    # Set up next page
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['4'])
    ## Density plots
    template[
        'local_nh_population_density'
    ] = f'{figure_path}/local_nh_population_density_{language}.jpg'
    template[
        'local_nh_intersection_density'
    ] = f'{figure_path}/local_nh_intersection_density_{language}.jpg'
    ## Density threshold captions
    for scenario in indicators['report']['thresholds']:
        template[scenario] = phrases[f'optimal_range - {scenario}'].format(
            _pct(
                fnum(
                    indicators['report']['thresholds'][scenario]['pct'],
                    '0.0',
                    locale,
                ),
                locale,
            ),
            fnum(
                indicators['report']['thresholds'][scenario]['criteria'],
                '#,000',
                locale,
            ),
            phrases['density_units'],
        )
    if os.path.exists(
        f'{config["folder_path"]}/process/configuration/assets/{phrases["Image 2 file"]}',
    ):
        template[
            'hero_image_2'
        ] = f'{config["folder_path"]}/process/configuration/assets/{phrases["Image 2 file"]}'
        template['hero_alt_2'] = ''
        template['Image 2 credit'] = phrases['Image 2 credit']
    template.render()
    # Set up next page
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['5'])
    template[
        'pct_access_500m_pt.jpg'
    ] = f'{figure_path}/pct_access_500m_pt_{language}.jpg'
    template[
        'pct_access_500m_public_open_space_large_score'
    ] = f'{figure_path}/pct_access_500m_public_open_space_large_score_{language}.jpg'
    if 'policy' in report_template:
        ## Checklist ratings for PT and POS
        for analysis in ['PT', 'POS']:
            for i, policy in enumerate(city_policy[analysis].index):
                row = i + 1
                for j, item in enumerate(
                    [x for x in city_policy[analysis][i]],
                ):
                    col = j + 1
                    template[
                        f'policy_{analysis}_text{row}_response{col}'
                    ] = item
    template['city_text'] = phrases['summary']
    template.render()
    # Set up last page
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['6'])
    template.render()
    return pdf


def plot_choropleth_map(
    r,
    field: str,
    layer: str = 'indicators_grid_100m',
    layer_id: str = 'grid_id',
    title: str = '',
    attribution: str = '',
):
    """Given a region, field, layer and layer id, plot an interactive map."""
    geojson = r.get_geojson(
        f'(SELECT {layer_id},{field},geom FROM {layer}) as sql',
        include_columns=[layer_id, field],
    )
    df = r.get_df(layer)[[layer_id, field]]
    map = choropleth_map(
        geojson=geojson,
        df=df[[layer_id, field]],
        boundary_centroid=tuple(r.get_centroid()),
        key_on=layer_id,
        fields=[layer_id, field],
        title=title,
        attribution=attribution,
    )
    return map


def choropleth_map(
    geojson: json,
    df: pd.DataFrame,
    key_on: str,
    fields: list,
    boundary_centroid: tuple,
    title: str,
    attribution: str,
):
    import folium

    # create a map object
    m = folium.Map(
        location=boundary_centroid,
        zoom_start=11,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    map_attribution = attribution
    folium.TileLayer(
        tiles='http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
        name='OpenStreetMap',
        active=True,
        attr=(
            (
                ' {} | '
                '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | &copy; <a href="http://cartodb.com/attributions">CartoDB</a>'
            ).format(map_attribution)
        ),
    ).add_to(m)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        name='Satellite',
        active=False,
        attr=(
            (
                ' {} | '
                'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
            ).format(map_attribution)
        ),
    ).add_to(m)
    # map
    data_layer = folium.Choropleth(
        geo_data=geojson,
        data=df,
        key_on=f'feature.properties.{key_on}',
        name='choropleth',
        columns=fields,
        fill_color='YlGn',
        fill_opacity=0.7,
        line_opacity=0.1,
        legend_name=title,
    ).add_to(m)
    folium.features.GeoJsonTooltip(
        fields=fields, labels=True, sticky=True,
    ).add_to(data_layer.geojson)
    folium.LayerControl(collapsed=True).add_to(m)
    m.fit_bounds(m.get_bounds())
    return m


def add_color_bar(ax, data, cmap):
    import matplotlib.axes as mpl_axes

    # Create colorbar as a legend
    vmin, vmax = data.min(), data.max()
    # sm = plt.cm.ScalarMappable(cmap=’Blues’, norm=plt.Normalize(vmin=vmin, vmax=vmax))
    divider = make_axes_locatable(ax)
    cax = divider.append_axes(
        'right', size='5%', pad=0.5, axes_class=mpl_axes.Axes,
    )
    sm = plt.cm.ScalarMappable(
        cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax),
    )
    # empty array for the data range
    sm._A = []
    # add the colorbar to the figure
    cbar = ax.figure.colorbar(sm, cax=cax, pad=0.5, location='left')


def study_region_map(
    engine,
    region_config,
    dpi=300,
    phrases={'north arrow': 'N', 'km': 'km'},
    locale='en',
    textsize=12,
    edgecolor='white',
    basemap=True,
    urban_shading=True,
    arrow_colour='black',
    scale_box=False,
    file_name='study_region_map',
    additional_layers=None,
    additional_attribution=None,
):
    """Plot study region boundary."""
    import cartopy.crs as ccrs
    import cartopy.io.ogc_clients as ogcc
    import matplotlib.patheffects as path_effects
    from subprocesses.batlow import batlow_map as cmap

    file_name = re.sub(r'\W+', '_', file_name)
    filepath = f'{region_config["region_dir"]}/figures/{file_name}.png'
    if os.path.exists(filepath):
        print(
            f'  figures/{os.path.basename(filepath)}; Already exists; Delete to re-generate.',
        )
        return filepath
    else:
        urban_study_region = gpd.GeoDataFrame.from_postgis(
            'SELECT * FROM urban_study_region', engine, geom_col='geom',
        ).to_crs(epsg=3857)
        # initialise figure
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.epsg(3857))
        plt.axis('equal')
        # basemap helper codes
        ogcc.METERS_PER_UNIT['urn:ogc:def:crs:EPSG:6.3:3857'] = 1
        ogcc._URN_TO_CRS[
            'urn:ogc:def:crs:EPSG:6.3:3857'
        ] = ccrs.GOOGLE_MERCATOR
        # optionally add additional urban information
        if urban_shading:
            urban = gpd.GeoDataFrame.from_postgis(
                'SELECT * FROM urban_region', engine, geom_col='geom',
            ).to_crs(epsg=3857)
            urban.plot(
                ax=ax, color='yellow', label='Urban centre (GHS)', alpha=0.4,
            )
            city = gpd.GeoDataFrame.from_postgis(
                'SELECT * FROM study_region_boundary', engine, geom_col='geom',
            ).to_crs(epsg=3857)
            city.plot(
                ax=ax,
                label='Administrative boundary',
                facecolor='none',
                edgecolor=edgecolor,
                lw=2,
            )
            # add study region boundary
            urban_study_region.plot(
                ax=ax,
                facecolor='none',
                hatch='///',
                label='Urban study region',
                alpha=0.5,
            )
        else:
            # add study region boundary
            urban_study_region.plot(
                ax=ax,
                facecolor='none',
                edgecolor=edgecolor,
                label='Urban study region',
                lw=2,
            )
        if basemap is not None:
            if basemap == 'satellite':
                basemap = {
                    'tiles': 'https://tiles.maps.eox.at/wms?service=wms&request=getcapabilities',
                    'layer': 's2cloudless-2020',
                    'attribution': 'Basemap: Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2021) released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License',
                }
                ax.add_wms(
                    basemap['tiles'], [basemap['layer']],
                )
                map_attribution = f'Study region boundary: {"; ".join(region_config["study_region_blurb"]["sources"])} | {basemap["attribution"]}'
            elif basemap == 'light':
                basemap = {
                    'tiles': 'https://tiles.maps.eox.at/wms?service=wms&request=getcapabilities',
                    'layer': 'streets',
                    'attribution': 'Basemap: Streets overlay © OpenStreetMap Contributors, Rendering © EOX and MapServer, from https://tiles.maps.eox.at/ released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License',
                }
                ax.add_wms(
                    basemap['tiles'], [basemap['layer']],
                )
                map_attribution = f'Study region boundary: {"; ".join(region_config["study_region_blurb"]["sources"])} | {basemap["attribution"]}'
                # ax.add_image(
                #     cimgt.Stamen(style='toner-lite'), 15, cmap='Greys_r',
                # )
                # map_attribution = f'Study region boundary: {"; ".join(region_config["study_region_blurb"]["sources"])} | Basemap: Stamen Toner Lite'
        else:
            map_attribution = f'Study region boundary: {"; ".join(region_config["study_region_blurb"]["sources"])}'
        if type(additional_layers) in [list, dict]:
            for layer in additional_layers:
                if (
                    type(additional_layers) == dict
                    and len(additional_layers[layer]) > 0
                ):
                    additional_layer_attributes = additional_layers[layer]
                else:
                    additional_layer_attributes = {
                        'facecolor': 'none',
                        'edgecolor': 'black',
                        'alpha': 0.7,
                        'lw': 0.5,
                        'markersize': 0.5,
                    }
                if 'column' in additional_layer_attributes:
                    column = additional_layer_attributes['column']
                    if 'where' in additional_layer_attributes:
                        where = additional_layer_attributes['where']
                    else:
                        where = ''
                    data = gpd.GeoDataFrame.from_postgis(
                        f"""SELECT "{column}", ST_Transform(geom,3857) geom FROM "{layer}" {where}""",
                        engine,
                        geom_col='geom',
                    )
                    data.dropna(subset=[column]).plot(
                        ax=ax,
                        column=column,
                        cmap=cmap,
                        label='Population density',
                        edgecolor=additional_layer_attributes['edgecolor'],
                        lw=additional_layer_attributes['lw'],
                        markersize=additional_layer_attributes['markersize'],
                        alpha=additional_layer_attributes['alpha'],
                    )
                    add_color_bar(ax, data[column], cmap)
                else:
                    data = gpd.GeoDataFrame.from_postgis(
                        f"""SELECT ST_Transform(geom,3857) geom FROM "{layer}" """,
                        engine,
                        geom_col='geom',
                    )
                    data.plot(
                        ax=ax,
                        facecolor=additional_layer_attributes['facecolor'],
                        edgecolor=additional_layer_attributes['edgecolor'],
                        lw=additional_layer_attributes['lw'],
                        markersize=additional_layer_attributes['markersize'],
                        alpha=additional_layer_attributes['alpha'],
                    )
        if additional_attribution is not None:
            map_attribution = (
                f"""{additional_attribution} | {map_attribution}"""
            )
        fig.text(
            0.00,
            0.00,
            map_attribution,
            fontsize=7,
            path_effects=[
                path_effects.withStroke(
                    linewidth=2, foreground='w', alpha=0.5,
                ),
            ],
            wrap=True,
            verticalalignment='bottom',
        )
        # scalebar
        add_scalebar(
            ax,
            length=int(
                (
                    urban_study_region.geometry.total_bounds[2]
                    - urban_study_region.geometry.total_bounds[0]
                )
                / (3000),
            ),
            multiplier=1000,
            units='kilometer',
            locale=locale,
            fontproperties=fm.FontProperties(size=textsize),
            loc='upper left',
            pad=0.2,
            color='black',
            frameon=scale_box,
        )
        # north arrow
        add_localised_north_arrow(
            ax,
            text=phrases['north arrow'],
            arrowprops=dict(facecolor=arrow_colour, width=4, headwidth=8),
            xy=(0.98, 0.96),
            textcolor=arrow_colour,
        )
        ax.set_axis_off()
        plt.subplots_adjust(
            left=0, bottom=0.1, right=1, top=1, wspace=0, hspace=0,
        )
        fig.savefig(filepath, dpi=dpi)
        fig.clf()
        print(f'  figures/{os.path.basename(filepath)}')
        return filepath


def set_scale(total_bounds):
    half_width = (total_bounds[2] - total_bounds[1]) / 2.0
    scale_values = {
        'large': {'distance': 25000, 'display': '25 km'},
        'default': {'distance': 20000, 'display': '20 km'},
        'small': {'distance': 10000, 'display': '10 km'},
        'tiny': {'distance': 5000, 'display': '5 km'},
    }
    if half_width < 10000:
        return scale_values['tiny']
    elif half_width < 20000:
        return scale_values['small']
    elif half_width < 25000:
        return scale_values['default']
    else:
        return scale_values['large']


def buffered_box(total_bounds, distance):
    mod = [-1, -1, 1, 1]
    buffer_distance = [x * distance for x in mod]
    new_bounds = [total_bounds[x] + buffer_distance[x] for x in range(0, 4)]
    return new_bounds


def reproject_raster(inpath, outpath, new_crs):
    import rasterio
    from rasterio.warp import (
        Resampling,
        calculate_default_transform,
        reproject,
    )

    dst_crs = new_crs  # CRS for web meractor
    with rasterio.open(inpath) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds,
        )
        kwargs = src.meta.copy()
        kwargs.update(
            {
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height,
            },
        )
        with rasterio.open(outpath, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                )
