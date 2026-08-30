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
            """yamllint ./data/examples/ES_Las_Palmas_2025/configuration/ES_Las_Palmas_2025.yml --strict""",
            shell=True,
        )
        self.assertTrue(valid == 0)

    def test_0_1_identify_invalid_yaml(self):
        """Confirm that invalid YAML are correctly identified to ensure that the previous test is acting as intended."""
        reference = 'ES_Las_Palmas_2025'
        incorrect = 'broken_config'
        # create modified version of reference configuration
        with open(ghsci.get_region_config_path(reference)) as file:
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
            './data/examples/ES_Las_Palmas_2025/configuration/ES_Las_Palmas_2025.yml',
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
        # the boundary distributed with the example study region, which now
        # lives alongside the rest of that region's data
        boundary = (
            'examples/ES_Las_Palmas_2025/boundaries/'
            'las_palmas_municipality.geojson'
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

    def test_0_11_retired_codename(self):
        """A retired codename is answered with advice, not a prompt."""
        from subprocesses import ghsci

        for codename in [
            'example_ES_Las_Palmas_2023',
            'example_ES_Las_Palmas_2023-ee',
        ]:
            with self.subTest(codename=codename):
                self.assertIn(codename, ghsci.RETIRED_CODENAMES)
                advice = ghsci.RETIRED_CODENAMES[codename]
                self.assertIn(ghsci.example_codename, advice)
                yaml = ghsci.get_region_config_path(codename)
                self.assertIn(
                    ghsci.example_codename,
                    ghsci.retired_codename_notice(codename, yaml),
                )
                r = ghsci.Region(codename)
                if os.path.isfile(yaml):
                    # a retired codename whose configuration is still present
                    # is still loaded, so that results analysed under it may
                    # be revisited or compared
                    self.assertIsNotNone(r.config)
                else:
                    # otherwise, no configuration is loaded and the region
                    # reports as such, rather than prompting to initialise a
                    # new study region
                    self.assertIsNone(r.config)
                # a path is always resolved, so that code reporting on a
                # region that could not be loaded can name it
                self.assertTrue(r.yaml.endswith(f'{codename}.yml'))

        # the codename it directs people to is one that actually resolves
        self.assertTrue(
            os.path.isfile(
                ghsci.get_region_config_path(ghsci.example_codename),
            ),
        )

    def test_0_11a_retired_codename_with_configuration(self):
        """A retired codename with a configuration present is loaded."""
        import shutil

        from subprocesses import ghsci

        codename = 'example_ES_Las_Palmas_2023-ee'
        yaml = f'{ghsci.config_path}/regions/{codename}.yml'
        if os.path.isfile(yaml):
            self.skipTest(f'A configuration already exists for {codename}')
        shutil.copyfile(
            ghsci.get_region_config_path(ghsci.example_codename),
            yaml,
        )
        try:
            r = ghsci.Region(codename)
            self.assertIsNotNone(r.config)
            self.assertEqual(r.yaml, yaml)
            self.assertEqual(r.codename, codename)
        finally:
            os.remove(yaml)

    def test_0_11b_compare_reports_regions_that_did_not_load(self):
        """Comparison with a region that did not load is reported clearly."""
        import compare
        from subprocesses import ghsci

        codename = 'example_ES_Las_Palmas_2023-ee'
        if os.path.isfile(ghsci.get_region_config_path(codename)):
            self.skipTest(f'A configuration exists for {codename}')
        with self.assertRaises(ValueError):
            compare.resolve_regions(codename, ghsci.example())

    def test_0_12_reference_data_dictionary(self):
        """The reference catalogue omits analyses not in this release."""
        import data_dictionary as dd

        catalogue = dd.reference_data_dictionary()
        categories = set(catalogue['Category'])
        self.assertTrue(categories, 'the catalogue should not be empty')
        for excluded in dd.REFERENCE_EXCLUDED_CATEGORIES:
            with self.subTest(category=excluded):
                self.assertNotIn(excluded, categories)

        # the describers themselves are intact, so that restoring a
        # category is a matter of removing it from the exclusion set
        category, description = dd.describe_variable(
            'pct_access_500m_fresh_food_market_score',
        )
        self.assertTrue(description)
        self.assertNotIn(category, dd.REFERENCE_EXCLUDED_CATEGORIES)

    def test_0_13_output_variables_resolve(self):
        """Reported output variables all resolve to a description."""
        import data_dictionary as dd
        from subprocesses import ghsci

        variables = (
            ghsci.indicators['output']['city_variables']
            + ghsci.indicators['output']['neighbourhood_variables']
        )
        self.assertTrue(variables, 'output variables should be configured')
        for variable in variables:
            with self.subTest(variable=variable):
                category, description = dd.describe_variable(variable)
                self.assertTrue(description)
                # the app labels its summary and comparison tables with
                # these descriptions; an 'Other fields' fallback means a
                # naming convention has drifted from its describer
                self.assertNotEqual(category, 'Other fields')

    def test_0_21_blue_space_and_open_space_variants(self):
        """Blue space criteria, and the public open space node layer variants."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _06_open_space_areas_setup as osa
        import ghsci

        oss = ghsci.osm_open_space_config({})
        polygon, line = osa.blue_space_criteria(oss)
        # linear water is included as line geometry, which is the whole point:
        # canals and drains are commonly mapped as ways and never reach the
        # polygon table the open space pipeline is built from
        self.assertIn('canal', line)
        self.assertIn('drain', line)
        self.assertIn('waterway', polygon)
        # an exclusion compared against a null tag yields null, not false, so it
        # must be coalesced or every feature lacking the tag is discarded
        for criteria in (polygon, line):
            self.assertIn('NOT COALESCE(', criteria)
            self.assertIn('swimming_pool', criteria)

        # the built-in node layer variants, and the SQL each derives
        variants = osa.public_open_space_variants({})  # empty region config
        self.assertEqual(sorted(variants), ['any', 'large', 'water'])
        self.assertIsNone(variants['any'])
        self.assertEqual(variants['water'], 'a.aos_ha_water > 0')
        sql = osa.public_open_space_variant_query('large', variants['large'])
        self.assertIn('aos_public_large_nodes_30m_line', sql)
        self.assertIn('a.aos_ha_public > 1.5', sql)
        # no criteria means no restriction, not an empty result
        self.assertNotIn(
            'AND ()',
            osa.public_open_space_variant_query(
                'any',
                variants['any'],
            ),
        )
        # a region may add or redefine variants
        configured = osa.public_open_space_variants(
            {
                'areas_of_interest': {
                    'public_open_space_variants': {
                        'near_water': 'a.aos_blue_distance_m <= 100',
                    },
                },
            },
        )
        self.assertEqual(
            configured['near_water'],
            'a.aos_blue_distance_m <= 100',
        )
        self.assertEqual(configured['large'], 'a.aos_ha_public > 1.5')

    def test_0_22_custom_destination_tags(self):
        """Requested source columns are retained as destination tags."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _05_compile_destinations as cd

        self.assertEqual(cd.requested_columns(None), [])
        self.assertEqual(cd.requested_columns('codigo_act'), ['codigo_act'])
        # a comma-separated string, as custom_aggregations uses, or a list
        self.assertEqual(
            cd.requested_columns('a, b ,c'),
            ['a', 'b', 'c'],
        )
        self.assertEqual(cd.requested_columns(['a', ' b']), ['a', 'b'])

    def test_9_custom_open_space_supplement_and_replace(self):
        """Custom areas_of_interest public_open_space supplements or replaces OSM.

        Using mock Regions (no database), asserts that:

        - get_custom_open_space_config resolves the public_open_space data
          entries (single mapping or list of mappings) under the
          areas_of_interest parent key, returning an empty list when the key
          is absent or has no data configured
        - with the default replace: false, supplement_open_space_setup loads
          data to a custom_open_space_areas staging table restricted to the
          buffered urban study region, deletes previously appended custom
          areas (idempotent re-runs), inserts new areas with offset aos_id
          values treated as fully public, and drops the staging table
        - with replace: true, custom_open_space_setup loads data directly as
          the open_space_areas table and derives geom_public/aos_ha_public
        - multiple configured data entries are staged separately then
          combined into the target layer with a minimal common schema
        - ghsci.custom_data_replace raises for mixed replace settings
        """
        from unittest.mock import MagicMock

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _06_open_space_areas_setup as aos_setup

        def mock_region(pos_entry):
            r = MagicMock()
            r.config = {
                'crs_srid': 'EPSG:32615',
                'buffered_urban_study_region': 'urban_study_region_buffered',
                'areas_of_interest': {'public_open_space': pos_entry},
            }
            r.get_bbox_string.return_value = '0.0 0.0 100.0 100.0'
            mock_connection = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_connection)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            r.engine.begin.return_value = mock_ctx
            return r, mock_connection

        # --- config resolution -------------------------------------------
        r, _ = mock_region({'data': 'pos.gpkg', 'replace': False})
        pos = aos_setup.get_custom_open_space_config(r)
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos[0]['data'], 'pos.gpkg')
        for config in [
            {},
            {'areas_of_interest': None},
            {'areas_of_interest': {'public_open_space': {'data': None}}},
            {'areas_of_interest': {'public_open_space': [{'data': None}]}},
        ]:
            empty = MagicMock()
            empty.config = config
            self.assertEqual(
                aos_setup.get_custom_open_space_config(empty),
                [],
            )

        # --- supplement (replace: false, the default) ---------------------
        aos_setup.supplement_open_space_setup(r, pos)
        kwargs = r.ogr_to_db.call_args.kwargs
        self.assertEqual(kwargs['source'], 'pos.gpkg')
        self.assertEqual(kwargs['layer'], 'custom_open_space_areas')
        self.assertIn('-spat 0.0 0.0 100.0 100.0', kwargs['query'])
        self.assertIn('-lco FID=aos_id', kwargs['query'])
        sql_calls = [
            str(call.args[0])
            for call in r.engine.begin.return_value.__enter__.return_value.execute.call_args_list
        ]
        appended = '\n'.join(sql_calls)
        self.assertIn('ST_MakeValid', appended)
        self.assertIn('urban_study_region_buffered', appended)
        self.assertIn(
            'DELETE FROM open_space_areas WHERE custom_aos',
            appended,
        )
        self.assertIn('INSERT INTO open_space_areas', appended)
        self.assertIn('COALESCE(MAX(aos_id), 0)', appended)
        self.assertIn('DROP TABLE custom_open_space_areas', appended)

        # --- replace: true -------------------------------------------------
        r, mock_connection = mock_region({'data': 'pos.gpkg', 'replace': True})
        pos = aos_setup.get_custom_open_space_config(r)
        aos_setup.custom_open_space_setup(r, pos)
        kwargs = r.ogr_to_db.call_args.kwargs
        self.assertEqual(kwargs['layer'], 'open_space_areas')
        sql_calls = '\n'.join(
            str(call.args[0])
            for call in mock_connection.execute.call_args_list
        )
        self.assertIn('SET geom_public = geom', sql_calls)
        self.assertIn(
            'aos_ha_public = ST_Area(geom_public)/10000.0',
            sql_calls,
        )

        # --- multiple pooled data entries ----------------------------------
        r, mock_connection = mock_region(
            [
                {'data': 'parks_a.gpkg', 'source': 'Agency A'},
                {'data': 'parks_b.shp', 'source': 'Agency B'},
            ],
        )
        pos = aos_setup.get_custom_open_space_config(r)
        self.assertEqual(len(pos), 2)
        aos_setup.supplement_open_space_setup(r, pos)
        staging_layers = [
            call.kwargs['layer'] for call in r.ogr_to_db.call_args_list
        ]
        self.assertEqual(
            staging_layers,
            [
                'custom_open_space_areas_src_0',
                'custom_open_space_areas_src_1',
            ],
        )
        sql_calls = '\n'.join(
            str(call.args[0])
            for call in mock_connection.execute.call_args_list
        )
        self.assertIn('UNION ALL', sql_calls)
        self.assertIn('row_number() OVER () AS aos_id', sql_calls)
        self.assertIn(
            'DROP TABLE IF EXISTS custom_open_space_areas_src_0',
            sql_calls,
        )

        # --- mixed replace settings are rejected ----------------------------
        ghsci_module = sys.modules['subprocesses.ghsci']
        with self.assertRaises(ValueError):
            ghsci_module.custom_data_replace(
                [{'data': 'a', 'replace': True}, {'data': 'b'}],
                context='areas_of_interest/public_open_space',
            )
        # normalisation helper: single mapping, list, and empty cases
        self.assertEqual(
            ghsci_module.custom_data_entries({'data': 'a'}),
            [{'data': 'a'}],
        )
        self.assertEqual(
            ghsci_module.custom_data_entries(
                [{'data': 'a'}, {'data': None}, 'not-a-mapping'],
            ),
            [{'data': 'a'}],
        )
        self.assertEqual(ghsci_module.custom_data_entries(None), [])

        # --- category-level form: replace + data_sources --------------------
        entries = ghsci_module.custom_data_entries(
            {
                'replace': True,
                'data_sources': [{'data': 'a'}, {'data': 'b'}],
            },
        )
        self.assertEqual([e['data'] for e in entries], ['a', 'b'])
        # entries inherit the category-level replace setting
        self.assertTrue(
            ghsci_module.custom_data_replace(entries, context='test'),
        )
        # an entry-level setting contradicting the category level is rejected
        with self.assertRaises(ValueError):
            ghsci_module.custom_data_entries(
                {
                    'replace': True,
                    'data_sources': [{'data': 'a', 'replace': False}],
                },
            )

    def test_9_osm_open_space_region_configuration(self):
        """Region-specific overrides of the OpenStreetMap open space definitions.

        The optional areas_of_interest 'osm_open_space' entry lets a region
        override individual definitions from configuration/osm_open_space.yml,
        so locally-relevant open space typologies can be captured without
        pre-processing custom data.  Asserts that:

        - with no region overrides, the resolved configuration matches the
          global definitions with the derived criteria applied (so existing
          study regions are unaffected)
        - a provided key directly replaces that definition's criteria, whether
          given as a bare value or as a mapping containing a 'criteria' key
          (so a whole block may be copied from the global config and edited)
        - definitions that are not provided keep their global defaults
        - an override of a source definition flows into the derived criteria
        - list-valued definitions (os_required) may be overridden with a list
        - an unknown definition name, or a mapping without 'criteria', is
          rejected with an informative error rather than silently ignored
        - the returned configuration is a copy, so overriding for one region
          cannot leak into another analysed in the same session
        """
        ghsci_module = sys.modules['subprocesses.ghsci']
        build = ghsci_module.osm_open_space_config

        def overridden(overrides):
            return build(
                {'areas_of_interest': {'osm_open_space': overrides}},
            )

        # --- no region overrides: global defaults + derived criteria --------
        base = build({})
        self.assertEqual(base['public_space'], build(None)['public_space'])
        self.assertEqual(
            base['public_space'],
            f"{base['public_not_in']['criteria']} AND "
            f"{base['additional_public_criteria']['criteria']}".replace(
                ',)',
                ')',
            ),
        )
        self.assertEqual(
            base['exclusion_criteria'],
            f"{base['os_excluded_keys']['criteria']} OR "
            f"{base['os_excluded_values']['criteria']}",
        )

        # --- a provided key replaces that definition's criteria -------------
        landuse = "'park','cemetery','meadow'"
        for override in (landuse, {'criteria': landuse}):
            new = overridden({'os_landuse': override})
            self.assertEqual(new['os_landuse']['criteria'], landuse)
            # definitions not provided keep their global defaults
            for key in [
                'os_water',
                'os_linear',
                'os_inclusion',
                'os_boundary',
            ]:
                self.assertEqual(
                    base[key]['criteria'],
                    new[key]['criteria'],
                )

        # --- an override flows into the derived criteria --------------------
        public_not_in = """("natural" IS NULL OR "natural" NOT IN ('scrub'))"""
        new = overridden({'public_not_in': public_not_in})
        self.assertEqual(
            new['public_space'],
            f"{public_not_in} AND "
            f"{base['additional_public_criteria']['criteria']}".replace(
                ',)',
                ')',
            ),
        )
        self.assertNotEqual(base['public_space'], new['public_space'])

        # --- list-valued definitions may be overridden with a list ----------
        required = ['landuse', 'natural', 'leisure']
        self.assertEqual(
            overridden({'os_required': required})['os_required']['criteria'],
            required,
        )

        # --- invalid overrides are rejected, not silently ignored -----------
        with self.assertRaises(ValueError):
            overridden({'os_landsue': landuse})  # misspelled definition
        with self.assertRaises(ValueError):
            overridden({'os_landuse': {'explanation': 'no criteria provided'}})

        # --- overrides must not leak between regions ------------------------
        self.assertEqual(
            build({})['os_landuse']['criteria'],
            base['os_landuse']['criteria'],
        )
        self.assertEqual(build({})['public_space'], base['public_space'])

    def test_9_z_custom_data_loads_against_database(self):
        """Custom data configurations resolve and load against a real database.

        The custom destination and areas of interest paths are exercised here
        against the analysed example region rather than against a mock,
        because the defects this guards against were all in code a mock
        cannot reach: a Region method that was never defined, configured data
        paths that were never resolved against the project data directory,
        and a caller's spatial filter being discarded when a geopackage layer
        was selected.  A MagicMock Region supplies whatever attribute is
        asked of it, so all three passed the unit tests while failing for
        anyone who actually configured custom data.

        Asserts that:

        - every documented way of configuring a category (a single data
          entry, a bare list, and a 'data_sources' list) has its path
          resolved against the project data directory, under both
          points_of_interest and areas_of_interest
        - public_open_space_variants, which holds SQL conditions rather than
          data entries, is left alone by that resolution
        - Region.get_bbox_string returns the study region bounds as four
          numbers, as ogr2ogr's '-spat' requires
        - a caller's spatial filter survives selection of a geopackage layer,
          by importing a fixture holding one point inside the study region
          and one outside it, and finding only the one inside
        """
        import json

        from sqlalchemy import text

        reference = 'ES_Las_Palmas_2025'
        codename = 'ES_Las_Palmas_2025_test_custom_data'
        fixture_dir = f'{ghsci.folder_path}/process/data/_test_custom_data'
        config_path = f'./configuration/regions/{codename}.yml'
        os.makedirs(fixture_dir, exist_ok=True)

        # A point within the study region, and one far outside it
        inside = (-15.43, 28.12)
        outside = (0.0, 0.0)
        fixture = f'{fixture_dir}/points.geojson'
        with open(fixture, 'w') as file:
            json.dump(
                {
                    'type': 'FeatureCollection',
                    'features': [
                        {
                            'type': 'Feature',
                            'properties': {'label': label},
                            'geometry': {
                                'type': 'Point',
                                'coordinates': list(xy),
                            },
                        }
                        for label, xy in [
                            ('inside', inside),
                            ('outside', outside),
                        ]
                    ],
                },
                file,
            )

        # --- path resolution, across every documented configuration form ---
        with open(ghsci.get_region_config_path(reference)) as file:
            configuration = file.read()
        configuration += """
points_of_interest:
  single_entry:
    data: _test_custom_data/points.geojson
  bare_list:
    - data: _test_custom_data/points.geojson
  data_sources_form:
    replace: false
    data_sources:
      - data: _test_custom_data/points.geojson
areas_of_interest:
  public_open_space:
    replace: false
    data_sources:
      - data: _test_custom_data/points.geojson
  blue_space:
    data: _test_custom_data/points.geojson
  public_open_space_variants:
    test_variant: a.aos_ha_public > 2
"""
        with open(config_path, 'w') as file:
            file.write(configuration)
        try:
            r_custom = ghsci.Region(codename)
            configured = r_custom.config
            resolved = []
            for section in ['points_of_interest', 'areas_of_interest']:
                for key, category in configured[section].items():
                    if key == 'public_open_space_variants':
                        # SQL conditions, not data entries; must be untouched
                        self.assertEqual(
                            category,
                            {'test_variant': 'a.aos_ha_public > 2'},
                        )
                        continue
                    entries = ghsci.custom_data_entries(category)
                    self.assertTrue(entries, f'no entries for {section}:{key}')
                    resolved.extend(entry['data'] for entry in entries)
            self.assertTrue(
                resolved,
                'no custom data entries were resolved',
            )
            for path in resolved:
                self.assertTrue(
                    os.path.isabs(path),
                    f'configured data path was not resolved: {path}',
                )
                self.assertTrue(
                    os.path.exists(path),
                    f'resolved data path does not exist: {path}',
                )
        finally:
            if os.path.exists(config_path):
                os.remove(config_path)

        # --- bounds and import, against the analysed example database ---
        r = ghsci.example()
        bbox = r.get_bbox_string()
        self.assertIsNotNone(
            bbox,
            'get_bbox_string returned None for an analysed region',
        )
        bounds = [float(x) for x in bbox.split()]
        self.assertEqual(len(bounds), 4)
        self.assertLess(bounds[0], bounds[2])
        self.assertLess(bounds[1], bounds[3])

        layer = '_test_custom_data_points'
        try:
            r.ogr_to_db(
                source=f'{fixture}:points',
                layer=layer,
                query=f'-spat {bbox} -spat_srs {r.config["crs_srid"]}',
            )
            with r.engine.begin() as connection:
                count = connection.execute(
                    text(f'SELECT count(*) FROM "{layer}";'),
                ).scalar()
            self.assertEqual(
                count,
                1,
                'the spatial filter was not applied when a geopackage or '
                'other layer was selected, so features outside the study '
                'region were imported',
            )
        finally:
            with r.engine.begin() as connection:
                connection.execute(
                    text(f'DROP TABLE IF EXISTS "{layer}";'),
                )
            if os.path.exists(fixture):
                os.remove(fixture)
            if os.path.exists(fixture_dir) and not os.listdir(fixture_dir):
                os.rmdir(fixture_dir)

    def test_9_compile_poi_destinations(self):
        """compile_poi_destinations uses custom spatial data for a dest_name.

        Creates a synthetic GeoJSON with three bus-stop points, configures a
        mock Region whose points_of_interest references that file with
        replace: true, and asserts that:

        - r.ogr_to_db is called with the correct source path and staging
          layer, restricted to the buffered urban study region bounding box
        - Destinations are inserted via ST_Centroid from the staging layer,
          restricted to points intersecting the buffered urban study region
        - A count query is scoped to the dest_name
        - dest_type receives an ON CONFLICT upsert (works for both replace modes)
        - dest_name_full and domain are resolved from ghsci.df_osm_dest for
          known dest_name keys (e.g. 'pt_any')
        - The temporary staging table is dropped after use
        - A category configured as a list of entries loads each data source
          to its own staging table (pooled within the one category)
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
            def mock_poi_region(pt_any_config):
                r = MagicMock()
                r.config = {
                    'crs_srid': 'EPSG:32628',
                    'buffered_urban_study_region': 'urban_study_region_buffered',
                    'points_of_interest': {'pt_any': pt_any_config},
                }
                r.get_bbox_string.return_value = '0.0 0.0 100.0 100.0'
                # Wire up engine context manager; count query returns 3
                mock_result = MagicMock()
                mock_result.first.return_value = [3]
                mock_result.rowcount = 3
                mock_connection = MagicMock()
                mock_connection.execute.return_value = mock_result
                mock_ctx = MagicMock()
                mock_ctx.__enter__ = MagicMock(return_value=mock_connection)
                mock_ctx.__exit__ = MagicMock(return_value=False)
                r.engine.begin.return_value = mock_ctx
                return r, mock_connection

            r, mock_connection = mock_poi_region(
                {
                    'data': tmp_path,
                    'source': 'Test transit stops',
                    'replace': True,
                },
            )

            # --- Call function under test -----------------------------------
            compile_poi_destinations(r)

            # ogr_to_db called once with the file path and staging layer name,
            # restricted to the buffered urban study region bounding box
            r.ogr_to_db.assert_called_once_with(
                source=tmp_path,
                layer='_poi_pt_any_0',
                query='-spat 0.0 0.0 100.0 100.0 -spat_srs EPSG:32628',
            )

            # Collect all SQL strings passed to connection.execute
            # SQLAlchemy TextClause.__str__() returns the raw SQL string
            sql_calls = [
                str(call.args[0])
                for call in mock_connection.execute.call_args_list
            ]

            # INSERT into destinations from the staging layer via ST_Centroid,
            # restricted to the buffered urban study region
            self.assertTrue(
                any(
                    '_poi_pt_any' in s
                    and 'ST_Centroid' in s
                    and 'ST_Intersects' in s
                    for s in sql_calls
                ),
                'Expected INSERT with ST_Centroid from _poi_pt_any restricted '
                'to the buffered urban study region',
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
                    'DROP TABLE' in s and '_poi_pt_any_0' in s
                    for s in sql_calls
                ),
                'Expected DROP TABLE for _poi_pt_any_0 staging table',
            )

            # --- List-form config: multiple pooled data sources --------------
            r, mock_connection = mock_poi_region(
                [
                    {'data': tmp_path, 'source': 'Test stops A'},
                    {'data': tmp_path, 'source': 'Test stops B'},
                ],
            )
            compile_poi_destinations(r)
            self.assertEqual(r.ogr_to_db.call_count, 2)
            staging_layers = [
                call.kwargs['layer'] for call in r.ogr_to_db.call_args_list
            ]
            self.assertEqual(
                staging_layers,
                ['_poi_pt_any_0', '_poi_pt_any_1'],
            )
        finally:
            os.unlink(tmp_path)

    def test_0_15_nearest_poi_query_columns(self):
        """Shared column/WHERE construction matches the historical inline forms."""
        import setup_sp

        # category analysis (e.g. destinations by dest_name), incl. quote escaping
        self.assertEqual(
            setup_sp.nearest_poi_query_columns(
                category_field='dest_name',
                categories=['fresh_food_market', "o'brien"],
                output_names=['fresh_food_market', 'obrien'],
                output_prefix='sp_nearest_node_',
            ),
            [
                (
                    'sp_nearest_node_fresh_food_market',
                    "dest_name = 'fresh_food_market'",
                ),
                ('sp_nearest_node_obrien', "dest_name = 'o''brien'"),
            ],
        )
        # filter-iteration analysis (e.g. GTFS headways); '==' becomes '='
        self.assertEqual(
            setup_sp.nearest_poi_query_columns(
                filter_field='headway',
                filter_iterations=['>=0', '<=20', '==10'],
                output_names=['pt_gtfs_any', 'pt_gtfs_freq_20', 'pt_gtfs_10'],
                output_prefix='sp_nearest_node_',
            ),
            [
                ('sp_nearest_node_pt_gtfs_any', 'headway >=0'),
                ('sp_nearest_node_pt_gtfs_freq_20', 'headway <=20'),
                ('sp_nearest_node_pt_gtfs_10', 'headway =10'),
            ],
        )
        # unfiltered analysis (e.g. public open space entry nodes)
        self.assertEqual(
            setup_sp.nearest_poi_query_columns(
                output_names=['public_open_space_any'],
                output_prefix='sp_nearest_node_',
            ),
            [('sp_nearest_node_public_open_space_any', '')],
        )

    def test_0_17_sample_point_indicators_no_fragmentation(self):
        """calculate_sample_point_indicators stays de-fragmented as analyses grow.

        Builds a wide sample-point frame and a config with 150 indicator
        analyses (comfortably past pandas' 100-block fragmentation threshold,
        where the previous per-column assignment would emit PerformanceWarnings)
        plus a chained analysis that reads a freshly computed indicator.  Asserts
        no fragmentation warning is emitted and that both a plain and a chained
        indicator hold the correct values.
        """
        import contextlib
        import io
        import types
        import warnings

        import geopandas as gpd
        import numpy as np
        import pandas as pd
        from shapely.geometry import Point

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _11_neighbourhood_analysis as nh
        import ghsci

        n = 40
        score_cols = [f'sp_access_x{i}_score' for i in range(150)]
        rng = np.random.default_rng(0)
        data = {'grid_id': range(n), 'edge_ogc_fid': range(n)}
        for c in score_cols:
            data[c] = rng.integers(0, 2, n).astype(float)
        gdf = gpd.GeoDataFrame(
            data,
            geometry=[Point(i, i) for i in range(n)],
            index=pd.Index(range(n), name='point_id'),
        )
        gdf = gdf[['grid_id', 'edge_ogc_fid', 'geometry'] + score_cols]

        analyses = {
            f'A{k}': {
                f'sp_sum_{k}': {
                    'columns': score_cols[k : k + 3],
                    'axis': 1,
                    'formula': 'sum',
                },
            }
            for k in range(150)
        }
        # a chained analysis that must read indicators produced earlier in the run
        analyses['chain'] = {
            'sp_chain': {
                'columns': ['sp_sum_0', 'sp_sum_1'],
                'axis': 1,
                'formula': 'max',
            },
        }
        original = ghsci.indicators.get('sample_point_analyses')
        ghsci.indicators['sample_point_analyses'] = analyses
        try:
            with warnings.catch_warnings(
                record=True,
            ) as caught, contextlib.redirect_stdout(io.StringIO()):
                warnings.simplefilter('always')
                result = nh.calculate_sample_point_indicators(
                    types.SimpleNamespace(indicators=ghsci.indicators),
                    gdf.copy(),
                )
        finally:
            ghsci.indicators['sample_point_analyses'] = original

        frag = [w for w in caught if 'fragmented' in str(w.message).lower()]
        self.assertEqual(
            frag,
            [],
            f'unexpected fragmentation warnings: {len(frag)}',
        )
        # plain indicator and chained indicator hold the correct values
        np.testing.assert_allclose(
            result['sp_sum_0'].to_numpy('float64'),
            gdf[score_cols[0:3]].sum(axis=1).to_numpy('float64'),
        )
        np.testing.assert_allclose(
            result['sp_chain'].to_numpy('float64'),
            np.maximum(
                gdf[score_cols[0:3]].sum(axis=1).to_numpy('float64'),
                gdf[score_cols[1:4]].sum(axis=1).to_numpy('float64'),
            ),
        )

    def test_0_18_grid_mean_summariser_bit_equality(self):
        """Vectorised density summariser bit-matches the pandas expression.

        The in-memory density branch replaces the per-source
        ``grid.loc[gdf_nodes.loc[reached, 'grid_id'].dropna().unique(),
        fields].mean()`` chain (measured ~90 ms/source on a 1.19M-cell grid)
        with a numpy reduction.  This asserts byte-identical output across the
        edge cases: NaN grid associations, duplicate cells (first-appearance
        order), all-NaN statistic values, empty selections, unsorted node ids,
        and a wide selection where pairwise-summation order matters.
        """
        import geopandas as gpd
        import numpy as np
        import pandas as pd
        from shapely.geometry import Point

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _11_neighbourhood_analysis as nh

        rng = np.random.default_rng(1)
        n_cells = 500
        grid = pd.DataFrame(
            {
                'pop_per_sqkm': rng.uniform(0, 1e4, n_cells),
                'intersections_per_sqkm': rng.uniform(0, 200, n_cells),
            },
            index=pd.Index(
                rng.permutation(np.arange(n_cells)) + 10,
                name='grid_id',
            ),
        )
        grid.iloc[5:9, 0] = np.nan  # some NaN statistic values
        node_osmids = rng.permutation(np.arange(1000, 1400))  # unsorted index
        grid_ids = rng.choice(grid.index.to_numpy('float64'), len(node_osmids))
        grid_ids[::7] = np.nan  # nodes outside the grid
        gdf_nodes = gpd.GeoDataFrame(
            {'grid_id': grid_ids},
            geometry=[Point(i, i) for i in range(len(node_osmids))],
            index=pd.Index(node_osmids, name='osmid'),
        )[['grid_id']]
        fields = ['pop_per_sqkm', 'intersections_per_sqkm']

        summarise = nh._grid_mean_summariser(grid, gdf_nodes, fields)

        cases = [
            node_osmids[:50],  # wide (order-sensitive sum)
            node_osmids[::7][:10],  # all-NaN grid associations
            np.array([node_osmids[3]] * 5),  # duplicates of one node
            node_osmids[::-1][:80],  # reversed order
            np.array([node_osmids[8]]),  # single node
        ]
        for reached in cases:
            expected = (
                grid.loc[
                    gdf_nodes.loc[reached, 'grid_id'].dropna().unique(),
                    fields,
                ]
                .mean()
                .values
            )
            np.testing.assert_array_equal(
                summarise(reached),
                expected,
                err_msg=f'mismatch for case of {len(reached)} nodes',
            )
        # a reached node absent from the nodes table raises, as .loc would
        with self.assertRaises(KeyError):
            summarise(np.array([99999999]))

    def test_5_z_pedestrian_routing_engine_equivalence(self):
        """Pedestrian in-memory routing engine matches pgRouting results exactly.

        Runs the nodes-to-nearest-POI stage of the neighbourhood analysis twice
        on the example region -- once per routing engine -- and asserts the
        resulting node-distance frames (the hand-off into the shared sample
        point code) are identical, reporting the wall time of each engine.
        Named test_5_z_* so it runs after test_5_example_analysis has
        populated the example region's database.
        """
        import time as timer

        import pandas as pd

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _11_neighbourhood_analysis as nh

        r = ghsci.example()
        if not {'nodes', 'edges', 'destinations'}.issubset(set(r.tables)):
            self.skipTest(
                'example region analysis outputs not available '
                '(run test_5_example_analysis first)',
            )
        for table in (
            'destinations',
            'aos_public_any_nodes_30m_line',
            'aos_public_large_nodes_30m_line',
            'pt_stops_headway',
        ):
            if table in r.tables:
                r.add_nearest_node_associations(table)
        start = timer.time()
        pg = nh.calculate_poi_accessibility(r, engine='pgrouting')
        t_pg = timer.time() - start
        start = timer.time()
        mem = nh.calculate_poi_accessibility(r, engine='inmemory')
        t_mem = timer.time() - start
        pd.testing.assert_frame_equal(pg, mem)
        print(
            f'\nPedestrian nearest-POI stage, {pg.shape[0]} nodes x '
            f'{pg.shape[1]} columns, identical results: '
            f'pgrouting {t_pg:.1f}s vs inmemory {t_mem:.1f}s '
            f'({t_pg / max(t_mem, 1e-9):.1f}x)',
        )
        r.engine.dispose()

    def test_5_z2_density_engine_equivalence(self):
        """In-memory neighbourhood density statistics match the stored (networkx) ones.

        Recomputes the node-level population and intersection density for the
        example region with the in-memory engine (no caching or writes) and
        compares against the stored nodes_pop_intersect_density table, which was
        produced by the networkx all-pairs path during test_5_example_analysis.
        The reachable node sets are identical by construction; the density means
        are float averages whose summation order may differ on exact distance
        ties, so comparison allows a relative tolerance of 1e-9 (and reports the
        bit-identical share).
        """
        import numpy as np

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _11_neighbourhood_analysis as nh

        r = ghsci.example()
        if 'nodes_pop_intersect_density' not in r.tables:
            self.skipTest(
                'example region analysis outputs not available '
                '(run test_5_example_analysis first)',
            )
        stored = r.get_gdf(
            'nodes_pop_intersect_density',
            index_col='osmid',
            geom_col='geometry',
        )
        nodes = r.get_gdf('nodes', index_col='osmid')
        nodes.columns = [
            'geometry' if x == 'geom' else x for x in nodes.columns
        ]
        nodes = nodes.set_geometry('geometry')
        edges = r.get_gdf('edges_simplified', index_col=['u', 'v', 'key'])
        edges.columns = [
            'geometry' if x == 'geom' else x for x in edges.columns
        ]
        edges = edges.set_geometry('geometry')
        fresh = nh.compute_nodes_pop_intersect_density(
            r,
            edges,
            nodes,
            ghsci.settings['network_analysis']['neighbourhood_distance'],
            engine='inmemory',
        )
        self.assertTrue(fresh.index.equals(stored.index))
        for col in nh.density_statistics.values():
            a = fresh[col].to_numpy('float64')
            b = stored[col].to_numpy('float64')
            both_nan = np.isnan(a) & np.isnan(b)
            exact = int(np.sum((a == b) | both_nan))
            np.testing.assert_allclose(a, b, rtol=1e-9, equal_nan=True)
            print(
                f'\n{col}: within rtol 1e-9; bit-identical '
                f'{exact}/{len(a)} nodes',
            )
        r.engine.dispose()

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
        codename = 'ES_Las_Palmas_2025'
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
        reference = 'ES_Las_Palmas_2025'
        comparison = 'ES_Las_Palmas_2025_test_not_urbanx'
        # create modified version of reference configuration
        with open(ghsci.get_region_config_path(reference)) as file:
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
