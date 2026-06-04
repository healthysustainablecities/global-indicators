"""
Locate origins.

Calculate and store the distances to the two nearest nodes (node pairs)
on edges for all sample point origins.  Previously this was also done for destinations at this point, but this has now been re-located to the neighbourhood analysis step in order to process all destinations at once.
"""
import sys
import time

import ghsci
from script_running_log import script_running_log
from sqlalchemy import text


def nearest_node_locations(codename):
    """A set of queries used to set up a dataset of open space areas using OpenStreetMap data, given a set of configuration definitions."""
    start = time.time()
    script = '_07_nearest_node_locations'
    task = 'Pre-prepare distance associations between origins, destinations and nearest node locations'
    r = ghsci.Region(codename)
    points = f"{ghsci.settings['sample_points']['points']}_{ghsci.settings['sample_points']['point_sampling_interval']}"
    sql_queries = {
        'Create sampling points along network at a regular interval': f"""
        DROP TABLE IF EXISTS {points};
        CREATE TABLE IF NOT EXISTS {points} AS
        WITH line AS
                (SELECT
                    ogc_fid,
                    (ST_Dump(ST_Transform(geom,{r.config['crs']['srid']}))).geom AS geom
                FROM edges),
            linemeasure AS
                (SELECT
                    ogc_fid,
                    ST_AddMeasure(line.geom, 0, ST_Length(line.geom)) AS linem,
                    generate_series(0, ST_Length(line.geom)::int, {ghsci.settings['sample_points']['point_sampling_interval']}) AS metres
                FROM line),
            geometries AS (
                SELECT
                    ogc_fid,
                    metres,
                    (ST_Dump(ST_GeometryN(ST_LocateAlong(linem, metres), 1))).geom AS geom
                FROM linemeasure)
        SELECT
            row_number() OVER() AS point_id,
            geometries.ogc_fid,
            geometries.metres,
            ST_SetSRID(ST_MakePoint(ST_X(geometries.geom), ST_Y(geometries.geom)), {r.config['crs']['srid']}) AS geom
        FROM geometries,
             {r.config['population_grid']} p
        WHERE ST_Intersects(geometries.geom, p.geom);
        CREATE UNIQUE INDEX IF NOT EXISTS {points}_idx ON {points} (point_id);
        CREATE INDEX IF NOT EXISTS {points}_geom_idx ON {points} USING GIST (geom);
        """,
        'Only retain point locations with unique geometries (discard duplicates co-located at junction of edges, retaining only single point)': f"""
        DELETE FROM {points} a
            USING {points} b
        WHERE a.point_id > b.point_id
          AND st_equals(a.geom, b.geom)
          AND a.geom && b.geom;
        """,
        'Delete any sampling points which were created within the bounds of areas of open space (ie. along paths through parks)...': f"""
        DELETE FROM {points} p
        USING open_space_areas o
        WHERE ST_Intersects(o.geom,p.geom);
        """,
        'Delete any sampling points intersecting grids with population estimated below minimum threshold...': f"""
        DELETE FROM {points} p
        USING {r.config['population_grid']} o
        WHERE ST_Intersects(o.geom,p.geom)
        AND o.pop_est < {r.config['population']['pop_min_threshold']};
        """,
        'Create new columns and indices for sampling point edge and node relations': f"""
        -- Split query in two parts to avoid memory errors
        -- Both parts of full query took just over 30 seconds for Bangkok (1472479 sampling points
        -- part 1
        DROP TABLE IF EXISTS sampling_locate_line;
        CREATE TABLE sampling_locate_line AS
        SELECT  s.point_id,
                s.ogc_fid edge_ogc_fid,
                o.grid_id,
                s.metres,
                "from" n1,
                "to" n2,
                e.geom AS edge_geom,
                ST_LineLocatePoint(e.geom, n1.geom) llp1,
                ST_LineLocatePoint(e.geom, s.geom) llpm,
                ST_LineLocatePoint(e.geom, n2.geom) llp2,
                s.geom
            FROM {points} s
            LEFT JOIN edges e  ON s.ogc_fid = e.ogc_fid
            LEFT JOIN nodes n1 ON e."from" = n1.osmid
            LEFT JOIN nodes n2 ON e."to" = n2.osmid
            LEFT JOIN {r.config['population_grid']} o
                ON ST_Intersects(o.geom,s.geom);

        -- part 2 (split to save memory on parallel worker query)
        DROP TABLE IF EXISTS sampling_temp;
        CREATE TABLE sampling_temp AS
        SELECT point_id,
               edge_ogc_fid,
               grid_id,
               metres,
               n1,
               n2,
               ST_Length(ST_LineSubstring(t.edge_geom, LEAST(t.llp1,t.llpm),GREATEST(t.llp1,t.llpm)))::int n1_distance,
               ST_Length(ST_LineSubstring(t.edge_geom, LEAST(t.llp2,t.llpm),GREATEST(t.llp2,t.llpm)))::int n2_distance,
               t.geom
        FROM sampling_locate_line t;
        DROP TABLE {points};
        DROP TABLE sampling_locate_line;
        ALTER TABLE sampling_temp RENAME TO {points};
        CREATE UNIQUE INDEX IF NOT EXISTS {points}_ix ON {points} (point_id);
        CREATE INDEX IF NOT EXISTS {points}_edge_ogc_fid_idx ON {points} (edge_ogc_fid);
        CREATE INDEX IF NOT EXISTS {points}_n1_idx ON {points} (n1);
        CREATE INDEX IF NOT EXISTS {points}_n2_idx ON {points} (n2);
        CREATE INDEX IF NOT EXISTS {points}_gix ON {points} USING GIST (geom);
        """,
        'Recreate urban sample points': f"""
        DROP TABLE IF EXISTS urban_sample_points;
        CREATE TABLE IF NOT EXISTS urban_sample_points AS
        SELECT a.*
        FROM {points} a
        WHERE EXISTS (
            SELECT 1 
            FROM urban_study_region b 
            WHERE a.geom && b.geom 
            AND ST_Intersects(a.geom, b.geom)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS urban_sample_points_ix ON urban_sample_points (point_id);
        CREATE INDEX IF NOT EXISTS urban_sample_points_gix ON urban_sample_points USING GIST (geom);
        """,
    }
    for sql in sql_queries:
        print(f'\n{sql}... ')
        start_time = time.time()
        with r.engine.begin() as connection:
            connection.execute(text(sql_queries[sql]))
        end_time = time.time()
        print(f'Completed in {(end_time - start_time) / 60:.02f} minutes.')

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    nearest_node_locations(codename)


if __name__ == '__main__':
    main()
