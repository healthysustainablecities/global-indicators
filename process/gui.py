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
        self.analysed = ticks[False]
        self.generated = ticks[False]
        self.centroid = default_location
        self.zoom = default_zoom
        self.geo_region = None
        self.geo_grid = None


ticks = ['✘', '✔']
default_location = (14.509097, 154.832401)
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
                    r.geo_region = {}  # r.get_geojson('indicators_region')
                    r.geo_grid = {}  # r.get_geojson(r.config['grid_summary'])
                    r.generated = ticks[
                        os.path.isfile(
                            f'{r.config["region_dir"]}/{r.codename}_indicators_region.csv',
                        )
                    ]
                else:
                    r.analysed = ticks[False]
                    r.generated = ticks[False]
                    r.geo_region = {}  # r.get_geojson('urban_study_region')
                    r.geo_grid = None
                if r.geo_region is not None:
                    # r.centroid = r.get_centroid()
                    r.centroid = r.get_df(
                        """SELECT ST_Y(geom), ST_X(geom) FROM (SELECT ST_Transform(ST_Centroid(geom),4326) geom FROM urban_study_region) t;""",
                    ).values.tolist()[0]
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
        finally:
            locations.append(location_as_dictionary(id, r))

    return locations


def set_region(map, selection: list) -> None:
    if len(selection) == 0:
        region.codename = ''
        region.name = ''
        region.country = ''
        region.year = ''
        region.configured = ticks[False]
        region.config = {}
        region.config['header_name'] = 'Select or create a new study region'
        region.config['notes'] = ''
        region.analysed = ticks[False]
        region.generated = ticks[False]
        region.centroid = default_location
        region.zoom = default_zoom
        region.geo_region = None
        region.geo_grid = None
        map.set_no_location(default_location, default_zoom)
    else:
        region.codename = selection[0]['codename']
        region.name = selection[0]['name']
        region.country = selection[0]['country']
        region.year = selection[0]['year']
        region.configured = selection[0]['configured']
        region.config = selection[0]['config']
        region.config['header_name'] = load_configuration_text(selection)
        region.config['notes'] = selection[0]['notes']
        region.analysed = selection[0]['analysed']
        region.generated = selection[0]['generated']
        region.centroid = selection[0]['centroid']
        region.zoom = selection[0]['zoom']
        region.geo_region = selection[0]['geo_region']
        region.geo_grid = selection[0]['geo_grid']
        if selection[0]['geo_region'] is None:
            # print(f'None: {selection}')
            map.set_no_location(region.centroid, region.zoom)
            # map.add_geojson(region.geo_region, layer_name='name', popup='popup')
        else:
            # print(f"Some: {selection[0]['name']} {selection[0]['centroid']}")
            map.set_location(selection[0]['centroid'], selection[0]['zoom'])
            # map.add_geojson(region.geo_region, layer_name='name', popup='popup')
    studyregion_ui.refresh()


def load_configuration_text(selection: list) -> str:
    if len(selection) == 0:
        return 'Select or create a new study region'
    else:
        region_summary = f"{', '.join([selection[0][x] for x in selection[0] if x in ['name','country','year']])}"
        if region_summary.replace(' ', '') == ',,':
            # return f"{selection[0]['codename']}Open region configuration file in a text editor to view or edit:<br>configuration/regions/{selection[0]['codename']}.yml"
            return f"{selection[0]['codename']}"
        else:
            # return f"{region_summary}Open region configuration file in a text editor to view or edit:<br>configuration/regions/{selection[0]['codename']}.yml"
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


# @ui.refreshable
def region_ui(map) -> None:
    locations = get_locations()
    with ui.table(
        columns=columns,
        rows=locations,
        pagination=10,
        selection='single',
        on_select=lambda e: set_region(map, e.selection),
    ).classes('w-full') as table:
        # with table.add_slot('top-left'):
        #     studyregion_ui()
        with table.add_slot('top-right'):
            with ui.input(placeholder='Search').props(
                'type=search',
            ).bind_value(table, 'filter').add_slot('append'):
                ui.icon('search').tooltip('Search for a study region')
        with table.add_slot('bottom-row'):
            with table.row():
                with table.cell():
                    ui.button(
                        on_click=lambda: (
                            configuration(new_codename.value),
                            table.add_rows(
                                add_location_row(
                                    new_codename.value, locations,
                                ),
                            ),
                            new_codename.set_value(None),
                        ),
                    ).props('flat fab-mini icon=add')
                ui.update()
                with table.cell():
                    with ui.input('Add new codename').on(
                        'keydown.enter',
                        lambda e: (
                            configuration(new_codename.value),
                            table.add_rows(
                                add_location_row(
                                    new_codename.value, locations,
                                ),
                            ),
                            new_codename.set_value(None),
                        ),
                    ) as new_codename:
                        ui.tooltip(
                            'For example, "AU_Melbourne_2023" is a codename for the city of Melbourne, Australia in 2023',
                        ).style('color: white;background-color: #6e93d6;')
                ui.update()
    ui.label().bind_text_from(
        table,
        'selected',
        lambda val: f'{val[0]["notes"] if len(val) > 0 else ""}',
    )


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
        with ui.tab_panels(tabs, value='Study regions'):
            with ui.tab_panel('Study regions'):
                region_ui(map)
            with ui.tab_panel('Configure'):
                ui.label(
                    'Project configuration details are summarised below.  It is recommended to view and modify these details using a text editor.',
                )
                # with ui.expansion('Region settings'):
                #     ui.markdown().bind_content_from(
                #         table,
                #         'selected',
                #         lambda val: load_configuration_text(val, True),
                #     )
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


with ui.dialog() as dialog, ui.card():
    result = ui.markdown()

# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
ui.run(reload=platform.system() != 'Windows', title='GHSCI', show=False)
