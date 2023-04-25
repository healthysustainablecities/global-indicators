import json
from datetime import datetime

from fpdf import FPDF
from sqlalchemy import create_engine
from subprocesses._project_setup import (
    __version__,
    authors,
    codename,
    db,
    db_host,
    db_pwd,
    db_user,
    pedestrian,
    region_config,
    study_buffer,
)
from subprocesses._utils import study_region_map


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
region_config['network']['description'] = network_description(region_config)

# connect to database
engine = create_engine(f'postgresql://{db_user}:{db_pwd}@{db_host}/{db}')

# prepare images
study_region_context_file = study_region_map(
    engine,
    region_config,
    urban_shading=False,
    arrow_colour='white',
    scale_box=True,
    file_name='study_region_boundary',
)

study_region_urban_shading = study_region_map(
    engine,
    region_config,
    basemap=False,
    file_name='study_region_boundary_urban_shading',
)

network_plot = study_region_map(
    engine,
    region_config,
    urban_shading=False,
    basemap=False,
    file_name='network_edges',
    additional_layers={
        'edges': {
            'facecolor': 'none',
            'edgecolor': 'black',
            'alpha': 0.7,
            'lw': 0.5,
            'markersize': None,
        },
        # 'nodes':{
        #     'facecolor': 'black',
        #     'edgecolor': 'none',
        #     'markersize': 0.4,
        #     'alpha': 0.7,
        #     'lw': 0,
        # },
        # f"""clean_intersections_{region_config['network']['intersection_tolerance']}m""":{
        #     'facecolor': 'yellow',
        #     'edgecolor': 'none',
        #     'markersize': 1,
        #     'alpha': 1,
        #     'lw': 0.5,
        # },
    },
    additional_attribution=f"""Pedestrian network edges: OpenStreetMap contributors {region_config['OpenStreetMap']['publication_date']} (network detail, including nodes and cleaned intersections can be explored using desktop mapping software like QGIS, using a connection to the {db} database).""",
)

population_grid = study_region_map(
    engine,
    region_config,
    urban_shading=False,
    basemap=False,
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
)

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
        'OpenStreetMap data published {OpenStreetMap[publication_date]} were sourced from [{OpenStreetMap[source]} ({OpenStreetMap[publication_date]})]({OpenStreetMap[url]}){OpenStreetMap[note]}  The buffered urban study region boundary was used to extract the region of interest from the source data using osmconvert and save this to the study region output folder.  Features for this region were then imported to the PostGIS database using osm2pgsql, and with geometries updated to match the project coordinate reference system.'.format(
            **region_config,
        ),
    ),
    ('h2', 'Pedestrian network set up'),
    ('blurb', '{network[description]}'.format(**region_config)),
    ('image', network_plot),
    ('h2', 'Population data set up'),
    (
        'blurb',
        """Population distribution data for {name} were sourced from [{population[name]} ({population[year_published]})]({population[source_url]}) for a target year of {population[year_target]}.  This data was used under {population[licence]} terms.   The configured population data grid had a resolution of {population[resolution]} m, with this grid being used for summarising the spatial distribution of indicator results prior to aggregation to larger scales.""".format(
            **region_config,
        ),
    ),
    ('image', population_grid),
    ('h2', 'Configuration parameters'),
    ('blurb', yaml.dump(region_config)),
]


# PDF layout set up


class PDF(FPDF):
    def header(self):
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
        # Position cursor at 1.5 cm from bottom:
        self.set_y(-15)
        # Setting font: helvetica italic 8
        self.set_font('helvetica', 'I', 8)
        # Printing page number:
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')


# def render_toc(pdf, outline):
#         pdf.y += 50
#         pdf.set_font("Helvetica", size=16)
#         pdf.set_draw_color(50)  # very dark grey
#         pdf.set_line_width(.5)
#         with pdf.table(borders_layout="NONE",markdown=True) as table:
#             for section in outline:
#                 row = table.row()
#                 link = pdf.add_link()
#                 pdf.set_link(link, page=section.page_number)
#                 row.cell(f"[{section.name}]({link})")
#                 row.cell(f"{section.page_number}")

# Instantiation of inherited class
pdf = PDF()
pdf.add_page()
pdf.set_font('Helvetica', size=12)
# pdf.insert_toc_placeholder(render_toc)
# pdf.write_html("<toc></toc>")
for element in elements:
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

capture = pdf.output('test.pdf')
