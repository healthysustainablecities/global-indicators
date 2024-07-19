"""Sketch a configuration GUI for a study region."""

from pathlib import Path

import yaml
from nicegui import ui

template = Path('/home/ghsci/process/configuration/assets/region_template.yml')


with ui.stepper().props('vertical').classes('w-full') as stepper:
    with open(template) as f:
        config = yaml.safe_load(f)
    # for key, value in config.items():
    with ui.step('Study region details'):
        # with ui.expansion(text='Expand to view and edit', group='group')
        ui.input(
            label='Full study region name',
            placeholder='Las Palmas de Gran Canaria',
            # validation={'Input too long': lambda value: len(value) < 50},
            on_change=lambda: preview_config.refresh(),
        ).bind_value_to(config, 'name').style('min-width:500px;')
        ui.number(
            label='Target year for analysis',
            format='%4.0g',
            placeholder=2023,
            min=0,
            max=2100,
            precision=0,
            on_change=lambda: preview_config.refresh(),
        ).bind_value_to(config, 'year').style('min-width:300px;')
        ui.input(
            label='Fully country name',
            placeholder='España',
            on_change=lambda: preview_config.refresh(),
        ).bind_value_to(config, 'name').style('min-width:500px;')
        ui.input(
            label='Two character country code (ISO3166 Alpha-2 code)',
            placeholder='ES',
            on_change=lambda: preview_config.refresh(),
        ).bind_value_to(config, 'name').style('min-width:500px;')
        for key, value in config['crs'].items():
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value_to(config['crs'], key)
        with ui.stepper_navigation():
            ui.button('Next', on_click=stepper.next)
    with ui.step('Study region boundary data'):
        for key, value in config['study_region_boundary'].items():
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value_to(config['study_region_boundary'], key)
        with ui.stepper_navigation():
            ui.button('Back', on_click=stepper.previous).props('flat')
            ui.button('Next', on_click=stepper.next)
    # with ui.step('Custom aggregation'):
    #     for key, value in config['custom_aggregations'].items():
    #         ui.input(
    #             label=key,
    #             placeholder=value,
    #             on_change=lambda: preview_config.refresh()
    #         ).bind_value_to(config['custom_aggregations'], key)
    #     with ui.stepper_navigation():
    #         ui.button('Back', on_click=stepper.previous).props('flat')
    #         ui.button('Next', on_click=stepper.next)
    with ui.step('Population data'):
        for key, value in config['population'].items():
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value_to(config['population'], key)
        with ui.stepper_navigation():
            ui.button('Back', on_click=stepper.previous).props('flat')
            ui.button('Next', on_click=stepper.next)
    with ui.step('OpenStreetMap data'):
        for key, value in config['OpenStreetMap'].items():
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value_to(config['OpenStreetMap'], key)
        with ui.stepper_navigation():
            ui.button('Back', on_click=stepper.previous).props('flat')
            ui.button('Next', on_click=stepper.next)
    with ui.step('Pedestrian street network data'):
        for key, value in config['network'].items():
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value_to(config['network'], key)
        with ui.stepper_navigation():
            ui.button('Back', on_click=stepper.previous).props('flat')
            ui.button('Next', on_click=stepper.next)
    with ui.step('Urban region data'):
        for key, value in config['urban_region'].items():
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value_to(config['urban_region'], key)
        # Query used to identify the specific urban region relevant for this region in the Urban Centres database
        ## GHS or other linkage of covariate data (GHS:variable='value', or path:variable='value' for a dataset with equivalently named fields defined in project parameters for air_pollution_covariates), e.g. GHS:UC_NM_MN=='Las Palmas de Gran Canaria' and CTR_MN_NM=='Spain'
        ui.input(
            'Urban query',
            placeholder="GHS:UC_NM_MN=='Las Palmas de Gran Canaria' and CTR_MN_NM=='Spain'",
        ).bind_value_to(config['urban_region'], 'urban_query')
        #  Additional study region summary covariates to be optionally linked. This is designed to retrieve the list of covariates specifies in the 'urban_region' configuration, either from the configured Global Human Settlements Layer data (enter "urban_query"), or from a CSV file (provide a path relative to the project data directory)
        ui.input(
            'Covariate data',
            placeholder='Urban query',
        ).bind_value_to(config['urban_region'], 'urban_query')
        with ui.stepper_navigation():
            ui.button('Back', on_click=stepper.previous).props('flat')
            ui.button('Next', on_click=stepper.next)


@ui.refreshable
def preview_config():
    """Preview the configuration file."""
    with ui.card().tight():
        preview = ui.code(yaml.dump(config), language='yaml')


preview_config()
# with ui.step('Ingredients'):
#     ui.label('Mix the ingredients')
#     with ui.stepper_navigation():
#         ui.button('Next', on_click=stepper.next)
#         ui.button('Back', on_click=stepper.previous).props('flat')
# with ui.step('Bake'):
#     ui.label('Bake for 20 minutes')
#     with ui.stepper_navigation():
#         ui.button('Done', on_click=lambda: ui.notify('Yay!', type='positive'))
#         ui.button('Back', on_click=stepper.previous).props('flat')

ui.run()
