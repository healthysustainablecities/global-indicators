"""
Create project configuration files.

Copies configuration templates to configuration folder for custom modification.
"""

import shutil
import sys

from subprocesses._utils import print_autobreak
from subprocesses.ghsci import get_region_configs, get_region_names

list_seperation = '\n  '
configuration_instructions = """
Before commencing analysis, your study regions will need to be configured.

Study regions are configured using .yml files.  These may be located within the `configuration/regions` sub-folder, or kept alongside the data they describe, in a `configuration` folder within a study region's own data folder; both are found automatically.  A worked example for Las Palmas de Gran Canaria (for which data supporting analysis is included) has been provided in the file `process/data/examples/ES_Las_Palmas_2025/configuration/ES_Las_Palmas_2025.yml`, and further additional example regions have also been provided.  The name of the file, for example `ES_Las_Palmas_2025`, acts a codename for the city when used in processing and avoids issues with ambiguity when analysing multiple cities across different regions and time points: 'ES' clarifies that this is a Spanish city, 'Las_Palmas' is a common short way of writing the city's name, and the analysis uses data chosen to target 2025.  Using a naming convention like this is recommended when creating new region configuration files (e.g. ES_Barcelona_2025.yml, or AU_Melbourne_2025.yml).

The study region configuration files have a file extension .yml (YAML files), which means they are text files that can be edited in a text editor to define region specific details, including which datasets used - eg cities from a particular region could share common excerpts of population and OpenStreetMap, potentially).

Additional configuration can optionally be performed using the following files:

config.yml                  Optional configuration of project settings, including your time zone for logging start and end times of analyses, and project-wide defaults (e.g. network and GTFS parameters)
_report_configuration.xlsx  Optional advanced configuration of reporting templates and languages.

You may also create configuration/datasets.yml (not shipped by default) to define dataset entries that can be referenced by name from multiple study region configuration files.

Optional configuration of other parameters is also possible.  Please visit our tool's website for further guidance:
https://global-healthy-liveable-cities.github.io/

The currently configured study regions are: {region_names}

To initialise a new study region configuration file, you can run the configuration utility with a codename for your study region, e.g.:

python configure.py [codename]

Or equivalently:

configure [codename]

If using Python or a Jupyter notebook, new regions can be configured using the configure() function, e.g.: ghsci.configure('your_codename_here')

To view instructions for other commands, enter: help
"""


def configuration(codename=None):
    """Initialise new study region configuration file."""
    if codename is not None:
        completion_directions = """Please open and edit this file in a text editor following the provided example directions in order to complete configuration for your study region.  Note that configured datasets need to be sourced and downloaded by the user and stored in the configured locations.  A completed example study region configuration can be viewed in the file 'data/examples/ES_Las_Palmas_2025/configuration/ES_Las_Palmas_2025.yml'; data has been supplied for this example city as a demonstration of how to set this up.\n\nTo view additional guidance on configuration, run the configure function without a codename. \n\nOnce configuration has been completed, the configuration can be loaded to proceed with analysis for this city.  For more help, see https://healthysustainablecities.github.io/software/#Configuration-1.\n\n"""
        # A codename may already be in use by a configuration file in the
        # project configuration folder, or by one co-located with a study
        # region's data.  Either way it is not available for a new region.
        existing = get_region_configs().get(codename)
        if existing:
            existing_paths = ', '.join(
                x.split('/process/')[-1] for x in existing
            )
            print_autobreak(
                f"\nConfiguration file for the specified study region codename '{codename}' already exists:\n{existing_paths}.\n\n{completion_directions}",
            )
        else:
            shutil.copyfile(
                '/home/ghsci/process/configuration/assets/region_template.yml',
                f'/home/ghsci/process/configuration/regions/{codename}.yml',
            )
            print_autobreak(
                f"\nNew region configuration file has been initialised using the codename, '{codename}', in the folder:\nconfiguration/regions/{codename}.yml\n\n{completion_directions}",
            )
    else:
        region_names = get_region_names()
        print_autobreak(
            configuration_instructions.format(
                region_names=list_seperation
                + list_seperation.join(sorted(region_names)),
            ),
        )


def main():
    try:
        codename = sys.argv[1]
        codename_length = len(codename)
        if codename_length >= 40:
            sys.exit(
                f"Study region codename must be less than 40 characters long. The specified codename '{codename}' is {codename_length} characters long.  Please try again with a shorter codename.",
            )
    except IndexError:
        codename = None
    configuration(codename)


if __name__ == '__main__':
    main()
