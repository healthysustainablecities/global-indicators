"""
Open space areas setup.

Prepare Areas of Open Space (AOS) for urban liveability indicators.
"""

import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
from script_running_log import script_running_log
from sqlalchemy import inspect, text


def add_required_osm_tags(engine, r, ghsci):
    """Define tags for which presence of values is suggestive of some kind of open space, given configuration parameter ('required tags')."""
    for shape in ['line', 'point', 'polygon', 'roads']:
        required_tags = '\n'.join(
            [
                (
                    f"""ALTER TABLE {r.config['osm_prefix']}_{shape} ADD COLUMN IF NOT EXISTS "{x}" varchar;"""
                )
                for x in ghsci.osm_open_space['os_required']['criteria']
            ],
        )
        sql = f"""
        -- Add other columns which are important if they exists, but not important if they don't
        -- --- except that their presence is required for ease of accurate querying.
        {required_tags}"""
        with engine.begin() as connection:
            connection.execute(text(required_tags))


def aos_setup_queries(engine, r, ghsci):
    """A set of queries used to set up a dataset of open space areas using OpenStreetMap data, given a set of configuration definitions."""
    db_contents = inspect(engine)
    if db_contents.has_table('aos_public_large_nodes_30m_line'):
        print(
            'Areas of Open Space (AOS) for urban liveability indicators has previously been prepared for this region.\n',
        )
    else:
        aos_setup_queries = [
            f"""
-- Create a 'Not Open Space' table
-- DROP TABLE IF EXISTS not_open_space;
CREATE TABLE IF NOT EXISTS not_open_space AS
SELECT ST_Union(geom) AS geom FROM {r.config['osm_prefix']}_polygon p
WHERE {ghsci.osm_open_space['exclusion_criteria']};
""",
            f"""
-- Create an 'Open Space' table
-- DROP TABLE IF EXISTS open_space;
CREATE TABLE IF NOT EXISTS open_space AS
SELECT p.* FROM {r.config['osm_prefix']}_polygon p
WHERE ({ghsci.osm_open_space['os_inclusion']['criteria']}
    OR p.landuse IN ({ghsci.osm_open_space['os_landuse']['criteria']})
    OR p.boundary IN ({ghsci.osm_open_space['os_boundary']['criteria']}));
""",
            """
-- Create unique POS id and add indices
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS os_id SERIAL PRIMARY KEY;
CREATE INDEX open_space_idx ON open_space USING GIST (geom);
CREATE INDEX  not_open_space_idx ON not_open_space USING GIST (geom);
""",
            """
-- Remove any portions of open space geometry intersecting excluded regions
UPDATE open_space p
SET geom = ST_Difference(p.geom,x.geom)
FROM not_open_space x
WHERE ST_Intersects(p.geom,x.geom);
-- Drop any empty geometries (ie. those which were wholly covered by excluded regions)
DELETE FROM open_space WHERE ST_IsEmpty(geom);
""",
            """
-- Create variable for park size
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS area_ha double precision;
UPDATE open_space SET area_ha = ST_Area(geom)/10000.0;
""",
            f"""
-- Create variable for associated line tags
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS tags_line jsonb;
WITH tags AS (
SELECT o.os_id,
    jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT l.amenity,l.leisure,l."natural",l.tourism,l.waterway) d)))AS attributes
FROM {r.config['osm_prefix']}_line  l,open_space o"""
            + """
WHERE ST_Intersects (l.geom,o.geom) )
UPDATE open_space o SET tags_line = attributes
FROM (SELECT os_id,
            jsonb_agg(distinct(attributes)) AS attributes
    FROM tags
    WHERE attributes != '{}'::jsonb
    GROUP BY os_id) t
WHERE o.os_id = t.os_id
AND t.attributes IS NOT NULL
;
""",
            f"""
-- Create variable for associated point tags
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS tags_point jsonb;
WITH tags AS (
SELECT o.os_id,
    jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT l.amenity,l.leisure,l."natural",l.tourism,l.historic) d)))AS attributes
FROM {r.config['osm_prefix']}_point l,open_space o"""
            + """
WHERE ST_Intersects (l.geom,o.geom) )
UPDATE open_space o SET tags_point = attributes
FROM (SELECT os_id,
            jsonb_agg(distinct(attributes)) AS attributes
    FROM tags
    WHERE attributes != '{}'::jsonb
    GROUP BY os_id) t
WHERE o.os_id = t.os_id
AND t.attributes IS NOT NULL
;
""",
            f"""
-- Create water feature indicator
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS water_feature boolean;
UPDATE open_space SET water_feature = FALSE;
UPDATE open_space SET water_feature = TRUE
WHERE "natural" IN ({ghsci.osm_open_space['os_water']['criteria']})
    OR landuse IN ({ghsci.osm_open_space['os_water']['criteria']})
    OR leisure IN ({ghsci.osm_open_space['os_water']['criteria']})
    OR sport IN ({ghsci.osm_open_space['os_water_sports']['criteria']})
    OR beach IS NOT NULL
    OR river IS NOT NULL
    OR water IS NOT NULL
    OR waterway IS NOT NULL
    OR wetland IS NOT NULL;
""",
            f"""
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS linear_features boolean;
UPDATE open_space SET linear_features = TRUE
WHERE waterway IN ({ghsci.osm_open_space['os_linear']['criteria']})
    OR "natural" IN ({ghsci.osm_open_space['os_linear']['criteria']})
    OR landuse IN ({ghsci.osm_open_space['os_linear']['criteria']})
    OR leisure IN ({ghsci.osm_open_space['os_linear']['criteria']}) ;
""",
            """
-- Create variable for AOS water geometry
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS water_geom geometry;
UPDATE open_space SET water_geom = geom WHERE water_feature = TRUE;
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS min_bounding_circle_area double precision;
UPDATE open_space SET min_bounding_circle_area = ST_Area(ST_MinimumBoundingCircle(geom));
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS min_bounding_circle_diameter double precision;
UPDATE open_space SET min_bounding_circle_diameter = 2*sqrt(min_bounding_circle_area / pi());
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS roundness double precision;
UPDATE open_space SET roundness = ST_Area(geom)/(ST_Area(ST_MinimumBoundingCircle(geom)));
""",
            f"""
-- Create indicator for linear features informed through EDA of OS topology
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS linear_feature boolean;
UPDATE open_space SET linear_feature = FALSE;
UPDATE open_space SET linear_feature = TRUE
WHERE {ghsci.osm_open_space['linear_feature_criteria']['criteria']};
""",
            """
---- Create 'Acceptable Linear Feature' indicator
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS acceptable_linear_feature boolean;
UPDATE open_space SET acceptable_linear_feature = FALSE WHERE linear_feature = TRUE;
UPDATE open_space o SET acceptable_linear_feature = TRUE
FROM (SELECT os_id,geom FROM open_space WHERE linear_feature = FALSE) nlf
WHERE o.linear_feature IS TRUE
AND  (
    -- acceptable if within a non-linear feature
    ST_Within(o.geom,nlf.geom)
OR  (
    -- acceptable if it intersects a non-linear feature if it is not too long
    -- and it has some reasonably strong relation with a non-linear feature
    o.min_bounding_circle_diameter < 800
    AND (
        -- a considerable proportion of geometry is within the non-linear feature
        (ST_Intersects(o.geom,nlf.geom)
        AND
        (st_area(st_intersection(o.geom,nlf.geom))/st_area(o.geom)) > .2)
    OR (
        -- acceptable if there is sufficent conjoint distance (> 50m) with a nlf
        ST_Length(ST_CollectionExtract(ST_Intersection(o.geom,nlf.geom), 2)) > 50
        AND o.os_id < nlf.os_id
        AND ST_Touches(o.geom,nlf.geom))))
    );
-- a feature identified as linear is acceptable as an OS if it is
--  large enough to contain an OS of sufficient size (0.4 Ha?)
-- (suggests it may be an odd shaped park with a lake; something like that)
-- Still, if it is really big its acceptability should be constrained
-- hence limit of min bounding circle diameter
UPDATE open_space o SET acceptable_linear_feature = TRUE
FROM open_space alt
WHERE o.linear_feature IS TRUE
AND  o.acceptable_linear_feature IS FALSE
AND o.min_bounding_circle_diameter < 800
AND  o.geom && alt.geom
AND st_area(st_intersection(o.geom,alt.geom))/10000.0 > 0.4
AND o.os_id != alt.os_id;
""",
            f"""
-- Remove potentially identifying tags from records
UPDATE open_space SET tags =  tags - {ghsci.osm_open_space['exclude_tags_like_name']} - ARRAY[{ghsci.osm_open_space['identifying_tags_to_exclude_other_than_name']['criteria']}]
;
""",
            f"""
-- Create variable to indicate public access, default of True
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS public_access boolean;
UPDATE open_space SET public_access = FALSE;
UPDATE open_space SET public_access = TRUE
WHERE {ghsci.osm_open_space['public_space']}
;
""",
            """
-- Check if area is within an indicated public access area
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS within_public boolean;
UPDATE open_space SET within_public = FALSE;
UPDATE open_space o
    SET within_public = TRUE
FROM open_space x
WHERE x.public_access = TRUE
    AND ST_CoveredBy(o.geom,x.geom)
    AND o.os_id!=x.os_id;
""",
            """
-- Check if area is within an indicated not public access area
-- for example, an OS may be within a non-public area nested within a public area
-- this additional check is required to ensure within_public is set to false
UPDATE open_space o
    SET public_access = FALSE
FROM open_space x
WHERE o.public_access = TRUE
    AND x.public_access = FALSE
    AND ST_CoveredBy(o.geom,x.geom)
    AND o.os_id!=x.os_id;
""",
            """
-- If an open space is within or co-extant with a space flagged as not having public access
-- which is not itself covered by a public access area
-- then it too should be flagged as not public (ie. public_access = FALSE)
UPDATE open_space o
    SET public_access = FALSE
FROM open_space x
WHERE o.public_access = TRUE
    AND x.public_access = FALSE
    AND x.within_public = FALSE
    AND ST_CoveredBy(o.geom,x.geom);
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS geom_public geometry;
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS geom_not_public geometry;
UPDATE open_space SET geom_public = geom WHERE public_access = TRUE;
UPDATE open_space SET geom_not_public = geom WHERE public_access = FALSE;
""",
            f"""
-- Create Areas of Open Space (AOS) table
-- the 'geom' attributes is the area within an AOS
--    -- this is what we want to use to evaluate collective OS area within the AOS (aos_ha)

-- DROP TABLE IF EXISTS open_space_areas;
CREATE TABLE IF NOT EXISTS open_space_areas AS
WITH clusters AS(
    SELECT unnest(ST_ClusterWithin(open_space.geom, .001)) AS gc
    FROM open_space
    WHERE (public_access IS TRUE
        OR
        (public_access IS FALSE
            AND
            within_public IS TRUE
            AND (acceptable_linear_feature IS TRUE
                OR
                linear_feature IS FALSE)))
    AND (linear_feature IS FALSE
            OR
            (acceptable_linear_feature IS TRUE
            ))
    AND linear_features IS NULL
UNION
    SELECT unnest(ST_ClusterWithin(not_public_os.geom, .001)) AS gc
    FROM open_space AS not_public_os
    WHERE public_access IS FALSE
    AND within_public IS FALSE
    AND linear_features IS NULL
UNION
    SELECT  linear_os.geom AS gc
    FROM open_space AS linear_os
    WHERE (linear_feature IS TRUE
    AND acceptable_linear_feature IS FALSE
    AND public_access IS TRUE
    AND linear_features IS NULL)
UNION
    SELECT  waterway_os.geom AS gc
    FROM open_space AS waterway_os
    WHERE linear_features IS TRUE
    )
, unclustered AS( --unpacking GeomCollections
    SELECT row_number() OVER () AS cluster_id, (ST_DUMP(gc)).geom AS geom
    FROM clusters)
SELECT cluster_id as aos_id,
    jsonb_agg(jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT {ghsci.osm_open_space['os_add_as_tags']['criteria']}) d))
        || hstore_to_jsonb(tags)
        || jsonb_build_object('tags_line',tags_line)
        || jsonb_build_object('tags_point',tags_point))) AS attributes,
    COUNT(1) AS numgeom,
    ST_Union(geom_public) AS geom_public,
    ST_Union(geom_not_public) AS geom_not_public,
    ST_Union(water_geom) AS geom_water,
    ST_Union(geom) AS geom
    FROM open_space
    INNER JOIN unclustered USING(geom)
    GROUP BY cluster_id;
""",
            """
CREATE UNIQUE INDEX aos_idx ON open_space_areas (aos_id);
CREATE INDEX idx_aos_jsb ON open_space_areas USING GIN (attributes);
""",
            """
-- Create variable for AOS size
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_public double precision;
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_not_public double precision;
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha double precision;
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_water double precision;
""",
            """
-- Calculate total area of AOS in Ha
UPDATE open_space_areas SET aos_ha_public = COALESCE(ST_Area(geom_public)/10000.0,0);
UPDATE open_space_areas SET aos_ha_not_public = COALESCE(ST_Area(geom_not_public)/10000.0,0);
UPDATE open_space_areas SET aos_ha = ST_Area(geom)/10000.0;
UPDATE open_space_areas SET aos_ha_water = COALESCE(ST_Area(geom_water)/10000.0,0);
""",
            """
-- Set water_feature as true where OS feature intersects a noted water feature
-- wet by association
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS has_water_feature boolean;
UPDATE open_space_areas SET has_water_feature = FALSE;
UPDATE open_space_areas o SET has_water_feature = TRUE
FROM (SELECT * from open_space WHERE water_feature = TRUE) w
WHERE ST_Intersects (o.geom,w.geom);
""",
            """
-- Create variable for Water percent
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS water_percent numeric;
UPDATE open_space_areas SET water_percent = 0;
UPDATE open_space_areas SET water_percent = 100 * aos_ha_water/aos_ha::numeric WHERE aos_ha > 0;
""",
            f"""
-- Create a linestring aos table
-- DROP TABLE IF EXISTS aos_line;
CREATE TABLE IF NOT EXISTS aos_line AS
WITH bounds AS
(SELECT aos_id, ST_SetSRID(st_astext((ST_Dump(geom)).geom),{r.config['crs']['srid']}) AS geom  FROM open_space_areas)
SELECT aos_id, ST_Length(geom)::numeric AS length, geom
FROM (SELECT aos_id, ST_ExteriorRing(geom) AS geom FROM bounds) t;
""",
            """
-- Generate a point every 20m along a park outlines:
-- DROP TABLE IF EXISTS aos_nodes;
CREATE TABLE IF NOT EXISTS aos_nodes AS
WITH aos AS
(SELECT aos_id,
        length,
        generate_series(0,1,20/length) AS fraction,
        geom FROM aos_line)
SELECT aos_id,
    row_number() over(PARTITION BY aos_id) AS node,
    ST_LineInterpolatePoint(geom, fraction)  AS geom
FROM aos;

CREATE INDEX aos_nodes_idx ON aos_nodes USING GIST (geom);
ALTER TABLE aos_nodes ADD COLUMN IF NOT EXISTS aos_entryid varchar;
UPDATE aos_nodes SET aos_entryid = aos_id::text || ',' || node::text;
""",
            """
-- Create subset data for public_open_space_areas
-- DROP TABLE IF EXISTS aos_public_osm;
CREATE TABLE IF NOT EXISTS aos_public_osm AS
-- restrict to features > 10 sqm (e.g. 5m x 2m; this is very small, but plausible - and should be excluded)
SELECT * FROM open_space_areas WHERE aos_ha_public > 0.001;
CREATE INDEX aos_public_osm_idx ON aos_nodes (aos_id);
CREATE INDEX aos_public_osm_gix ON aos_nodes USING GIST (geom);
""",
            """
-- Create table of points within 30m of lines (should be your road network)
-- Distinct is used to avoid redundant duplication of points where they are within 20m of multiple roads
-- DROP TABLE IF EXISTS aos_public_any_nodes_30m_line;
CREATE TABLE IF NOT EXISTS aos_public_any_nodes_30m_line AS
SELECT DISTINCT n.*
FROM aos_nodes n LEFT JOIN aos_public_osm a ON n.aos_id = a.aos_id,
    edges l
WHERE a.aos_id IS NOT NULL
AND ST_DWithin(n.geom ,l.geom,30);
CREATE INDEX aos_public_any_nodes_30m_line_gix ON aos_public_any_nodes_30m_line USING GIST (geom);
""",
            """
-- Create table of points within 30m of lines (should be your road network)
-- Distinct is used to avoid redundant duplication of points where they are within 20m of multiple roads
-- DROP TABLE IF EXISTS aos_public_large_nodes_30m_line;
CREATE TABLE IF NOT EXISTS aos_public_large_nodes_30m_line AS
SELECT DISTINCT n.*
FROM aos_nodes n LEFT JOIN aos_public_osm a ON n.aos_id = a.aos_id,
    edges l
WHERE a.aos_id IS NOT NULL
AND a.aos_ha_public > 1.5
AND ST_DWithin(n.geom ,l.geom,30);
CREATE INDEX aos_public_large_nodes_30m_line_gix ON aos_public_large_nodes_30m_line USING GIST (geom);
""",
        ]
        for sql in aos_setup_queries:
            query_start = time.time()
            print(f'\nExecuting: {sql}')
            with engine.begin() as connection:
                connection.execute(text(sql))
            print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')


def open_space_areas_setup(codename):
    # simple timer for log file
    start = time.time()
    script = '_06_open_space_areas_setup'
    task = 'Prepare Areas of Open Space (AOS)'
    r = ghsci.Region(codename)
    engine = r.get_engine()
    ghsci.osm_open_space[
        'exclusion_criteria'
    ] = f"{ghsci.osm_open_space['os_excluded_keys']['criteria']} OR {ghsci.osm_open_space['os_excluded_values']['criteria']}"
    ghsci.osm_open_space[
        'exclude_tags_like_name'
    ] = """(SELECT array_agg(tags) from (SELECT DISTINCT(skeys(tags)) tags FROM open_space) t WHERE tags ILIKE '%name%')"""
    ghsci.osm_open_space[
        'public_space'
    ] = f"{ghsci.osm_open_space['public_not_in']['criteria']} AND {ghsci.osm_open_space['additional_public_criteria']['criteria']}".replace(
        ',)', ')',
    )
    add_required_osm_tags(engine, r, ghsci)
    aos_setup_queries(engine, r, ghsci)
    # output to completion log
    script_running_log(r.config, script, task, start)
    engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    open_space_areas_setup(codename)


if __name__ == '__main__':
    main()
