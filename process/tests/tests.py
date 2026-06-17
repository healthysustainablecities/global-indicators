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

    def test_0_3_cycling_pick_highway(self):
        """_pick_highway resolves list-like tags and gives cycleway precedence."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import numpy as np

        import _cycling_lts_network as lts

        self.assertEqual(lts._pick_highway('residential'), 'residential')
        # highest-capacity class wins in a merged tag
        self.assertEqual(
            lts._pick_highway("['residential', 'service']"), 'residential',
        )
        # a cycleway value takes precedence (mirrors R createCycleway)
        self.assertEqual(
            lts._pick_highway("['residential', 'cycleway']"), 'cycleway',
        )
        self.assertEqual(lts._pick_highway('cycleway'), 'cycleway')
        self.assertIsNone(lts._pick_highway(None))
        self.assertIsNone(lts._pick_highway(np.nan))

    def test_0_4_cycling_parse_speed_kmh(self):
        """parse_speed_kmh converts mph, keeps km/h, and yields NaN otherwise."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import numpy as np
        import pandas as pd

        import _cycling_lts_network as lts

        out = lts.parse_speed_kmh(
            pd.Series(['30', '30 mph', '50 km/h', None, 'ES:urban']),
        )
        np.testing.assert_allclose(
            np.asarray(out[:3], dtype='float'), [30, 30 * 1.60934, 50],
        )
        self.assertTrue(np.isnan(out[3]) and np.isnan(out[4]))

    def test_0_5_cycling_classify_cycleway(self):
        """classify_cycleway maps OSM cycle tags to the bike_facility classes."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import pandas as pd

        import _cycling_lts_network as lts

        edges = pd.DataFrame(
            {
                'highway': [
                    'cycleway', 'residential', 'residential',
                    'residential', 'secondary',
                ],
                'cycleway': [None, 'track', 'lane', 'shared_lane', None],
                'cycleway_left': [None, None, None, None, None],
                'cycleway_right': [None, None, None, None, None],
                'bicycle': [None, None, None, None, None],
                'foot': [None, None, None, None, None],
                'motor_vehicle': [None, None, None, None, None],
            },
        )
        _, facility = lts.classify_cycleway(edges)
        self.assertEqual(
            facility.tolist(),
            [
                'shared_path', 'separated_lane', 'simple_lane',
                'shared_street', 'no lane/track/path',
            ],
        )

    def test_0_6_cycling_assign_lts(self):
        """assign_lts reproduces representative cells of manuscript Table 1."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import pandas as pd

        import _cycling_lts_network as lts

        def lts_for(highway, facility, speed):
            highway = pd.Series(highway)
            facility = pd.Series(facility)
            speed = pd.Series(speed, dtype='float')
            adt = lts.assign_adt(highway)
            return lts.assign_lts(highway, facility, speed, adt).tolist()

        nolane = 'no lane/track/path'
        # mixed traffic: footway off-road, then residential 30/50/60/70,
        # then secondary 30, primary 30
        self.assertEqual(
            lts_for(
                ['footway', 'residential', 'residential', 'residential',
                 'residential', 'secondary', 'primary'],
                [nolane] * 7,
                [30, 30, 50, 60, 70, 30, 30],
            ),
            [1, 1, 2, 3, 4, 3, 3],
        )
        # separated cycle lane on a residential road at 50 / 60 / 70 km/h
        self.assertEqual(
            lts_for(
                ['residential'] * 3,
                ['separated_lane'] * 3,
                [50, 60, 70],
            ),
            [1, 2, 4],
        )
        # on-road (simple) cycle lane on a local road at 30 / 50 / 60 km/h
        self.assertEqual(
            lts_for(
                ['residential'] * 3,
                ['simple_lane'] * 3,
                [30, 50, 60],
            ),
            [1, 2, 3],
        )

    def test_0_7_cycling_lookup_sql_parameterisation(self):
        """build_dest_node_lookup batch SQL honours cycling cost / where overrides."""
        from unittest.mock import MagicMock

        import setup_sp

        captured = []
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = lambda stmt: captured.append(str(stmt))
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        # cycling override
        setup_sp._run_lookup_batch(
            mock_engine,
            [1, 2, 3],
            5000,
            edge_table='edges',
            cost='cost_lts',
            reverse_cost='cost_lts_reverse',
            where='lvl_traf_stress <= 2 AND bike_permitted',
        )
        cycling_sql = captured[-1]
        self.assertIn('cost_lts::float AS cost', cycling_sql)
        self.assertIn('cost_lts_reverse::float AS reverse_cost', cycling_sql)
        self.assertIn('lvl_traf_stress <= 2 AND bike_permitted', cycling_sql)

        # pedestrian default is unchanged
        setup_sp._run_lookup_batch(mock_engine, [1, 2, 3], 5000)
        default_sql = captured[-1]
        self.assertIn('e.length::float AS cost', default_sql)
        self.assertIn('e.length::float AS reverse_cost', default_sql)
        self.assertNotIn('lvl_traf_stress', default_sql)

    def test_0_8_cycling_config_and_speed_defaults(self):
        """cycling_config gating and load_speed_defaults source selection."""
        import types

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts

        def region(value):
            return types.SimpleNamespace(
                config={'cycling_indicators': value},
            )

        # true -> enabled with empty config; mapping -> passed through;
        # false / absent -> disabled (None)
        self.assertEqual(lts.cycling_config(region(True)), {})
        self.assertEqual(
            lts.cycling_config(region({'no_cycle': ['steps']})),
            {'no_cycle': ['steps']},
        )
        self.assertIsNone(lts.cycling_config(region(False)))
        self.assertIsNone(
            lts.cycling_config(types.SimpleNamespace(config={})),
        )

        # inline defaults are lower-cased; absent config falls back to the
        # built-in global table
        self.assertEqual(
            lts.load_speed_defaults(
                {'defaults': {'Residential': 40, 'Service': 25}},
            ),
            {'residential': 40, 'service': 25},
        )
        self.assertEqual(lts.load_speed_defaults({}), lts.DEFAULT_SPEED_KMH)

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
                    'dest_type' in s
                    and 'pt_any' in s
                    and 'ON CONFLICT' in s
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
                    'DROP TABLE' in s and '_poi_pt_any' in s
                    for s in sql_calls
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
