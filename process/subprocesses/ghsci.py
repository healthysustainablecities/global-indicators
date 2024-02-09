"""
Global Healthy & Sustainable City Indicators.

A tool for calculating and reporting on spatial urban indicators to support research, planning and advocacy for healthy and sustainable cities.

Example usage to construct an r Region object containing the externally defined configuration for the study region corresponding to the codename, that may be used in further analyses as required:

import ghsci
codename = 'example_ES_Las_Palmas_2023'
r = ghsci.Region(codename)
"""

import os
import shutil
import sys
import time

os.environ[
    'USE_PYGEOS'
] = '0'  # preparation for geopandas 0.14 release which will migrate to using Shapely 2.0, that incorporates pygeos
import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from geoalchemy2 import Geometry
from sqlalchemy import create_engine, inspect, text


def configure(codename: str = None) -> None:
    """Initialise new study region configuration file."""
    sys.path.append('/home/ghsci/process')
    from configure import configuration as configure

    configure(codename)


def initialise_configuration():
    try:
        print(
            'Initialising project configuration files in the process/configuration folder...',
        )
        for folder, subfolders, files in os.walk('./configuration/templates'):
            for file in files:
                path_file = os.path.join(folder, file)
                if os.path.exists(f'./configuration/{file}'):
                    print(f'\t- {file} exists.')
                else:
                    shutil.copyfile(
                        path_file, path_file.replace('templates/', ''),
                    )
                    print(f'\t- created {file}')
    except Exception as e:
        raise Exception(f'An error occurred: {e}')


def load_yaml(yml):
    """Load yaml file and return as dictionary."""
    if os.path.isfile(yml):
        with open(yml) as f:
            try:
                configuration = yaml.safe_load(f)
            except Exception as e:
                sys.exit(
                    f'\n\nError: {e}\n\nLoading of configuration file {yml} failed.  Please confirm that configuration has been completed for this city, consulting the provided example configuration files as required.\n\nFor more details, enter:\nconfigure\n\nFurther assistance may be requested by logging an issue at:\nhttps://github.com/global-healthy-liveable-cities/global-indicators/issues\n\n',
                )
        if 'description' in configuration:
            # remove description from yaml, if present, storing for reference
            configuration = configuration.pop('description', None)
        return configuration
    elif os.path.splitext(os.path.basename(yml))[0] == 'None':
        sys.exit(
            'This script requires a study region code name corresponding to .yml files '
            'in configuration/regions be provided as an argument:\n\n'
            'configure <codename>\n'
            'analysis <codename>\n'
            'generate <codename>\n'
            'compare <reference> <comparison>\n\n'
            'Alternatively, each of the above commands can be run without a codename to view usage instructions.\n\n'
            'Each of the steps (configure, analysis, generate, compare) needs to be successfully completed before moving to the next.\n\n'
            'The provided example for Las Palmas de Gran Canaria, Spain, may be run by using the codename: example_ES_Las_Palmas_2023\n\n'
            f'The code names for all currently configured regions are {region_names}\n',
        )
    else:
        sys.exit(
            f'\n\nThe configuration file {yml} could not be located.  Please ensure that the configuration files have been initialised. For more details, enter:\nconfigure\n\n',
        )


# get names of regions for which configuration files exist
def get_region_names() -> list:
    region_names = [
        x.split('.yml')[0]
        for x in os.listdir(f'{config_path}/regions')
        if x.endswith('.yml')
    ]
    return region_names


def region_boundary_blurb_attribution(
    name, study_region_boundary, urban_region, urban_query,
):
    """Generate a blurb and attribution for the study region boundary."""
    sources = []
    if (
        study_region_boundary == 'urban_query'
        or type(study_region_boundary) == dict
        and 'data' in study_region_boundary
        and study_region_boundary['data'] == 'urban_query'
    ):
        blurb_1 = f"The study region boundary was defined using an SQL query that was run using ogr2ogr to import the corresponding features from {urban_region['name']} to the database."
        sources.append(
            f"{urban_region['name']} under {urban_region['licence']}",
        )
    else:
        blurb_1 = f"The study region boundary was defined and imported to the database using ogr2ogr with data sourced from [{study_region_boundary['source']} ({format_date(study_region_boundary['publication_date'],'%Y')})]({study_region_boundary['url']})."
        sources.append(
            f"{study_region_boundary['source']} under {study_region_boundary['licence']}",
        )
    if (
        'ghsl_urban_intersection' in study_region_boundary
        and study_region_boundary['ghsl_urban_intersection']
    ):
        blurb_2 = f""" The urban portion of {name} was identified using the intersection of the study region boundary and urban regions sourced from {urban_region['name']} published as {urban_region['citation']}."""
        sources.append(
            f"{urban_region['name']} under {urban_region['licence']}",
        )
    else:
        blurb_2 = f""" This study region boundary was taken to represent the {name} urban region."""
    if urban_query:
        blurb_3 = f""" The SQL query used to extract urban areas from {urban_region['name']} was: {urban_query}."""
    else:
        blurb_3 = ''
    return {
        'blurb': blurb_1 + blurb_2 + blurb_3,
        'sources': set(sources),
    }


def network_description(region_config):
    blurbs = []
    blurbs.append(
        f"""The [OSMnx](https://geoffboeing.com/2016/11/osmnx-python-street-networks/#) software package was used to derive an undirected [non-planar](https://geoffboeing.com/publications/osmnx-complex-street-networks/) pedestrian network of edges (lines) and nodes (vertices, or intersections) for the buffered study region area using the following custom definition: **{region_config['network']['pedestrian']}**.  This definition was used to retrieve matching data via Overpass API for {region_config['OpenStreetMap']['publication_date']}.""",
    )
    if region_config['network']['osmnx_retain_all']:
        blurbs.append(
            'The network was extracted using OSMnx with the "retain_all" parameter set to __True__.  This meant that all network segments were retained, including those that were not connected to the main network.  This could mean that isolated network segments could be included, which could be problematic for evaluating accessibility if these are not truly disconnected in reality; this should be considered when reviewing results.',
        )
    else:
        blurbs.append(
            'The network was extracted using OSMnx with the "retain_all" parameter set to __False__.  This meant that only the main connected network was retained. In many circumstances this is the appropriate setting, however please ensure this is appropriate for your study region, as networks on real islands may be excluded.',
        )
    if region_config['network']['polygon_iteration']:
        blurb = 'To account for multiple disconnected pedestrian networks within the study region (for example, as may occur in a city spanning several islands), the network was extracted iteratively for each polygon of the study region boundary multipolygon. This meant that the network was extracted for each polygon, and then the resulting networks were combined to form the final network.'
        if type(region_config['network']['connection_threshold']) == int:
            blurb = f"""{blurb}.  Network islands were only included if meeting a minimum total network distance threshold set at {region_config['network']['connection_threshold']} metres. """
        blurbs.append(blurb)
    blurbs.append(
        f"""The OSMnx [consolidate_intersections()](https://osmnx.readthedocs.io/en/stable/osmnx.html#osmnx.simplification.consolidate_intersections) function was used to prepare a dataset of cleaned intersections with three or more legs, using a tolerance parameter of {region_config['network']['intersection_tolerance']} to consolidate network nodes within this distance as a single node.  This ensures that intersections that exist for representational or connectivity purposes (for example a roundabout, that may be modelled with multiple nodes but in effect is a single intersections) do not inflate estimates when evaluating street connectivity for pedestrians.""",
    )
    blurbs.append(
        'The derived pedestrian network nodes and edges, and the dataset of cleaned intersections were stored in the PostGIS database.',
    )
    return ' '.join(blurbs)


def get_analysis_report_region_configuration(region_config, settings):
    """Generate the region configuration for the analysis report."""
    region_config['study_buffer'] = settings['project']['study_buffer']
    region_config['study_region_blurb'] = region_boundary_blurb_attribution(
        region_config['name'],
        region_config['study_region_boundary'],
        region_config['urban_region'],
        region_config['urban_query'],
    )
    region_config['network']['pedestrian'] = settings['network_analysis'][
        'pedestrian'
    ]
    region_config['network']['description'] = network_description(
        region_config,
    )
    if 'data_type' in region_config['population'] and region_config[
        'population'
    ]['data_type'].startswith('vector'):
        region_config[
            'population_grid_setup'
        ] = f'used the field "{region_config["population"]["vector_population_data_field"]}" to source estimates'
    else:
        region_config['population_grid_setup'] = (
            f'grid had a resolution of {region_config["population"]["resolution"]} m',
        )
    return region_config


def format_date(date, format='%Y-%m-%d'):
    """Format date as string."""
    from datetime import date as datetime_date

    if type(date) is datetime_date:
        return date.strftime(format)
    else:
        return str(date)


class Region:
    """A class for a study region (e.g. a city) that is used to load and store parameters contained in a yaml configuration file in the configuration/regions folder."""

    def __init__(self, name):
        self.codename = name
        self.config = load_yaml(f'{config_path}/regions/{name}.yml')
        self._check_required_configuration_parameters()
        self.name = self.config['name']
        self.config = self._region_dictionary_setup(folder_path)
        self.config['data_check_failures'] = self._run_data_checks()
        self.engine = self.get_engine()
        self.tables = self.get_tables()
        self.log = f"{self.config['region_dir']}/__{self.name}__{self.codename}_processing_log.txt"
        self.header = f"\n{self.name} ({self.codename})\n\nOutput directory:\n  {self.config['region_dir'].replace('/home/ghsci/','')}\n"

    def _check_required_configuration_parameters(
        self, required=['name', 'year', 'country'],
    ):
        """Check required parameters are configured."""
        for key in required:
            if key not in self.config or self.config[key] is None:
                sys.exit(
                    f'\nThe required parameter "{key}" has not yet been configured in {self.codename}.yml.  Please check the configured settings before proceeding.\n',
                )

    def _region_dictionary_setup(self, folder_path):
        """Set up region configuration dictionary."""
        codename = self.codename
        r = self.config.copy()
        r['authors'] = settings['documentation']['authors']
        study_buffer = settings['project']['study_buffer']
        units = settings['project']['units']
        buffered_urban_study_region = (
            f'urban_study_region_{study_buffer}{units}'
        )
        r['crs_srid'] = f"{r['crs']['standard']}:{r['crs']['srid']}"
        data_path = f'{folder_path}/process/data'
        r[
            'region_dir'
        ] = f'{folder_path}/process/data/_study_region_outputs/{codename}'
        if r['study_region_boundary']['data'] != 'urban_query':
            r['study_region_boundary'][
                'data'
            ] = f"{data_path}/{r['study_region_boundary']['data']}"
        r['urban_region'] = self._region_data_setup(
            codename, r, 'urban_region', data_path,
        )
        r['buffered_urban_study_region'] = buffered_urban_study_region
        r['db'] = codename.lower()
        r[
            'dbComment'
        ] = f'Liveability indicator data for {codename} {r["year"]}.'
        r['db_host'] = settings['sql']['db_host']
        r['db_port'] = settings['sql']['db_port']
        r['db_user'] = settings['sql']['db_user']
        r['db_pwd'] = settings['sql']['db_pwd']
        r['population'] = self._region_data_setup(
            codename, r, 'population', data_path,
        )
        r['population_grid_field'] = 'pop_est'
        if r['population']['data_type'].startswith('raster'):
            resolution = f"{r['population']['resolution'].replace(' ', '')}_{r['population']['year_target']}".lower()
        elif r['population']['data_type'].startswith('vector'):
            resolution = f"{r['population']['alias']}_{r['population']['vector_population_data_field']}".lower()
            r[
                'population_grid_field'
            ] = f"pop_est_{r['population']['vector_population_data_field'].lower()}"
        r['population_grid'] = f'population_{resolution}'.lower()
        if 'population_denominator' not in r['population']:
            r['population']['population_denominator'] = r[
                'population_grid_field'
            ].lower()
        else:
            r['population']['population_denominator'] = r['population'][
                'population_denominator'
            ].lower()
        r['population'][
            'crs_srid'
        ] = f'{r["population"]["crs_standard"]}:{r["population"]["crs_srid"]}'
        r['OpenStreetMap'] = self._region_data_setup(
            codename, r, 'OpenStreetMap', data_path,
        )
        r['osm_prefix'] = f"osm_{r['OpenStreetMap']['publication_date']}"
        r['OpenStreetMap'][
            'osm_region'
        ] = f'{r["region_dir"]}/{codename}_{r["osm_prefix"]}.pbf'
        r['codename_poly'] = f'{r["region_dir"]}/poly_{r["db"]}.poly'
        if 'osmnx_retain_all' not in r['network']:
            r['network']['osmnx_retain_all'] = False
        if 'osmnx_retain_all' not in r['network']:
            r['network']['osmnx_retain_all'] = False
        if 'buffered_region' not in r['network']:
            r['network']['buffered_region'] = True
        if 'polygon_iteration' not in r['network']:
            r['network']['polygon_iteration'] = False
        if 'connection_threshold' not in r['network']:
            r['network']['connection_threshold'] = None
        if (
            'intersections' in r['network']
            and r['network']['intersections'] is not None
        ):
            intersections = os.path.splitext(
                os.path.basename(r['network']['intersections']['data']),
            )[0]
            r['intersections_table'] = f'intersections_{intersections}'
        else:
            r[
                'intersections_table'
            ] = f"intersections_osmnx_{r['network']['intersection_tolerance']}m"
        r['gpkg'] = f'{r["region_dir"]}/{codename}_{study_buffer}m_buffer.gpkg'
        r['point_summary'] = 'indicators_sample_points'
        r['grid_summary'] = f'indicators_{resolution}'
        r['city_summary'] = 'indicators_region'
        if 'custom_aggregations' not in r:
            r['custom_aggregations'] = {}
        # backwards compatibility with old templates
        if 'country_gdp' in r and r['country_gdp'] is not None:
            if 'reference' in r['country_gdp']:
                r['country_gdp']['citation'] = r['country_gdp'].pop(
                    'reference', None,
                )
        if 'custom_destinations' in r and r['custom_destinations'] is not None:
            if 'attribution' in r['custom_destinations']:
                r['custom_destinations']['citation'] = r[
                    'custom_destinations'
                ].pop('attribution', None)
        if (
            'policy_review' in r
            and r['policy_review'] is not None
            and r['policy_review'].endswith('.xlsx')
        ):
            r['policy_review'] = f"{folder_path}/{r['policy_review']}"
        else:
            # for now, we'll insert the blank template to allow the report to be generated
            r[
                'policy_review'
            ] = f'{folder_path}/process/data/policy_review/_policy_review_template_v0_TO-BE-UPDATED.xlsx'
        r = get_analysis_report_region_configuration(r, settings)
        return r

    def _verify_data_dir(self, data_dir, verify_file_extension=None) -> dict:
        """Return true if supplied data directory exists, optionally checking for existance of at least one file matching a specific extension within that directory."""
        if verify_file_extension is None:
            return {
                'data': data_dir,
                'exists': os.path.exists(data_dir),
            }
            # If False: f'The configured file in datasets.yml could not be located at {data_dir}.  Please check file and configuration of datasets.yml.',
        else:
            if os.path.isfile(data_dir):
                return {
                    'data': data_dir,
                    'exists': True,
                }
            else:
                check = any(
                    File.endswith(verify_file_extension)
                    for File in os.listdir(data_dir)
                )
                return {
                    'data': data_dir,
                    'exists': f'{check} ({verify_file_extension})',
                }

    # Set up region data
    def _region_data_setup(
        self, region, region_config, data, data_path=None,
    ):
        """Check data configuration for regions and make paths absolute."""
        try:
            if type(region_config[data]) == str:
                if data not in datasets or datasets[data] is None:
                    sys.exit(
                        f'\nAn entry for at least one {data} dataset does not appear to have been defined in datasets.yml.  This parameter is required for analysis, and is used to cross-reference a relevant dataset defined in datasets.yml with region configuration in {region}.yml.  Please update datasets.yml to proceed.\n',
                    )
                elif region_config[data] is None:
                    sys.exit(
                        f'\nThe entry for {data} does not appear to have been defined in {region}.yml.  This parameter is required for analysis, and is used to cross-reference a relevant dataset defined in datasets.yml.  Please update {region}.yml to proceed.\n',
                    )
                elif datasets[data][region_config[data]] is None:
                    sys.exit(
                        f'\nThe configured entry for {region_config[data]} under {data} within datasets.yml does not appear to be associated within any values.  Please check and amend the specification for this entry within datasets.yml , or the configuration within {region}.yml to proceed. (is this entry and its records indented as per the provided example?)\n',
                    )
                data_dictionary = datasets[data][region_config[data]].copy()
            else:
                if data == 'urban_region' and (
                    data not in region_config or region_config[data] is None
                ):
                    urban_region_checks = [
                        self.config['study_region_boundary'][
                            'ghsl_urban_intersection'
                        ],
                        'covariate_data' in self.config
                        and self.config['covariate_data'] == 'urban_query',
                    ]
                    if any(urban_region_checks):
                        data_dictionary = {'data_dir': None, 'citation': ''}
                    else:
                        # print(
                        #     f'Configuration for {data} not found in configuration file; skipping...',
                        # )
                        data_dictionary = {
                            'data_dir': 'Not required (neither urban region intersection or covariates referenced)',
                            'citation': '',
                        }
                else:
                    data_dictionary = region_config[data].copy()
            if 'citation' not in data_dictionary:
                if data != 'OpenStreetMap':
                    sys.exit(
                        f'\nNo citation record has been configured for the {data} dataset configured for this region.  Please add this to its record in datasets.yml (see template datasets.yml for examples).\n',
                    )
                elif 'source' not in data_dictionary:
                    data_dictionary[
                        'citation'
                    ] = f'OpenStreetMap Contributors ({str(data_dictionary["publication_date"])[:4]}). {data_dictionary["url"]}'
                else:
                    data_dictionary[
                        'citation'
                    ] = f'OpenStreetMap Contributors.  {data_dictionary["source"]} ({str(data_dictionary["publication_date"])[:4]}). {data_dictionary["url"]}'
            if ('data_dir' not in data_dictionary) or (
                data_dictionary['data_dir'] is None
            ):
                sys.exit(
                    f"The 'data_dir' entry for {data} does not appear to have been defined.  This parameter is required for analysis of {region}, and is used to locate a required dataset cross-referenced in {region}.yml.  Please check the configured settings before proceeding.",
                )
            if data_path is not None:
                data_dictionary[
                    'data_dir'
                ] = f"{data_path}/{data_dictionary['data_dir']}"
            return data_dictionary
        except Exception as e:
            sys.exit(e)

    def _run_data_checks(self):
        """Check configured data exists for this specified region."""
        checks = []
        failures = []
        data_check_report = ''
        self.config['study_region_boundary'][
            'ghsl_urban_intersection'
        ] = self.config['study_region_boundary'].pop(
            'ghsl_urban_intersection', False,
        )
        urban_region_checks = [
            self.config['study_region_boundary']['ghsl_urban_intersection'],
            'covariate_data' in self.config
            and self.config['covariate_data'] == 'urban_query',
        ]
        if (
            'urban_region' in self.config
            and self.config['urban_region'] is not None
        ) and (urban_region_checks[0] or urban_region_checks[1]):
            checks.append(
                self._verify_data_dir(
                    self.config['urban_region']['data_dir'],
                    verify_file_extension=None,
                ),
            )
        elif urban_region_checks[0]:
            checks.append(
                {
                    'data': "Urban region not configured, but required when 'ghsl_urban_intersection' is set to True",
                    'exists': False,
                },
            )
        elif urban_region_checks[1]:
            checks.append(
                {
                    'data': "Urban region not configured, but required when 'covariate_data' set to 'urban_query'",
                    'exists': False,
                },
            )
        checks.append(
            self._verify_data_dir(
                self.config['OpenStreetMap']['data_dir'],
                verify_file_extension=None,
            ),
        )
        checks.append(
            self._verify_data_dir(
                self.config['population']['data_dir'],
                verify_file_extension='tif',
            ),
        )
        if self.config['study_region_boundary']['data'] != 'urban_query':
            checks.append(
                self._verify_data_dir(
                    self.config['study_region_boundary']['data'].split(':')[0],
                ),
            )
        for check in checks:
            data_check_report += f"\n{check['exists']}: {check['data']}".replace(
                folder_path, '...',
            )
            if not check['exists']:
                failures.append(check)
        data_check_report += '\n'
        if len(failures) > 0:
            data_check_report = (
                '\nOne or more required resources were not located in the configured paths; please check your configuration for any items marked "False":\n'
                + data_check_report
            )
            # print(data_check_report)
        else:
            data_check_report = None
        return data_check_report

    def analysis(self):
        """Run analysis for this study region."""
        from analysis import analysis as run_analysis

        run_analysis(self)

    def generate(self):
        """Generate analysis outputs for this study region."""
        from generate import generate as generate_resources

        generate_resources(self)

    def compare(self, comparison):
        """Compare analysis outputs for this study region with those of another."""
        from compare import compare as compare_resources

        comparison = compare_resources(self, comparison)
        return comparison

    def drop(self, table=''):
        """Attempt to drop database results for this study region."""
        if table == '':
            from _drop_study_region_database import (
                drop_study_region_database as drop_resources,
            )

            drop_resources(self)
        else:
            with self.engine.begin() as connection:
                try:
                    print('Dropping table {table}...}')
                    connection.execute(
                        text(f"""DROP TABLE IF EXISTS {table};"""),
                    )
                except Exception as e:
                    print(f'Error: {e}')

    def _create_database(self):
        """Create database for this study region."""
        from _00_create_database import create_database

        create_database(self.codename)
        return f"Database {self.config['db']} created."

    def _create_study_region(self):
        """Create study region boundaries for this study region."""
        from _01_create_study_region import create_study_region

        create_study_region(self.codename)
        return 'Study region boundaries created.'

    def _create_osm_resources(self):
        """Create OSM resources for this study region."""
        from _02_create_osm_resources import create_osm_resources

        create_osm_resources(self.codename)
        return 'OSM resources created.'

    def _create_network_resources(self):
        """Create network resources for this study region."""
        from _03_create_network_resources import create_network_resources

        create_network_resources(self.codename)
        return 'Network resources created.'

    def _create_population_grid(self):
        """Create population grid for this study region."""
        from _04_create_population_grid import create_population_grid

        create_population_grid(self.codename)
        return 'Population grid created.'

    def _create_destinations(self):
        """Compile destinations for this study region."""
        from _05_compile_destinations import compile_destinations

        compile_destinations(self.codename)
        return 'Destinations compiled.'

    def _create_open_space_areas(self):
        """Create open space areas for this study region."""
        from _06_open_space_areas_setup import open_space_areas_setup

        open_space_areas_setup(self.codename)
        return 'Open space areas created.'

    def _create_neighbourhoods(self):
        """Create neighbourhood relations between nodes for this study region."""
        from _07_locate_origins_destinations import nearest_node_locations

        nearest_node_locations(self.codename)
        return 'Neighbourhoods created.'

    def _create_destination_summary_tables(self):
        """Create destination summary tables for this study region."""
        from _08_destination_summary import destination_summary

        destination_summary(self.codename)
        return 'Destination summary tables created.'

    def _link_urban_covariates(self):
        """Link urban covariates to nodes for this study region."""
        from _09_urban_covariates import link_urban_covariates

        link_urban_covariates(self.codename)
        return 'Urban covariates linked.'

    def _gtfs_analysis(self):
        from _10_gtfs_analysis import gtfs_analysis

        gtfs_analysis(self.codename)
        return 'GTFS analysis completed.'

    def _neighbourhood_analysis(self):
        from _11_neighbourhood_analysis import neighbourhood_analysis

        neighbourhood_analysis(self.codename)
        return 'Neighbourhood analysis completed.'

    def _area_analysis(self):
        from _12_aggregation import aggregate_study_region_indicators

        aggregate_study_region_indicators(self.codename)
        return 'Area analysis completed.'

    def get_engine(self):
        """Given configuration details, create a database engine."""
        engine = create_engine(
            f"postgresql://{settings['sql']['db_user']}:{settings['sql']['db_pwd']}@{settings['sql']['db_host']}/{self.config['db']}",
            future=True,
            pool_pre_ping=True,
            connect_args={
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            },
        )
        return engine

    def get_tables(self) -> list:
        """Given configuration details, create a database engine."""
        try:
            db_contents = inspect(self.engine)
            tables = db_contents.get_table_names()
        except Exception as e:
            tables = []
        finally:
            return tables

    def get_gdf(
        self,
        sql: str,
        geom_col='geom',
        crs=None,
        index_col=None,
        coerce_float=True,
        parse_dates=None,
        params=None,
        chunksize=None,
    ) -> gpd.GeoDataFrame:
        """Return a postgis database layer or sql query as a geodataframe."""
        try:
            with self.engine.begin() as connection:
                geo_data = gpd.read_postgis(
                    sql,
                    connection,
                    geom_col=geom_col,
                    crs=crs,
                    index_col=index_col,
                    coerce_float=coerce_float,
                    parse_dates=parse_dates,
                    params=params,
                    chunksize=chunksize,
                )
        except:
            geo_data = None
        finally:
            return geo_data

    def get_df(
        self,
        sql: str,
        index_col=None,
        coerce_float=True,
        params=None,
        parse_dates=None,
        columns=None,
        chunksize=None,
        dtype=None,
    ) -> pd.DataFrame:
        """Return a postgis database layer or sql query as a dataframe."""
        try:
            with self.engine.begin() as connection:
                df = pd.read_sql(
                    sql,
                    connection,
                    index_col=index_col,
                    coerce_float=coerce_float,
                    params=None,
                    parse_dates=parse_dates,
                    columns=columns,
                    chunksize=chunksize,
                    dtype=dtype,
                )
        except:
            df = None
        finally:
            return df

    def get_centroid(
        self, table='urban_study_region', geom_col='geom',
    ) -> tuple:
        """Return the centroid of a postgis database layer or sql query."""
        query = f"""SELECT ST_Y(geom), ST_X(geom) FROM (SELECT ST_Transform(ST_Centroid(geom),4326) geom FROM {table}) t;"""
        try:
            with self.engine.begin() as connection:
                centroid = tuple(connection.execute(text(query)).fetchall()[0])
        except:
            centroid = None
        finally:
            return centroid

    def get_geojson(
        self,
        table='urban_study_region',
        geom_col='geom',
        include_columns=None,
    ) -> dict:
        """Return a postgis database layer or sql query as a geojson dictionary."""
        columns_query = """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema ='public'
               AND table_name   ='{}';
        """
        geojson_query = """
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', json_agg(ST_AsGeoJSON(t.*)::json)
            )
        FROM ({}) as t;
        """
        try:
            with self.engine.begin() as connection:
                columns = connection.execute(
                    text(columns_query.format(table)),
                ).fetchall()
                non_geom_columns = ','.join(
                    [
                        f'"{x[0]}"'
                        for x in columns
                        if x[0] not in ['db', geom_col]
                    ],
                )
                if include_columns is not None:
                    non_geom_columns = ','.join(
                        [f'"{x}"' for x in include_columns],
                    )
                if non_geom_columns != '':
                    non_geom_columns = non_geom_columns + ','
                sql = f"""
                    SELECT
                        {non_geom_columns}
                        ST_ForcePolygonCCW(ST_Transform(ST_SimplifyPreserveTopology({geom_col},0.1),4326)) as {geom_col}
                    FROM {table}"""
                geojson = connection.execute(
                    text(geojson_query.format(sql)),
                ).fetchone()[0]
                # print(geojson_query.format(sql))
        except Exception as e:
            print(e)
            geojson = None
        finally:
            return geojson

    def ogr_to_db(
        self,
        source: str,
        layer: str,
        query: str = '',
        promote_to_multi: bool = False,
        source_crs: str = None,
    ):
        """Read spatial data with ogr2ogr and save to Postgis database."""
        import subprocess as sp

        if source.count(':') == 1:
            # appears to be using optional query syntax as could be used for a geopackage
            parts = source.split(':')
            source = parts[0]
            query = parts[1]
            del parts

        crs_srid = self.config['crs_srid']
        db = self.config['db']
        db_host = self.config['db_host']
        db_port = self.config['db_port']
        db_user = self.config['db_user']
        db_pwd = self.config['db_pwd']
        if source_crs is not None:
            # Some spatial data files may require clarification of the source coordinate reference system
            # If this is required, source_crs can be defined, e.g. 'EPSG:4326' in the case of a WGS84 source
            s_srs = f'-s_srs {source_crs}'
        else:
            s_srs = ''
        if promote_to_multi:
            multi = '-nlt PROMOTE_TO_MULTI'
        else:
            multi = ''
        command = f' ogr2ogr -overwrite -progress -f "PostgreSQL" PG:"host={db_host} port={db_port} dbname={db} user={db_user} password={db_pwd}" "{source}" -lco geometry_name="geom" -lco precision=NO  -t_srs {crs_srid} {s_srs} -nln "{layer}" {multi} {query}'
        failure = sp.run(command, shell=True)
        print(failure)
        if failure == 1:
            sys.exit(
                f"Error reading in data for {layer} '{source}'; please check format and configuration.",
            )
        else:
            return failure

    def raster_to_db(
        self,
        raster: str,
        config: dict,
        field: str,
        to_vector: bool = True,
        reference_grid=False,
    ):
        """Read raster data save to Postgis database, optionally adding and indexing a unique grid_id variable for use as a reference grid for analysis."""
        import subprocess as sp

        from _utils import reproject_raster
        from osgeo import gdal

        # disable noisy GDAL logging
        # gdal.SetConfigOption('CPL_LOG', 'NUL')  # Windows
        gdal.SetConfigOption('CPL_LOG', '/dev/null')  # Linux/MacOS
        """Extract data from raster tiles and import to database."""
        print('Extracting raster data...')
        raster_grid = self.config['population_grid']
        raster_stub = (
            f'{self.config["region_dir"]}/{raster_grid}_{self.codename}'
        )
        # construct virtual raster table
        vrt = f'{config["data_dir"]}/{raster_grid}_{config["crs_srid"]}.vrt'
        raster_clipped = f'{raster_stub}_{config["crs_srid"]}.tif'
        raster_projected = f'{raster_stub}_{self.config["crs"]["srid"]}.tif'
        print(f'{raster} dataset...', end='', flush=True)
        if not os.path.isfile(vrt):
            tif_folder = f'{config["data_dir"]}'
            tif_files = [
                os.path.join(tif_folder, file)
                for file in os.listdir(tif_folder)
                if os.path.splitext(file)[-1] == '.tif'
            ]
            gdal.BuildVRT(vrt, tif_files)
            print(f'{raster} has now been indexed ({vrt}).')
        else:
            print(f'{raster}  has already been indexed ({vrt}).')
        print(f'\n{raster} data clipped to region...', end='', flush=True)
        if not os.path.isfile(raster_clipped):
            # extract study region boundary in projection of tiles
            clipping_query = f'SELECT geom FROM {self.config["buffered_urban_study_region"]}'
            clipping = self.get_gdf(
                text(clipping_query), geom_col='geom',
            ).to_crs(config['crs_srid'])
            # get clipping boundary values in required order for gdal translate
            bbox = list(
                clipping.bounds[['minx', 'maxy', 'maxx', 'miny']].values[0],
            )
            gdal.Translate(raster_clipped, vrt, projWin=bbox)
            print(f'{raster} has now been created ({raster_clipped}).')
        else:
            print(f'{raster} has already been created ({raster_clipped}).')
        print(f'\n{raster} projected for region...', end='', flush=True)
        if not os.path.isfile(raster_projected):
            # reproject and save the re-projected clipped raster
            reproject_raster(
                inpath=raster_clipped,
                outpath=raster_projected,
                new_crs=self.config['crs']['srid'],
            )
            print(f'  has now been created ({raster_projected}).')
        else:
            print(f'  has already been created ({raster_projected}).')
        if raster_grid not in self.tables:
            print(
                f'\nImport grid {raster_grid} to database... ',
                end='',
                flush=True,
            )
            # import raster to postgis and vectorise, as per http://www.brianmcgill.org/postgis_zonal.pdf
            if to_vector:
                command = (
                    f'raster2pgsql -d -s {self.config["crs"]["srid"]} -I -Y '
                    f"-N {config['raster_nodata']} "
                    f'-t  1x1 {raster_projected} {raster_grid} '
                    f'| PGPASSWORD={self.config["db_pwd"]} psql -U postgres -h {self.config["db_host"]} -d {self.config["db"]} '
                    '>> /dev/null'
                )
                sp.call(command, shell=True)
                # remove empty cells
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            f"""DELETE FROM {raster_grid} WHERE (ST_SummaryStats(rast)).sum IS NULL;""",
                        ),
                    )
                # if reference grid add and index grid id
                if reference_grid:
                    queries = [
                        f"""ALTER TABLE {raster_grid} DROP COLUMN rid;""",
                        f"""ALTER TABLE {raster_grid} ADD grid_id bigserial;""",
                        f"""CREATE INDEX {raster_grid}_ix  ON {raster_grid} (grid_id);""",
                    ]
                    for sql in queries:
                        with self.engine.begin() as connection:
                            connection.execute(text(sql))
                # add geometry column and calculate statistic
                queries = [
                    f"""ALTER TABLE {raster_grid} ADD COLUMN IF NOT EXISTS geom geometry;""",
                    f"""UPDATE {raster_grid} SET geom = ST_ConvexHull(rast);""",
                    f"""CREATE INDEX {raster_grid}_gix ON {raster_grid} USING GIST(geom);""",
                    f"""ALTER TABLE {raster_grid} ADD COLUMN IF NOT EXISTS {field} int;""",
                    f"""UPDATE {raster_grid} SET {field} = (ST_SummaryStats(rast)).sum;""",
                    f"""ALTER TABLE {raster_grid} DROP COLUMN rast;""",
                ]
                for sql in queries:
                    with self.engine.begin() as connection:
                        connection.execute(text(sql))
            print('Done.')
        else:
            print(f'{raster_grid} has been imported to database.')

    def choropleth(
        self,
        field: str,
        layer: str,
        id: str,
        title: str,
        save=True,
        attribution: str = 'Global Healthy and Sustainable City Indicators Collaboration',
    ):
        """Plot a choropleth map of a specified field in a specified layer, with a custom title and attribution, with optional saving to an html file."""
        from _utils import plot_choropleth_map

        tables = self.get_tables()
        if layer not in tables:
            print(
                f"Layer {layer} not found in current list of database tables ({', '.join(tables)}).",
            )
            return None
        else:
            map = plot_choropleth_map(
                self,
                field=field,
                layer=layer,
                layer_id=id,
                title=title,
                attribution=attribution,
            )
            if save:
                file = f'{self.config["region_dir"]}/{layer} - {field}.html'
                map.save(file)
                print(
                    f"Choropleth map saved as {self.config['region_dir']}/{layer} - {field}.html.",
                )
            return map

    def to_csv(self, table, file, drop=['geom'], index=False):
        """Write an SQL table or query to a csv file."""
        df = self.get_df(table)
        df = df[[c for c in df.columns if c not in drop]]
        df.to_csv(file, index=index)
        return file


# Allow for project setup to run from different directories; potentially outside docker
# This means project configuration and set up can be verified in externally launched tests
if os.path.exists(f'{os.getcwd()}/../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../')
    sys.path.append(os.path.abspath('./subprocesses'))
elif os.path.exists(f'{os.getcwd()}/../../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../../')
    sys.path.append(os.path.abspath('.'))
else:
    folder_path = os.getcwd()

with open(f'{folder_path}/.ghsci_version') as f:
    __version__ = f.read().strip()

# Load project configuration files
config_path = f'{folder_path}/process/configuration'

if not os.path.exists(f'{config_path}/config.yml'):
    initialise_configuration()

region_names = get_region_names()
settings = load_yaml(f'{config_path}/config.yml')
datasets = load_yaml(f'{config_path}/datasets.yml')
osm_open_space = load_yaml(f'{config_path}/osm_open_space.yml')
indicators = load_yaml(f'{config_path}/indicators.yml')
policies = load_yaml(f'{config_path}/policies.yml')
dictionary = pd.read_csv(
    f'{config_path}/assets/output_data_dictionary.csv',
).set_index('Variable')

# Load OpenStreetMap destination and open space parameters
df_osm_dest = pd.read_csv(
    f'{config_path}/osm_destination_definitions.csv',
).replace(np.nan, 'NULL', regex=True)


# Set up date and time
os.environ['TZ'] = settings['project']['analysis_timezone']
time.tzset()
date = time.strftime('%Y-%m-%d')
date_hhmm = time.strftime('%Y-%m-%d_%H%M')


# Database setup
os.environ['PGHOST'] = settings['sql']['db_host']
os.environ['PGPORT'] = str(settings['sql']['db_port'])
os.environ['PGUSER'] = settings['sql']['db_user']
os.environ['PGPASSWORD'] = settings['sql']['db_pwd']

grant_query = f"""GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {settings['sql']['db_user']};
                 GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {settings['sql']['db_user']};"""


# SQL alchemy >= 1.4 warns about planned deprecations in version 2
# however, Pandas / Geopandas doesn't yet support the new syntax
# and migration of syntax is not straightforward
# (warnings are obscure); hence ignoring warnings
# and pinning sqlalchemy < 2.0
os.environ['SQLALCHEMY_SILENCE_UBER_WARNING'] = '1'


def main():
    print(
        f'\nGlobal Healthy Liveable City Indicators, version {__version__}\n\nRegion code names for running scripts:\n\n{" ".join(region_names)}\n',
    )
    return region_names


if __name__ == '__main__':
    main()
# else:
# print(f'\nGlobal Healthy Liveable City Indicators, version {__version__}')
