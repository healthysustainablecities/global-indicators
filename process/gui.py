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
        self.configured = ticks[False]


def get_locations() -> dict:
    locations = []
    for id, codename in enumerate(ghsci.region_names):
        try:
            r = ghsci.Region(codename)
            locations.append(
                {'id': id, 'codename': codename, 'configured': ticks[True]},
            )
        except:
            locations.append(
                {'id': id, 'codename': codename, 'configured': ticks[False]},
            )
            # ui.notify(f'Please complete configuration for {codename} before proceeding to analysis')
    return locations


def set_region_codename(selection: list) -> None:
    if len(selection) == 0:
        region.codename = ''
        region.configured = ticks[False]
    else:
        region.codename = selection[0]['codename']
        region.configured = selection[0]['configured']


def load_configuration_text(selection: list) -> str:
    if len(selection) == 0:
        return 'Select or create a new codename representing a study region in the panel to the left to view and/or complete it configuration settings here.'
    else:
        return str(selection[0]['codename'])


ticks = ['✘', '✔']
region = Region()
locations = get_locations()
configurations = {}
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
]

# Begin layout
## Header
ui.label(
    f'Global Healthy and Sustainable City Indicators {ghsci.__version__}',
).style('color: #6E93D6; font-size: 200%; font-weight: 300')


## Body
with ui.splitter(value='500px') as splitter:
    with splitter.before:
        with ui.table(
            title='Study regions',
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
                                table.add_rows(
                                    {
                                        'id': max([x['id'] for x in locations])
                                        + 1,
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
                        with ui.input('Add new codename').on(
                            'keydown.enter',
                            lambda e: (
                                table.add_rows(
                                    {
                                        'id': max([x['id'] for x in locations])
                                        + 1,
                                        'codename': new_codename.value,
                                        'configured': ticks[False],
                                    },
                                ),
                                configuration(new_codename.value),
                                new_codename.set_value(None),
                                print(locations),
                            ),
                        ) as new_codename:
                            ui.tooltip(
                                'e.g. AU_Melbourne_2023 is a codename for the city of Melbourne, Australia in 2023',
                            ).style('color: white;background-color: #6e93d6;')
    with splitter.after:
        with ui.tabs().props('align="left"') as tabs:
            ui.tab('Configure', icon='build')
            ui.tab('Analysis', icon='data_thresholding')
            ui.tab('Generate', icon='perm_media')
            ui.tab('Compare', icon='balance')
        with ui.tab_panels(tabs, value='Configure'):
            with ui.tab_panel('Configure'):
                ui.label().bind_text_from(
                    table,
                    'selected',
                    lambda val: load_configuration_text(val),
                )
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

# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
ui.run(reload=platform.system() != 'Windows', title='GHSCI', show=False)
