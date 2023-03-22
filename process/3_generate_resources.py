"""
Global scorecards.

Format and save indicator reports.
"""

import os
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
    languages = _report_functions.get_and_setup_language_cities(config)
    if languages == []:
        sys.exit(
            '\nReport generation failed (no language configured for this city).  Please confirm that city and its corresponding codename have been configured in the city details and language worksheets of configuration/_report_configuration.xlsx.\n\n',
        )
    for language in languages:
        _report_functions.generate_report_for_language(
            config, language, indicators, policies,
        )


if __name__ == '__main__':
    main()
