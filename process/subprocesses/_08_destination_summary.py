"""
Summarise destinations.

Summarise destination counts for grid cells.
"""

import sys
import time

import ghsci
from script_running_log import script_running_log
from sqlalchemy import text


def destination_summary(codename):
    start = time.time()
    script = '_08_destination_summary'
    task = 'Summarise destinations'
    r = ghsci.Region(codename)
    sql = f"""
    DROP TABLE IF EXISTS population_dest_summary;
    CREATE TABLE IF NOT EXISTS population_dest_summary AS
    SELECT p.grid_id,
           d.dest_name_full,
           COUNT(d.geom) AS count,
           p.geom
    FROM {r.config['population_grid']} p,
    destinations d
    WHERE ST_Intersects(p.geom,d.geom)
    GROUP BY p.grid_id, d.dest_name_full, p.geom;
    """
    with r.engine.begin() as conn:
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
           t.count/a.area_sqkm/(pop_est/10000.0) AS dest_per_sqkm_per_10kpop
    FROM urban_study_region a,
         (SELECT d.dest_name_full,
                 COUNT(d.*) count
            FROM destinations d,
                 urban_study_region c
        WHERE ST_Intersects(d.geom, c.geom)
        GROUP BY dest_name_full ) t
    ;
    """
    with r.engine.begin() as conn:
        result = conn.execute(text(count_sql))

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    destination_summary(codename)


if __name__ == '__main__':
    main()
