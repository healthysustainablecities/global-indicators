# Script:  17_parcel_indicators.py
# Purpose: Create parcel indicators for national liveability project
# Author:  Carl Higgs 
# Date:    20180717

import time
import psycopg2 
from sqlalchemy import create_engine

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'create destination indicator tables'

# Connect to postgresql database     
conn = psycopg2.connect(database=db, user=db_user, password=db_pwd)
curs = conn.cursor()

engine = create_engine("postgresql://{user}:{pwd}@{host}/{db}".format(user = db_user,
                                                                 pwd  = db_pwd,
                                                                 host = db_host,
                                                                 db   = db))
# Indicator configuration sheet is 'df_inds', read in from config file in the config script

# Restrict to indicators associated with study region (except distance to closest dest indicators)
ind_matrix = df_inds[df_inds['locale'].str.contains('|'.join([locale,'\*']))]

# Get a list of destinations processed within this region for distance to closest
# sql = '''SELECT DISTINCT(dest_name) dest_name FROM od_closest ORDER BY dest_name;'''
sql = '''SELECT dest_name FROM dest_type ORDER BY dest_name;'''
curs.execute(sql)
categories = [x[0] for x in curs.fetchall()]

# get the set of distance to closest regions which match for this region
destinations = df_inds[df_inds['ind'].str.contains('destinations')]
current_categories = [x for x in categories if 'distance_m_{}'.format(x) in destinations.ind_plain.str.encode('utf8').tolist()]
ind_matrix = ind_matrix.append(destinations[destinations['ind_plain'].str.replace('distance_m_','').str.contains('|'.join(current_categories))])
ind_matrix['order'] = ind_matrix.index
ind_soft = ind_matrix.loc[ind_matrix.tags=='_{threshold}',:].copy()
ind_hard = ind_matrix.loc[ind_matrix.tags=='_{threshold}',:].copy()
ind_soft.replace(to_replace='{threshold}', value='soft', inplace=True,regex=True)
ind_hard.replace(to_replace='{threshold}', value='hard', inplace=True,regex=True)

ind_matrix = pandas.concat([ind_matrix,ind_soft,ind_hard], ignore_index=True).sort_values('ind')
ind_matrix.drop(ind_matrix[ind_matrix.tags == '_{threshold}'].index, inplace=True)
# Restrict to indicators with a defined query
ind_matrix = ind_matrix[pandas.notnull(ind_matrix['Query'])]
ind_matrix.drop(ind_matrix[ind_matrix['updated?'] == 'n'].index, inplace=True)

# Make concatenated indicator and tag name (e.g. 'walk_14' + 'hard')
# Tags could be useful later as can allow to search by name for e.g. threshold type,
# or other keywords (policy, binary, obsolete, planned --- i don't know, whatever)
# These tags are tacked on the end of the ind name seperated with underscores
ind_matrix['indicators'] = ind_matrix['ind'] + ind_matrix['tags'].fillna('')
# ind_matrix['sort_cat'] = pandas.Categorical(ind_matrix['ind'], categories=mylist, ordered=True)
# ind_matrix.sort_values('sort_cat', inplace=True)
# Compile list of indicators
ind_matrix.sort_values('order', inplace=True)
ind_list = ind_matrix['indicators'].tolist()

# Compile string of queries, and of unique sources to plug in SQL table creation query
ind_queries = '\n'.join(ind_matrix['Query'])
ind_sources = '\n'.join(ind_matrix['Source'].unique())

# Generate strings for checking nulls: by column (indicator), and by row
null_query_summary = ',\n'.join("SUM(" + ind_matrix['indicators'] + " IS NULL::int) AS " + ind_matrix['indicators'])
null_query_combined = '+\n'.join("(" + ind_matrix['indicators'] + " IS NULL::int)")

                                                                                
# Define parcel level indicator table creation query
# Note that we modify inds slightly later when aggregated to reflect cutoffs etc
create_parcel_indicators = '''
DROP TABLE IF EXISTS parcel_indicators;
CREATE TABLE parcel_indicators AS
SELECT
p.{id}                   ,
p.count_objectid         ,
p.point_x                ,
p.point_y                ,
p.hex_id                 ,
abs.mb_code_2016         ,
abs.mb_category_name_2016,
abs.dwelling             ,
abs.person               ,
abs.sa1_maincode         ,
abs.sa2_name_2016        ,
abs.sa3_name_2016        ,
abs.sa4_name_2016        ,
abs.gccsa_name           ,
abs.state_name           ,
non_abs.ssc_code_2016    ,
non_abs.ssc_name_2016    ,
non_abs.lga_code_2016    ,
non_abs.lga_name_2016    ,
sos.sos_name_2016        ,
{indicators}             
p.geom                   
FROM
parcel_dwellings p                                                                                 
LEFT JOIN abs_linkage abs ON p.mb_code_20 = abs.mb_code_2016
LEFT JOIN non_abs_linkage non_abs ON p.{id} = non_abs.{id}
LEFT JOIN parcel_sos sos ON p.{id} = sos.{id}
{sources}
'''.format(id = points_id, indicators = ind_queries, sources = ind_sources)

# Define null query tables
null_query_summary_table = '''
DROP TABLE IF EXISTS parcel_inds_null_summary; 
CREATE TABLE parcel_inds_null_summary AS
SELECT {null_query_summary} 
FROM parcel_indicators;
'''.format(null_query_summary = null_query_summary)

null_query_combined_table = '''
DROP TABLE IF EXISTS parcel_inds_null_tally; 
CREATE TABLE parcel_inds_null_tally AS
SELECT {id},
       {null_query_combined} AS null_tally,
       {total_inds} AS total_inds
FROM parcel_indicators;
'''.format(id = points_id,
           null_query_combined = null_query_combined,
           total_inds = len(ind_list))

 
print("Creating compiled set of parcel level indicators...")
print("SQL query:")
print(create_parcel_indicators)
curs.execute(create_parcel_indicators)
conn.commit()
print("Done.")

print("Creating summary of nulls per indicator... ")
print("SQL query:")
print(null_query_summary_table)
curs.execute(null_query_summary_table)
conn.commit()
print("Done.")

print("Creating row-wise tally of nulls for each parcel...")
print("SQL query:")
print(null_query_combined_table)
curs.execute(null_query_combined_table)
conn.commit()
print("Done.\n")

# Generate some summary information to print to screen
df = pandas.read_sql_query('SELECT * FROM "parcel_inds_null_summary";',con=engine)
df = df.transpose()
df.columns = ['Null count']
print("Summary of nulls by {} variables for {} of {} in state of {}:".format(len(ind_list),region,locale,state))
print(df)

df2 = pandas.read_sql_query('SELECT * FROM "parcel_inds_null_tally";',con=engine)
print("Summary of row-wise null values across {} variables:".format(len(ind_list)))
print(df2['null_tally'].describe().round(2))

df.to_sql(name='parcel_ind_null_summary_t',con=engine,if_exists='replace')
df2['null_tally'].describe().round(2).to_sql(name='parcel_inds_null_tally_summary',con=engine,if_exists='replace')

# Drop index for ind_description table if it exists; 
# this causes an error when (re-)creating the ind_description table if index exists
curs.execute('DROP INDEX IF EXISTS ix_ind_description_index;')
conn.commit()
ind_matrix.to_sql(name='ind_description',con=engine,if_exists='replace')

print("\n Nulls by indicator and Section of state")
for ind in ind_list:
  print("\n{}".format(ind))
  null_ind = pandas.read_sql_query("SELECT sos_name_2016, COUNT(*) null_count FROM parcel_indicators p WHERE {ind} IS NULL GROUP BY sos_name_2016;".format(ind = ind),con=engine)
  if len(null_ind) != 0:
    print(null_ind)
  if len(null_ind) == 0:
    print("No null values")


print("\nPostgresql summary tables containing the above were created:")
print("To view a description of all indicators for your region: SELECT * FROM ind_description;")
print("To view a summary of by variable name: SELECT * FROM parcel_ind_null_summary_t;")
print("To view a summary of row-wise null values: SELECT * FROM parcel_inds_null_tally_summary;")
print("To view a summary of null values for a particular indicator stratified by section of state:")
print(" SELECT sos_name_2016, COUNT(*) indicator_null_count FROM parcel_indicators p LEFT JOIN parcel_sos sos ON p.{id} = sos.{id} WHERE indicator IS NULL GROUP BY sos_name_2016;".format(id = points_id))

# output to completion log    
script_running_log(script, task, start, locale)
conn.close()
