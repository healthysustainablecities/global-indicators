"""
Global scorecards.

Format and save indicator reports.
"""

import os
import shutil
import sys

# import and set up functions
import subprocesses._report_functions as _report_functions
from subprocesses._project_setup import (
    codename,
    folder_path,
    indicators,
    policies,
    region_config,
    region_names,
)
from subprocesses._utils import get_terminal_columns, print_autobreak


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
    # List existing generated resources
    print('Analysis parameter summary text file')
    print(f'  {codename}.yml')
    print('\nAnalysis log text file')
    print(f"  __{region_config['name']}__{codename}_processing_log.txt")
    print('\nData files')
    print(f"  {os.path.basename(region_config['gpkg'])}")
    print(f"  {region_config['grid_summary']}.csv")
    print(f"  {region_config['city_summary']}.csv")
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
    # Generate reports
    languages = _report_functions.get_and_setup_language_cities(config)
    if languages == []:
        print_autobreak(
            '  - Report generation skippped.  Please confirm that city and its corresponding codename have been configured in the city details and language worksheets of configuration/_report_configuration.xlsx.',
        )
    else:
        for language in languages:
            _report_functions.generate_report_for_language(
                config, language, indicators, policies,
            )
    print_autobreak(
        '\n\nIt is important to take the time to familiarise yourself with the various outputs generated from the configuration and analysis of your region of interest to ensure they provide a fair and accurate representation given local knowledge.  Any issues or limitations identified should be understood and can be iteratively addressed and/or acknowledged in documentation prior to dissemination.\n\n',
    )


if __name__ == '__main__':
    main()
