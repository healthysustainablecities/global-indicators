#!/usr/bin/env python3
"""GHSCI graphical user interface; run and access at https://localhost:8080."""

import asyncio
import concurrent.futures
import multiprocessing as mp
import os.path
from datetime import datetime

import pandas as pd
from configure import configuration
from nicegui import Client, app, run, ui
from subprocesses import ghsci
from subprocesses.leaflet import leaflet
from subprocesses.local_file_picker import local_file_picker

ticks = ['✘', '✔']
# default_location = [14.509097, 154.832401]
default_location = [10, 154.8]
default_zoom = 2

regions = {}
region_list = []
selection = None


def get_region(codename) -> dict:
    # initialise region
    region = {
        'id': len(regions) + 1,
        'codename': codename,
        'config': None,
        'name': '',
        'study_region': 'Select or create a new study region',
        'configured': ticks[False],
        'analysed': ticks[False],
        'generated': ticks[False],
        'geojson': None,
        'failure': None,
    }
    # load region
    try:
        # print(codename)
        r = ghsci.Region(codename)
        if r is None:
            region['study_region'] = (
                f'{codename} (configuration not yet complete)'
            )
            region['failure'] = 'Region could not be loaded'
        elif r.config['data_check_failures'] is not None:
            region['study_region'] = (
                f'{codename} (configuration not yet complete)'
            )
            region['failure'] = r.config['data_check_failures']
            # print(
            # '- study region configuration file could not be loaded and requires completion in a text editor.',
            # )
        else:
            region['study_region'] = (
                f"{r.name}, {r.config['country']}, {r.config['year']}"
            )
            region['config'] = r.config
            region['configured'] = ticks[True]
            if 'urban_study_region' in r.tables and os.path.exists(r.config['region_dir']):
                if {'indicators_region', r.config['grid_summary']}.issubset(
                    r.tables,
                ):
                    region['analysed'] = ticks[True]
                    region['generated'] = ticks[
                        os.path.isfile(
                            f'{r.config["region_dir"]}/{r.codename}_indicators_region.csv',
                        )
                    ]
                    region['geojson'] = r.get_geojson(
                        'urban_study_region',
                        include_columns=['db'],
                    )
    except Exception as e:
        region['study_region'] = f'{codename} (configuration not yet complete)'
        region['failure'] = f'Region could not be loaded: {e}'
        # print(
        # '- study region configuration file could not be loaded and requires completion in a text editor.',
        # )
    finally:
        regions[codename] = region
        return region


def map_to_html(m, title, file=None, wrap_length=80) -> str:
    """Convert folium map to html and reformat for display."""
    import re

    # m.get_root().html.add_child(folium.Element(map_style_html_css))
    # html = m.get_root().render()
    html = m.get_root()._repr_html_()
    ## Wrap legend text if too long
    ## 65 chars seems to work well, conservatively)
    if len(title) > wrap_length:
        import textwrap

        legend_lines = textwrap.wrap(title, wrap_length)
        legend_length = len(title)
        n_lines = len(legend_lines)
        legend_height = 25 + 15 * n_lines
        old = f'''.attr(&quot;class&quot;, &quot;caption&quot;)\n        .attr(&quot;y&quot;, 21)\n        .text(&quot;{title}&quot;);'''
        new = '.append(&quot;tspan&quot;)'.join(
            [
                '''.attr(&quot;class&quot;,&quot;caption&quot;)
        .attr(&quot;x&quot;, 0)
        .attr(&quot;y&quot;, {pos})
        .text(&quot;{x}&quot;)
        '''.format(
                    x=x,
                    pos=21 + 15 * legend_lines.index(x),
                )
                for x in legend_lines
            ],
        )
        html = html.replace(old, new)
        html = html.replace(
            '.attr(&quot;height&quot;, 40);',
            f'.attr(&quot;height&quot;, {legend_height});',
        )

    # move legend to lower right corner
    html = html.replace(
        '''legend = L.control({position: &#x27;topright''',
        '''legend = L.control({position: &#x27;bottomright''',
    )

    # give legend white background
    old = '''&lt;/style&gt;'''
    new = '''    .legend.leaflet-control {
                            background-color: #FFF;
                        }
                 .leaflet-control-attribution.leaflet-control {
                            width: 72%;
                        }
                    &lt;/style&gt;'''
    html = html.replace(old, new)

    # reduce html export dimensions
    old = (
        '''style="position:relative;width:100%;height:0;padding-bottom:60%;'''
    )
    new = (
        '''style="position:relative;width:100%;height:0;padding-bottom:50%;'''
    )
    old = '''.foliumtooltip {'''
    new = '''.foliumtooltip {
        max-width: 15rem;
        width: max-content;
        white-space: normal;'''
    html = html.replace(old, new)
    # export or return
    if file is not None:
        # save map
        save_text_to_file(html, f'{file}.html')
    else:
        return html


def save_text_to_file(text, filename, encode='utf8'):
    if filename is not None:
        fid = open(filename, 'wb')
        fid.write(text.encode(encode))
        return filename.replace('/home/ghsci', '')
    else:
        return 'File could not be saved; skipping.'


def process_region(codename):
    get_region(codename)
    region_list.append(
        {
            'id': regions[codename]['id'],
            'codename': regions[codename]['codename'],
            'name': regions[codename]['name'],
            'study_region': regions[codename]['study_region'],
            'configured': regions[codename]['configured'],
            'analysed': regions[codename]['analysed'],
            'generated': regions[codename]['generated'],
            'failure': regions[codename]['failure'],
        },
    )
    if regions[codename]['geojson'] is not None:
        map.add_geojson(
            regions[codename]['geojson'],
            remove=False,
            zoom=False,
        )


async def get_regions(map):
    global regions
    regions = {}
    global region_list
    region_list = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_region, ghsci.get_region_names())
    return regions


def get_region_list(regions):
    region_list = [regions[config] for config in regions]
    return region_list


# set the default region using the selected object
def set_region(map, selection) -> None:
    global region
    if (
        region == regions[selection['codename']]
        and region['geojson'] is not None
    ):
        summary_table()
    else:
        region = regions[selection['codename']]
        # print(region)
        if region['configured'] == ticks[True]:
            if region['geojson'] is not None:
                try:
                    map.add_geojson(region['geojson'])
                except Exception as e:
                    map.set_no_location(default_location, default_zoom)
            else:
                map.set_no_location(default_location, default_zoom)
        else:
            map.set_no_location(default_location, default_zoom)


async def set_selection(map, selection):
    set_region(map, selection)
    studyregion_ui.refresh()
    show_analysis_options.refresh()
    show_generate_options.refresh()
    show_compare_options.refresh()
    show_policy_options.refresh()


@ui.refreshable
def region_ui(map, selection) -> None:
    global grid

    async def output_selected_row():
        global selection
        selection = await grid.get_selected_row()
        await set_selection(map, selection)

    def add_new_codename(new_codename, regions) -> None:
        """Add a new codename to the list of study regions."""
        if (
            new_codename.value.strip() != ''
            and new_codename.value not in ghsci.region_names
        ):
            codename = new_codename.value
            configuration(codename)
            new_row = add_location_row(codename, regions)
            regions[codename] = new_row
            region_list.append(new_row)
            grid.update()
            grid.run_row_method(new_row['id'], 'setSelected', newValue=True)
            new_codename.set_value(None)

    def add_location_row(codename: str, regions) -> dict:
        location_row = {
            'id': len(regions) + 1,
            'codename': codename,
            'name': '',
            'study_region': f'{codename} (configuration not yet complete)',
            'configured': ticks[False],
            'analysed': ticks[False],
            'generated': ticks[False],
            'geojson': None,
            'failure': None,
        }
        # regions[codename] = location_row.copy()
        return location_row

    def setup_ag_columns() -> dict:
        # not_included_columns = ['id', 'centroid', 'zoom', 'geojson']
        not_editable_columns = ['configured', 'analysed', 'generated']
        columns = ['codename', 'study_region'] + not_editable_columns
        ag_columns = []
        for c in columns:
            ag_columns.append(
                {'headerName': c.capitalize(), 'field': c, 'tooltipField': c},
            )
        ag_columns[0]['sort'] = 'asc'
        ag_columns[0]['width'] = 190
        ag_columns[1]['width'] = 190
        return ag_columns

    ag_columns = setup_ag_columns()

    with ui.row().style('width: 80%'):
        with ui.input('Add new codename').style('width: 30%').on(
            'keydown.enter',
            lambda e: (add_new_codename(new_codename, regions),),
        ) as new_codename:
            ui.tooltip(
                'For example, "AU_Melbourne_2023" is a codename for the city of Melbourne, Australia in 2023',
            ).props('anchor="bottom middle" self="bottom left"').style(
                'color: white;background-color: #6e93d6;',
            )
        with ui.input(
            'Search configured regions',
            on_change=lambda e: grid.call_api_method(
                'setQuickFilter',
                filter_text.value,
            ),
        ).props('clearable').style('width: 50%') as filter_text:
            ui.tooltip(
                'Enter text to filter the list of configured regions.',
            ).props('anchor="bottom middle" self="bottom left"').style(
                'color: white;background-color: #6e93d6;',
            )
        with ui.button(
            icon='refresh',
            on_click=lambda e: refresh_main_page(map),
        ).style('position: absolute;right: 0;'):
            ui.tooltip('Refresh the list of configured regions.').style(
                'color: white;background-color: #6e93d6;',
            )
    grid = ui.aggrid(
        {
            'columnDefs': ag_columns,
            'defaultColDef': {
                # 'flex': 1,
                'width': 95,
                'sortable': True,
            },
            'rowData': region_list,
            'rowSelection': 'single',
            'accentedSort': True,
            # 'cacheQuickFilter': True,
        },
        theme='material',
    ).on('click', output_selected_row)
    # if type(selection)==str:
    #     set_selection(selection)

    with ui.row():
        ui.label().bind_text_from(region, 'notes').style('font-style: italic;')


async def refresh_main_page(map):
    # regions = await get_regions(map)
    # ui.navi()
    # grid.update()
    ui.navigate.reload()


def try_function(
    function,
    args=[],
    fail_message='Function failed to run; please check configuration and that the preceding analysis steps have been performed successfully.',
):
    """Run a function and catch any exceptions."""
    try:
        result = function(*args)
    except Exception as e:
        ui.notify(f'{fail_message}: {e}')
        result = None
    finally:
        return result


async def handle_analysis():
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        codename = region['codename']
        try:
            ui.label(
                f"Analysis in progress for study region '{codename}'...",
            ).style('font-style: italic; display: flex; align-items: center;')
            ui.spinner(size='lg')
            await loop.run_in_executor(
                pool,
                ghsci.Region(codename).analysis,
            )
        except Exception as e:
            ui.notify(
                f"Analysis failed for study region {codename}; please check configuration and that the preceding analysis steps have been performed successfully: {e}",
            )
        finally:
            show_analysis_options.refresh()
            formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ui.label(
                f"Analysis for study region '{codename}' completed at {formatted_time}.",
            ).style('font-style: italic;')
            await refresh_main_page(map)


async def handle_generate_resources():
    with concurrent.futures.ThreadPoolExecutor() as pool:
        try:
            loop = asyncio.get_running_loop()
            ui.label(
                f"Generating resources for study region '{region['codename']}'...",
            ).style('font-style: italic; display: flex; align-items: center;')
            ui.spinner(size='lg')
            await loop.run_in_executor(
                pool,
                ghsci.Region(region['codename']).generate,
            )
        except Exception as e:
            ui.notify(
                f"Generating resources failed for study region {region['codename']}; please check configuration and that the preceding analysis steps have been performed successfully: {e}",
            )
        finally:
            show_generate_options.refresh()
            formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ui.label(
                f"Generating resources for study region '{region['codename']}' completed at {formatted_time}.",
            ).style('font-style: italic;')
            await refresh_main_page(map)


def summary_table():
    if region['study_region'] == 'Select or create a new study region':
        with ui.dialog() as dialog, ui.card():
            ui.label(
                "Select a study region from the list in the table below; these correspond to configuration files located in the folder 'process/configuration/regions'.  You can also initialise a new study region configuration via the 'Add a new codename' field. Once configuration is complete, analysis can be run.  Following analysis, summary indicator results can be viewed by clicking the city name heading and PDF analysis and indicator reports may be generated and comparison analyses run.",
            )
            ui.button('Close', on_click=dialog.close)
        dialog.open()
        return None
    else:
        region['summary'] = ghsci.Region(region['codename']).get_df(
            'indicators_region',
            exclude='geom',
        )
        if region['summary'] is None:
            with ui.dialog() as dialog, ui.card():
                status = ['Configuration', 'Analysis'][
                    region['configured'] == ticks[True]
                ]
                hints = [
                    'Hints for next steps may be displayed in the command line interface used to launch the app. ',
                ][region['configured'] == ticks[True]]
                if region['failure'] is not None:
                    ui.markdown(
                        f"""{status} does not appear to have been completed for the selected city.  {hints} Please check the following:
                    """
                        + region['failure']
                        .replace('False:', '\n- ')
                        .replace('_', '\\_')
                        .replace(
                            'One or more required resources were not located in the configured paths; please check your configuration for any items marked "False":',
                            '',
                        ),
                    ).style(
                        'width:500px;text-wrap: auto;overflow-wrap: break-word;',
                    )
                else:
                    ui.label(
                        f'{status} does not appear to have been completed for the selected city.{hints}Once configuration is complete, analysis can be run.  Following analysis, summary indicator results can be viewed by clicking the city name heading and PDF analysis and indicator reports may be generated and comparison analyses run.',
                    )
                ui.button('Close', on_click=dialog.close)
            dialog.open()
            return None
        region['summary'] = region['summary'].transpose().dropna()
        row_key = region['summary'].index.name
        indicator_dictionary = ghsci.dictionary['Description'].to_dict()
        region['summary'].index = region['summary'].index.map(
            indicator_dictionary,
            na_action='ignore',
        )
        region['summary'] = region['summary'].reset_index()
        values = region['summary'].to_dict('records')
        values = [
            {
                k: float(f'{v:.1f}') if isinstance(v, float) else v
                for k, v in x.items()
            }
            for x in values
        ]
        if region['summary'] is not None:
            with ui.dialog() as dialog, ui.card():
                table = ui.table(
                    columns=[
                        {
                            'name': col,
                            'label': '',
                            'field': col,
                            'style': 'white-space: normal;',
                        }
                        for col in region['summary'].columns
                    ],
                    rows=values,
                    row_key=row_key,
                ).style('white-space: normal;')
                with table.add_slot('top-left'):

                    def toggle() -> None:
                        table.toggle_fullscreen()
                        button.props(
                            (
                                'icon=fullscreen_exit'
                                if table.is_fullscreen
                                else 'icon=fullscreen'
                            ),
                        )

                    button = ui.button(
                        'Toggle fullscreen',
                        icon='fullscreen',
                        on_click=toggle,
                    ).props('flat')
                with table.add_slot('top-right'):

                    async def get_choropleth(indicator) -> None:
                        if (
                            indicator
                            in ghsci.indicators['output'][
                                'neighbourhood_variables'
                            ]
                        ):
                            r = ghsci.Region(region['codename'])
                            choropleth = r.choropleth(
                                field=indicator,
                                layer=r.config['grid_summary'],
                                title=indicator_dictionary[
                                    indicator.replace('pct', 'pop_pct')
                                ],
                                save=False,
                            )
                            choropleth = map_to_html(
                                choropleth,
                                title=indicator_dictionary[
                                    indicator.replace('pct', 'pop_pct')
                                ],
                            )
                            return choropleth

                    async def popup_choropleth(indicator) -> None:
                        if indicator is not None:
                            choropleth = await get_choropleth(indicator)
                            if choropleth is not None:
                                with ui.dialog() as map_dialog, ui.card().style(
                                    'min-width: 75%',
                                ):

                                    ui.button(
                                        'Export map',
                                        on_click=lambda: (
                                            ui.notify(
                                                save_text_to_file(
                                                    choropleth,
                                                    f'{region["config"]["region_dir"]}/{indicator}.html',
                                                ),
                                            )
                                        ),
                                    ).props(
                                        'icon=download_for_offline outline',
                                    ).classes(
                                        'shadow-lg',
                                    ).tooltip(
                                        'Save self-contained interactive HTML map to region directory.\nPlease wait a few moments for this to be generated after clicking.',
                                    ).style(
                                        'color: white;background-color: #6e93d6;',
                                    )
                                    ui.html(choropleth).style(
                                        'min-width: 100%;',
                                    )
                                    map_dialog.open()

                    with ui.select(
                        options=ghsci.indicators['output'][
                            'neighbourhood_variables'
                        ],
                        label='View indicator map',
                        with_input=True,
                    ).props('flat') as indicator:
                        ui.tooltip(
                            'New experimental feature: for larger study regions, this may take some time to load!',
                        ).props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style(
                            'color: white;background-color: #6e93d6;',
                        )
                        indicator.on(
                            'update:model-value',
                            lambda e: popup_choropleth(indicator.value),
                        )
                dialog.open()


def comparison_table(
    comparison,
    comparison_list=None,
    save=False,
    display=True,
):
    if region['codename'] is None:
        ui.notify(
            "Please select a reference region having completed analysis from the table in the 'Study Regions' tab before proceeding.",
        )
        return
    elif region['codename'] not in comparison_list:
        ui.notify(
            f"Please confirm that analysis has been completed for {region['codename']} before proceeding.",
        )
        return
    elif comparison == region['codename']:
        ui.notify(
            f'Selected region and comparison region are the same ({comparison}).  Please select a different study region to compare.',
        )
        return
    else:
        result = try_function(
            ghsci.Region(region['codename']).compare,
            [comparison, save],
        )
        if save:
            ui.notify(
                f"Comparison saved as a dated CSV file in study region directory ({region['config']['region_dir'].replace('/home/ghsci/','')}/compare_{region['codename']}_{comparison}_date_hhmm.csv).",
            )
        if result is None:
            ui.notify(
                "Check that the reference and comparison study regions have been selected and analysed before proceeding (current selection didn't work!)",
            )
            return None
        if display:
            result.index = result.index.map(
                ghsci.dictionary['Description'].to_dict(),
                na_action='ignore',
            ).set_names('Indicators')
            result = result.reset_index()
            values = result.to_dict('records')
            values = [
                {
                    k: float(f'{v:.1f}') if isinstance(v, float) else v
                    for k, v in x.items()
                }
                for x in values
            ]
            if result is not None:
                with ui.dialog() as dialog, ui.card().style('min-width:90%'):
                    table = ui.table(
                        columns=[
                            {
                                'name': col,
                                'label': col,
                                'field': col,
                                'style': 'white-space: normal;',
                            }
                            for col in result.columns
                        ],
                        rows=values,
                        row_key='Indicators',
                    ).style('white-space: normal;')
                    with table.add_slot('top-left'):

                        def toggle() -> None:
                            table.toggle_fullscreen()
                            button.props(
                                (
                                    'icon=fullscreen_exit'
                                    if table.is_fullscreen
                                    else 'icon=fullscreen'
                                ),
                            )

                        button = ui.button(
                            'Toggle fullscreen',
                            icon='fullscreen',
                            on_click=toggle,
                        ).props('flat')
                    dialog.open()


def format_policy_checklist(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    df = pd.read_excel(xlsx, sheet_name='Policy Checklist', header=1)
    df.columns = [
        'Indicators',
        'Measures',
        'Principles',
        'Policy',
        'Level of government',
        'Adoption date',
        'Citation',
        'Text',
        'Mandatory',
        'Measurable target',
        'Measurable target text',
        'Evidence-informed threshold',
        'Threshold explanation',
        'Notes',
    ]
    # Exclude dataframe rows where an indicator is defined without a corresponding measure
    # These are short name headings, and this is the quickest way to get rid of them!
    df = df.query('~(Indicators == Indicators and Measures != Measures)')
    # fill down Indicators column values
    df.loc[:, 'Indicators'] = df.loc[:, 'Indicators'].ffill()
    # fill down Measures column values
    df.loc[:, 'Measures'] = df.loc[:, 'Measures'].ffill()
    df = df.loc[~df['Indicators'].isna()]
    df = df.loc[df['Indicators'] != 'Indicators']
    df['qualifier'] = (
        df['Principles']
        .apply(
            lambda x: (
                x
                if (
                    x == 'No' or x == 'Yes' or x == 'Yes, explicit mention of:'
                )
                else pd.NA
            ),
        )
        .ffill()
        .fillna('')
    )
    # replace df['qualifier'] with '' where df['Principles'] is in ['Yes','No'] (i.e. where df['Principles'] is a qualifier)
    df = df.loc[
        ~df['Principles'].isin(['No', 'Yes', 'Yes, explicit mention of:'])
    ]
    df.loc[:, 'Principles'] = df.apply(
        lambda x: (
            x['Principles']
            if x['qualifier'] == ''
            else f"{x['qualifier']}: {x['Principles']}".replace('::', ':')
        ),
        axis=1,
    )
    df.drop(columns=['qualifier'], inplace=True)
    sections = {
        'CITY PLANNING REQUIREMENTS': {
            'indicators': {
                'Integrated transport and urban planning': 'Integrated transport and urban planning actions to create healthy and sustainable cities',
                'Air pollution': 'Limit air pollution from land use and transport',
                'Transport infrastructure investment by mode': 'Priority investment in public and active transport',
                'Disaster mitigation': 'City planning contributes to adaptation and mitigating  the effects of climate change',
            },
        },
        'WALKABILITY POLICIES': {
            'indicators': {
                'Density': 'Appropriate context-specific housing densities that encourage walking; including higher density development around activity centres and transport hubs',
                'Demand management': 'Limit car parking and price parking appropriately for context',
                'Diversity': 'Diverse mix of housing types and local destinations needed for daily living',
                'Destination proximity': ' Local destinations for walkable cities',
                'Desirability': 'Crime prevention through urban design principles, manage traffic exposure, and establish urban greening provisions',
                'Design': 'Create pedestrian- and cycling-friendly neighbourhoods, requiring highly connected street networks; pedestrian and cycling infrastructure provision; and public open space',
            },
        },
        'PUBLIC TRANSPORT POLICIES': {
            'indicators': {
                'Destination accessibility': 'Coordinated planning for transport, employment and infrastructure that ensures access by public transport',
                'Distribution of employment': 'A balanced ratio of jobs to housing ',
                'Distance to public transport': 'Nearby, walkable access to public transport',
            },
        },
    }
    indicator_measures = {
        'Integrated transport and urban planning actions to create healthy and sustainable cities': [
            'Transport and planning combined in one government department',
            'Explicit health-focused actions in urban policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Explicit health-focused actions in transport policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Health Impact Assessment requirements incorporated into urban/transport policy or legislation',
            'Urban and/or transport policy explicitly aims for integrated city planning',
        ],
        'Limit air pollution from land use and transport': [
            'Transport policies to limit air pollution',
            'Land use policies to reduce air pollution exposure',
        ],
        'Priority investment in public and active transport': [
            'Information on government expenditure on infrastructure for different transport modes',
        ],
        'City planning contributes to adaptation and mitigating  the effects of climate change': [
            'Adaptation and disaster risk reduction strategies',
        ],
        'Appropriate context-specific housing densities that encourage walking; including higher density development around activity centres and transport hubs': [
            'Housing density requirements citywide or within close proximity to transport or town centres',
            'Height restrictions on residential buildings (min and/or max)',
            'Required urban growth boundary or maximum levels of greenfield housing development',
        ],
        'Limit car parking and price parking appropriately for context': [
            'Parking restrictions to discourage car use',
        ],
        'Diverse mix of housing types and local destinations needed for daily living': [
            'Mixture of local destinations for daily living ',
            'Mixture of housing types and sizes',
        ],
        'Local destinations for healthy, walkable cities': [
            'Requirements for distance to daily living destinations',
            'Requirements for healthy food environments',
        ],
        'Crime prevention through urban design principles, manage traffic exposure, and establish urban greening provisions': [
            'Tree canopy and urban greening requirements',
            'Urban biodiversity protection & promotion',
            'Traffic safety requirements',
            'Crime prevention through environmental design requirements',
        ],
        'Create pedestrian- and cycling-friendly neighbourhoods, requiring highly connected street networks; pedestrian and cycling infrastructure provision; and public open space': [
            'Street connectivity requirements',
            'Pedestrian infrastructure provision requirements',
            'Cycling infrastructure provision requirements',
            'Walking participation targets',
            'Cycling participation targets',
            'Minimum requirements for public open space access',
        ],
        'Coordinated planning for transport, employment and infrastructure that ensures access by public transport': [
            'Requirements for public transport access to employment and services',
        ],
        'A balanced ratio of jobs to housing ': [
            'Employment distribution requirements',
            'Requirements for ratio of jobs to housing',
        ],
        'Nearby, walkable access to public transport': [
            'Minimum requirements for public transport access',
            'Targets for public transport use ',
        ],
    }
    for section in sections:
        for indicator in sections[section]['indicators']:
            # clean up Measures column values (remove 'see also' references, remove leading and trailing spaces, replace '&nbsp' with ' ', replace '  ' with ' ')
            df.loc[
                df.loc[:, 'Indicators']
                == sections[section]['indicators'][indicator],
                'Measures',
            ] = (
                df.loc[
                    df.loc[:, 'Indicators']
                    == sections[section]['indicators'][indicator]
                ]
                .apply(
                    lambda x: (
                        x.str.strip().replace('&nbsp', ' ').replace('  ', '')
                        if x['Measures'] in indicator_measures[x['Indicators']]
                        else pd.NA
                    ),
                    axis=1,
                )['Measures']
                .ffill()
            )
            # concatenate section and short form of indicator name
            df.loc[
                df.loc[:, 'Indicators']
                == sections[section]['indicators'][indicator],
                'Indicators',
            ] = f'{section} - {indicator}'
    return df


@ui.refreshable
def studyregion_ui() -> None:
    with ui.button(
        region['study_region'],
        on_click=summary_table,
        color='#6e93d6',
    ).props('icon=info').style('color: white'):
        if region['analysed'] == ticks[True]:
            ui.tooltip('View summary indicator results').style(
                'color: white;background-color: #6e93d6;',
            )
        elif region['failure'] is not None:
            ui.tooltip(
                'Region configuration does not yet appear complete.  Click for more information.',
            ).style(
                'color: white;background-color: #6e93d6;',
            )
        else:
            ui.tooltip(
                'To view a study region, select it from the list below, or from the map (if analysis has been undertaken).',
            ).style('color: white;background-color: #6e93d6;')


ghsci.datasets.pop('dictionary', None)


async def load_policy_checklist() -> None:
    xlsx = await local_file_picker(
        '/home/ghsci/process/data',
        multiple=True,
        filter='*.xlsx',
    ).style('min-width: 400px')
    if xlsx is not None:

        async def handle_generate_policy_report():
            from policy_report import PDF_Policy_Report

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                try:
                    with ui.row():
                        spinner = ui.spinner(size='lg')
                        label = ui.label('Generating policy report...').style(
                            'font-style: italic;',
                        )
                        pdf = PDF_Policy_Report(xlsx[0])
                        result = await loop.run_in_executor(
                            pool,
                            pdf.generate_policy_report,
                        )
                        spinner.delete()
                        label.delete()
                    with ui.row():
                        ui.icon('check_circle', size='lg').style(
                            'color: green;',
                        )
                        ui.label(
                            f"Policy report generated: {result.replace('/home/ghsci/','')}.",
                        ).style('font-style: italic;')
                except Exception as e:
                    ui.notify(f'Generating policy report failed: {e}')

        try:
            df = format_policy_checklist(xlsx[0])
        except Exception as e:
            ui.notify(
                f'Policy checklist could not be loaded; please check the file is in the correct format and try again. Specific error: {e}',
            )
            return None
        policy_columns = []
        for c in df.columns:
            policy_columns.append(
                {
                    'name': c,
                    'label': c.capitalize().strip(),
                    'field': c,
                    'sortable': True,
                    'required': True,
                    'width': 100,
                    'wrap-cells': True,
                },
            )
        with ui.dialog() as dialog, ui.card().style('min-width: 90%'):
            with ui.table(
                columns=policy_columns,
                rows=df.to_dict('records'),
            ).classes('w-full').props(
                'wrap-cells=true table-style="{vertical-align: text-top}"',
            ) as table:
                with table.add_slot('top-left'):
                    ui.button(
                        'Generate PDF',
                        on_click=handle_generate_policy_report,
                    ).props('icon=download_for_offline outline').classes(
                        'shadow-lg',
                    ).tooltip(
                        f"Save an indexed PDF of the policy checklist to {xlsx[0].replace('.xlsx','.pdf')}.  Please wait a few moments for this to be generated after clicking.",
                    ).style(
                        'color: white;background-color: #6e93d6;',
                    )
                with table.add_slot('top-right'):
                    with ui.input(placeholder='Search').props(
                        'type=search',
                    ).bind_value(table, 'filter').add_slot('append'):
                        ui.icon('search').tooltip(
                            'Search for key words',
                        ).style('color: white;background-color: #6e93d6;')
            dialog.open()


def ui_exit():
    with ui.dialog() as dialog, ui.card():
        ui.label(
            'The Global Healthy and Sustainable City Indicators web app has been shut down.  This window can now be closed.',
        )
        dialog.open()
        app.shutdown()


def reset_region():
    global region
    region = {
        'id': None,
        'codename': None,
        'config': None,
        'name': '',
        'study_region': 'Select or create a new study region',
        'configured': ticks[False],
        'analysed': ticks[False],
        'generated': ticks[False],
        'geojson': None,
        'failure': None,
    }


@ui.refreshable
def show_analysis_options():
    # create a list of images in the region output figures folder
    help = 'For further help, see the directions at <a href=https://healthysustainablecities.github.io/software/#Analysis target="_blank">https://healthysustainablecities.github.io/software/#Analysis</a>'
    if region['study_region'] == 'Select or create a new study region':
        ui.markdown(
            f'Select a configured study region, or configure a new one and then select it, before proceeding with analysis.  {help}.',
        )
    elif region['configured'] == ticks[False]:
        ui.markdown(
            f'Configuration for {region["codename"]} is not yet complete.  Please complete the configuration in a text editor before proceeding with analysis.    {help}.',
        )
    elif region['configured'] == ticks[True]:
        if region['analysed'] == ticks[True]:
            ui.markdown(
                f'Analysis has already been completed for {region["study_region"]}.  To re-run the analysis, click the button below.  Progress can be monitored from your terminal window, however this user interface may not respond until processing is complete.  {help}.',
            )
        else:
            ui.markdown(
                f'Click the button below to run the analysis workflow for {region["study_region"]}.  Progress can be monitored from your terminal window, however this user interface may not respond until processing is complete.  {help} and guidance on <a href=https://healthysustainablecities.github.io/software/#Processing-time target="_blank">processing time</a>.',
            )
        ui.button(
            'Perform study region analysis',
            on_click=handle_analysis,
        )


@ui.refreshable
def show_generate_options():
    # create a list of images in the region output figures folder
    help = 'For further help, see the directions at <a href=https://healthysustainablecities.github.io/software/#Generate target="_blank">https://healthysustainablecities.github.io/software/#Generate</a>.'
    if region['study_region'] == 'Select or create a new study region':
        ui.markdown(
            f'Select a configured study region for which analysis has been completed to generate and/or view resources.  {help}',
        )
    elif region['configured'] == ticks[False]:
        ui.markdown(
            f'Configuration for {region["study_region"]} is not yet complete.  Please complete the configuration in a text editor and perform analysis before proceeding to generate resources.    {help}.',
        )
    elif region['analysed'] == ticks[False]:
        ui.markdown(
            f'Analysis of {region["study_region"]} has not yet been completed.  Please complete analysis before proceeding to generate resources.    {help}.',
        )
    elif region['analysed'] == ticks[True]:
        ui.markdown(
            f'Click the button below to generate project documentation and resources (data, images, maps, reports, etc).  More information on the outputs is displayedin the terminal window.  {help}',
        )
        images = []
        if (
            region['config'] is not None
            and 'region_dir' in region['config']
            and os.path.isdir(f'{region["config"]["region_dir"]}/figures')
        ):
            images = [
                f'{region["config"]["region_dir"]}/figures/{x}'
                for x in os.listdir(
                    f'{region["config"]["region_dir"]}/figures',
                )
                if x.endswith('.png') or x.endswith('.jpg')
            ]
        if len(images) > 0:
            with ui.row():
                # add nicegui button to 'View Resources'
                ui.markdown(
                    'Resources have already been generated for this region. Please delete manually any files you wish to recreate to ensure changes to configuration settings are reflected when re-running the resource generation process.',
                )
                ui.button(
                    'Generate resources',
                    on_click=handle_generate_resources,
                )
                ui.separator()
                ui.button(
                    'View generated images',
                    on_click=lambda: view_resources(images),
                    color='#6e93d6',
                ).props('icon=perm_media').style('color: white')
        else:
            ui.button(
                'Generate resources',
                on_click=handle_generate_resources,
            )
    else:
        print(region)


@ui.refreshable
def show_compare_options():
    # create a list of images in the region output figures folder
    help = 'For further help, see the directions at <a href=https://healthysustainablecities.github.io/software/#Compare target="_blank">https://healthysustainablecities.github.io/software/#Compare</a>.'
    if region['study_region'] == 'Select or create a new study region':
        ui.markdown(
            f"Select a configured study region for which analysis has been completed to proceed with comparison against another study region's results.  {help}",
        )
    elif region['configured'] == ticks[False]:
        ui.markdown(
            f'Configuration for {region["study_region"]} is not yet complete.  Please complete the configuration in a text editor and perform analysis before proceeding to compare study regions.    {help}.',
        )
    elif region['analysed'] == ticks[False]:
        ui.markdown(
            f'Analysis of {region["study_region"]} has not yet been completed.  Please complete analysis before proceeding to compare study regions.    {help}.',
        )
    elif region['analysed'] == ticks[True]:
        ui.markdown(
            f'To compare {region["study_region"]} with another comparison region with generated resources (eg. as a sensitivity analysis, a benchmark comparison, or evaluation of an intervention or scenario), select a comparison using the drop down menu:',
        )
        if regions is not None:
            comparison_list = [
                regions[r]['codename']
                for r in regions
                if regions[r]['generated'] == ticks[True]
            ]
            comparison = ui.select(
                comparison_list,
                with_input=True,
                label='Select comparison study region codename',
            ).style('width:60%')
            ui.button(
                'View comparison',
                on_click=lambda: (
                    comparison_table(
                        comparison.value,
                        comparison_list,
                        save=False,
                        display=True,
                    )
                ),
            )
            ui.button(
                'Export comparison',
                on_click=lambda: (
                    comparison_table(
                        comparison.value,
                        comparison_list,
                        save=True,
                        display=False,
                    )
                ),
            )


@ui.refreshable
def show_policy_options():
    # create a list of images in the region output figures folder
    help = 'For further help, see the directions at <a href=https://healthysustainablecities.github.io/software/#Policy-checklist target="_blank">https://healthysustainablecities.github.io/software/#Policy-checklist</a>.'
    # if region['study_region'] == 'Select or create a new study region':
    #     ui.markdown(
    #         f'Select a configured study region referencing a completed policy checklist Excel file or use the button below to select a completed policy checklist file.  {help}',
    #     )
    # elif region['configured'] == ticks[True]:
    #     ui.markdown(
    #         f'Configuration for {region["study_region"]} is not yet complete.  Please complete the configuration in a text editor and perform analysis before proceeding to generate resources.    {help}.',
    #     )
    ui.markdown(
        'Optionally, upload a completed policy checklist to explore and link with analysis results.',
    )
    ui.button('Choose file', on_click=load_policy_checklist).props(
        'icon=folder',
    )


def view_resources(images):
    with ui.dialog() as dialog, ui.card().style(
        'min-width:800px; min-height: 700px',
    ):
        # add nicegui carousel
        with ui.carousel(arrows=True, navigation=False).props(
            # 'thumbnails=True,autoplay="1000"'
            'thumbnails=True',
        ).classes('bg-grey-9 shadow-2 rounded-borders').style(
            'min-width:700px; height:700px; display: block; margin-left: auto; margin-right: auto; control-color: #6e93d6',
        ):
            for image in images:
                with ui.carousel_slide().style('height:700px; width:700px;'):
                    ui.image(image).props('width=600px').style(
                        'display: block; margin-left: auto; margin-right: auto;background: #FFFFFF',
                    )
                    ui.label(os.path.basename(image)).style(
                        'text-align: center; font-size: 150%; font-weight: 300; color: #FFFFFF;',
                    )
        ui.button('Close', on_click=dialog.close)
    dialog.open()


# design and arrange the ui for the web application
@ui.page('/')
async def main_page(client: Client):
    # get Leaflet popup text to identify region
    async def get_map_tooltip():
        global region
        global selection
        try:
            clicked = await ui.run_javascript(
                """document.querySelector('[id*="leaflet-tooltip-"]')""",
            )
            if clicked is not None and len(clicked) > 0:
                codename = await ui.run_javascript(
                    """document.querySelector('[class*="leaflet-pane leaflet-tooltip-pane"]').innerText""",
                )
                if (
                    region['codename'] is not None
                    and region['codename'].lower() == codename
                ):
                    summary_table()
                else:
                    region = [
                        x
                        for x in region_list
                        if x['codename'].lower() == codename
                    ][0]
                    selection = regions[region['codename']]
                    grid.run_row_method(
                        region['id'] - 1,
                        'setSelected',
                        True,
                        timeout=20,
                    )
                    await set_selection(map, selection)

        except Exception as e:
            print(f'Error attempting map selection: {e}')
            pass

    # Begin layout
    reset_region()
    ## Title
    with ui.column().props('style="max-width: 900px; margin-top: 20px;"'):
        with ui.row().classes('fixed').style(
            'top: 0px; left: 50%; transform: translateX(-50%); max-width: 900px',
        ):
            ui.label('Global Healthy and Sustainable City Indicators').style(
                'color: #6E93D6; font-size: 200%; font-weight: 300; margin-top: 20px',
            )
            ui.button().props('icon=logout outline round ').classes(
                'shadow-lg',
            ).style('position: absolute; right: 0px; margin-top: 25px').on(
                'click',
                ui_exit,
            ).tooltip(
                'Exit',
            )
            ui.markdown(
                'Open-source software for calculating and reporting on policy and spatial indicators for healthy, sustainable cities worldwide using open or custom data. This tool has been created to support the 1000 Cities Challenge of the  <a href=https://healthysustainablecities.org target="_blank">Global Observatory of Healthy and Sustinable Cities</a>.',
            ).style(
                'color: #6E93D6',
            )
            ## Body
            with ui.card().tight().style('width:900px;').classes(
                'justify-center',
            ) as card:
                studyregion_ui()
                ## Body
                map = (
                    leaflet()
                    .style('width:100%;height:20rem')
                    .on('click', get_map_tooltip)
                )
                # map.set_no_location(default_location, default_zoom)
                regions = await get_regions(map)
                map.set_no_location(default_location, default_zoom)
                # define and design the six tab heads
                with ui.tabs().props('align="left"').style(
                    'width:100%',
                ) as tabs:
                    with ui.tab('Study regions', icon='language'):
                        ui.tooltip(
                            'Select or create a new study region',
                        ).props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style(
                            'color: white;background-color: #6e93d6;',
                        )
                    with ui.tab('Configure', icon='build'):
                        ui.tooltip('Configuration details').props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style('color: white;background-color: #6e93d6;')
                    with ui.tab('Analysis', icon='data_thresholding'):
                        ui.tooltip('Perform spatial indicator analysis').props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style('color: white;background-color: #6e93d6;')
                    with ui.tab('Generate', icon='perm_media'):
                        ui.tooltip(
                            'Generate project reports and resources',
                        ).props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style(
                            'color: white;background-color: #6e93d6;',
                        )
                    with ui.tab('Compare', icon='balance'):
                        ui.tooltip(
                            'Compare results across study regions',
                        ).props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style(
                            'color: white;background-color: #6e93d6;',
                        )
                    with ui.tab('Policy checklist', icon='check_circle'):
                        ui.tooltip(
                            'View, query and export policy checklist results',
                        ).props(
                            'anchor="bottom middle" self="bottom left"',
                        ).style(
                            'color: white;background-color: #6e93d6;',
                        )
                # define and design the panels for the six tabs
                with ui.tab_panels(tabs, value='Study regions').style(
                    'width:100%; max-height:80%',
                ):
                    with ui.tab_panel('Study regions'):
                        region_ui(map, selection)
                    with ui.tab_panel('Configure'):
                        ui.markdown(
                            'Study region, shared dataset and project details can be set up and modified by editing the .yml text files located in the process/configuration/regions folder in a text editor, as per the directions at <a href=https://healthysustainablecities.github.io/software/#Configuration-1 target="_blank">https://healthysustainablecities.github.io/software/#Configuration-1</a>.  An example file ("example_ES_Las_Palmas_2023.yml") has been provided as a guide that can be modified and saved with a new filename (a codename used to identify the study region) to configure analysis for a new study region.  Once configuration is complete, analysis can be run.',
                        )
                    with ui.tab_panel('Analysis'):
                        show_analysis_options(),
                    with ui.tab_panel('Generate'):
                        show_generate_options(),
                    with ui.tab_panel('Compare'):
                        show_compare_options(),
                    with ui.tab_panel('Policy checklist'):
                        show_policy_options(),


# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
app.on_startup(
    lambda: print(
        'GHSCI app launched for viewing in your web browser at: http://localhost:8080\nPlease wait a few moments for the app to load.',
    ),
)

ui.run(
    # reload=platform.system() != 'Windows',
    reload=False,
    title='GHSCI',
    show=False,
    favicon=r'configuration/assets/favicon.ico',
    show_welcome_message=False,
)
