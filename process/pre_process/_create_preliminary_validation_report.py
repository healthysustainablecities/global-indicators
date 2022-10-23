"""

Create preliminary validation report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Script:  
    _create_preliminary_validation_report.py
Purpose: 
    Create indicators based on linkage with boundary data from specification in datasets section of configuration file

"""

import time
import os
import pandas as pd
import geopandas as gpd
import subprocess as sp
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colors
import contextily as ctx
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.font_manager as fm
from matplotlib import patheffects
from matplotlib import transforms
import psycopg2
from sqlalchemy import create_engine,inspect
from shapely.geometry import box

fontprops = fm.FontProperties(size=12)
dpi = 300                    
attribution_size = 8
# Set up project and region parameters for GHSCIC analyses
from _project_setup import *

def set_scale(total_bounds):
    half_width = (total_bounds[2] - total_bounds[1])/2.0
    scale_values = {
                    'large': {'distance': 25000, 'display': '25 km'},
                    'default': {'distance': 20000, 'display': '20 km'},
                    'small': {'distance': 10000, 'display': '10 km'},
                    'tiny': {'distance': 5000, 'display': '5 km'}
                    }
    if half_width < 10000:
        return(scale_values['tiny'])
    elif  half_width < 20000:
        return(scale_values['small'])
    elif  half_width < 25000:
        return(scale_values['default'])
    else:
        return(scale_values['large'])


def buffered_box(total_bounds,distance):
    mod = [-1,-1,1,1]
    buffer_distance = [x*distance for x in mod]
    new_bounds = [total_bounds[x] + buffer_distance[x] for x in range(0,4)]
    return(new_bounds)

def get_sphinx_conf_header():
    import time
    
    current_year = time.strftime("%Y")
    header=(
            "# Configuration file for the Sphinx documentation builder.\r\n"
            "# -- Project information -----------------------------------------------------\r\n"
           f"\r\nproject = 'Global Liveability Indicators, preliminary report: {full_locale}'"
           f"\r\ncopyright = '{current_year}, {authors}'"
           f"\r\nauthor = '{authors}'"
            "\r\n\r\n# The full version, including alpha/beta/rc tags"
           f"\r\nrelease = '{version}'\r\n"
            )
    return(header)

def line_prepender(infile, outfile, line):
    with open(infile, 'r') as i:
        lines = ''.join([line]+i.readlines())
        with open(outfile, "w") as o:
            print(lines, file=o)

destination_tags = {
'fresh_food_market':'''
The following key-value tags were used to identify supermarkets, fresh food and market destinations using OpenStreetMap:

================ ==============
     Key              Value
================ ==============
shop             supermarket
supermarket      
amenity          supermarket
building         supermarket
shop             grocery
shop             bakery
shop             pastry
name             Tortillería
shop             butcher
shop             seafood
shop             fishmonger
shop             greengrocer
shop             fruit
shop             fruits
shop             vegetables
shop             deli
shop             cheese
amenity          marketplace
amenity          market
amenity          market_place
amenity          public_market
shop             marketplace
shop             market
================ ==============
''',
'convenience':'''
The following key-value tags were used to identify convenience stores using OpenStreetMap:

================ ==============
     Key              Value
================ ==============
shop             convenience
amenity          fuel
shop             kiosk
shop             newsagent
shop             newsagency
amenity          newsagency
================ ==============
''',
'pt_any':'''
It is planned to use General Transit Feed Specification (GTFS) data where available for public transport analysis.  However, GTFS data is not available for all cities, so additional analysis will be undertaken for all cities using OSM public transport data.

The following key-value tags were used to identify public transport stops using OpenStreetMap:

================ ==============
     Key              Value
================ ==============
public_transport platform
public_transport stop_position
highway          bus_stop
highway          platform
railway          platform
public_transport station
amenity          ferry_terminal
railway          tram_stop
railway          stop
================ ==============
''',
'pos':'''
The identification of public open space using OpenStreetMap is a distinct question to other kinds of destinations which are usually localised as discrete 'points': public open space are areas (or polygons), and often may be quite large.    Parks, nature reserves, plazas and squares could all be considered areas of open space: open areas where people may gather for leisure.

Going into the full detail of the methods which we use to derive areas of open space using OpenStreetMap is beyond the scope of this report; however, the basic workflow is as follows:

Identify open space
###################

A series of logical queries are used to identify areas of open space; meeting any one of these is grounds for inclusion of consideration as a potential area of open space (noting that this may yet include private areas, which are not public open space). For example, any polygons with keys of 'leisure','natural','sport','beach','river','water,'waterway','wetland' with recorded values are recorded, in addition to specific combinations such as 'place=square'.   Other recorded combinations include 

* landuse, with values of: common, conservation, forest, garden, leisure, park, pitch, recreation_ground, sport, trees, village_green, winter_sports, wood, dog_park, nature_reserve, off_leash , sports_centre, 

* os_boundary, with values of: protected_area, national_park, nature_reserve, forest, water_protection_area, state_forest, state_park, regional_park, park, county_park

Exclusion criteria
##################

Any portions of the areas of the identified as being potential areas of open space which overlap areas identified as being 'excluded' are omitted from the open space dataset.

We create a polygon layer of areas which are categorically not to be considered as open space.  For example, if there is an area which has been coded to suggest it could be a natural area that might potentially be an open space (e.g. perhaps 'boundary=nature_reserve'), but actually is entirely within an area with a military or industrial land use, or is tagged to indicate that access is not public (e.g. for employees or staff only, private, or otherwise inaccessible): this is not an area of public open space and will be excluded.

Evaluating access
#################

Once areas of public open space have been identified, proxy locations for entry points are created at regular intervals (every 20 metres) on the sections of the boundaries of those areas of public open space which are within 30 metres of the road network.
'''
}

def main():
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'Create preliminary validation report'
    print(task)
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
    
    required_file = '../collaborator_report/_static/cities_data.tex'
    if not os.path.exists(required_file):
        sys.exit(f'''The file {required_file} doesn't appear to exist.  This implies that all required scripts for the cities defined in the region_configuration file have not been successfully run, or at least the script '_city_summary_tex_table.py' which generates required tables for this script probably hasn't.  Please ensure that the table 'cities_data.tex' has been generated before proceeding.''')
    
    # Create maps (Web Mercator epsg 3857, for basemap purposes)
    # Plot study region (after projecting to web mercator)
    # basemap = 'https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png'
    # basemap_attribution = "Map tiles by Carto, under CC BY 3.0. Data by OpenStreetMap, under ODbL."
    basemap = [ctx.providers.Esri.WorldImagery,ctx.providers.Esri.WorldImagery.attribution]
    city = gpd.GeoDataFrame.from_postgis(f'SELECT * FROM {study_region}', engine, geom_col='geom' ).to_crs(epsg=3857)
    urban = gpd.GeoDataFrame.from_postgis('SELECT * FROM urban_region', engine, geom_col='geom' ).to_crs(epsg=3857)
    urban_study_region = gpd.GeoDataFrame.from_postgis(f'SELECT * FROM urban_study_region', engine, geom_col='geom' ).to_crs(epsg=3857)
    bounding_box = box(*buffered_box(urban_study_region.total_bounds,500))
    urban_buffer = gpd.GeoDataFrame(gpd.GeoSeries(bounding_box), columns=['geometry'],crs=3857)
    clip_box = transforms.Bbox.from_extents(*urban_buffer.total_bounds)
    xmin, ymin, xmax, ymax = urban_study_region.total_bounds
    scaling = set_scale(urban_study_region.total_bounds)
    if not os.path.exists(f'../data/study_region/{study_region}/{study_region}_m_urban_boundary.png'):
        f, ax = plt.subplots(figsize=(10, 10), edgecolor='k')
        urban.plot(ax=ax,color='yellow',label='Urban centre (GHS)',alpha=0.4)
        urban_study_region.plot(ax=ax, facecolor="none",hatch='///',label='Urban study region',alpha=0.5) 
        city.plot(ax=ax,label='Administrative boundary',facecolor="none",  edgecolor='white', lw=2)
        ax.set_title(f'Study region boundary for {full_locale}', fontsize=12)
        plt.axis('equal')
        # map_attribution = 'Administrative boundary (attribution to be added) | Urban centres (Global Human Settlements Urban Centre Database UCDB R2019A) | {basemap_attribution}'.format(basemap_attribution = basemap[1])
        map_attribution = basemap[1]
        ctx.add_basemap(ax,source=basemap[0],attribution = '')
        ax.text(
            0.005,
            0.005,
            map_attribution,
            transform=ax.transAxes,
            size=attribution_size,
            path_effects=[patheffects.withStroke(linewidth=2, foreground="w")],
            wrap=False
        )
        scalebar = AnchoredSizeBar(ax.transData,
                                   scaling['distance'], scaling['display'], 'lower right', 
                                   pad=2,
                                   color='white',
                                   frameon=False,
                                   size_vertical=1,
                                   fontproperties=fontprops)

        ax.add_artist(scalebar)
        ax.set_axis_off()
        plt.tight_layout()
        ax.figure.savefig(f'../data/study_region/{study_region}/{study_region}_m_urban_boundary.png', bbox_inches = 'tight', pad_inches = .2, dpi=dpi)   
        ax.clear()
    
    # Other plots
    basemap = [ctx.providers.Stamen.TonerLite,ctx.providers.Stamen.TonerHybrid.attribution]
    
    if not os.path.exists(f'../data/study_region/{study_region}/{study_region}_m_pos.png'):
        # Plot public open space
        sql = '''
        SELECT geom_public geom
          FROM open_space_areas
         WHERE geom_public IS NOT NULL 
           AND ST_IsValid(geom_public) 
           AND NOT ST_IsEmpty(geom_public)
           AND ST_GeometryType(geom_public) IN ('ST_Polygon','ST_MultiPolygon')
           AND aos_ha_public > 0.000001;
         '''
        pos = gpd.GeoDataFrame.from_postgis(sql, engine, geom_col='geom' ).to_crs(epsg=3857)
        urban_pos = gpd.overlay(pos, urban_buffer, how='intersection')
        f, ax = plt.subplots(figsize=(10, 10), edgecolor='k')
        urban_study_region.plot(ax=ax,facecolor="none",label='Urban study region',alpha=1,  edgecolor='black', lw=2)
        urban_pos.plot(ax=ax,color='green',label='Public Open Space (POS)',alpha=0.7)
        plt.axis([xmin,xmax,ymin,ymax])
        ax.set_title(f'Public open space of urban {full_locale}', fontsize=12)
        plt.axis('equal')
        map_attribution = 'Open space data: OpenStreetMap contributors, 2019 | {basemap_attribution}'.format(basemap_attribution = basemap[1])
        ctx.add_basemap(ax,source=basemap[0],attribution = '',alpha=0.5)
        ax.text(
            0.005,
            0.005,
            map_attribution,
            transform=ax.transAxes,
            size=attribution_size,
            path_effects=[patheffects.withStroke(linewidth=2, foreground="w")],
            wrap=False
        )
        scalebar = AnchoredSizeBar(ax.transData,
                                   scaling['distance'], scaling['display'], 'lower right', 
                                   pad=1.2,
                                   color='black',
                                   frameon=False,
                                   size_vertical=1,
                                   fontproperties=fontprops)
        ax.add_artist(scalebar)
        ax.set_axis_off()
        plt.tight_layout()
        ax.figure.savefig(f'../data/study_region/{study_region}/{study_region}_m_pos.png', bbox_inches = 'tight', pad_inches = .2, dpi=dpi)   
        ax.clear() 
    
    # hexplot
    pop_grid = gpd.GeoDataFrame.from_postgis(f'SELECT * FROM  {population_grid}', engine, geom_col='geom' ).to_crs(epsg=3857)
    urban_grid = gpd.overlay(pop_grid, urban_buffer, how='intersection')
    if not os.path.exists(f'../data/study_region/{study_region}/{study_region}_m_popdens.png'):
        f, ax = plt.subplots(figsize=(10, 10), edgecolor='k')
        urban_grid.dropna(subset=['pop_per_sqkm']).plot(ax=ax,column='pop_per_sqkm', cmap='Blues',label='Population density',alpha=0.4)
        urban_study_region.plot(ax=ax,facecolor="none",label='Urban study region',alpha=1,  edgecolor='black', lw=2)
        plt.axis([xmin,xmax,ymin,ymax])
        ax.set_title(f'Population density estimate per km² in urban {full_locale}', fontsize=12)
        plt.axis('equal')
        map_attribution = 'Population data (2015): GHS, 2019 | {basemap_attribution}'.format(basemap_attribution = basemap[1])
        ctx.add_basemap(ax,source=basemap[0],attribution = '',alpha=0.5)
        ax.text(
            0.005,
            0.005,
            map_attribution,
            transform=ax.transAxes,
            size=attribution_size,
            path_effects=[patheffects.withStroke(linewidth=2, foreground="w")],
            wrap=False
        )
        scalebar = AnchoredSizeBar(ax.transData,
                                   scaling['distance'], scaling['display'], 'lower right', 
                                   pad=1.2,
                                   color='black',
                                   frameon=False,
                                   size_vertical=1,
                                   fontproperties=fontprops)
        ax.add_artist(scalebar)
        ax.set_axis_off()
        # Create colorbar as a legend
        vmin,vmax = urban_grid['pop_per_sqkm'].min(),urban_grid['pop_per_sqkm'].max()
        # sm = plt.cm.ScalarMappable(cmap=’Blues’, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="5%", pad=0.05)
        sm = plt.cm.ScalarMappable(cmap='Blues',norm=plt.Normalize(vmin=vmin, vmax=vmax))
        # empty array for the data range
        sm._A = []
        # add the colorbar to the figure
        cbar = ax.figure.colorbar(sm,cax=cax,fraction=0.046, pad=0.04)
        plt.tight_layout()
        ax.figure.savefig(f'../data/study_region/{study_region}/{study_region}_m_popdens.png', bbox_inches = 'tight', pad_inches = .2, dpi=dpi)   
        ax.clear() 
    
    ## manually defining the destination list to ensure desired order
    destinations = [
                    ('fresh_food_market', 'Fresh Food / Market'),
                    ('convenience', 'Convenience'), 
                    ('pt_any', 'Public transport stop (any)')
                    ]
    for dest in destinations:
        dest_name = dest[0]
        if not os.path.exists(f'../data/study_region/{study_region}/{study_region}_m_{dest_name}.png'):
            dest_name_full = dest[1]
            # print(dest[1])
            f, ax = plt.subplots(figsize=(10, 10), edgecolor='k')
            urban_grid.dropna(subset=[f'count_{dest_name}']).plot(ax=ax,column=f'count_{dest_name}', cmap='viridis_r',label='{dest_name_full} count',alpha=0.7)
            urban_study_region.plot(ax=ax,facecolor="none",label='Urban study region',alpha=1,  edgecolor='black', lw=2)
            plt.axis([xmin,xmax,ymin,ymax])
            ax.set_title(f'{dest_name_full} count in urban {full_locale}', fontsize=12)
            plt.axis('equal')
            map_attribution = 'Population data (2015): GHS, 2019 | {basemap_attribution}'.format(basemap_attribution = basemap[1])
            ctx.add_basemap(ax,source=basemap[0],attribution = '',alpha=0.5)
            ax.text(
                0.005,
                0.005,
                map_attribution,
                transform=ax.transAxes,
                size=attribution_size,
                path_effects=[patheffects.withStroke(linewidth=2, foreground="w")],
                wrap=False
            )
            scalebar = AnchoredSizeBar(ax.transData,
                                       scaling['distance'], scaling['display'], 'lower right', 
                                       pad=1.2,
                                       color='black',
                                       frameon=False,
                                       size_vertical=1,
                                       fontproperties=fontprops)
            ax.add_artist(scalebar)
            ax.set_axis_off()
            # Create colorbar as a legend
            vmin,vmax = urban_grid[f'count_{dest_name}'].min(),urban_grid[f'count_{dest_name}'].max()
            # sm = plt.cm.ScalarMappable(cmap=’Blues’, norm=plt.Normalize(vmin=vmin, vmax=vmax))
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right", size="5%", pad=0.05)
            sm = plt.cm.ScalarMappable(cmap='viridis_r',norm=plt.Normalize(vmin=vmin, vmax=vmax))
            # empty array for the data range
            sm._A = []
            # add the colorbar to the figure
            cbar = ax.figure.colorbar(sm,cax=cax,fraction=0.046, pad=0.04,
             ticks=np.arange(np.min(urban_grid[f'count_{dest_name}']),np.max(urban_grid[f'count_{dest_name}'])+1))
            plt.tight_layout()
            ax.figure.savefig(f'../data/study_region/{study_region}/{study_region}_m_{dest_name}.png', bbox_inches = 'tight', pad_inches = .2, dpi=dpi)   
            ax.clear() 
    
    # Render report
    sql = '''
        SELECT dest_name, 
             dest_name_full,
             (osm_id IS NOT NULL)::boolean AS osm_sourced,
             COALESCE(COUNT(d.*),0) count
        FROM destinations d, 
             urban_study_region u 
        WHERE ST_DWithin(d.geom,u.geom,500) 
        GROUP BY dest_name, dest_name_full, osm_sourced;
    '''
    dest_counts = pd.read_sql(sql,engine,index_col='dest_name')   
    urban_area = urban_study_region.area_sqkm[0]
    urban_pop = int(urban_study_region.pop_est[0])
    urban_pop_dens = urban_study_region.pop_per_sqkm[0]
    
    # # Study region context
    if  area_data.startswith('GHS:'):
        # Cities like Maiduguri, Seattle and Baltimore have urban areas defined by GHS
        query = area_data.replace('GHS:','')
        blurb = (
          f'The urban portion of the city of {full_locale} was defined '
           'using the Global Human Settlements (GHS, 2019) urban centre '
          f'layer for 2015 filtered using the query, {query}.'
          f'Urban {full_locale} has an area of ' 
          f'{urban_area:,.2f} km² and had a population estimate of approximately ' 
          f'{urban_pop:,} persons in 2015, or {urban_pop_dens:,.2f} per km².'
          )
        desc_sr = (
           f'The GHS urban centre (yellow shading) of  {full_locale} was used '
            'to define the study region (cross-hatching} used for analysis of '
           f'liveability in {full_locale}.'
            )
    elif not_urban_intersection:
        # urban area defined using supplied administrative boundary only.
        # The main reason for this option being taken is that the administrative boundary 
        # for a city (e.g. Vic) does not correspond with any area in the GHS urban layer.
        blurb = (
          f'The administrative boundary for {full_locale} was used as the '
          f'urban study region for analysis purposes. Unlike other cities, it was not possible '
          'to use the  Global Human Settlements (GHS, 2019) urban centre layer to define '
          "the city's urban extent. "
          f'Urban {full_locale} has an area of ' 
          f'{urban_area:,.2f} km² and had a population estimate of approximately ' 
          f'{urban_pop:,} persons in 2015, or {urban_pop_dens:,.2f} per km².'
          )
        desc_sr = (
            'The administrative boundary (white outline) '
            'was used to define the '
            'study region (cross-hatching} used for analysis of '
           f'liveability in {full_locale}.'
           )
    else:
        # intersection of GHS urban area with administrative boundary
        blurb = (
          f'The urban portion of the city of {full_locale} was defined '
           'as the intersection of its administrative boundary '
           'and the Global Human Settlements (GHS, 2019) urban centre '
          f'layer for 2015 :cite:`ghs_ucl_data`.  Urban {full_locale} has an area of ' 
          f'{urban_area:,.2f} km² and had a population estimate of approximately ' 
          f'{urban_pop:,} persons in 2015, or {urban_pop_dens:,.2f} per km² :cite:`ghs_pop_method,ghs_pop_data`.'
          )
        desc_sr = (
            'The intersection of administrative boundary (white outline) '
            'and urban centre (yellow shading) areas was used to define the '
            'study region (cross-hatching} used for analysis of '
           f'liveability in {full_locale}.'
           )
    desc_pop = (
         'Spatial distribution of relative population density '
         '(estimated population per square kilometre) '
        f'for {full_locale}.'
    )
    rst = (
          f'Study region context\r\n^^^^^^^^^^^^^^^^^^^^\r\n\r\n'
          f'{blurb}\r\n\r\n'
          f'.. figure:: ../data/study_region/{study_region}/{study_region}_m_urban_boundary.png\r\n'
           '   :width: 70%\r\n'
           '   :align: center\r\n\r\n'
          f'   {desc_sr}\r\n\r\n'
          f'.. figure:: ../data/study_region/{study_region}/{study_region}_m_popdens.png\r\n'
           '   :width: 70%\r\n'
           '   :align: center\r\n\r\n'
          f'   {desc_pop}\r\n\r\n'
          f'Destinations\r\n^^^^^^^^^^^^\r\n\r\n'
           'Destinations sourced from OpenStreetMap (OSM) were identified using key-value pair tags.  '
           'Please see the :ref:`osm` section for more information, '
           'including links to guidelines for these categories and for '
           'country specific coding guidelines.\r\n'
          ) 
    if custom_destinations['file'] is not None:
        rst = f"{rst}Additional custom sourced destinations specific to the {full_locale} context were included in analyses using data collated with the assistance of {custom_destinations['attribution']}.\r\n"
    
    for d in destinations:
        dest_name = d[0]
        dest_name_full = d[1]
        dest_underline = '~'*len(dest_name_full)
        dest_count = dest_counts.loc[dest_name,'count'].sum()
        intro = destination_tags[dest_name]
        if dest_count == 0:
            rst = f'{rst}\r\n{intro}\r\nFor the city of {full_locale}, no destinations of this type were identified within a 500 metres Euclidean distance buffer of the urban study region boundary using OpenStreetMap data with the above listed key-value pair tags.'
            if custom_destinations['file'] is not None:
                rst = f'{rst}  Nor were destinations of this type included based on the custom data source specified in the configuration file.'
        else:
            dest_count_list = {}
            sources = ['custom','OSM']
            for l in [True,False]:
                dest_count_check = dest_counts.query(f"(dest_name_full=='{dest_name_full}') & (osm_sourced=={str(l)})")['count']
                if len(dest_count_check) == 0:
                    dest_count_list[sources[l]] = 0
                else:
                    dest_count_list[sources[l]] = dest_count_check[0]
            
            blurb = f"Within a 500 metres Euclidean distance buffer of {full_locale}'s urban study region boundary the count of {dest_name_full} destinations identified using OpenStreetMap data was {dest_count_list['OSM']:,}."
            
            if custom_destinations['file'] is not None:
                blurb = f"{blurb}  Using custom data, the {dest_name_full} count within this distance was {dest_count_list['custom']:,}."
            
            blurb = f'{blurb}\r\n\r\nPlease note that Euclidean distance analysis of destination counts was only undertaken in order to enumerate destinations within proximal distance of the city in order to produce this report; all indicators of access will be evaluated using network distance for sample points at regular intervals along the street network, prior to aggregation of estimates at small area and city scales.'
            desc_dest = f'Destinations defined using key-value pair tags (listed above) were extracted from matching OpenStreetMap points or polygon centroids to comprise the category of \'{dest_name_full}\'.  Aggregate counts of destinations within each cell of a 250m grid was undertaken to illustrate the spatial distribution of the identified data points.'
            rst = (
                  f'{rst}\r\n\r\n{dest_name_full}\r\n{dest_underline}\r\n\r\n'
                  f'{intro}\r\n{blurb}\r\n\r\n'
                  f'.. figure:: ../data/study_region/{study_region}/{study_region}_m_{dest_name}.png\r\n'
                   '   :width: 70%\r\n'
                   '   :align: center\r\n\r\n'
                  f'   {desc_dest}\r\n\r\n'
                  )   
    # POS
    blurb = destination_tags['pos']
    desc_pos = f'For the city of {full_locale}, areas of public open space identified in {full_locale} have been plotted in green in the above map.'
    rst = (
          f'{rst}\r\n\r\nPublic open space\r\n~~~~~~~~~~~~~~~~~\r\n\r\n'
          f'{blurb}\r\n\r\n'
          f'.. figure:: ../data/study_region/{study_region}/{study_region}_m_pos.png\r\n'
           '   :width: 70%\r\n'
           '   :align: center\r\n\r\n'
          f'   {desc_pos}\r\n\r\n'
          )       
          
    # Finally, we'll reference the bibliography under assumption this is the final chapter in report
    rst = (
          f'{rst}\r\n\r\n'
           '.. bibliography:: references.bib\r\n'
           '    :style: unsrt\r\n\r\n'
           )
    with open("../collaborator_report/report.rst", "w") as text_file:
        print(f"{rst}", file=text_file)
        
    index_rst = (
    '.. Global Liveability collaborator report template\r\n\r\n'
    'Global Liveability Indicators\r\n'
    '=============================\r\n\r\n'
   f'About\r\n'
    '*****\r\n'
    '.. toctree:: \r\n'
    '   :maxdepth: 3 \r\n'
    '   :caption: Contents: \r\n\r\n'
    '   about \r\n'
    '   dest_summary \r\n\r\n'
   f'{full_locale}\r\n'
    '{full_locale_underline}\r\n\r\n'
    '.. toctree:: \r\n'
    '   :maxdepth: 4 \r\n\r\n'
    '   report \r\n'
    ).format(full_locale=full_locale,
             full_locale_underline = '*'*len(full_locale))
    with open("../collaborator_report/index.rst", "w") as text_file:
        print(f"{index_rst}", file=text_file)
    line_prepender('../collaborator_report/conf_template.py','../collaborator_report/conf.py',get_sphinx_conf_header())
    city = full_locale.lower().replace(' ','')
    make = (
            "make clean" 
            "  && make latexpdf"
           f"  && cp _build/latex/globalliveabilityindicatorspreliminaryreport{city}.pdf "
           f"  ../data/study_region/{study_region}/global_liveability_{city}.pdf "
            )    
    sp.call(make, cwd ='../collaborator_report', shell=True)  
    engine.dispose()

if __name__ == '__main__':
    main()