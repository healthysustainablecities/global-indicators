"""

Utility functions
~~~~~~~~~~~~~~~~~

::

    Script:  _utils.py
    Purpose: These functions may be used in other scripts to undertake specific tasks.
    Authors: Carl Higgs
    Context: Liveability indicator calculation (general tools for data wrangling)

Todo:
    * further refactor and abstract code as functions for autodoc purposes
    
"""

import os

# function for printing dictionaries in 'pretty' format to screen 
def pretty(d, indent=0):
    """Print dictionary data structure in 'pretty' format to screen 
    
    Args:       
        d (dict): a python dictionary
    """
    for key, value in d.items():
       depth = 0
       print('\t' * indent + str(key)+':'),
       if isinstance(value, dict):
         if depth == 0:
           print(" ")
           depth+=1
         pretty(value, indent+1)
       else:
         print(' ' + str(value))
    
def table_exists(name):
    """Check if a database table already exists
    
    Args:       
        name (str): a table which may or may not exist
    
    Outputs:
        ret (bool): a logical indication of existance (True or False)
    """
    ret = engine.dialect.has_table(engine, name)
    print('Table "{}" exists: {}'.format(name, ret))
    return ret

# function for returning a pandas type given a string value representing that type
def valid_type(str_of_type):
    """Function for returning a pandas type given a string value representing that type
    
    Args:       
        str_of_type (str): a python type in string form
    
    Outputs:
        the Pandas term for that type
    """
    if str_of_type in ['int','integer']:
        return('Int64')
    elif str_of_type in ['float','double precision']:
        return('float64')
    elif str_of_type in ['str','string','text','object']:
        return('object')
    else:
        return('object')

def style_dict_fcn(type = 'qualitative',colour=0):
    """Return a set of colours for use in maps
    
    Rationale:
        Make use of colourbrewer colour scheme readily accessible and swappable
    
    Args:       
        type (str): Either 'qualitative or 'diverging' for preset schemas
        colour (int): index number of colour to return
    
    Outputs:
        A png file in the specified output directory
    
    Todo:
        * re-think the purpose of this -- perhaps could use an existing colorbrewer library?
        * or just include the standard colorbrewer options (pgrn etc)
    """
    # Colours for presenting maps
    colours = {}
    # http://colorbrewer2.org/#type=qualitative&scheme=Dark2&n=8
    colours['qualitative'] = ['#1b9e77','#d95f02','#7570b3','#e7298a','#66a61e','#e6ab02','#a6761d','#666666']
    # http://colorbrewer2.org/#type=diverging&scheme=PuOr&n=8
    colours['diverging'] = ['#8c510a','#bf812d','#dfc27d','#f6e8c3','#c7eae5','#80cdc1','#35978f','#01665e']
    
    if type not in ['qualitative','diverging']:
        print("Specified type unknown; assuming 'qualitative'.")
        type = 'qualitative'
    return {
        'fillOpacity': 0.5,
        'line_opacity': 0.2,
        'fillColor': colours[type][colour],
        'lineColor': colours[type][colour]
    }

def folium_to_image(input_dir='',output_dir='',map_name='',formats=['png'],width=1000,height=800,pause=3,strip_elements=["leaflet-control-zoom","leaflet-control-layers"]):
    """This function converts an input html page to a png image
    
    Rationale:
        Leaflet is useful for creating interactive maps; this function is used to 
        re-purpose these as static maps too.
    
    Args:       
        input_dir (str): the input directory for an html file
        output_dir (str): the output directory for a png file
        map_name (str): the file basename
        formats (str): the desired output format
        width (int): width in pixels (default = 1000)
        height (int): height in pixels (default = 800)
        pause (int): a delay time to allow the web page to fully load (e.g. online basemaps)
        strip_elements (str array): A list of div tags to remove (e.g. interactive legend, zoom controls)
    
    Outputs:
        A png file in the specified output directory
    
    Todo:
        * input should be path not seperate dir and file; can get base path from the single file path
        * modify this to also allow to pdf -- perhaps using pdfkit
            * https://stackoverflow.com/questions/54390417/how-to-download-a-web-page-as-a-pdf-using-python
            * I think in future should use puppeteer with headless chrome (or pyppeteer)
    """
    import selenium.webdriver
    import time
    try:
        if (input_dir=='' or map_name==''):
            raise Exception(('This function requires specification of an input directory.\n'
                   'Please specify the function in the following form:\n'
                   'folium_to_png(input_dir,output_dir,map_name,[["format","format"]],[width],[height],[pause])'
                   ))
            return
        if output_dir=='':
            output_dir = input_dir
        options=selenium.webdriver.firefox.options.Options()
        options.add_argument('--headless')
        driver = selenium.webdriver.Firefox(options=options)
        driver.set_window_size(width, height)  # choose a resolution
        driver.get('file:///{}/{}/{}.html'.format(os.getcwd(),input_dir,map_name))
        # You may need to add time.sleep(seconds) here
        time.sleep(pause)
        # Remove zoom controls from snapshot
        for leaflet_class in strip_elements:
            element = driver.find_element_by_class_name(leaflet_class)
            driver.execute_script("""
            var element = arguments[0];
            element.parentNode.removeChild(element);
            """, element)
        if 'png' in formats:
            driver.save_screenshot('{}/{}.png'.format(output_dir,map_name))
        # if 'pdf' in formats:
            # import pdfkit
            # with open("{}/__folium_temp.html".format(output_dir), "w") as f:
                # f.write(driver.page_source)
            # pdfkit.from_file("{}/__folium_temp.html".format(output_dir), 
                             # '{}/{}.pdf'.format(output_dir,map_name))
            # os.remove("{}/__folium_temp.html".format(output_dir))
        driver.close()
    except Exception as error:
        print("Export of {} failed.".format('{}/{}.png: {}'.format(output_dir,map_name,error)))

def define_geojson_coordinates(i,coords=['lat','long']):
    """Updates json coordinates for display as geojson.
    
    This function takes a json feature collection feature which has been 
    set up as though it were a geojson (ie. with correct structure and
    tags) and replaces the template null geometry tags with the actual
    coordinates recorded for that feature.
    
    Rationale:
        The `Air4Thai`_ data can be saved as json. 
        This records measurements for various pollutants at stations across 
        Thailand, as well as metadata for each station including its coordi-
        nates in latitude and longitude.  
        
        However some manipulation is required to reformat this json data for
        correct display as a geojson, retaining all the included attributes.
    
    Example input:
    
        ::
        
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        0,
                        0
                    ]
                },
                "properties": {
                    ...
                    "lat": "13.666183",
                    "long": "100.605742",
                    ...
               }
            }
        
    Example output:
    
        ::
        
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        100.605742,
                        13.666183
                    ]
                },
                "properties": {
                    ...
                    "lat": "13.666183",
                    "long": "100.605742",
                    ...
               }
            }
    
    Args:
        i (geojson feature): This is a geojson feature, containing incorrect
        coords (2-tuple of strings): a 2-item list of 
            string names for the latitude and longitude coordinates
    
    Returns:
        geojson feature: Geojson feature with coordinates replaced as per the specified
        coordinates in the input feature's properties record.
    
    .. _Air4Thai:
        http://air4thai.pcd.go.th

    """
    i['geometry']['coordinates'][0] = float(i['properties'][coords[1]])
    i['geometry']['coordinates'][1] = float(i['properties'][coords[0]])
    return i

def unnest_json_property(i,nested_property):
    """This function takes each item of the nested list and returns as a 
    property in its own right, prefixed by an underscore '_' to mitigate
    risk of name clash.  For any nested items, the nested list name is
    taken as a prefix and append to any child items.  
    
    Rationale:
        The `Air4Thai`_ data can be saved as json. 
        This records measurements for various pollutants at stations across 
        Thailand.  However, this is recorded as a nested list, which without 
        further processing (un-nesting) cannot be mapped or analysed directly.
    
    Args:
        i (geojson feature): This is a geojson feature, containing incorrect
        nested_property (string): a string identifying a nested property
    
    Returns:
        geojson feature: Geojson feature with its nested property un-nested.
    
    .. _Air4Thai:
        http://air4thai.pcd.go.th
    """
    for x in i['properties'][nested_property]:
        if type(i['properties'][nested_property][x]) is not dict:
            i['properties']['_{}'.format(x)] = i['properties'][nested_property][x]
        else:
            for n in i['properties'][nested_property][x]:
                i['properties']['_{}_{}'.format(x,n)] = i['properties'][nested_property][x][n]
    return i

def recast_json_properties(i,na=[]):
    """This function iterates over properties and recasts to integer or float 
    values as appropriate.  Any "N/A" values are replaced as numpy nan values.
    
    Rationale:
        The `Air4Thai`_ data can be saved as json. 
        This records measurements for various pollutants at stations across 
        Thailand.  However, numeric values are presented as strings, and 
        have hard-coded text "N/A" values for not applicable data.
    
    Args:
        i (json feature): This is a json feature
        na (string array): a list of strings representing values which should be 
        interpreted as nan
    
    Returns:
        geojson feature: Geojson feature with recast properties
    
    .. _Air4Thai:
        http://air4thai.pcd.go.th
    """
    import numpy as np
    for p in i['properties']:
        # print(i['properties'][p])
        if type(i['properties'][p]) is not dict:
            # if appears to be integer, cast to int
            if '{}'.format(i['properties'][p]).isdigit():
                i['properties'][p] = int(i['properties'][p])
            # if appears to be float, cast as float
            elif '{}'.format(i['properties'][p]).replace('.','',1).isdigit():
                i['properties'][p] = float(i['properties'][p])
            # if appears to be na, cast as np.nan
            elif '{}'.format(i['properties'][p]) in na:
                i['properties'][p] = np.nan
            # otherwise, let it be - probably a string
    
    return i

def add_json_datetime_property(i,date='_date',time='_time',format= '{d}T{t}:00',datetime_field='time'):
    """Format datetime field based on given date, time, and format.
    
    Rationale:
        Some applications require a joint date-time variable in a specific format.
        Given an input json feature with properties and the names of fields 
        representing 'date' and 'time', a 'datetime' field is returned.
    
    Args:
        i (geojson feature): This is a geojson feature, containing incorrect
        date (string): Property name of date string
        time (string): Property name of time string
        format (string): A parameterised format for combining these two fields
        datetime_field : A new field to contain the formatted datetime variable
    
    Returns:
        geojson feature: Geojson feature with date time variable
    """
    t = i['properties']['_time']
    d = i['properties']['_date']
    i['properties'][datetime_field] = format.format(d=d,t=t)
    return i

def reproject_raster(inpath, outpath, new_crs):
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    dst_crs = new_crs # CRS for web meractor 
    with rasterio.open(inpath) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': dst_crs,
            'transform': transform,
            'width': width,
            'height': height
        })
        with rasterio.open(outpath, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest)
                    
                    
hex_function = '''
        --------------------------------------------------------------------------------------------------------------------------------
        -- HEX GRID - Create function
        --------------------------------------------------------------------------------------------------------------------------------
        --
        -- Hugh Saalmans (@minus34)
        -- 2015/04/10
        --
        -- DESCRIPTION:
        -- 
        -- Function returns a grid of mathmatically correct hexagonal polygons.
        -- Useful for hexbinning (the art of mapping clusters of information unbiased by political/historical/statistical boundaries).
        --
        -- INPUT
        --
        --   areakm2     : area of each hexagon in square km.
        --                   - note: hexagon size can be off slightly due to coordinate rounding in the calcs.
        --
        --   xmin, ymin  : min coords of the grid extents.
        --
        --   xmax, ymax  : max coords of the grid extents.
        --
        --   inputsrid   : the coordinate system (SRID) of the input min/max coords.
        --
        --   workingsrid : the SRID used to process the polygons.
        --                   - SRID must be a projected coord sys (i.e. in metres) as the calcs require ints. Degrees are out.
        --                   - should be an equal area SRID such as Albers or Lambert Azimuthal (e.g. Australia = 3577, US = 2163).
        --                   - using Mercator will NOT return hexagons of equal area due to its distortions (don't try it in Greenland).
        --
        --   ouputsrid   : the SRID of the output polygons.
        --
        -- NOTES
        --
        --   Hexagon height & width are rounded up & down to the nearest metre, hence the area may be off slightly.
        --   This is due to the Postgres generate_series function which doesn't support floats.
        --
        --   Why are my areas wrong in QGIS, MapInfo, etc...?
        --      Let's assume you created WGS84 lat/long hexagons, you may have noticed the areas differ by almost half in a desktop GIS
        --      like QGIS or MapInfo Pro. This is due to the way those tools display geographic coordinate systems like WGS84 lat/long.
        --      Running the following query in PostGIS will confirm the min & max sizes of your hexagons (in km2):
        --
        --         SELECT (SELECT (MIN(ST_Area(geom::geography, FALSE)) / 1000000.0)::numeric(10,3) From my_hex_grid) AS minarea,
        --               (SELECT (MAX(ST_Area(geom::geography, FALSE)) / 1000000.0)::numeric(10,3) From my_hex_grid) AS maxarea;
        --
        --   Hey, why doesn't the grid cover the area I defined using my min/max extents?
        --      Assuming you used lat/long extents and processed the grid with an equal area projection, the projection caused your
        --      min/max coords to describe a conical shape, not a rectangular one - and the conical area didn't cover everything you
        --      wanted to include.  See au-hex-grid.png as an example of this.
        --      If you're bored - learn why projections distort maps here: http://www.icsm.gov.au/mapping/about_projections.html
        --
        --   This code is based on this PostGIS Wiki article: https://trac.osgeo.org/postgis/wiki/UsersWikiGenerateHexagonalGrid
        --
        --   Dimension calcs are based on formulae from: http://hexnet.org/content/hexagonal-geometry
        --
        -- LICENSE
        --
        -- This work is licensed under the Apache License, Version 2: https://www.apache.org/licenses/LICENSE-2.0
        --
        --------------------------------------------------------------------------------------------------------------------------------
        
        --DROP FUNCTION IF EXISTS hex_grid(areakm2 FLOAT, xmin FLOAT, ymin FLOAT, xmax FLOAT, ymax FLOAT, inputsrid INTEGER,
        --  workingsrid INTEGER, ouputsrid INTEGER);
        CREATE OR REPLACE FUNCTION hex_grid(areakm2 FLOAT, xmin FLOAT, ymin FLOAT, xmax FLOAT, ymax FLOAT, inputsrid INTEGER,
          workingsrid INTEGER, ouputsrid INTEGER)
          RETURNS SETOF geometry AS
        $BODY$
        
        DECLARE
          minpnt GEOMETRY;
          maxpnt GEOMETRY;
          x1 INTEGER;
          y1 INTEGER;
          x2 INTEGER;
          y2 INTEGER;
          aream2 FLOAT;
          qtrwidthfloat FLOAT;
          qtrwidth INTEGER;
          halfheight INTEGER;
        
        BEGIN
        
          -- Convert input coords to points in the working SRID
          minpnt = ST_Transform(ST_SetSRID(ST_MakePoint(xmin, ymin), inputsrid), workingsrid);
          maxpnt = ST_Transform(ST_SetSRID(ST_MakePoint(xmax, ymax), inputsrid), workingsrid);
        
          -- Get grid extents in working SRID coords
          x1 = ST_X(minpnt)::INTEGER;
          y1 = ST_Y(minpnt)::INTEGER;
          x2 = ST_X(maxpnt)::INTEGER;
          y2 = ST_Y(maxpnt)::INTEGER;
        
          -- Get height and width of hexagon - FLOOR and CEILING are used to get the hexagon size closer to the requested input area
          aream2 := areakm2 * 1000000.0;
          qtrwidthfloat := sqrt(aream2/(sqrt(3.0) * (3.0/2.0))) / 2.0;
          
          qtrwidth := FLOOR(qtrwidthfloat);
          halfheight := CEILING(qtrwidthfloat * sqrt(3.0));
        
          -- Return the hexagons - done in pairs, with one offset from the other
          RETURN QUERY (
            SELECT ST_Transform(ST_SetSRID(ST_Translate(geom, x_series::FLOAT, y_series::FLOAT), workingsrid), ouputsrid) AS geom
              FROM generate_series(x1, x2, (qtrwidth * 6)) AS x_series,
                   generate_series(y1, y2, (halfheight * 2)) AS y_series,
                   (
                     SELECT ST_GeomFromText(
                       format('POLYGON((0 0, %s %s, %s %s, %s %s, %s %s, %s %s, 0 0))',
                         qtrwidth, halfheight,
                         qtrwidth * 3, halfheight,
                         qtrwidth * 4, 0,
                         qtrwidth * 3, halfheight * -1,
                         qtrwidth, halfheight * -1
                       )
                     ) AS geom
                     UNION
                     SELECT ST_Translate(
                       ST_GeomFromText(
                         format('POLYGON((0 0, %s %s, %s %s, %s %s, %s %s, %s %s, 0 0))',
                           qtrwidth, halfheight,
                           qtrwidth * 3, halfheight,
                           qtrwidth * 4, 0,
                           qtrwidth * 3, halfheight * -1,
                           qtrwidth, halfheight * -1
                         )
                       )
                     , qtrwidth * 3, halfheight) as geom
                   ) AS two_hex);
        
        END$BODY$
          LANGUAGE plpgsql VOLATILE
          COST 100;
        '''