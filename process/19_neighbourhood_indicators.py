# Script:  16_neighbourhood_indicators.py
# Purpose: Compile destinations results and neighbourhood indicator tables
# Author:  Carl Higgs 
# Date:    20180712

import os
import sys
import time
import psycopg2 

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'create destination indicator tables'

conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

print("Re-import areas to ensure proper indexing, and restrict other imported areas to study region.")
# Check if the table main_mb_2016_aust_full exists; if it does, these areas have previously been re-imported, so no need to re-do
curs.execute('''SELECT 1 WHERE to_regclass('public.main_mb_2016_aust_full') IS NOT NULL;''')
res = curs.fetchone()
if res is None:
  for area in areas:
    print('{}: '.format(areas[area]['name_f'])), 
    command = 'ogr2ogr -overwrite -progress -f "PostgreSQL" -a_srs "EPSG:{srid}" '.format(srid = srid) \
              + 'PG:"host={host} port=5432 dbname={db} '.format(host = db_host,db = db) \
              + 'user={user} password = {pwd}" '.format(user = db_user,pwd = db_pwd) \
              + '{shp} '.format(shp = areas[area]['data']) \
              + '-lco geometry_name="geom"  -lco precision=NO ' \
              + '-nlt MULTIPOLYGON' 
    # print(command)
    sp.call(command, shell=True) 
    curs.execute('''
    DELETE FROM  {area} a 
          USING {buffered_study_region} b 
      WHERE NOT ST_Intersects(a.geom,b.geom) 
             OR a.geom IS NULL;
    '''.format(area = areas[area]['table'],
               buffered_study_region = buffered_study_region))
    conn.commit()
else:
  print('''It appears that area linkage tables have previously been imported; nice one.\n''')

print("Create area level destination counts... ")
# We drop these tables first, since some destinations may have been processed since previously running.
# These queries are quick to run, so not much cost to drop and create again.
for area in areas:
  area_name = areas[area]['name_s']
  print("{}... ".format(areas[area]['name_f'])),
  query = '''
  DROP TABLE IF EXISTS {area_name}_dest_counts;
  CREATE TABLE IF NOT EXISTS {area_name}_dest_counts AS
  SELECT a.{area_id}, dest_class, count(d.geom) AS count
  FROM {area_table} a
  LEFT JOIN 
       study_destinations d ON st_contains(a.geom,d.geom)
  GROUP BY a.{area_id},dest_class
  ORDER BY a.{area_id},dest_class;  
  '''.format(area_name = area_name,
             area_table = areas[area]['table'],
             area_id = areas[area]['id'])
  # print(query)
  curs.execute(query)
  conn.commit()
  print("Done.")

# Legacy fallback code: Rename ABS IRSD table if it exists to ensure it works with future scripts
curs.execute('''ALTER TABLE IF EXISTS abs_2016_irsd RENAME TO area_disadvantage;''')
conn.commit()

print('Creating or replacing threshold functions ... '),
create_threshold_functions = '''
-- Function for returning counts of values in an array less than a threshold distance
-- e.g. an array of distances in m to destinations, evaluated against a threshold of 800m
-- SELECT gnaf_pid, count_in_threshold(distances,1600) FROM sport_3200m;
-- is equivalent to 
-- SELECT gnaf_pid, count(distances) 
--   FROM (SELECT gnaf_pid,unnest(array_agg) distances FROM sport_3200m) t 
-- WHERE distance < 1600 GROUP BY gnaf_pid;
CREATE OR REPLACE FUNCTION count_in_threshold(distances int[],threshold int) returns bigint as $$
    SELECT COUNT(*) 
    FROM unnest(distances) dt(b)
    WHERE b < threshold
$$ language sql;

-- a binary threshold indicator  (e.g. of access given distance and threshold)
CREATE OR REPLACE FUNCTION threshold_hard(distance int, threshold int, out int) 
    RETURNS NULL ON NULL INPUT
    AS $$ SELECT (distance < threshold)::int $$
    LANGUAGE SQL;

-- a soft threshold indicator (e.g. of access given distance and threshold)
CREATE OR REPLACE FUNCTION threshold_soft(distance int, threshold int) returns float AS 
$$
BEGIN
  -- We check to see if the value we are exponentiation is more or less than 100; if so,
  -- if so the result will be more or less either 1 or 0, respectively. 
  -- If the value we are exponentiating is much > abs(700) then we risk overflow/underflow error
  -- due to the value exceeding the numerical limits of postgresql
  -- If the value we are exponentiating is based on a positive distance, then we know it is invalid!
  -- For reference, a 10km distance with 400m threshold yields a check value of -120, 
  -- the exponent of which is 1.30418087839363e+052 and 1 - 1/(1+exp(-120)) is basically 1 - 1 = 0
  -- Using a check value of -100, the point at which zero is returned with a threshold of 400 
  -- is for distance of 3339km
  IF (distance < 0) 
      THEN RETURN NULL;
  ELSIF (-5*(distance-threshold)/(threshold::float) < -100) 
    THEN RETURN 0;
  ELSE 
    RETURN 1 - 1/(1+exp(-5*(distance-threshold)/(threshold::float)));
  END IF;
END;
$$
LANGUAGE plpgsql
RETURNS NULL ON NULL INPUT;  
  '''
curs.execute(create_threshold_functions)
print('Done.')

# Restrict to indicators associated with study region (except distance to closest dest indicators)
ind_matrix = df_inds[df_inds['locale'].str.contains('|'.join([locale,'\*']))]

# Get a list of all potential destinations for distance to closest 
# (some may not be present in region, will be null, so we can refer to them in later queries)
# destination names
categories = [x for x in df_destinations.destination.tolist()]
category_list = ','.join(categories)
category_types = '"{}" int'.format('" int, "'.join(categories))

# destination classes
array_categories = [x for x in df_destinations.destination_class.tolist()]
array_category_list = ','.join(array_categories)
array_category_types = '"{}" int[]'.format('" int[], "'.join(array_categories))

# get the set of distance to closest regions which match for this region
destinations = df_inds[df_inds['ind'].str.contains('destinations')]

print("Create summary table of destination distances (dest_distance_m)... "),
table = 'dest_distance_m'
crosstab = '''
DROP TABLE IF EXISTS dest_distance_m;
CREATE TABLE dest_distance_m AS
SELECT *
  FROM   crosstab(
   'SELECT {id}, dest_name, distance
    FROM   od_closest
    ORDER  BY 1,2'  -- could also just be "ORDER BY 1" here
  ,$$SELECT unnest('{curly_o}{category_list}{curly_c}'::text[])$$
   ) AS distance ("{id}" text, {category_types});
'''.format(id = points_id.lower(),
           curly_o = "{",
           curly_c = "}",
           category_list = category_list,
           category_types = category_types)
curs.execute(crosstab)
conn.commit()
create_index = '''CREATE UNIQUE INDEX {table}_idx ON {table} ({id});'''.format(table = table, id = points_id.lower())
curs.execute(create_index)
conn.commit()
print("Done.")


table = 'dest_distances_3200m'
print("Create summary table of distances to destinations in 3.2km ({table})".format(table = table)),
sql = '''SELECT dest_class FROM dest_type ORDER BY dest_class;'''
curs.execute(sql)
dest_class_in_region = [x[0] for x in curs.fetchall()]
create_table = '''
DROP TABLE IF EXISTS {table}; 
CREATE TABLE {table} AS SELECT {id} FROM parcel_dwellings;
'''.format(table = table, id = points_id.lower())
curs.execute(create_table)
conn.commit()
create_index = '''CREATE UNIQUE INDEX {table}_idx ON {table} ({id});'''.format(table = table, id = points_id.lower())
curs.execute(create_index)
conn.commit()
for dest_class in array_categories:
    add_field = '''
    -- Note that we take NULL for distance to closest in this context to mean absence of presence
    -- Error checking at other stages of processing should confirm whether this is the case.
    ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {dest_class} int[];
    '''.format(table = table, dest_class = dest_class)
    curs.execute(add_field)
    conn.commit()
    if dest_class in dest_class_in_region:
        update_field = '''
                       UPDATE {table} t SET 
                         {dest_class} = distances
                       FROM od_distances_3200m o
                       WHERE t.{id} = o.{id} AND dest_class = '{dest_class}';
                       '''.format(id = points_id.lower(),
                                  table = table, 
                                  dest_class = dest_class)
        curs.execute(update_field)
        conn.commit()
        print("."),
print(" Done.")

# Neighbourhood_indicators
print("Create nh_inds_distance (curated distance to closest table for re-use by other indicators)... "),
nh_distance = '''
DROP TABLE IF EXISTS {table};
CREATE TABLE IF NOT EXISTS {table} AS
SELECT 
       {id},
       activity_centres_2017                                                       AS activity_centres_hlc_2017     , 
       LEAST(convenience_osm,newsagent_osm,petrolstation_osm,market_osm)           AS convenience_osm_2018          , 
       supermarkets_2017                                                           AS supermarket_hlc_2017          , 
       supermarket_osm                                                             AS supermarket_osm_2018          , 
       gtfs_2018_stops                                                             AS pt_any_gtfs_hlc_2018          ,
       gtfs_2018_stop_30_mins_final                                                AS pt_freq_gtfs_hlc_2018         ,
       childcare_all_meet_2019                                                     AS childcare_meets_acequa_2019   ,
       primary_schools2018                                                         AS primary_school_acara_2017     ,
       secondary_schools2018                                                       AS secondary_school_acara_2017   ,
       LEAST(community_centre_osm,place_of_worship_osm)                            AS community_pow_osm_2018        ,
       libraries_2018                                                              AS libraries_hlc_2018            ,
       postoffice_osm                                                              AS postoffice_osm_2018           ,
       "Dental_GeneralDental"                                                      AS dentist_nhsd_2017             ,
       "CommunityHealthCare_Pharmacy"                                              AS pharmacy_nhsd_2017            ,
       "GeneralPracticeGP_GP"                                                      AS gp_nhsd_2017                  ,
       LEAST(bakery_osm,meat_seafood_osm,fruit_veg_osm,deli_osm)                   AS food_fresh_specialty_osm_2018 ,
       fastfood_2017                                                               AS food_fast_hlc_2017            ,
       LEAST(fastfood_osm,food_court_osm)                                          AS food_fast_osm_2018            ,
       LEAST(restaurant_osm,cafe_osm,pub_osm)                                      AS food_dining_osm_2018          ,
       LEAST(museum_osm, theatre_osm, cinema_osm, art_gallery_osm, art_centre_osm) AS culture_osm_2018              ,
       LEAST(bar_osm, nightclub_osm,pub_osm)                                       AS alcohol_nightlife_osm_2018    ,
       alcohol_osm                                                                 AS alcohol_offlicence_osm_2018   ,
       alcohol_offlicence                                                          AS alcohol_offlicence_hlc_2017_19,
       alcohol_onlicence                                                           AS alcohol_onlicence_hlc_2017_19 ,  
       tobacco_osm                                                                 AS tobacco_osm_2018              ,
       gambling_osm                                                                AS gambling_osm_2018           
FROM dest_distance_m;
CREATE UNIQUE INDEX {table}_idx ON  {table} ({id}); 
'''.format(id = points_id.lower(),table = 'nh_inds_distance')
curs.execute(nh_distance)
conn.commit()
print("Done.")

print("Create hard and soft threshold indicators for curated destination categories...")
for threshold_type in ['hard','soft']:
    for nh_threshold in [400,800,1000,1600]:
        print("  - nh_inds_{threshold_type}_{nh_threshold}m".format(threshold_type = threshold_type, nh_threshold = nh_threshold))
        sql = '''
        DROP TABLE IF EXISTS nh_inds_{threshold_type}_{nh_threshold}m;
        CREATE TABLE IF NOT EXISTS nh_inds_{threshold_type}_{nh_threshold}m AS
        SELECT  
        {id},
        threshold_{threshold_type}(activity_centres_hlc_2017     ,{nh_threshold}) AS activity_centres_hlc_2017     , 
        threshold_{threshold_type}(convenience_osm_2018          ,{nh_threshold}) AS convenience_osm_2018          , 
        threshold_{threshold_type}(supermarket_hlc_2017          ,{nh_threshold}) AS supermarket_hlc_2017          , 
        threshold_{threshold_type}(supermarket_osm_2018          ,{nh_threshold}) AS supermarket_osm_2018          , 
        threshold_{threshold_type}(pt_any_gtfs_hlc_2018          ,{nh_threshold}) AS pt_any_gtfs_hlc_2018          ,
        threshold_{threshold_type}(pt_freq_gtfs_hlc_2018         ,{nh_threshold}) AS pt_freq_gtfs_hlc_2018         ,
        threshold_{threshold_type}(childcare_meets_acequa_2019   ,{nh_threshold}) AS childcare_meets_acequa_2019   ,
        threshold_{threshold_type}(primary_school_acara_2017     ,{nh_threshold}) AS primary_school_acara_2017     ,
        threshold_{threshold_type}(secondary_school_acara_2017   ,{nh_threshold}) AS secondary_school_acara_2017   ,
        threshold_{threshold_type}(community_pow_osm_2018        ,{nh_threshold}) AS community_pow_osm_2018        ,
        threshold_{threshold_type}(libraries_hlc_2018            ,{nh_threshold}) AS libraries_hlc_2018            ,
        threshold_{threshold_type}(postoffice_osm_2018           ,{nh_threshold}) AS postoffice_osm_2018           ,
        threshold_{threshold_type}(dentist_nhsd_2017             ,{nh_threshold}) AS dentist_nhsd_2017             ,
        threshold_{threshold_type}(pharmacy_nhsd_2017            ,{nh_threshold}) AS pharmacy_nhsd_2017            ,
        threshold_{threshold_type}(gp_nhsd_2017                  ,{nh_threshold}) AS gp_nhsd_2017                  ,
        threshold_{threshold_type}(food_fresh_specialty_osm_2018 ,{nh_threshold}) AS food_fresh_specialty_osm_2018 ,
        threshold_{threshold_type}(food_fast_hlc_2017            ,{nh_threshold}) AS food_fast_hlc_2017            ,
        threshold_{threshold_type}(food_fast_osm_2018            ,{nh_threshold}) AS food_fast_osm_2018            ,
        threshold_{threshold_type}(food_dining_osm_2018          ,{nh_threshold}) AS food_dining_osm_2018          ,
        threshold_{threshold_type}(culture_osm_2018              ,{nh_threshold}) AS culture_osm_2018              ,
        threshold_{threshold_type}(alcohol_nightlife_osm_2018    ,{nh_threshold}) AS alcohol_nightlife_osm_2018    ,
        threshold_{threshold_type}(alcohol_offlicence_osm_2018   ,{nh_threshold}) AS alcohol_offlicence_osm_2018   ,
        threshold_{threshold_type}(alcohol_offlicence_hlc_2017_19,{nh_threshold}) AS alcohol_offlicence_hlc_2017_19,
        threshold_{threshold_type}(alcohol_onlicence_hlc_2017_19 ,{nh_threshold}) AS alcohol_onlicence_hlc_2017_19 ,  
        threshold_{threshold_type}(tobacco_osm_2018              ,{nh_threshold}) AS tobacco_osm_2018              ,
        threshold_{threshold_type}(gambling_osm_2018             ,{nh_threshold}) AS gambling_osm_2018           
        FROM nh_inds_distance ;
        CREATE UNIQUE INDEX nh_inds_{threshold_type}_{nh_threshold}m_idx ON  nh_inds_{threshold_type}_{nh_threshold}m ({id}); 
        '''.format(id = points_id.lower(),threshold_type = threshold_type, nh_threshold = nh_threshold)
        curs.execute(sql)
        conn.commit()
print("Done.")

print("Processing neighbourhood indicators:")

clean_up = '''
-- remove previous versions of indicators which could be confusing if persisting
DROP TABLE IF EXISTS dailyliving; 
DROP TABLE IF EXISTS daily_living; 
DROP TABLE IF EXISTS ind_dailyliving;
DROP TABLE IF EXISTS ind_foodratio;
DROP TABLE IF EXISTS ind_food_ratio;
DROP TABLE IF EXISTS ind_food_proportion;
DROP TABLE IF EXISTS ind_supermarket1000;
DROP TABLE IF EXISTS ind_pos_distance;
'''
curs.execute(clean_up)
conn.commit()

# Define table name and abbreviation
# This saves us having to retype these values, and allows the code to be more easily re-used
table = ['ind_daily_living','dl']
print(" - {table}".format(table = table[0])),
create_table = '''DROP TABLE IF EXISTS {table}; CREATE TABLE {table} AS SELECT {id} FROM parcel_dwellings;'''.format(table = table[0], id = points_id.lower())
curs.execute(create_table)
conn.commit()

for threshold_type in ['hard','soft']:
    for nh_threshold in [400,800,1000,1600]:
        populate_table = '''
        -- Note that we take NULL for distance to closest in this context to mean absence of presence
        -- Error checking at other stages of processing should confirm whether this is the case.
        ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {abbrev}_{threshold_type}_{nh_threshold}m float;
        UPDATE {table} t SET 
           {abbrev}_{threshold_type}_{nh_threshold}m = COALESCE(convenience_osm_2018,0) + 
                                                       GREATEST(COALESCE(supermarket_hlc_2017,0),COALESCE(supermarket_osm_2018,0)) + 
                                                       COALESCE(pt_any_gtfs_hlc_2018,0)
        FROM nh_inds_{threshold_type}_{nh_threshold}m nh
        WHERE t.{id} = nh.{id};
        '''.format(table = table[0], 
                   abbrev = table[1], 
                   id = points_id.lower(),
                   threshold_type = threshold_type, 
                   nh_threshold = nh_threshold)
        curs.execute(populate_table)
        conn.commit()
        print("."),
create_index = '''CREATE UNIQUE INDEX {table}_idx ON  {table} ({id});  '''.format(table = table[0], id = points_id.lower())
curs.execute(create_index)
print(" Done.")

table = ['ind_local_living','ll']
print(" - {table}".format(table = table[0])),
create_table = '''DROP TABLE IF EXISTS {table}; CREATE TABLE {table} AS SELECT {id} FROM parcel_dwellings;'''.format(table = table[0], id = points_id.lower())
curs.execute(create_table)
conn.commit()

for threshold_type in ['hard','soft']:
    for nh_threshold in [400,800,1000,1600]:
        populate_table = '''
        -- Note that we take NULL for distance to closest in this context to mean absence of presence
        -- Error checking at other stages of processing should confirm whether this is the case.
        ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {abbrev}_{threshold_type}_{nh_threshold}m float;
        UPDATE {table} t SET 
           {abbrev}_{threshold_type}_{nh_threshold}m = COALESCE(community_pow_osm_2018,0) + 
                                                       COALESCE(libraries_hlc_2018,0) +
                                                       COALESCE(childcare_meets_acequa_2019,0) +
                                                       COALESCE(dentist_nhsd_2017,0) +
                                                       COALESCE(gp_nhsd_2017,0) +
                                                       COALESCE(pharmacy_nhsd_2017,0) +
                                                       GREATEST(COALESCE(supermarket_hlc_2017,0),COALESCE(supermarket_osm_2018,0)) + 
                                                       COALESCE(convenience_osm_2018,0) +
                                                       COALESCE(food_fresh_specialty_osm_2018,0) +
                                                       COALESCE(postoffice_osm_2018,0) + 
                                                       COALESCE(pt_any_gtfs_hlc_2018,0)
        FROM nh_inds_{threshold_type}_{nh_threshold}m nh
        WHERE t.{id} = nh.{id};
        '''.format(table = table[0], 
                   abbrev = table[1], 
                   id = points_id.lower(),
                   threshold_type = threshold_type, 
                   nh_threshold = nh_threshold)
        curs.execute(populate_table)
        conn.commit()
        print("."),
create_index = '''CREATE UNIQUE INDEX {table}_idx ON  {table} ({id});  '''.format(table = table[0], id = points_id.lower())
curs.execute(create_index)
print(" Done.")


table = ['ind_walkability','wa']
print(" - {table}".format(table = table[0])),
create_table = '''DROP TABLE IF EXISTS {table}; CREATE TABLE {table} AS SELECT {id} FROM parcel_dwellings;'''.format(table = table[0], id = points_id.lower())
curs.execute(create_table)
conn.commit()
# we just calculate walkability at 1600m, so we'll set nh_threshold to that value
nh_threshold = 1600
for threshold_type in ['hard','soft']:
    populate_table = '''
    -- Note that we take NULL for distance to closest in this context to mean absence of presence
    -- Error checking at other stages of processing should confirm whether this is the case.
    ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {abbrev}_{threshold_type}_{nh_threshold}m float;
    UPDATE {table} t SET 
       {abbrev}_{threshold_type}_{nh_threshold}m = dl.z_dl + sc.z_sc + dd.z_dd
    FROM (SELECT {id}, (dl_{threshold_type}_{nh_threshold}m - AVG(dl_{threshold_type}_{nh_threshold}m) OVER())/stddev_pop(dl_{threshold_type}_{nh_threshold}m) OVER() as z_dl FROM ind_daily_living) dl
    LEFT JOIN (SELECT {id}, (sc_nh1600m - AVG(sc_nh1600m) OVER())/stddev_pop(sc_nh1600m) OVER() as z_sc FROM sc_nh1600m) sc ON sc.{id} = dl.{id}
    LEFT JOIN (SELECT {id}, (dd_nh1600m - AVG(dd_nh1600m) OVER())/stddev_pop(dd_nh1600m) OVER() as z_dd FROM dd_nh1600m) dd ON dd.{id} = dl.{id}
    WHERE t.{id} = dl.{id};
    '''.format(table = table[0], 
               abbrev = table[1], 
               id = points_id.lower(),
               threshold_type = threshold_type, 
               nh_threshold = nh_threshold)
    curs.execute(populate_table)
    conn.commit()
    print("."),
create_index = '''CREATE UNIQUE INDEX {table}_idx ON  {table} ({id});  '''.format(table = table[0], id = points_id.lower())
curs.execute(create_index)
print(" Done.")

table = ['ind_food','f']
print(" - {table}".format(table = table[0])),
create_table = '''DROP TABLE IF EXISTS {table}; CREATE TABLE {table} AS SELECT {id} FROM parcel_dwellings;'''.format(table = table[0], id = points_id.lower())
curs.execute(create_table)
conn.commit()
# we just calculate food ratio at 1600m, so we'll set nh_threshold to that value
nh_threshold = 1600
sql = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS supermarket_count int;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS fastfood_count int;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS food_proportion_{nh_threshold}m float;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS food_ratio_{nh_threshold}m float;
-- We can't use both the OSM and scraped data as we would expect this to lead to double counting
-- However, we can take the larger of the two values under the assumption that this represents
-- the more comprehensive record of neighbourhood information.
UPDATE {table} t 
SET supermarket_count = d.supermarkets, 
    fastfood_count    = d.fastfood,
    food_proportion_{nh_threshold}m =  d.supermarkets / (d.supermarkets + d.fastfood):: float,
    food_ratio_{nh_threshold}m =  d.supermarkets / NULLIF(d.fastfood:: float,0)
FROM (SELECT 
        {id},
        GREATEST(COALESCE(count_in_threshold(supermarket,1600),0),COALESCE(count_in_threshold(supermarket_osm,1600),0)) AS supermarkets,
        GREATEST(COALESCE(count_in_threshold(fast_food,1600),0),COALESCE(count_in_threshold(fastfood_osm,1600),0)) AS fastfood
      FROM dest_distances_3200m) d
WHERE t.{id} = d.{id} AND (d.supermarkets + d.fastfood) > 0;
'''.format(table = table[0], 
           abbrev = table[1], 
           id = points_id.lower(),
           nh_threshold = nh_threshold)
curs.execute(sql)
conn.commit()
print("."),
create_index = '''CREATE UNIQUE INDEX {table}_idx ON  {table} ({id});  '''.format(table = table[0], id = points_id.lower())
curs.execute(create_index)
print(" Done.")

# Create Open Space measures (distances, which can later be considered with regard to thresholds)
# In addition to public open space (pos), also includes sport areas and blue space
table = ['ind_os_distance','os']
print(" - {table}".format(table = table[0])),
create_table = '''DROP TABLE IF EXISTS {table}; CREATE TABLE {table} AS SELECT {id} FROM parcel_dwellings;'''.format(table = table[0], id = points_id.lower())
curs.execute(create_table)
conn.commit()

create_index = '''CREATE UNIQUE INDEX {table}_idx ON  {table} ({id});  '''.format(table = table[0], id = points_id.lower())
curs.execute(create_index)
print("."),

measure = 'pos_any_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 0
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_5k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 0.5
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_15k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 1.5
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_20k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 2
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_4k_10k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 0.4
                   AND aos_ha_public <= 1
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_10k_50k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 1
                   AND aos_ha_public <= 5
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_50k_200k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 5
                   AND aos_ha_public <= 20
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'pos_50k_sqm_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  min(distance) AS distance
             FROM parcel_dwellings p
             LEFT JOIN 
             (SELECT {id},
                    (obj->>'aos_id')::int AS aos_id,
                    (obj->>'distance')::int AS distance
              FROM od_aos_jsonb,
                   jsonb_array_elements(attributes) obj) o ON p.{id} = o.{id}
             LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id
                 WHERE pos.aos_id IS NOT NULL
                   AND aos_ha_public > 5
             GROUP BY p.{id}) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),

measure = 'sport_distances_3200m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int[];
UPDATE {table} t 
SET {measure} = os_filtered.distances
FROM parcel_dwellings orig
LEFT JOIN (SELECT p.{id}, 
                  array_agg(distance) AS distances
           FROM parcel_dwellings p
           LEFT JOIN (SELECT {id},
                             (obj->>'aos_id')::int AS aos_id,
                             (obj->>'distance')::int AS distance
                        FROM od_aos_jsonb,
                             jsonb_array_elements(attributes) obj
                       WHERE (obj->>'distance')::int < 3200) o ON p.{id} = o.{id}                  
           WHERE EXISTS -- we restrict our results to distances to AOS with sports facilities 
                       (SELECT 1 FROM open_space_areas sport,
                                      jsonb_array_elements(attributes) obj
                        WHERE (obj->>'leisure' IN ('golf_course','sports_club','sports_centre','fitness_centre','pitch','track','fitness_station','ice_rink','swimming_pool') 
                           OR (obj->>'sport' IS NOT NULL 
                          AND obj->>'sport' != 'no'))
                          AND  o.aos_id = sport.aos_id)
           GROUP BY p.{id} ) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print("."),


measure = 'pos_toilet_distance_m'
add_and_update_measure = '''
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {measure} int;
UPDATE {table} t 
SET {measure} = os_filtered.distance
FROM parcel_dwellings orig
LEFT JOIN (SELECT DISTINCT ON (p.gnaf_pid) p.gnaf_pid, distance
           FROM parcel_dwellings p
           LEFT JOIN   
                    (SELECT gnaf_pid,  
                    (obj->>'aos_id')::int AS aos_id, 
                    (obj->>'distance')::int AS distance 
                    FROM od_aos_jsonb, 
                    jsonb_array_elements(attributes) obj) o ON p.gnaf_pid = o.gnaf_pid 
           LEFT JOIN open_space_areas pos ON o.aos_id = pos.aos_id 
               WHERE pos.aos_id IS NOT NULL  
                 AND co_location_100m ? 'toilets'
           ORDER BY gnaf_pid, distance asc) os_filtered ON orig.{id} = os_filtered.{id}
WHERE t.{id} = orig.{id};
'''.format(id = points_id, table = table[0], measure = measure)
curs.execute(add_and_update_measure)
conn.commit()
print(" Done.")

# print("Create ISO37120 indicator (hard threshold is native version; soft threshold is novel...")
# to do... could base on the nh_inds with specific thresholds

# output to completion log    
script_running_log(script, task, start, locale)
conn.close()
