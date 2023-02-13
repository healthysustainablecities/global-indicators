"""
Link urban covariates.

Create layer of additional urban study region covariates.
"""

import time

import geopandas as gpd
import pandas as pd
import psycopg2
from _project_setup import *
from script_running_log import script_running_log


def main():
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create layer of additional urban study region covariates'
    conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
    curs = conn.cursor()
    if len(covariate_list) > 0:
        if covariate_data is not None and covariate_data.startswith('GHS:'):
            # load covariate data
            covariates = gpd.read_file(urban_region['data_dir'])
            # filter and retrieve covariate data for study region
            covariates = covariates.query(covariate_data.split(':')[1])[
                covariate_list
            ]
        elif covariate_data is not None and (
            str(covariate_data) not in ['', 'nan']
        ):
            # if this field has been completed, and is not GHS, then assuming it is a csv file
            # localted in the city's study region folder, containg records only for this study region,
            # and with the covariate list included in the available variables
            covariates = pd.read_csv(f'{locale_dir}/{covariate_data}')[
                covariate_list
            ]
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
        covariates_sql = ',\r\n' + ',\r\n'.join(
            [
                f'{covariates[x]} "{x}"'
                if str(covariates[x]) != 'nan'
                else f'NULL "{x}"'
                for x in covariates
            ],
        )
    else:
        covariates_sql = ''

    sql = f"""
    DROP TABLE IF EXISTS urban_covariates;
    CREATE TABLE urban_covariates AS
    SELECT '{continent}'::text "Continent",
           '{country}'::text "Country",
           '{region}'::text "ISO 3166-1 alpha-2",
           u.study_region "City",
           u.area_sqkm "Area (sqkm)",
           u.pop_est "Population estimate",
           u.pop_per_sqkm "Population per sqkm",
           i.intersections "Intersections",
           i.intersections/u.area_sqkm "Intersections per sqkm"
           {covariates_sql}
    FROM urban_study_region u,
         (SELECT COUNT(c.geom) intersections
            FROM {intersections_table} c,
                 urban_study_region
          WHERE ST_Intersects(urban_study_region.geom, c.geom)) i
    """
    curs.execute(sql)
    conn.commit()

    script_running_log(script, task, start, locale)
    conn.close()


if __name__ == '__main__':
    main()
