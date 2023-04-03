"""Generate resources supporting urban indicator dissemination and usage."""

import os
import shutil
import sys

from sqlalchemy import create_engine
from subprocesses._project_setup import (
    authors,
    codename,
    db,
    db_host,
    db_pwd,
    db_user,
    email,
    folder_path,
    gtfs,
    indicators,
    individualname,
    name,
    policies,
    positionname,
    region_config,
    region_names,
    time,
    url,
    year,
)
from subprocesses._report_functions import (
    generate_metadata_xml,
    generate_metadata_yml,
    generate_report_for_language,
    get_and_setup_language_cities,
    get_terminal_columns,
    postgis_to_csv,
    postgis_to_geopackage,
    print_autobreak,
)


class config:
    """Basic configuration file for report generation."""

    city = codename
    generate_resources = True
    language = 'English'
    auto_language = True
    templates = ['web']
    configuration = './configuration/_report_configuration.xlsx'


if config.city not in region_names:
    sys.exit(
        f'Specified city ({config.city}) does not appear to be in the list of configured cities ({region_names})',
    )

config.folder_path = folder_path
config.region = region_config
if not os.path.exists(config.region['region_dir']):
    sys.exit(
        f"\n\nProcessed resource folder for this city couldn't be located:"
        f'\n[{config.region["region_dir"]}]'
        '\nPlease ensure city has been successfully processed before continuing\n',
    )


def main():
    engine = create_engine(
        f'postgresql://{db_user}:{db_pwd}@{db_host}/{db}', future=True,
    )
    # List existing generated resources
    print('Analysis parameter summary text file')
    print(f'  {codename}.yml')
    print('\nAnalysis log text file')
    print(f"  __{region_config['name']}__{codename}_processing_log.txt")
    print('\nData files')
    print(f"  {os.path.basename(region_config['gpkg'])}")
    tables = [
        region_config['city_summary'],
        region_config['grid_summary'],
        region_config['point_summary'],
        'aos_public_osm',
        'dest_type',
        'destinations',
        region_config['intersections_table'],
        'edges',
        'nodes',
    ]
    if region_config['gtfs_feeds'] is not None:
        tables = tables + [gtfs['headway']]
    postgis_to_geopackage(
        region_config['gpkg'], db_host, db_user, db, db_pwd, tables,
    )
    for layer in ['city', 'grid']:
        print(
            postgis_to_csv(
                f"  {region_config[f'{layer}_summary']}.csv",
                db_host,
                db_user,
                db,
                db_pwd,
                region_config[f'{layer}_summary'],
            ),
        )
    # Generate data dictionary
    print('\nData dictionaries')
    required_assets = [
        'output_data_dictionary.csv',
        'output_data_dictionary.xlsx',
    ]
    for file in required_assets:
        shutil.copyfile(
            f'./configuration/assets/{file}',
            f"{config.region['region_dir']}/{file}",
        )
        print(f'  {file}')

    # Generate metadata
    print('\nMetadata')
    metadata_yml = generate_metadata_yml(
        engine,
        folder_path,
        region_config,
        codename,
        name,
        year,
        authors,
        url,
        individualname,
        positionname,
        email,
    )
    print(f'  {metadata_yml}')
    metadata_xml = generate_metadata_xml(config.region['region_dir'], codename)
    print(f'  {metadata_xml}')

    # Generate reports
    languages = get_and_setup_language_cities(config)
    if languages == []:
        print_autobreak(
            '  - Report generation skippped.  Please confirm that city and its corresponding codename have been configured in the city details and language worksheets of configuration/_report_configuration.xlsx.',
        )
    else:
        for language in languages:
            generate_report_for_language(
                config, language, indicators, policies,
            )
    print_autobreak(
        '\n\nIt is important to take the time to familiarise yourself with the various outputs generated from the configuration and analysis of your region of interest to ensure they provide a fair and accurate representation given local knowledge.  Any issues or limitations identified should be understood and can be iteratively addressed and/or acknowledged in documentation prior to dissemination.\n\n',
    )


if __name__ == '__main__':
    main()
