Validation process:
1. Data:
   Download OSM gpkg file from : https://cloudstor.aarnet.edu.au/plus/s/j1UababLcIw8vbM
   Download official dataset 
   
2. Change these names into the correct filename and POIs of interest in POIs_validation.py
   official_filename = "Restaurant_and_Food_Related.shp"
   OSM_filename = "belfast_gb_2019_1600m_buffer.gpkg"
   POIs_name = "fresh_food_market"

3. Run the POIs_validation.py file

Findings:

1. Belfast:
     
     number of OSM points:  124
     
     number of Official points:  1479
     
     number of intersection items:  26
     
     Percentage:  20.967741935483872
    
    {'init': 'epsg:29903'}

    
    100m buffering of Official points:
       
       intersection:  95
       
       percent of OSM points 76.61290322580645

     
     100m buffering of OSM points:
       
       intersection:  392
       
       percent of Official Point:  26.504394861392832

     Nearest distance histogram: belfast_nearest_distance.png

2. Sao Paulo

3. Olomouc

