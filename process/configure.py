"""
Create project configuration files.

Copies configuration templates to configuration folder for custom modification.
"""

import os
import shutil
import sys

from subprocesses._utils import get_terminal_columns, print_autobreak
from subprocesses.ghsci import region_names

list_seperation = '\n  '
configuration_instructions = f"""
Before commencing analysis, your study regions will need to be configured.

Study regions are configured using .yml files located within the `configuration/regions` sub-folder. An example configuration for Las Palmas de Gran Canaria (for which data supporting analysis is included) has been provided in the file `process/configuration/regions/example_ES_Las_Palmas_2023.yml`, and further additional example regions have also been provided.  The name of the file, for example `example_ES_Las_Palmas_2023`, acts a codename for the city when used in processing and avoids issues with ambiguity when analysing multiple cities across different regions and time points: 'example' clarifies that this is an example, 'ES' clarifies that this is a Spanish city, 'Las_Palmas' is a common short way of writing the city's name, and the analysis uses data chosen to target 2023.  Using a naming convention like this is recommended when creating new region configuration files (e.g. ES_Barcelona_2023.yml, or AU_Melbourne_2023.yml).

The study region configuration files have a file extension .yml (YAML files), which means they are text files that can be edited in a text editor to define region specific details, including which datasets used - eg cities from a particular region could share common excerpts of population and OpenStreetMap, potentially).

Additional configuration may be required to define datasets referenced for regions, configuration of language for reporting using the following files:

datasets.yml: Configuration of datasets, which may be referenced by study regions of interest

_report_configuration.xlsx: (required to generate reports) Use to configure generation of images and reports generated for processed cities; in particular, the translation of prose and executive summaries for different languages.  This can be edited in a spreadsheet program like Microsoft Excel.

config.yml: (optional) Configuration of overall project, including your time zone for logging start and end times of analyses

Optional configuration of other parameters is also possible.  Please visit our tool's website for further guidance:
https://global-healthy-liveable-cities.github.io/

The currently configured study regions are: {list_seperation}{list_seperation.join(region_names)}

To initialise a new study region configuration file, you can run this script again providing your choice of codename:

python configure.py [codename]

Or equivalently:

configure [codename]

To view instructions for other commands, enter: help
"""

completion_directions = "Please open and edit this file in a text editor following the provided example directions in order to complete configuration for your study region.  A completed example study region configuration can be viewed in the file 'configuration/regions/example_ES_Las_Palmas_2023.yml'.\n\nTo view additional guidance on configuration, run this script again without a codename. \n\nOnce configuration has been completed, to proceed to analysis for this city, enter:\nanalysis"


def configuration(codename=None):
    if codename is not None:
        if os.path.exists(f'./configuration/regions/{codename}.yml'):
            print_autobreak(
                f"\nConfiguration file for the specified study region codename '{codename}' already exists:\nconfiguration/regions/{codename}.yml.\n\n{completion_directions} {codename}\n",
            )
        else:
            shutil.copyfile(
                './configuration/assets/region_template.yml',
                f'./configuration/regions/{codename}.yml',
            )
            print_autobreak(
                f"\nNew region configuration file has been initialised using the codename, '{codename}', in the folder:\nconfiguration/regions/{codename}.yml\n\n{completion_directions} {codename}\n",
            )
    else:
        print_autobreak(configuration_instructions)


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
