#!/usr/bin/env python3
"""GHSCI graphical user interface; run and access at https://localhost:8080."""

import asyncio
import os.path
import platform
import shlex

import geopandas as gpd
import pandas as pd
import yaml
from analysis import analysis
from compare import compare
from configure import configuration
from generate import generate
from geoalchemy2 import Geometry, WKTElement
from local_file_picker import local_file_picker
from nicegui import Client, ui
from subprocesses import ghsci
from subprocesses.leaflet import leaflet


class Region:
    """Minimal class to define a region."""

    def __init__(self, name=''):
        self.codename = name
        self.name = ''
        self.country = ''
        self.year = ''
        self.configured = ticks[False]
        self.config = {}
        self.config['header_name'] = 'Select or create a new study region'
        self.config['notes'] = ''
        self.notes = ''
        self.analysed = ticks[False]
        self.generated = ticks[False]
        self.centroid = default_location
        self.zoom = default_zoom
        self.geo_region = None
        self.geo_grid = None


ticks = ['✘', '✔']
default_location = [14.509097, 154.832401]
default_zoom = 2
region = Region()


def get_config_string(codename: str) -> str:
    try:
        with open(f'configuration/regions/{codename}.yml') as f:
            config_string = f.read()
    except:
        config_string = 'Unable to load configuration file; please edit using a text editor in consulation with the documentation and examples and try again.'
    finally:
        return config_string


def location_as_dictionary(id, r) -> None:
    location_dictionary = {
        'id': id,
        'codename': r.codename,
        'name': r.name,
        'country': r.config.pop('country', ''),
        'year': str(r.config.pop('year', '')),
        'notes': r.config.pop('notes', ''),
        'configured': r.configured,
        'config': r.config,
        'analysed': r.analysed,
        'generated': r.generated,
        'centroid': r.centroid,
        'zoom': r.zoom,
        'geo_region': r.geo_region,
        'geo_grid': r.geo_grid,
    }
    return location_dictionary


def get_locations() -> dict:
    locations = []
    for id, codename in enumerate(ghsci.region_names):
        # Load region or return null values
        try:
            r = ghsci.Region(codename)
            r.configured = ticks[True]
            if r.tables != []:
                if {'indicators_region', r.config['grid_summary']}.issubset(
                    r.tables,
                ):
                    r.analysed = ticks[True]
                    r.geo_region = r.get_geojson('indicators_region')
                    r.geo_grid = {}  # r.get_geojson(r.config['grid_summary'])
                    r.generated = ticks[
                        os.path.isfile(
                            f'{r.config["region_dir"]}/{r.codename}_indicators_region.csv',
                        )
                    ]
                else:
                    r.analysed = ticks[False]
                    r.generated = ticks[False]
                    r.geo_region = r.get_geojson('urban_study_region')
                    r.geo_grid = None
                if r.geo_region is not None:
                    r.centroid = r.get_centroid()
                    r.zoom = 9
                else:
                    r.centroid = None
                    r.zoom = None
            else:
                r.analysed = ticks[False]
                r.generated = ticks[False]
                r.geo_region = None
                r.geo_grid = None
                r.centroid = None
                r.zoom = None
        except:
            r = Region(name=codename)
            r.config = {
                'name': '',
                'header_name': f'{codename} (configuration not yet complete)',
                'notes': 'Region configuration file could not be loaded and requires completion in a text editor.',
            }
            r.notes = r.config['notes']
        finally:
            locations.append(location_as_dictionary(id, r))

    return locations


def set_region(map, selection) -> None:
    region.codename = selection['codename']
    region.name = selection['name']
    region.country = selection['country']
    region.year = selection['year']
    region.configured = selection['configured']
    region.config = selection['config']
    region.config['header_name'] = load_configuration_text(selection)
    region.config['notes'] = selection['notes']
    region.notes = selection['notes']
    region.analysed = selection['analysed']
    region.generated = selection['generated']
    region.centroid = selection['centroid']
    region.zoom = selection['zoom']
    region.geo_region = selection['geo_region']
    region.geo_grid = selection['geo_grid']
    if selection['notes'] not in [None, '']:
        pass
    if selection['geo_region'] is None:
        map.set_no_location(region.centroid, region.zoom)
    else:
        map.add_geojson(region.geo_region, name='name', popup='popup')
    studyregion_ui.refresh()


def load_configuration_text(selection: list) -> str:
    if len(selection) == 0:
        return 'Select or create a new study region'
    else:
        region_summary = f"{', '.join([selection[x] for x in selection if x in ['name','country','year']])}"
        if region_summary.replace(' ', '') == ',,':
            return f"{selection['codename']}"
        else:
            return f'{region_summary}'


def try_function(
    function,
    args,
    fail_message='Function failed to run; please check configuration.',
):
    try:
        return function(*args)
    except:
        ui.notify(fail_message)
        return None


def comparison_table(comparison):
    row_key = comparison.index.name
    comparison = comparison.reset_index()
    if comparison is not None:
        ui.table(
            columns=[
                {'name': col, 'label': col, 'field': col}
                for col in comparison.columns
            ],
            rows=comparison.round(1).to_dict('records'),
            row_key=row_key,
        ),


def get_new_id(locations) -> int:
    return max([x['id'] for x in locations]) + 1


def add_location_row(codename: str, locations) -> dict:
    location_row = {
        'id': get_new_id(locations),
        'codename': codename,
        'name': '',
        'country': '',
        'year': '',
        'configured': ticks[False],
        'config': {
            'header_name': 'Select or create a new study region',
            'notes': 'New study region; to be configured',
        },
        'notes': 'New study region; to be configured',
        'analysed': ticks[False],
        'generated': ticks[False],
        'centroid': default_location,
        'zoom': default_zoom,
        'geo_region': None,
        'geo_grid': None,
    }
    return location_row


def setup_ag_columns() -> dict:
    not_included_columns = ['id', 'centroid', 'zoom', 'geo_region', 'geo_grid']
    not_editable_columns = ['configured', 'analysed', 'generated']
    columns = ['codename', 'name'] + not_editable_columns
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


# @ui.refreshable
def region_ui(map) -> None:
    async def get_selected_row():
        selection = await grid.get_selected_row()
        if selection:
            set_region(map, selection)

    async def edit_selected_row():
        selection = await grid.get_selected_row()
        if selection:
            update_region_config()

    def update_region_config() -> None:
        config_definition = [
            {'Parameter': k, 'Definition': region.config[k]}
            for k in region.config
        ]
        dialog.open()
        config_table.call_api_method(
            'setRowData', config_definition,
        )

    def add_new_codename(new_codename, locations) -> None:
        """Add a new codename to the list of study regions."""
        if (
            new_codename.value.strip() != ''
            and new_codename.value not in ghsci.region_names
        ):
            configuration(new_codename.value)
            new_row = add_location_row(new_codename.value, locations)
            locations.append(new_row)
            new_codename.set_value(None)
            grid.update()

    with ui.row():
        with ui.input('Add new codename').style('width: 25%').on(
            'keydown.enter',
            lambda e: (add_new_codename(new_codename, locations),),
        ) as new_codename:
            ui.tooltip(
                'For example, "AU_Melbourne_2023" is a codename for the city of Melbourne, Australia in 2023',
            ).style('color: white;background-color: #6e93d6;')
        with ui.input(
            'Search configured regions',
            on_change=lambda e: grid.call_api_method(
                'setQuickFilter', filter_text.value,
            ),
        ).props('clearable').style('width: 70%') as filter_text:
            ui.tooltip(
                'Enter text to filter the list of configured regions.',
            ).style('color: white;background-color: #6e93d6;')
    locations = get_locations()
    grid = ui.aggrid(
        {
            'columnDefs': ag_columns,
            'defaultColDef': {
                # 'flex': 1,
                'width': 95,
                'sortable': True,
            },
            'rowData': locations,
            'rowSelection': 'single',
            'accentedSort': True,
            # 'cacheQuickFilter': True,
        },
        theme='material',
    ).on('click', get_selected_row)
    with ui.row():
        ui.label().bind_text_from(region, 'notes').style('font-style: italic;')
    ui.button('Edit selected configuration').props(
        'flat fab-mini icon=edit',
    ).on('click', edit_selected_row)
    with ui.dialog() as dialog, ui.card().style('min-width: 800px'):
        config_table = ui.aggrid(
            {
                'columnDefs': [
                    {
                        'headerName': 'Parameter',
                        'field': 'Parameter',
                        'tooltipField': 'Parameter',
                        'width': 80,
                    },
                    {
                        'headerName': 'Definition',
                        'field': 'Definition',
                        'tooltipField': 'Definition',
                        'editable': True,
                    },
                ],
                'rowData': [
                    {'Parameter': k, 'Definition': region.config[k]}
                    for k in region.config
                ],
                'rowSelection': 'single',
            },
            theme='material',
        )
        ui.button('Close', on_click=dialog.close)


@ui.refreshable
def studyregion_ui() -> None:
    ui.html(region.config['header_name']).style(
        'color: #6E93D6; font-size: 123%; font-weight: 500',
    )


ghsci.datasets.pop('dictionary', None)


columns = []
for c in [
    'codename',
    'configured',
    'analysed',
    'generated',
]:
    columns.append(
        {
            'name': c,
            'label': c.capitalize(),
            'field': c,
            'sortable': True,
            'required': True,
        },
    )


@ui.page('/')
async def main_page(client: Client):
    async def load_policy_checklist() -> None:
        xlsx = await local_file_picker(
            '/home/ghsci/process/data', multiple=True,
        )
        df = pd.read_excel(xlsx[0], sheet_name='Checklist', header=1)
        df.columns = [
            'Indicators',
            'Measures',
            'Principles',
            'Policy',
            'Adoption date',
            'Citation',
            'Text',
            'Measurable target',
            'Measurable target text',
            'Evidence-informed threshold',
            'Threshold explanation',
            'Mandatory',
            'Notes',
        ]
        # Exclude dataframe rows where an indicator is defined without a corresponding measure
        # These are short name headings, and this is the quickest way to get rid of them!
        df = df.query('~(Indicators == Indicators and Measures != Measures)')
        # fill down Indicators column values
        df.loc[:, 'Indicators'] = df.loc[:, 'Indicators'].fillna(
            method='ffill',
        )
        # fill down Measures column values
        df.loc[:, 'Measures'] = df.loc[:, 'Measures'].fillna(method='ffill')
        # Define report sections and their indicators (short and long forms of names)
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
        print(df.columns)
        print(df.iloc[3].transpose())
        columns = []
        for c in df.columns:
            columns.append(
                {
                    'name': c,
                    'label': c.capitalize(),
                    'field': c,
                    'sortable': True,
                    'required': True,
                },
            )
        # Identify and store the records corresponding for each indicator, omitting the indicator column itself (tautology)
        # for section in sections:
        #     ui.markdown(f'# {section}')
        #     for indicator in sections[section]['indicators']:
        #         i = sections[section]['indicators'][indicator]
        #         sections[section][i] = df.query(f'Indicators=="{i}"')[df.columns[1:]]
        #         ui.markdown(f'## {indicator}')
        with ui.dialog() as dialog, ui.card().style('min-width: 800px'):
            with ui.table(
                columns=columns,
                rows=df,
                # pagination=10,
                selection='single',
                # on_select=lambda e: ui.notify(e.selection),
            ).classes('w-full') as table:
                with table.add_slot('top-right'):
                    with ui.input(placeholder='Search').props(
                        'type=search',
                    ).bind_value(table, 'filter').add_slot('append'):
                        ui.icon('search').tooltip('Search for key words')

        dialog.open()
        # except Exception as e:
        #     ui.notify(f'Unable to load policy checklist; please check configuration: {e}')

    # Begin layout
    ## Title
    ui.label(
        f'Global Healthy and Sustainable City Indicators {ghsci.__version__}',
    ).style('color: #6E93D6; font-size: 200%; font-weight: 300')
    with ui.card().tight().style('width:900px;') as card:
        studyregion_ui()
        ## Body
        map = leaflet().classes('w-full h-96')
        await client.connected()  # wait for websocket connection
        map.set_no_location(default_location, default_zoom)
        with ui.tabs().props('align="left"') as tabs:
            ui.tab('Study regions', icon='language')
            ui.tab('Configure', icon='build')
            ui.tab('Analysis', icon='data_thresholding')
            ui.tab('Generate', icon='perm_media')
            ui.tab('Compare', icon='balance')
            ui.tab('Policy checklist', icon='check_circle')
        with ui.tab_panels(tabs, value='Study regions'):
            with ui.tab_panel('Study regions'):
                region_ui(map)
            with ui.tab_panel('Configure'):
                ui.label(
                    'Project configuration details are summarised below.  It is recommended to view and modify these details using a text editor.',
                )
                with ui.expansion('Datasets'):
                    ui.markdown(
                        f'Define shared datasets for use in your project using configuration/datasets.yml:\n\n```{ghsci.datasets}```',
                    )
                with ui.expansion('Advanced settings'):
                    with ui.expansion('Reporting languages and templates'):
                        ui.markdown(
                            'Edit settings in configuration/_report_configuration.xlsx',
                        )
                    with ui.expansion('Project'):
                        ui.markdown(
                            f'Edit the following project settings in configuration/config.yml:\n\n```{ghsci.settings}```',
                        )
                    with ui.expansion(
                        'OpenStreetMap-derived Areas of Open Space',
                    ):
                        ui.markdown(
                            f'Edit settings in configuration/osm_open_space.yml:\n\n```{ghsci.osm_open_space}```',
                        )
                    with ui.expansion('Indicators'):
                        ui.markdown(
                            f'Edit settings in configuration/indicators.yml:\n\n```{ghsci.indicators}```',
                        )
                    with ui.expansion('Policies'):
                        ui.markdown(
                            f'Edit settings in configuration/policies.yml:\n\n```{ghsci.policies}```',
                        )
            with ui.tab_panel('Analysis'):
                ui.label(
                    'Click the button below to run the analysis workflow.  Progress can be monitored from your terminal window, however this user interface may not respond until processing is complete.',
                )
                ui.button(
                    'Perform study region analysis',
                    on_click=lambda: try_function(analysis, [region.codename]),
                )
            with ui.tab_panel('Generate'):
                ui.label(
                    'Click the button below to generate project documentation and resources (data, images, maps, reports, etc).  More information on the outputs is displayedin the terminal window.',
                )
                ui.button(
                    'Generate resources',
                    on_click=lambda: try_function(generate, [region.codename]),
                )
            with ui.tab_panel('Compare'):
                ui.label(
                    'To compare the selected region with another comparison region with generated resources (eg. as a sensitivity analysis, a benchmark comparison, or evaluation of an intervention or scenario), select a comparison using the drop down menu:',
                )
                comparisons = ui.select(
                    ghsci.region_names,
                    with_input=True,
                    value='Select comparison study region codename',
                )
                ui.button(
                    'Compare study regions',
                    on_click=lambda: (
                        comparison_table(
                            try_function(
                                compare, [region.codename, comparisons.value],
                            ),
                        )
                    ),
                )
            with ui.tab_panel('Policy checklist'):
                ui.label(
                    'Upload a completed policy checklist to explore and link with analysis results.',
                )
                ui.button('Choose file', on_click=load_policy_checklist).props(
                    'icon=folder',
                )


# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
ui.run(reload=platform.system() != 'Windows', title='GHSCI', show=False)
