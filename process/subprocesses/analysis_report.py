"""Analysis report subprocess."""

import os
from datetime import datetime

import pandas as pd
import yaml
from fpdf import FPDF
from PIL import ImageFile
from sqlalchemy import create_engine
from subprocesses._utils import study_region_map
from subprocesses.ghsci import df_osm_dest

ImageFile.LOAD_TRUNCATED_IMAGES = True


def compile_analysis_report(engine, region_config, settings):
    """Compile the analysis report for the region."""
    openstreetmap_date = datetime.strptime(
        str(region_config['OpenStreetMap']['publication_date']), '%Y%m%d',
    ).strftime('%d %B %Y')
    openstreetmap_note = f".  The following note was recorded: __{region_config['OpenStreetMap']['note'] if 'note' in region_config['OpenStreetMap'] and region_config['OpenStreetMap']['note'] is not None else ''}__"
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
    study_region_urban_shading = study_region_map(
        engine,
        region_config,
        edgecolor='black',
        basemap='light',
        file_name='study_region_boundary_urban_shading',
    )
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
        additional_attribution=f"""Pedestrian network edges: OpenStreetMap contributors ({openstreetmap_date}), under {region_config['OpenStreetMap']['licence']}; network detail, including nodes and cleaned intersections can be explored using desktop mapping software like QGIS, using a connection to the {region_config['db']} database.""",
    )
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
    destination_plots = {}
    relavent_destinations = [
        'Fresh Food / Market',
        'Convenience',
        'Public transport stop (any)',
    ]
    for dest in [
        x
        for x in df_osm_dest['dest_full_name'].unique()
        if x in relavent_destinations
    ]:
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
            additional_attribution=f"""{dest} counts: OpenStreetMap contributors ({openstreetmap_date}), under {region_config['OpenStreetMap']['licence']}.""",
        )
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
    # # get input configuration
    # with open(f'home/ghsci/process/configuration/regions/{region_config["codename"]}.yml', 'r') as file:
    #     region_config['input_region_config'] = file.read()
    # with open(f'home/ghsci/process/configuration/config.yml', 'r') as file:
    #     region_config['input_project_config'] = file.read()

    # prepare report elements
    elements = [
        (
            'blurb',
            f'Analysis conducted by {region_config["authors"]}\n{region_config["date_hhmm"].replace("_"," ")}',
        ),
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
            'OpenStreetMap data published {openstreetmap_date} were sourced from [{OpenStreetMap[source]} ({openstreetmap_date})]({OpenStreetMap[url]}){openstreetmap_note}  The buffered urban study region boundary was used to extract the region of interest from the source data using osmconvert and save this to the study region output folder.  Features for this region were then imported to the PostGIS database using osm2pgsql, and with geometries updated to match the project coordinate reference system.'.format(
                openstreetmap_date=openstreetmap_date,
                openstreetmap_note=openstreetmap_note,
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
            """Population distribution data for {name} were sourced from [{population[name]} ({population[year_published]})]({population[source_url]}) for a target year of {population[year_target]}.  This data was used under {population[licence]} terms. The configured population {population_grid_setup}, and was used for summarising the spatial distribution of indicator results prior to aggregation to larger scales. Density estimates for population and clean intersections per square kilometre were calculated for each population area.""".format(
                **region_config,
            ),
        ),
        ('image', population_grid),
        ('h2', 'Configuration parameters'),
        ('blurb', yaml.dump(region_config['parameters'])),
    ]
    region_config['elements'] = elements
    return region_config


# PDF layout set up
class PDF_Analysis_Report(FPDF):
    """PDF report class for analysis report."""

    def __init__(self, region_config, settings, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self.region_config = region_config
        self.settings = settings
        self.db = region_config['db']
        self.db_host = region_config['parameters']['project']['sql']['db_host']
        self.db_user = region_config['parameters']['project']['sql']['db_user']
        self.db_pwd = region_config['parameters']['project']['sql']['db_pwd']

    def get_engine(self):
        """Get database engine."""
        engine = create_engine(
            f'postgresql://{self.db_user}:{self.db_pwd}@{self.db_host}/{self.db}',
            future=True,
        )
        return engine

    def header(self):
        """Header of the report."""
        self.set_margins(19, 20, 19)
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
            with self.local_context(text_color=(89, 39, 226)):
                self.cell(38)
                self.write_html(
                    '<br><br><section><h1><font color="#5927E2"><b>{name}, {country}</b></font></h1></section>'.format(
                        **self.region_config,
                    ),
                )
                self.write_html(
                    '<font color="#CCCCCC"><b>Analysis report</b></font><br><br>'.format(
                        **self.region_config,
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
            with self.local_context(text_color=(89, 39, 226)):
                self.cell(38)
                self.multi_cell(
                    w=134,
                    txt='{name}, {country}'.format(**self.region_config),
                    border=0,
                    align='R',
                )
        self.set_margins(19, 32, 19)

    def footer(self):
        """Page footer function."""
        # Position cursor at 1.5 cm from bottom:
        self.set_y(-15)
        # Setting font: helvetica italic 8
        self.set_font('helvetica', 'I', 8)
        # Printing page number:
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

    def generate_analysis_report(self):
        """Generate analysis report."""
        engine = self.get_engine()
        region_config = compile_analysis_report(
            engine, self.region_config, self.settings,
        )
        self.add_page()
        self.set_font('Helvetica', size=12)
        # pdf.insert_toc_placeholder(render_toc)
        # pdf.write_html("<toc></toc>")
        for element in region_config['elements']:
            if element[0].startswith('h') and element[0][1].isdigit():
                capture = self.write_html(
                    f'<section><{element[0]}><font color="#5927E2">{element[1]}</font></{element[0]}><br></section>',
                )
            elif element[0] == 'newpage':
                capture = self.add_page()
            elif element[0] == 'blurb':
                capture = self.multi_cell(0, txt=element[1], markdown=True)
                capture = self.ln(2)
            elif element[0] == 'image':
                capture = self.ln(2)
                capture = self.image(element[1], x=30, w=150)
                capture = self.ln(2)
            elif element[0] == 'table':
                capture = self.ln(4)
                # assuming that element[1]['data'] is a pandas dataframe
                # and that element[1]['description'] describes it
                capture = self.multi_cell(
                    0, txt=f"__{element[1]['description']}__", markdown=True,
                )
                capture = self.ln(2)
                if 'align' in element[1]:
                    align = element[1]['align']
                else:
                    align = 'CENTER'
                with self.table(
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
        report_file = f'{self.region_config["region_dir"]}/analysis_report_{self.region_config["date_hhmm"]}.pdf'
        capture = self.output(report_file)
        print(f'  {os.path.basename(report_file)}')
