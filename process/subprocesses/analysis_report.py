"""Analysis report subprocess."""

import os
from datetime import datetime

import pandas as pd
import yaml
from fpdf import FPDF
from PIL import ImageFile
from sqlalchemy import create_engine
from subprocesses._project_setup import (
    __version__,
    authors,
    codename,
    date_hhmm,
    db,
    db_host,
    db_pwd,
    db_user,
    df_osm_dest,
    pedestrian,
    region_config,
    study_buffer,
)
from subprocesses._utils import study_region_map

ImageFile.LOAD_TRUNCATED_IMAGES = True


def region_boundary_blurb_attribution(
    name, study_region_boundary, urban_region, urban_query,
):
    """Generate a blurb and attribution for the study region boundary."""
    citations = []
    sources = []
    if study_region_boundary == 'urban_query':
        blurb_1 = f"The study region boundary was defined using an SQL query that was run using ogr2ogr to import the corresponding features from {urban_region['name']} to the database."
        citations.append(urban_region['citation'])
        sources.append(
            f"{urban_region['name']} under {urban_region['license']}",
        )
    else:
        blurb_1 = f"The study region boundary was defined and imported to the database using ogr2ogr with data sourced from [{study_region_boundary['source']} ({study_region_boundary['publication_date'].strftime('%Y')})]({study_region_boundary['url']})."
        citations.append(study_region_boundary['citation'])
        sources.append(
            f"{study_region_boundary['source']} under {study_region_boundary['licence']}",
        )
    if study_region_boundary['ghsl_urban_intersection']:
        blurb_2 = f""" The urban portion of {name} was identified using the intersection of the study region boundary and urban regions sourced from {urban_region['name']} published as {urban_region['citation']}."""
        citations.append(urban_region['citation'])
        sources.append(
            f"{urban_region['name']} under {urban_region['licence']}",
        )
    else:
        blurb_2 = f""" This study region boundary was taken to represent the {name} urban region."""
    if urban_query:
        blurb_3 = f""" The SQL query used to extract urban areas from {urban_region['name']} was: {urban_query}."""
    else:
        blurb_3 = ''
    return {
        'blurb': blurb_1 + blurb_2 + blurb_3,
        'sources': set(sources),
        'citations': set(citations),
    }


# PDF layout set up
class PDF_Analysis_Report(FPDF):
    """PDF report class for analysis report."""

    def header(self):
        """Header of the report."""
        pdf.set_margins(19, 20, 19)
        if self.page_no() == 1:
            # Rendering logo:
            self.image(
                'configuration/assets/GOHSC - white logo transparent.svg',
                19,
                19,
                42,
            )
            # Printing title:
            self.set_font('helvetica', 'B', 24)
            with pdf.local_context(text_color=(89, 39, 226)):
                self.cell(38)
                self.write_html(
                    '<br><br><section><h1><font color="#5927E2"><b>{name}, {country}</b></font></h1></section>'.format(
                        **region_config,
                    ),
                )
                self.write_html(
                    '<font color="#CCCCCC"><b>Analysis report</b></font><br><br>'.format(
                        **region_config,
                    ),
                )
        else:
            # Rendering logo:
            self.image(
                'configuration/assets/GOHSC - white logo transparent.svg',
                19,
                19,
                42,
            )
            # Printing title:
            self.set_font('helvetica', 'B', 18)
            with pdf.local_context(text_color=(89, 39, 226)):
                self.cell(38)
                self.multi_cell(
                    w=134,
                    txt='{name}, {country}'.format(**region_config),
                    border=0,
                    align='R',
                )
        pdf.set_margins(19, 32, 19)

    def footer(self):
        """Page footer function."""
        # Position cursor at 1.5 cm from bottom:
        self.set_y(-15)
        # Setting font: helvetica italic 8
        self.set_font('helvetica', 'I', 8)
        # Printing page number:
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')


def network_description(region_config):
    blurbs = []
    blurbs.append(
        f"""The [OSMnx](https://geoffboeing.com/2016/11/osmnx-python-street-networks/#) software package was used to derive an undirected [non-planar](https://geoffboeing.com/publications/osmnx-complex-street-networks/) pedestrian network of edges (lines) and nodes (vertices, or intersections) for the buffered study region area using the following custom definition: **{region_config['network']['pedestrian']}**.  This definition was used to retrieve matching data via Overpass API for {region_config['OpenStreetMap']['publication_date']}.""",
    )
    if region_config['network']['osmnx_retain_all']:
        blurbs.append(
            'The network was extracted using OSMnx with the "retain_all" parameter set to __True__.  This meant that all network segments were retained, including those that were not connected to the main network.  This could mean that isolated network segments could be included, which could be problematic for evaluating accessibility if these are not truly disconnected in reality; this should be considered when reviewing results.',
        )
    else:
        blurbs.append(
            'The network was extracted using OSMnx with the "retain_all" parameter set to __False__.  This meant that only the main connected network was retained. In many circumstances this is the appropriate setting, however please ensure this is appropriate for your study region, as networks on real islands may be excluded.',
        )
    if region_config['network']['polygon_iteration']:
        blurb = 'To account for multiple disconnected pedestrian networks within the study region (for example, as may occur in a city spanning several islands), the network was extracted iteratively for each polygon of the study region boundary multipolygon. This meant that the network was extracted for each polygon, and then the resulting networks were combined to form the final network.'
        if type(region_config['network']['connection_threshold']) == int:
            blurb = f"""{blurb}.  Network islands were only included if meeting a minimum total network distance threshold set at {region_config['network']['connection_threshold']} metres. """
        blurbs.append(blurb)
    blurbs.append(
        f"""The OSMnx [consolidate_intersections()](https://osmnx.readthedocs.io/en/stable/osmnx.html#osmnx.simplification.consolidate_intersections) function was used to prepare a dataset of cleaned intersections with three or more legs, using a tolerance parameter of {region_config['network']['intersection_tolerance']} to consolidate network nodes within this distance as a single node.  This ensures that intersections that exist for representational or connectivity purposes (for example a roundabout, that may be modelled with multiple nodes but in effect is a single intersections) do not inflate estimates when evaluating street connectivity for pedestrians.""",
    )
    blurbs.append(
        'The derived pedestrian network nodes and edges, and the dataset of cleaned intersections were stored in the PostGIS database.',
    )
    return ' '.join(blurbs)


def get_analysis_report_region_configuration(region_config):
    region_config['__version__'] = __version__
    region_config['authors'] = authors
    region_config['codename'] = codename
    region_config['OpenStreetMap'][
        'note'
    ] = f".  The following note was recorded: __{region_config['OpenStreetMap']['note'] if region_config['OpenStreetMap']['note'] is not None else ''}__"
    region_config['OpenStreetMap']['publication_date'] = datetime.strptime(
        str(region_config['OpenStreetMap']['publication_date']), '%Y%m%d',
    ).strftime('%d %B %Y')
    region_config['study_buffer'] = study_buffer
    region_config['study_region_blurb'] = region_boundary_blurb_attribution(
        region_config['name'],
        region_config['study_region_boundary'],
        region_config['urban_region'],
        region_config['urban_query'],
    )
    region_config['network']['pedestrian'] = pedestrian
    region_config['network']['description'] = network_description(
        region_config,
    )
    with open(f"{region_config['region_dir']}/_parameters.yml") as f:
        region_config['parameters'] = yaml.safe_load(f)
    return region_config


def render_analysis_report(region_config):
    # Instantiation of inherited class
    pdf = PDF_Analysis_Report()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    # pdf.insert_toc_placeholder(render_toc)
    # pdf.write_html("<toc></toc>")
    for element in region_config['elements']:
        if element[0].startswith('h') and element[0][1].isdigit():
            capture = pdf.write_html(
                f'<section><{element[0]}><font color="#5927E2">{element[1]}</font></{element[0]}><br></section>',
            )
        elif element[0] == 'newpage':
            capture = pdf.add_page()
        elif element[0] == 'blurb':
            capture = pdf.multi_cell(0, txt=element[1], markdown=True)
            capture = pdf.ln(2)
        elif element[0] == 'image':
            capture = pdf.ln(2)
            capture = pdf.image(element[1], x=30, w=150)
            capture = pdf.ln(2)
        elif element[0] == 'table':
            capture = pdf.ln(4)
            # assuming that element[1]['data'] is a pandas dataframe
            # and that element[1]['description'] describes it
            capture = pdf.multi_cell(
                0, txt=f"__{element[1]['description']}__", markdown=True,
            )
            capture = pdf.ln(2)
            if 'align' in element[1]:
                align = element[1]['align']
            else:
                align = 'CENTER'
            with pdf.table(
                borders_layout='SINGLE_TOP_LINE',
                cell_fill_color=200,  # greyscale
                cell_fill_mode='ROWS',
                text_align='CENTER',
                line_height=5,
            ) as table:
                # add header row
                capture = table.row(list(element[1]['data'].columns))
                # add data rows
                for d in element[1]['data'].itertuples():
                    row = table.row()
                    for datum in d[1:]:
                        capture = row.cell(str(datum))
    report_file = (
        f'{region_config["region_dir"]}/analysis_report_{date_hhmm}.pdf'
    )
    capture = pdf.output(report_file)
    print(f'  {os.path.basename(report_file)}')


def generate_analysis_report(engine, region_config):
    region_config = get_analysis_report_region_configuration(region_config)
    # prepare images
    study_region_context_file = study_region_map(
        engine,
        region_config,
        urban_shading=False,
        basemap='satellite',
        arrow_colour='white',
        scale_box=True,
        file_name='study_region_boundary',
    )
    print('  figures/study_region_boundary.jpg')
    study_region_urban_shading = study_region_map(
        engine,
        region_config,
        edgecolor='black',
        basemap='light',
        file_name='study_region_boundary_urban_shading',
    )
    print('  figures/study_region_boundary_urban_shading.jpg')
    network_plot = study_region_map(
        engine,
        region_config,
        edgecolor='black',
        urban_shading=False,
        basemap='light',
        file_name='network_edges',
        additional_layers={
            'edges': {
                'facecolor': 'none',
                'edgecolor': 'black',
                'alpha': 0.7,
                'lw': 0.5,
                'markersize': None,
            },
        },
        additional_attribution=f"""Pedestrian network edges: OpenStreetMap contributors ({region_config['OpenStreetMap']['publication_date']}), under {region_config['OpenStreetMap']['licence']}; network detail, including nodes and cleaned intersections can be explored using desktop mapping software like QGIS, using a connection to the {db} database.""",
    )
    print('  figures/network_edges.jpg')
    population_grid = study_region_map(
        engine,
        region_config,
        edgecolor='black',
        urban_shading=False,
        basemap='light',
        file_name='population_grid',
        additional_layers={
            f'{region_config["grid_summary"]}': {
                'facecolor': 'none',
                'edgecolor': 'none',
                'alpha': 1,
                'lw': 0,
                'markersize': None,
                'column': 'pop_est',
            },
        },
        additional_attribution=f"""Population grid estimates: {region_config['population']['name']}, under {region_config['population']['licence']}.""",
    )
    print('  figures/population_grid.jpg')
    destination_plots = {}
    for dest in df_osm_dest['dest_full_name'].unique():
        destination_plots[dest] = study_region_map(
            engine,
            region_config,
            edgecolor='black',
            urban_shading=False,
            basemap='light',
            file_name=f'destination_count_{dest}',
            additional_layers={
                'population_dest_summary': {
                    'facecolor': 'none',
                    'edgecolor': 'none',
                    'alpha': 1,
                    'lw': 0,
                    'markersize': None,
                    'column': 'count',
                    'where': f"""WHERE dest_name_full = '{dest}'""",
                },
            },
            additional_attribution=f"""{dest} counts: OpenStreetMap contributors ({region_config['OpenStreetMap']['publication_date']}), under {region_config['OpenStreetMap']['licence']}.""",
        )
        print(f'  figures/destination_count_{dest}.jpg')
    # prepare tables
    osm_destination_definitions = df_osm_dest[
        ['dest_full_name', 'key', 'value', 'pre-condition']
    ].set_index('dest_full_name')
    osm_destination_definitions['pre-condition'] = osm_destination_definitions[
        'pre-condition'
    ].replace('NULL', 'OR')
    with engine.connect() as connection:
        destination_counts = pd.read_sql(
            """SELECT dest_name_full Destination, count from dest_type;""",
            connection,
        )
    # prepare report elements
    elements = [
        ('image', study_region_context_file),
        ('h2', 'Background'),
        (
            'blurb',
            'An analysis was conducted for {name} using the [Global Healthy and Sustainable City Indicators (GHSCI; global-indicators) software](https://global-healthy-liveable-cities.github.io/).  This software supports  analysis and reporting on health related spatial indicators of urban design and transport features for diverse regions of interest using open and/or custom data.  Spatial and network analyses are conducted according to user configuration for sample points generated along a derived pedestrian network. Results are aggregated to a grid with resolution corresponding to the input population data used, as well as overall summaries for the city or region of interest. It outputs data, documentation, maps, figures and reports in multiple languages to support further analysis as well as publication and sharing of findings.  The software is designed to support the 1000 Cities Challenge of the [Global Observatory of Healthy and Sustainable Cities](https://healthysustainablecities.org).'.format(
                **region_config,
            ),
        ),
        ('newpage',),
        ('h2', 'Software details'),
        (
            'blurb',
            'The analysis was conducted using [version {__version__} of the global-indicators code](https://github.com/global-healthy-liveable-cities/global-indicators/releases/tag/v{__version__}) along with the [corresponding Docker image](globalhealthyliveablecities/global-indicators:v{__version__}).  The GHSCI Docker image is officially sponsored as an open source project and provides a stable, curated suite of software allowing the analysis to be launched and run on different computing platforms, including Linux, Python, OSMnx, NetworkX, GeoPandas, Pandas, Matplotlib, Shapely, Fiona, Rasterio, GDAL, Pyproj, and others.  The full list of software used is described in the following text files in the docker folder: Dockerfile, environment.yml, and requirements.txt.  In addition the pgRouting Docker image was also retrieved, to run a Postgres SQL database with the PostGIS and pgRouting extensions, supporting data management and advanced spatial and network analyses.  A shell script retrieved and launched the Docker images with these dependencies as containers, with a command prompt guiding users through the three step analysis process: configuration, analysis and generation of resources.'.format(
                **region_config,
            ),
        ),
        ('h2', 'Configuration'),
        (
            'blurb',
            'Analysis was configured and run for {name} ({country}, {continent}) with a target time point of {year} by {authors}.  The spatial coordinate reference system used was {crs[name]} ({crs[standard]}:{crs[srid]}).  Data were retrieved and stored on the computer used for analysis.  Corresponding metadata including the file paths required to locate the data were defined in text configuration files along with the parameters used to configure the analysis (see `parameters.yml`).'.format(
                **region_config,
            ),
        ),
        ('h2', 'Database set up'),
        (
            'blurb',
            "An SQL database was created ({db}) with the PostGIS and pgRouting extensions, that could be connected to within the Docker container.  The database could also be connected to by external application (e.g. for creation of maps in QGIS) by specifying the host as 'localhost' on port 5433.".format(
                **region_config,
            ),
        ),
        ('h2', 'Study region set up'),
        (
            'blurb',
            'The study region folder was created using the configured codename (__{codename}__), and data were imported to construct the study region boundaries. {study_region_blurb[blurb]} To ensure the environmental contexts of locations near the edge of the study region boundary were fairly represented a {study_buffer} m buffer was applied to be used when extracting features from datasets to ensure that nearby features and amenities considered when constructing indicators were accounted for, even if located outside the urban region itself.'.format(
                **region_config,
            ),
        ),
        ('image', study_region_urban_shading),
        ('h2', 'OpenStreetMap data set up'),
        (
            'blurb',
            """[OpenStreetMap](https://www.openstreetmap.org/) is a collaborative mapping platform with an open data ethos launched in 2004 that provides a publicly accessible, richly attributed and longitudinally archived global dataset that can be used to identify road, point and area features, including fresh food or markets and public open space.  It is an important source for consistently coded road network data globally, with estimated completeness of coverage being [very high for urban areas](https://doi.org/10.1371/journal.pone.0180698) with favourable comparisons to official datasets, and having established tools supporting its use in geospatial urban transport analysis.""",
        ),
        (
            'blurb',
            'OpenStreetMap data published {OpenStreetMap[publication_date]} were sourced from [{OpenStreetMap[source]} ({OpenStreetMap[publication_date]})]({OpenStreetMap[url]}){OpenStreetMap[note]}  The buffered urban study region boundary was used to extract the region of interest from the source data using osmconvert and save this to the study region output folder.  Features for this region were then imported to the PostGIS database using osm2pgsql, and with geometries updated to match the project coordinate reference system.'.format(
                **region_config,
            ),
        ),
        (
            'blurb',
            """There are established guidelines for tagging destinations in OpenStreetMap using English or bilingually, for specific types of destinations of interest that were drawn upon to identify features of interest for this analysis.  These included: [Supermarkets](https://wiki.openstreetmap.org/wiki/Tag:shop%3Dsupermarket) (commonly used in built environment analysis as a primary source of fresh food); [Markets](https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dmarketplace) (which may be a major source of fresh food in some locations of some cities); [Shops](https://wiki.openstreetmap.org/wiki/Key:shop), in general (which may include bakeries, or other specific locations selling fresh food); [Convenience stores](https://wiki.openstreetmap.org/wiki/Tag:shop%3Dconvenience) (where basic and non-essential items may be acquired); [Public transport](https://wiki.openstreetmap.org/wiki/Public_transport) (in the absence of more informative transport schedule data, OpenStreetMap can include information on bus, tram/light rail, train/metro/rail, ferry stops or stations, et cetera); [Public open space]( which can include [green space](https://wiki.openstreetmap.org/wiki/Green_space_access_ITO_map), [squares](https://wiki.openstreetmap.org/wiki/Tag:place%3Dsquare), or other kinds of [public areas for pedestrians](https://wiki.openstreetmap.org/wiki/Tag:highway%3Dpedestrian).""",
        ),
        (
            'blurb',
            """The above guidelines were consulted along with [OSM TagInfo](https://taginfo.openstreetmap.org/) to identify a set of appropriate tags which collectively were used define sets of destinations belonging to each of these categories.  A tag is a way which contributors to OSM mark data using combinations of terms called key-value pairs.  Where a destination in the real world does not appear in an extract of the OSM data, there are two reasons this might be the case; either there is no information on the destination in OSM (it has not been entered by an OSM contributor), or alternatively the way the destination was tagged was not considered during the extraction process.  The GHSCIC have audited the use of OpenStreetMap, and like other researchers, we have found it broadly acceptable for use in our urban contexts, however for some contexts supplementary data will be required to ensure that the data used is complete and accurate.""",
        ),
        (
            'blurb',
            """Destination counts and distribution maps for {name} are provided below, followed by the tags used for coding.  If you are considering modifying the configured values for OpenStreetMap destinations, [OSM TagInfo](https://taginfo.openstreetmap.org/) can be used to query the usage of a 'key' like '[shop](https://taginfo.openstreetmap.org/keys/shop), or a value associated with a key like: "shop = [supermarket](https://taginfo.openstreetmap.org/tags/shop=supermarket)".  Using this website, you can also view a [map of the global distribution](https://taginfo.openstreetmap.org/tags/shop=supermarket#map) of such tags.  If you want to view the spatial distribution of tagging in a particular country in detail, you can click the 'Overpass turbo' button, which will load up a map on the right hand side of a window and some code in the left hand side; drag and zoom or search for your area of interest and then click 'Run' the code.  Any locations tagged in this way in this location will be displayed.  You can click on a particular location to view additional tags that may have been coded, in addition to the one which you initially queried.  This can be a useful way to identify additional tags that could be used to customise the analysis to account for the local context of your region of interest.  There are also additional applied [guidelines](https://wiki.openstreetmap.org/wiki/Category:Tagging_guidelines_by_country) available for many countries/regions.""",
        ),
        (
            'table',
            {
                'data': destination_counts,
                'description': 'Destination counts using OpenStreetMap and/or custom data.  Note that definitions were provided for some additional locations that were not included in the analysis, but which may be of interest to some users.  These are included in the table below for reference (restaurants, cafes, food courts, fast food, pub and bar locations).',
                'align': ['LEFT', 'RIGHT'],
            },
        ),
        (
            'table',
            {
                'data': osm_destination_definitions.loc['Fresh Food / Market'],
                'description': 'Tags used to identify fresh food market locations using OpenStreetMap.',
                'align': ['LEFT', 'LEFT', 'CENTER'],
            },
        ),
        ('image', destination_plots['Fresh Food / Market']),
        (
            'table',
            {
                'data': osm_destination_definitions.loc['Convenience'],
                'description': 'Tags used to identify convenience locations using OpenStreetMap.',
                'align': ['LEFT', 'LEFT', 'CENTER'],
            },
        ),
        ('image', destination_plots['Convenience']),
        (
            'table',
            {
                'data': osm_destination_definitions.loc[
                    'Public transport stop (any)'
                ],
                'description': 'Tags used to identify public transport stop (any) locations using OpenStreetMap.',
                'align': ['LEFT', 'LEFT', 'CENTER'],
            },
        ),
        ('image', destination_plots['Public transport stop (any)']),
        ('h2', 'Pedestrian network set up'),
        ('blurb', '{network[description]}'.format(**region_config)),
        ('image', network_plot),
        ('h2', 'Population data set up'),
        (
            'blurb',
            """Population distribution data for {name} were sourced from [{population[name]} ({population[year_published]})]({population[source_url]}) for a target year of {population[year_target]}.  This data was used under {population[licence]} terms.   The configured population data grid had a resolution of {population[resolution]} m, and was used for summarising the spatial distribution of indicator results prior to aggregation to larger scales.  Density estimates for population and clean intersections per square kilometre were calculated for each grid cell.""".format(
                **region_config,
            ),
        ),
        ('image', population_grid),
        ('h2', 'Configuration parameters'),
        ('blurb', yaml.dump(region_config['parameters'])),
    ]
    region_config['elements'] = elements
    render_analysis_report(region_config)
