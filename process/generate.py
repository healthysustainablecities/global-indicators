"""Generate resources supporting urban indicator dissemination and usage."""

import shutil
import sys

import yaml
from subprocesses._utils import postgis_to_geopackage, print_autobreak

# Load study region configuration
from subprocesses.ghsci import Region, __version__, datasets, os, settings


def export_indicators(r, gpkg=True, csv=True):
    custom_aggregations = r.config.pop('custom_aggregations', {})
    tables = [f'indicators_{x}' for x in custom_aggregations] + [
        r.config['city_summary'],
        r.config['grid_summary'],
        r.config['point_summary'],
        'aos_public_osm',
        'dest_type',
        'destinations',
        r.config['intersections_table'],
        'edges',
        'nodes',
    ]
    if ('gtfs_feeds' in r.config) and (r.config['gtfs_feeds'] is not None):
        tables = tables + [datasets['gtfs']['headway']]
    r.tables = r.get_tables()
    if r.tables == []:
        sys.exit(
            f"\nResults don't appear to have been processed for {r.codename}.\n\nPlease ensure that the analysis process has been run for this study region successfully and then try again.",
        )
    print('\nData files')
    tables_not_in_database = [x for x in tables if x not in r.tables]
    if len(tables_not_in_database) > 0:
        print(
            f"The following tables were not found in the database, and so not exported: {', '.join(tables_not_in_database)} (please ensure processing has been completed to export these)",
        )
    if gpkg:
        if os.path.exists(r.config['gpkg']):
            print(
                f"  {r.config['gpkg'].replace(r.config['region_dir'],'')} (exists; delete or rename to re-generate)",
            )
        else:
            print(f"  {os.path.basename(r.config['gpkg'])}")
            postgis_to_geopackage(
                r.config['gpkg'],
                settings['sql']['db_host'],
                settings['sql']['db_user'],
                r.config['db'],
                settings['sql']['db_pwd'],
                [t for t in tables if t in r.tables],
            )
    if csv:
        for layer in ['city', 'grid'] + [x for x in custom_aggregations]:
            if layer in ['city', 'grid']:
                table = r.config[f'{layer}_summary']
            else:
                table = f'indicators_{layer}'
            if table in r.tables:
                file = f"{r.config['region_dir']}/{r.codename}_{table}.csv"
                if os.path.exists(file):
                    print(
                        f"  {file.replace(r.config['region_dir'],'')} (exists; delete or rename to re-generate)",
                    )
                else:
                    print('  ' + os.path.basename(r.to_csv(table, file)))


def generate(r):
    """List resources that have been generated for this study region."""
    if type(r) is str:
        codename = r
        r = Region(codename)
    else:
        codename = r.codename
    print(r.header)
    if not os.path.exists(r.config['region_dir']):
        sys.exit(
            f"\n\nProcessed resource folder for this city couldn't be located:"
            f'\n[{r.config["region_dir"]}]'
            '\nPlease ensure city has been successfully processed before continuing\n',
        )
    if os.path.exists(f"{r.config['region_dir']}/_parameters.yml"):
        with open(f"{r.config['region_dir']}/_parameters.yml") as f:
            r.config['parameters'] = yaml.safe_load(f)
        print('\nAnalysis parameter summary text file:')
        print('  _parameters.yml')
    if os.path.exists(r.log):
        print('\nAnalysis log text file:')
        print(f'  {os.path.basename(r.log)}')
    export_indicators(r)
    # Generate data dictionary
    print('\nData dictionaries:')
    required_assets = [
        'output_data_dictionary.csv',
        'output_data_dictionary.xlsx',
    ]
    for file in required_assets:
        shutil.copyfile(
            f'./configuration/assets/{file}',
            f"{r.config['region_dir']}/{file}",
        )
        print(f'  {file}')

    # Generate metadata
    print('\nMetadata:')
    metadata_yml = r.get_metadata(format='YAML', return_path=True)
    print(f'  {metadata_yml}')
    metadata_xml = r.get_metadata(format='XML', return_path=True)
    print(f'  {metadata_xml}')
    # Generate scorecard statistics
    try:
        r.get_scorecard_statistics(export=True)
    except Exception as e:
        print(
            f"  Unable to generate scorecard statistics: {e}\n  (this may mean that policy and/or spatial analysis has not yet been completed or correctly configured)",
        )
    # Generate web reports by language
    print('\nReports:')
    for language in r.config['reporting']['languages']:
        r.generate_report(language=language, report='indicators')

    # Generate analysis report
    print('\nAnalysis report')
    r.generate_report(report='analysis')

    # Advise user to check outputs
    print_autobreak(
        '\n\nIt is important to take the time to familiarise yourself with the various outputs generated from the configuration and analysis of your region of interest to ensure they provide a fair and accurate representation given local knowledge.  Any issues or limitations identified should be understood and can be iteratively addressed and/or acknowledged in documentation prior to dissemination.\n\n',
    )


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    r = Region(codename)
    r.generate()


if __name__ == '__main__':
    main()
