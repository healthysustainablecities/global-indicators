import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import great_circle

official_filename = "Restaurant_and_Food_Related.shp"
OSM_filename = "belfast_gb_2019_1600m_buffer.gpkg"
POIs_name = "fresh_food_market"

gdf = gpd.read_file(OSM_filename, layer='destinations')
OSM_points = gdf[gdf['dest_name']==POIs_name]

OPoints = gpd.GeoDataFrame.from_file(official_filename)
print("number of OSM points: " ,len(OSM_points))
print("number of Official points: ", len(OPoints))

#Calculate number of OSM_points intersect with OPoints
mask1 = OSM_points['geometry'].intersects(OPoints['geometry'].unary_union)

print("number of intersection items: ",len(OSM_points[mask1]))
print("Percentage: ",len(OSM_points[mask1])*100/len(OSM_points) )
# #print(len(OSM_points[~mask1]))

# mask2 = OPoints['geometry'].intersects(OSM_points['geometry'].unary_union)
# print(len(OPoints[mask2]))


#Project OSM_points to the crs of the official layer
OSM_points = OSM_points.to_crs(OPoints.crs)
print(OSM_points.crs)
#ax = OSM_points.plot()

#Draw 100m buffer around OSM points; draw 100m buffer around official points
OSM_buffer = OSM_points
OSM_buffer['geometry'] = OSM_buffer.geometry.buffer(100)
OP_buffer = OPoints
OP_buffer['geometry'] = OP_buffer.geometry.buffer(100)

#Calculate percent of OSM points within Official points 100m buffer
mask = OSM_points['geometry'].intersects(OP_buffer['geometry'].unary_union)
print("intersection: ",len(OSM_points[mask]))
print("percent of OSM points", str(len(OSM_points[mask])*100/len(OSM_points)))

#Calculate percent of Official Point within OSM points 100m buffer
mask = OPoints['geometry'].intersects(OSM_buffer['geometry'].unary_union)
print("intersection: ",len(OPoints[mask]))
print("percent of Official Point: ", str(len(OPoints[mask])*100/len(OPoints)))

#Calculate distance to all Official polygons and pick the min
def min_distance(OSM_points, OPoints):
    nearest_dists = []
    for item in OSM_points.geometry:
        nearest_dist = OPoints.distance(item).min()
        nearest_dists.append(nearest_dist)
    OSM_points['nearest_distance'] = nearest_dists
    print(OSM_points['nearest_distance'])


min_distance(OSM_points,OPoints)
#Graphing the histogram of distance from OSM_points to nearest Official points
ax = OSM_points['nearest_distance'].hist()
plt.show()

mean_dist = OSM_points['nearest_distance'].mean()
print("mean nearest distance: ",mean_dist)

median_dist = OSM_points['nearest_distance'].median()
print("median nearest distance: ", median_dist)



