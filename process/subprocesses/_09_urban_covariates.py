"""
Link urban covariates.

Create layer of additional urban study region covariates.
"""

import sys
import time

import geopandas as gpd
import ghsci
import pandas as pd
from script_running_log import script_running_log
from sqlalchemy import text


def link_urban_covariates(codename):
    start = time.time()
    script = '_09_urban_covariates'
    task = 'Create layer of additional urban study region covariates'
    r = ghsci.Region(codename)
    covariate_list = r.config['urban_region']['covariates'].keys()
    if len(covariate_list) > 0:
        if r.config['covariate_data'] == 'urban_query':
            # load covariate data
            covariates = gpd.read_file(r.config['urban_region']['data_dir'])
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
                f'{r.config["region_dir"]}/{r.config["covariate_data"]}',
            )[covariate_list]
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
           u.study_region,
           u.area_sqkm "Area (sqkm)",
           u.pop_est "Population estimate",
           u.pop_per_sqkm "Population per sqkm",
           i.intersections "Intersections",
           i.intersections/u.area_sqkm "Intersections per sqkm"
           {covariates_sql}
    FROM urban_study_region u,
         (SELECT COUNT(c.geom) intersections
            FROM {r.config["intersections_table"]} c,
                 urban_study_region
          WHERE ST_Intersects(urban_study_region.geom, c.geom)) i
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
