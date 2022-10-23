# Purpose: Prepare Areas of Open Space (AOS) for ntnl liveability indicators
#           -- *** Assumes already in correct projection for project (e.g. GDA2020 GA LCC) *** 
#           -- copies features within study region to project gdb
#           -- calculates geodesic area in hectares
#           -- makes temporary line feature from polygons
#           -- traces vertices at set interval (aos_vertices in config file) -- pseudo entry points
#           -- creates three subset features of AOS pseudo-entries, at intervals of 20, 30 and 50m from road network
#           -- Preliminary EDA suggests the 30m distance pseudo entry points will be most appropriate to use 
#              for OD network analysis
#
#         This assumes 
#           -- a study region specific section of OSM has been prepared and is referenced in the configuration files
#           -- the postgis_sfcgal extension has been created in the active database
#
# Authors:  Carl Higgs, Julianna Rozek
# Date:    20180626

import subprocess as sp     # for executing external commands (e.g. pgsql2shp or ogr2ogr)
import time
import psycopg2
import json
from sqlalchemy import create_engine,inspect
from script_running_log import script_running_log

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Prepare Areas of Open Space (AOS)'

date_yyyy_mm_dd =  time.strftime("%Y%m%d")

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()  

engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
db_contents = inspect(engine)

# Drop redundant tables if exist
for table in ['aos_nodes_20m_line','aos_nodes_50m_line']:
    sql = f'''DROP TABLE IF EXISTS {table};'''
    curs.execute(sql)
    conn.commit()

# Back up old Open Space assets if exist, with date time
if not db_contents.has_table(f'open_space_pre_{date_yyyy_mm_dd}'):
    for table in ['open_space','open_space_areas','aos_nodes_30m_line']:
        sql = f'''ALTER TABLE IF EXISTS {table} RENAME TO {table}_pre_{date_yyyy_mm_dd}'''
        curs.execute(sql)
        conn.commit()
    
    for index in ["open_space_pkey","open_space_idx","aos_idx","idx_aos_jsb"]:
        sql = f'''ALTER INDEX IF EXISTS {index} RENAME TO {index}_pre_{date_yyyy_mm_dd}'''
        print(sql)
        curs.execute(sql)
        conn.commit()

specific_inclusion        = os_inclusion['criteria']
os_landuse                = os_landuse['criteria']
os_boundary               = os_boundary['criteria']
excluded_keys             = os_excluded_keys['criteria']
excluded_values           = os_excluded_values['criteria']
exclusion_criteria = '{} OR {}'.format(os_excluded_keys['criteria'],os_excluded_values['criteria'])
exclude_tags_like_name = '''(SELECT array_agg(tags) from (SELECT DISTINCT(skeys(tags)) tags FROM open_space) t WHERE tags ILIKE '%name%')'''
water_features            = os_water['criteria']              
linear_features           = os_linear['criteria']                               
water_sports              = os_water_sports['criteria']
linear_feature_criteria   = linear_feature_criteria['criteria']
identifying_tags          = identifying_tags_to_exclude_other_than_name['criteria'] 
os_add_as_tags            = os_add_as_tags['criteria']

public_space = '{} AND {}'.format(public_not_in['criteria'],additional_public_criteria['criteria']).replace(",)",")")

# Define tags for which presence of values is suggestive of some kind of open space 
# These are defined in the _project_configuration worksheet 'open_space_defs' under the 'required_tags' column.
for shape in ['line','point','polygon','roads']:
    required_tags = '\n'.join([(
        f'ALTER TABLE {osm_prefix}_{shape} ADD COLUMN IF NOT EXISTS "{x}" varchar;'
        ) for x in os_required['criteria']]
        )
    sql = f'''
    -- Add other columns which are important if they exists, but not important if they don't
    -- --- except that their presence is required for ease of accurate querying.
    {required_tags}'''
    curs.execute(sql)
    conn.commit()


aos_setup = [f'''
-- Create a 'Not Open Space' table
DROP TABLE IF EXISTS not_open_space;
CREATE TABLE not_open_space AS 
SELECT ST_Union(geom) AS geom FROM {osm_prefix}_polygon p 
WHERE {exclusion_criteria};
''',
f'''
-- Create an 'Open Space' table
DROP TABLE IF EXISTS open_space;
CREATE TABLE open_space AS 
SELECT p.* FROM {osm_prefix}_polygon p
WHERE ({specific_inclusion}
       OR p.landuse IN ({os_landuse})
       OR p.boundary IN ({os_boundary}));
''',
'''
-- Create unique POS id and add indices
ALTER TABLE open_space ADD COLUMN os_id SERIAL PRIMARY KEY;         
CREATE INDEX open_space_idx ON open_space USING GIST (geom);
CREATE INDEX  not_open_space_idx ON not_open_space USING GIST (geom);
''',
'''
-- Remove any portions of open space geometry intersecting excluded regions
UPDATE open_space p 
   SET geom = ST_Difference(p.geom,x.geom)
  FROM not_open_space x
 WHERE ST_Intersects(p.geom,x.geom);
-- Drop any empty geometries (ie. those which were wholly covered by excluded regions)
DELETE FROM open_space WHERE ST_IsEmpty(geom);
''',
'''
-- Create variable for park size 
ALTER TABLE open_space ADD COLUMN area_ha double precision; 
UPDATE open_space SET area_ha = ST_Area(geom)/10000.0;
''',
f'''
-- Create variable for associated line tags
ALTER TABLE open_space ADD COLUMN tags_line jsonb; 
WITH tags AS ( 
SELECT o.os_id,
       jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT l.amenity,l.leisure,l."natural",l.tourism,l.waterway) d)))AS attributes 
FROM {osm_prefix}_line  l,open_space o''' +
'''
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
''',
f'''
-- Create variable for associated point tags
ALTER TABLE open_space ADD COLUMN tags_point jsonb; 
WITH tags AS ( 
SELECT o.os_id,
       jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT l.amenity,l.leisure,l."natural",l.tourism,l.historic) d)))AS attributes 
FROM {osm_prefix}_point l,open_space o''' +
'''
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
''',
f'''
 -- Create water feature indicator
ALTER TABLE open_space ADD COLUMN water_feature boolean;
UPDATE open_space SET water_feature = FALSE;
UPDATE open_space SET water_feature = TRUE 
   WHERE "natural" IN ({water_features}) 
      OR landuse IN ({water_features})
      OR leisure IN ({water_features}) 
      OR sport IN ({water_sports})
      OR beach IS NOT NULL
      OR river IS NOT NULL
      OR water IS NOT NULL 
      OR waterway IS NOT NULL 
      OR wetland IS NOT NULL;
''',
f'''
ALTER TABLE open_space ADD COLUMN linear_features boolean; 
UPDATE open_space SET linear_features = TRUE
 WHERE waterway IN ({linear_features}) 
    OR "natural" IN ({linear_features}) 
    OR landuse IN ({linear_features})
    OR leisure IN ({linear_features}) ;
''',
'''
-- Create variable for AOS water geometry
ALTER TABLE open_space ADD COLUMN water_geom geometry; 
UPDATE open_space SET water_geom = geom WHERE water_feature = TRUE;
''',
'''
ALTER TABLE open_space ADD COLUMN min_bounding_circle_area double precision; 
UPDATE open_space SET min_bounding_circle_area = ST_Area(ST_MinimumBoundingCircle(geom));
''',
'''
ALTER TABLE open_space ADD COLUMN min_bounding_circle_diameter double precision; 
UPDATE open_space SET min_bounding_circle_diameter = 2*sqrt(min_bounding_circle_area / pi());
''',
'''
ALTER TABLE open_space ADD COLUMN roundness double precision; 
UPDATE open_space SET roundness = ST_Area(geom)/(ST_Area(ST_MinimumBoundingCircle(geom)));
''',
f'''
-- Create indicator for linear features informed through EDA of OS topology
ALTER TABLE open_space ADD COLUMN linear_feature boolean;
UPDATE open_space SET linear_feature = FALSE;
UPDATE open_space SET linear_feature = TRUE 
WHERE {linear_feature_criteria};
''',
'''
---- Create 'Acceptable Linear Feature' indicator
ALTER TABLE open_space ADD COLUMN acceptable_linear_feature boolean;
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
''',
f'''
-- Remove potentially identifying tags from records
UPDATE open_space SET tags =  tags - {exclude_tags_like_name} - ARRAY[{identifying_tags}]
;
''',   
f'''
-- Create variable to indicate public access, default of True
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS public_access boolean; 
UPDATE open_space SET public_access = FALSE;
UPDATE open_space SET public_access = TRUE
WHERE {public_space}
 ;
''',
 '''
 -- Check if area is within an indicated public access area
 ALTER TABLE open_space ADD COLUMN within_public boolean;
 UPDATE open_space SET within_public = FALSE;
 UPDATE open_space o
    SET within_public = TRUE
   FROM open_space x
  WHERE x.public_access = TRUE
    AND ST_CoveredBy(o.geom,x.geom)
    AND o.os_id!=x.os_id;
''',
 '''
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
''',
 '''
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
''',
'''
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS geom_public geometry; 
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS geom_not_public geometry; 
UPDATE open_space SET geom_public = geom WHERE public_access = TRUE;
UPDATE open_space SET geom_not_public = geom WHERE public_access = FALSE;
''',
f'''
-- Create Areas of Open Space (AOS) table
-- the 'geom' attributes is the area within an AOS 
--    -- this is what we want to use to evaluate collective OS area within the AOS (aos_ha)

DROP TABLE IF EXISTS open_space_areas; 
CREATE TABLE open_space_areas AS 
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
       jsonb_agg(jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT {os_add_as_tags}) d)) 
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
''',
''' 
CREATE UNIQUE INDEX aos_idx ON open_space_areas (aos_id);  
CREATE INDEX idx_aos_jsb ON open_space_areas USING GIN (attributes);
''',
''' 
-- Create variable for AOS size 
ALTER TABLE open_space_areas ADD COLUMN aos_ha_public double precision; 
ALTER TABLE open_space_areas ADD COLUMN aos_ha_not_public double precision; 
ALTER TABLE open_space_areas ADD COLUMN aos_ha double precision; 
ALTER TABLE open_space_areas ADD COLUMN aos_ha_water double precision; 
''',
'''
-- Calculate total area of AOS in Ha
UPDATE open_space_areas SET aos_ha_public = COALESCE(ST_Area(geom_public)/10000.0,0);
UPDATE open_space_areas SET aos_ha_not_public = COALESCE(ST_Area(geom_not_public)/10000.0,0);
UPDATE open_space_areas SET aos_ha = ST_Area(geom)/10000.0; 
UPDATE open_space_areas SET aos_ha_water = COALESCE(ST_Area(geom_water)/10000.0,0);
''',
'''
 -- Set water_feature as true where OS feature intersects a noted water feature
 -- wet by association
ALTER TABLE open_space_areas ADD COLUMN has_water_feature boolean; 
UPDATE open_space_areas SET has_water_feature = FALSE; 
UPDATE open_space_areas o SET has_water_feature = TRUE 
   FROM (SELECT * from open_space WHERE water_feature = TRUE) w
   WHERE ST_Intersects (o.geom,w.geom);
''',
'''
-- Create variable for Water percent
ALTER TABLE open_space_areas ADD COLUMN water_percent numeric; 
UPDATE open_space_areas SET water_percent = 0; 
UPDATE open_space_areas SET water_percent = 100 * aos_ha_water/aos_ha::numeric WHERE aos_ha > 0; 
''',
f'''
-- Create a linestring aos table 
DROP TABLE IF EXISTS aos_line;
CREATE TABLE aos_line AS 
WITH bounds AS
   (SELECT aos_id, ST_SetSRID(st_astext((ST_Dump(geom)).geom),{srid}) AS geom  FROM open_space_areas)
SELECT aos_id, ST_Length(geom)::numeric AS length, geom    
FROM (SELECT aos_id, ST_ExteriorRing(geom) AS geom FROM bounds) t;
''',
'''
-- Generate a point every 20m along a park outlines: 
DROP TABLE IF EXISTS aos_nodes; 
CREATE TABLE aos_nodes AS 
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
ALTER TABLE aos_nodes ADD COLUMN aos_entryid varchar; 
UPDATE aos_nodes SET aos_entryid = aos_id::text || ',' || node::text; 
''',
'''
-- Create subset data for public_open_space_areas
DROP TABLE IF EXISTS aos_public_osm;
CREATE TABLE aos_public_osm AS
-- restrict to features > 10 sqm (e.g. 5m x 2m; this is very small, but plausible - and should be excluded)
SELECT * FROM open_space_areas WHERE aos_ha_public > 0.001;
CREATE INDEX aos_public_osm_idx ON aos_nodes (aos_id);
CREATE INDEX aos_public_osm_gix ON aos_nodes USING GIST (geom);
''',
f'''
-- Create table of points within 30m of lines (should be your road network) 
-- Distinct is used to avoid redundant duplication of points where they are within 20m of multiple roads 
DROP TABLE IF EXISTS aos_public_any_nodes_30m_line;
CREATE TABLE aos_public_any_nodes_30m_line AS 
SELECT DISTINCT n.* 
FROM aos_nodes n LEFT JOIN aos_public_osm a ON n.aos_id = a.aos_id,
     edges l
WHERE a.aos_id IS NOT NULL
  AND ST_DWithin(n.geom ,l.geom,30);
CREATE INDEX aos_public_any_nodes_30m_line_gix ON aos_public_any_nodes_30m_line USING GIST (geom);
''',
f'''
-- Create table of points within 30m of lines (should be your road network) 
-- Distinct is used to avoid redundant duplication of points where they are within 20m of multiple roads 
DROP TABLE IF EXISTS aos_public_large_nodes_30m_line;
CREATE TABLE aos_public_large_nodes_30m_line AS 
SELECT DISTINCT n.* 
FROM aos_nodes n LEFT JOIN aos_public_osm a ON n.aos_id = a.aos_id,
     edges l
WHERE a.aos_id IS NOT NULL
  AND a.aos_ha_public > 1.5
  AND ST_DWithin(n.geom ,l.geom,30);
CREATE INDEX aos_public_large_nodes_30m_line_gix ON aos_public_large_nodes_30m_line USING GIST (geom);
'''
]

for sql in aos_setup:
    start = time.time()
    print("\nExecuting: {}".format(sql))
    curs.execute(sql)
    conn.commit()
    print("Executed in {} mins".format((time.time()-start)/60))
 
curs.execute(grant_query)
conn.commit()

# output to completion log    
script_running_log(script, task, start, locale)
conn.close()
