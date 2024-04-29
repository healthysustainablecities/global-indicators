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


def generate_metadata(
    r, settings, format='YAML', return_path=True,
):
    """Generate YAML metadata control file."""
    import yaml
    from sqlalchemy import text

    format = format.upper()
    if format not in ['YAML', 'XML', 'YML']:
        print(
            "Supported metadata formats are 'YAML' or 'XML'.  Returning YAML metadata.",
        )

    if os.path.exists(f"{r.config['region_dir']}/_parameters.yml"):
        with open(f"{r.config['region_dir']}/_parameters.yml") as f:
            r.config['parameters'] = yaml.safe_load(f)

    sql = """SELECT ST_Extent(ST_Transform(geom,4326)) FROM urban_study_region;"""

    with r.engine.begin() as connection:
        bbox = (
            connection.execute(text(sql))
            .fetchone()[0]
            .replace(' ', ',')
            .replace('(', '[')
            .replace(')', ']')[3:]
        )

    yml = f'{r.config["folder_path"]}/process/configuration/assets/metadata_template.yml'

    with open(yml) as f:
        metadata = f.read()

    metadata = metadata.format(
        name=r.config['name'],
        year=r.config['year'],
        authors=settings['documentation']['authors'],
        url=settings['documentation']['url'],
        individualname=settings['documentation']['individualname'],
        positionname=settings['documentation']['positionname'],
        email=settings['documentation']['email'],
        datestamp=time.strftime('%Y-%m-%d'),
        dateyear=time.strftime('%Y'),
        spatial_bbox=bbox,
        spatial_crs='WGS84',
        region_config=r.config['parameters'],
    )
    metadata = (
        f'# {r.config["name"]} ({r.config["codename"]})\n'
        f'# YAML metadata control file (MCF) template for pygeometa\n{metadata}'
    )
    metadata_path = (
        f'{r.config["region_dir"]}/{r.config["codename"]}_metadata.yml'
    )
    with open(metadata_path, 'w') as f:
        f.write(metadata)
    if format == 'XML':
        """Generate xml metadata given a yml metadata control file as per the specification required by pygeometa."""
        yml_in = (
            f'{r.config["region_dir"]}/{r.config["codename"]}_metadata.yml'
        )
        metadata_path = (
            f'{r.config["region_dir"]}/{r.config["codename"]}_metadata.xml'
        )
        command = f'pygeometa metadata generate "{yml_in}" --output "{metadata_path}" --schema iso19139-2'
        sp.call(command, shell=True)
        with open(metadata_path) as f:
            metadata = f.read()
    if return_path:
        return os.path.basename(metadata_path)
    else:
        return metadata


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


def generate_report_for_language(
    r, language, indicators, policies, template=None, cmap=None,
):
    if cmap is None:
        from subprocesses.batlow import batlow_map as cmap

    """Generate report for a processed city in a given language."""
    # get city and grid results summary data, indicators, policy review, phrases and font for reports
    gdfs = {}
    gdfs['city'] = r.get_gdf(r.config['city_summary'])
    indicators, gdfs['grid'] = r.get_indicators(return_gdf=True)
    policy_review = policy_data_setup(r.config['policy_review'], policies)
    phrases = r.get_phrases(language)
    font = get_and_setup_font(language, r.config)
    # Generate resources
    print(f'\nFigures and maps ({language})')
    if phrases['_export'] == 1:
        capture_return = generate_resources(
            r,
            gdfs['city'],
            gdfs['grid'],
            phrases,
            indicators,
            policy_review,
            language,
            cmap,
        )
        # instantiate template
        if template is None:
            reporting_templates = r.config['reporting']['templates']
        else:
            reporting_templates = [template]
        for report_template in reporting_templates:
            print(f'\nReport ({report_template} PDF template; {language})')
            capture_return = generate_scorecard(
                r,
                phrases,
                indicators,
                policy_review,
                language,
                report_template,
                font,
            )
            print(capture_return)
    else:
        print(
            '  - Skipped: This language has not been flagged for export in _report_configuration.xlsx (some languages such as Tamil may have features to their writing that currently are not supported, such as Devaganari conjuncts; perhaps for this reason it has not been flagged for export, or otherwise it has not been fully configured).',
        )


def download_file(url, file, context=None, overwrite=False):
    """Retrieve a file given a URL if the file does not already exist."""
    import os

    import requests

    url = str(url).strip()
    file = str(file).strip()
    if os.path.exists(file):
        if not overwrite:
            print(f'File exists: {file}')
            return file
        else:
            print(f'Attempting to replace {file} from {url}')
    if context is not None:
        print(context)
    get_file = input(
        f"Would you like to attempt to download and save {url} to {file}? (enter 'y' or space to confirm) ",
    )
    if get_file.lower() in ['y', ' ']:
        try:
            r = requests.get(url)
            if not os.path.exists(os.path.dirname(file)):
                os.makedirs(os.path.dirname(file))
            if url.endswith('.zip') and not file.endswith('.zip'):
                with open(f'{file}.zip', 'wb') as f:
                    f.write(r.content)
                    print(
                        f"{url} saved as '{file}.zip'.  This zipped archive may need to be extracted before usage as configured ('{file}').\n",
                    )
                    return None
            else:
                with open(file, 'wb') as f:
                    f.write(r.content)
                print(f'Saved {url} to {file}.')
                return file

        except Exception:
            print(f'Failed to retrieve font from {url}.')
            return None
    else:
        print(
            'Skipping file retrieval.  If this file has been configured for analysis you may have to manually retrieve, or adjust your configuration settings to point to another file.',
        )
        return None


def get_and_setup_font(language, config):
    """Setup and return font for given language configuration."""
    fonts = pd.read_excel(
        config['reporting']['configuration'], sheet_name='fonts',
    )
    fonts['Language'] = fonts['Language'].str.split(',')
    fonts = fonts.explode('Language')
    if language.replace(' (Auto-translation)', '') in fonts.Language.unique():
        fonts = fonts.loc[
            fonts['Language'] == language.replace(' (Auto-translation)', '')
        ].fillna('')
    else:
        fonts = fonts.loc[fonts['Language'] == 'default'].fillna('')
    fonts['File'] = fonts['File'].str.strip()
    main_font = fonts.File.values[0]
    for index, row in fonts.iterrows():
        if not os.path.exists(row['File']):
            context = f"Font '{row['File']}' has been configured for {language}, however this file could not be located."
            download_file(
                url=row['URL'],
                file=row['File'],
                context=context,
                extract_zip=True,
            )
    fm.fontManager.addfont(main_font)
    prop = fm.FontProperties(fname=main_font)
    fm.findfont(
        prop=prop, directory=main_font, rebuild_if_missing=True,
    )
    plt.rcParams['font.family'] = prop.get_name()
    font = fonts.Font.values[0]
    return font


def _checklist_policy_exists(policy):
    """Check if policy exists.

    If any policy name entered for a particular measure ('Yes'); otherwise, 'None identified'.
    """
    exists = any(~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']))
    return ['-', '✔'][exists]


def _checklist_policy_aligns(policy):
    """Check if policy aligns with healthy and sustainable cities principles.

    Yes: If policy details not entered under 'no' principles (qualifier!='No'; noting some policies aren't yes or no)

    No: If a policy exists with details entered under 'no' principles, without an aligned policy identified

    Mixed: If both 'yes' (and aligned) and 'no' principles identified
    """
    # policy_count = len(policy.query("""qualifier!='No'"""))
    exists = any(~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']))
    # aligns = any(policy.query("""Policy.astype('str') not in ['No','','nan','NaN'] and qualifier!='No' and `Measurable target`!='No'""")['Policy'])
    # all_aligns = policy.query("""Policy.astype('str') not in ['No','','nan','NaN'] and qualifier!='No'""")['Policy']
    # aligns_count = len(all_aligns)
    # aligns = any(all_aligns)
    aligns = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and qualifier!='No' and `Evidence-informed threshold`.astype('str') not in ['No']""",
        )['Policy'],
    )
    does_not_align = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and qualifier=='No'""",
        )['Policy'],
    )
    # if aligns_count == policy_count:
    #     return '✔'
    if aligns and does_not_align:
        return '✔/✘'
    elif aligns:
        return '✔'
        # return f'✔ ({aligns_count}/{policy_count})'
    elif exists and (not aligns or does_not_align):
        return '✘'
    else:
        return '-'


def _checklist_policy_measurable(policy):
    """Check if policy has a measurable target."""
    exists = any(~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']))
    measurable = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Measurable target`.astype('str') not in ['No','','nan','NaN','Unclear']""",
        )['Policy'],
    )
    not_measurable = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Measurable target`.astype('str') in ['No','','nan','NaN','Unclear']""",
        )['Policy'],
    )
    if measurable and not_measurable:
        return '✔'
        # return '✔+✘'
    elif measurable:
        return '✔'
    elif exists and (not measurable or not_measurable):
        return '✘'
    else:
        return '-'


def _checklist_policy_evidence(policy):
    """Check if policy has an evidence informed threshold target."""
    exists = any(~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']))
    evidence = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Evidence-informed threshold`.astype('str') not in ['No','','nan','NaN']""",
        )['Policy'],
    )
    not_evidence = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Evidence-informed threshold`.astype('str') in ['No','','nan','NaN']""",
        )['Policy'],
    )
    if evidence and not_evidence:
        return '✔+✘'
    elif evidence:
        return '✔'
    elif exists and (not evidence or not_evidence):
        return '✘'
    else:
        return '-'


def policy_data_setup(xlsx: str, policies: dict):
    """Returns a dictionary of policy data."""
    from policy_report import get_policy_checklist

    # get list of all valid measures
    measures = [
        measure
        for categories in [
            policies['Checklist'][x] for x in policies['Checklist']
        ]
        for measure in categories
    ]
    # read in completed policy checklist
    audit = get_policy_checklist(xlsx)
    if audit is not None:
        # restrict policy checklist to valid measures
        audit = audit.loc[audit['Measures'].isin(measures)]
    else:
        print('Policy checklist evaluation will be skipped.')
        return None
    # initialise and populate checklist for specific themes
    checklist = {}
    for topic in policies['Checklist']:
        checklist[topic] = pd.DataFrame.from_dict(
            policies['Checklist'][topic],
        ).set_index(0)
        checklist[topic].index.name = 'Measure'
        # initialise criteria columns
        checklist[topic]['exists'] = '-'
        checklist[topic]['aligns'] = '-'
        checklist[topic]['measurable'] = '-'
        for measure in checklist[topic].index:
            if audit is not None:
                policy_measure = audit.query(f'Measures == "{measure}"')
                # evaluate indicators against criteria
                checklist[topic].loc[
                    measure, 'exists',
                ] = _checklist_policy_exists(policy_measure)
                checklist[topic].loc[
                    measure, 'aligns',
                ] = _checklist_policy_aligns(policy_measure)
                checklist[topic].loc[
                    measure, 'measurable',
                ] = _checklist_policy_measurable(policy_measure)
                # checklist[topic].loc[measure,'evidence'] = _checklist_policy_evidence(policy_measure)
            else:
                checklist[topic].loc[
                    measure, ['exists', 'aligns', 'measurable'],
                ] = '-'
    return checklist


def get_policy_presence_quality_score_dictionary(xlsx):
    """
    Returns a dictionary with scores for presence and quality of policy data.

    Only unique measures are evaluated (ie. if a measure is reported multiple themes, only its highest rating instance is evaluated).

    'Transport and planning combined in one government department' is excluded from quality rating.

    Quality scores for 'aligns':
    - '✔': 1
    - '✔/✘': -0.5
    - '✘': -1

    Quality scores for 'measurable':
    - no relevant policy = 0;
    - policy but 'no' measurable target = 1;
    - policy with 'yes' measurable target = 2.

    Final quality score for measures is the product of the 'align score' and 'measurable score'.

    Overall quality score is the sum of the quality scores for each measure.
    """
    from policy_report import get_policy_checklist

    # read in completed policy checklist
    audit = get_policy_checklist(xlsx)
    if audit is None:
        print(
            f'Policy document does not appear to have been completed and evaluation will be skipped.  Check the configured document {xlsx} is complete to proceed.',
        )
        return None
    # initialise and populate checklist for specific themes
    checklist = pd.DataFrame.from_dict(audit['Measures'].unique()).set_index(0)
    checklist.index.name = 'Measure'
    # initialise criteria columns
    checklist['exists'] = '-'
    checklist['aligns'] = '-'
    checklist['measurable'] = '-'
    for measure in checklist.index:
        if audit is not None:
            policy_measure = audit.query(f'Measures == "{measure}"')
            # evaluate indicators against criteria
            checklist.loc[measure, 'exists'] = _checklist_policy_exists(
                policy_measure,
            )
            checklist.loc[measure, 'aligns'] = _checklist_policy_aligns(
                policy_measure,
            )
            checklist.loc[
                measure, 'measurable',
            ] = _checklist_policy_measurable(policy_measure)
            # checklist.loc[measure,'evidence'] = _checklist_policy_evidence(policy_measure)
        else:
            checklist.loc[measure, ['exists', 'aligns', 'measurable']] = '-'
    checklist['align_score'] = checklist['aligns'].map(
        {'✔': 1, '✔/✘': -0.5, '✘': -1},
    )
    checklist['measurable_score'] = checklist['measurable'].map(
        {'✔': 2, '✘': 1, '-': 0},
    )
    checklist['quality'] = (
        checklist['align_score'] * checklist['measurable_score']
    )
    policy_score = {}
    policy_score['presence'] = {
        'numerator': (checklist['exists'] == '✔').sum(),
        'denominator': len(checklist),
    }
    policy_score['quality'] = {
        'numerator': checklist.loc[
            ~(
                checklist.index
                == 'Transport and planning combined in one government department'
            ),
            'quality',
        ].sum(),
        'denominator': len(
            checklist.loc[
                ~(
                    checklist.index
                    == 'Transport and planning combined in one government department'
                )
            ],
        )
        * 2,
    }
    return policy_score


def evaluate_threshold_pct(
    df, indicator, relationship, reference, field='pop_est',
):
    """Evaluate whether a pandas series meets a threshold criteria (eg. '<' or '>'."""
    percentage = round(
        100
        * df.query(f'{indicator} {relationship} {reference}')[field].sum()
        / df[field].sum(),
        1,
    )
    return percentage


def generate_resources(
    r, gdf_city, gdf_grid, phrases, indicators, policy_review, language, cmap,
):
    """
    The function prepares a series of image resources required for the global indicator score cards.

    The city_path string variable is returned, where generated resources will be stored upon successful execution.
    """
    config = r.config
    figure_path = f'{config["region_dir"]}/figures'
    locale = phrases['locale']
    city_stats = r.get_city_stats(phrases=phrases)
    if not os.path.exists(figure_path):
        os.mkdir(figure_path)
    # Access profile
    file = f'{figure_path}/access_profile_{language}.png'
    if os.path.exists(file):
        print(
            f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
        )
    else:
        r.access_profile(
            city_stats=city_stats,
            title=phrases['Population % with access within 500m to...'],
            cmap=cmap,
            phrases=phrases,
            path=file,
        )
        print(f'  figures/access_profile_{language}.png')
    # Spatial distribution maps
    spatial_maps = compile_spatial_map_info(
        indicators['report']['spatial_distribution_figures'],
        gdf_city,
        phrases,
        locale,
        language,
    )
    ## constrain extreme outlying walkability for representation
    gdf_grid['all_cities_walkability'] = gdf_grid[
        'all_cities_walkability'
    ].apply(lambda x: -6 if x < -6 else (6 if x > 6 else x))
    for f in spatial_maps:
        labels = {'': spatial_maps[f]['label'], '_no_label': ''}
        for label in labels:
            file = f'{figure_path}/{spatial_maps[f]["outfile"]}'
            path = os.path.splitext(file)
            file = f'{path[0]}{label}{path[1]}'
            if os.path.exists(file):
                print(
                    f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
                )
            else:
                spatial_dist_map(
                    gdf_grid,
                    column=f,
                    range=spatial_maps[f]['range'],
                    label=labels[label],
                    tick_labels=spatial_maps[f]['tick_labels'],
                    cmap=cmap,
                    path=file,
                    phrases=phrases,
                    locale=locale,
                )
                print(f"  {file.replace(config['region_dir'],'')}")
    # Threshold maps
    for scenario in indicators['report']['thresholds']:
        labels = {
            '': f"{phrases[indicators['report']['thresholds'][scenario]['title']]} ({phrases['density_units']})",
            '_no_label': '',
        }
        for label in labels:
            file = f"{figure_path}/{indicators['report']['thresholds'][scenario]['field']}_{language}.jpg"
            path = os.path.splitext(file)
            file = f'{path[0]}{label}{path[1]}'
            if os.path.exists(file):
                print(
                    f"  {file.replace(config['region_dir'],'')} (exists; delete or rename to re-generate)",
                )
            else:
                threshold_map(
                    gdf_grid,
                    column=indicators['report']['thresholds'][scenario][
                        'field'
                    ],
                    scale=indicators['report']['thresholds'][scenario][
                        'scale'
                    ],
                    comparison=indicators['report']['thresholds'][scenario][
                        'criteria'
                    ],
                    label=labels[label],
                    cmap=cmap,
                    path=file,
                    phrases=phrases,
                    locale=locale,
                )
                print(f"  {file.replace(config['region_dir'],'')}")
    return figure_path


def fpdf2_mm_scale(mm):
    """Returns a width double that of the conversion of mm to inches.

    This has been found, via trial and error, to be useful when preparing images for display in generated PDFs using fpdf2.
    """
    return 2 * mm / 25.4


def _pct(value, locale, length='short'):
    """Formats a percentage sign according to a given locale."""
    return format_unit(value, 'percent', locale=locale, length=length)


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
        spatial_maps[i]['label'] = spatial_maps[i]['label'].format(**phrases)
        spatial_maps[i]['outfile'] = spatial_maps[i]['outfile'].format(
            **locals(),
        )
        if spatial_maps[i]['tick_labels'] is not None:
            spatial_maps[i]['tick_labels'] = [
                x.format(**phrases) for x in spatial_maps[i]['tick_labels']
            ]
        if i.startswith('pct_'):
            city_summary_percent = _pct(
                fnum(gdf_city[f'pop_{i}'].fillna(0)[0], '0.0', locale), locale,
            )
            phrases[spatial_maps[i]['label']] = phrases[
                spatial_maps[i]['label']
            ].format(percent=city_summary_percent, **phrases)
            spatial_maps[i]['label'] = phrases[spatial_maps[i]['label']]
    if gdf_city['pop_pct_access_500m_pt_gtfs_freq_20_score'][
        0
    ] is None or pd.isna(
        gdf_city['pop_pct_access_500m_pt_gtfs_freq_20_score'][0],
    ):
        city_summary_percent = _pct(
            fnum(
                gdf_city['pop_pct_access_500m_pt_any_score'].fillna(0)[0],
                '0.0',
                locale,
            ),
            locale,
        )
        phrases[
            'Percentage of population with access to public transport'
        ] = phrases[
            'Percentage of population with access to public transport'
        ].format(
            percent=city_summary_percent, **phrases,
        )
        spatial_maps['pct_access_500m_pt_any_score'] = spatial_maps.pop(
            'pct_access_500m_pt_gtfs_freq_20_score',
        )
        spatial_maps['pct_access_500m_pt_any_score']['label'] = phrases[
            'Percentage of population with access to public transport'
        ]
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
    **kwargs,
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
        **kwargs,
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
        if len(tick_labels) == len(range):
            cax.xaxis.set_major_locator(ticker.FixedLocator(range))
            cax.set_xticklabels(tick_labels)
        else:
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
    if comparison is not None:
        cax.plot(
            comparison,
            0.7,
            marker='v',
            color='black',
            markersize=9,
            zorder=10,
            clip_on=False,
        )
        cax.text(
            comparison,
            1.5,
            phrases['target threshold'],
            ha='center',
            va='center',
            size=textsize,
        )
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
    if comparison is not None:
        ax_ = ax.twiny()
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
    config, template, font=None, language='English', phrases=None,
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
    fonts = pd.read_excel(
        config['reporting']['configuration'], sheet_name='fonts',
    )
    fonts['Language'] = fonts['Language'].str.split(',')
    fonts = fonts.explode('Language')
    right_to_left = fonts.query('Align=="Right"')['Language'].unique()
    conditional_size = fonts.loc[~fonts['Conditional size'].isna()]
    document_pages = elements.page.unique()
    # Conditional formatting for specific languages to improve pagination
    if language in right_to_left:
        elements['align'] = (
            elements['align'].replace('L', 'R').replace('J', 'R')
        )
    if language in conditional_size['Language'].unique().tolist():
        for condition in conditional_size.loc[
            conditional_size['Language'] == language, 'Conditional size',
        ].unique():
            tuple = str(condition).split(',')
            if len(tuple) == 2:
                expression = f"((elements['type'] == 'T')|(elements['type'] == 'W')) & (elements['size'] {tuple[0]})"
                elements.loc[eval(expression), 'size'] = elements.loc[
                    eval(expression), 'size',
                ] + eval(tuple[1])
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
                del elements[i][plane]
    pages = format_pages(document_pages, elements, phrases)
    return pages


def format_pages(document_pages, elements, phrases):
    """Format page with phrases."""
    pages = {}
    for page in document_pages:
        pages[f'{page}'] = [x for x in elements if x['page'] == page]
        for i, item in enumerate(pages[f'{page}']):
            if item['name'] in phrases:
                try:
                    pages[f'{page}'][i]['text'] = phrases[item['name']].format(
                        **phrases,
                    )
                except Exception:
                    pages[f'{page}'][i]['text'] = phrases[item['name']]
    return pages


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


def prepare_pdf_fonts(pdf, report_configuration, report_language):
    """Prepare PDF fonts."""
    fonts = pd.read_excel(report_configuration, sheet_name='fonts')
    fonts['Language'] = fonts['Language'].str.split(',')
    fonts = fonts.explode('Language')
    fonts = (
        fonts.loc[
            fonts['Language'].isin(
                [
                    'default',
                    report_language.replace(' (Auto-translation)', ''),
                ],
            )
        ]
        .fillna('')
        .drop_duplicates()
    )
    for s in ['', 'b', 'i', 'bi']:
        for langue in ['default', report_language]:
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
    pdf.set_fallback_fonts(['dejavu'])
    pdf.set_text_shaping(True)
    return pdf


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
    r,
    phrases,
    indicators,
    policy_review,
    language='English',
    report_template='policy_spatial',
    font=None,
):
    """
    Format a PDF using the pyfpdf FPDF2 library, and drawing on definitions from a UTF-8 CSV file.

    Included in this function is the marking of a policy 'scorecard', with ticks, crosses, etc.
    """
    import re

    from ghsci import date

    pdf = generate_pdf(
        r, font, report_template, language, phrases, indicators, policy_review,
    )
    # Output report pdf
    filename = f"GOHSC {phrases['current_year']} - {phrases['title_series_line2'].capitalize()} - {phrases['city_name']} {phrases['country']} {phrases['year']} - {phrases['vernacular']}{phrases['filename_publication_check']}.pdf"
    # ensure filename doesn't inadvertently have multiple spaces
    filename = re.sub(r'\s+', ' ', filename)
    try:
        capture_result = save_pdf_layout(
            pdf, folder=r.config['region_dir'], filename=filename,
        )
    except OSError as Exception:
        if Exception.errno == 36:
            # handle filename too long error
            filename = f"GOHSC {phrases['current_year']}-{report_template}-{r.config['country_code']}-{phrases['city_name']}-{phrases['year']}-{phrases['language_code']}{phrases['filename_publication_check']}.pdf".replace(
                ' ', '',
            )
            capture_result = save_pdf_layout(
                pdf, folder=r.config['region_dir'], filename=filename,
            )
        else:
            raise Exception
    return capture_result


def _pdf_initialise_document(phrases, config):
    """Initialise PDF document."""
    pdf = FPDF(orientation='portrait', format='A4', unit='mm')
    pdf = prepare_pdf_fonts(
        pdf, config['reporting']['configuration'], config['pdf']['language'],
    )
    pdf.set_author(phrases['metadata_author'])
    pdf.set_title(f"{phrases['metadata_title1']} {phrases['metadata_title2']}")
    pdf.set_auto_page_break(False)
    return pdf


def get_policy_checklist_item(
    policy_review_setting, phrases, item='Levels of Government',
):
    """Get policy checklist items (e.g. 'Levels of Government' or 'Environmnetal disaster context')."""
    if policy_review_setting is None:
        return []
    levels = policy_review_setting[item].split('\n')
    levels = [
        phrases[level[0].strip()].strip()
        for level in [x.split(': ') for x in levels]
        if str(level[1]).strip()
        not in ['No', 'missing', 'nan', 'None', 'N/A', '']
    ]
    return levels


def _pdf_insert_cover_page(pdf, pages, phrases, r):
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['1'])
    _insert_report_image(template, r, phrases, 1)
    template.render()
    return pdf


def _pdf_insert_citation_page(pdf, pages, phrases, r):
    """Add and render PDF report citation page."""
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['2'])
    template['citations'] = phrases['citations']
    template['authors'] = template['authors'].format(**phrases)
    template['edited'] = template['edited'].format(**phrases)
    template['translation'] = template['translation'].format(**phrases)
    # template['author_names'] = phrases['author_names']
    if phrases['translation_names'] in [None, '']:
        template['translation'] = ''
        # template['translation_names'] = ''
    example = False
    if r.codename == 'example_ES_Las_Palmas_2023':
        template[
            'other_credits'
        ] = f"{phrases['example_report_only']}:\n\nhttps://healthysustainablecities.github.io/software/"
        example = True
    if (
        'policy' in r.config['pdf']['report_template']
        and r.config['pdf']['policy_review'] is not None
        and r.config['pdf']['policy_review_setting'] is not None
        and 'Date' in r.config['pdf']['policy_review_setting']
    ):
        date = r.config['pdf']['policy_review_setting']['Date']
        if str(date) in ['', 'nan', 'NaN', 'None']:
            date = ''
        else:
            date = f' ({date})'
        policy_review_credit = f"""{phrases['Policy review conducted by']}: {r.config['pdf']['policy_review_setting']['Person(s)']}{date}{['',' (example only)'][example]}"""
        template['citations'] = phrases['citations'].replace(
            '.org\n\n', f'.org\n\n{policy_review_credit}\n\n',
        )
        if r.config['pdf']['report_template'] == 'policy':
            template[
                'citations'
            ] = '{citation_series}: {study_citations}\n\n{policy_review_credit}'.format(
                policy_review_credit=policy_review_credit, **phrases,
            )
    template.render()
    return pdf


def _pdf_insert_introduction_page(pdf, pages, phrases, r):
    """Add and render PDF report introduction page."""
    pdf.add_page()
    template = FlexTemplate(pdf, elements=pages['3'])
    if r.config['pdf']['report_template'] == 'policy':
        template['introduction'] = f"{phrases['policy_intro']}".format(
            **phrases,
        )
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template['introduction'] = f"{phrases['policy_spatial_intro']}".format(
            **phrases,
        )
    elif r.config['pdf']['report_template'] == 'spatial':
        template['introduction'] = f"{phrases[f'spatial_intro']}".format(
            **phrases,
        )
    template = format_template_context(
        template, r, r.config['pdf']['language'], phrases,
    )
    if 'hero_image_2' in template:
        _insert_report_image(
            template, r, phrases, 2, alternate_text='hero_alt',
        )
    template.render()
    return pdf


def _pdf_insert_context_page(pdf, pages, phrases, r):
    """Add and render PDF report context page."""
    if 'spatial' in r.config['pdf']['report_template']:
        template = FlexTemplate(pdf, elements=pages['4'])
        pdf.add_page()
        basemap = r.config['reporting']['study_region_context_basemap']
        template['study_region_context'] = study_region_map(
            r.get_engine(),
            r.config,
            urban_shading=True,
            basemap=basemap,
            arrowcolor='black',
            scale_box=False,
            file_name=f'study_region_boundary_{basemap}',
        )
        if len(r.config['study_region_blurb']['layers']) == 1:
            key = list(r.config['study_region_blurb']['layers'].keys())[0]
            template[
                'study region legend patch a'
            ] = 'configuration/assets/study region legend patches_study region.svg'
            template['study region legend patch text a'] = phrases[
                'study region legend patch text c'
            ].format(source=r.config['study_region_blurb']['layers'][key])
            template['study region legend patch b'] = ''
            template['study region legend patch c'] = ''
            template['study region legend patch text b'] = ''
            template['study region legend patch text c'] = ''
        elif len(r.config['study_region_blurb']['layers']) == 2:
            template[
                'study region legend patch a'
            ] = 'configuration/assets/study region legend patches_administrative.svg'
            template[
                'study region legend patch b'
            ] = 'configuration/assets/study region legend patches_urban.svg'
            template[
                'study region legend patch c'
            ] = 'configuration/assets/study region legend patches_study region.svg'
            template['study region legend patch text a'] = phrases[
                'study region legend patch text a'
            ].format(
                source=r.config['study_region_blurb']['layers'][
                    'administrative_boundary'
                ],
            )
            template['study region legend patch text b'] = phrases[
                'study region legend patch text b'
            ].format(
                source=r.config['study_region_blurb']['layers'][
                    'urban_boundary'
                ],
            )
            template['study region legend patch text c'] = phrases[
                'study region legend patch text c'
            ].format(source=phrases['intersection'])
        # template = format_template_context(
        #     template, r, r.config['pdf']['language'],
        # )
        # if 'study_region_context_caption' in template:
        #     template['study_region_context_caption'] = phrases[
        #         'study_region_context_caption'
        #     ].format(number=1, **phrases)
        # template['city_text'] = phrases['summary']
        template.render()
    return pdf


def _pdf_insert_policy_scoring_page(pdf, pages, phrases, r):
    """Add and render PDF report integrated city planning policy page."""
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['4'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['5'])
    else:
        return pdf
    pdf.add_page()
    if r.config['pdf']['policy_review'] is not None:
        ## Policy ratings
        # template[
        #     'presence_rating'
        # ] = f"{r.config['pdf']['figure_path']}/policy_presence_rating_{r.config['pdf']['language']}.jpg"
        # template[
        #     'quality_rating'
        # ] = f"{r.config['pdf']['figure_path']}/policy_checklist_rating_{r.config['pdf']['language']}.jpg"
        # phrases['policy_checklist_levels'] = ', '.join(
        #     get_policy_checklist_levels_of_government(
        #         r.config['pdf']['policy_review_setting'],
        #         phrases
        #     ),
        # )
        # phrases['levels_of_government'] = phrases[
        #     'levels_of_government'
        # ].format(**phrases)
        policy_rating = get_policy_presence_quality_score_dictionary(
            r.config['policy_review'],
        )
        if policy_rating is not None:
            template['presence_rating'] = template['presence_rating'].format(
                presence=int(policy_rating['presence']['numerator']),
                n=int(policy_rating['presence']['denominator']),
                percent=_pct(
                    fnum(
                        100
                        * policy_rating['presence']['numerator']
                        / policy_rating['presence']['denominator'],
                        '0.0',
                        r.config['pdf']['locale'],
                    ),
                    r.config['pdf']['locale'],
                ),
            )
            template['quality_rating'] = template['quality_rating'].format(
                quality=int(policy_rating['quality']['numerator']),
                n=int(policy_rating['quality']['denominator']),
                percent=_pct(
                    fnum(
                        100
                        * policy_rating['quality']['numerator']
                        / policy_rating['quality']['denominator'],
                        '0.0',
                        r.config['pdf']['locale'],
                    ),
                    r.config['pdf']['locale'],
                ),
            )
    template.render()
    return pdf


def _pdf_insert_25_city_study_box(pdf, pages, phrases, r):
    if r.config['pdf']['report_template'] == 'spatial':
        # display 25 cities comparison blurb
        template = FlexTemplate(pdf, elements=pages['5'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['6'])
    else:
        return pdf
    pdf.add_page()
    template.render()
    return pdf


def _pdf_insert_policy_integrated_planning_page(pdf, pages, phrases, r):
    """Add and render PDF report integrated city planning policy page."""
    if r.config['pdf']['report_template'] == 'policy':
        # display 25 cities comparison blurb
        template = FlexTemplate(pdf, elements=pages['5'])
        pdf.add_page()
        template.render()
        template = FlexTemplate(pdf, elements=pages['6'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['7'])
    else:
        return pdf
    pdf.add_page()
    ## Walkable neighbourhood policy checklist
    template = format_template_policy_checklist(
        template,
        phrases=phrases,
        policies=r.config['pdf']['policy_review'],
        checklist=1,
        title=False,
    )
    if 'hero_image_2' in template:
        _insert_report_image(
            template, r, phrases, 2, alternate_text='hero_alt',
        )
    # if os.path.exists(
    #     f'{r.config["folder_path"]}/process/configuration/assets/{phrases["Image 2 file"]}',
    # ):
    #     template[
    #         'hero_image_2'
    #     ] = f'{r.config["folder_path"]}/process/configuration/assets/{phrases["Image 2 file"]}'
    #     template['hero_alt_2'] = ''
    #     template['Image 2 credit'] = phrases['Image 2 credit']
    template.render()
    return pdf


def _pdf_insert_accessibility_policy(pdf, pages, phrases, r):
    """Add and render PDF report accessibility policy page."""
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['7'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['8'])
    else:
        return pdf
    from ghsci import policies

    pdf.add_page()
    if r.config['pdf']['policy_review'] is not None:
        template = format_template_policy_checklist(
            template,
            phrases=phrases,
            policies=r.config['pdf']['policy_review'],
            checklist=2,
            title=True,
        )
    else:
        checklist = 2
        policy_checklist = list(policies['Checklist'].keys())[checklist - 1]
        template[f'policy_checklist{checklist}_title'] = phrases[
            policy_checklist
        ]
    template.render()
    return pdf


def _pdf_insert_accessibility_spatial(pdf, pages, phrases, r):
    """Add and render PDF report accessibility page."""
    if r.config['pdf']['report_template'] == 'spatial':
        for page in [6, 7]:
            template = FlexTemplate(pdf, elements=pages[f'{page}'])
            template = _pdf_add_spatial_accessibility_plots(
                template, r, phrases,
            )
            pdf.add_page()
            template.render()
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        for page in [9, 10]:
            template = FlexTemplate(pdf, elements=pages[f'{page}'])
            template = _pdf_add_spatial_accessibility_plots(
                template, r, phrases,
            )
            pdf.add_page()
            template.render()
    return pdf


def _pdf_insert_thresholds_page(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'spatial':
        for page in [8, 9]:
            template = FlexTemplate(pdf, elements=pages[f'{page}'])
            template = _pdf_add_threshold_plots(template, r, phrases)
            pdf.add_page()
            template.render()
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['11'])
        pdf.add_page()
        if 'hero_image_3' in template:
            _insert_report_image(template, r, phrases, 3)
        template.render()
        for page in [12, 13]:
            template = FlexTemplate(pdf, elements=pages[f'{page}'])
            template = _pdf_add_threshold_plots(template, r, phrases)
            pdf.add_page()
            template.render()
    return pdf


def _pdf_insert_transport_policy_page(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['8'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['14'])
    else:
        return pdf
    if r.config['pdf']['policy_review'] is not None:
        template = format_template_policy_checklist(
            template,
            phrases=phrases,
            policies=r.config['pdf']['policy_review'],
            checklist=3,
            title=False,
        )
    pdf.add_page()
    template.render()
    return pdf


def _pdf_insert_transport_spatial_page(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'spatial':
        template = FlexTemplate(pdf, elements=pages['10'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['15'])
    else:
        return pdf
    results = r.config['pdf']['indicators_region']
    regular_pt = results['pop_pct_access_500m_pt_gtfs_freq_20_score'][0]
    if regular_pt is None or pd.isna(
        results['pop_pct_access_500m_pt_gtfs_freq_20_score'][0],
    ):
        pt_label = phrases[
            'Percentage of population with access to public transport'
        ]
    else:
        pt_label = phrases[
            'Percentage of population with access to public transport with service frequency of 20 minutes or less'
        ]
    template[
        'pct_access_500m_pt.jpg'
    ] = f"{r.config['pdf']['figure_path']}/pct_access_500m_pt_{r.config['pdf']['language']}_no_label.jpg"
    template['pct_access_500m_pt_label'] = pt_label.replace(
        '\n', ' ',
    ).replace('  ', ' ')
    pdf.add_page()
    template.render()
    return pdf


def _pdf_insert_open_space_policy_page(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['9'])
    elif (
        'policy' in r.config['pdf']['report_template']
        and r.config['pdf']['policy_review'] is not None
    ):
        template = FlexTemplate(pdf, elements=pages['16'])
    else:
        return pdf
    template = format_template_policy_checklist(
        template,
        phrases=phrases,
        policies=r.config['pdf']['policy_review'],
        checklist=4,
        title=False,
    )
    pdf.add_page()
    if 'hero_image_4' in template:
        _insert_report_image(template, r, phrases, 4)
    template.render()
    return pdf


def _pdf_insert_open_space_spatial_page(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'spatial':
        template = FlexTemplate(pdf, elements=pages['11'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['17'])
    else:
        return pdf
    pdf.add_page()
    template[
        'pct_access_500m_public_open_space_large_score'
    ] = f"{r.config['pdf']['figure_path']}/pct_access_500m_public_open_space_large_score_{r.config['pdf']['language']}_no_label.jpg"
    pos_label = (
        phrases[
            'Percentage of population with access to public open space of area 1.5 hectares or larger'
        ]
        .replace('\n', ' ')
        .replace('  ', ' ')
    )
    template['pct_access_500m_public_open_space_large_score_label'] = pos_label
    template.render()
    return pdf


def _pdf_insert_nature_based_solutions(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['10'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['18'])
    else:
        return pdf
    # Set up last page
    if (
        'policy' in r.config['pdf']['report_template']
        and r.config['pdf']['policy_review'] is not None
    ):
        template = format_template_policy_checklist(
            template,
            phrases=phrases,
            policies=r.config['pdf']['policy_review'],
            checklist=5,
            title=False,
        )
    pdf.add_page()
    template.render()
    return pdf


def _pdf_insert_climate_change_risk_reduction(pdf, pages, phrases, r):
    """Add and render PDF report thresholds page."""
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['11'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['19'])
    else:
        return pdf
    # Set up last page
    if (
        'policy' in r.config['pdf']['report_template']
        and r.config['pdf']['policy_review'] is not None
    ):
        template = format_template_policy_checklist(
            template,
            phrases=phrases,
            policies=r.config['pdf']['policy_review'],
            checklist=6,
            title=False,
        )
    pdf.add_page()
    if 'hero_image_4' in template:
        _insert_report_image(template, r, phrases, 4)
    template.render()
    return pdf


def _pdf_insert_back_page(pdf, pages, phrases, r):
    # Set up last page
    if r.config['pdf']['report_template'] == 'policy':
        template = FlexTemplate(pdf, elements=pages['12'])
    elif r.config['pdf']['report_template'] == 'spatial':
        template = FlexTemplate(pdf, elements=pages['12'])
    elif r.config['pdf']['report_template'] == 'policy_spatial':
        template = FlexTemplate(pdf, elements=pages['20'])
    else:
        return pdf
    pdf.add_page()
    template.render()
    return pdf


def _insert_report_image(
    template, r, phrases, number: int, alternate_text=None,
):
    if (
        os.path.exists(
            f'{r.config["folder_path"]}/process/configuration/assets/{phrases[f"Image {number} file"]}',
        )
        and f'hero_image_{number}' in template
    ):
        template[
            f'hero_image_{number}'
        ] = f'{r.config["folder_path"]}/process/configuration/assets/{phrases[f"Image {number} file"]}'
        if alternate_text is None:
            template[f'hero_alt_{number}'] = ''
        else:
            template[alternate_text] = ''
        template[f'Image {number} credit'] = phrases[f'Image {number} credit']


def format_template_policy_checklist(
    template, phrases, policies: dict, checklist: int, title=False,
):
    """Format report template policy checklist."""
    if policies is None:
        print('  No policy review data available. Skipping policy checklist.')
        return template
    policy_checklist = list(policies.keys())[checklist - 1]
    if title:
        template[f'policy_checklist{checklist}_title'] = phrases[
            policy_checklist
        ]
    template['policy_checklist_header1'] = phrases['Policy identified']
    template['policy_checklist_header2'] = phrases[
        'Aligns with healthy cities principles'
    ]
    template['policy_checklist_header3'] = phrases['Measurable target']
    # template['policy_checklist_header4'] = phrases['Evidence-informed threshold']
    for i, policy in enumerate(policies[policy_checklist].index):
        row = i + 1
        template[f'policy_checklist{checklist}_text{row}'] = phrases[policy]
        for j, item in enumerate(
            [x for x in policies[policy_checklist].loc[policy]],
        ):
            col = j + 1
            template[
                f'policy_checklist{checklist}_text{row}_response{col}'
            ] = item
    return template


def format_template_context(template, r, language, phrases):
    """Format report template context."""
    context = r.config['reporting']['languages'][language]['context']
    keys = [
        ''.join(x)
        for x in r.config['reporting']['languages'][language]['context']
    ]
    context_list = [
        (k, d[k][0]['summary'] if d[k][0]['summary'] is not None else '')
        for k, d in zip(keys, context)
    ]

    def update_value_if_key_in_template(
        key, value, template, phrases, skip=False,
    ):
        """Update item tuple if in template."""
        if key in template:
            if skip:
                template[key] = ''
                template[f'{key} blurb'] = ''
                return template
            else:
                template[key] = phrases[key].format(**phrases)
                if value.strip() != '':
                    template[f'{key} blurb'] = value
                else:
                    try:
                        template[f'{key} blurb'] = phrases[
                            f'{key} blurb'
                        ].format(**phrases)
                    except Exception:
                        template[f'{key} blurb'] = ''
                return template
        else:
            return template

    for heading, blurb in context_list:
        template = update_value_if_key_in_template(
            heading, blurb, template, phrases,
        )
        if 'policy' in r.config['pdf']['report_template']:
            if heading == 'Levels of Government':
                # fill in blurb based on policy checklist
                if blurb.strip() in ['', 'None specified']:
                    phrases['policy_checklist_levels'] = ', '.join(
                        get_policy_checklist_item(
                            r.config['pdf']['policy_review_setting'],
                            phrases,
                            item=heading,
                        ),
                    )
                    if phrases['policy_checklist_levels'] != '':
                        template[f'{heading} blurb'] = phrases[
                            f'{heading} blurb'
                        ].format(**phrases)
                    else:
                        template = update_value_if_key_in_template(
                            heading, blurb, template, phrases, skip=True,
                        )
            if heading == 'Environmental disaster context':
                hazards = get_policy_checklist_item(
                    r.config['pdf']['policy_review_setting'],
                    phrases,
                    item=heading,
                )
                if len(hazards) > 1:
                    phrases['policy_checklist_hazards'] = ', '.join(
                        get_policy_checklist_item(
                            r.config['pdf']['policy_review_setting'],
                            phrases,
                            item=heading,
                        ),
                    )
                template[f'{heading} blurb'] = phrases[
                    f'{heading} blurb'
                ].format(**phrases)
    return template


def _pdf_add_spatial_accessibility_plots(template, r, phrases):
    ## Walkability plot
    if 'all_cities_walkability' in template:
        template[
            'all_cities_walkability'
        ] = f"{r.config['pdf']['figure_path']}/all_cities_walkability_{r.config['pdf']['language']}_no_label.jpg"
    if 'walkability_below_median_pct' in template:
        template['walkability_below_median_pct'] = phrases[
            'walkability_below_median_pct'
        ].format(
            percent=_pct(
                fnum(
                    r.config['pdf']['indicators']['report']['walkability'][
                        'walkability_below_median_pct'
                    ],
                    '0.0',
                    r.config['pdf']['locale'],
                ),
                r.config['pdf']['locale'],
            ),
            city_name=phrases['city_name'],
        )
    if 'access_profile' in template:
        # Access profile plot
        template[
            'access_profile'
        ] = f"{r.config['pdf']['figure_path']}/access_profile_{r.config['pdf']['language']}.png"
    return template


def _pdf_add_threshold_plots(template, r, phrases):
    for scenario in r.config['pdf']['indicators']['report']['thresholds']:
        if scenario in template:
            plot = r.config['pdf']['indicators']['report']['thresholds'][
                scenario
            ]['field']
            template[
                plot
            ] = f"{r.config['pdf']['figure_path']}/{plot}_{r.config['pdf']['language']}_no_label.jpg"
            template[scenario] = phrases[f'optimal_range - {scenario}'].format(
                percent=_pct(
                    fnum(
                        r.config['pdf']['indicators']['report']['thresholds'][
                            scenario
                        ]['pct'],
                        '0.0',
                        r.config['pdf']['locale'],
                    ),
                    r.config['pdf']['locale'],
                ),
                n=fnum(
                    r.config['pdf']['indicators']['report']['thresholds'][
                        scenario
                    ]['criteria'],
                    '#,000',
                    r.config['pdf']['locale'],
                ),
                per_unit=phrases['density_units'],
                city_name=phrases['city_name'],
            )
    for percentage in [0, 20, 40, 60, 80, 100]:
        if f'pct_{percentage}' in template:
            template[f'pct_{percentage}'] = _pct(
                fnum(percentage, '0', r.config['pdf']['locale']),
                r.config['pdf']['locale'],
            )
    return template


def generate_pdf(
    r, font, report_template, language, phrases, indicators, policy_review,
):
    """
    Generate a PDF based on a template for web distribution.

    This template includes reporting on both policy and spatial indicators.
    """
    from policy_report import get_policy_setting

    r.config['pdf'] = {}
    r.config['pdf']['font'] = font
    r.config['pdf']['language'] = language
    r.config['pdf']['locale'] = phrases['locale']
    r.config['pdf']['report_template'] = report_template
    r.config['pdf']['figure_path'] = f"{r.config['region_dir']}/figures"
    r.config['pdf']['indicators'] = indicators
    r.config['pdf']['policy_review'] = policy_review
    r.config['pdf']['policy_review_setting'] = get_policy_setting(
        r.config['policy_review'],
    )
    r.config['pdf']['indicators_region'] = r.get_df('indicators_region')

    if 'policy' in r.config['pdf']['report_template']:
        if r.config['pdf']['policy_review'] is None:
            phrases[
                'disclaimer'
            ] = f"{phrases['disclaimer']} {phrases['policy checklist incomplete warning']}"
            print(
                '\n  No policy review data available.\n  Policy checklists will be incomplete until this has been successfully completed and configured.\n  For more information, see https://healthysustainablecities.github.io/software/#Policy-checklist\n',
            )
        if 'spatial' in r.config['pdf']['report_template']:
            phrases['title_series_line2'] = phrases[
                'policy and spatial indicators'
            ]
        else:
            phrases['title_series_line2'] = phrases['policy indicators']
    elif r.config['pdf']['report_template'] == 'spatial':
        phrases['title_series_line2'] = phrases['spatial indicators']
    pages = pdf_template_setup(
        r.config, report_template, font, language, phrases,
    )
    pdf = _pdf_initialise_document(phrases, r.config)
    pdf = _pdf_insert_cover_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_citation_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_introduction_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_context_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_policy_scoring_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_25_city_study_box(pdf, pages, phrases, r)
    pdf = _pdf_insert_policy_integrated_planning_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_accessibility_policy(pdf, pages, phrases, r)
    pdf = _pdf_insert_accessibility_spatial(pdf, pages, phrases, r)
    pdf = _pdf_insert_thresholds_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_transport_policy_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_transport_spatial_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_open_space_policy_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_open_space_spatial_page(pdf, pages, phrases, r)
    pdf = _pdf_insert_nature_based_solutions(pdf, pages, phrases, r)
    pdf = _pdf_insert_climate_change_risk_reduction(pdf, pages, phrases, r)
    pdf = _pdf_insert_back_page(pdf, pages, phrases, r)
    return pdf


def plot_choropleth_map(
    r,
    field: str = 'local_walkability',
    layer: str = None,
    layer_id: str = 'grid_id',
    title: str = '',
    auto_alias: bool = True,
    aliases: list = None,
    **args,
):
    """Given a region, field, layer and layer id, plot an interactive map."""
    from ghsci import dictionary

    if layer is None:
        layer = r.config['grid_summary']
    columns = [layer_id, field]
    if auto_alias:
        indicator_dictionary = dictionary['Description'].to_dict()
        try:
            aliases = [
                layer_id,
                indicator_dictionary[field.replace('pct', 'pop_pct')],
            ]
        except KeyError:
            print(
                'Attempted to use indicator dictionary for choropleth tooltip alias but did not succeed; using column names instead.',
            )
            aliases = columns
    elif aliases is None:
        aliases = columns

    geojson = r.get_geojson(
        f'(SELECT {layer_id},{field},geom FROM {layer}) as sql',
        include_columns=columns,
    )
    df = r.get_df(layer, columns=columns)
    map = choropleth_map(
        geojson=geojson,
        df=df,
        boundary_centroid=tuple(r.get_centroid()),
        key_on=layer_id,
        fields=columns,
        title=title,
        aliases=aliases,
        **args,
    )
    return map


def choropleth_map(
    geojson: json,
    df: pd.DataFrame,
    key_on: str,
    fields: list,
    boundary_centroid: tuple,
    title: str,
    aliases: list,
    line_opacity: float = 0.1,
    fill_color: str = 'YlGn',
    fill_opacity: float = 0.7,
    attribution: str = 'Global Healthy and Sustainable City Indicators Collaboration',
    **args,
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
        fill_color=fill_color,
        fill_opacity=fill_opacity,
        line_opacity=0.1,
        legend_name=title,
        **args,
    ).add_to(m)
    folium.features.GeoJsonTooltip(
        fields=fields,
        aliases=aliases,
        labels=True,
        sticky=True,
        localize=True,
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
    facecolor='#fbd8da',
    edgecolor='#fbd8da',
    basemap='satellite',
    urban_shading=True,
    arrowcolor='black',
    scale_box=False,
    file_name='study_region_map',
    additional_layers=None,
    additional_attribution=None,
):
    """Plot study region boundary."""
    import cartopy.crs as ccrs
    import cartopy.io.ogc_clients as ogcc
    import matplotlib.patheffects as path_effects
    from matplotlib.transforms import Bbox
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
        # ogcc.METERS_PER_UNIT['urn:ogc:def:crs:EPSG:6.3:3857'] = 1
        # ogcc._URN_TO_CRS[
        #     'urn:ogc:def:crs:EPSG:6.3:3857'
        # ] = ccrs.GOOGLE_MERCATOR
        # optionally add additional urban information
        if urban_shading:
            urban = gpd.GeoDataFrame.from_postgis(
                'SELECT * FROM urban_region', engine, geom_col='geom',
            ).to_crs(epsg=3857)
            urban.plot(
                ax=ax, color=facecolor, label='Urban centre (GHS)', alpha=0.4,
            )
            city = gpd.GeoDataFrame.from_postgis(
                'SELECT * FROM study_region_boundary', engine, geom_col='geom',
            ).to_crs(epsg=3857)
            city.plot(
                ax=ax,
                label='Administrative boundary',
                facecolor='none',
                edgecolor=edgecolor,
                # alpha=0.4,
                lw=2,
            )
            # add study region boundary
            urban_study_region.plot(
                ax=ax,
                facecolor='none',
                edgecolor=edgecolor,
                hatch='///',
                label='Urban study region',
                # alpha=0.4,
                lw=0.5,
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
            basemap = get_basemap(basemap)
            ax.add_wms(
                basemap['tiles'], [basemap['layer']], cmap='Grays',
            )
            map_attribution = f'Study region boundary (shaded region): {"; ".join(region_config["study_region_blurb"]["sources"])} | {basemap["attribution"]}'
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
            bbox_to_anchor=Bbox.from_bounds(0, 0, 0.15, 1),
            bbox_transform=ax.figure.transFigure,
        )
        # north arrow
        add_localised_north_arrow(
            ax,
            text=phrases['north arrow'],
            arrowprops=dict(facecolor=arrowcolor, width=4, headwidth=8),
            # xy=(0.98, 0.96),
            xy=(0.98, 1.08),
            textcolor=arrowcolor,
        )
        ax.set_axis_off()
        plt.subplots_adjust(
            left=0, bottom=0.1, right=1, top=0.9, wspace=0, hspace=0,
        )
        fig.savefig(filepath, dpi=dpi)
        fig.clf()
        print(f'  figures/{os.path.basename(filepath)}')
        return filepath


def get_basemap(basemap='satellite') -> dict:
    """Get basemap tile data and attribution, returning this in a dictionary."""
    if basemap == 'light':
        basemap = {
            'tiles': 'https://tiles.maps.eox.at/wms?service=wms&request=getcapabilities',
            'layer': 'streets',
            'attribution': 'Basemap: Streets overlay © OpenStreetMap Contributors, Rendering © EOX and MapServer, from https://tiles.maps.eox.at/ released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License',
        }
    elif basemap == 'osm':
        basemap = {
            'tiles': 'https://tiles.maps.eox.at/wms?service=wms&request=getcapabilities',
            'layer': 'osm',
            'attribution': 'Basemap: Streets overlay © OpenStreetMap Contributors, Rendering © EOX and MapServer, from https://tiles.maps.eox.at/ released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License',
        }
    else:
        # including, if basemap == 'satellite':
        basemap = {
            'tiles': 'https://tiles.maps.eox.at/wms?service=wms&request=getcapabilities',
            'layer': 's2cloudless-2020',
            'attribution': 'Basemap: Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2021) released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License',
        }
    return basemap


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
