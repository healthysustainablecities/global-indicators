#!/usr/bin/env python3
"""GHSCI graphical user interface; run and access at https://localhost:8080."""

import asyncio
import os.path
import platform
import shlex

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
        self.config = {}
        self.configured = False
        self.settings = ghsci.settings


async def select_study_region() -> None:
    codename = await configuration_picker(
        'configuration/regions', multiple=False,
    )
    try:
        r = ghsci.Region(codename)
        region.codename = codename
        region.config = r.config
        region.configured = True
        ui.notify(
            f'Selected {r.name}, {r.config["country"]} with a target time point of {r.config["year"]} ({codename})',
        )
    except Exception as e:
        ui.notify(
            f'Please complete configuration for {codename} before proceeding to analysis. (Specific error: {e})',
        )
        region.codename = codename
        region.config = {}
        region.configured = False
    finally:
        globals()['region'] = region


# async def run_command(command: str) -> None:
#     '''Run a command in the background and display the output in the pre-created dialog.'''
#     dialog.open()
#     result.content = ''
#     process = await asyncio.create_subprocess_exec(
#         *shlex.split(command),
#         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
#         cwd=os.path.dirname(os.path.abspath(__file__))
#     )
#     # NOTE we need to read the output in chunks, otherwise the process will block
#     output = ''
#     while True:
#         new = await process.stdout.read(4096)
#         if not new:
#             break
#         output += new.decode()
#         # NOTE the content of the markdown element is replaced every time we have new output
#         result.content = f'```\n{output}\n```'


def get_locations() -> dict:
    locations = []
    for id, codename in enumerate(ghsci.region_names):
        try:
            r = ghsci.Region(codename)
            locations.append(
                {
                    'id': id,
                    'codename': codename,
                    'configured': ticks[True],
                    'config': r.config,
                },
            )
            # ui.notify(f'Selected {r.name}, {r.config["country"]} with a target time point of {r.config["year"]} ({codename})')
        except Exception as e:
            locations.append(
                {
                    'id': id,
                    'codename': codename,
                    'configured': ticks[False],
                    'config': {},
                },
            )
            # ui.notify(f'Please complete configuration for {codename} before proceeding to analysis')
    return locations


ui.label(
    f'Global Healthy and Sustainable City Indicators {ghsci.__version__}',
).style('color: #6E93D6; font-size: 200%; font-weight: 300')

# ui.mermaid('''
# graph LR;
#     subgraph Validation
#         direction RL
#         A[Configure] --> B[Analysis];
#         B --> C[Generate];
#         C --> D[Compare];
#         D[Compare] --> A;
#     end
#     Validation --> F{Dissemination};
# ''')

# @ui.page('/')
# async def main_page(client: Client):
#     map = leaflet().classes('w-full h-96')
#     selection = ui.select(locations, on_change=lambda e: map.set_location(e.value)).classes('w-40')
#     await client.connected()  # wait for websocket connection
#     selection.set_value(next(iter(locations)))  # trigger map.set_location with first location in selection

# locations = {
#     (52.5200, 13.4049): 'Berlin',
#     (40.7306, -74.0060): 'New York',
#     (39.9042, 116.4074): 'Beijing',
#     (35.6895, 139.6917): 'Tokyo',
# }

ticks = [
    '✘',
    '✔',
]


locations = get_locations()

region = Region()
columns = [
    {
        'name': 'codename',
        'label': 'Codename',
        'field': 'codename',
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
    # {'name': 'config', 'label': 'Configuration', 'field': 'config', 'sortable': False},
]


def set_region_codename(location):
    region.codename = location['codename']
    region.config = location['config']
    region.configured = location['configured']


with ui.splitter() as splitter:
    with splitter.before:
        with ui.table(
            title='Study regions',
            columns=columns,
            rows=locations,
            pagination=10,
            selection='single',
            on_select=lambda e: set_region_codename(e.selection[0]),
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
                                table.add_rows(
                                    {
                                        'codename': new_codename.value,
                                        'configured': False,
                                    },
                                ),
                                configuration(new_codename.value),
                                new_codename.set_value(None),
                            ),
                        ).props('flat fab-mini icon=add')
                    ui.update()
                    with table.cell():
                        new_codename = ui.input(
                            'Add new study region codename',
                        )
        # ui.label().bind_text_from(table, 'selected', lambda val: f'Current selection: {val}')
        # with ui.expansion('Study region', icon='travel_explore').classes('w-full') as t:
        #     ui.button('Select existing study region', on_click=select_study_region)
        #     codename_input = ui.input(
        #         label='Codename',
        #         placeholder='Enter a codename to create a new one, e.g. AU_Melbourne_2023',
        #         # on_change=lambda: ui.notify(f'{region.codename = }')
        #         ).style('width: 42em').bind_value(region, 'codename')
    with splitter.after:
        with ui.tabs() as tabs:
            ui.tab('Configure', icon='build')
            ui.tab('Analysis', icon='data_thresholding')
            ui.tab('Generate', icon='perm_media')
            ui.tab('Compare', icon='balance')

        with ui.tab_panels(tabs, value='Home'):
            with ui.tab_panel('Configure'):
                ui.label(f'{region.config}')
                # ui.button(
                #     'Configure study region',
                #     on_click=lambda: configuration(region.codename)
                # ).props('no-caps')
                # ui.button(
                #     'Load configuration',
                #     on_click=lambda: ui.label().bind_text_from(region,'config')
                # ).props('no-caps')

            with ui.tab_panel('Analysis'):
                ui.button(
                    'Perform study region analysis',
                    on_click=lambda: analysis(region.codename),
                )
            with ui.tab_panel('Generate'):
                ui.button(
                    'Generate resources',
                    on_click=lambda: generate(region.codename),
                )
            with ui.tab_panel('Compare'):
                ui.label(
                    'To compare two study regions with generated resources.  Select reference region on left and comparison region below:',
                )
                comparisons = ui.select(
                    ghsci.region_names,
                    with_input=True,
                    value='Select comparison codename',
                )
                ui.button(
                    'Compare study regions',
                    on_click=lambda: compare(
                        region.codename, comparisons.value,
                    ),
                )


with ui.dialog() as dialog, ui.card():
    result = ui.markdown()

# commands = [
#     {'label':'Configure','action':f'python3 configure.py {codename}'}
#     ]
# with ui.row():
#     for command in commands:
#         ui.button(command['label'], on_click=lambda _, c=command['action']: background_tasks.create(run_command(c))).props('no-caps')


# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
ui.run(reload=platform.system() != 'Windows', title='GHSCI', show=False)
