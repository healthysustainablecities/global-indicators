"""Sketch a configuration GUI for a study region."""

import json
import os
from datetime import datetime
from pathlib import Path

import yaml
from ghsci import Region
from local_file_picker import local_file_picker
from nicegui import ui

template_path = Path(
    '/home/ghsci/process/configuration/assets/region_template.yml',
)
countries_path = Path(
    '/home/ghsci/process/configuration/assets/WorldBank-Countries-2024.json',
)
config_path = '/home/ghsci/process/configuration'


# with open(template_path) as f:
#     region_template = yaml.safe_load(f)

with open(countries_path) as f:
    countries = dict(
        sorted(
            {
                element['name']: element
                for element in json.load(f)[1]
                if element['region']['id'] != 'NA'
            }.items(),
        ),
    )


def load_configuration(study_region=None):
    """Load yaml file and return as dictionary."""
    if type(study_region) is Region:
        return study_region.config
    if os.path.isfile(f'{config_path}/{study_region}.yml'):
        yml = f'{config_path}/{study_region}.yml'
    else:
        yml = template_path
    with open(yml) as f:
        try:
            config = yaml.safe_load(f)
        except Exception as e:
            print(f'Unable to load configuration file: {e}')
            config = yaml.safe_load(template_path)
    return config


# class Configuration:
#     def __init__(self, study_region=None):
#         config = load_configuration(study_region)
#         # Initialize attributes based on the keys in the region_template
#         for key, value in config.items():
#             setattr(self, key, config.get(key, value))


config = load_configuration(Region('example_ES_Las_Palmas_2023'))
policy_templates = {
    x: True if x in config['reporting']['templates'] else False
    for x in ['policy', 'spatial', 'policy_spatial']
}
image_ratios = {
    1: '(.jpg, 2100px by 1000px; or equivalent 21:10 aspect ratio)',
    2: '(.jpg, 2100px by 1000px; or equivalent 21:10 aspect ratio)',
    3: '(.jpg, 1000px by 1000px; or equivalent 1:1 aspect ratio)',
    4: '(.jpg, 1000px by 1000px; or equivalent 1:1 aspect ratio)',
}
context_steps = {
    'City context': 'Background context for your study region, for example, the location, history and topography, as relevant.',
    'Demographics and health equity': 'Highlight socio-economic demographic characteristics and key health challenges and inequities present in this urban area.',
    'Environmental disaster context': 'Environmental hazards likely to be experienced by the urban area over the next 5-10 years.  Completed policy checklist values will be added, but prose may be customised here.',
    'Levels of Government': 'This section is only included in policy reports. For example, for this report, policies from [insert levels of government from policy checklist,  e.g. national, metropolitan, local] levels of government were analysed.Completed policy checklist values will be added, but prose may be customised here.',
    'Additional context': 'This section is only included in spatial reports, and only if additional information is entered.  Detail any other considerations relating to urban health inequities and geography in this city, or data considerations that could influence interpretation of findings.',
}


def getUTM(longitude, latitude):
    """
    Get UTM zone number and EPSG code from latitude and longitude, accounting for Norway and Svalbard.

    Drawing on contributions from user2232395 and user52366 at
    https://gis.stackexchange.com/questions/365584/convert-utm-zone-into-epsg-code
    """

    def latlon2utm(lon, lat):
        import math

        # Norway_Svalbard_mappings
        if lat >= 72.0 and lat < 84.0:
            if lon >= 0.0 and lon < 9.0:
                return 31
            if lon >= 9.0 and lon < 21.0:
                return 33
            if lon >= 21.0 and lon < 33.0:
                return 35
            if lon >= 33.0 and lon < 42.0:
                return 37
        if lat >= 56 and lat < 64.0 and lon >= 3 and lon <= 12:
            return 32
        return math.floor((lon + 180) / 6) + 1

    try:
        longitude = float(longitude)
        latitude = float(latitude)
    except Exception as e:
        print(f'Unable to convert lat/lon to float (error: {e})')
        return None
    zone = latlon2utm(longitude, latitude)
    # zone = (math.floor((longitude + 180) / 6) ) + 1  # without special zones for Svalbard and Norway
    epsg_code = 32600
    epsg_code += int(zone)
    if latitude < 0:  # South
        epsg_code += 100
        zone = f'{zone}S'
    else:
        zone = f'{zone}N'

    return {
        'zone': zone,
        'epsg': epsg_code,
    }


def country_update():
    if config['country'] not in countries.keys():
        ui.notify(
            f"Unable to auto-fill additional details as country '{config['country']}' was not found in World Bank (2023) data",
        )
    else:
        utm = getUTM(
            countries[config['country']]['longitude'],
            countries[config['country']]['latitude'],
        )
        with ui.dialog() as dialog, ui.card():
            if utm is not None:
                ui.label(
                    f"Do you want to auto-fill additional details on country two-letter region code, World Bank income category (2023), and co-ordinate reference system* based on the selected country '{config['country']}'? These may be modified as required.",
                )
                ui.label(
                    f"Note that coordinate reference system based on country selection may not necessarily be an appropriate choice for your study region.  Please review https://spatialreference.org/ref/epsg/{utm['epsg']} for more information on the UTM{utm['zone']} projection and consider whether there are more accurate options available.)",
                )
            else:
                ui.label(
                    f"Do you want to auto-fill additional details on country two-letter region code and World Bank income category (2023) based on the selected country '{config['country']}'? These may be modified as required.",
                ),
            with ui.row():
                ui.button(
                    'No, go back',
                    on_click=lambda: {
                        preview_config.refresh(),
                        dialog.close(),
                    },
                )
                ui.button(
                    'Yes, auto-fill',
                    on_click=lambda: {
                        run_country_updates(),
                        preview_config.refresh(),
                        dialog.close(),
                    },
                )
        dialog.open()


def run_country_updates():
    config['continent'] = countries[config['country']]['region']['value']
    config['country_gdp']['classification'] = countries[config['country']][
        'incomeLevel'
    ]['value']
    config['country_gdp'][
        'citation'
    ] = 'The World Bank. 2023. World Bank country and lending groups. https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups'
    utm = getUTM(
        countries[config['country']]['longitude'],
        countries[config['country']]['latitude'],
    )
    if utm is not None:
        config['crs']['srid'] = utm['epsg']
        config['crs']['name'] = f'WGS 84 / UTM zone {utm["zone"]}'
        config['crs']['standard'] = 'EPSG'


@ui.refreshable
def preview_config():
    """Preview the configuration file."""
    if config['country'] in countries.keys():
        config['country_code'] = countries[config['country']]['iso2Code']
    with ui.card().tight():
        for feed in [f for f in config['gtfs_feeds'] if f != 'folder']:
            start = config['gtfs_feeds'][feed]['start_date_mmdd']
            end = config['gtfs_feeds'][feed]['end_date_mmdd']
            if end < start:
                with ui.dialog() as dialog, ui.card():
                    ui.label(
                        f"Configuration error in optional GTFS analysis (feed '{feed}'):",
                    )
                    ui.label(
                        f"end date ({datetime.strptime(str(end),'%Y%m%d').strftime('%Y-%m-%d')})",
                    )
                    ui.label('should be later than')
                    ui.label(
                        f"start date ({datetime.strptime(str(start),'%Y%m%d').strftime('%Y-%m-%d')})",
                    )
                    ui.label('(not earlier)')
                    ui.button('Okay', on_click=dialog.close)
                dialog.open()
    config['reporting']['templates'] = [
        x for x in policy_templates if policy_templates[x]
    ]
    preview = ui.code(
        yaml.dump(config, default_flow_style=False, sort_keys=False),
        language='yaml',
    )


def stepper_navigation(stepper, back=True, next=True):
    with ui.stepper_navigation():
        with ui.row():
            if back:
                ui.button('Back', on_click=stepper.previous).props('flat')
            if next:
                ui.button('Next', on_click=stepper.next)


def get_country_code(country=None):
    """Get the country code from the country name."""
    codes = [k for k, v in countries.items() if v == country]
    if len(codes) > 0:
        return codes[0]
    return 'Two-letter country code'


async def locate_file(
    path: str = '/home/ghsci/process/data',
    dict: dict = None,
    record: str = 'data',
):
    """Locate a file."""
    file = await local_file_picker(path)
    if len(file) > 0:
        file = file[0]
    else:
        print('File selection was not successful.')
        return
    if record == 'data':
        dict.update(data=file)
    if record == 'data_dir':
        dict.update(data_dir=file)
    if record == 'policy_review':
        dict.update(policy_review=file)
    if record == 'folder':
        if not file.startswith('/home/ghsci/process/data/transit_feeds/'):
            ui.notify(
                'Please select a folder within the transit_feeds directory',
            )
            return
        else:
            dict.update(
                folder=file.replace(
                    '/home/ghsci/process/data/transit_feeds/',
                    '',
                ),
            )
    preview_config.refresh()


# def add_exception(exception, language):
#     """Add an exception to the configuration file."""
#     ui.input(
#         label=f"{exception}",
#         placeholder=exception,
#         on_change=lambda: preview_config.refresh(),
#     ).bind_value(config['reporting']['exceptions'][language], exception).style('min-width:500px;')


def toggle_network_source(value):
    if value == 'Custom' and 'intersections' not in config['network']:
        config['network']['intersections'] = {}
        config['network']['intersections']['data'] = ''
        config['network']['intersections']['citation'] = ''
        config['network']['intersections']['note'] = ''


def toggle_aggregation_source(area, value):
    keys = [
        'data',
        'id',
        'keep_columns',
        'aggregation_source',
        'aggregate_within_distance',
        'weight',
        'note',
    ]
    if value == 'Custom':
        config['network']['intersections'] = {}
        config['network']['intersections']['data'] = ''
        config['network']['intersections']['citation'] = ''
        config['network']['intersections']['note'] = ''


class Aggregation:
    """Define a custom aggregation area."""

    def __init__(self, area='New area', props={}):
        self.name = area
        self.area = {}
        self.area['data'] = props.get('data', None)
        self.area['id'] = props.get('id', None)
        self.area['keep_columns'] = props.get('keep_columns', None)
        self.area['aggregation_source'] = props.get('aggregation_source', None)
        self.area['aggregate_within_distance'] = props.get(
            'aggregate_within_distance',
            None,
        )
        self.area['weight'] = props.get('weight', None)
        self.area['note'] = props.get('note', None)


class ToggleButton(ui.button):
    """A toggle-able button, with true and false state."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._state = False
        self.on('click', self.toggle)
        self.props('round size="8px"')

    def toggle(self) -> None:
        """Toggle the button state."""
        self._state = not self._state
        self.update()

    def update(self) -> None:
        """Update button properties based on state."""
        self.props(f'color={"blue" if self._state else "grey"}')
        super().update()


def editable_input(
    label,
    placeholder,
    dictionary,
    value,
    on_change=lambda: preview_config.refresh(),
    backward=lambda value: value,
    forward=lambda value: value,
    validation={},
):
    """Display a row containing an edit icon and text label; when the edit icon is clicked, the text label is replaced with an input box."""
    ui.label(label).style('font-weight:700;')
    with ui.row().style('width:100%'):
        with ui.column().style('width:1.2em'):
            edit = ToggleButton(icon='edit')
        with ui.column().style('width:90%'):
            input = (
                ui.input(
                    placeholder=placeholder,
                    on_change=on_change,
                    validation=validation,
                )
                .bind_value(
                    dictionary,
                    value,
                    backward=backward,
                    forward=forward,
                )
                .bind_visibility_from(edit, '_state')
                .style('width:80%; position: relative; top:-1.2em;')
            )
            text = (
                ui.label()
                .bind_visibility_from(edit, '_state', value=False)
                .bind_text_from(input, 'value')
            )


def editable_number(
    label,
    placeholder,
    dictionary,
    value,
    on_change=lambda: preview_config.refresh(),
    backward=lambda value: int(value),
    forward=lambda value: int(value),
    validation={},
    format='%d',
    min=None,
    max=None,
    precision=0,
):
    """Display a row containing an edit icon and number; when the edit icon is clicked, the number is replaced with an editable number input."""
    ui.label(label).style('font-weight:700;')
    with ui.row().style('width:100%'):
        with ui.column().style('width:1.2em'):
            edit = ToggleButton(icon='edit')
        with ui.column().style('width:90%'):
            input = (
                ui.number(
                    format=format,
                    placeholder=placeholder,
                    min=min,
                    max=max,
                    precision=precision,
                    on_change=on_change,
                )
                .bind_value(
                    dictionary,
                    value,
                    backward=backward,
                    forward=forward,
                )
                .bind_visibility_from(edit, '_state')
                .style('position: relative; top:-1.2em;')
            )
            text = (
                ui.label()
                .bind_visibility_from(edit, '_state', value=False)
                .bind_text_from(input, 'value')
            )


def editable_select(
    label,
    options,
    dictionary,
    value,
    on_change=lambda: preview_config.refresh(),
    backward=lambda value: value,
    forward=lambda value: value,
    validation={},
):
    """Display a row containing an edit icon and text; when the edit icon is clicked, the text is replaced with a select box."""
    ui.label(label).style('font-weight:700;')
    with ui.row().style('width:100%'):
        with ui.column().style('width:1.2em'):
            edit = ToggleButton(icon='edit')
        with ui.column().style('width:90%'):
            input = (
                ui.select(
                    options=options,
                    with_input=True,
                    new_value_mode='add',
                    on_change=on_change,
                    validation=validation,
                )
                .bind_value(
                    dictionary,
                    value,
                    backward=backward,
                    forward=forward,
                )
                .bind_visibility_from(edit, '_state')
                .style('width:80%; position: relative; top:-1.2em;')
            )
            text = (
                ui.label()
                .bind_visibility_from(edit, '_state', value=False)
                .bind_text_from(input, 'value')
            )


def configure_study_region(stepper):
    # for key, value in config.items():
    with ui.step('Study region details'):
        editable_input(
            'Study region (e.g. city or region)',
            'Las Palmas de Gran Canaria',
            config,
            'name',
        )
        editable_number('Target year for analysis', 2023, config, 'year')
        ui.label('Context').style('font-weight:700;')
        with ui.card().style('width: 100%'):
            editable_select(
                'Select country from list or enter customised name',
                list(sorted(countries.keys())),
                config,
                'country',
            )
            editable_input(
                'Two character country code (ISO3166 Alpha-2 code)',
                get_country_code(config['country']),
                config,
                'country_code',
            )
            if config['country'] in countries.keys():
                ui.button(
                    'Auto-fill details based on country selection',
                    icon='info',
                    on_click=country_update,
                )
            editable_input(
                'Continent or region',
                'Europe',
                config,
                'continent',
            )
            editable_input(
                'World Bank country income group classification',
                'Lower middle income',
                config['country_gdp'],
                'classification',
            )
            editable_input(
                'Citation for country context details',
                'The World Bank. 2023. World Bank country and lending groups. https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups',
                config['country_gdp'],
                'citation',
            )
            ui.label('Coordinate Reference System').style('font-weight:700;')
            ui.markdown(
                'Please specify a suitable [projected coordinate reference system](https://en.wikipedia.org/wiki/Projected_coordinate_system#Examples_of_projected_CRS) (CRS; having units in metres) for this study region. Search [https://epsg.io](https://epsg.io) or [https://spatialreference.org/](https://spatialreference.org/) for a suitable projection noting its name (e.g. ), standard (e.g. EPSG) and spatial reference identifier code (SRID).  This will be used for analysis of accessibility using units of metres.',
            )
            editable_input(
                'CRS name',
                'WGS 84 / UTM zone 28N',
                config['crs'],
                'name',
            )
            editable_input(
                'Standard used to define this CRS, eg. EPSG',
                'EPSG',
                config['crs'],
                'standard',
            )
            editable_number(
                'Spatial reference identifier (SRID) integer for this CRS and standard',
                'EPSG',
                config['crs'],
                'srid',
            )
        editable_input(
            'Notes on this study region',
            'Any additional aspects of this study region or analysis that should be noted.',
            config,
            'notes',
        )
        stepper_navigation(stepper)


def configure_boundary(stepper):
    with ui.step('Study region boundary data'):
        ui.label(
            'Please provide the path to the study region boundary data, relative to the project directory.',
        )
        ui.label(
            'For example, to load a file (geojson, shapefile, or geopackage), you could enter "region_boundaries/Example/Las Palmas de Gran Canaria - Centro Nacional de Información Geográfica - WGS84 - EPSG4326.geojson".',
        )
        ui.label(
            'Geopackage layers may be specified using a colon separator, e.g. "region_boundaries/data.gpkg:layer_name".',
        )
        ui.label(
            '''Data may optionally be queried to return a boundary matching specific attributes, for example: region_boundaries/your_geopackage.gpkg:layer_name -where "some_attribute=='some_value'"''',
        )
        # file path browser for boundary data
        ui.button(
            'Select a file in the process/data folder',
            on_click=lambda: locate_file(
                dict=config['study_region_boundary'],
                record='data',
            ),
        ).props(
            'icon=folder',
        )
        ui.input(
            label='Boundary data path',
            placeholder='/path/to/boundary/data.shp',
            on_change=lambda: preview_config.refresh(),
        ).bind_value(
            config['study_region_boundary'],
            'data',
            backward=lambda path: path.replace(
                '/home/ghsci/process/data/',
                '',
            ),
        ).style(
            'width:100%;',
        ),
        with ui.card().style('width:100%;'):
            ui.label('Citation details').style('font-weight:700;')
            ui.input(
                label='The name of the source of this data.',
                placeholder='Centro Nacional de Información Geográfica',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['study_region_boundary'], 'source').style(
                'width:100%;',
            )
            ui.input(
                label='URL for the source dataset.',
                placeholder='https://datos.gob.es/en/catalogo/e00125901-spaignllm',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['study_region_boundary'], 'url').style(
                'width:100%;',
            )
            ui.textarea(
                label='A formal citation for this data.',
                placeholder='Instituto Geográfico Nacional (2019). Base de datos de divisiones administrativas de España. https://datos.gob.es/en/catalogo/e00125901-spaignllm',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(
                config['study_region_boundary'],
                'citation',
            ).style(
                'width:100%;',
            )
            ui.label('Publication date')
            with ui.input('Date') as date:
                with ui.menu().props('no-parent-event') as menu:
                    with ui.date().bind_value(date).bind_value(
                        config['study_region_boundary'],
                        'publication_date',
                    ):
                        with ui.row().classes('justify-end'):
                            ui.button('Close', on_click=menu.close).props(
                                'flat',
                            )
                with date.add_slot('append'):
                    ui.icon('edit_calendar').on('click', menu.open).classes(
                        'cursor-pointer',
                    )
            ui.input(
                label='Licence for the data, e.g. CC-BY-4.0',
                placeholder='CC-BY-4.0',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['study_region_boundary'], 'licence').style(
                'min-width:500px;',
            )
            ui.textarea(
                label='Notes',
                placeholder='manually extracted municipal boundary for Las Palmas de Gran Canaria in WGS84 from the downloaded zip file "lineas_limite.zip" using QGIS to a geojson file for demonstration purposes.',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['study_region_boundary'], 'notes').style(
                'width:100%;',
            )
        ui.checkbox(
            text='Restrict analysis to an urban area defined by its intersection with a defined urban region (configured later)?',
            on_change=lambda: preview_config.refresh(),
        ).bind_value(
            config['study_region_boundary'],
            'ghsl_urban_intersection',
        ).style(
            'min-width:500px;',
        )
        stepper_navigation(stepper)


def configure_population(stepper):
    with ui.step('Population data'):
        ui.markdown(
            'Population distribution may be represented using a raster population grid or vector data.  Our provided example uses the [Global Human Settlements Layer population destimates](https://human-settlement.emergency.copernicus.eu/download.php?ds=pop).  Note that if using this data, you must select an epoch for population estimates/projections (e.g. 2025).  The default resolution of 100m is recommended.  Your study region may span multiple grid tiles; check using the map at the above link, then download and extract tif files to a sub-folder within the process/data folder that you can browse to using the button below.',
        )
        # file path browser for boundary data
        ui.button(
            'Select a folder containing  in the process/data folder',
            on_click=lambda: locate_file(
                dict=config['population'],
                record='data_dir',
            ),
        ).props(
            'icon=folder',
        )
        ui.input(
            label='Path relative to project data directory to folder containing tifs, or to vector file',
            placeholder='population_grids/Example/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R5_C23',
            on_change=lambda: preview_config.refresh(),
        ).bind_value(
            config['population'],
            'data_dir',
            backward=lambda path: path.replace(
                '/home/ghsci/process/data/',
                '',
            ),
        ).style(
            'width:100%;',
        )
        with ui.card().style('width: 100%'):
            ui.label('Citation details').style('font-weight:700;')
            ui.input(
                label='Name of the population data',
                placeholder='Global Human Settlements population data 2020 (EU JRC, 2022)',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['population'], 'name').style(
                'width:100%;',
            )
            ui.textarea(
                label='URL(s) used to retrieve this data',
                placeholder='https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2022A/GHS_POP_E2020_GLOBE_R2022A_54009_100/V1-0/tiles/GHS_POP_E2020_GLOBE_R2022A_54009_100_V1_0_R6_C17.zip',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['population'], 'source_url').style(
                'width:100%;',
            )
            ui.textarea(
                label='Citation',
                placeholder='Schiavina, Marcello; Freire, Sergio; MacManus, Kytt (2022): GHS-POP R2022A - GHS population grid multitemporal (1975-2030). European Commission, Joint Research Centre (JRC) [Dataset] doi: 10.2905/D6D86A90-4351-4508-99C1-CB074B022C4A',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['population'], 'citation').style(
                'width:100%;',
            )
            ui.input(
                label='Licence, e.g. "CC BY 4.0"',
                placeholder='CC BY 4.0',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['population'], 'licence').style(
                'min-width:500px;',
            )
            ui.input(
                label='Year the data was published (yyyy), e.g. 2023',
                placeholder='2022',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['population'], 'year_published').style(
                'min-width:500px;',
            )
            ui.input(
                label='The year the data is intended to represent (yyyy), e.g. 2020',
                placeholder='2020',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['population'], 'year_target').style(
                'min-width:500px;',
            )
            ui.label('Retrieval date')
            with ui.input('Date') as date:
                with ui.menu().props('no-parent-event') as menu:
                    with ui.date().bind_value(date).bind_value(
                        config['population'],
                        'date_acquired',
                    ):
                        with ui.row().classes('justify-end'):
                            ui.button('Close', on_click=menu.close).props(
                                'flat',
                            )
                with date.add_slot('append'):
                    ui.icon('edit_calendar').on('click', menu.open).classes(
                        'cursor-pointer',
                    )
        with ui.card().style('width: 100%'):
            with ui.expansion(
                'Advanced configuration options',
                icon='settings',
            ).classes('w-full'):
                ui.label(
                    'If you are using the GHSL-POP data, as demonstrated in the provided example, you may not have to modify the following options.  However, if you are using alternative data it is likely that additional configuration will be required.',
                )
                ui.input(
                    label='Type of data (e.g. "raster:Int64" or "vector")',
                    placeholder='raster:Int64',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'data_type').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Resolution of the image, e.g. 100 m',
                    placeholder='100m',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'resolution').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='The image band containing the relevant data, e.g. for GHSL-POP, 1',
                    placeholder='1',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'raster_band').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='A value in the image that represents "no data", e.g. for GHSL-POP, -200',
                    placeholder='-200',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'raster_nodata').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Sample points intersecting grid cells with estimated population less than this will be excluded from analysis.  Depending on your population data resolution, you can use this to exclude areas with very low population due to the uncertainty of where anyone might live in that area, or if they do at all',
                    placeholder='1',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'pop_min_threshold').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Coordinate reference system metadata for population data (e.g. Mollweide, ESRI, 54009)',
                    placeholder='Mollweide',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'crs_name').style(
                    'min-width:500px;',
                )
        stepper_navigation(stepper)


def configure_openstreetmap(stepper):
    with ui.step('OpenStreetMap data'):
        # file path browser for boundary data
        ui.button(
            'Select a file in the process/data folder',
            on_click=lambda: locate_file(
                dict=config['OpenStreetMap'],
                record='data_dir',
            ),
        ).props(
            'icon=folder',
        )
        ui.input(
            label='OpenStreetMap .pbf file',
            placeholder='OpenStreetMap/Example/iran_51.092,35.567_51.603,35.829.osm.pbf',
            on_change=lambda: preview_config.refresh(),
        ).bind_value(
            config['OpenStreetMap'],
            'data_dir',
            backward=lambda path: path.replace(
                '/home/ghsci/process/data/',
                '',
            ),
        ).style(
            'width:100%;',
        )
        with ui.card().style('width: 100%'):
            ui.label('Citation details').style('font-weight:700;')
            ui.input(
                label='The source of the OpenStreetMap data (e.g. Planet OSM, GeoFabrik or OpenStreetMap.fr)',
                placeholder='OpenStreetMap.fr',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['OpenStreetMap'], 'source').style(
                'width:100%;',
            )
            ui.label('Publication date')
            with ui.input('Date') as date:
                with ui.menu().props('no-parent-event') as menu:
                    with ui.date().bind_value(date).bind_value(
                        config['OpenStreetMap'],
                        'publication_date',
                        backward=lambda date: datetime.strptime(
                            str(date),
                            '%Y%m%d',
                        ).strftime('%Y-%m-%d'),
                        forward=lambda date: datetime.strptime(
                            str(date),
                            '%Y-%m-%d',
                        ).strftime('%Y%m%d'),
                    ):
                        with ui.row().classes('justify-end'):
                            ui.button('Close', on_click=menu.close).props(
                                'flat',
                            )
                with date.add_slot('append'):
                    ui.icon('edit_calendar').on('click', menu.open).classes(
                        'cursor-pointer',
                    )
            ui.textarea(
                label='The URL from where it was downloaded',
                placeholder='https://download.openstreetmap.fr/extracts/africa/spain/canarias/las_palmas-latest.osm.pbf',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['OpenStreetMap'], 'url').style(
                'width:100%;',
            )
            ui.textarea(
                label='An optional note regarding this data',
                placeholder='This is configured with a derived excerpt from the larger OpenStreetMap dataset for Las Canarias based on the 1600m buffered municipal boundary of Las Palmas de Gran Canaria to reduce file size for demonstration purposes.',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['OpenStreetMap'], 'note').style(
                'width:100%;',
            )
        stepper_navigation(stepper)


def configure_network(stepper):
    with ui.step('Pedestrian street network data'):
        ui.label('Data source for intersection analysis')
        switch = ui.toggle(
            [
                'OpenStreetMap',
                'Custom',
            ],
            value=['OpenStreetMap', 'Custom'][
                'intersections' in config['network']
            ],
            on_change=lambda e: toggle_network_source(e.value),
            clearable=False,
        ).style(
            'font-weight:700;',
        )
        with ui.card().style('width: 100%').bind_visibility_from(
            switch,
            'value',
            value='Custom',
        ):
            ui.label(
                'Optionally, data for evaluating intersections can be provided as an alternative to deriving intersections from OpenStreetMap (where available, this may be preferable).  See the provided example configuration file for directions on how to do this.',
            )

        with ui.card().style('width: 100%').bind_visibility_from(
            switch,
            'value',
            value='OpenStreetMap',
        ):
            ui.label(
                'Tolerance in metres for cleaning intersections.  If not providing your own data for evaluating intersection density (see below), this is an important methodological choice.  The chosen parameter should be robust to a variety of network topologies in the city being studied.  See https://github.com/gboeing/osmnx-examples/blob/main/notebooks/04-simplify-graph-consolidate-nodes.ipynb',
            )
            ui.input(
                label='Intersection tolerance (m)',
                placeholder='12',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['network'], 'intersection_tolerance').style(
                'min-width:500px;',
            )
            with ui.expansion(
                'Advanced configuration options',
                icon='settings',
            ).classes('w-full'):
                ui.checkbox(
                    text='Retain main connected network when retrieving OSM roads? The default is unchecked or "false" for most settings, however if your study region spans multiple disconnected islands it may be more appropriate set to checked or "true"',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['network'], 'osmnx_retain_all')
                ui.checkbox(
                    text='Extract the network for the buffered study region?  The default is checked or "true" in most cases.  Setting this to unchecked or "false" may be appropriate for study regions comprised of multiple islands, but could be problematic for anywhere else where the network and associated amenities may be accessible beyond the edge of the study region boundary.',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['network'], 'buffered_region')
                ui.checkbox(
                    text='Iterate over and combine polygons?  The default is unchecked or "false" for most cases, but may be appropriate for a series of islands, like Hong Kong.',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['network'], 'polygon_iteration')
                ui.label(
                    'Minimum total network distance for subgraphs to retain.  This is a useful parameter for customising analysis for islands, like Hong Kong, but for most purposes you can leave this blank (the default).',
                )
                ui.number(
                    label='Metres (None, or > 0).',
                    placeholder=None,
                    min=-1,
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['network'],
                    'connection_threshold',
                    backward=lambda value: (
                        int(value) if value is not None and value > 0 else None
                    ),
                ).style(
                    'min-width:500px;',
                )
                ui.label(
                    'Pedestrian network definition.  This is the query used to retrieve the pedestrian network from OpenStreetMap.  The default is a query that excludes motorways, proposed roads, construction sites, abandoned roads, platforms, raceways, private roads, and roads with private access.  You may customise this query to suit your study region.  See https://osmnx.readthedocs.io/en/stable/user-reference.html#module-osmnx.graph and https://wiki.openstreetmap.org/wiki/Overpass_API.',
                )
                ui.textarea(
                    'OSMnx Overpass custom filter query',
                    placeholder='["highway"]["area"!~"yes"]["highway"!~"motor|proposed|construction|abandoned|platform|raceway"]["foot"!~"no"]["service"!~"private"]["access"!~"private"]',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['network'],
                    'pedestrian',
                ).style(
                    'width:100%;',
                )
        stepper_navigation(stepper)


def configure_urban_region(stepper):
    with ui.step('Urban region data'):
        ui.markdown(
            'You can configure analysis to be restricted to a specific urban region for analysis using the Global Human Settlements Layer (GHSL) Urban Centres Database (UCDB).  This database has a target year of 2015, however it provides data on urban agglomerations globally linked with relevant contextual attributes.  Further details including links to download the full GHSL UCDB (R2019A) are available [here](https://data.jrc.ec.europa.eu/dataset/53473144-b88c-44bc-b4a3-4583ed1f547e).',
        )
        ui.button(
            'Select a file in the process/data folder',
            on_click=lambda: locate_file(
                dict=config['urban_region'],
                record='data_dir',
            ),
        ).props(
            'icon=folder',
        )
        ui.input(
            label='Path to data relative to the project data directory',
            placeholder='urban_regions/Example/GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.gpkg',
            on_change=lambda: preview_config.refresh(),
        ).bind_value(
            config['urban_region'],
            'data_dir',
            backward=lambda path: path.replace(
                '/home/ghsci/process/data/',
                '',
            ),
        ).style(
            'width:100%;',
        )
        ui.textarea(
            label='Query used to identify the specific urban region relevant for this region in the Urban Centres database',
            placeholder='GHS:UC_NM_MN==\'Las Palmas de Gran Canaria\' and CTR_MN_NM==\'Spain\'',
            on_change=lambda: preview_config.refresh(),
        ).bind_value(config, 'urban_query').style('width: 100%;')
        with ui.card().style('width: 100%'):
            ui.label('Citation details').style('font-weight:700;')
            ui.input(
                label='Name for the urban region data',
                placeholder='GHS Urban Centre Database 2015 (EU JRC, 2019)',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['urban_region'], 'name').style(
                'min-width:500px;',
            )
            ui.input(
                label='Citation for this data, this has been pre-filled for the GHSL UCDB (2019), but change as required if using',
                placeholder='Florczyk, A. et al. (2019): GHS Urban Centre Database 2015, multitemporal and multidimensional attributes, R2019A. European Commission, Joint Research Centre (JRC). https://data.jrc.ec.europa.eu/dataset/53473144-b88c-44bc-b4a3-4583ed1f547e',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['urban_region'], 'citation').style(
                'min-width:500px;',
            )
            ui.input(
                label='Licence, e.g. CC BY 4.0',
                placeholder='CC BY 4.0',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['urban_region'], 'licence').style(
                'min-width:500px;',
            )
        with ui.card().style('width: 100%'):
            with ui.expansion(
                'Advanced configuration options',
                icon='settings',
            ).classes('w-full'):
                ui.label(
                    'A list of additional covariates can be optionally linked for cities included in the GHSL UCDB.  These may be edited in a text editor according to the provided examples.',
                )
        stepper_navigation(stepper)


def configure_optional(stepper):
    with ui.step('Optional analyses'):
        with ui.switch('Policy review').style(
            'font-weight:700;',
        ) as policy_review:
            if 'policy_review' in config:
                policy_review.value = True
            else:
                policy_review.value = False
                config['policy_review'] = (
                    'policy_review/gohsc-policy-indicator-checklist.xlsx'
                )
        with ui.card().bind_visibility_from(
            policy_review,
            'value',
        ):
            ui.button(
                'Select a file in the process/data folder',
                on_click=lambda: locate_file(
                    path='/home/ghsci/process/data/policy_review',
                    dict=config,
                    record='policy_review',
                ),
            ).props(
                'icon=folder',
            )
            ui.input(
                label='Path to the policy review file',
                placeholder='policy_review/gohsc-policy-indicator-checklist.xlsx',
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config, 'policy_review').style(
                'min-width:500px;',
            )
        with ui.switch('Custom aggregation').style(
            'font-weight:700;',
        ) as aggregation:
            if (
                'custom_aggregations' in config
                and len(config['custom_aggregations']) > 0
            ):
                aggregation.value = True
            else:
                aggregation.value = False
                config['custom_aggregations'] = {}
        with ui.card().bind_visibility_from(aggregation, 'value'):
            ui.label(
                'Optional custom aggregation to additional areas of interest (e.g. neighbourhoods, suburbs, specific developments).  This has not yet been implemented in the graphical user interface set up, but may be configured by manually editing a configuration file following provided examples.',
            )
            for area in config['custom_aggregations']:
                ui.separator()
                ui.label(area).style('font-weight:700;')
                config['custom_aggregations'][area] = Aggregation(
                    area,
                    config['custom_aggregations'][area],
                ).area
                configureCustomAggregations(area)

        with ui.switch(
            'General Transit Feed Specification (GTFS; scheduled public transport services)',
        ).style('font-weight:700;') as gtfs:
            if 'gtfs_feeds' in config:
                gtfs.value = True
            else:
                gtfs.value = False
                config['gtfs_feeds'] = (
                    'policy_review/gohsc-policy-indicator-checklist.xlsx'
                )
            # Rest of the code remains unchangedon('click', lambda: stepper.set_value('Custom aggregation')):
        with ui.card().bind_visibility_from(
            gtfs,
            'value',
        ):
            ui.label(
                'GTFS feed data is used to evaluate access to public transport stops with regular weekday daytime service. If departure times are not specified in the stop_times.txt file for a specific GTFS feed, if these are not interpolated, or if the interpolation is not accurate, then the feed should be omitted as results will be inaccurate. For cities with no GTFS feeds identified, this section may be omitted.',
            )
            ui.button(
                'Select a sub-folder in the process/data/transit_feeds directory',
                on_click=lambda: locate_file(
                    path='/home/ghsci/process/data/transit_feeds',
                    dict=config['gtfs_feeds'],
                    record='folder',
                ),
            ).props(
                'icon=folder',
            )
            ui.input(
                label="Sub-folder in the 'process/data/transit_feeds' directory containing zipped GTFS feeds",
                on_change=lambda: preview_config.refresh(),
            ).bind_value(config['gtfs_feeds'], 'folder').style(
                'min-width:500px;',
            )
            for feed in [f for f in config['gtfs_feeds'] if f != 'folder']:
                ui.label(feed).style('font-weight:700;')
                ui.input(
                    label='Name of agency that published this data',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['gtfs_feeds'][feed],
                    'gtfs_provider',
                ).style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Year the data was published',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['gtfs_feeds'][feed], 'gtfs_year').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Source URL for the data',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['gtfs_feeds'][feed], 'gtfs_url').style(
                    'min-width:500px;',
                )
                ui.label(
                    'Select the start and end dates of a representative period for analysis, ideally outside school holidays and extreme weather events.  The GTFS feed provided should have scheduled services within this period.',
                )
                ui.label('Analysis start date').style('font-weight:700;')
                with ui.input('Date') as date:
                    with ui.menu().props('no-parent-event') as menu:
                        with ui.date().bind_value(date).bind_value(
                            config['gtfs_feeds'][feed],
                            'start_date_mmdd',
                            backward=lambda date: datetime.strptime(
                                str(date),
                                '%Y%m%d',
                            ).strftime('%Y-%m-%d'),
                            forward=lambda date: datetime.strptime(
                                str(date),
                                '%Y-%m-%d',
                            ).strftime('%Y%m%d'),
                        ):
                            with ui.row().classes('justify-end'):
                                ui.button('Close', on_click=menu.close).props(
                                    'flat',
                                )
                    with date.add_slot('append'):
                        ui.icon('edit_calendar').on(
                            'click',
                            menu.open,
                        ).classes(
                            'cursor-pointer',
                        )
                ui.label('Analysis end date').style('font-weight:700;')
                with ui.input('Date') as date:
                    with ui.menu().props('no-parent-event') as menu:
                        with ui.date().bind_value(date).bind_value(
                            config['gtfs_feeds'][feed],
                            'end_date_mmdd',
                            backward=lambda date: datetime.strptime(
                                str(date),
                                '%Y%m%d',
                            ).strftime('%Y-%m-%d'),
                            forward=lambda date: datetime.strptime(
                                str(date),
                                '%Y-%m-%d',
                            ).strftime('%Y%m%d'),
                        ):
                            with ui.row().classes('justify-end'):
                                ui.button('Close', on_click=menu.close).props(
                                    'flat',
                                )
                    with date.add_slot('append'):
                        ui.icon('edit_calendar').on(
                            'click',
                            menu.open,
                        ).classes(
                            'cursor-pointer',
                        )
                ui.label(
                    'If departure_times within the stop_times.txt file are missing for stops, analysis will be inaccurate unless these are filled in.  In such a case, processing of the GTFS feed will halt with a warning advising the user.  A user could: source alternate data, or fill/interpolate these values themselves.  A function has been provided to perform a linear interpolation according to the provided stop sequence start and end times within each trip_id.  This is an approximation based on the available information, and results may still differ from the actual service frequencies at these stops.  It is the user\'s responsibility to determine if this interpolation is appropriate for their use case.  Enable the following checkbox to interpolate stop_times where these are missing.',
                )
                ui.checkbox(
                    text='Interpolate stop times',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['gtfs_feeds'][feed],
                    'interpolate_stop_times',
                )
        stepper_navigation(stepper)


def configureCustomAggregations(area):
    for key, value in config['custom_aggregations'][area].items():
        if key == 'data':
            ui.label('Data source')
            switch = ui.toggle(
                [
                    'OpenStreetMap',
                    'Custom',
                ],
                value=['OpenStreetMap', 'Custom'][
                    not config['custom_aggregations'][area]['data'].startswith(
                        'OSM',
                    )
                ],
                clearable=False,
            ).style(
                'font-weight:700;',
            )
            with ui.card().style('width: 100%').bind_visibility_from(
                switch,
                'value',
                value='Custom',
            ):
                ui.button(
                    'Select spatial data containing polygons in the process/data folder',
                    on_click=lambda area=area: locate_file(
                        dict=config['custom_aggregations'][area],
                        record='data',
                    ),
                ).props(
                    'icon=folder',
                )
                ui.input(
                    label='data',
                    placeholder=value,
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['custom_aggregations'][area],
                    'data',
                    backward=lambda path: path.replace(
                        '/home/ghsci/process/data/',
                        '',
                    ),
                ).style(
                    'min-width:500px;',
                )
                # ui.input(
                #     label='Field used as unique identifier for each polygon',
                #     placeholder=value,
                #     on_change=lambda: preview_config.refresh(),
                # ).bind_value(
                #     config['custom_aggregations'][area],
                #     'id',
                # ).style(
                #     'min-width:500px;',
                # )
                ui.input(
                    label='A list of column field names to be retained',
                    placeholder=value,
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['custom_aggregations'][area],
                    'keep_columns',
                ).style(
                    'min-width:500px;',
                )
            with ui.card().style('width: 100%').bind_visibility_from(
                switch,
                'value',
                value='OpenStreetMap',
            ):
                ui.label(
                    'OpenStreetMap attribute to be queried, e.g. "building"',
                )
                ui.input(
                    label='data',
                    placeholder=value,
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['custom_aggregations'][area],
                    'keep_columns',
                ).bind_value(
                    config['custom_aggregations'][area],
                    'data',
                    backward=lambda path: path.replace(
                        'OSM:',
                        '',
                    ).replace(' is not NULL', ''),
                    forward=lambda path: f'OSM:{path} is not NULL',
                ).style(
                    'min-width:500px;',
                )
        elif key == 'keep_columns':
            pass
        elif key == 'aggregation_source':
            ui.label(
                'The indicator layer to be aggregated ("point" or "grid").  Aggregation is based on the average of intersecting results, unless the agg_distance parameter is defined.',
            )
            ui.toggle(
                ['point', 'grid'],
                on_change=lambda: preview_config.refresh(),
            ).bind_value(
                config['custom_aggregations'][area],
                'aggregation_source',
            )
        elif key == 'aggregate_within_distance':
            ui.label(
                'The distance in metres within which to aggregate results.  If not specified, aggregation will be based on the average of intersecting results.',
            )
            ui.number(
                label='Metres',
                placeholder=value,
                min=0,
                on_change=lambda: preview_config.refresh(),
            ).bind_value(
                config['custom_aggregations'][area],
                'aggregate_within_distance',
            ).style(
                'min-width:500px;',
            )
        elif key == 'weight':
            ui.toggle(
                {
                    'pop_est': 'Weight by population',
                    None: 'Unweighted',
                },
                on_change=lambda: preview_config.refresh(),
            ).bind_value(
                config['custom_aggregations'][area],
                'weight',
            )
        else:
            ui.input(
                label=key,
                placeholder=value,
                on_change=lambda: preview_config.refresh(),
            ).bind_value(
                config['custom_aggregations'][area],
                key,
            ).style(
                'width:100%;',
            )


def configure_reporting(stepper):
    with ui.step('Reporting'):
        ui.label(
            'The following parameters are used to configure the reporting of the study region configuration and results.  These are not used in the analysis, but are important for documenting the study region and results.',
        )
        with ui.stepper().props('vertical').classes(
            'w-full',
        ) as report_stepper:
            with ui.step('General options').on(
                'click',
                lambda: report_stepper.set_value('General options'),
            ):
                ui.label(
                    'Reporting templates to be used (depending on analyses conducted)',
                ).style('font-weight: 700;')
                with ui.row():
                    policy_report = ui.checkbox(
                        text='Policy indicators',
                        value='policy',
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(policy_templates, 'policy')
                    spatial_report = ui.checkbox(
                        text='Spatial indicators',
                        value='spatial',
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(policy_templates, 'spatial')
                    policy_spatial_report = ui.checkbox(
                        text='Policy and spatial indicators',
                        value='policy_spatial',
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(policy_templates, 'policy_spatial')
                ui.label(
                    'Analysis and reporting has been validated as publication ready?',
                ).style('font-weight: 700;')
                ui.checkbox(
                    '',
                    value=True,
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['reporting'], 'publication_ready')
                ui.label(
                    'Which basemap should be used for the report context map?',
                ).style('font-weight: 700;')
                ui.toggle(
                    {
                        'satellite': 'Satellite (recent cloudless composite image of Sentinel-2 satellite imagery to view the urban fabric, https://s2maps.eu by EOX IT Services GmbH)',
                        'osm': 'OpenStreetMap (a light coloured thematic map based on OpenStreetMap with labels)',
                        'streets': 'Streets (a light coloured thematic map based on OpenStreetMap without labels, displaying streets)',
                    },
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['reporting'],
                    'study_region_context_basemap',
                )
                ui.label(
                    'DOI (you can register this once you are publication ready, using a repository like Zenodo or Figshare)',
                ).style('font-weight: 700;')
                ui.input(
                    label='DOI URL, e.g. https://doi.org/10.25439/rmt.19586770.v1',
                ).bind_value(config['reporting'], 'doi').style(
                    'min-width:500px;',
                )
                stepper_navigation(report_stepper)
            with ui.step('Images').on(
                'click',
                lambda: report_stepper.set_value('Images'),
            ):
                ui.label(
                    'Report images are to be saved in the configuration/assets directory, and may be configured for inclusion in reports here.',
                )
                for image in config['reporting']['images']:
                    ui.label(
                        f'Image {image} {image_ratios[image]}',
                    ).style('font-weight: 700;')
                    ui.input(
                        label='Path to the image relative to the project directory',
                        placeholder='image_name.jpg',
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(
                        config['reporting']['images'][image],
                        'file',
                    ).style(
                        'min-width:500px;',
                    )
                    ui.input(
                        label='Description for the image',
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(
                        config['reporting']['images'][image],
                        'description',
                    ).style(
                        'min-width:500px;',
                    )
                    ui.input(
                        'Image credit, e.g. Photographer Name, Year',
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(
                        config['reporting']['images'][image],
                        'credit',
                    ).style(
                        'min-width:500px;',
                    )
                stepper_navigation(report_stepper)
            with ui.step('Languages').on(
                'click',
                lambda: report_stepper.set_value('Languages'),
            ):
                with ui.stepper().props('vertical').classes(
                    'w-full',
                ) as language_stepper:
                    for language in config['reporting']['languages']:
                        with ui.step(language).on(
                            'click',
                            lambda language=language: language_stepper.set_value(
                                language,
                            ),
                        ):
                            ui.input(
                                label='City name',
                                on_change=lambda: preview_config.refresh(),
                            ).bind_value(
                                config['reporting']['languages'][language],
                                'name',
                            ).style(
                                'min-width:500px;',
                            )
                            ui.input(
                                label='Country name',
                                on_change=lambda: preview_config.refresh(),
                            ).bind_value(
                                config['reporting']['languages'][language],
                                'country',
                            ).style(
                                'min-width:500px;',
                            )
                            ui.textarea(
                                label='Summary (update this after first generating reports and reviewing results)',
                                on_change=lambda: preview_config.refresh(),
                            ).bind_value(
                                config['reporting']['languages'][language],
                                'summary',
                            ).style(
                                'min-width:500px;',
                            )
                            # with ui.stepper().props('vertical').classes('w-full') as context_stepper:
                            for i, step in enumerate(context_steps):
                                # with ui.step(f'{language} - {step}').on('click', lambda step=f'{language} - {step}': context_stepper.set_value(step)):
                                ui.textarea(
                                    label=step,
                                    placeholder=context_steps[step],
                                    on_change=lambda: preview_config.refresh(),
                                ).bind_value(
                                    config['reporting']['languages'][language][
                                        'context'
                                    ][i][step][0],
                                    'summary',
                                ).style(
                                    'min-width:500px;',
                                )
                                ui.input(
                                    label=f'{step} citation',
                                    on_change=lambda: preview_config.refresh(),
                                ).bind_value(
                                    config['reporting']['languages'][language][
                                        'context'
                                    ][i][step][1],
                                    'source',
                                ).style(
                                    'min-width:500px;',
                                )
                                # stepper_navigation(context_stepper)
                            for exception in config['reporting']['exceptions'][
                                language
                            ]:
                                ui.input(
                                    label=f'{exception}',
                                    placeholder=exception,
                                    on_change=lambda: preview_config.refresh(),
                                ).bind_value(
                                    config['reporting']['exceptions'][
                                        language
                                    ],
                                    exception,
                                ).style(
                                    'min-width:500px;',
                                )
                            # ui.button('Add a new exception', on_click=lambda: add_exception(exception, language)).props('flat')
                            stepper_navigation(language_stepper)
                stepper_navigation(report_stepper)
        stepper_navigation(stepper, next=False)


@ui.page('/')
async def main_page():
    with ui.row():
        with ui.column().classes('w-1/2'):
            with ui.stepper().props(
                'v-model="step" header-nav ref="stepper" color="primary" animated',
            ).classes('w-full') as stepper:
                configure_study_region(stepper)
                configure_boundary(stepper)
                configure_population(stepper)
                configure_openstreetmap(stepper)
                configure_network(stepper)
                configure_urban_region(stepper)
                configure_optional(stepper)
                configure_reporting(stepper)
        with ui.column().style('max-width: 40%'):
            ui.label('Study region configuration preview').style(
                'font-weight:700;',
            )
            preview_config()
        # with ui.column():
        #     ui.code(countries, language='json')


# preview_config()
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
