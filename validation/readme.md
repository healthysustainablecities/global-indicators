# Points of Interest (POIs) Validation process:

### 1. Data:
   
   Download OSM gpkg file and official datasets from google drive for the city of interest
   
### 2. Change these names into the correct filenames and POIs of interest in POIs_validation.py
   
   official_filename = "Restaurant_and_Food_Related.shp"
   
   OSM_filename = "belfast_gb_2019_1600m_buffer.gpkg"
   
   POIs_name = "fresh_food_market"

### 3. Run the POIs_validation.py file

### 4. Preliminary findings for Olomouc, Belfast, and Sao Paulo fresh food POIs can be found in poi_validation_findings.md


# Street Network Validation process:

### 1. Data:
### 2. Change these names into the correct filenames 
   
   graphml_path = "belfast_gb_2019_10000m_all_osm_20190902.graphml"
   
   osm_buffer_file="belfast_gb_2019_1600m_buffer.gpkg"
   
   gdf_official = gpd.GeoDataFrame.from_file("Belfast_City_Council_Area_Street_Network.shp")

### 3. Run the edge_validation.py file

### 4. Preliminary findings for Olomouc, Belfast, and Hong Kong street networks can be found in edge_validation_findings.md
