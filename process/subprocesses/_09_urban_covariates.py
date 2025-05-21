"""
Link urban covariates.

Create layer of additional urban study region covariates.
"""

import sys
import time

import geopandas as gpd
import ghsci
import numpy as np
import pandas as pd
from script_running_log import script_running_log
from sqlalchemy import text


def check_covariate_list(covariate_list, covariates):
    # Check presence of required columns
    not_covariate_list = [x for x in covariate_list if x not in covariates]
    if len(not_covariate_list) > 0:
        covariate_list = [
            x for x in covariate_list if x not in not_covariate_list
        ]
        print(
            'The following configured covariates are not present in the urban region data and will be ignored: ',
            not_covariate_list,
        )
    return covariate_list


def link_urban_covariates(codename):
    start = time.time()
    script = '_10_urban_covariates'
    task = 'Create layer of additional urban study region covariates'
    r = ghsci.Region(codename)
    if (
        'urban_region' in r.config
        and type(r.config['urban_region']) == dict
        and 'covariates' in r.config['urban_region']
        and type(r.config['urban_region']['covariates']) == dict
    ):
        covariate_list = r.config['urban_region']['covariates'].keys()
    else:
        covariate_list = []
    if len(covariate_list) > 0:
        if r.config['covariate_data'] == 'urban_query':
            # load covariate data
            covariates = gpd.read_file(r.config['urban_region']['data_dir'])
            covariate_list = check_covariate_list(
                covariate_list, covariates.columns,
            )
            # filter and retrieve covariate data for study region
            covariates = covariates.query(
                r.config['urban_query'].split(':')[1],
            )[covariate_list]
        elif r.config['covariate_data'] is not None and (
            str(r.config['covariate_data']) not in ['', 'nan']
        ):
            # if this field has been completed, and is not GHS, then assuming it is a csv file
            # localted in the city's study region folder, containg records only for this study region,
            # and with the covariate list included in the available variables
            covariates = pd.read_csv(
                f'{ghsci.folder_path}/process/data/{r.config["covariate_data"]}',
            )
            covariate_list = check_covariate_list(
                covariate_list, covariates.columns,
            )
            covariates = covariates[covariate_list]
        else:
            covariates = []
        if len(covariates) == 0:
            if r.config['covariate_data'] == 'urban_query':
                sys.exit(
                    f'\nThe urban query used to filter the covariate data ({r.config["urban_query"]}) '
                    'returned no results.  Please check the urban query and how this relates to '
                    'the configured urban region data and try again. You may want to explore the '
                    'urban region data in desktop software like QGIS to help with this.\n',
                )
            else:
                print(
                    'Study region covariate data input is either null or not recognised, '
                    'and null values will be returned for covariate list',
                )
            covariates = (
                pd.DataFrame(
                    zip(covariate_list, [np.nan] * len(covariate_list)),
                )
                .set_index(0)
                .transpose()
            )
        covariates = list(
            covariates[covariate_list].transpose().to_dict().values(),
        )[0]
        covariates_sql = ''
        for x in covariates:
            if str(covariates[x]) != 'nan':
                if type(covariates[x]) in [int, float]:
                    covariates_sql = (
                        f"""{covariates_sql},\r\n{covariates[x]} "{x}" """
                    )
                else:
                    covariates_sql = (
                        f"""{covariates_sql},\r\n'{covariates[x]}' "{x}" """
                    )
            else:
                covariates_sql = f"""{covariates_sql},\r\nNULL "{x}" """
    else:
        covariates_sql = ''

    sql = f"""
    DROP TABLE IF EXISTS urban_covariates;
    CREATE TABLE urban_covariates AS
    SELECT '{r.config["continent"]}'::text "Continent",
           '{r.config["country"]}'::text "Country",
           '{r.config["country_code"]}'::text "ISO 3166-1 alpha-2",
           study_region,
           area_sqkm "Area (sqkm)",
           pop_est "Population estimate",
           pop_per_sqkm "Population per sqkm",
           intersection_count "Intersections",
           intersections_per_sqkm "Intersections per sqkm"
           {covariates_sql}
    FROM urban_study_region;
    """
    with r.engine.begin() as conn:
        result = conn.execute(text(sql))

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    link_urban_covariates(codename)


if __name__ == '__main__':
    main()
