# Script:  19_area_indicators.py
# Purpose: Create area level indicator tables
# Author:  Carl Higgs 
# Date:    20 July 2018

import os
import sys
import time
import psycopg2 
import subprocess as sp     # for executing external commands (e.g. pgsql2shp)

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Create area level indicator tables for {}'.format(locale)


# Read in indicator description matrix
ind_matrix = df_inds

# Restrict to indicators associated with study region
ind_matrix = ind_matrix[ind_matrix['locale'].str.contains(locale)]

# Restrict to indicators with a defined source, or the urban liveability index
ind_matrix = ind_matrix[((pandas.notnull(ind_matrix['Source'])) | (ind_matrix['ind']=='uli'))]

# Make concatenated indicator and tag name (e.g. 'walk_14' + 'hard')
# Tags could be useful later as can allow to search by name for e.g. threshold type,
# or other keywords (policy, binary, obsolete, planned --- i don't know, whatever)
# These tags are tacked on the end of the ind name seperated with underscores
ind_matrix['indicators'] = ind_matrix['ind'] + ind_matrix['tags'].fillna('')

# Compile list of indicators
ind_list = ind_matrix['indicators'].tolist()

# Note that postgresql ignores null values when calculating averages
# We can passively exploit this feature in the case of POS as those parcels with nulls will be 
# ignored --- this is exactly what we want.  Excellent.
ind_avg = ',\n'.join("AVG(" + ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') + ind_matrix['indicators'] + " ) AS " + ind_matrix['indicators'])

ind_sd = ',\n'.join("stddev_samp(" + ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') + ind_matrix['indicators'] + " ) AS " + ind_matrix['indicators'])

# Create query for indicator range (including scaling of percent variables)
ind_range = ',\n'.join("ROUND(MIN(" +
                       ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') +
                       ind_matrix['indicators'] + 
                       ")::numeric,1)::text || ' to ' ||ROUND(MAX(" +
                       ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') +
                       ind_matrix['indicators'] + 
                       ")::numeric,1)::text AS " +
                       ind_matrix['indicators'])
# Create query for median       
ind_median = ',\n'.join("round(percentile_cont(0.5) WITHIN GROUP (ORDER BY " +
                        ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') + ind_matrix['indicators'] + 
                       ")::numeric,1) AS " +
                       ind_matrix['indicators'])                       
                       
# Create query for Interquartile range interval (25% to 75%) to represent the range within which the middle 50% of observations lie                       
ind_iqr = ',\n'.join("round(percentile_cont(0.25) WITHIN GROUP (ORDER BY " +
                       ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') +
                       ind_matrix['indicators'] + 
                       ")::numeric,1)::text || ' to ' ||round(percentile_cont(0.75) WITHIN GROUP (ORDER BY " +
                       ind_matrix['agg_scale'].apply(lambda x: '100.0*' if x == 100 else '1.0*') +
                       ind_matrix['indicators'] + 
                       ")::numeric,1)::text AS " +
                       ind_matrix['indicators'])                  

# Create a second pass table including binary indicators
## TO DO

# Create query for percentile           
ind_percentile = ',\n'.join("round(100*cume_dist() OVER(ORDER BY "+
                            ind_matrix['indicators'] + 
                            " " +
                            ind_matrix['polarity'] +
                            ")::numeric,0) AS " +
                            ind_matrix['indicators'])        

# Map query for raw indicators
map_ind_raw = ',\n'.join("round(raw." +
                         ind_matrix['indicators'] + 
                         "::numeric,1) AS r_" +
                         ind_matrix['indicators'])   
                         
# Map query for sd indicators
map_ind_sd = ',\n'.join("round(sd." +
                         ind_matrix['indicators'] + 
                         "::numeric,1) AS sd_" +
                         ind_matrix['indicators'])                          
 
# Map query for percentile indicators
map_ind_percentile = ',\n'.join("round(perc." +
                          ind_matrix['indicators'] + 
                          "::numeric,1) AS p_" +
                          ind_matrix['indicators'])               
 
# Map query for range indicators
map_ind_range = ',\n'.join("range." + 
                           ind_matrix['indicators'] + 
                           " AS d_" +
                           ind_matrix['indicators'])                   
 
# Map query for median indicators
map_ind_median = ',\n'.join("median." + 
                         ind_matrix['indicators'] + 
                         " AS med_" +
                         ind_matrix['indicators']) 
                         
# Map query for iqr indicators
map_ind_iqr = ',\n'.join("iqr." + 
                         ind_matrix['indicators'] + 
                         " AS m_" +
                         ind_matrix['indicators']) 
                         
exclusion_criteria = 'WHERE  {0} NOT IN (SELECT DISTINCT({0}) FROM excluded_parcels) AND sos_name_2016 IS NOT NULL'.format(points_id.lower())
## I'm not sure if the below is still relevant
# parcelmb_exclusion_criteria = 'WHERE  parcelmb.{0} NOT IN (SELECT DISTINCT({0}) FROM excluded_parcels)'.format(points_id.lower())



# The shape file for map features are output 
map_features_outpath = os.path.join(folderPath,'study_region','wgs84_epsg4326','map_features')

if not os.path.exists(map_features_outpath):
  os.makedirs(map_features_outpath)   

      
      
# SQL Settings
conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

areas = {'mb_code_2016':'mb',
         'sa1_maincode':'sa1',
         'ssc_name_2016':'ssc',
         'lga_name_2016':'lga',
         'sos_name_2016':'sos',
         'region':'region'}
         
# create aggregated raw liveability estimates for selected area
for area_code in areas.keys():
  area = areas[area_code]
  area_code2 = area_code
  if area == 'region':
    area_code2 = " 'region'::varchar AS region "
  print("Create aggregate indicator table li_inds_{}... ".format(area)),
  createTable = '''
  DROP TABLE IF EXISTS li_inds_{area} ; 
  CREATE TABLE li_inds_{area} AS
  SELECT {area_code2},
    {indicators}
    FROM parcel_indicators
    {exclusion}
    GROUP BY {area_code}
    ORDER BY {area_code} ASC;
  ALTER TABLE li_inds_{area} ADD PRIMARY KEY ({area_code});
  '''.format(area = area,
             area_code = area_code,
             area_code2 = area_code2,
             indicators = ind_avg,
             exclusion = exclusion_criteria)
  curs.execute(createTable)
  conn.commit()
  print("Done.")
  
  
  ### Note: for now, we are just doing the continuous scale indicators with averages; later I'll implement a second pass to evaluate the threshold cutoffs.
  
  print("Create sd summary table li_sd_{}... ".format(area)),
  createTable = '''
  DROP TABLE IF EXISTS li_sd_{area} ; 
  CREATE TABLE li_sd_{area} AS
  SELECT {area_code2},
    {indicators}     
    FROM parcel_indicators
    {exclusion}
    GROUP BY {area_code}
    ORDER BY {area_code} ASC;
  ALTER TABLE li_sd_{area} ADD PRIMARY KEY ({area_code});
  '''.format(area = area,
             area_code = area_code,
             area_code2 = area_code2,
             indicators = ind_sd,
             exclusion = exclusion_criteria)
  curs.execute(createTable)
  conn.commit()
  print("Done.")
  
  print("Create range summary table li_range_{}... ".format(area)),
  createTable = '''
  DROP TABLE IF EXISTS li_range_{area} ; 
  CREATE TABLE li_range_{area} AS
  SELECT {area_code2},
    {indicators}     
    FROM parcel_indicators
    {exclusion}
    GROUP BY {area_code}
    ORDER BY {area_code} ASC;
  ALTER TABLE li_range_{area} ADD PRIMARY KEY ({area_code});
  '''.format(area = area,
             area_code = area_code,
             area_code2 = area_code2,
             indicators = ind_range,
             exclusion = exclusion_criteria)
  curs.execute(createTable)
  conn.commit()
  print("Done.")
  
  print("Create median summary table li_median_{}... ".format(area)),  
  createTable = '''
  DROP TABLE IF EXISTS li_median_{area} ; 
  CREATE TABLE li_median_{area} AS
  SELECT {area_code2},
    {indicators}     
    FROM parcel_indicators
    {exclusion}
    GROUP BY {area_code}
    ORDER BY {area_code} ASC;
  ALTER TABLE li_median_{area} ADD PRIMARY KEY ({area_code});
  '''.format(area = area,
             area_code = area_code,
             area_code2 = area_code2,
             indicators = ind_median,
             exclusion = exclusion_criteria)
  curs.execute(createTable)
  conn.commit()
  print("Done.")
  
  print("Create IQR summary table li_iqr_{}... ".format(area)),  
  createTable = '''
  DROP TABLE IF EXISTS li_iqr_{area} ; 
  CREATE TABLE li_iqr_{area} AS
  SELECT {area_code2},
    {indicators}     
    FROM parcel_indicators
    {exclusion}
    GROUP BY {area_code}
    ORDER BY {area_code} ASC;
  ALTER TABLE li_iqr_{area} ADD PRIMARY KEY ({area_code});
  '''.format(area = area,
             area_code = area_code,
             area_code2 = area_code2,
             indicators = ind_iqr,
             exclusion = exclusion_criteria)
  curs.execute(createTable)
  conn.commit()
  print("Done.")
  
  map_ind_percentile_area = ''
  if area != 'region':
    print("Create percentile summary table li_percentiles_{}... ".format(area)),      
    createTable = '''
    DROP TABLE IF EXISTS li_percentiles_{area} ; 
    CREATE TABLE li_percentiles_{area} AS
    SELECT {area_code2},
           {indicators}
    FROM li_inds_{area}
    ORDER BY {area_code} ASC;
    ALTER TABLE li_percentiles_{area} ADD PRIMARY KEY ({area_code});
    '''.format(area = area,
               area_code = area_code,
               area_code2 = area_code2,
               indicators = ind_percentile)
    curs.execute(createTable)
    conn.commit()
    print("Done.")
    map_ind_percentile_area = '\n{},'.format(map_ind_percentile)
    
  if area_code != 'mb_code_2016':
    # Create shape files for interactive map visualisation
    area_strings   = {'sa1_maincode' :'''area.sa1_maincode AS sa1   ,\n area.suburb ,\n area.lga ,area.resid_parcels, area.dwellings, area.resid_persons \n''',
                      'ssc_name_2016':''' '-'::varchar AS sa1 ,\n area.suburb AS suburb,\n area.lga AS lga , area.resid_parcels, area.dwellings, area.resid_persons \n''',
                      'lga_name_2016':''' '-'::varchar AS sa1 ,\n '-'::varchar AS suburb ,\n area.lga  AS lga ,area.resid_parcels, area.dwellings, area.resid_persons \n''',
                      'sos_name_2016':''' '-'::varchar AS sa1 ,\n '-'::varchar AS suburb ,\n '-'  AS lga , area.sos_name_2016 AS sos \n''',
                      'region':''' 'region':: varchar AS region '''
                      }    
              
    area_code2 = {'sa1_maincode' :'sa1_maincode',
                  'ssc_name_2016':'suburb',
                  'lga_name_2016':'lga',
                  'sos_name_2016':'sos_name_2016',
                  'region':'region'}    

    area_names2 = {'sa1_maincode' :'sa1_mainco',
                  'ssc_name_2016':'ssc_name_2',
                  'lga_name_2016':'lga_name_2',
                  'sos_name_2016':'sos_name_2016',
                  'region':'region'}                      

    area_tables = {'sa1_maincode' :'area_sa1',
                  'ssc_name_2016':'area_ssc',
                  'lga_name_2016':'area_lga',
                  'sos_name_2016': 'study_region_urban',
                  'region': ''' (SELECT 'region'::varchar AS region, ST_Union(geom) AS geom FROM study_region_urban) '''}   
                  
    area_code_tables = {'sa1_maincode' :'''LEFT JOIN main_sa1_2016_aust_full AS area_code ON area.sa1_maincode = area_code.sa1_mainco''',
                        'ssc_name_2016':'''LEFT JOIN main_ssc_2016_aust      AS area_code ON area.suburb       = area_code.ssc_name_2''',
                        'lga_name_2016':'''LEFT JOIN main_lga_2016_aust      AS area_code ON area.lga          = area_code.lga_name_2''',
                        'sos_name_2016': ''' ''',
                        'region': ''' '''}
                      
    community_code = {'sa1_maincode' :'''area_code.sa1_7digit AS community_code''',
                      'ssc_name_2016':'''CONCAT('SSC',area_code.ssc_code_2::varchar) AS community_code''',
                      'lga_name_2016':'''CONCAT('LGA',area_code.lga_code_2::varchar) AS community_code''',
                      'sos_name_2016':''' '-'::varchar ''',
                      'region':''' '-'::varchar '''}

    boundary_tables = {'sa1_maincode' :'''main_sa1_2016_aust_full b WHERE b.sa1_mainco IN (SELECT sa1_maincode FROM area_sa1) ''',
                       'ssc_name_2016': '''main_ssc_2016_aust b WHERE b.ssc_name_2 IN (SELECT suburb FROM area_ssc) ''',
                       'lga_name_2016': '''main_lga_2016_aust b WHERE b.lga_name_2 IN (SELECT lga FROM area_lga) ''',
                       'sos_name_2016': '''study_region_urban b ''',
                       'region': ''' (SELECT 'region'::varchar AS region, ST_Union(geom) AS geom FROM study_region_urban) b ''',}
                       
    percentile_join_string = ' '              
    if area != 'region':
      percentile_join_string = 'LEFT JOIN li_percentiles_{area} AS perc ON area.{area_code2} = perc.{area_code}'.format(area = area,area_code = area_code, area_code2 = area_code2[area_code])

    # Note -i've excerpted SD and median out of the below table for now; too much for SA1s  
    #        {sd},
    #        {median},
    # LEFT JOIN li_median_{area} AS median ON area.{area_code2} = median.{area_code}
    # LEFT JOIN li_sd_{area} AS sd ON area.{area_code2} = raw.{area_code}
    createTable = '''DROP TABLE IF EXISTS li_map_{area};
    CREATE TABLE li_map_{area} AS
    SELECT {area_strings},
           {raw},
           {percentile}
           {range},
           {iqr},
           {community_code},
           ST_TRANSFORM(area.geom,4326) AS geom              
    FROM {area_table} AS area
    LEFT JOIN li_inds_{area} AS raw ON area.{area_code2} = raw.{area_code}
    {percentile_join}
    LEFT JOIN li_range_{area} AS range ON area.{area_code2} = range.{area_code}
    LEFT JOIN li_iqr_{area} AS iqr ON area.{area_code2} = iqr.{area_code}
    {area_code_table};
    '''.format(area = area,
               area_code = area_code,
               area_table = area_tables[area_code],
               area_strings = area_strings[area_code],
               raw = map_ind_raw,
               sd = map_ind_sd,
               percentile = map_ind_percentile_area,
               range = map_ind_range,
               median = map_ind_median,
               iqr = map_ind_iqr,
               community_code = community_code[area_code],
               area_code2 = area_code2[area_code],
               area_code_table = area_code_tables[area_code],
               percentile_join = percentile_join_string)
    print("Creating map feature at {} level".format(area))
    curs.execute(createTable)
    conn.commit()
    
    createTable = '''
    DROP TABLE IF EXISTS boundaries_{area};
    CREATE TABLE boundaries_{area} AS
    SELECT b.{area_names2} AS {area_code},
            ST_Transform(b.geom,4326) AS geom         
    FROM {boundaries};
    '''.format(area = area,
               area_names2 = area_names2[area_code],
               area_code = area_code,
               boundaries = boundary_tables[area_code])
    print("Creating boundary overlays at {} level".format(area)),
    curs.execute(createTable)
    conn.commit()
    print("Done.")
    
print("Output to geopackage gpkg: {path}/li_map_{db}.gpkg... ".format(path = map_features_outpath, db = db)),
# need to add in a geometry column to ind_description to allow for importing of this table as a layer in geoserver
# If it doesn't already exists
# So, check if it already exists
curs.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ind_description' and column_name='geom';")
null_geom_check = curs.fetchall()
if len(null_geom_check)==0:
  # if geom doesn't exist, created it
  curs.execute("SELECT AddGeometryColumn ('public','ind_description','geom',4326,'POINT',2);")
  conn.commit()
# Output to geopackage using ogr2ogr; note that this command is finnicky and success depends on version of ogr2ogr that you have  
command = 'ogr2ogr -overwrite -f GPKG {path}/li_map_{db}.gpkg PG:"host={host} user={user} dbname={db} password={pwd}" '.format(path = map_features_outpath,
                                                                                                                               host = db_host,
                                                                                                                               user = db_user,
                                                                                                                               pwd = db_pwd,
                                                                                                                               db = db) \
          + ' "li_map_sa1" "li_map_ssc" "li_map_lga" "li_map_sos" "li_map_region" "ind_description" "boundaries_sa1" "boundaries_ssc" "boundaries_lga" "study_region_urban"  "study_region_not_urban" "area_no_dwelling" "area_no_irsd"'
sp.call(command)
print("Done.")


print("Can you please also run the following from the command prompt in the following directory: {folderPath}/study_region//wgs84_epsg4326/".format(folderPath = folderPath))
print('pg_dump -U postgres -h localhost -W  -t "li_map_sa1" -t "li_map_ssc" -t "li_map_lga" -t "li_map_sos" -t "li_map_region" -t "ind_description" -t "boundaries_sa1" -t "boundaries_ssc" -t "boundaries_lga" -t "study_region_urban"  -t "study_region_not_urban" -t "area_no_dwelling" -t "area_no_irsd" {db} > {db}.sql'.format(db = db))

print("Created SA1, suburb and LGA level tables for map web app.")
conn.close()
  
# output to completion log    
script_running_log(script, task, start, locale)
