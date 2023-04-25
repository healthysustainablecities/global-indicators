"""Generate resources supporting urban indicator dissemination and usage."""

import os
import shutil
import sys

from sqlalchemy import create_engine
from subprocesses._project_setup import (
    __version__,
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
from subprocesses._utils import (
    check_and_update_config_reporting_parameters,
    generate_metadata_xml,
    generate_metadata_yml,
    generate_report_for_language,
    get_terminal_columns,
    postgis_to_csv,
    postgis_to_geopackage,
    print_autobreak,
)
from subprocesses.analysis_report import PDF_Analysis_Report


class config:
    """Basic configuration file for report generation."""

    city = codename
    templates = ['web']
    configuration = './configuration/_report_configuration.xlsx'


if config.city not in region_names:
    sys.exit(
        f'Specified city ({config.city}) does not appear to be in the list of configured cities ({region_names})',
    )

config.folder_path = folder_path
config.region = region_config
config.authors = authors
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
    print(f"  __{config.region['name']}__{codename}_processing_log.txt")
    print('\nData files')
    print(f"  {os.path.basename(config.region['gpkg'])}")
    tables = [
        config.region['city_summary'],
        config.region['grid_summary'],
        config.region['point_summary'],
        'aos_public_osm',
        'dest_type',
        'destinations',
        config.region['intersections_table'],
        'edges',
        'nodes',
    ]
    if config.region['gtfs_feeds'] is not None:
        tables = tables + [gtfs['headway']]
    postgis_to_geopackage(
        config.region['gpkg'], db_host, db_user, db, db_pwd, tables,
    )
    for layer in ['city', 'grid']:
        print(
            postgis_to_csv(
                f"{config.region['region_dir']}/{config.region[f'{layer}_summary']}.csv",
                db_host,
                db_user,
                db,
                db_pwd,
                config.region[f'{layer}_summary'],
            ).replace(f"{config.region['region_dir']}/", ''),
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
        config.region,
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
    # Generate web reports by language
    config.region['reporting'] = check_and_update_config_reporting_parameters(
        config,
    )
    for language in config.region['reporting']['languages']:
        generate_report_for_language(
            engine, config, language, indicators, policies,
        )
    # Generate analysis report
    print('\nAnalysis report (work in progress...)')
    PDF_Analysis_Report.generate_analysis_report(engine, region_config)

    # Advise user to check outputs
    print_autobreak(
        '\n\nIt is important to take the time to familiarise yourself with the various outputs generated from the configuration and analysis of your region of interest to ensure they provide a fair and accurate representation given local knowledge.  Any issues or limitations identified should be understood and can be iteratively addressed and/or acknowledged in documentation prior to dissemination.\n\n',
    )


if __name__ == '__main__':
    main()
