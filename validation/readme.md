# Validation process:

### 1. Data:
   
   Download OSM gpkg file from : https://cloudstor.aarnet.edu.au/plus/s/j1UababLcIw8vbM
   
   Download official dataset 
   
### 2. Change these names into the correct filenames and POIs of interest in POIs_validation.py
   
   official_filename = "Restaurant_and_Food_Related.shp"
   
   OSM_filename = "belfast_gb_2019_1600m_buffer.gpkg"
   
   POIs_name = "fresh_food_market"

### 3. Run the POIs_validation.py file

# Findings:

### 1. Belfast:
     
     number of OSM points:  124 - Fresh food and market POINTS
     
     number of Official points:  1479 - Food and Restaurant Related POLYGONS
     
     number of intersection items:  26
     
     Percentage:  20.967741935483872
    
    {'init': 'epsg:29903'} vs 29902 

    
    100m buffering of Official points:
       
       intersection:  95
       
       percent of OSM points 76.61290322580645

     
     100m buffering of OSM points:
       
       intersection:  392
       
       percent of Official Point:  26.504394861392832

     Nearest distance histogram: belfast_nearest_distance.png
     
     Some noted problems: 
       
       Mismatched definitions (restaurants included or not?)
       Official points as POLYGONS (of city block size) - confirming with collaborators
       Unmatched crs between what's in the official dataset and the one used for OSM

### 2. Sao Paulo

     number of OSM points:  2132 - Fresh food and market POINTS
     
     number of Official points:  939 - street markets, municipal markets, municipal restaurants, grocery bigbags POINTS
     
     number of intersection items:  0
     
     Percentage:  0.0
    
    {'init': 'epsg:31983'} vs 32723

    
    100m buffering of Official points:
       
       intersection:  487
       
       percent of OSM points: 22.842401500938088 

     
     100m buffering of OSM points:
       
       intersection:  205
       
       percent of Official Point: 21.831735889243877

     Nearest distance histogram: sao_paulo_nearest_distance.png
     Mean nearest distance: 1416.304145492677
     Median nearest distance: 248.37187706365415
     
     Some noted problems:
         
        Street markets: - periodic markets, linear features represented in points
        Unmatched crs between what's in the official dataset and the one used for OSM
        

### 3. Olomouc

     number of OSM points:  67
     
     number of Official points:  63
     
     number of intersection items:  0
     
     Percentage:  0.0
    
    {'init': 'epsg: 5513'} vs 32633

    
    100m buffering of Official points:
       
       intersection:  0
       
       percent of OSM points : 0

     
     100m buffering of OSM points:
       
       intersection:  0
       
       percent of Official Point:  0

     Nearest distance histogram: olomouc_nearest_distance.png
