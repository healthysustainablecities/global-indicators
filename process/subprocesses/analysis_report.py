from datetime import datetime

from fpdf import FPDF
from subprocesses._project_setup import (
    __version__,
    authors,
    codename,
    region_config,
    study_buffer,
)


def region_boundary_blurb(
    name, study_region_boundary, urban_region, urban_query,
):
    """Generate a blurb for the study region boundary."""
    if study_region_boundary == 'urban_query':
        blurb_1 = f"The study region boundary was defined using an SQL query that was run using ogr2ogr to import the corresponding features from {urban_region['name']} to the database."
    else:
        blurb_1 = f"The study region boundary was defined and imported to the database using ogr2ogr with data sourced from {study_region_boundary['source']} published in  {study_region_boundary['publication_date']} and retrievable from {study_region_boundary['url']}."
    if study_region_boundary['ghsl_urban_intersection']:
        blurb_2 += f""" This study region boundary was taken to represent the {name} urban region."""
    else:
        blurb_2 = f""" The urban portion of {name} was identified using the intersection of the study region boundary and urban regions sourced from {urban_region['name']} published as {urban_region['citation']}."""
    if urban_query:
        blurb_3 = f""" The SQL query used to extract urban areas from {urban_region['name']} was: {urban_query}."""
    else:
        blurb_3 = ''
    return blurb_1 + blurb_2 + blurb_3


region_config['__version__'] = __version__
region_config['authors'] = authors
region_config['codename'] = codename
region_config['OpenStreetMap'][
    'note'
] = f".  The following note was stored: <<{region_config['OpenStreetMap']['note'] if region_config['OpenStreetMap']['note'] is not None else ''}>>"
region_config['OpenStreetMap']['publication_date'] = datetime.strptime(
    str(region_config['OpenStreetMap']['publication_date']), '%Y%m%d',
).strftime('%d %B %Y')
region_config['study_buffer'] = study_buffer
region_config['study_region_blurb'] = region_boundary_blurb(
    region_config['name'],
    region_config['study_region_boundary'],
    region_config['urban_region'],
    region_config['urban_query'],
)

blurbs = {
    'Background': 'An analysis was conducted using the Global Healthy and Sustainable City Indicators (global-indicators) software (https://global-healthy-liveable-cities.github.io/).  This software supports  analysis and reporting on health related spatial indicators of urban design and transport features for diverse regions of interest using open and/or custom data.  Spatial and network analyses are conducted according to user configuration for sample points generated along a derived pedestrian network. Results are aggregated to a grid with resolution corresponding to the input population data used, as well as overall summaries for the city or region of interest. It outputs data, documentation, maps, figures and reports in multiple languages to support further analysis as well as publication and sharing of findings.  The software is designed to support the 1000 Cities Challenge of the Global Observatory of Healthy and Sustainable Cities (https://healthysustainablecities.org).'.format(
        **region_config,
    ),
    'Software details': 'The analysis was conducted using version {__version__} of the global-indicators code, retrivable from https://github.com/global-healthy-liveable-cities/global-indicators/releases/tag/v{__version__} along with the corresponding Docker image (globalhealthyliveablecities/global-indicators:v{__version__}) that includes a suite of open source software used to run the analysis, including Linux, Python, OSMnx, NetworkX, GeoPandas, Pandas, Matplotlib, Shapely, Fiona, Rasterio, GDAL, Pyproj, and others (see the text files in the docker folder: Dockerfile, environment.yml and requirements.txt for full details).  Our software is officialy sponsored by Docker as an open-source software project.  In addition the pgRouting Docker image was also retrieved, to run a Postgres SQL database with the PostGIS and pgRouting extensions, supporting data management and advanced spatial and network analyses.  A shell script retrieved and launched the Docker images with these dependencies as containers, with a command prompt guiding users through the three step analysis process: configuration, analysis and generation of resources.'.format(
        **region_config,
    ),
    'Configuration': 'Analysis was configured and run for {name} ({country}, {continent}) with a target time point of {year} by {authors}.  The spatial coordinate reference system used was {crs[name]} ({crs[standard]}:{crs[srid]}).  Data were retrieved and stored, with corresponding metadata defined in text configuration files along with the parameters used to configure the analysis (see `parameters.yml`).'.format(
        **region_config,
    ),
    'Database set up': """An SQL database was created ({db}) with the PostGIS and pgRouting extensions, that could be connected to within the Docker container:
psql -U postgres -h gateway.docker.internal -p 5433 -d "example_es_las_palmas_2023
The database could also be connected to by external application (e.g. for creation of maps in QGIS) by specifying the host as 'localhost' on port 5433.""".format(
        **region_config,
    ),
    'Study region set up': 'The study region folder was created using the configured codename ({codename}), and data were imported to construct the study region boundaries. {study_region_blurb} \nTo ensure the environmental contexts of locations near the edge of the study region boundary were fairly represented a {study_buffer} m buffer was applied to be used when extracting features from datasets to ensure that nearby features and amenities considered when constructing indicators were accounted for, even if located outside the urban region itself.'.format(
        **region_config,
    ),
    'OpenStreetMap data set up': 'OpenStreetMap data published {OpenStreetMap[publication_date]} were sourced from {OpenStreetMap[source]} ({OpenStreetMap[citation]}){OpenStreetMap[note]}.'.format(
        **region_config,
    ),
}


class PDF(FPDF):
    def header(self):
        # Rendering logo:
        self.image(
            'configuration/assets/GOHSC - white logo transparent.svg',
            10,
            8,
            33,
        )
        # Setting font: helvetica bold 15
        self.set_font('helvetica', 'B', 15)
        # Moving cursor to the right:
        self.cell(80)
        # Printing title:
        self.cell(
            txt='{name}, {country}'.format(**region_config),
            border=0,
            align='R',
        )
        # Performing a line break:
        self.ln(20)

    def footer(self):
        # Position cursor at 1.5 cm from bottom:
        self.set_y(-15)
        # Setting font: helvetica italic 8
        self.set_font('helvetica', 'I', 8)
        # Printing page number:
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')


# Instantiation of inherited class
pdf = PDF()
pdf.add_page()
pdf.set_font('Helvetica', size=12)
pdf.set_margins(19, 19, 19)
for blurb in blurbs:
    pdf.write_html(f'<h2>{blurb}</h2>')
    pdf.ln(5)
    pdf.multi_cell(0, txt=blurbs[blurb])

pdf.output('test.pdf')
