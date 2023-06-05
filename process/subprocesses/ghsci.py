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

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import create_engine, inspect, text


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


class Region:
    """A class for a study region (e.g. a city) that is used to load and store parameters contained in a yaml configuration file in the configuration/regions folder."""

    def __init__(self, name):
        self.codename = name
        self.config = load_yaml(f'{config_path}/regions/{name}.yml')
        self.name = self.config['name']
        self.config = self.region_dictionary_setup(
            self.codename, self.config, folder_path,
        )
        self.engine = self.get_engine()
        self.tables = self.get_tables()
        self.header = f"\n{self.name} ({self.codename})\n\nOutput directory:\n  {self.config['region_dir'].replace('/home/ghsci/','')}\n"

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

    def get_geojson(self, table='urban_study_region', geom_col='geom') -> dict:
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
                sql = f"""
                    SELECT
                        {','.join([f'"{x[0]}"' for x in columns if x[0] not in ['db',geom_col]])},
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

    def to_csv(self, table, file, drop=['geom'], index=False):
        """Write an SQL table or query to a csv file."""
        df = self.get_df(table)
        df = df[[c for c in df.columns if c not in drop]]
        df.to_csv(file, index=index)
        return file

    def run_data_checks(self):
        """Check configured data exists for this specified region."""
        assert self.verify_data_dir(
            self.config['urban_region']['data_dir'],
            verify_file_extension=None,
        )
        assert self.verify_data_dir(
            self.config['OpenStreetMap']['data_dir'],
            verify_file_extension=None,
        )
        assert self.verify_data_dir(
            self.config['population']['data_dir'], verify_file_extension='tif',
        )
        if self.config['study_region_boundary']['data'] != 'urban_query':
            assert self.verify_data_dir(
                self.config['study_region_boundary']['data'].split(':')[0],
            )

    # Set up region data
    def region_data_setup(
        self, region, region_config, data, data_path=None,
    ):
        """Check data configuration for regions and make paths absolute."""
        try:
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
            else:
                if 'citation' not in datasets[data][region_config[data]]:
                    if data != 'OpenStreetMap':
                        sys.exit(
                            f'\nNo citation record has been configured for the {data} dataset configured for this region.  Please add this to its record in datasets.yml (see template datasets.yml for examples).\n',
                        )
                    elif 'source' not in region_config['OpenStreetMap']:
                        datasets[data][region_config[data]][
                            'citation'
                        ] = f'OpenStreetMap Contributors ({str(datasets[data][region_config[data]]["publication_date"])[:4]}). {datasets[data][region_config[data]]["url"]}'
                    else:
                        datasets[data][region_config[data]][
                            'citation'
                        ] = f'OpenStreetMap Contributors.  {datasets[data][region_config[data]]["source"]} ({str(datasets[data][region_config[data]]["publication_date"])[:4]}). {datasets[data][region_config[data]]["url"]}'
                data_dictionary = datasets[data][region_config[data]].copy()
            if ('data_dir' not in data_dictionary) or (
                data_dictionary['data_dir'] is None
            ):
                sys.exit(
                    f"The 'data_dir' entry for {data} does not appear to have been defined in datasets.yml.  This parameter is required for analysis of {region}, and is used to locate a required dataset cross-referenced in {region}.yml.  Please update datasets.yml to proceed.",
                )
            if data_path is not None:
                data_dictionary[
                    'data_dir'
                ] = f"{data_path}/{datasets[data][region_config[data]]['data_dir']}"
            return data_dictionary
        except Exception as e:
            sys.exit(e)

    def verify_data_dir(self, data_dir, verify_file_extension=None):
        """Return true if supplied data directory exists, optionally checking for existance of at least one file matching a specific extension within that directory."""
        if verify_file_extension is None:
            return os.path.exists(data_dir)
            # If False: f'The configured file in datasets.yml could not be located at {data_dir}.  Please check file and configuration of datasets.yml.',
        else:
            return any(
                File.endswith(verify_file_extension)
                for File in os.listdir(data_dir)
            )

    def region_dictionary_setup(self, codename, region_config, folder_path):
        """Set up region configuration dictionary."""
        r = region_config.copy()
        date = time.strftime('%Y-%m-%d')
        study_buffer = settings['project']['study_buffer']
        units = settings['project']['units']
        buffered_urban_study_region = (
            f'urban_study_region_{study_buffer}{units}'
        )
        r['crs_srid'] = f"{r['crs']['standard']}:{r['crs']['srid']}"
        r[
            'osm_prefix'
        ] = f"osm_{datasets['OpenStreetMap'][r['OpenStreetMap']]['publication_date']}"
        r[
            'region_dir'
        ] = f'{folder_path}/process/data/_study_region_outputs/{codename}'
        data_path = f'{folder_path}/process/data'
        if r['study_region_boundary']['data'] != 'urban_query':
            r['study_region_boundary'][
                'data'
            ] = f"{data_path}/{r['study_region_boundary']['data']}"
        r['urban_region'] = self.region_data_setup(
            codename, region_config, 'urban_region', data_path,
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
        r['population'] = self.region_data_setup(
            codename, region_config, 'population', data_path,
        )
        resolution = r['population']['resolution'].replace(' ', '')
        r['population'][
            'crs_srid'
        ] = f'{r["population"]["crs_standard"]}:{r["population"]["crs_srid"]}'
        r[
            'population_grid'
        ] = f'population_{resolution}_{r["population"]["year_target"]}'
        r['OpenStreetMap'] = self.region_data_setup(
            codename, region_config, 'OpenStreetMap', data_path,
        )
        r['OpenStreetMap'][
            'osm_region'
        ] = f'{r["region_dir"]}/{codename}_{r["osm_prefix"]}.pbf'
        r['codename_poly'] = f'{r["region_dir"]}/poly_{r["db"]}.poly'
        r[
            'intersections_table'
        ] = f"clean_intersections_{r['network']['intersection_tolerance']}m"
        r['gpkg'] = f'{r["region_dir"]}/{codename}_{study_buffer}m_buffer.gpkg'
        r['point_summary'] = 'indicators_sample_points'
        r['grid_summary'] = f'indicators_grid_{resolution}'
        r['city_summary'] = 'indicators_region'
        if 'custom_aggregations' not in r:
            r['custom_aggregations'] = {}
        if 'policy_review' in r:
            r['policy_review'] = f"{folder_path}/{r['policy_review']}"
        else:
            r['policy_review'] = None
        if r['network']['buffered_region']:
            r[
                'graphml'
            ] = f'{r["region_dir"]}/{codename}_{study_buffer}m_pedestrian_{r["osm_prefix"]}.graphml'
            r[
                'graphml_proj'
            ] = f'{r["region_dir"]}/{codename}_{study_buffer}m_pedestrian_{r["osm_prefix"]}_proj.graphml'
        else:
            r[
                'graphml'
            ] = f'{r["region_dir"]}/{codename}_pedestrian_{r["osm_prefix"]}.graphml'
            r[
                'graphml_proj'
            ] = f'{r["region_dir"]}/{codename}_pedestrian_{r["osm_prefix"]}_proj.graphml'
        return r


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

# get names of regions for which configuration files exist
region_names = [
    x.split('.yml')[0]
    for x in os.listdir(f'{config_path}/regions')
    if x.endswith('.yml')
]

settings = load_yaml(f'{config_path}/config.yml')
datasets = load_yaml(f'{config_path}/datasets.yml')
osm_open_space = load_yaml(f'{config_path}/osm_open_space.yml')
indicators = load_yaml(f'{config_path}/indicators.yml')
policies = load_yaml(f'{config_path}/policies.yml')

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
