import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import great_circle

official_filename = "Restaurant_and_Food_Related.shp"
OSM_filename = "belfast_gb_2019_1600m_buffer.gpkg"
POIs_name = "fresh_food_market"

gdf = gpd.read_file(OSM_filename, layer='destinations')
gdf_osm = gdf[gdf['dest_name']==POIs_name]

gdf_official = gpd.GeoDataFrame.from_file(official_filename)
print("number of OSM points: " ,len(gdf_osm))
print("number of Official points: ", len(gdf_official))

#Project gdf_osm to the crs of the official layer
gdf_osm = gdf_osm.to_crs(gdf_official.crs)
print(gdf_osm.crs)
#ax = gdf_osm.plot()

#Calculate number of gdf_osm intersect with gdf_official
mask1 = gdf_osm['geometry'].intersects(gdf_official['geometry'].unary_union)

print("number of intersection items: ",len(gdf_osm[mask1]))
print("Percentage: ",len(gdf_osm[mask1])*100/len(gdf_osm) )


#Draw 100m buffer around OSM points; draw 100m buffer around official points
OSM_buffer = gdf_osm
OSM_buffer['geometry'] = OSM_buffer.geometry.buffer(100)
OP_buffer =gdf_official
OP_buffer['geometry'] = OP_buffer.geometry.buffer(100)

#Calculate percent of OSM points within Official points 100m buffer
mask = gdf_osm['geometry'].intersects(OP_buffer['geometry'].unary_union)
print("intersection: ",len(gdf_osm[mask]))
print("percent of OSM points", str(len(gdf_osm[mask])*100/len(gdf_osm)))

#Calculate percent of Official Point within OSM points 100m buffer
mask = gdf_official['geometry'].intersects(OSM_buffer['geometry'].unary_union)
print("intersection: ",len(gdf_official[mask]))
print("percent of Official Point: ", str(len(gdf_official[mask])*100/len(gdf_official)))

#Calculate distance to all Official polygons and pick the min
def min_distance(gdf_osm, gdf_official):
    nearest_dists = []
    for item in gdf_osm.geometry:
        nearest_dist = gdf_official.distance(item).min()
        nearest_dists.append(nearest_dist)
    gdf_osm['nearest_distance'] = nearest_dists
    print(gdf_osm['nearest_distance'])


min_distance(gdf_osm,gdf_official)
#Graphing the histogram of distance from gdf_osm to nearest Official points
ax = gdf_osm['nearest_distance'].hist()
plt.show()

mean_dist = gdf_osm['nearest_distance'].mean()
print("mean nearest distance: ",mean_dist)

median_dist = gdf_osm['nearest_distance'].median()
print("median nearest distance: ", median_dist)



