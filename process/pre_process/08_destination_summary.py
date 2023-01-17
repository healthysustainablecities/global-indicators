"""
Summarise destinations.

Summarise destination counts for grid cells.
"""

import time

import pandas as pd
from _project_setup import *
from script_running_log import script_running_log
from sqlalchemy import create_engine, inspect, text


def main():
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = "Summarise destinations and public open space"
    date_yyyymmdd = time.strftime("%d%m%Y")

    engine = create_engine(
        f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}", future=True
    )
    sql = f"""
    DROP TABLE IF EXISTS population_dest_summary;
    CREATE TABLE IF NOT EXISTS population_dest_summary AS
    SELECT p.grid_id,
           d.dest_name_full,
           COUNT(d.geom) AS count,
           p.geom
    FROM {population_grid} p,
    destinations d
    WHERE ST_Intersects(p.geom,d.geom)
    GROUP BY p.grid_id, d.dest_name_full, p.geom;
    """
    with engine.begin() as conn:
        result = conn.execute(text(sql))

    count_sql = """
    DROP TABLE IF EXISTS urban_dest_summary;
    CREATE TABLE IF NOT EXISTS urban_dest_summary AS
    SELECT a."study_region",
           t.dest_name_full,
           t.count,
           a.pop_est,
           a.area_sqkm,
           a.pop_per_sqkm,
           t.count/a.area_sqkm AS dest_per_sqkm,
           t.count/a.area_sqkm/(pop_est/10000) AS dest_per_sqkm_per_10kpop
    FROM urban_study_region a,
         (SELECT d.dest_name_full,
                 COUNT(d.*) count
            FROM destinations d,
                 urban_study_region c
        WHERE ST_Intersects(d.geom, c.geom)
        GROUP BY dest_name_full ) t
    ;
    """
    with engine.begin() as conn:
        result = conn.execute(text(sql))

    script_running_log(script, task, start, locale)
    engine.dispose()


if __name__ == "__main__":
    main()
