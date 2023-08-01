"""Perform series of study region analysis subprocesses to generate spatial urban indicators."""

import shutil
import subprocess
import sys

import yaml
from subprocesses._utils import get_terminal_columns, print_autobreak

# Load study region configuration
from subprocesses.ghsci import (
    Region,
    __version__,
    date_hhmm,
    folder_path,
    os,
    settings,
    time,
)
from tqdm.auto import tqdm


def archive_parameters(r, settings):
    current_parameters = {
        'date': date_hhmm,
        'software_version': __version__,
        'project': settings,
        r.codename: r.config,
    }
    r = Region(r.codename)
    parameters_exists = os.path.isfile(
        f'{r.config["region_dir"]}/_parameters.yml',
    )
    if parameters_exists:
        with open(f'{r.config["region_dir"]}/_parameters.yml') as f:
            saved_parameters = yaml.safe_load(f)
    else:
        saved_parameters = None
    if (
        saved_parameters is not None
        and current_parameters['project'] == saved_parameters['project']
        and current_parameters[r.codename] == saved_parameters[r.codename]
    ):
        print_autobreak(
            f"The copy of region and project parameters from a previous analysis dated {saved_parameters['date'].replace('_',' at ')} saved in the output directory as _parameters_{saved_parameters['date']}.yml matches the current configuration parameters and will be retained.\n\n",
        )
    elif saved_parameters is not None:
        shutil.copyfile(
            f'{r.config["region_dir"]}/_parameters.yml',
            f'{r.config["region_dir"]}/_parameters_{saved_parameters["date"]}.yml',
        )
        with open(f'{r.config["region_dir"]}/_parameters.yml', 'w') as f:
            yaml.safe_dump(
                current_parameters,
                f,
                default_style=None,
                default_flow_style=False,
                sort_keys=False,
                width=float('inf'),
            )
        print_autobreak(
            f"Project or region parameters from a previous analysis dated {saved_parameters['date'].replace('_',' at ')} appear to have been modified. The previous parameter record file has been copied to the output directory as _parameters_{saved_parameters['date']}.yml, while the current ones have been saved as _parameters.yml.\n",
        )
    else:
        with open(f'{r.config["region_dir"]}/_parameters.yml', 'w') as f:
            yaml.safe_dump(
                current_parameters,
                f,
                default_style=None,
                default_flow_style=False,
                sort_keys=False,
                width=float('inf'),
            )
        print_autobreak(
            f'A dated copy of project and region parameters has been saved as {r.config["region_dir"]}/_parameters.yml.'.replace(
                '/home/ghsci/', '',
            ),
        )


def analysis(r):
    """Perform series of study region analysis subprocesses to generate spatial urban indicators."""
    if type(r) == str:
        codename = r
        r = Region(codename)
    else:
        codename = r.codename
    print(r.header)
    # Create study region folder if not exists
    if not os.path.exists(f'{folder_path}/process/data/_study_region_outputs'):
        os.makedirs(f'{folder_path}/process/data/_study_region_outputs')
    if not os.path.exists(r.config['region_dir']):
        os.makedirs(r.config['region_dir'])

    archive_parameters(r, settings)

    print_autobreak(
        f"\nAnalysis time zone: {settings['project']['analysis_timezone']} (to set time zone for where you are, edit config.yml)\n\n",
    )
    start_analysis = time.time()
    print(f"Analysis start:\t{time.strftime('%Y-%m-%d_%H%M')}")
    study_region_setup = {
        '_00_create_database.py': 'Create database',
        '_01_create_study_region.py': 'Create study region',
        '_02_create_osm_resources.py': 'Create OpenStreetMap resources',
        '_03_create_network_resources.py': 'Create pedestrian network',
        '_04_create_population_grid.py': 'Align population distribution',
        '_05_compile_destinations.py': 'Compile destinations',
        '_06_open_space_areas_setup.py': 'Identify public open space',
        '_07_locate_origins_destinations.py': 'Analyse local neighbourhoods',
        '_08_destination_summary.py': 'Summarise spatial distribution',
        '_09_urban_covariates.py': 'Collate urban covariates',
        '_10_gtfs_analysis.py': 'Analyse GTFS Feeds',
        '_11_neighbourhood_analysis.py': 'Analyse neighbourhoods',
        '_12_aggregation.py': 'Aggregate region summary analyses',
    }
    pbar = tqdm(
        study_region_setup,
        position=0,
        leave=True,
        bar_format='{desc:35} {percentage:3.0f}%|{bar:30}| ({n_fmt}/{total_fmt})',
    )
    append_to_log_file = open(
        f'{r.config["region_dir"]}/__{r.name}__{codename}_processing_log.txt',
        'a',
    )
    completed = False
    try:
        for step in pbar:
            pbar.set_description(study_region_setup[step])
            process = subprocess.check_call(
                f'python {step} {codename}',
                shell=True,
                cwd='./subprocesses',
                stderr=append_to_log_file,
                stdout=append_to_log_file,
            )
        completed = True
    except Exception as e:
        print_autobreak(
            f'\n\nProcessing {step} failed: {e}\n\n Please review the processing log file for this study region for more information on what caused this error and how to resolve it. The file __{r.name}__{codename}_processing_log.txt is located in the output directory and may be opened for viewing in a text editor.',
        )
    finally:
        duration = (time.time() - start_analysis) / 60
        print(
            f'Analysis end:\t{time.strftime("%Y-%m-%d_%H%M")} (approximately {duration:.1f} minutes)',
        )
        if completed:
            print_autobreak(
                f'\nTo generate resources (data files, documentation, maps, figures, reports) using the processed results for this study region, enter "generate {codename}" if using the command line, or using the generate() function if using python, e.g. "r.generate()".'
                f"\n\nThe Postgis SQL database for this city {r.config['db']} can also be accessed from QGIS or other applications by specifying the server as 'localhost' and port as '5433', with username '{settings['sql']['db_user']}' and password '{settings['sql']['db_pwd']}'."
                'The SQL database can also be explored on the command line by using the above password after entering,'
                f"""'psql -U {settings['sql']['db_user']} -h gateway.docker.internal -p 5433 -d "{r.config['db']}"'. """
                "When using psql, you can type '\\dt' to list database tables, '\\d <table_name>' to list table columns, and 'SELECT * FROM <table_name> LIMIT 10;' to view the first 10 rows of a table.  To exit psql, enter '\\q'."
                '\n\n',
            )


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    r = Region(codename)
    r.analysis()


if __name__ == '__main__':
    main()
