"""
Tests for the Global Healthy and Sustainable City Indicator software workflow.

This module may be run from the process directory as follows:

    python -m unittest -v tests/tests.py

For example, from within process directory:

>docker compose -f .test-compose.yml run ghsci
test_global_indicators_shell (tests.tests.tests)
Unix shell script should only have unix-style line endings. ... ok
test_project_setup (tests.tests.tests)
Check if _project_setup.py imported successfully. ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.003s

OK

Successful running of all tests may require running of tests within the global-indicators Docker container, hence the use of a custom .test-compose.yml for this purpose.
"""

import os
import subprocess as sp
import sys
import unittest

try:
    from subprocesses import ghsci

    project_setup = True
except ImportError as e:
    project_setup = f'ghsci.py import error: {e}'

# Right-to-left (Arabic/Persian) report rendering regression tests; the
# imports register the test cases with unittest when this file is run
# directly (as done in continuous integration).
from tests.test_rtl_rendering import (  # noqa: F401
    TestArabicJoining,
    TestBidiOrdering,
    TestFpdfJoiningControlPreservation,
    TestLocaleProfiles,
    TestLTRUnchanged,
    TestMatplotlibComplexTextLayout,
    TestMultilineWrapping,
    TestPDFPageGeneration,
    TestPDFShapingConfiguration,
    TestTemplateLayoutTransformations,
    TestVisualMatplotlibFixture,
    TestZWNJPreservation,
)


class tests(unittest.TestCase):
    """A collection of tests to help ensure functionality."""

    def test_0_0_valid_yaml(self):
        """Check if example configuration file is valid YAML."""
        valid = sp.call(
            """yamllint ./configuration/regions/example_ES_Las_Palmas_2023.yml --strict""",
            shell=True,
        )
        self.assertTrue(valid == 0)

    def test_0_1_identify_invalid_yaml(self):
        """Confirm that invalid YAML are correctly identified to ensure that the previous test is acting as intended."""
        reference = 'example_ES_Las_Palmas_2023'
        incorrect = 'broken_config'
        # create modified version of reference configuration
        with open(f'./configuration/regions/{reference}.yml') as file:
            configuration = file.read()
            configuration = configuration.replace(
                'study_region_boundary:',
                ' study_region_boundary: "this YML is so invalid!',
            )
        with open(f'./configuration/regions/{incorrect}.yml', 'w') as file:
            file.write(configuration)
        invalid = sp.call(
            f"""yamllint ./configuration/regions/{incorrect}.yml --strict""",
            shell=True,
        )
        self.assertTrue(invalid == 1)

    def test_0_2_schema_yaml(self):
        """Check if example configuration file is valid against jsonschema file."""
        import json

        import yaml
        from jsonschema import validate

        # Convert integer keys to strings
        def convert_keys_to_strings(d):
            if isinstance(d, dict):
                return {
                    str(k): convert_keys_to_strings(v) for k, v in d.items()
                }
            elif isinstance(d, list):
                return [convert_keys_to_strings(i) for i in d]
            else:
                return d

        # Ensure dates are parsed as strings for schema validation purposes
        yaml.constructor.SafeConstructor.yaml_constructors[
            'tag:yaml.org,2002:timestamp'
        ] = yaml.constructor.SafeConstructor.yaml_constructors[
            'tag:yaml.org,2002:str'
        ]

        with open(
            './configuration/regions/example_ES_Las_Palmas_2023.yml',
        ) as f:
            example = yaml.safe_load(f)

        example = convert_keys_to_strings(example)

        with open('./configuration/regions/region-json-schema.json') as f:
            schema = json.load(f)

        valid_example_configuration = validate(instance=example, schema=schema)
        self.assertTrue(valid_example_configuration is None)

    def test_0_3_configured_resolution(self):
        """Configured population resolutions are read as metric cell sizes."""
        from subprocesses.ghsci import _configured_resolution

        # resolutions in metres, as recorded for raster population grids
        for resolution, expected in [
            ('100m', (100.0, 100.0)),
            ('100 m', (100.0, 100.0)),
            ('1000m', (1000.0, 1000.0)),
            (100, (100.0, 100.0)),
            (250.0, (250.0, 250.0)),
        ]:
            with self.subTest(resolution=resolution):
                self.assertEqual(_configured_resolution(resolution), expected)
        # values which do not describe a cell size in metres; these fall
        # back to preserving the pixel count of the source raster
        for resolution in [
            None,
            '9 arcsec',
            '30 arcsec',
            '3ss',
            'AGEB',
            'SA1',
            '',
            '0m',
            '-100m',
        ]:
            with self.subTest(resolution=resolution):
                self.assertIsNone(_configured_resolution(resolution))

    def test_0_4_reproject_raster_resolution(self):
        """Reprojection conserves both the cell size and the value total."""
        import tempfile

        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        from subprocesses._utils import reproject_raster

        # a 100 m cell size population grid in the Mollweide projection
        # used by the Global Human Settlement Layer population grids
        cell_size = 100
        values = np.arange(1, 401, dtype='float32').reshape(20, 20)
        profile = {
            'driver': 'GTiff',
            'dtype': 'float32',
            'count': 1,
            'width': values.shape[1],
            'height': values.shape[0],
            'crs': 'ESRI:54009',
            'transform': from_origin(-1000000, 4000000, cell_size, cell_size),
        }
        # REGCAN95 / LAEA Europe, as used by the example study region
        new_crs = 'EPSG:4083'
        with tempfile.TemporaryDirectory() as directory:
            source = f'{directory}/source.tif'
            with rasterio.open(source, 'w', **profile) as raster:
                raster.write(values, 1)
            outputs = {}
            for label, resolution in [
                ('specified', (cell_size, cell_size)),
                ('default', None),
            ]:
                outputs[label] = f'{directory}/{label}.tif'
                reproject_raster(
                    inpath=source,
                    outpath=outputs[label],
                    new_crs=new_crs,
                    resolution=resolution,
                )
            results = {}
            for label, path in outputs.items():
                with rasterio.open(path) as raster:
                    results[label] = {
                        'cell_size': (
                            abs(raster.transform.a),
                            abs(raster.transform.e),
                        ),
                        'total': float(np.nansum(raster.read(1))),
                    }
        # the configured cell size is retained, where specified
        self.assertEqual(
            results['specified']['cell_size'],
            (cell_size, cell_size),
        )
        # otherwise, cells inflate to preserve the source pixel count
        self.assertGreater(results['default']['cell_size'][0], cell_size)
        # summing values on reprojection conserves the total; this is
        # exact for the configured cell size, while the larger default
        # cells lose a fraction of the total at the raster edges
        total = float(values.sum())
        self.assertAlmostEqual(results['specified']['total'], total, places=1)
        self.assertLess(abs(results['default']['total'] - total) / total, 0.01)

    def test_0_5_custom_aggregation_keep_columns(self):
        """Retained custom aggregation columns are unambiguously qualified."""
        from subprocesses._12_aggregation import qualify_keep_columns

        # column names are lower cased when boundary data is imported
        meshblock_columns = {
            x: x
            for x in [
                'mb_code21',
                'mb_cat21',
                'sal_name21',
                'dwelling',
                'person',
                'geom',
            ]
        }
        suburb_columns = {x: x for x in ['sal_name21', 'geom']}
        # retained columns are qualified as belonging to the boundaries,
        # regardless of the case in which they were configured
        self.assertEqual(
            qualify_keep_columns(
                'MB_CAT21, SAL_NAME21, Dwelling, Person',
                'MB_CODE21',
                meshblock_columns,
            ),
            'b."mb_cat21", b."sal_name21", b."dwelling", b."person",',
        )
        # a retained column matching the identifier is omitted, as the
        # identifier is already selected as b.{id}; were it not, the
        # unqualified reference would be ambiguous with the same column
        # retained by the aggregation being summarised (as occurs when
        # suburbs summarise mesh blocks which retained the suburb name)
        for id, keep_columns in [
            ('SAL_NAME21', 'SAL_NAME21'),
            ('SAL_NAME21', 'sal_name21'),
            ('sal_name21', 'SAL_NAME21'),
        ]:
            with self.subTest(id=id, keep_columns=keep_columns):
                self.assertEqual(
                    qualify_keep_columns(
                        keep_columns,
                        id,
                        suburb_columns,
                    ),
                    '',
                )
        # unconfigured or empty specifications retain no columns
        for keep_columns in [None, '', ' ', ',', ', ,']:
            with self.subTest(keep_columns=keep_columns):
                self.assertEqual(
                    qualify_keep_columns(
                        keep_columns,
                        'MB_CODE21',
                        meshblock_columns,
                    ),
                    '',
                )
        # a column which is retained is always qualified, whether or not it
        # could be matched with a column of the boundaries
        fragment = qualify_keep_columns(
            'SAL_NAME21, Dwelling',
            'MB_CODE21',
            {},
        )
        self.assertEqual(fragment, 'b."sal_name21", b."dwelling",')
        # where the boundary column is not lower case, it is referenced as
        # it exists, so that quoting does not make the match case sensitive
        self.assertEqual(
            qualify_keep_columns(
                'sal_name21',
                'MB_CODE21',
                {'sal_name21': 'SAL_NAME21'},
            ),
            'b."SAL_NAME21",',
        )
        # the fragment is comma terminated for interpolation before the
        # geometry in both the select list and the group by clause
        group_by = f'GROUP BY b.MB_CODE21, {fragment} b.geom'
        self.assertEqual(
            group_by,
            'GROUP BY b.MB_CODE21, b."sal_name21", b."dwelling", b.geom',
        )

    def test_0_6_custom_aggregation_clip(self):
        """Custom aggregation boundaries are clipped to the analysed area."""
        from subprocesses._12_aggregation import clipped_boundary_sql

        # by default, boundaries are restricted to the urban study region,
        # which defines the area actually analysed
        prelude, geometry, source = clipped_boundary_sql(
            True,
            'agg_suburbs',
            7856,
        )
        self.assertEqual(geometry, 'b.analysed_geom')
        self.assertEqual(source, 'analysed b')
        self.assertIn('urban_study_region', prelude)
        self.assertIn('ST_Intersection(b.geom, u.geom)', prelude)
        self.assertIn('"agg_suburbs" b', prelude)
        # the clipped geometry is cast to the study region's own projection,
        # so that areas derived from it are in metres
        self.assertIn('geometry(MultiPolygon, 7856)', prelude)
        # boundaries meeting the study region only along an edge clip to an
        # empty polygon; they are dropped rather than divided by an area of
        # zero when deriving densities
        self.assertIn('ST_Area(analysed_geom) > 0', prelude)

        # with clipping disabled the boundaries are summarised and reported
        # as configured, and no common table expression is required
        prelude, geometry, source = clipped_boundary_sql(
            False,
            'agg_suburbs',
            7856,
        )
        self.assertEqual(prelude, '')
        self.assertEqual(geometry, 'b.geom')
        self.assertEqual(source, '"agg_suburbs" b')

        # the geometry expression is what the area, the densities derived
        # from it, and the reported geometry are all built from, so the two
        # settings must not be confusable
        self.assertNotEqual(
            clipped_boundary_sql(True, 'agg_suburbs', 7856)[1],
            clipped_boundary_sql(False, 'agg_suburbs', 7856)[1],
        )

    def test_0_7_custom_aggregation_data_load(self):
        """Custom aggregation data sources are read as configured."""
        import os
        import tempfile
        import zipfile
        from unittest import mock

        import geopandas as gpd
        from subprocesses import _12_aggregation, ghsci

        data = f'{ghsci.folder_path}/process/data'
        # the boundary distributed with the example study region
        boundary = (
            'region_boundaries/Example/Las Palmas de Gran Canaria'
            ' - Centro Nacional de Información Geográfica'
            ' - WGS84 - EPSG4326.geojson'
        )
        self.assertTrue(
            os.path.isfile(f'{data}/{boundary}'),
            f'The example boundary is expected at {boundary}',
        )

        class StubRegion:
            def __init__(self, source):
                self.config = {
                    'custom_aggregations': {'example': {'data': source}},
                    'db_host': 'host',
                    'db_port': 5433,
                    'db': 'db',
                    'db_user': 'user',
                    'db_pwd': 'pwd',
                    'crs_srid': 'EPSG:32628',
                }

        def load(source, returncode=0):
            """Return the table and the ogr2ogr command that would be run."""
            with mock.patch.object(
                _12_aggregation.sp,
                'call',
                return_value=returncode,
            ) as call:
                table = _12_aggregation.custom_data_load(
                    StubRegion(source),
                    'example',
                )
            return table, call.call_args[0][0]

        # a path is used as configured, relative to the project data directory
        table, command = load(boundary)
        self.assertEqual(table, 'agg_example')
        self.assertIn(f'"{data}/{boundary}"', command)

        # an attribute query is not part of the path: it has to be separated
        # from it, or the resulting path cannot be opened
        query = '-where "ESTADO = \'Vigente\'"'
        table, command = load(f'{boundary} {query}')
        self.assertIn(f'"{data}/{boundary}"', command)
        self.assertIn(query, command)
        # the query is no longer part of the quoted source path
        self.assertNotIn(f'{boundary} -where', command)

        # a layer may be selected from a geopackage, with or without a query
        for source, expected in [
            ('region_boundaries/example.gpkg:boundary', 'boundary'),
            (
                'region_boundaries/example.gpkg:boundary -where "pop > 0"',
                'boundary -where "pop > 0"',
            ),
        ]:
            with self.subTest(source=source):
                table, command = load(source)
                self.assertIn(
                    f'"{data}/region_boundaries/example.gpkg"',
                    command,
                )
                self.assertTrue(command.rstrip().endswith(expected))
                self.assertNotIn('/vsizip/', command)

        # zipped data is read in place through GDAL's virtual file system,
        # rather than having to be unpacked first.  The example boundary is
        # written out as a zipped shapefile, as the ABS and other agencies
        # distribute their boundaries, so that the path this builds can be
        # confirmed to open rather than merely to look correct.
        with tempfile.TemporaryDirectory(dir=data) as tmp:
            stem = 'example_boundary'
            gdf = gpd.read_file(f'{data}/{boundary}')
            gdf.to_file(f'{tmp}/{stem}.shp', driver='ESRI Shapefile')
            archive = f'{tmp}/{stem}.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
                for name in sorted(os.listdir(tmp)):
                    if name.startswith(f'{stem}.') and not name.endswith(
                        '.zip',
                    ):
                        z.write(f'{tmp}/{name}', name)
            relative = f'{os.path.basename(tmp)}/{stem}.zip'
            table, command = load(relative)
            vsizip = f'/vsizip//{data}/{relative}'
            self.assertIn(f'"{vsizip}"', command)
            # the constructed path is one GDAL can actually read
            self.assertEqual(len(gpd.read_file(vsizip)), len(gdf))

        # any non-zero return code is a failure; a code other than 1 must not
        # be mistaken for success, or the missing table surfaces later as an
        # error pointing at the configuration rather than at the data
        for returncode in [1, 2, 127]:
            with self.subTest(returncode=returncode):
                with self.assertRaises(SystemExit):
                    load(boundary, returncode)

    def test_0_8_data_key_synonym(self):
        """The path key is 'data', with 'data_dir' accepted as a synonym."""
        from subprocesses import ghsci

        cases = {
            'data only': {'data': 'a/path', 'citation': 'c'},
            'data_dir only': {'data_dir': 'a/path', 'citation': 'c'},
            'both, agreeing': {
                'data': 'a/path',
                'data_dir': 'a/path',
                'citation': 'c',
            },
        }
        for name, configured in cases.items():
            with self.subTest(configured=name):
                resolved = ghsci._normalise_data_key(
                    dict(configured),
                    'test_region',
                    'population',
                )
                # whichever key was configured, only 'data' is passed on
                self.assertEqual(resolved['data'], 'a/path')
                self.assertNotIn('data_dir', resolved)

        # a block configuring neither is left alone, to be reported as a
        # missing 'data' entry by the check that follows in the caller
        self.assertNotIn(
            'data',
            ghsci._normalise_data_key({'citation': 'c'}, 'r', 'population'),
        )

        # two different paths cannot be silently reconciled
        with self.assertRaises(SystemExit):
            ghsci._normalise_data_key(
                {'data': 'one', 'data_dir': 'another'},
                'test_region',
                'population',
            )

    def test_0_9_region_configuration_discovery(self):
        """Configuration is found in the project folder and beside data."""
        from subprocesses import ghsci

        configs = ghsci.get_region_configs()
        names = ghsci.get_region_names()
        self.assertEqual(names, sorted(set(names)))
        self.assertEqual(sorted(configs), names)

        # every configuration file in the project regions folder is offered
        project = {
            os.path.splitext(x)[0]
            for x in os.listdir(f'{ghsci.config_path}/regions')
            if x.endswith('.yml')
        }
        self.assertTrue(project.issubset(set(names)))

        # each codename resolves to a file that exists, and a codename that
        # is not configured resolves to where it would be created
        for codename in names:
            with self.subTest(codename=codename):
                path = ghsci.get_region_config_path(codename)
                self.assertTrue(os.path.isfile(path), path)
        self.assertEqual(
            ghsci.get_region_config_path('a_codename_that_is_not_configured'),
            f'{ghsci.config_path}/regions/'
            'a_codename_that_is_not_configured.yml',
        )

        # a codename defined more than once is ambiguous: it would give two
        # study regions the same output folder and database
        from unittest import mock

        duplicated = {
            'duplicated_codename': [
                f'{ghsci.config_path}/regions/duplicated_codename.yml',
                f'{ghsci.data_path}/x/configuration/duplicated_codename.yml',
            ],
        }
        with mock.patch.object(
            ghsci,
            'get_region_configs',
            return_value=duplicated,
        ):
            with self.assertRaises(SystemExit):
                ghsci.get_region_config_path('duplicated_codename')

    def test_0_10_gtfs_folder_resolution(self):
        """GTFS folders resolve relative to the project data directory."""
        import tempfile
        from unittest import mock

        from subprocesses import ghsci

        with tempfile.TemporaryDirectory() as root:
            data = f'{root}/process/data'
            colocated = 'examples/ES_Las_Palmas_2025/gtfs'
            os.makedirs(f'{data}/{colocated}')
            os.makedirs(f'{data}/transit_feeds/Example')
            with mock.patch.object(ghsci, 'folder_path', root):
                # configured beside the study region's other data
                self.assertEqual(
                    ghsci.get_gtfs_folder_path(colocated),
                    f'{data}/{colocated}',
                )
                # configured under the shared GTFS root, as previously
                self.assertEqual(
                    ghsci.get_gtfs_folder_path('Example'),
                    f'{data}/transit_feeds/Example',
                )
                # where neither exists, the project data directory location
                # is reported, so that advice names the expected place
                self.assertEqual(
                    ghsci.get_gtfs_folder_path('absent'),
                    f'{data}/absent',
                )

    def test_1_global_indicators_shell(self):
        """Unix shell script should only have unix-style line endings."""
        counts = calculate_line_endings('../global-indicators.sh')
        lf = counts.pop(b'\n')
        self.assertTrue(sum(counts.values()) == 0 and lf > 0)

    def test_2_project_setup(self):
        """Check if _project_setup.py imported successfully."""
        self.assertTrue(project_setup)

    def test_3_load_example_region(self):
        """Load example region."""
        r = ghsci.example()

    def test_4_create_db(self):
        """Load example region."""
        codename = 'example_ES_Las_Palmas_2023'
        r = ghsci.Region(codename)
        r._create_database()

    def test_5_example_analysis(self):
        """Analyse example region."""
        r = ghsci.example()
        r.analysis()

    def test_6_example_generate(self):
        """Generate resources for example region."""
        r = ghsci.example()
        r.generate()

    def test_7_sensitivity(self):
        """Test sensitivity analysis of urban intersection parameter."""
        reference = 'example_ES_Las_Palmas_2023'
        comparison = 'ES_Las_Palmas_2023_test_not_urbanx'
        # create modified version of reference configuration
        with open(f'./configuration/regions/{reference}.yml') as file:
            configuration = file.read()
            configuration = configuration.replace(
                'urban_intersection: true',
                'urban_intersection: false',
            )
        with open(f'./configuration/regions/{comparison}.yml', 'w') as file:
            file.write(configuration)
        r_comparison = ghsci.Region(comparison)
        # create output folder for comparison region
        if not os.path.exists(
            f'{ghsci.folder_path}/process/data/_study_region_outputs',
        ):
            os.makedirs(
                f'{ghsci.folder_path}/process/data/_study_region_outputs',
            )
        if not os.path.exists(r_comparison.config['region_dir']):
            os.makedirs(r_comparison.config['region_dir'])
        with open(f'./configuration/regions/{comparison}.yml', 'w') as file:
            file.write(configuration)
        r = ghsci.Region(reference)
        df = r.get_df('indicators_region')
        df[df.columns[(df.dtypes == 'float64').values]] = df[
            df.columns[(df.dtypes == 'float64').values]
        ].astype(int)
        df.to_csv(
            f"{r_comparison.config['region_dir']}/{r_comparison.codename}_indicators_region.csv",
            index=False,
        )
        r.compare(comparison)

    def test_8_example_generate_report_in_another_language(self):
        """Generate resources for example region."""
        r = ghsci.example()
        r.generate_report('Spanish - Latin America')

    def test_9_compile_poi_destinations(self):
        """compile_poi_destinations uses custom spatial data for a dest_name.

        Creates a synthetic GeoJSON with three bus-stop points, configures a
        mock Region whose points_of_interest references that file with
        replace: true, and asserts that:

        - r.ogr_to_db is called with the correct source path and staging layer
        - Destinations are inserted via ST_Centroid from the staging layer
        - A count query is scoped to the dest_name
        - dest_type receives an ON CONFLICT upsert (works for both replace modes)
        - dest_name_full and domain are resolved from ghsci.df_osm_dest for
          known dest_name keys (e.g. 'pt_any')
        - The temporary staging table is dropped after use
        """
        import json
        import os
        import tempfile
        from unittest.mock import MagicMock

        # _05_compile_destinations uses bare `import ghsci`; alias the module
        # already loaded so it is not re-initialised from disk.
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        from _05_compile_destinations import compile_poi_destinations

        # Three synthetic bus-stop points near Las Palmas de Gran Canaria
        geojson = {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [-15.41, 28.11],
                    },
                    'properties': {'name': 'Stop A'},
                },
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [-15.42, 28.12],
                    },
                    'properties': {'name': 'Stop B'},
                },
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [-15.43, 28.13],
                    },
                    'properties': {'name': 'Stop C'},
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.geojson',
            delete=False,
        ) as f:
            json.dump(geojson, f)
            tmp_path = f.name

        try:
            # --- Build mock Region -----------------------------------------
            r = MagicMock()
            r.config = {
                'points_of_interest': {
                    'pt_any': {
                        'data': tmp_path,
                        'source': 'Test transit stops',
                        'replace': True,
                    },
                },
            }

            # Wire up engine context manager; count query returns 3
            mock_result = MagicMock()
            mock_result.first.return_value = [3]
            mock_connection = MagicMock()
            mock_connection.execute.return_value = mock_result
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_connection)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            r.engine.begin.return_value = mock_ctx

            # --- Call function under test -----------------------------------
            compile_poi_destinations(r)

            # ogr_to_db called once with the file path and staging layer name
            r.ogr_to_db.assert_called_once_with(
                source=tmp_path,
                layer='_poi_pt_any',
            )

            # Collect all SQL strings passed to connection.execute
            # SQLAlchemy TextClause.__str__() returns the raw SQL string
            sql_calls = [
                str(call.args[0])
                for call in mock_connection.execute.call_args_list
            ]

            # INSERT into destinations from the staging layer via ST_Centroid
            self.assertTrue(
                any(
                    '_poi_pt_any' in s and 'ST_Centroid' in s
                    for s in sql_calls
                ),
                'Expected INSERT with ST_Centroid from _poi_pt_any',
            )
            # Count query scoped to the dest_name
            self.assertTrue(
                any("dest_name = 'pt_any'" in s for s in sql_calls),
                'Expected count query scoped to pt_any',
            )
            # Upsert into dest_type with ON CONFLICT so pooling also works
            self.assertTrue(
                any(
                    'dest_type' in s and 'pt_any' in s and 'ON CONFLICT' in s
                    for s in sql_calls
                ),
                'Expected ON CONFLICT upsert into dest_type for pt_any',
            )
            # dest_name_full resolved from df_osm_dest for the known key
            osm_row = ghsci.df_osm_dest[
                ghsci.df_osm_dest['dest_name'] == 'pt_any'
            ].iloc[0]
            expected_full_name = osm_row['dest_full_name']
            self.assertTrue(
                any(expected_full_name in s for s in sql_calls),
                f'Expected dest_name_full "{expected_full_name}" from '
                'df_osm_dest in generated SQL',
            )
            # Staging table dropped after use
            self.assertTrue(
                any(
                    'DROP TABLE' in s and '_poi_pt_any' in s for s in sql_calls
                ),
                'Expected DROP TABLE for _poi_pt_any staging table',
            )
        finally:
            os.unlink(tmp_path)


def calculate_line_endings(path):
    """
    Tally line endings of different types, returning dictionary of counts.

    Based on code posted at https://stackoverflow.com/questions/29695861/get-newline-stats-for-a-text-file-in-python.
    """
    # order matters!
    endings = [
        b'\r\n',
        b'\n\r',
        b'\n',
        b'\r',
    ]
    counts = dict.fromkeys(endings, 0)

    with open(path, 'rb') as fp:
        for line in fp:
            for x in endings:
                if line.endswith(x):
                    counts[x] += 1
                    break
    return counts


if __name__ == '__main__':
    unittest.main(failfast=True)
