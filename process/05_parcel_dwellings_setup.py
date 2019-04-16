# Purpose: Clip addresses to study region area (if Dwellings present) and associate w/ hex
# Author:  Carl Higgs
# Date:    2016 11 01


import subprocess as sp     # for executing external commands (e.g. pgsql2shp or ogr2ogr)
import time
import psycopg2
from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *

# simple timer for log file
start = time.time()
script = os.path.basename(sys.argv[0])
task = 'Clip address to study region, dissolve by location counting collapse degree'

# ArcGIS environment settings
arcpy.env.workspace = gdb_path  
# create project specific folder in temp dir for scratch.gdb, if not exists
if not os.path.exists(os.path.join(temp,db)):
    os.makedirs(os.path.join(temp,db))
    
arcpy.env.scratchWorkspace = os.path.join(temp,db)  
arcpy.env.overwriteOutput = True 

scratch_shape  = os.path.join(arcpy.env.scratchGDB,'scratch_shape')

# parcel meshblock dwellings output -- temporary, and long term
scratch_points = os.path.join(arcpy.env.scratchGDB,'scratch_points')
scratch_doppel = os.path.join(arcpy.env.scratchGDB,'scratch_points_D')

# Define make reduced feature layer method
def renameSkinny(is_geo, in_obj, out_obj, keep_fields_list=[''], rename_fields_list=None, where_clause=''):
          ''' Make an ArcGIS Feature Layer or Table View, containing only the fields
              specified in keep_fields_list, using an optional SQL query. Default
              will create a layer/view with NO fields. Method amended (Carl 17 Nov 2016) to include a rename clause - all fields supplied in rename must correspond to names in keep_fields'''
          field_info_str = ''
          input_fields = arcpy.ListFields(in_obj)
          if not keep_fields_list:
              keep_fields_list = []
          i = 0
          for field in input_fields:
              if field.name in keep_fields_list:
                  possibleNewName = (rename_fields_list[i],field.name)[rename_fields_list==None]
                  field_info_str += field.name + ' ' + possibleNewName + ' VISIBLE;'
                  i += 1
              else:
                  field_info_str += field.name + ' ' + field.name + ' HIDDEN;'
          field_info_str.rstrip(';')  # Remove trailing semicolon
          if is_geo:
              arcpy.MakeFeatureLayer_management(in_obj, out_obj, where_clause, field_info=field_info_str)
          else:
              arcpy.MakeTableView_management(in_obj, out_obj, where_clause, field_info=field_info_str)
          return out_obj

# OUTPUT PROCESS
# Note that feature point sources always are a list (often of one source, but formatting as a list
# easily allows for contexts of multiple point data sources; e.g. cities across state boundaries)

if arcpy.Exists(parcel_dwellings):
    arcpy.Delete_management(parcel_dwellings)

for feature in points:  
  print("Processing point source {}...".format(feature))
  arcpy.MakeFeatureLayer_management(os.path.join(folderPath,feature), 'feature') 
  print("  - Select parcels within the inclusion region ({})... ".format(study_region))
  selection = arcpy.SelectLayerByLocation_management(in_layer='feature', 
                                       overlap_type='intersect',
									   select_features=study_region)
									   
  print("Done.\n  - Join (ie. restrict) study inclusion region-defined parcel address points to meshblocks with dwellings... "),
								   
  arcpy.SpatialJoin_analysis(target_features   = selection, 
                           join_features     = 'mb_dwellings', 
                           out_feature_class = scratch_points, 
                           join_operation="JOIN_ONE_TO_ONE", 
                           join_type="KEEP_COMMON", 
                           field_mapping="""{0} "{0}" true true false 15 Text 0 0 ,First,#,{1},{0},-1,-1;{2} "{2}" true true false 11 Text 0 0 ,First,#,{3},{2},-1,-1""".format(points_id,selection,meshblock_id,'mb_dwellings'),
                           match_option="INTERSECT")
		
  print("Done.\n  - Dissolve on XY coordinates, including count of collapsed doppels... "),
  # This can potentially remove a large number of redundant points, where they exist overlapping one another, and so have otherwise identical environmental exposure measurements.  ie. this data is redundant; instead, a field is added with a point count where overlaps were identified. 
  arcpy.AddXY_management(scratch_points)

  arcpy.Dissolve_management(scratch_points, 
                          scratch_doppel, 
						  dissolve_field="POINT_X;POINT_Y", 
						  statistics_fields="{} FIRST;{} FIRST;OBJECTID COUNT".format(points_id,meshblock_id), 
						  multi_part="SINGLE_PART")

  print("Done.\n  - Spatially associate each parcel w/ a hex ... ")
  arcpy.Delete_management(scratch_points)								   

  arcpy.SpatialJoin_analysis(target_features   = scratch_doppel, 
                           join_features     = hex_grid, 
                           out_feature_class = scratch_points, 
                           join_operation="JOIN_ONE_TO_ONE", 
                           join_type="KEEP_ALL", 
                           field_mapping= """{0} "{0}" true true false 15 Text 0 0 ,First,#,{1},{2},-1,-1; {3} "{3}" true true false 11 Text 0 0 ,First,#,{1},{4},-1,-1;{5} "{5}" true true false 4 Long 0 0 ,First,#,{6},{5},-1,-1;{7} "{7}" true true false 4 Long 0 0 ,First,#,{1},{7},-1,-1;{8} "{8}" true true false 8 Double 0 0 ,First,#,{1},{8},-1,-1;{9} "{9}" true true false 8 Double 0 0 ,First,#,{1},{9},-1,-1""".format(points_id,scratch_doppel,'FIRST_'+points_id,meshblock_id,'FIRST_'+meshblock_id,'Input_FID',hex_grid,'COUNT_OBJECTID','POINT_X','POINT_Y'), 
                           match_option="INTERSECT")     

  print("Done.\n  - Associate parcel with overlaying hex (as the join provides input_fid, but not OBJECTID which is used as hex identifier... "),
                           
  arcpy.AlterField_management (hex_grid, "OBJECTID",new_field_alias="HEX_ID")                        
  arcpy.MakeFeatureLayer_management(scratch_points, 'points')
  arcpy.MakeFeatureLayer_management(hex_grid, 'hex_grid')
                           
  arcpy.AddJoin_management(in_layer_or_view = 'points', 
                         in_field         = 'Input_FID',
                         join_table       = 'hex_grid',
                         join_field       = 'Input_FID',
                         join_type        = "KEEP_ALL")     

  print("Done.\n  - Rename ID fields to original identifiers and export/append meshblock parcel dwellings feature to geodatabase... ")

  oldfields = ['scratch_points.OBJECTID', 'scratch_points.Shape',  'scratch_points.{}'.format(points_id), 'scratch_points.{}'.format(meshblock_id), 'scratch_points.COUNT_OBJECTID', 'scratch_points.POINT_X', 'scratch_points.POINT_Y', '{}.OBJECTID'.format(hex_grid)] 
  newfields = ['OBJECTID','Shape','{}'.format(points_id),'{}'.format(meshblock_id),'COUNT_OBJECTID','POINT_X','POINT_Y','HEX_ID']				 
  renameSkinny(is_geo = True, 
             in_obj = 'points', 
             out_obj = 'tempFull', 
             keep_fields_list = oldfields, 
             rename_fields_list = newfields,
             where_clause = '')
  print("Done.")	 
  if not arcpy.Exists(parcel_dwellings):
    arcpy.CopyFeatures_management('tempFull', parcel_dwellings)    
  else:
    arcpy.Append_management('tempFull', parcel_dwellings,schema_type = "NO_TEST")   


# gdb to pgsql
#  Copy the parcel_dwellings from gdb to postgis, correcting the projection in process
command = 'ogr2ogr -overwrite -progress -f "PostgreSQL" ' \
        + 'PG:"host={host} port=5432 dbname={db} '.format(host = db_host,db = db) \
        + 'user={user} password = {pwd} " '.format(user = db_user,pwd = db_pwd) \
        + '{gdb} "{feature}" '.format(gdb = gdb_path,feature = parcel_dwellings) \
        + '-a_srs "EPSG:{from_srs} " '.format(from_srs = points_srid) \
        + '-t_srs "EPSG:{to_srs} " '.format(to_srs = srid) \
        + '-lco geometry_name="geom" '
sp.call(command, shell=True)

# connect to the PostgreSQL server and ensure privileges are granted for all public tables
conn = psycopg2.connect(dbname=db, user=db_user, password=db_pwd)
curs = conn.cursor()
curs.execute(grant_query)
conn.commit()
conn.close()

# pgsql to gdb
# this is a clumsy workaround: I struggled to get the source GNAF data in the correct format at pre-processing stage
# QGIS ntv2 plugin converted GNAF data from a GDA94 transformation to GDA2020 (ArcGIS read both as 'custom')
# I found projecting with manual specification from EPSG 7844 to 7845 formally fixed the definition.
# Copied back to ArcGIS, the spatial reference is now recognised correctly as GDA2020 GA LLC
arcpy.env.workspace = db_sde_path
arcpy.CopyFeatures_management('public.parcel_dwellings', os.path.join(gdb_path,'parcel_dwellings'))

# output to completion log					
script_running_log(script, task, start, locale)
