"""Sketch a configuration GUI for a study region."""

import json
import os
from pathlib import Path

import yaml
from ghsci import Region
from nicegui import ui

template_path = Path(
    '/home/ghsci/process/configuration/assets/region_template.yml',
)
country_codes_path = Path('/home/ghsci/process/data/flags/countries.json')
config_path = '/home/ghsci/process/configuration'


# with open(template_path) as f:
#     region_template = yaml.safe_load(f)

with open(country_codes_path) as f:
    country_codes = {v: k for k, v in json.load(f).items()}


def load_yaml(study_region=None):
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
#         config = load_yaml(study_region)
#         # Initialize attributes based on the keys in the region_template
#         for key, value in config.items():
#             setattr(self, key, config.get(key, value))


config = load_yaml(Region('example_ES_Las_Palmas_2023'))
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


@ui.refreshable
def preview_config():
    """Preview the configuration file."""
    with ui.card().tight():
        if str(config['year']).isdigit():
            config['year'] = int(config['year'])
        if config['country'] in country_codes.keys():
            config['country_code'] = country_codes[config['country']]
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
    codes = [k for k, v in country_codes.items() if v == country]
    if len(codes) > 0:
        return codes[0]
    return 'Two-letter country code'


# def add_exception(exception, language):
#     """Add an exception to the configuration file."""
#     ui.input(
#         label=f"{exception}",
#         placeholder=exception,
#         on_change=lambda: preview_config.refresh(),
#     ).bind_value(config['reporting']['exceptions'][language], exception).style('min-width:500px;')

with ui.row():
    with ui.column().classes('w-1/2'):
        with ui.stepper().props('vertical').classes('w-full') as stepper:
            # for key, value in config.items():
            with ui.step('Study region details').on(
                'click',
                lambda: stepper.set_value('Study region details'),
            ):
                # with ui.expansion(text='Expand to view and edit', group='group')
                ui.input(
                    label='Full study region name',
                    placeholder='Las Palmas de Gran Canaria',
                    # validation={'Input too long': lambda value: len(value) < 50},
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'name').style('min-width:500px;')
                ui.select(
                    options=list(sorted(country_codes.keys())),
                    label='Select country from list or enter customised name',
                    with_input=True,
                    new_value_mode='add',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'country').style('min-width:500px;')
                ui.input(
                    label='Two character country code (ISO3166 Alpha-2 code)',
                    placeholder=get_country_code(config['country']),
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'country_code').style('min-width:500px;')
                ui.input(
                    label='Target year for analysis',
                    placeholder=2024,
                    validation={
                        'Must be a 4-digit numeric year (e.g. 2023)': lambda value: type(
                            value,
                        )
                        is int
                        and value > 999
                        and value < 10000,
                    },
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'year').style('min-width:300px;')
                # ui.number(
                #     label='Target year for analysis',
                #     format='%d',
                #     placeholder=2023,
                #     min=0,
                #     max=2100,
                #     precision=0,
                #     on_change=lambda: preview_config.refresh(),
                # ).bind_value(config, 'year').style('min-width:300px;')
                ui.input(
                    label='Country GDP classification, e.g. lower-middle',
                    placeholder='High-income',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['country_gdp'], 'classification').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Citation for the GDP classification, e.g. The World Bank. 2020. World Bank country and lending groups. https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups',
                    placeholder='The World Bank. 2020. World Bank country and lending groups. https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['country_gdp'], 'citation').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Notes',
                    placeholder='Any additional aspects of this study region or analysis that should be noted.',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'notes').style('min-width:500px;')
                policy_review_switch = ui.switch('Policy review (optional)')
                if config['policy_review'].endswith(
                    'gohsc-policy-indicator-checklist.xlsx',
                ):
                    policy_review_switch.value = True
                ui.input(
                    label='Path to the policy review file',
                    placeholder='policy_review/gohsc-policy-indicator-checklist.xlsx',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'policy_review').style(
                    'min-width:500px;',
                ).bind_visibility_from(
                    policy_review_switch,
                    'value',
                )
                stepper_navigation(stepper, back=False)
            with ui.step('Projected coordinate reference system (CRS)').on(
                'click',
                lambda: stepper.set_value(
                    'Projected coordinate reference system (CRS)',
                ),
            ):
                ui.markdown(
                    'Please specify a suitable [projected coordinate reference system](https://en.wikipedia.org/wiki/Projected_coordinate_system#Examples_of_projected_CRS) (CRS; having units in metres) for this study region. Search [https://epsg.io](https://epsg.io) or [https://spatialreference.org/](https://spatialreference.org/) for a suitable projection noting its name (e.g. ), standard (e.g. EPSG) and spatial reference identifier code (SRID).  This will be used for analysis of accessibility using units of metres.',
                )
                ui.input(
                    label='CRS name',
                    placeholder='WGS 84 / UTM zone 28N',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['crs'], 'name').style('min-width:500px;')
                ui.input(
                    label='Acronym of the standard catalogue defining this CRS, eg. EPSG',
                    placeholder='EPSG',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['crs'], 'standard').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Spatial reference identifier (SRID) integer for this CRS and standard',
                    placeholder='EPSG',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['crs'], 'srid').style('min-width:500px;')
                stepper_navigation(stepper)
            with ui.step('Study region boundary data').on(
                'click',
                lambda: stepper.set_value('Study region boundary data'),
            ):
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
                ui.input(
                    label='Boundary data path',
                    placeholder='/path/to/boundary/data.shp',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['study_region_boundary'], 'data').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='The name of the source of this data.',
                    placeholder='Centro Nacional de Información Geográfica',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['study_region_boundary'], 'source').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Publication date for study region area data source, using the format yyyy-mm-dd. e.g. 2019-02-01',
                    placeholder='2019-02-01',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['study_region_boundary'],
                    'publication_date',
                ).style(
                    'min-width:500px;',
                )
                ui.input(
                    label='URL for the source dataset, or its provider, e.g. https://datos.gob.es/en/catalogo/e00125901-spaignllm',
                    placeholder='https://datos.gob.es/en/catalogo/e00125901-spaignllm',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['study_region_boundary'], 'url').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Licence for the data, e.g. CC-BY-4.0',
                    placeholder='CC-BY-4.0',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['study_region_boundary'], 'licence').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Whether the provided study region boundary will be further restricted to an urban area defined by its intersection with a linked urban region dataset (see urban_region), e.g. true',
                    placeholder='true',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['study_region_boundary'],
                    'ghsl_urban_intersection',
                ).style(
                    'min-width:500px;',
                )
                ui.input(
                    label='A formal citation for this data, e.g. "Instituto Geográfico Nacional (2019). Base de datos de divisiones administrativas de España. https://datos.gob.es/en/catalogo/e00125901-spaignllm."',
                    placeholder='Instituto Geográfico Nacional (2019). Base de datos de divisiones administrativas de España. https://datos.gob.es/en/catalogo/e00125901-spaignllm',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['study_region_boundary'],
                    'citation',
                ).style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Notes',
                    placeholder='manually extracted municipal boundary for Las Palmas de Gran Canaria in WGS84 from the downloaded zip file "lineas_limite.zip" using QGIS to a geojson file for demonstration purposes.',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['study_region_boundary'], 'notes').style(
                    'min-width:500px;',
                )

                # Rest of the code remains unchangedon('click', lambda: stepper.set_value('Custom aggregation')):
                ui.label(
                    'Optional custom aggregation to additional areas of interest (e.g. neighbourhoods, suburbs, specific developments).  This has not yet been implemented in the graphical user interface set up, but may be configured by manually editing a configuration file following provided examples.',
                )
                # for key, value in config['custom_aggregations'].items():
                #     ui.input(
                #         label=key,
                #         placeholder=value,
                #         on_change=lambda: preview_config.refresh()
                #     ).bind_value(config['custom_aggregations'], key)
                stepper_navigation(stepper)
            with ui.step('Population data').on(
                'click',
                lambda: stepper.set_value('Population data'),
            ):
                ui.input(
                    label='Name of the population data',
                    placeholder='Global Human Settlements population data 2020 (EU JRC, 2022)',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'name').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Path relative to project data directory to folder containing tifs, or to vector file',
                    placeholder='population_grids/Example/GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R5_C23',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'data_dir').style(
                    'min-width:500px;',
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
                ui.input(
                    label='URL for where this data was sourced from',
                    placeholder='https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2022A/GHS_POP_E2020_GLOBE_R2022A_54009_100/V1-0/tiles/GHS_POP_E2020_GLOBE_R2022A_54009_100_V1_0_R6_C17.zip',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'source_url').style(
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
                ui.input(
                    label='The date you retrieved it (yyyymmdd).  This can be useful to record as data can be subject to revision.  e.g. 20230627',
                    placeholder='20230222',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'date_acquired').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Licence, e.g. "CC BY 4.0"',
                    placeholder='CC BY 4.0',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'licence').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Citation, e.g. "Schiavina, M; Freire, S; Carioli, A., MacManus, K (2023): GHS-POP R2023A - GHS population grid multitemporal (1975-2030). European Commission, Joint Research Centre (JRC) [Dataset] doi: 10.2905/D6D86A90-4351-4508-99C1-CB074B022C4A"',
                    placeholder='Schiavina, Marcello; Freire, Sergio; MacManus, Kytt (2022): GHS-POP R2022A - GHS population grid multitemporal (1975-2030). European Commission, Joint Research Centre (JRC) [Dataset] doi: 10.2905/D6D86A90-4351-4508-99C1-CB074B022C4A',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['population'], 'citation').style(
                    'min-width:500px;',
                )
                stepper_navigation(stepper)
            with ui.step('OpenStreetMap data').on(
                'click',
                lambda: stepper.set_value('OpenStreetMap data'),
            ):
                ui.input(
                    label='Path relative to project data directory to OpenStreetMap data file',
                    placeholder='OpenStreetMap/Example/iran_51.092,35.567_51.603,35.829.osm.pbf',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['OpenStreetMap'], 'data_dir').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='The source of the OpenStreetMap data (e.g. Planet OSM, GeoFabrik or OpenStreetMap.fr)',
                    placeholder='OpenStreetMap.fr',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['OpenStreetMap'], 'source').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='When it was published (yyyymmdd), e.g. 20230627',
                    placeholder='20230221',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(
                    config['OpenStreetMap'],
                    'publication_date',
                ).style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Licence (which is most likely ODbL for OpenStreetMap data published since 2012)',
                    placeholder='ODbL',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['OpenStreetMap'], 'licence').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='The URL from where it was downloaded',
                    placeholder='https://download.openstreetmap.fr/extracts/africa/spain/canarias/las_palmas-latest.osm.pbf',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['OpenStreetMap'], 'url').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='An optional note regarding this data',
                    placeholder='This is configured with a derived excerpt from the larger OpenStreetMap dataset for Las Canarias based on the 1600m buffered municipal boundary of Las Palmas de Gran Canaria to reduce file size for demonstration purposes.',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['OpenStreetMap'], 'note').style(
                    'min-width:500px;',
                )
                stepper_navigation(stepper)
            with ui.step('Pedestrian street network data').on(
                'click',
                lambda: stepper.set_value('Pedestrian street network data'),
            ):
                # The following includes parameters for a basic analysis.  Additional advanced configuration options are available by editing a configuration file in a text editor according to the provided examples.
                ui.label(
                    'Tolerance in metres for cleaning intersections.  If not providing your own data for evaluating intersection density (see below), this is an important methodological choice.  The chosen parameter should be robust to a variety of network topologies in the city being studied.  See https://github.com/gboeing/osmnx-examples/blob/main/notebooks/04-simplify-graph-consolidate-nodes.ipynb',
                )
                ui.label(
                    'Optionally, data for evaluating intersections can be provided as an alternative to deriving intersections from OpenStreetMap (where available, this may be preferable).  See the provided example configuration file for directions on how to do this.',
                )
                for key, value in config['network'].items():
                    ui.input(
                        label=key,
                        placeholder=value,
                        on_change=lambda: preview_config.refresh(),
                    ).bind_value(config['network'], key)
                stepper_navigation(stepper)
            with ui.step('Urban region data').on(
                'click',
                lambda: stepper.set_value('Urban region data'),
            ):
                ui.input(
                    label='Name for the urban region data, e.g. "Global Human Settlements urban centres: 2015 (EU JRC, 2019)"',
                    placeholder='Global Human Settlements urban centres: 2015 (EU JRC, 2019; Las Palmas de Gran Canaria only)',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['urban_region'], 'name').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Path to data relative to the project data directory, e.g. "urban_regions/GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.gpkg"',
                    placeholder='urban_regions/Example/GHS_STAT_UCDB2015MT_GLOBE_R2019A_V1_2.gpkg',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['urban_region'], 'data_dir').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Licence, e.g. CC BY 4.0',
                    placeholder='CC BY 4.0',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['urban_region'], 'licence').style(
                    'min-width:500px;',
                )
                ui.input(
                    label='Citation for this data, this has been pre-filled for the GHSL UCDB (2019), but change as required if using',
                    placeholder='Florczyk, A. et al. (2019): GHS Urban Centre Database 2015, multitemporal and multidimensional attributes, R2019A. European Commission, Joint Research Centre (JRC). https://data.jrc.ec.europa.eu/dataset/53473144-b88c-44bc-b4a3-4583ed1f547e',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config['urban_region'], 'citation').style(
                    'min-width:500px;',
                )
                ui.label(
                    'A list of additional covariates can be optionally linked for cities included in the GHSL UCDB.  These may be edited in a text editor according to the provided examples.',
                )
                ui.input(
                    label='Query used to identify the specific urban region relevant for this region in the Urban Centres database',
                    placeholder='GHS:UC_NM_MN==\'Las Palmas de Gran Canaria\' and CTR_MN_NM==\'Spain\'',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'urban_query').style('min-width:500px;')
                ui.input(
                    label='Additional study region summary covariates to be optionally linked. This is designed to retrieve the list of covariates specifies in the \'urban_region\' configuration, either from the configured Global Human Settlements Layer data (enter "urban_query"), or from a CSV file (provide a path relative to the project data directory)',
                    placeholder='urban_query',
                    on_change=lambda: preview_config.refresh(),
                ).bind_value(config, 'covariate_data').style(
                    'min-width:500px;',
                )
                stepper_navigation(stepper)
            with ui.step('Reporting').on(
                'click',
                lambda: stepper.set_value('Reporting'),
            ):
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
                                        config['reporting']['languages'][
                                            language
                                        ],
                                        'name',
                                    ).style(
                                        'min-width:500px;',
                                    )
                                    ui.input(
                                        label='Country name',
                                        on_change=lambda: preview_config.refresh(),
                                    ).bind_value(
                                        config['reporting']['languages'][
                                            language
                                        ],
                                        'country',
                                    ).style(
                                        'min-width:500px;',
                                    )
                                    ui.textarea(
                                        label='Summary (update this after first generating reports and reviewing results)',
                                        on_change=lambda: preview_config.refresh(),
                                    ).bind_value(
                                        config['reporting']['languages'][
                                            language
                                        ],
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
                                            config['reporting']['languages'][
                                                language
                                            ]['context'][i][step][0],
                                            'summary',
                                        ).style(
                                            'min-width:500px;',
                                        )
                                        ui.input(
                                            label=f'{step} citation',
                                            on_change=lambda: preview_config.refresh(),
                                        ).bind_value(
                                            config['reporting']['languages'][
                                                language
                                            ]['context'][i][step][1],
                                            'source',
                                        ).style(
                                            'min-width:500px;',
                                        )
                                        # stepper_navigation(context_stepper)
                                    for exception in config['reporting'][
                                        'exceptions'
                                    ][language]:
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
    with ui.column().style('max-width: 40%'):
        ui.label('Study region configuration preview')
        preview_config()
    # with ui.column():
    #     ui.code(country_codes, language='json')


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
