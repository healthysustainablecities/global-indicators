#!/usr/bin/env python3
"""GHSCI graphical user interface; run and access at https://localhost:8080."""

import asyncio
import os.path
import platform
import shlex

import yaml
from analysis import analysis
from compare import compare
from configure import configuration
from generate import generate
from nicegui import background_tasks, ui
from nicegui.events import ValueChangeEventArguments
from subprocesses import ghsci


class Region:
    """Minimal class to define a region."""

    def __init__(self):
        self.codename = ''
        self.name = ''
        self.country = ''
        self.year = ''
        self.configured = ticks[False]
        self.config = {}
        self.config[
            'header_name'
        ] = 'Select or create a new codename representing a study region to view region configuration details'
        self.config['notes'] = ''


def get_config_string(codename: str) -> str:
    try:
        with open(f'configuration/regions/{codename}.yml') as f:
            config_string = f.read()
    except:
        config_string = 'Unable to load configuration file; please edit using a text editor in consulation with the documentation and examples and try again.'
    finally:
        return config_string


def get_locations() -> dict:
    locations = []
    for id, codename in enumerate(ghsci.region_names):
        try:
            r = ghsci.Region(codename)
            locations.append(
                {
                    'id': id,
                    'codename': codename,
                    'name': r.name,
                    'country': r.config['country'],
                    'year': str(r.config['year']),
                    'notes': r.config['notes'],
                    'configured': ticks[True],
                    'config': r.config,
                },
            )
        except:
            locations.append(
                {
                    'id': id,
                    'codename': codename,
                    'name': '',
                    'country': '',
                    'year': '',
                    'notes': '',
                    'configured': ticks[False],
                    'config': {
                        'header_name': f'{codename} (configuration not yet complete)',
                        'notes': 'Region configuration file could not be loaded and requires completion in a text editor.',
                    },
                },
            )
            locations[-1]['config']['name'] = ''
    return locations


def set_region_codename(selection: list) -> None:
    if len(selection) == 0:
        region.codename = ''
        region.name = ''
        region.country = ''
        region.year = ''
        region.configured = ticks[False]
        region.config = {}
        region.config[
            'header_name'
        ] = 'Select or create a new codename representing a study region to view region configuration details'
    else:
        region.codename = selection[0]['codename']
        region.name = selection[0]['name']
        region.country = selection[0]['country']
        region.year = selection[0]['year']
        region.configured = selection[0]['configured']
        region.config = selection[0]['config']
        region.config['header_name'] = load_configuration_text(selection)
    studyregion_ui.refresh()


def load_configuration_text(selection: list) -> str:
    if len(selection) == 0:
        return 'Select or create a new codename representing a study region to view region configuration details'
    else:
        region_summary = f"{', '.join([selection[0][x] for x in selection[0] if x in ['name','country','year']])}"
        if region_summary.replace(' ', '') == ',,':
            return f"{selection[0]['codename']}<br><br>Open region configuration file in a text editor to view or edit:<br>configuration/regions/{selection[0]['codename']}.yml"
        else:
            return f"{region_summary}<br><br>Open region configuration file in a text editor to view or edit:<br>configuration/regions/{selection[0]['codename']}.yml"


def try_function(
    function,
    args,
    fail_message='Function failed to run; please check configuration.',
):
    try:
        function(*args)
    except:
        ui.notify(fail_message)


@ui.refreshable
def studyregion_ui() -> None:
    ui.html(region.config['header_name']).style(
        'color: #6E93D6; font-size: 123%; font-weight: 500',
    )


ticks = ['✘', '✔']
region = Region()
locations = get_locations()
ghsci.datasets.pop('dictionary', None)
columns = [
    {
        'name': 'name',
        'label': 'Name',
        'field': 'name',
        'sortable': True,
        'required': True,
    },
    {
        'name': 'codename',
        'label': 'Codename',
        'field': 'codename',
        'sortable': True,
        'required': True,
    },
    {
        'name': 'year',
        'label': 'Year',
        'field': 'year',
        'sortable': True,
        'required': True,
    },
    {
        'name': 'configured',
        'label': 'Configured?',
        'field': 'configured',
        'sortable': True,
        'required': True,
    },
]

# Begin layout
## Header
ui.label(
    f'Global Healthy and Sustainable City Indicators {ghsci.__version__}',
).style('color: #6E93D6; font-size: 200%; font-weight: 300')


# ui.html().bind_content_from(
#     table,
#     'selected',
#     lambda val: load_configuration_text(val),
# ).style('color: #6E93D6; font-size: 123%; font-weight: 500')
studyregion_ui()

## Body
with ui.tabs().props('align="left"') as tabs:
    ui.tab('Study regions', icon='language')
    ui.tab('Configure', icon='build')
    ui.tab('Analysis', icon='data_thresholding')
    ui.tab('Generate', icon='perm_media')
    ui.tab('Compare', icon='balance')
with ui.tab_panels(tabs, value='Study regions'):
    with ui.tab_panel('Study regions'):
        # with ui.splitter(value='500px') as splitter:
        #     with splitter.before:
        with ui.table(
            title='Select or create a new study region',
            columns=columns,
            rows=locations,
            pagination=10,
            selection='single',
            on_select=lambda e: set_region_codename(e.selection),
        ) as table:
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
                                    {
                                        'id': max([x['id'] for x in locations])
                                        + 1,
                                        'codename': new_codename.value,
                                        'configured': False,
                                    },
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
                                    {
                                        'id': max([x['id'] for x in locations])
                                        + 1,
                                        'codename': new_codename.value,
                                        'configured': ticks[False],
                                    },
                                ),
                                new_codename.set_value(None),
                            ),
                        ) as new_codename:
                            ui.tooltip(
                                'e.g. AU_Melbourne_2023 is a codename for the city of Melbourne, Australia in 2023',
                            ).style('color: white;background-color: #6e93d6;')
            # with splitter.after:
            # To do: insert study region map here, for where study region boundaries have been configured and loaded
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
            with ui.expansion('OpenStreetMap-derived Areas of Open Space'):
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
            'To compare two study regions with generated resources.  Select a reference region in on left panel and a comparison region below:',
        )
        comparisons = ui.select(
            ghsci.region_names,
            with_input=True,
            value='Select comparison codename',
        )
        ui.button(
            'Compare study regions',
            on_click=lambda: try_function(
                compare, [region.codename, comparisons.value],
            ),
        )


with ui.dialog() as dialog, ui.card():
    result = ui.markdown()

# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
ui.run(reload=platform.system() != 'Windows', title='GHSCI', show=False)
