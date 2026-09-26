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
import re
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

    def test_0_01_valid_yaml(self):
        """Check if example configuration file is valid YAML."""
        valid = sp.call(
            """yamllint ./data/examples/ES_Las_Palmas_2025/configuration/ES_Las_Palmas_2025.yml --strict""",
            shell=True,
        )
        self.assertTrue(valid == 0)

    def test_0_02_identify_invalid_yaml(self):
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

    def test_0_03_schema_yaml(self):
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

    def test_0_04_cycling_pick_highway(self):
        """_pick_highway resolves list-like tags and gives cycleway precedence."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import numpy as np

        self.assertEqual(lts._pick_highway('residential'), 'residential')
        # highest-capacity class wins in a merged tag
        self.assertEqual(
            lts._pick_highway("['residential', 'service']"),
            'residential',
        )
        # a cycleway value takes precedence (mirrors R createCycleway)
        self.assertEqual(
            lts._pick_highway("['residential', 'cycleway']"),
            'cycleway',
        )
        self.assertEqual(lts._pick_highway('cycleway'), 'cycleway')
        self.assertIsNone(lts._pick_highway(None))
        self.assertIsNone(lts._pick_highway(np.nan))

    def test_0_05_cycling_parse_speed_kmh(self):
        """parse_speed_kmh converts mph, keeps km/h, and yields NaN otherwise."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import numpy as np
        import pandas as pd

        out = lts.parse_speed_kmh(
            pd.Series(['30', '30 mph', '50 km/h', None, 'ES:urban']),
        )
        np.testing.assert_allclose(
            np.asarray(out[:3], dtype='float'),
            [30, 30 * 1.60934, 50],
        )
        self.assertTrue(np.isnan(out[3]) and np.isnan(out[4]))

    def test_0_06_cycling_classify_cycleway(self):
        """classify_cycleway maps OSM cycle tags to the bike_facility classes."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import pandas as pd

        edges = pd.DataFrame(
            {
                'highway': [
                    'cycleway',
                    'residential',
                    'residential',
                    'residential',
                    'secondary',
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
                'shared_path',
                'separated_lane',
                'simple_lane',
                'shared_street',
                'no lane/track/path',
            ],
        )

    def test_0_07_cycling_assign_lts(self):
        """assign_lts reproduces representative cells of manuscript Table 1."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import pandas as pd

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
                [
                    'footway',
                    'residential',
                    'residential',
                    'residential',
                    'residential',
                    'secondary',
                    'primary',
                ],
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

    def test_0_08_cycling_lookup_sql_parameterisation(self):
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

    def test_0_09_cycling_config_and_speed_defaults(self):
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

        # inline defaults are lower-cased and layered OVER the built-in table, so a
        # class the region omits (e.g. unclassified) still gets a speed rather than
        # falling through to NaN -> LTS 4
        merged = lts.load_speed_defaults(
            {'defaults': {'Residential': 33, 'Service': 25}},
        )
        self.assertEqual(merged['residential'], 33)  # overridden
        self.assertEqual(merged['service'], 25)
        self.assertEqual(  # gap filled from built-in
            merged['unclassified'],
            lts.DEFAULT_SPEED_KMH['unclassified'],
        )
        # absent config returns the built-in global table (as a copy)
        self.assertEqual(lts.load_speed_defaults({}), lts.DEFAULT_SPEED_KMH)

    def test_0_10_activity_centre_config(self):
        """activity_centre_config gating, defaults and overrides."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_accessibility as acc

        # enabled by default when cycling indicators are on (config is {} / mapping)
        self.assertEqual(
            acc.activity_centre_config({}),
            acc.ACTIVITY_CENTRE_DEFAULTS,
        )
        # explicit false / None disables
        self.assertIsNone(
            acc.activity_centre_config({'activity_centres': False}),
        )
        self.assertIsNone(acc.activity_centre_config(None))
        # a mapping overrides only the supplied keys; defaults untouched (no mutation)
        cfg = acc.activity_centre_config(
            {'activity_centres': {'walk_threshold': 800}},
        )
        self.assertEqual(cfg['walk_threshold'], 800)
        self.assertEqual(cfg['categories'], ['food', 'pos', 'pt'])
        self.assertEqual(
            cfg['tiers'],
            {'local': 'lenient', 'complete': 'strict'},
        )
        self.assertEqual(acc.ACTIVITY_CENTRE_DEFAULTS['walk_threshold'], 400)

    def test_0_11_cycling_motor_restriction(self):
        """motor_restricted detection and apply_motor_restriction speed/ADT capping."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import numpy as np
        import pandas as pd

        mv = pd.Series(
            [
                'destination',
                'no',
                'private',
                'permissive',
                'yes',
                None,
                "['no', 'destination']",
                'agricultural;forestry',
            ],
        )
        self.assertEqual(
            lts.motor_restricted(mv).tolist(),
            [True, True, True, False, False, False, True, True],
        )

        # an unclassified lane tagged motor_vehicle=destination with no posted speed is
        # capped to the local speed (30) and local ADT, so it classifies LTS 1 like R
        edges = pd.DataFrame(
            {
                'highway': ['unclassified', 'unclassified'],
                'motor_vehicle': ['destination', None],
            },
        )
        speed = pd.Series([np.nan, np.nan])
        adt = lts.assign_adt(edges['highway'])  # local -> 750
        speed2, adt2 = lts.apply_motor_restriction(edges, speed, adt)
        self.assertEqual(speed2.tolist()[0], lts.MOTOR_LOCAL_SPEED_KMH)
        self.assertTrue(
            pd.isna(speed2.tolist()[1]),
        )  # untouched where unrestricted
        facility = pd.Series(['no lane/track/path', 'no lane/track/path'])
        self.assertEqual(
            lts.assign_lts(edges['highway'], facility, speed2, adt2).tolist()[
                0
            ],
            1,
        )

    def test_0_12_cycling_bike_permitted_override(self):
        """bicycle=designated/yes overrides the no_cycle class ban; explicit no bars."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import pandas as pd

        edges = pd.DataFrame(
            {
                'highway': [
                    'footway',
                    'footway',
                    'path',
                    'residential',
                    'steps',
                ],
                'bicycle': ['designated', None, 'yes', 'no', None],
            },
        )
        # no_cycle bans footway/path/steps; designated/yes on footway/path override it,
        # residential bicycle=no is barred, plain footway and steps stay barred
        result = lts.assign_bike_permitted(
            edges,
            no_cycle=['footway', 'path', 'steps', 'corridor', 'pedestrian'],
        ).tolist()
        self.assertEqual(result, [True, False, True, False, False])

    def test_0_13_cycling_no_cycle_uses_raw_merged_tag(self):
        """The no_cycle ban tests every token of a merged tag, with a ramp exemption."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import pandas as pd

        # OSMnx records merged ways as the repr of a list; _pick_highway would resolve
        # each of these away from 'steps', so only a raw-tag test catches them.
        edges = pd.DataFrame(
            {
                'highway_osm': [
                    "['footway', 'steps']",  # part staircase -> barred
                    "['residential', 'steps']",  # resolves to residential -> still barred
                    "['footway', 'steps']",  # staircase has a wheeling ramp -> permitted
                    'footway',  # no no_cycle token -> unaffected
                    'steps',  # plain staircase -> barred
                ],
                'highway': [
                    'footway',
                    'residential',
                    'footway',
                    'footway',
                    'steps',
                ],
                'bicycle': [None, None, None, None, None],
                'bike_ramp': [False, False, True, False, False],
            },
        )
        self.assertEqual(
            lts.assign_bike_permitted(edges).tolist(),
            [False, False, True, True, False],
        )

        # foot_dismount must exclude the same staircases even though they resolve to a
        # DISMOUNT_HIGHWAYS class.  bicycle=no keeps every row out of bike_permitted, so
        # each is a dismount candidate and only the raw-tag ban decides.
        walk = pd.DataFrame(
            {
                'highway_osm': [
                    "['footway', 'steps']",  # part staircase -> not walkable with a bike
                    "['steps', 'path']",  # resolves to path -> still barred
                    "['footway', 'steps']",  # wheeling ramp -> walkable
                    'footway',  # ordinary footway -> walkable (unchanged)
                ],
                'highway': ['footway', 'path', 'footway', 'footway'],
                'bicycle': ['no', 'no', 'no', 'no'],
                'bike_ramp': [False, False, True, False],
                'foot': [None, None, None, None],
            },
        )
        walk['bike_permitted'] = lts.assign_bike_permitted(walk)
        self.assertEqual(walk['bike_permitted'].tolist(), [False] * 4)
        self.assertEqual(
            lts.compute_foot_dismount(walk).tolist(),
            [False, False, True, True],
        )

    def test_0_14_cycling_region_no_cycle_does_not_bar_walking(self):
        """A region banning riding on footways still allows walking the bike there."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import pandas as pd

        # Wuerzburg's configuration bans riding on footway/path/pedestrian as well as
        # steps/corridor.  foot_dismount exists precisely to make those walkable, so the
        # dismount exclusion must key off NO_DISMOUNT_HIGHWAYS, not the region list.
        region_no_cycle = [
            'pedestrian',
            'footway',
            'steps',
            'path',
            'corridor',
        ]
        edges = pd.DataFrame(
            {
                'highway_osm': [
                    'footway',
                    "['footway', 'steps']",
                    "['footway', 'steps']",
                ],
                'highway': ['footway', 'footway', 'footway'],
                'bicycle': [None, None, None],
                'bike_ramp': [False, False, True],
                'foot': [None, None, None],
            },
        )
        edges['bike_permitted'] = lts.assign_bike_permitted(
            edges,
            region_no_cycle,
        )
        # riding is banned on all three (footway is on the region's no_cycle list); the
        # ramp lifts only the staircase part of the ban, not the footway part
        self.assertEqual(
            edges['bike_permitted'].tolist(),
            [False, False, False],
        )
        # but the plain footway and the ramped staircase remain walkable
        self.assertEqual(
            lts.compute_foot_dismount(edges).tolist(),
            [True, False, True],
        )

    def test_0_15_cycling_tag_tokens_and_has_class(self):
        """_tag_tokens splits merged tags; _has_class matches any token."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_lts_network as lts
        import numpy as np
        import pandas as pd

        self.assertEqual(lts._tag_tokens('steps'), ['steps'])
        self.assertEqual(
            lts._tag_tokens("['footway', 'steps']"),
            ['footway', 'steps'],
        )
        self.assertEqual(lts._tag_tokens(None), [])
        self.assertEqual(lts._tag_tokens(np.nan), [])
        series = pd.Series(["['footway', 'steps']", 'footway', None])
        self.assertEqual(
            lts._has_class(series, ['steps', 'corridor']).tolist(),
            [True, False, False],
        )
        # way ids parse from either form
        self.assertEqual(lts._way_ids('12345'), [12345])
        self.assertEqual(lts._way_ids('[12345, 678]'), [12345, 678])

    def test_0_16_combined_and_named_sets(self):
        """combined_access sets, member resolution and named activity centres."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _cycling_accessibility as acc

        specs = [
            {
                'name': 'fresh_food_market',
                'category': 'food',
                'variant': 'strict',
            },
            {
                'name': 'fresh_food_pooled',
                'category': 'food',
                'variant': 'lenient',
            },
            {
                'name': 'public_open_space_large',
                'category': 'pos',
                'variant': 'strict',
            },
            {
                'name': 'public_open_space_any',
                'category': 'pos',
                'variant': 'lenient',
            },
            {'name': 'pt_frequent', 'category': 'pt', 'variant': 'strict'},
            {'name': 'pt_any', 'category': 'pt', 'variant': 'lenient'},
            {'name': 'bike_rack', 'category': 'bike_rack', 'variant': 'any'},
        ]
        # default -> only the standard global set; config adds a local_custom set
        self.assertEqual(
            acc.combined_access_sets({}, specs),
            {'standard': ['food', 'pos', 'pt']},
        )
        sets = acc.combined_access_sets(
            {
                'combined_access': {
                    'local_custom': {
                        'categories': ['food', 'pos', 'pt', 'bike_rack'],
                    },
                },
            },
            specs,
        )
        self.assertEqual(sets['standard'], ['food', 'pos', 'pt'])
        self.assertEqual(
            sets['local_custom'],
            ['food', 'pos', 'pt', 'bike_rack'],
        )
        # a single-variant category resolves into both strictness variants
        self.assertEqual(
            acc._resolve_member(specs, 'bike_rack', 'strict')['name'],
            'bike_rack',
        )
        self.assertEqual(
            acc._resolve_member(specs, 'bike_rack', 'lenient')['name'],
            'bike_rack',
        )
        self.assertEqual(
            acc._resolve_member(specs, 'food', 'strict')['name'],
            'fresh_food_market',
        )
        self.assertEqual(
            acc._resolve_member(specs, 'food', 'lenient')['name'],
            'fresh_food_pooled',
        )
        # named activity-centre map auto-includes 'standard'
        defs = acc.activity_centre_definitions(
            {
                'activity_centres': {
                    'local_custom': {
                        'categories': ['food', 'pos', 'pt', 'bike_rack'],
                    },
                },
            },
        )
        self.assertEqual(set(defs), {'standard', 'local_custom'})
        self.assertEqual(defs['standard']['categories'], ['food', 'pos', 'pt'])
        self.assertEqual(
            defs['local_custom']['categories'],
            ['food', 'pos', 'pt', 'bike_rack'],
        )
        # single-option form still yields just the customised standard def
        single = acc.activity_centre_definitions(
            {'activity_centres': {'walk_threshold': 800}},
        )
        self.assertEqual(set(single), {'standard'})
        self.assertEqual(single['standard']['walk_threshold'], 800)
        self.assertEqual(
            acc.activity_centre_definitions({'activity_centres': False}),
            {},
        )

    def test_0_17_shared_accessibility_specification(self):
        """Destinations and activity centres are shared by both analyses."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _accessibility_spec as spec
        import _cycling_accessibility as acc
        import _pedestrian_accessibility as ped
        import data_dictionary as dd

        # The names moved to the shared module are re-exported unchanged, so
        # that existing imports of _cycling_accessibility keep resolving.
        for name in (
            'ACTIVITY_CENTRE_DEFAULTS',
            'DEFAULT_DESTINATIONS',
            'STANDARD_SET',
            'activity_centre_config',
            'activity_centre_definitions',
            'combined_access_sets',
            'derive_activity_centres',
            'usable_destination_specs',
            '_resolve_member',
            '_build_dest_table',
            '_DEST_TABLE',
        ):
            self.assertIs(getattr(acc, name), getattr(spec, name), name)

        # A mode-specific block inherits only the shared keys it does not set.
        shared = {
            'destinations': [{'name': 'a', 'layer': 'destinations'}],
            'combined_access': {'s': {'categories': ['x', 'y']}},
        }
        merged = spec.effective_config(shared, {'distances': [2000]})
        self.assertEqual(merged['distances'], [2000])
        self.assertEqual(merged['destinations'], shared['destinations'])
        self.assertEqual(merged['combined_access'], shared['combined_access'])
        own = spec.effective_config(
            shared,
            {'destinations': [{'name': 'b', 'layer': 'destinations'}]},
        )
        self.assertEqual(own['destinations'][0]['name'], 'b')
        # An explicit false is a value, not an omission, so it is not filled in.
        self.assertIs(
            spec.effective_config(
                {'activity_centres': {'z': {'categories': ['x']}}},
                {'activity_centres': False},
            )['activity_centres'],
            False,
        )

        # The pedestrian analysis is opt-in: without an accessibility block it
        # does nothing, leaving the indicators.yml walking indicators as the
        # only walking output.
        class _Region:
            def __init__(self, config):
                self.config = config

        self.assertIsNone(ped.pedestrian_config(_Region({})))
        self.assertIsNone(
            ped.pedestrian_config(
                _Region({'accessibility': {'pedestrian': False}}),
            ),
        )
        config = ped.pedestrian_config(
            _Region(
                {
                    'accessibility': {
                        'pedestrian': {'distances': [500, 1000, 1500]},
                        'destinations': [
                            {'name': 'a', 'layer': 'destinations'},
                        ],
                    },
                },
            ),
        )
        self.assertEqual(config['destinations'][0]['name'], 'a')
        self.assertEqual(ped.resolve_thresholds(config), (500, 1000, 1500))
        # bands are de-duplicated and ordered, whatever the configuration says
        self.assertEqual(
            ped.resolve_thresholds({'distances': [1500, 500, 500]}),
            (500, 1500),
        )
        # and default to the project accessibility distance
        self.assertEqual(ped.resolve_thresholds({}), (500,))
        # distances may be searched beyond the largest band, never short of it
        self.assertEqual(
            ped.resolve_search_distance({}, (500, 1500)),
            1500,
        )
        self.assertEqual(
            ped.resolve_search_distance(
                {'search_distance': 5000},
                (500, 1500),
            ),
            5000,
        )
        with self.assertRaises(ValueError):
            ped.resolve_search_distance({'search_distance': 1000}, (500, 1500))

        # A region may set its own co-location radius per definition without
        # disturbing the global default other cities are compared on.
        defs = spec.activity_centre_definitions(
            {
                'activity_centres': {
                    'services': {
                        'walk_threshold': 300,
                        'categories': ['food_retail', 'pharmacy'],
                        'tiers': {'local': 'lenient'},
                    },
                },
            },
        )
        self.assertEqual(set(defs), {'standard', 'services'})
        self.assertEqual(defs['services']['walk_threshold'], 300)
        self.assertEqual(defs['standard']['walk_threshold'], 400)
        self.assertEqual(spec.ACTIVITY_CENTRE_DEFAULTS['walk_threshold'], 400)

        # The column names the analysis writes, and those the aggregation step
        # derives from them, must all resolve in the data dictionary: an
        # unresolved name is reported as 'Other fields' with no units.
        self.assertEqual(ped.DISTANCE_PREFIX, 'sp_walk_nearest_node_')
        self.assertEqual(ped.ACCESS_PREFIX, 'sp_walk_access_')
        walking = 'Indicator estimates: access (walking)'
        for name, units, statistic in (
            ('sp_walk_nearest_node_denue_pharmacy', 'metres', 'value'),
            ('sp_walk_access_denue_pharmacy_1500m', 'score 0-1', 'value'),
            ('pct_access_walk_denue_pharmacy_500m', 'percent', 'percentage'),
            (
                'pop_pct_access_walk_denue_pharmacy_500m',
                'percent',
                'percentage',
            ),
            ('avg_walk_dist_denue_pharmacy', 'metres', 'mean'),
            ('pop_avg_walk_dist_denue_pharmacy', 'metres', 'mean'),
        ):
            category, description = dd.describe_variable(name)
            self.assertEqual(category, walking, name)
            self.assertTrue(description, name)
            self.assertEqual(dd.describe_units(name), (units, statistic), name)

        # A named definition may be switched off, including the implicit
        # 'standard' one: a region reporting against its own threshold should
        # not have to carry the global 400 m centre's columns as well.
        only_local = spec.activity_centre_definitions(
            {
                'activity_centres': {
                    'standard': False,
                    'services': {
                        'walk_threshold': 300,
                        'categories': ['food_retail', 'pharmacy'],
                        'tiers': {'local': 'lenient'},
                    },
                },
            },
        )
        self.assertEqual(set(only_local), {'services'})

        # A spec may set its own policy-relevant band without adding that band
        # to every other destination, and the routing must still reach it.
        banded = [
            {'name': 'petrol', 'distances': [250]},
            {'name': 'pharmacy'},
        ]
        self.assertEqual(
            spec.spec_thresholds(banded, (500, 1000, 1500)),
            {'petrol': (250,), 'pharmacy': (500, 1000, 1500)},
        )
        self.assertEqual(
            spec.all_thresholds(banded, (500, 1000, 1500)),
            (250, 500, 1000, 1500),
        )
        # the spec a distance column belongs to is recoverable whatever the
        # routing pass prefix, which is what per-spec bands are keyed on
        self.assertEqual(
            spec.spec_name('sp_walk_nearest_node_denue_petrol_station'),
            'denue_petrol_station',
        )
        self.assertEqual(
            spec.spec_name('sp_cycle_safe_nearest_node_fresh_food_market'),
            'fresh_food_market',
        )

        # An avoided destination reports the opposite polarity, and says so:
        # 'access within 250 m' and 'living beyond 250 m' are not the same
        # claim, so the name has to carry the difference.
        beyond = 'pct_beyond_walk_denue_petrol_station_250m'
        category, description = dd.describe_variable(beyond)
        self.assertEqual(category, walking)
        self.assertIn('further than 250 m', description)
        self.assertIn('higher is better', description)
        self.assertEqual(dd.describe_units(beyond), ('percent', 'percentage'))
        self.assertEqual(
            dd.describe_units('sp_walk_beyond_denue_petrol_station_250m'),
            ('score 0-1', 'value'),
        )

        # A definition name containing underscores must not be mistaken for
        # part of the tier name.
        self.assertIn(
            "'local_custom' definition ('complete' tier)",
            dd.describe_variable(
                'avg_walk_dist_activity_centre_local_custom_complete',
            )[1],
        )
        # The cycling measures added since the dictionary was written resolve
        # too, rather than falling through to 'Other fields'.
        for name in (
            'sp_cycle_ride_nearest_node_fresh_food_market',
            'sp_cycle_dmgap_extra_fresh_food_market',
            'pct_access_cycle_dmgap_fresh_food_market_2000m',
            'pop_avg_cycle_extra_dmgap_fresh_food_market',
        ):
            self.assertEqual(
                dd.describe_variable(name)[0],
                'Indicator estimates: cycling accessibility',
                name,
            )
            self.assertNotEqual(dd.describe_units(name), ('', ''), name)

    def test_0_18_diversity_sets_and_scores(self):
        """Diversity set resolution, and the entropy and richness scores.

        The scores are the point of the measure, so they are checked against
        hand-computed values rather than against themselves: an even spread over
        every configured sub-type is 1, a single sub-type is 0, and nothing
        reachable is 0 rather than null -- a location with nothing available has
        no diversity, and recording that as missing would drop the worst-served
        locations out of every mean computed afterwards.
        """
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _accessibility_spec as spec
        import data_dictionary as dd
        import numpy as np
        import pandas as pd

        config = {
            'diversity': {
                'fresh_food': {
                    'distances': [500, 1000],
                    'groups': {
                        'meat': "dest_name = 'x' AND tags->>'c' = '1'",
                        'produce': "dest_name = 'x' AND tags->>'c' = '2'",
                    },
                },
                # fewer than two groups says nothing a count does not, and is
                # skipped rather than scored
                'too_small': {'groups': {'only': "dest_name = 'y'"}},
            },
        }
        sets = spec.diversity_sets(config)
        self.assertEqual(list(sets), ['fresh_food'])
        self.assertEqual(sets['fresh_food']['layer'], 'destinations')
        self.assertEqual(spec.diversity_bands(sets, (500,)), (500, 1000))
        self.assertEqual(
            spec.set_bands(sets['fresh_food'], (500,)),
            (500, 1000),
        )

        # each group becomes an ordinary destination spec, tagged so that the
        # combined-access and activity-centre machinery ignores it
        group_specs = spec.diversity_specs(sets)
        self.assertEqual(
            [x['name'] for x in group_specs],
            ['fresh_food__meat', 'fresh_food__produce'],
        )
        self.assertTrue(all(x['variant'] == 'group' for x in group_specs))
        self.assertEqual(
            spec.combined_access_sets({}, group_specs),
            {'standard': []},
        )

        # a set with no distances of its own falls back to the analysis bands
        plain = spec.diversity_sets(
            {
                'diversity': {
                    's': {
                        'groups': {
                            'a': 'true',
                            'b': 'true',
                        },
                    },
                },
            },
        )
        self.assertEqual(spec.set_bands(plain['s'], (500, 1500)), (500, 1500))

        counts = pd.DataFrame(
            [
                [5, 0, 0, 0],  # one sub-type only
                [3, 3, 3, 3],  # even across every configured sub-type
                [0, 0, 0, 0],  # nothing reachable
                [2, 2, 0, 0],  # even across half of them
                [9, 1, 0, 0],  # dominated by one
            ],
            columns=['a', 'b', 'c', 'd'],
        )
        entropy = spec.normalised_entropy(counts)
        richness = spec.richness(counts)
        self.assertEqual(entropy[0], 0.0)
        self.assertEqual(entropy[1], 1.0)
        self.assertEqual(entropy[2], 0.0)
        self.assertAlmostEqual(entropy[3], np.log(2) / np.log(4))
        self.assertLess(entropy[4], entropy[3])
        self.assertGreater(entropy[4], 0)
        self.assertEqual(list(richness), [0.25, 1.0, 0.0, 0.5, 0.5])
        # negating a sum of zeros gives -0.0, which reads as a different number
        self.assertFalse(any(np.signbit(entropy.to_numpy())))
        # k comes from the configuration, not from what happens to be present:
        # a sub-type absent everywhere still counts against the score
        self.assertLess(spec.normalised_entropy(counts.assign(e=0))[1], 1.0)

        # count columns carry their band, a nearest distance does not
        self.assertEqual(
            spec.count_column('sp_walk_count_', 'fresh_food__meat', 500),
            'sp_walk_count_fresh_food__meat_500m',
        )

        # every new output family resolves to a description and units rather
        # than falling through to blanks in the generated data dictionary
        for name in (
            'sp_walk_count_fresh_food__meat_500m',
            'avg_count_walk_fresh_food__meat_500m',
            'pop_avg_count_walk_fresh_food__meat_500m',
            'sp_walk_diversity_fresh_food_500m',
            'avg_diversity_walk_fresh_food_1000m',
            'pop_avg_diversity_walk_fresh_food_500m',
            'sp_walk_richness_fresh_food_500m',
            'avg_richness_walk_fresh_food_500m',
            'pct_access_walk_blue_space_500m',
            'avg_walk_dist_public_open_space_with_water',
        ):
            self.assertEqual(
                dd.describe_variable(name)[0],
                'Indicator estimates: access (walking)',
                name,
            )
            self.assertNotEqual(dd.describe_units(name), ('', ''), name)
        # 'Shannon' is a name, and must survive the sentence casing
        self.assertIn(
            'Shannon',
            dd.describe_variable('sp_walk_diversity_fresh_food_500m')[1],
        )

    def test_0_18a_diversity_name_lengths(self):
        """Diversity names too long for PostgreSQL fail before any routing."""
        import _accessibility_spec as spec
        import _pedestrian_accessibility as ped

        groups = {'community': 'true', 'recreation': 'true'}
        # Mexicali's set: at 1000 m and above the population-weighted count
        # columns exceed 63 characters, and PostgreSQL kept only
        # '..._community_1000' and '..._recreation_100' of them
        long_set = spec.diversity_sets(
            {
                'diversity': {
                    'community_culture_recreation': {
                        'distances': [300, 500, 1000, 1500],
                        'groups': groups,
                    },
                },
            },
        )
        with self.assertRaises(ValueError) as raised:
            ped.validate_diversity_names(long_set, (500,))
        message = str(raised.exception)
        self.assertIn(
            'pop_avg_count_walk_community_culture_recreation__recreation_1000m',
            message,
        )
        # the room left for the set and its longest group at 1500 m:
        # 63 - len('pop_avg_count_walk_') - len('__') - len('_1500m') = 36
        self.assertIn('at most 36 together with any group name', message)
        # a name that fits at 300 m is not reported as though it did not
        self.assertNotIn('community_300m', message)

        # the same groups under a set name two characters shorter fit at every
        # band, the longest derived name then being exactly at the limit
        short_set = spec.diversity_sets(
            {
                'diversity': {
                    'civic_recreation_amenities': {
                        'distances': [300, 1500],
                        'groups': groups,
                    },
                },
            },
        )
        ped.validate_diversity_names(short_set, (500,))
        city = (
            spec.CITY_SUMMARY_PREFIX + 'avg_count_walk_',
            spec.CITY_SUMMARY_PREFIX + 'avg_diversity_walk_',
            spec.CITY_SUMMARY_PREFIX + 'avg_richness_walk_',
        )
        names = spec.diversity_column_names(short_set, (500,), city)
        self.assertEqual(
            max(len(n) for n in names['civic_recreation_amenities']),
            spec.IDENTIFIER_LIMIT,
        )
        # the city names the aggregation makes are the ones checked
        self.assertEqual(
            ped.summary_columns(
                [
                    'sp_walk_count_civic_recreation_amenities__recreation_1500m',
                    'sp_walk_diversity_civic_recreation_amenities_1500m',
                    'geom',
                ],
            ),
            [
                'pop_avg_count_walk_civic_recreation_amenities__recreation_1500m',
                'pop_avg_diversity_walk_civic_recreation_amenities_1500m',
            ],
        )
        # a set with no distances of its own is checked at the analysis bands:
        # '..._community_500m' fits, '..._community_1000m' does not
        plain = spec.diversity_sets(
            {
                'diversity': {
                    'community_culture_recreation': {
                        'groups': {'community': 'true', 'sport': 'true'},
                    },
                },
            },
        )
        ped.validate_diversity_names(plain, (500,))
        with self.assertRaises(ValueError):
            ped.validate_diversity_names(plain, (500, 1000))

        # the generic check names every over-long column, and nothing else
        with self.assertRaises(ValueError) as raised:
            spec.check_identifier_lengths(['a' * 63, 'b' * 64], 'Test')
        self.assertIn('b' * 64, str(raised.exception))
        self.assertNotIn('a' * 63 + ' ', str(raised.exception))
        spec.check_identifier_lengths(['a' * 63], 'Test')

    def test_0_19_blue_space_and_open_space_variants(self):
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

    def test_0_20_custom_destination_tags(self):
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

    def test_0_21_pedestrian_inmemory_semantics(self):
        """In-memory nearest-POI engine reproduces pgRouting lookup semantics exactly.

        Hand-computed reference on a synthetic network, deliberately covering the
        semantic edge cases that distinguish the pgRouting lookup from a naive
        (super-source) in-memory formulation:

        - the network-distance cap applies BEFORE destination offsets, so a
          nearer-in-total destination whose network leg exceeds the cap must be
          excluded (node 10 / column A: seed 30 at 120 m + 5 m offset = 125 total
          must lose to seed 20 at 60 m + 70 m offset = 130);
        - the cap is inclusive (node 40 / column B: network leg exactly 100 m);
        - a destination co-located with a node is reachable at its offset;
        - duplicate (column, seed) rows reduce to their minimum offset (SQL MIN);
        - a seed appearing in two columns keeps its per-column offset;
        - parallel edges reduce to their minimum cost (pgr directed:=false);
        - seeds and nodes absent from the edge graph yield -999, as pgRouting
          never returns vertices that appear in no edge.
        """
        import types

        import numpy as np
        import pandas as pd
        import setup_sp

        edges = pd.DataFrame(
            {
                'u': [10, 10, 20, 10, 50],
                'v': [20, 20, 30, 40, 60],
                'cost': [60.0, 90.0, 60.0, 100.0, 10.0],
            },
        )
        col_a = pd.DataFrame(
            {
                'dest_node': [30, 20, 20, 70],
                'offset': [5.0, 70.0, 80.0, 0.0],
            },
        )
        col_b = pd.DataFrame(
            {'dest_node': [10, 20], 'offset': [3.0, 1.0]},
        )

        def get_df(sql):
            if 'FROM edges' in sql:
                return edges.copy()
            if 'FROM layer_a' in sql:
                return col_a.copy()
            if 'FROM layer_b' in sql:
                return col_b.copy()
            raise AssertionError(f'unexpected query: {sql}')

        r = types.SimpleNamespace(get_df=get_df)
        node_index = pd.Index(
            [10, 20, 30, 40, 50, 60, 70],
            name='osmid',
        )
        result = setup_sp.cal_dist_nodes_to_nearest_pois_inmemory(
            r,
            [('layer_a', 'A', ''), ('layer_b', 'B', '')],
            distance=100,
            node_index=node_index,
            chunk_size=2,  # force multiple Dijkstra chunks
        )
        expected = pd.DataFrame(
            {
                'A': [130.0, 65.0, 5.0, -999.0, -999.0, -999.0, -999.0],
                'B': [3.0, 1.0, 61.0, 103.0, -999.0, -999.0, -999.0],
            },
            index=node_index,
        )
        pd.testing.assert_frame_equal(result, expected)

        # the graph loader reduced the 10-20 parallel edge pair to 60 m
        graph, node_ids = setup_sp.load_network_graph(r)
        self.assertEqual(node_ids.tolist(), [10, 20, 30, 40, 50, 60])
        self.assertEqual(graph[0, 1], 60.0)

    def test_0_22_nearest_poi_query_columns(self):
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

    def test_0_23_neighbourhood_reachable_nodes(self):
        """In-memory neighbourhood search matches networkx all-pairs Dijkstra.

        On a synthetic network with parallel edges, an exactly-at-cutoff node
        and an isolated source, the reachable node sets must equal networkx's
        (inclusive cutoff), and each yielded sequence must be ordered
        nearest-first (networkx's discovery order).
        """
        import networkx as nx
        import numpy as np
        import setup_sp

        u = [1, 1, 2, 1, 3]
        v = [2, 2, 3, 3, 4]
        w = [50.0, 80.0, 50.0, 120.0, 100.0]
        cutoff = 100
        sources = np.array([1, 5, 3], dtype='int64')  # 5 is isolated

        graph, node_ids = setup_sp.graph_from_edge_arrays(u, v, w)
        reached = list(
            setup_sp.neighbourhood_reachable_nodes(
                graph,
                node_ids,
                sources,
                cutoff,
                chunk_size=2,
                progress=False,
            ),
        )

        g = nx.MultiGraph()
        for a, b, length in zip(u, v, w):
            g.add_edge(a, b, length=length)
        for source, result in zip(sources, reached):
            if source not in g:
                self.assertEqual(result.tolist(), [source])
                continue
            lengths = nx.single_source_dijkstra_path_length(
                g,
                source,
                cutoff=cutoff,
                weight='length',
            )
            # same reachable set as networkx (inclusive cutoff)
            self.assertEqual(set(result.tolist()), set(lengths))
            # nearest-first ordering
            dists = [lengths[node] for node in result.tolist()]
            self.assertEqual(dists, sorted(dists))
        # spot-check the exactly-at-cutoff inclusions: from 3, both 1 (50+50)
        # and 4 (100) lie at exactly the cutoff and must be included
        self.assertEqual(set(reached[2].tolist()), {3, 2, 1, 4})

    def test_0_24_sample_point_indicators_no_fragmentation(self):
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

    def test_0_25_grid_mean_summariser_bit_equality(self):
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

    def test_0_26_r_python_comparison_metrics(self):
        """R-vs-Python comparison metrics on known synthetic data."""
        import compare_cycling_r_python as cmp
        import pandas as pd

        # binary_agreement: R [1,1,1,0,0] vs Py [1,1,0,0,1]
        # both=2, r_only=1, py_only=1, neither=1 -> agreement 60%
        s = cmp.binary_agreement([1, 1, 1, 0, 0], [1, 1, 0, 0, 1])
        self.assertEqual(s['n'], 5)
        self.assertAlmostEqual(s['agreement_pct'], 60.0)
        self.assertAlmostEqual(s['r_pct'], 60.0)
        self.assertAlmostEqual(s['py_pct'], 60.0)
        self.assertEqual((s['py_only'], s['r_only']), (1, 1))
        # perfect agreement -> kappa 1
        s2 = cmp.binary_agreement([1, 0, 1, 0], [1, 0, 1, 0])
        self.assertAlmostEqual(s2['kappa'], 1.0)
        # rows with a missing value in either series are dropped
        self.assertEqual(cmp.binary_agreement([1, None, 0], [1, 1, 0])['n'], 2)

        # ordinal_confusion (LTS): exact 3/5, all within +/-1
        o = cmp.ordinal_confusion([1, 2, 3, 4, 2], [1, 2, 4, 4, 1])
        self.assertAlmostEqual(o['exact_pct'], 60.0)
        self.assertAlmostEqual(o['within1_pct'], 100.0)
        self.assertAlmostEqual(o['mean_abs_diff'], 0.4)
        self.assertEqual(o['confusion'].shape, (4, 4))

        # class_shares, unweighted and length-weighted
        cs = cmp.class_shares([1, 1, 2, 3], labels=[1, 2, 3, 4])
        self.assertAlmostEqual(cs.loc[1], 50.0)
        self.assertAlmostEqual(cs.loc[4], 0.0)
        csw = cmp.class_shares([1, 2], [10, 30], labels=[1, 2])
        self.assertAlmostEqual(csw.loc[1], 25.0)
        self.assertAlmostEqual(csw.loc[2], 75.0)

        # compare_sample_points: string vs int point_id join + pt_any fallback
        r_sp = pd.DataFrame(
            {
                'point_id': ['10', '20', '30', '40'],
                'fresh_food_market_safe_2km': [1, 1, 0, 0],
                'pt_20min_or_any_safe_2km': [1, 0, 1, 0],
            },
        )
        py_sp = pd.DataFrame(
            {
                'point_id': [10, 20, 30, 40, 99],
                'sp_cycle_access_fresh_food_market_2000m': [1, 1, 0, 1, 0],
                'sp_cycle_access_pt_any_2000m': [1, 0, 1, 1, 0],
            },
        )
        mapping = [
            (
                'fresh_food_market_safe_2km',
                'sp_cycle_access_fresh_food_market_2000m',
                'Food 2km',
            ),
            (
                'pt_20min_or_any_safe_2km',
                'sp_cycle_access_pt_frequent_2000m',
                'PT 2km',
            ),
        ]
        table, n = cmp.compare_sample_points(r_sp, py_sp, mapping)
        self.assertEqual(n, 4)  # point 99 is Python-only
        self.assertAlmostEqual(table.iloc[0]['agreement_pct'], 75.0)
        self.assertIn('pt_any fallback', table.iloc[1]['indicator'])

        # resolve_sp_mapping: vintage coupling (old R pt_any -> Python pt_any;
        # new R pt_20min_or_any -> Python pt_frequent; POS prefers 'large')
        py_cols = [
            'sp_cycle_access_fresh_food_market_2000m',
            'sp_cycle_access_public_open_space_large_2000m',
            'sp_cycle_access_public_open_space_any_2000m',
            'sp_cycle_access_pt_frequent_2000m',
            'sp_cycle_access_pt_any_2000m',
            'sp_cycle_access_all_strict_2000m',
            'sp_cycle_access_activity_centre_local_2000m',
        ]
        old = {
            r: p
            for r, p, _ in cmp.resolve_sp_mapping(
                ['pt_any_safe_2km', 'public_open_space_safe_2km'],
                py_cols,
                [2000],
            )
        }
        self.assertEqual(
            old['pt_any_safe_2km'],
            'sp_cycle_access_pt_any_2000m',
        )
        self.assertEqual(
            old['public_open_space_safe_2km'],
            'sp_cycle_access_public_open_space_large_2000m',
        )
        new = cmp.resolve_sp_mapping(
            ['pt_20min_or_any_safe_2km'],
            py_cols,
            [2000],
        )
        self.assertEqual(new[0][1], 'sp_cycle_access_pt_frequent_2000m')

        # distribution comparison needs no point_id alignment (different n)
        dt = cmp.compare_sample_point_distributions(
            pd.DataFrame({'pt_any_safe_2km': [1, 1, 0, 0, 1]}),  # R 60%
            pd.DataFrame(
                {'sp_cycle_access_pt_any_2000m': [1, 1, 1, 0]},
            ),  # Py 75%
            [('pt_any_safe_2km', 'sp_cycle_access_pt_any_2000m', 'PT')],
        ).iloc[0]
        self.assertAlmostEqual(dt['R %'], 60.0)
        self.assertAlmostEqual(dt['Python %'], 75.0)
        self.assertAlmostEqual(dt['delta_py_minus_r'], 15.0)

        # python_only_access_indicators flags the port's extra coverage
        extra = cmp.python_only_access_indicators(
            pd.DataFrame(columns=py_cols),
            new,
        )
        self.assertIn('sp_cycle_access_activity_centre_local_2000m', extra)

    def test_10_0_series_yaml_schema(self):
        """Series configuration schema accepts valid and rejects invalid files."""
        import tempfile

        from subprocesses.validate_config import validate_yaml_schema

        schema = './configuration/regions/series-json-schema.json'
        valid = """
name: Example
country: Spain
description: Test series
timepoints:
  - region: ES_Las_Palmas_2025
    label: '2025'
  - region: ES_Las_Palmas_2025_t2
    label: '2026'
    policy_review: false
reference: '2025'
alignment:
  centroid_tolerance_m: 10
  min_shared_fraction: 0.95
equity:
  quantiles: [0.1, 0.5, 0.9]
  stratification:
    - name: districts
      aggregation: school_districts_grid_pop
      stratifier_column: quintile
      n_groups: 5
"""
        # invalid: only one timepoint, and an unknown top-level key
        invalid_cases = [
            valid.replace(
                """  - region: ES_Las_Palmas_2025_t2
    label: '2026'
    policy_review: false
""",
                '',
            ),
            valid + '\nunexpected_key: true\n',
        ]
        with tempfile.TemporaryDirectory() as folder:
            valid_path = f'{folder}/valid_series.yml'
            with open(valid_path, 'w') as file:
                file.write(valid)
            self.assertTrue(validate_yaml_schema(valid_path, schema))
            for i, case in enumerate(invalid_cases):
                invalid_path = f'{folder}/invalid_series_{i}.yml'
                with open(invalid_path, 'w') as file:
                    file.write(case)
                self.assertFalse(validate_yaml_schema(invalid_path, schema))

    def test_10_1_change_metrics(self):
        """Change metrics route bounded/unbounded indicators appropriately."""
        import numpy as np
        import pandas as pd
        from subprocesses import longitudinal

        panel = pd.DataFrame(
            {
                'grid_id': [1, 2, 1, 2, 1, 2, 1, 2],
                'timepoint': ['2016'] * 4 + ['2021'] * 4,
                'indicator': [
                    'pct_access_500m_pt_any_score',
                    'pct_access_500m_pt_any_score',
                    'local_nh_population_density',
                    'local_nh_population_density',
                ]
                * 2,
                'value': [50.0, 0.0, 100.0, 0.0, 75.0, 20.0, 110.0, 5.0],
                'pop_est': [10] * 8,
            },
        )
        panel.attrs['timepoints'] = ['2016', '2021']
        change = longitudinal.compute_change(panel)
        # bounded pct indicator: percentage point change only
        bounded = change.query(
            "indicator == 'pct_access_500m_pt_any_score'",
        )
        self.assertEqual(set(bounded['metric']), {'pp_change'})
        self.assertEqual(
            bounded.set_index('grid_id')['change'].to_dict(),
            {1: 25.0, 2: 20.0},
        )
        # unbounded indicator: diff and pct_change, with a zero baseline
        # yielding missing (not infinite) relative change
        unbounded = change.query(
            "indicator == 'local_nh_population_density'",
        )
        self.assertEqual(set(unbounded['metric']), {'diff', 'pct_change'})
        diff = unbounded.query("metric == 'diff'").set_index('grid_id')
        self.assertEqual(diff['change'].to_dict(), {1: 10.0, 2: 5.0})
        pct = unbounded.query("metric == 'pct_change'").set_index('grid_id')
        self.assertAlmostEqual(pct.loc[1, 'change'], 10.0)
        self.assertTrue(np.isnan(pct.loc[2, 'change']))
        # pairing options over three timepoints
        extra = panel.query("timepoint == '2021'").assign(timepoint='2026')
        three = pd.concat([panel, extra], ignore_index=True)
        three.attrs['timepoints'] = ['2016', '2021', '2026']

        def pairs(option):
            result = longitudinal.compute_change(three, pairs=option)
            return set(zip(result['t0'], result['t1']))

        self.assertEqual(
            pairs('reference'),
            {('2016', '2021'), ('2016', '2026')},
        )
        self.assertEqual(
            pairs('consecutive'),
            {('2016', '2021'), ('2021', '2026')},
        )
        self.assertEqual(
            pairs('all'),
            {('2016', '2021'), ('2016', '2026'), ('2021', '2026')},
        )

    def test_10_2_weighted_quantiles_and_gaps(self):
        """Weighted quantiles behave analytically; gaps suppress ratios for bounded indicators."""
        import numpy as np
        import pandas as pd
        from subprocesses import longitudinal

        # median of equally weighted values; min and max at the extremes
        np.testing.assert_allclose(
            longitudinal.weighted_quantile(
                [1, 2, 3],
                [1, 1, 1],
                [0, 0.5, 1],
            ),
            [1, 2, 3],
        )
        # cumulative weight midpoints are recovered exactly: for values
        # [1, 2] with weights [2, 1], the midpoints lie at 1/3 and 5/6
        np.testing.assert_allclose(
            longitudinal.weighted_quantile(
                [1, 2],
                [2, 1],
                [1 / 3, 5 / 6],
            ),
            [1, 2],
        )
        # a dominant weight pulls the median onto (nearly) that value
        self.assertAlmostEqual(
            longitudinal.weighted_quantile([1, 10], [1000, 1], 0.5)[0],
            1,
            delta=0.01,
        )
        # gaps: p90-p10 for a uniform 0..100 distribution, and change
        panel = pd.DataFrame(
            {
                'grid_id': list(range(11)) * 2,
                'timepoint': ['2016'] * 11 + ['2021'] * 11,
                'indicator': ['pct_access_500m_pt_any_score'] * 22,
                'value': [10.0 * i for i in range(11)]
                + [50.0] * 11,  # converged to 50 by 2021
                'pop_est': [1] * 22,
            },
        )
        panel.attrs['timepoints'] = ['2016', '2021']
        quantile_df = longitudinal.weighted_quantiles(panel)
        gaps = longitudinal.quantile_gaps(quantile_df)
        p90_p10 = gaps.query("statistic == 'p90_p10_gap'").set_index(
            'timepoint',
        )['value']
        self.assertGreater(p90_p10['2016'], 0)
        self.assertEqual(p90_p10['2021'], 0)
        gap_change = gaps.query(
            "statistic == 'p90_p10_gap_change' and timepoint == '2021'",
        )['value']
        self.assertAlmostEqual(
            gap_change.iloc[0],
            -p90_p10['2016'],
        )
        # ratio statistics are suppressed for bounded pct indicators
        self.assertNotIn('p90_p10_ratio', set(gaps['statistic']))
        # low/high end change classifies convergence
        ends = longitudinal.low_high_end_change(quantile_df)
        classification = ends.query('low_q == 0.1')['classification'].iloc[0]
        self.assertTrue(classification.startswith('converging'))

    def test_10_3_concentration_index(self):
        """Weighted Gini matches analytic cases; shortfall computed for bounded."""
        import numpy as np
        import pandas as pd
        from subprocesses import longitudinal

        # perfect equality
        self.assertAlmostEqual(
            longitudinal.gini([5, 5, 5, 5], [1, 1, 1, 1]),
            0,
        )
        # all value held by one of four equally weighted units:
        # G = sum|xi-xj| / (2 n^2 mean) = 6 / 8 = 0.75
        self.assertAlmostEqual(
            longitudinal.gini([1, 0, 0, 0], [1, 1, 1, 1]),
            0.75,
        )
        # weighting equivalence: duplicating equals doubling the weight
        self.assertAlmostEqual(
            longitudinal.gini([1, 0, 0], [1, 2, 1]),
            longitudinal.gini([1, 0, 0, 0], [1, 1, 1, 1]),
        )
        panel = pd.DataFrame(
            {
                'grid_id': [1, 2, 3, 4],
                'timepoint': ['2016'] * 4,
                'indicator': ['pct_access_500m_pt_any_score'] * 4,
                'value': [100.0, 0.0, 0.0, 0.0],
                'pop_est': [1] * 4,
            },
        )
        panel.attrs['timepoints'] = ['2016']
        concentration = longitudinal.concentration_index(panel)
        statistics = concentration.set_index('statistic')['value']
        self.assertAlmostEqual(statistics['gini'], 0.75)
        # shortfall Gini (of 100 - value) diverges from attainment Gini
        self.assertAlmostEqual(statistics['shortfall_gini'], 0.25)
        self.assertAlmostEqual(statistics['weighted_mean'], 25.0)

    def test_10_4_stratified_summary(self):
        """Stratified summaries: weighted means, gaps and trends by stratum."""
        import pandas as pd
        from subprocesses import longitudinal

        # two areas per stratum, three timepoints; the low stratum (1)
        # improves by 10 per period, the high stratum (5) is static
        rows = []
        for year, timepoint in [
            (2016, '2016'),
            (2021, '2021'),
            (2026, '2026'),
        ]:
            for area, stratum, base in [
                (1, 1, 20.0),
                (2, 1, 40.0),
                (3, 5, 80.0),
                (4, 5, 90.0),
            ]:
                value = base + (year - 2016) * 2 if stratum == 1 else base
                rows.append(
                    {
                        'area_id': area,
                        'timepoint': timepoint,
                        'year': year,
                        'indicator': 'pct_access_500m_pt_any_score',
                        'value': value,
                        'pop_est': 100,
                    },
                )
        panel = pd.DataFrame(rows)
        panel.attrs['timepoints'] = ['2016', '2021', '2026']
        stratifier = pd.DataFrame(
            {'area_id': [1, 2, 3, 4], 'quintile': [1, 1, 5, 5]},
        )
        summary = longitudinal.stratified_summary(
            panel,
            stratifier,
            'quintile',
        )
        means = summary.query("statistic == 'weighted_mean'").set_index(
            ['timepoint', 'stratum'],
        )['value']
        self.assertAlmostEqual(means[('2016', 1)], 30.0)
        self.assertAlmostEqual(means[('2026', 1)], 50.0)
        self.assertAlmostEqual(means[('2016', 5)], 85.0)
        gaps = summary.query("statistic == 'stratum_gap'").set_index(
            'timepoint',
        )['value']
        self.assertAlmostEqual(gaps['2016'], 55.0)
        self.assertAlmostEqual(gaps['2026'], 35.0)
        gap_change = summary.query(
            "statistic == 'stratum_gap_change' and timepoint == '2026'",
        )['value'].iloc[0]
        self.assertAlmostEqual(gap_change, -20.0)
        trends = summary.query("statistic == 'trend_per_year'").set_index(
            'stratum',
        )['value']
        self.assertAlmostEqual(trends[1], 2.0)
        self.assertAlmostEqual(trends[5], 0.0)

    def test_10_7_series_variant_configuration(self):
        """A region configuration's series block defines resolvable variants."""
        import copy

        from subprocesses import longitudinal

        # override merging: recursive, null removes, _replace replaces
        base = {
            'year': 2021,
            'network': {'intersection_tolerance': 12, 'buffered_region': True},
            'gtfs_feeds': {'folder': 'a', 'feed_a.zip': {'gtfs_year': 2021}},
            'notes': 'base',
        }
        original = copy.deepcopy(base)
        merged = ghsci.merge_overrides(
            base,
            {
                'network': {'intersection_tolerance': 8},
                'gtfs_feeds': {
                    '_replace': True,
                    'folder': 'b',
                    'feed_b.zip': {'gtfs_year': 2016},
                },
                'notes': None,
            },
        )
        self.assertEqual(base, original)
        self.assertEqual(
            merged['network'],
            {'intersection_tolerance': 8, 'buffered_region': True},
        )
        self.assertEqual(
            merged['gtfs_feeds'],
            {'folder': 'b', 'feed_b.zip': {'gtfs_year': 2016}},
        )
        self.assertNotIn('notes', merged)
        self.assertNotIn('_replace', merged['gtfs_feeds'])

        # a copy of the example configuration defining a series
        reference = 'ES_Las_Palmas_2025'
        base_codename = 'ES_Las_Palmas_2025_seriestest'
        path = f'./configuration/regions/{base_codename}.yml'
        with open(ghsci.get_region_config_path(reference)) as file:
            configuration = file.read()
        self.assertNotIn('\nseries:', configuration)
        configuration += """
series:
  reference: base
  timepoints:
    base:
      label: '2025'
    t2:
      label: '2026'
      year: 2026
      overrides:
        network:
          intersection_tolerance: 8
"""
        with open(path, 'w') as file:
            file.write(configuration)
        try:
            variant = f'{base_codename}_t2'
            resolved = ghsci.resolve_series_variant(variant)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved[1:], (base_codename, 't2'))
            self.assertIsNone(ghsci.resolve_series_variant(reference))
            r = ghsci.Region(variant)
            self.assertIsNotNone(r.config)
            self.assertEqual(r.codename, variant)
            self.assertEqual(r.config['db'], variant.lower())
            self.assertEqual(r.config['year'], 2026)
            self.assertEqual(r.config['network']['intersection_tolerance'], 8)
            self.assertIn('buffered_region', r.config['network'])
            self.assertNotIn('series', r.config)
            self.assertEqual(r.config['series_variant']['key'], 't2')
            self.assertTrue(r.config['yaml'].endswith('::t2'))
            self.assertTrue(r._stable_grid_ids())
            # reconstructed from its configuration reference, as by the
            # analysis subprocesses
            r_again = ghsci.Region(r.config['yaml'])
            self.assertEqual(r_again.codename, variant)
            self.assertEqual(r_again.config['year'], 2026)
            r.engine.dispose()
            r_again.engine.dispose()
            # the series, as a series configuration
            config = longitudinal.load_series_config(base_codename)
            self.assertEqual(config['codename'], f'{base_codename}_series')
            self.assertEqual(len(config['timepoints']), 2)
            self.assertEqual(config['reference'], '2025')
            description = longitudinal.describe_series(base_codename)
            self.assertEqual(
                set(description['codename']),
                {f'{base_codename}_base', variant},
            )
            self.assertTrue(description['exists'].any())
        finally:
            os.remove(path)

    def test_10_8_stratified_inequality_and_lookup(self):
        """Time-matched strata, slope/relative inequality indices and lookups."""
        import tempfile

        import numpy as np
        import pandas as pd
        from subprocesses import longitudinal

        # two timepoints stratified by different areas (as for SA1 editions)
        rows = []
        for timepoint, year, areas in [
            ('2016', 2016, [(101, 40.0), (102, 60.0)]),
            ('2021', 2021, [(201, 50.0), (202, 60.0)]),
        ]:
            for area, value in areas:
                rows.append(
                    {
                        'area_id': area,
                        'timepoint': timepoint,
                        'year': year,
                        'indicator': 'pct_access_500m_pt_any_score',
                        'value': value,
                        'pop_est': 100,
                    },
                )
        panel = pd.DataFrame(rows)
        panel.attrs['timepoints'] = ['2016', '2021']
        stratifier = pd.DataFrame(
            {
                'area_id': ['101', '102', '201', '202'],
                'decile': [1, 2, 1, 2],
                'timepoint': ['2016', '2016', '2021', '2021'],
            },
        )
        summary = longitudinal.stratified_summary(panel, stratifier, 'decile')
        means = summary.query("statistic == 'weighted_mean'").set_index(
            ['timepoint', 'stratum'],
        )['value']
        self.assertAlmostEqual(means[('2016', 1)], 40.0)
        self.assertAlmostEqual(means[('2021', 1)], 50.0)
        indices = summary.query("stratum == 'all'").set_index(
            ['statistic', 'timepoint'],
        )['value']
        # equal shares: ranks 0.25 and 0.75, slope = difference / 0.5
        self.assertAlmostEqual(indices[('sii', '2016')], 40.0)
        self.assertAlmostEqual(indices[('rii', '2016')], 70.0 / 30.0)
        self.assertAlmostEqual(indices[('sii', '2021')], 20.0)
        self.assertAlmostEqual(indices[('sii_change', '2021')], -20.0)
        # fewer than three distinct years: no trend estimates
        self.assertNotIn('trend_per_year', set(summary['statistic']))

        # an Excel lookup table with header rows and trailing notes
        with tempfile.TemporaryDirectory() as folder:
            workbook = f'{folder}/indexes.xlsx'
            table = pd.DataFrame(
                {
                    'code': ['101', '102', '© notes'],
                    'score': [900.5, 1100.2, np.nan],
                    'decile': [1, 10, np.nan],
                },
            )
            table.to_excel(
                workbook,
                sheet_name='Table 1',
                startrow=3,
                index=False,
            )
            lookup = longitudinal.read_lookup(
                {
                    'data': workbook,
                    'sheet': 'Table 1',
                    'skiprows': 4,
                    'header': None,
                    'usecols': 'A:C',
                    'names': ['sa1', 'irsd_score', 'irsd_decile'],
                },
            )
        self.assertEqual(
            list(lookup.columns),
            ['sa1', 'irsd_score', 'irsd_decile'],
        )
        self.assertEqual(len(lookup), 3)
        self.assertEqual(
            list(longitudinal._as_id(pd.Series([101.0, 102.0]))),
            ['101', '102'],
        )

    def test_10_9_access_profile_longitudinal_styles(self):
        """Longitudinal access profiles render in change, grouped and marker styles."""
        import tempfile

        import pandas as pd
        from subprocesses import longitudinal_plots

        indicators = [
            'Food market',
            'Convenience store',
            'Public transport stop',
            'Any public open space',
            'Large public open space',
        ]
        phrases = {
            'Population % with access within 500m to...': (
                '% of population with access within 500m to:'
            ),
            'locale': 'en',
            'city_name': 'Test city',
            '25 city comparison': '25 city comparison',
            'Large public open space': 'Large public open space',
        }

        class StubRegion:
            codename = 'stub'

            def __init__(self, values):
                self.values = values

            def get_city_stats(self, phrases=None):
                return {
                    'access': pd.Series(self.values, index=indicators),
                    'percentiles': {
                        'p25': [20] * len(indicators),
                        'p50': [40] * len(indicators),
                        'p75': [60] * len(indicators),
                    },
                }

        class StubTimepoint:
            def __init__(self, label, values):
                self.label = label
                self.year = int(label)
                self.region = StubRegion(values)
                self.codename = f'stub_{label}'

        class StubSeries:
            def __init__(self, timepoints):
                self.timepoints = timepoints
                self.reference = timepoints[0]
                self.config = {}

        three = StubSeries(
            [
                StubTimepoint('2016', [30, 50, 70, 90, 60]),
                StubTimepoint('2021', [35, 48, 75, 91, 62]),
                StubTimepoint('2026', [42, 45, 80, 92, 70]),
            ],
        )
        with tempfile.TemporaryDirectory() as folder:
            for style, kwargs in [
                ('change', {}),
                ('change', {'timepoints': ['2021', '2026']}),
                ('grouped', {}),
                ('markers', {'show_reference': True}),
                ('auto', {}),
            ]:
                path = f'{folder}/access_profile_{style}_{len(kwargs)}.png'
                result = longitudinal_plots.access_profile_longitudinal(
                    three,
                    phrases=phrases,
                    style=style,
                    path=path,
                    **kwargs,
                )
                self.assertEqual(result, path)
                self.assertGreater(os.path.getsize(path), 0)
        with self.assertRaises(ValueError):
            longitudinal_plots.access_profile_longitudinal(
                three,
                phrases=phrases,
                style='unknown',
            )
        self.assertEqual(
            longitudinal_plots._format_point_change(4.25, phrases),
            '+4.2 pp',
        )

    def test_10_5_alignment_validation(self):
        """Grid alignment validation flags offsets, growth and disjoint grids."""
        import pandas as pd
        from subprocesses import longitudinal

        def frame(ids, offset=0.0):
            return pd.DataFrame(
                {
                    'grid_id': ids,
                    'centroid_x': [100.0 * i + offset for i in ids],
                    'centroid_y': [100.0 * i for i in ids],
                },
            )

        reference = frame(range(100))
        # identical grid: ok
        report = longitudinal.validate_grid_alignment(
            {'ref': reference, 'same': frame(range(100))},
            'ref',
        )
        self.assertEqual(report['same']['status'], 'ok')
        self.assertEqual(report['same']['n_new'], 0)
        # urban growth (reference is a subset): still ok, new cells noted
        report = longitudinal.validate_grid_alignment(
            {'ref': reference, 'grown': frame(range(120))},
            'ref',
        )
        self.assertEqual(report['grown']['status'], 'ok')
        self.assertEqual(report['grown']['n_new'], 20)
        self.assertEqual(report['grown']['shared_fraction'], 1.0)
        # centroid offset beyond tolerance: warn
        report = longitudinal.validate_grid_alignment(
            {'ref': reference, 'shifted': frame(range(100), offset=25.0)},
            'ref',
            centroid_tolerance_m=10,
        )
        self.assertEqual(report['shifted']['status'], 'warn')
        self.assertAlmostEqual(report['shifted']['max_offset_m'], 25.0)
        # mostly disjoint grid identifiers: error
        report = longitudinal.validate_grid_alignment(
            {'ref': reference, 'other': frame(range(90, 200))},
            'ref',
        )
        self.assertEqual(report['other']['status'], 'error')
        # missing centroids fall back to identifier-only comparison
        report = longitudinal.validate_grid_alignment(
            {
                'ref': reference[['grid_id']],
                'ids': frame(range(100))[['grid_id']],
            },
            'ref',
        )
        self.assertEqual(report['ids']['method'], 'grid_id_only')
        self.assertEqual(report['ids']['status'], 'ok')

    def test_10_6_longitudinal_report_configuration(self):
        """Longitudinal template worksheets, phrases and page maps are consistent."""
        import pandas as pd
        from subprocesses.longitudinal_report import (
            LONGITUDINAL_PHRASES,
            LONGITUDINAL_TEMPLATE_PAGES,
        )

        try:
            reports = ghsci.reports
        except NameError:
            # ghsci requires the container environment; the reports
            # dict consistency check then runs in-container only
            reports = None
        # elements each template's inserters fill, by logical page
        required_elements = {
            'introduction': ['introduction'],
            'access_profile': ['access_profile'],
            'pt': ['pt_small_multiples', 'pt_change_map'],
            'pos': ['pos_small_multiples', 'pos_change_map'],
            'distribution': ['quantile_bands', 'threshold_trends'],
            'equity': ['equity_stratified', 'equity_dumbbell'],
            'policy_trend': [
                'presence_rating_longitudinal',
                'quality_rating_longitudinal',
            ],
            'policy_comparison': ['policy_comparison_table'],
        }
        for xlsx in [
            './configuration/_report_configuration.xlsx',
            './configuration/templates/_report_configuration.xlsx',
        ]:
            book = pd.ExcelFile(xlsx)
            languages = pd.read_excel(xlsx, sheet_name='languages').fillna(
                '',
            )
            english = languages.set_index('name')['English']
            reference_columns = list(
                pd.read_excel(xlsx, sheet_name='spatial').columns,
            )
            for template, page_map in LONGITUDINAL_TEMPLATE_PAGES.items():
                # worksheet exists with the standard element schema
                self.assertIn(template, book.sheet_names, xlsx)
                elements = pd.read_excel(xlsx, sheet_name=template)
                self.assertEqual(
                    list(elements.columns),
                    reference_columns,
                    f'{xlsx}:{template}',
                )
                # every mapped physical page exists in the worksheet
                pages = set(elements['page'])
                for logical, page in page_map.items():
                    self.assertIn(
                        page,
                        pages,
                        f'{xlsx}:{template}: page {page} ({logical})',
                    )
                    for name in required_elements.get(logical, []):
                        self.assertIn(
                            name,
                            set(
                                elements.loc[
                                    elements['page'] == page,
                                    'name',
                                ],
                            ),
                            f'{xlsx}:{template} page {page}: {name}',
                        )
                # back page carries the template's summary element
                self.assertIn(
                    f'summary_{template}',
                    set(
                        elements.loc[
                            elements['page'] == page_map['back'],
                            'name',
                        ],
                    ),
                    f'{xlsx}:{template}',
                )
                # reports dict title phrase is translated in English
                if reports is not None:
                    self.assertIn(template, reports, template)
                    title_key = reports[template]
                    self.assertIn(title_key, english.index, xlsx)
                    self.assertNotEqual(
                        str(english[title_key]).strip(),
                        '',
                        title_key,
                    )
            # longitudinal phrase rows exist with English defaults
            for phrase in LONGITUDINAL_PHRASES:
                self.assertIn(phrase, english.index, f'{xlsx}: {phrase}')
                self.assertNotEqual(
                    str(english[phrase]).strip(),
                    '',
                    f'{xlsx}: {phrase}',
                )

    def test_0_27_configured_resolution(self):
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

    def test_0_28_reproject_raster_resolution(self):
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

    def test_0_29_custom_aggregation_keep_columns(self):
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

    def test_0_30_custom_aggregation_clip(self):
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

    def test_0_31_custom_aggregation_data_load(self):
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

    def test_0_51_custom_aggregation_join(self):
        """Attribute tables are read and prepared for linkage as configured."""
        import tempfile

        import pandas as pd
        from subprocesses import _12_aggregation

        join_specs = _12_aggregation.join_specs
        prepare = _12_aggregation.prepare_join_table

        # a single table or a list; the boundary identifier defaults to the
        # aggregation's own, and columns may be a comma-separated string
        spec = {
            'id': 'MB_CODE21',
            'join': {'data': 'counts.csv', 'id': 'MB_CODE_2021'},
        }
        (join,) = join_specs(spec)
        self.assertEqual(join['boundary_id'], 'MB_CODE21')
        self.assertIsNone(join['columns'])
        joins = join_specs(
            {
                'join': [
                    {
                        'data': 'a.csv',
                        'id': 'code',
                        'columns': 'Dwelling, Person',
                    },
                    {
                        'data': 'b.csv',
                        'id': 'code',
                        'boundary_id': 'other',
                        'columns': ['x'],
                    },
                ],
            },
        )
        self.assertEqual(joins[0]['boundary_id'], 'ogc_fid')
        self.assertEqual(joins[0]['columns'], ['Dwelling', 'Person'])
        self.assertEqual(joins[1]['boundary_id'], 'other')
        self.assertEqual(join_specs({}), [])
        with self.assertRaises(ValueError):
            join_specs({'join': {'data': 'counts.csv'}})

        with tempfile.TemporaryDirectory() as tmp:
            # a CSV, with codes too long to survive as floats, one written
            # as a float, and a footnote row as in ABS releases
            csv = f'{tmp}/counts.csv'
            with open(csv, 'w', encoding='cp1252') as f:
                f.write(
                    'MB_CODE_2016,Dwelling,Person,State\n'
                    '20000009499,,12288,2\n'
                    '20000010000,42,69,2\n'
                    '20000020000.0,3,5,2\n'
                    ',,,\n'
                    '© Commonwealth of Australia 2017,,,\n',
                )
            linked = prepare(
                join_specs(
                    {
                        'join': {
                            'data': csv,
                            'id': 'MB_CODE_2016',
                            'columns': 'Dwelling, Person',
                        },
                    },
                )[0],
            )
            self.assertEqual(
                list(linked.columns),
                ['id', 'dwelling', 'person'],
            )
            self.assertEqual(
                list(linked['id'])[:3],
                ['20000009499', '20000010000', '20000020000'],
            )
            self.assertEqual(linked['person'].iloc[:3].sum(), 12362)
            # all columns other than the identifier by default
            linked = prepare(
                join_specs({'join': {'data': csv, 'id': 'MB_CODE_2016'}})[0],
            )
            self.assertEqual(
                list(linked.columns),
                ['id', 'dwelling', 'person', 'state'],
            )
            # absent identifiers or columns are reported, not ignored
            for join in [
                {'data': csv, 'id': 'MB_CODE_2021'},
                {'data': csv, 'id': 'MB_CODE_2016', 'columns': 'Persons'},
            ]:
                with self.subTest(join=join):
                    with self.assertRaises(ValueError):
                        prepare(join_specs({'join': join})[0])
            # duplicated identifiers would link a boundary more than once
            duplicated = f'{tmp}/duplicated.csv'
            pd.DataFrame({'code': ['1', '1'], 'n': [1, 2]}).to_csv(
                duplicated,
                index=False,
            )
            with self.assertRaises(ValueError):
                prepare(
                    join_specs({'join': {'data': duplicated, 'id': 'code'}})[
                        0
                    ],
                )

            # a release spread over several worksheets, below title rows
            workbook = f'{tmp}/counts.xlsx'
            with pd.ExcelWriter(workbook) as writer:
                for sheet, codes in [
                    ('Table 1', ['0101', '0102']),
                    ('Table 1.1', ['0103']),
                ]:
                    pd.DataFrame(
                        {'CODE': codes, 'Person': range(len(codes))},
                    ).to_excel(
                        writer,
                        sheet_name=sheet,
                        startrow=2,
                        index=False,
                    )
            linked = prepare(
                join_specs(
                    {
                        'join': {
                            'data': workbook,
                            'id': 'CODE',
                            'sheet': ['Table 1', 'Table 1.1'],
                            'skiprows': 2,
                        },
                    },
                )[0],
            )
            # leading zeros are retained, as identifiers are read as text
            self.assertEqual(list(linked['id']), ['0101', '0102', '0103'])
            self.assertEqual(list(linked.columns), ['id', 'person'])

    def test_0_32_data_key_synonym(self):
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

    def test_0_33_region_configuration_discovery(self):
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

    def test_0_34_gtfs_folder_resolution(self):
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

    def test_0_35_retired_codename(self):
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
                    # a retired codename whose configuration is still
                    # present is still loaded, so that results analysed
                    # under it may be revisited or compared
                    self.assertIsNotNone(r.config)
                else:
                    # otherwise, no configuration is loaded and the region
                    # reports as such, rather than prompting to initialise
                    # a new study region
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

    def test_0_36_retired_codename_with_configuration(self):
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

    def test_0_37_compare_reports_regions_that_did_not_load(self):
        """Comparison with a region that did not load is reported clearly."""
        import compare
        from subprocesses import ghsci

        codename = 'example_ES_Las_Palmas_2023-ee'
        if os.path.isfile(ghsci.get_region_config_path(codename)):
            self.skipTest(f'A configuration exists for {codename}')
        with self.assertRaises(ValueError):
            compare.resolve_regions(codename, ghsci.example())

    def test_0_38_output_variables_resolve(self):
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

    def test_0_39_reference_data_dictionary(self):
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

    def test_0_40_wampi_reproduces_published(self):
        """The weighted Adjusted MPI reproduces Mazziotta & Pareto (2022).

        Table 2 of 'Weighting in composite indices construction: the case of
        the Mazziotta-Pareto Index': goalposts are each indicator's minimum
        and maximum, and its reference value the mean.
        """
        import pandas as pd
        from subprocesses import _composite_index as ci

        data = pd.DataFrame(
            {
                'X1': [110, 90, 70, 50, 30],
                'X2': [1, 3, 3, 3, 1],
                'X3': [0.4, 0.2, 0.8, 0.2, 0.4],
            },
        )
        cases = {
            (1, 1, 1): [90.6, 102.9, 119.1, 92.3, 74.8],
            (0.6, 0.2, 0.2): [104.6, 107.7, 110.4, 88.9, 72.6],
            (0.2, 0.6, 0.2): [75.9, 110.8, 121.1, 103.5, 69.7],
            (0.2, 0.2, 0.6): [94.4, 91.8, 126.9, 86.5, 83.7],
        }
        for weights, expected in cases.items():
            spec = ci.normalise_index_spec(
                'example',
                {
                    'indicators': [
                        {'variable': c, 'polarity': 'positive', 'weight': w}
                        for c, w in zip(data.columns, weights)
                    ],
                },
            )
            prepared = ci.prepare(data, spec)
            params = ci.resolve_parameters(prepared, spec)
            scores = ci.score(prepared, spec, params)['sp_index_example']
            for value, published in zip(scores, expected):
                with self.subTest(weights=weights, published=published):
                    self.assertAlmostEqual(value, published, delta=0.051)
        # the normalised values themselves, for the first unit
        normalised = ci.normalise(prepared, params).iloc[0]
        self.assertAlmostEqual(normalised['X1'], 130.0)
        self.assertAlmostEqual(normalised['X2'], 64.0)
        self.assertAlmostEqual(normalised['X3'], 100.0)

    def test_0_41_wmpi_reproduces_published(self):
        """The weighted MPI reproduces Mazziotta & Pareto (2022), Table 1.

        Indicators are standardised using the population standard deviation.
        """
        import pandas as pd
        from subprocesses import _composite_index as ci

        data = pd.DataFrame(
            {
                'X1': [110, 90, 70, 50, 30],
                'X2': [1, 3, 3, 3, 1],
                'X3': [0.4, 0.2, 0.8, 0.2, 0.4],
            },
        )
        cases = {
            (1, 1, 1): [99.5, 101.4, 108.3, 96.7, 90.8],
            (0.6, 0.2, 0.2): [105.0, 103.6, 104.8, 95.1, 88.7],
            (0.2, 0.6, 0.2): [94.3, 104.0, 108.2, 101.0, 89.5],
            (0.2, 0.2, 0.6): [99.7, 96.9, 112.1, 94.3, 94.3],
        }
        for weights, expected in cases.items():
            spec = ci.normalise_index_spec(
                'example',
                {
                    'method': 'mpi',
                    'outliers': 'none',
                    'indicators': [
                        {'variable': c, 'polarity': 'positive', 'weight': w}
                        for c, w in zip(data.columns, weights)
                    ],
                },
            )
            prepared = ci.prepare(data, spec)
            params = ci.resolve_parameters(prepared, spec)
            scores = ci.score(prepared, spec, params)['sp_index_example']
            for value, published in zip(scores, expected):
                with self.subTest(weights=weights, published=published):
                    self.assertAlmostEqual(value, published, delta=0.051)
        z = ci.normalise(prepared, params).iloc[0]
        self.assertAlmostEqual(z['X1'], 114.1, delta=0.05)
        self.assertAlmostEqual(z['X2'], 87.8, delta=0.05)
        # the MPI defaults to the Urban Liveability Index outlier treatment
        self.assertEqual(
            ci.normalise_index_spec(
                'u',
                {'method': 'mpi', 'indicators': ['sp_walk_access_x_300m']},
            )['outliers'],
            'compress',
        )

    def test_0_42_ampi_time_comparison(self):
        """The AMPI reproduces Mazziotta & Pareto (2018), and compares over time.

        Table 1 of 'Measuring well-being over time: the Adjusted
        Mazziotta-Pareto Index versus other non-compensatory indices', with
        goalposts centred on the 2014 average.  Once goalposts are fixed, a
        unit's score depends only on its own values: scoring it alongside a
        later timepoint does not change it.
        """
        import tempfile

        import numpy as np
        import pandas as pd
        from subprocesses import _composite_index as ci

        countries = {
            'Australia': (82.0, 74, 72, 31197),
            'Austria': (81.1, 82, 73, 29256),
            'Belgium': (80.5, 71, 62, 27811),
            'Canada': (81.0, 89, 72, 30212),
            'Chile': (78.3, 72, 62, 13762),
            'Czech Rep.': (78.0, 92, 67, 17262),
            'Denmark': (79.9, 77, 73, 25172),
            'Estonia': (76.3, 89, 67, 14382),
            'Finland': (80.6, 84, 70, 26904),
            'France': (82.2, 72, 64, 29322),
            'Germany': (80.8, 86, 73, 30721),
            'Greece': (80.8, 67, 51, 19095),
            'Hungary': (75.0, 82, 57, 15240),
            'Ireland': (80.6, 73, 59, 23721),
            'Italy': (82.7, 56, 58, 24724),
            'Japan': (82.7, 93, 71, 25066),
            'Korea': (81.1, 81, 64, 18035),
            'Mexico': (74.4, 36, 61, 12850),
            'Netherlands': (81.3, 72, 75, 25697),
            'New Zealand': (81.2, 74, 72, 21773),
            'Norway': (81.4, 82, 76, 32093),
            'Poland': (76.9, 89, 60, 16234),
            'Portugal': (80.8, 35, 62, 18806),
            'Slovak Rep.': (76.1, 91, 60, 17228),
            'Slovenia': (80.1, 84, 64, 19692),
            'Spain': (82.4, 54, 56, 22799),
            'Sweden': (81.9, 87, 74, 27546),
            'Switzerland': (82.8, 86, 79, 30745),
            'U.K.': (81.1, 77, 71, 25828),
            'United States': (78.7, 89, 67, 39531),
        }
        t1 = pd.DataFrame.from_dict(
            countries,
            orient='index',
            columns=['X1', 'X2', 'X3', 'X4'],
        )
        spec = ci.normalise_index_spec(
            'wellbeing',
            {
                'indicators': [
                    {'variable': c, 'polarity': 'positive'} for c in t1.columns
                ],
            },
        )
        prepared = ci.prepare(t1, spec)
        params = ci.resolve_parameters(prepared, spec)
        scores = ci.score(prepared, spec, params)['sp_index_wellbeing']
        for country, published in {
            'Australia': 109.43,
            'Mexico': 68.11,
            'Switzerland': 117.64,
            'United States': 107.36,
            'Greece': 85.83,
        }.items():
            with self.subTest(country=country):
                self.assertAlmostEqual(scores[country], published, delta=0.02)

        # a later timepoint, with higher incomes throughout
        t2 = t1.assign(X4=t1['X4'] * 1.05)
        together = ci.score(
            ci.prepare(pd.concat([t1, t2.add_suffix(' (t2)', axis=0)]), spec),
            spec,
            params,
        )['sp_index_wellbeing']
        np.testing.assert_allclose(together.loc[t1.index], scores)
        later = together.loc[t2.index + ' (t2)'].to_numpy()
        self.assertTrue((later > scores.to_numpy()).all())

        # pooled goalposts span both timepoints, centred on the first
        pooled = ci.series_parameters(
            [prepared, ci.prepare(t2, spec)],
            spec,
            reference=0,
        )
        self.assertAlmostEqual(pooled['indicators']['X4']['sup'], 39531 * 1.05)
        self.assertAlmostEqual(
            pooled['indicators']['X4']['reference'],
            t1['X4'].mean(),
        )
        self.assertGreater(
            pooled['indicators']['X4']['max']
            - pooled['indicators']['X4']['min'],
            params['indicators']['X4']['max']
            - params['indicators']['X4']['min'],
        )

        # recorded parameters reproduce the scores when supplied again
        with tempfile.TemporaryDirectory() as folder:
            path = ci.save_parameters(
                os.path.join(folder, 'parameters.yml'),
                params,
            )
            frozen = ci.load_goalposts(path)
        self.assertIn('wellbeing', frozen)
        ci.check_parameters(spec, frozen['wellbeing'])
        np.testing.assert_allclose(
            ci.score(prepared, spec, frozen['wellbeing'])[
                'sp_index_wellbeing'
            ],
            scores,
        )

    def test_0_43_composite_index_helpers(self):
        """Transformations, polarity, domains and configuration checks."""
        import numpy as np
        import pandas as pd
        from subprocesses import _composite_index as ci

        # soft threshold: 0.5 at the threshold, and nothing found scores 0
        soft = ci.soft_threshold(pd.Series([0, 300, 600, None]), 300)
        self.assertAlmostEqual(soft[1], 0.5)
        self.assertAlmostEqual(soft[0], 1 / (1 + np.exp(-5)))
        self.assertGreater(soft[1], soft[2])
        self.assertEqual(soft[3], 0)

        # Urban Liveability Index outlier compression: an extreme value is
        # brought to three standard deviations; others are untouched
        values = pd.Series([0.0] * 20 + [100.0])
        stats = ci.compression_parameters(values)
        compressed = ci.compress_outliers(values, **stats)
        self.assertAlmostEqual(
            compressed.iloc[-1],
            stats['mean'] + 3 * stats['sd'],
        )
        self.assertTrue((compressed.iloc[:20] == 0).all())

        # polarity inferred from names where it can be, and required otherwise
        self.assertEqual(
            ci.infer_polarity('sp_walk_nearest_node_pharmacy'),
            ci.NEGATIVE,
        )
        self.assertEqual(
            ci.infer_polarity('sp_walk_nearest_node_pharmacy', True),
            ci.POSITIVE,
        )
        self.assertEqual(ci.infer_polarity('sp_euclid_dist_x'), ci.NEGATIVE)
        self.assertEqual(
            ci.infer_polarity('sp_walk_beyond_petrol_250m'),
            ci.POSITIVE,
        )
        with self.assertRaises(ValueError):
            ci.normalise_indicator({'variable': 'sp_urban_heat_guhvi'}, 'x')
        with self.assertRaises(ValueError):
            ci.normalise_indicator(
                {
                    'variable': 'sp_walk_access_x_300m',
                    'transform': {'soft_threshold': 300},
                },
                'x',
            )
        indicator = ci.normalise_indicator(
            {
                'variable': 'sp_walk_nearest_node_x',
                'transform': {'soft_threshold': 300},
            },
            'x',
        )
        self.assertEqual(indicator['id'], 'x')
        self.assertEqual(indicator['polarity'], ci.POSITIVE)

        # a negative indicator is the complement about 200 of a positive one
        frame = pd.DataFrame({'x': [1.0, 2.0, 3.0, 4.0]})
        normalised = {}
        for polarity in ('positive', 'negative'):
            spec = ci.normalise_index_spec(
                'p',
                {'indicators': [{'variable': 'x', 'polarity': polarity}]},
            )
            prepared = ci.prepare(frame, spec)
            normalised[polarity] = ci.normalise(
                prepared,
                ci.resolve_parameters(prepared, spec),
            )['x']
        np.testing.assert_allclose(
            normalised['negative'],
            200 - normalised['positive'],
        )

        # domains: an indicator that does not vary is left out, with a
        # warning; each domain is a composite of its indicators, and the index
        # a composite of its domains
        frame = pd.DataFrame(
            {
                'a': [0.0, 1.0, 2.0, 3.0],
                'c': [1.0, 2.0, np.nan, 4.0],
                'b': [3.0, 1.0, 2.0, 0.0],
                'd': [5.0, 5.0, 5.0, 5.0],
            },
        )
        config = {
            'domains': {
                'one': {
                    'indicators': [
                        {'variable': 'a', 'polarity': 'positive'},
                        {'variable': 'c', 'polarity': 'positive'},
                    ],
                },
                'two': {
                    'weight': 2,
                    'indicators': [
                        {'variable': 'b', 'polarity': 'negative'},
                        {'variable': 'd', 'polarity': 'positive'},
                    ],
                },
            },
        }
        spec = ci.normalise_index_spec('t', config)
        prepared = ci.prepare(frame, spec)
        with self.assertWarns(UserWarning):
            params = ci.resolve_parameters(prepared, spec)
        self.assertIn('d', params['dropped'])
        self.assertEqual(params['domains'], {'one': 1.0, 'two': 2.0})
        scores = ci.score(prepared, spec, params)
        np.testing.assert_allclose(
            scores['sp_index_t__two'],
            ci.normalise(prepared, params)['b'],
        )
        self.assertTrue(np.isnan(scores['sp_index_t__one'].iloc[2]))
        self.assertTrue(np.isnan(scores['sp_index_t'].iloc[2]))
        expected = ci.mpi_aggregate(
            scores[['sp_index_t__one', 'sp_index_t__two']],
            [1, 2],
        )['index']
        np.testing.assert_allclose(scores['sp_index_t'], expected)
        self.assertEqual(
            ci.index_columns(spec, indicators=False),
            [
                'index_t',
                'index_t_mean',
                'index_t_penalty',
                'index_t_n',
                'index_t__one',
                'index_t__two',
            ],
        )
        # requiring fewer indicators scores the row from those present
        relaxed = ci.normalise_index_spec('t', {**config, 'min_indicators': 1})
        self.assertFalse(
            np.isnan(
                ci.score(prepared, relaxed, params)['sp_index_t'].iloc[2],
            ),
        )
        # a balanced profile is penalised less than an unbalanced one with
        # the same mean
        balanced = ci.mpi_aggregate(
            pd.DataFrame({'x': [100.0, 90.0], 'y': [100.0, 110.0]}),
            [1, 1],
        )
        self.assertEqual(balanced['mean'][0], balanced['mean'][1])
        self.assertGreater(balanced['index'][0], balanced['index'][1])

        # configuration checks
        with self.assertRaises(ValueError):
            ci.normalise_index_spec(
                'Bad-Name',
                {'indicators': ['sp_walk_access_x_300m']},
            )
        with self.assertRaises(ValueError):
            ci.normalise_index_spec(
                'a' * 60,
                {'indicators': ['sp_walk_access_x_300m']},
            )
        with self.assertRaises(ValueError):
            ci.normalise_index_spec('t', {})
        with self.assertRaises(ValueError):
            ci.check_parameters(
                ci.normalise_index_spec(
                    't',
                    {
                        **config,
                        'domains': {**config['domains'], 'three': ['e_score']},
                    },
                ),
                params,
            )
        self.assertIsNone(
            ci.composite_index_config(type('R', (), {'config': {}})()),
        )

    def test_0_44_euclidean_catchments(self):
        """Straight-line catchment specifications, scores and descriptions."""
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _euclidean_accessibility as ea
        import _pedestrian_accessibility as ped
        import data_dictionary as dd
        import numpy as np
        import pandas as pd

        spec = ea.resolve_spec(
            {'name': 'police_station', 'data': 'x.gpkg', 'distances': [15000]},
        )
        self.assertEqual(spec['max_distance'], 15000)
        self.assertEqual(spec['direction'], 'access')
        for bad in (
            {'name': 'x', 'distances': [1000]},
            {'name': 'x', 'data': 'a', 'layer': 'b', 'distances': [1000]},
            {'name': 'x', 'data': 'a'},
            {'name': 'x', 'data': 'a', 'distances': [1000], 'max_distance': 5},
            {'name': 'X-1', 'data': 'a', 'distances': [1000]},
        ):
            with self.subTest(spec=bad), self.assertRaises(ValueError):
                ea.resolve_spec(bad)

        class _Region:
            def __init__(self, config):
                self.config = config

        catchments = {
            'euclidean': {
                'destinations': [
                    {
                        'name': 'police',
                        'layer': 'destinations',
                        'distances': [15000],
                    },
                ],
            },
        }
        region = _Region({'accessibility': catchments})
        self.assertEqual(
            ea.euclidean_config(region)['destinations'][0]['name'],
            'police',
        )
        # declaring catchments alone does not switch on the walking analysis
        self.assertIsNone(ped.pedestrian_config(region))
        self.assertIsNotNone(
            ped.pedestrian_config(
                _Region({'accessibility': {**catchments, 'pedestrian': {}}}),
            ),
        )
        self.assertIsNone(ea.euclidean_config(_Region({})))

        specs = [
            ea.resolve_spec(
                {'name': 'police', 'layer': 'd', 'distances': [15000]},
            ),
            ea.resolve_spec(
                {
                    'name': 'plant',
                    'layer': 'd',
                    'distances': [1000],
                    'direction': 'avoid',
                },
            ),
            ea.resolve_spec({'name': 'none', 'layer': 'd', 'distances': [1]}),
        ]
        distances = pd.DataFrame(
            {
                'sp_euclid_dist_police': [100.0, 20000.0, np.nan],
                'sp_euclid_dist_plant': [100.0, 20000.0, np.nan],
                'sp_euclid_dist_none': [np.nan, np.nan, np.nan],
            },
        )
        scores = ea.catchment_scores(distances, specs)
        self.assertEqual(
            scores['sp_euclid_access_police_15000m'].tolist(),
            [1.0, 0.0, 0.0],
        )
        self.assertEqual(
            scores['sp_euclid_beyond_plant_1000m'].tolist(),
            [0.0, 1.0, 1.0],
        )
        self.assertTrue(scores['sp_euclid_access_none_1m'].isna().all())

        for variable, category, units in (
            ('sp_euclid_dist_police', dd.CATCHMENT, ('metres', 'value')),
            (
                'sp_euclid_access_police_15000m',
                dd.CATCHMENT,
                ('score 0-1', 'value'),
            ),
            (
                'pct_access_euclid_police_15000m',
                dd.CATCHMENT,
                ('percent', 'percentage'),
            ),
            (
                'pop_pct_beyond_euclid_plant_1000m',
                dd.CATCHMENT,
                ('percent', 'percentage'),
            ),
            ('avg_euclid_dist_police', dd.CATCHMENT, ('metres', 'mean')),
            (
                'sp_index_uli',
                dd.COMPOSITE,
                ('index (100 = reference)', 'value'),
            ),
            (
                'index_uli__daily_living',
                dd.COMPOSITE,
                ('index (100 = reference)', 'mean'),
            ),
            (
                'pop_index_uli_penalty',
                dd.COMPOSITE,
                ('index (100 = reference)', 'mean'),
            ),
            ('index_uli_n', dd.COMPOSITE, ('count', 'mean')),
        ):
            with self.subTest(variable=variable):
                resolved_category, description = dd.describe_variable(variable)
                self.assertEqual(resolved_category, category)
                self.assertTrue(description)
                self.assertEqual(dd.describe_units(variable), units)

    def test_0_45_mexicali_uli_configuration(self):
        """The Mexicali ULI region's catchments and composite index resolve."""
        import yaml
        from subprocesses import _composite_index as ci
        from subprocesses import validate_config

        path = os.path.join('data', 'MX', 'MX_Mexicali_2025_ULI.yml')
        if not os.path.isfile(path):
            self.skipTest('The Mexicali ULI configuration is not present')
        with open(path, encoding='utf-8') as f:
            config = yaml.safe_load(f)
        self.assertTrue(
            validate_config.validate_config_dict(
                config,
                'configuration/regions/region-json-schema.json',
            ),
        )
        specs = ci.normalise_config(config['composite_indices'])
        self.assertIn('uli', specs)
        # the Adapted Urban Liveability Framework's domains, alphabetically
        # (in English) as the dashboard presents them, each with the figure's
        # colours and the variable sheet's definition; housing and the
        # sociodemographic characteristics are described but not scored
        uli = specs['uli']
        self.assertEqual(
            [d['name'] for d in uli['domains']],
            [
                'ambient_environment',
                'built_environment',
                'economic_development',
                'housing',
                'mobility_transport',
                'safety',
                'social_infrastructure',
                'sociodemographics',
            ],
        )
        self.assertEqual(
            [d['name'] for d in uli['domains'] if not d['scored']],
            ['housing', 'sociodemographics'],
        )
        for domain in uli['domains']:
            with self.subTest(domain=domain['name']):
                self.assertEqual(set(domain['colour']), {'fill', 'stroke'})
                self.assertEqual(set(domain['about']), {'es', 'en'})
        # every indicator seen through a lens, with a subdomain in at least
        # one of its domains
        for indicator in uli['indicators']:
            with self.subTest(indicator=indicator['id']):
                self.assertIn(indicator['lens'], ci.LENSES)
                self.assertTrue(
                    any(
                        ci.subdomain_in(indicator, d)
                        for d in indicator['domains']
                    ),
                )
                # its shares of its domains sum to one
                self.assertAlmostEqual(sum(indicator['domains'].values()), 1)
        # every sub-variable of the ULI variable sheet with data that vary,
        # one per paired access / population-with-access row, and daytime
        # thermal comfort, listed but scored only where walkability is not
        # attenuated by it
        self.assertEqual(len(uli['indicators']), 29)
        self.assertEqual(len(list(ci.iter_indicators(uli))), 28)
        # indicators the sheet assigns to several domains count a share of
        # their weight in each: walkability a third in each of three
        walk = next(i for i in uli['indicators'] if i['id'] == 'walkability')
        self.assertEqual(
            set(walk['domains']),
            {
                'built_environment',
                'mobility_transport',
                'social_infrastructure',
            },
        )
        safety = next(d for d in uli['domains'] if d['name'] == 'safety')
        self.assertEqual(
            set(safety['members']),
            {
                'major_roads',
                'block_size',
                'police_2km',
                'fire_3km',
                'cycle_low_stress_food',
            },
        )
        self.assertAlmostEqual(
            sum(w['effective'] for w in ci.effective_weights(uli).values()),
            1,
        )
        inactive = [i for i in uli['indicators'] if not i['active']]
        self.assertEqual([i['id'] for i in inactive], ['thermal_comfort'])
        self.assertEqual(inactive[0]['variable'], 'sp_utci_day_mean')
        self.assertEqual(set(inactive[0]['inactive_reason']), {'es', 'en'})
        # by default walkability is attenuated by thermal comfort; the one
        # variant uses walkability alone and scores thermal comfort instead
        walkability = [
            i for i in ci.iter_indicators(uli) if i['id'] == 'walkability'
        ]
        self.assertEqual(walkability[0]['variable'], 'sp_walk_idx_300_tm')
        variants = [s for s in specs.values() if s.get('variant_of') == 'uli']
        self.assertEqual([v['name'] for v in variants], ['uli_plain'])
        self.assertEqual(len(list(ci.iter_indicators(variants[0]))), 29)
        self.assertEqual(uli['variants'][0]['name'], 'uli')
        self.assertTrue(uli['variants'][0]['attenuation'])
        self.assertEqual(
            uli['variants'][1]['activates'],
            ['thermal_comfort'],
        )
        self.assertEqual(set(uli['description']), {'es', 'en'})
        # only daytime thermal comfort is linked
        self.assertNotIn(
            'utci_night_mean',
            config['linkage_indicators']['utci']['columns'],
        )
        # every variable a variant swaps in is one walkability_variants writes
        from subprocesses import _walkability_variants as wv

        written = {
            v['column']
            for v in wv.variants(
                wv.normalise_config(config['walkability_variants']),
            )
        }
        self.assertTrue(
            {v['variable'] for v in uli['variants']} <= written,
        )
        # linked sources resolve, and the four walking bands include 500 m
        from subprocesses import _linkage_indicators as li

        self.assertEqual(
            set(li.normalise_config(config['linkage_indicators'])),
            {'utci', 'external'},
        )
        self.assertEqual(
            config['accessibility']['pedestrian']['distances'],
            [300, 500, 1000, 1500],
        )
        # each language's conceptual model is a file the exporter can copy
        for name, language in config['reporting']['languages'].items():
            with self.subTest(language=name):
                figure = os.path.join('data', language['conceptual_model'])
                if not os.path.isfile(figure):
                    self.skipTest(
                        'The conceptual model figures are not present',
                    )
        self.assertEqual(
            config['accessibility']['pedestrian']['distances'][0],
            300,
        )
        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _euclidean_accessibility as ea

        for spec in config['accessibility']['euclidean']['destinations']:
            ea.resolve_spec(spec)

    def test_10_10_series_composite_goalposts(self):
        """Series goalposts pool timepoints, or follow the reference alone."""
        import pandas as pd
        from subprocesses import _composite_index as ci

        spec = ci.normalise_index_spec(
            's',
            {'indicators': [{'variable': 'x', 'polarity': 'positive'}]},
        )
        frames = [
            ci.prepare(pd.DataFrame({'x': [0.0, 10.0]}), spec),
            ci.prepare(pd.DataFrame({'x': [5.0, 30.0]}), spec),
        ]
        pooled = ci.series_parameters(frames, spec)['indicators']['x']
        self.assertEqual((pooled['inf'], pooled['sup']), (0.0, 30.0))
        self.assertEqual(pooled['reference'], 5.0)
        self.assertEqual((pooled['min'], pooled['max']), (-10.0, 20.0))
        baseline = ci.series_parameters(frames, spec, goalposts='reference')
        self.assertEqual(baseline['indicators']['x']['sup'], 10.0)
        later = ci.series_parameters(frames, spec, reference=1)
        self.assertEqual(later['indicators']['x']['reference'], 17.5)
        with self.assertRaises(ValueError):
            ci.series_parameters(frames, spec, goalposts='unknown')

    def test_0_46_composite_indicator_columns(self):
        """Each indicator's normalised score is written once, by its id."""
        import data_dictionary as dd
        import numpy as np
        import pandas as pd
        from subprocesses import _composite_index as ci

        frame = pd.DataFrame(
            {
                'sp_walk_nearest_node_pharmacy': [100.0, 400.0, 900.0, np.nan],
                'sp_walk_access_school_300m': [1.0, 0.0, 1.0, 0.0],
                'heat': [20.0, 40.0, 60.0, 80.0],
            },
        )
        config = {
            'domains': {
                'services': {
                    'indicators': [
                        {
                            'variable': 'sp_walk_nearest_node_pharmacy',
                            'transform': {'soft_threshold': 300},
                        },
                        'sp_walk_access_school_300m',
                    ],
                },
                'environment': {
                    'indicators': [
                        {'variable': 'heat', 'polarity': 'negative'},
                    ],
                },
            },
        }
        spec = ci.normalise_index_spec('uli', config)
        # identifiers are the variables less where they were measured
        self.assertEqual(
            [i['id'] for i in ci.iter_indicators(spec)],
            ['pharmacy', 'school_300m', 'heat'],
        )
        prepared = ci.prepare(frame, spec)
        params = ci.resolve_parameters(prepared, spec)
        scores = ci.score(prepared, spec, params)
        normalised = ci.normalise(prepared, params)
        np.testing.assert_allclose(
            scores['sp_index_uli__pharmacy'],
            normalised['pharmacy'],
        )
        heat = scores['sp_index_uli__heat']
        np.testing.assert_allclose(heat, normalised['heat'])
        # already oriented: the coolest location scores highest
        self.assertEqual(int(heat.idxmax()), 0)
        self.assertEqual(
            ci.index_columns(spec),
            [
                'index_uli',
                'index_uli_mean',
                'index_uli_penalty',
                'index_uli_n',
                'index_uli__services',
                'index_uli__environment',
                'index_uli__pharmacy',
                'index_uli__school_300m',
                'index_uli__heat',
            ],
        )
        quiet = ci.normalise_index_spec(
            'uli',
            {**config, 'write_indicators': False},
        )
        self.assertNotIn(
            'sp_index_uli__pharmacy',
            ci.score(prepared, quiet, params),
        )
        flat = ci.normalise_index_spec(
            'f',
            {
                'indicators': [
                    {'variable': 'heat', 'polarity': 'negative'},
                    'sp_walk_access_school_300m',
                ],
            },
        )
        flat_prepared = ci.prepare(frame, flat)
        self.assertIn(
            'sp_index_f__heat',
            ci.score(
                flat_prepared,
                flat,
                ci.resolve_parameters(flat_prepared, flat),
            ),
        )

        structure = ci.index_structure(spec, params)
        self.assertEqual(structure['columns']['index'], 'index_uli')
        services = structure['domains'][0]
        self.assertEqual(services['column'], 'index_uli__services')
        self.assertEqual(
            [i['column'] for i in services['indicators']],
            [
                'index_uli__pharmacy',
                'index_uli__school_300m',
            ],
        )
        self.assertEqual(services['indicators'][0]['share'], 1.0)
        self.assertFalse(structure['shared'])
        self.assertEqual(services['indicators'][0]['soft_threshold'], 300.0)
        self.assertIn('reference', services['indicators'][0]['normalisation'])

        # a collision needs an explicit name, and a long column is refused
        with self.assertRaises(ValueError):
            ci.normalise_index_spec(
                'uli',
                {
                    'indicators': [
                        'sp_walk_access_school_300m',
                        'sp_euclid_access_school_300m',
                    ],
                },
            )
        with self.assertRaises(ValueError):
            ci.normalise_index_spec(
                'uli',
                {
                    'domains': {
                        'a_rather_long_domain_name': {
                            'indicators': [
                                'sp_walk_nearest_node_an_exceptionally_long_destination_name_for_testing',
                            ],
                        },
                    },
                },
            )
        for variable in (
            'index_uli__pharmacy',
            'pop_index_uli__pharmacy',
            'sp_index_uli__pharmacy',
            # as written before indicator scores were written once
            'index_uli__services__pharmacy',
        ):
            with self.subTest(variable=variable):
                category, description = dd.describe_variable(variable)
                self.assertEqual(category, dd.COMPOSITE)
                self.assertIn('pharmacy', description)
        self.assertEqual(
            dd.describe_units('index_uli__pharmacy'),
            ('index (100 = reference)', 'mean'),
        )
        # knowing the index's domains, a domain and an indicator are told apart
        known = {'uli': {'services', 'environment'}}
        self.assertIn(
            'normalised score of its indicator',
            dd._describe_composite_index('index_uli__pharmacy', known),
        )
        self.assertIn(
            'less a penalty',
            dd._describe_composite_index('index_uli__services', known),
        )

    def test_0_47_composite_dashboard_classes(self):
        """Composite scores share diverging classes centred on the reference."""
        from subprocesses import _composite_index as ci

        spec = ci.normalise_index_spec(
            'uli',
            {
                'domains': {
                    'a': {'indicators': ['sp_walk_access_x_300m']},
                    'b': {'indicators': ['sp_walk_access_y_300m']},
                },
            },
        )
        structure = ci.index_structure(spec)
        ranges = {
            'index_uli': (91.0, 108.0),
            'index_uli__a': (78.0, 121.0),
            'index_uli__b': (85.0, 112.0),
            'index_uli__x_300m': (40.0, 160.0),
            'index_uli_mean': (92.0, 110.0),
            'index_uli_penalty': (0.0, 9.0),
        }
        classes = ci.composite_classes(structure, ranges)
        shared = classes['index_uli__a']
        # sized from the index (91-108), not from its widest domain (78-121):
        # a domain of one binary indicator spans most of the normalised range,
        # and classes sized to reach it leave the index in one middle class
        self.assertEqual(
            shared['edges'],
            [90.0, 94.0, 98.0, 102.0, 106.0, 110.0],
        )
        self.assertTrue(shared['open_low'] and shared['open_high'])
        self.assertEqual(shared['ramp'], 'vik')
        for column in (
            'index_uli',
            'index_uli__b',
            'index_uli__x_300m',
            'index_uli_mean',
        ):
            with self.subTest(column=column):
                self.assertEqual(classes[column], shared)
        # the penalty is not a score, and a column with no range is unclassed
        self.assertNotIn('index_uli_penalty', classes)
        self.assertNotIn('index_uli__y_300m', classes)
        # the reference is the middle of the middle class
        edges = shared['edges']
        middle = len(edges) // 2
        self.assertAlmostEqual((edges[middle - 1] + edges[middle]) / 2, 100.0)
        # a narrower index gets a finer step
        narrow = ci.composite_classes(
            structure,
            {'index_uli': (98.0, 103.0), 'index_uli__a': (97.0, 104.0)},
        )
        self.assertEqual(
            narrow['index_uli']['edges'],
            [95.0, 97.0, 99.0, 101.0, 103.0, 105.0],
        )
        # Mexicali's grid: extremes of 77-116 give a step of 10, leaving three
        # quarters of cells in the middle class; sized from the middle 90% of
        # values instead, the step is 4, and the tails take the open classes
        grid = {'index_uli': (77.03, 115.82), 'index_uli__a': (42.9, 150.0)}
        self.assertEqual(
            ci.composite_classes(structure, grid)['index_uli']['step'],
            10,
        )
        robust = ci.composite_classes(
            structure,
            grid,
            spreads={'index_uli': (90.6, 108.4)},
        )
        self.assertEqual(
            robust['index_uli']['edges'],
            [90.0, 94.0, 98.0, 102.0, 106.0, 110.0],
        )
        self.assertEqual(robust['index_uli__a'], robust['index_uli'])
        # a spread only counts for a column that has a range
        self.assertEqual(
            ci.composite_classes(
                structure,
                grid,
                spreads={'index_uli_missing': (99.0, 101.0)},
            ),
            ci.composite_classes(structure, grid),
        )

    def test_0_48_composite_distribution_diagnostics(self):
        """Indicator distributions are described, and awkward ones flagged."""
        import warnings

        import numpy as np
        import pandas as pd
        from subprocesses import _composite_index as ci

        rng = np.random.default_rng(48)
        normal = pd.Series(rng.normal(50, 10, 5000))
        described = ci.distribution_diagnostics(normal)
        self.assertEqual(described['flags'], [])
        self.assertLess(abs(described['skewness']), 0.2)
        # a heavy right tail meets the skewness and kurtosis rule of thumb
        skewed = pd.Series(rng.lognormal(0, 1.2, 5000))
        self.assertIn('skewed', ci.distribution_diagnostics(skewed)['flags'])
        # a binary catchment reached by 98% of points: tied, whatever else
        tied = pd.Series([1.0] * 980 + [0.0] * 20)
        described = ci.distribution_diagnostics(tied)
        self.assertIn('tied', described['flags'])
        self.assertAlmostEqual(described['tied_share'], 0.98)
        self.assertEqual(ci.distribution_diagnostics(pd.Series([None])), {})

        spec = ci.normalise_index_spec(
            'uli',
            {
                'domains': {
                    'a': {'indicators': ['sp_walk_access_x_300m']},
                    'b': {'indicators': ['sp_walk_access_y_300m']},
                },
            },
        )
        frame = pd.DataFrame(
            {
                'sp_walk_access_x_300m': tied.to_numpy(),
                'sp_walk_access_y_300m': normal.iloc[:1000].to_numpy(),
            },
        )
        prepared = ci.prepare(frame, spec)
        # a 98/2 binary is extremely skewed as well as tied
        with self.assertWarnsRegex(UserWarning, r'x_300m \(skewed, tied\)'):
            params = ci.resolve_parameters(prepared, spec)
        self.assertEqual(
            params['indicators']['x_300m']['distribution']['flags'],
            ['skewed', 'tied'],
        )
        self.assertEqual(
            params['indicators']['y_300m']['distribution']['flags'],
            [],
        )
        # treated, the flag is still recorded but no longer warned about
        compressed = ci.normalise_index_spec(
            'uli',
            {
                'outliers': 'compress',
                'domains': {
                    'a': {'indicators': ['sp_walk_access_x_300m']},
                    'b': {'indicators': ['sp_walk_access_y_300m']},
                },
            },
        )
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            params = ci.resolve_parameters(prepared, compressed)
        self.assertIn(
            'tied',
            params['indicators']['x_300m']['distribution']['flags'],
        )

    def test_0_49_composite_framework_metadata(self):
        """Lenses, subdomains and colours are carried to the index structure."""
        from subprocesses import _composite_index as ci

        # a lens is inferred where the variable says what it measures
        for variable, transformed, lens in (
            ('sp_walk_nearest_node_denue_pharmacy', True, 'proximity'),
            ('sp_walk_nearest_node_denue_pharmacy', False, 'proximity'),
            ('sp_euclid_dist_imip_police_station', False, 'proximity'),
            (
                'sp_walk_access_denue_employer_medium_1000m',
                False,
                'accessibility',
            ),
            ('sp_local_nh_avg_intersection_density', False, 'density'),
            ('sp_walk_diversity_denue_food_1000m', False, 'diversity'),
            ('sp_walk_count_denue_food_1000m', False, 'quantity'),
            ('sp_urban_heat_guhvi', False, None),
        ):
            with self.subTest(variable=variable, transformed=transformed):
                self.assertEqual(ci.infer_lens(variable, transformed), lens)

        spec = ci.normalise_index_spec(
            'uli',
            {
                'colour': '#4E8EF7',
                'domains': {
                    'social_infrastructure': {
                        'colour': {'fill': '#FFE7C2', 'stroke': '#FFBD59'},
                        'indicators': [
                            {
                                'variable': 'sp_walk_nearest_node_pharmacy',
                                'transform': {'soft_threshold': 300},
                                'subdomain': {'en': 'Health', 'es': 'Salud'},
                            },
                        ],
                    },
                    'ambient_environment': {
                        'indicators': [
                            {
                                'variable': 'heat',
                                'polarity': 'negative',
                                'lens': 'Quality',
                            },
                        ],
                    },
                },
            },
        )
        structure = ci.index_structure(spec)
        self.assertEqual(structure['colour'], {'fill': '#4E8EF7'})
        social, ambient = structure['domains']
        self.assertEqual(
            social['colour'],
            {'fill': '#FFE7C2', 'stroke': '#FFBD59'},
        )
        self.assertIsNone(ambient['colour'])
        pharmacy = social['indicators'][0]
        self.assertEqual(pharmacy['lens'], 'proximity')
        self.assertEqual(
            pharmacy['subdomain'],
            {'en': 'Health', 'es': 'Salud'},
        )
        self.assertEqual(pharmacy['k'], ci.SOFT_THRESHOLD_K)
        self.assertEqual(ambient['indicators'][0]['lens'], 'quality')
        # the lenses used, labelled, in the framework's order
        self.assertEqual(list(structure['lenses']), ['quality', 'proximity'])
        self.assertEqual(structure['lenses']['quality']['es'], 'Calidad')

        # regrouped, an index's old domain and indicator columns are stale on
        # every scale; its current ones, and other indices', are not
        self.assertEqual(
            ci.stale_columns(
                spec,
                [
                    'index_uli',
                    'index_uli_penalty',
                    'index_uli__social_infrastructure',
                    'index_uli__pharmacy',
                    'pop_index_uli__heat',
                    # indicator scores as written before September 2026
                    'index_uli__social_infrastructure__pharmacy',
                    'index_uli__daily_essentials',
                    'pop_index_uli__daily_essentials__pharmacy',
                    'index_other__daily_essentials',
                    'grid_id',
                ],
            ),
            [
                'index_uli__social_infrastructure__pharmacy',
                'index_uli__daily_essentials',
                'pop_index_uli__daily_essentials__pharmacy',
            ],
        )

        for bad in (
            {'lens': 'nearness'},
            {'colour_of_domain': 'red'},
            {'colour_of_domain': {'fill': '#FFF', 'border': '#000'}},
        ):
            with self.subTest(bad=bad):
                indicator = {'variable': 'heat', 'polarity': 'negative'}
                domain = {'indicators': [indicator]}
                if 'lens' in bad:
                    indicator['lens'] = bad['lens']
                else:
                    domain['colour'] = bad['colour_of_domain']
                with self.assertRaises(ValueError):
                    ci.normalise_index_spec('uli', {'domains': {'a': domain}})

    def test_0_50_dashboard_conceptual_models(self):
        """Each language's conceptual model figure is copied and listed."""
        import tempfile
        import types

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        sys.path.insert(0, os.path.abspath('subprocesses'))
        import _export_dashboard as ed

        self.assertEqual(ed.language_code('English'), 'en')
        self.assertEqual(ed.language_code('Spanish - Latin America'), 'es')
        self.assertEqual(
            ed.language_code('Spanish - Spain', {'Spanish - Spain': 'es'}),
            'es',
        )
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, 'source')
            out = os.path.join(folder, 'out')
            os.makedirs(source)
            os.makedirs(out)
            for name in ('model.svg', 'modelo.pdf', 'notes.txt'):
                with open(os.path.join(source, name), 'w') as f:
                    f.write('<svg/>')
            r = types.SimpleNamespace(
                config={
                    'reporting': {
                        # an unreadable sheet falls back to the names
                        'configuration': os.path.join(folder, 'missing.xlsx'),
                        'languages': {
                            'English': {
                                'name': 'X',
                                'country': 'Y',
                                'conceptual_model': os.path.join(
                                    source,
                                    'model.svg',
                                ),
                            },
                            'Spanish - Latin America': {
                                'name': 'X',
                                'country': 'Y',
                                'conceptual_model': {
                                    'file': os.path.join(source, 'modelo.pdf'),
                                    'caption': 'Modelo',
                                },
                            },
                            'Catalan': {
                                'name': 'X',
                                'country': 'Y',
                                'conceptual_model': os.path.join(
                                    source,
                                    'notes.txt',
                                ),
                            },
                            'Danish': {
                                'name': 'X',
                                'country': 'Y',
                                'conceptual_model': os.path.join(
                                    source,
                                    'absent.png',
                                ),
                            },
                            'Dutch': {'name': 'X', 'country': 'Y'},
                        },
                    },
                },
            )
            models = ed.conceptual_models(r, out)
            self.assertEqual(sorted(models), ['en', 'es'])
            self.assertEqual(
                models['en'],
                {
                    'file': 'conceptual_model_en.svg',
                    'type': 'image',
                    'caption': None,
                    'alt': None,
                },
            )
            self.assertEqual(models['es']['type'], 'document')
            self.assertEqual(models['es']['caption'], 'Modelo')
            self.assertEqual(
                sorted(os.listdir(out)),
                ['conceptual_model_en.svg', 'conceptual_model_es.pdf'],
            )

    def test_0_52_linkage_geometry_matching(self):
        """Linked areas are identified by geometry, exactly or by overlap."""
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import box
        from subprocesses import _linkage_indicators as li

        reference = gpd.GeoDataFrame(
            {'area_id': ['a', 'b', 'c']},
            geometry=[
                box(0, 0, 10, 10),
                box(10, 0, 20, 10),
                box(20, 0, 30, 10),
            ],
            crs=6366,
        )
        source = gpd.GeoDataFrame(
            {'value': [1.0, 2.0, 4.0, 9.0]},
            geometry=[
                # identical to 'a', listed in another vertex order
                box(0, 0, 10, 10).reverse(),
                # 'b', slightly redrawn: matched by overlap
                box(10.2, 0, 20, 10),
                # the two halves of 'c', delivered separately
                box(20, 0, 25, 10),
                box(25, 0, 30, 10),
            ],
            crs=6366,
        )
        ids, shares, report = li.match_by_geometry(source, reference)
        self.assertEqual(list(ids), ['a', 'b', 'c', 'c'])
        self.assertEqual(report['exact'], 1)
        self.assertEqual(report['overlap'], 3)
        self.assertEqual(report['unmatched'], 0)
        self.assertEqual(report['shared_ids'], 1)
        # a feature mostly outside any reference feature is not matched
        stray = source.iloc[[0]].copy()
        stray['geometry'] = [box(28, 0, 40, 10)]
        ids, _, report = li.match_by_geometry(stray, reference)
        self.assertTrue(ids.isna().all())
        self.assertEqual(report['unmatched'], 1)
        # parts of one area are combined as an area weighted mean
        combined = li.combine_matched(
            source,
            li.match_by_geometry(source, reference)[0],
            ['value'],
        ).set_index('area_id')
        self.assertAlmostEqual(combined.loc['c', 'value'], 6.5)
        # unreliable values are masked, and missing values filled as configured
        spec = li.normalise_spec(
            'x',
            {
                'data': 'x.gpkg',
                'mask': 'ok',
                'columns': ['v', 'w'],
                'null_as': {'w': 0},
            },
        )
        frame = pd.DataFrame(
            {'v': [1.0, 2.0], 'w': [None, 3.0], 'ok': [True, False]},
        )
        ruled = li.apply_rules(frame, spec)
        self.assertEqual(ruled['v'].isna().tolist(), [False, True])
        self.assertEqual(ruled['w'].tolist()[0], 0)
        # but not in a layer that does not measure the column at all
        unmeasured = li.apply_rules(frame.assign(w=None), spec)
        self.assertTrue(unmeasured['w'].isna().all())
        # names the exporter reads meaning into are refused
        with self.assertRaises(ValueError):
            li.normalise_spec('x', {'data': 'x', 'columns': ['pct_x']})
        # sample points take the first layer holding a value for them
        points = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy([5, 15, 60], [5, 5, 5]),
            crs=6366,
        )
        grid = gpd.GeoDataFrame(
            {'v': [1.0, None]},
            geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
            crs=6366,
        )
        blocks = gpd.GeoDataFrame(
            {'v': [7.0]},
            geometry=[box(12, 0, 18, 10)],
            crs=6366,
        )
        values = li.sample_point_values(points, [(grid, None), (blocks, 30)])
        self.assertEqual(values['v'].tolist()[:2], [1.0, 7.0])
        self.assertTrue(pd.isna(values['v'].tolist()[2]))

    def test_0_57_linked_and_walkability_dictionary(self):
        """Linked indicators are described as configured, never inferred."""
        from types import SimpleNamespace

        from subprocesses import _linkage_indicators as li
        from subprocesses import data_dictionary as dd

        block = {
            'utci': {
                'data': 'x.gpkg',
                'source': 'Modelling team',
                'licence': 'CC BY 4.0',
                'columns': {
                    'utci_day_mean': {
                        'label': {'en': 'Daytime thermal comfort'},
                        'units': 'degC',
                        'statistic': 'mean',
                        'description': 'Unit mean of daytime UTCI',
                    },
                },
            },
            'external': {
                'data': 'y.gpkg',
                'prefix': 'ext_',
                'columns': {'ndvi': {'units': 'NDVI'}, 'mix': {}},
            },
        }
        described = li.linked_variables(li.normalise_config(block))
        area = described['utci_day_mean']
        self.assertEqual(area['description'], 'Unit mean of daytime UTCI')
        self.assertEqual((area['units'], area['statistic']), ('degC', 'mean'))
        self.assertEqual(area['source'], 'Modelling team')
        self.assertEqual(area['licence'], 'CC BY 4.0')
        # the sample point value is replicated from its area, and the city
        # summary is a population weighted mean of the grid
        self.assertIn(
            'replicated',
            described['sp_utci_day_mean']['description'],
        )
        self.assertEqual(described['pop_utci_day_mean']['statistic'], 'mean')
        # what is not configured is left empty, not guessed from the name
        self.assertEqual(described['ext_ndvi']['units'], 'NDVI')
        self.assertEqual(described['ext_ndvi']['statistic'], '')
        self.assertEqual(
            (described['ext_mix']['units'], described['ext_mix']['statistic']),
            ('', ''),
        )
        self.assertEqual(described['ext_mix']['description'], 'mix')
        # a statistic outside the dictionary's vocabulary is refused
        bad = {'data': 'x', 'columns': {'v': {'statistic': 'average'}}}
        with self.assertRaises(ValueError):
            li.normalise_spec('x', bad)
        self.assertEqual(set(li.STATISTICS), set(dd.STATISTICS))
        # the data dictionary reports them so, in their own category
        r = SimpleNamespace(config={'linkage_indicators': block})
        linked = dd._linked_variables(r)
        frame = dd._finalise(
            [
                {
                    'Category': dd.LINKED,
                    'Description': linked[v]['description'],
                    'Variable': v,
                    'Scale': 'grid',
                    'order': i,
                }
                for i, v in enumerate(['utci_day_mean', 'ext_ndvi'])
            ],
            units={v: (m['units'], m['statistic']) for v, m in linked.items()},
        ).set_index('Variable')
        self.assertEqual(frame.loc['utci_day_mean', 'Statistic'], 'mean')
        self.assertEqual(frame.loc['ext_ndvi', 'Units'], 'NDVI')
        self.assertEqual(frame.loc['ext_ndvi', 'Statistic'], '')
        # walkability variants resolve from their names, as the code computes
        # them: sample point values, averaged for areas
        self.assertEqual(
            dd.describe_units('walk_idx_300'),
            ('index (sum of z-scores)', 'mean'),
        )
        self.assertEqual(
            dd.describe_units('walk_idx_300_tm'),
            ('index 0-1', 'mean'),
        )
        self.assertEqual(
            dd.describe_units('sp_walk_dl_300'),
            ('destinations', 'value'),
        )
        category, text = dd.describe_variable('walk_idx_300_tm')
        self.assertEqual(category, dd.WALKABILITY)
        self.assertIn('attenuation', text)
        # the heat measure and how it was re-scaled are those configured
        heat, daily_living = dd._walkability_config(
            SimpleNamespace(
                config={
                    'walkability_variants': {
                        'daily_living': ['convenience'],
                        'heat': {
                            't': {
                                'variable': 'sp_utci_day_mean',
                                'range': [30, 50],
                                'label': {'en': 'thermal comfort'},
                            },
                        },
                    },
                },
            ),
        )
        text = dd._describe_walkability_variant(
            'walk_idx_300_tm',
            heat,
            daily_living,
        )
        self.assertIn(
            'thermal comfort re-scaled from 0 at 30 to 1 at 50',
            text,
        )
        self.assertIn('lambda = 0.5', text)
        self.assertNotIn('P5', text)
        # an additive variant takes the z-score of heat, not a re-scaling
        text = dd._describe_walkability_variant('walk_idx_300_ta', heat)
        self.assertNotIn('re-scaled', text)
        self.assertIn(
            'convenience',
            dd._describe_walkability_variant(
                'walk_dl_300',
                daily_living=daily_living,
            ),
        )

    def test_0_53_walkability_variants(self):
        """Walkability at chosen distances, and its heat variants."""
        import numpy as np
        import pandas as pd
        from subprocesses import _walkability_variants as wv

        config = wv.normalise_config(
            {
                'distances': [300, 500],
                'heat': {'g': 'h_g', 't': {'variable': 'h_t'}},
                'sets': ['g', 'gt'],
            },
        )
        columns = [v['column'] for v in wv.variants(config)]
        self.assertIn('sp_walk_idx_300', columns)
        self.assertIn('sp_walk_idx_500_gtm', columns)
        self.assertEqual(len(columns), 2 * (1 + 2 * 2))
        rng = np.random.default_rng(3)
        n = 400
        frame = pd.DataFrame(
            {
                v: rng.integers(0, 2, n).astype(float)
                for v in wv.input_variables(config)
                if v.startswith('sp_walk_access_')
            },
        )
        frame['sp_local_nh_avg_pop_density'] = rng.gamma(2, 2000, n)
        frame['sp_local_nh_avg_intersection_density'] = rng.gamma(3, 30, n)
        frame['h_g'] = rng.uniform(0, 60, n)
        frame['h_t'] = rng.normal(45, 1, n)
        out = wv.compute_variants(frame, config)

        # the unadjusted index is the GHSCI sum of z-scores
        def z(x):
            return (x - x.mean()) / x.std()

        daily = frame[
            [f'sp_walk_access_{d}_300m' for d in wv.DAILY_LIVING]
        ].sum(axis=1)
        expected = (
            z(daily)
            + z(frame['sp_local_nh_avg_pop_density'])
            + z(frame['sp_local_nh_avg_intersection_density'])
        )
        np.testing.assert_allclose(out['sp_walk_idx_300'], expected)
        # additive: less heat is better, so its z-score is subtracted
        np.testing.assert_allclose(
            out['sp_walk_idx_300_ga'],
            expected - z(frame['h_g']),
        )
        # attenuation: bounded to (0, 1], never above the rank it attenuates,
        # and by at most half at the hottest
        attenuated = out['sp_walk_idx_300_gtm']
        rank = expected.rank(pct=True)
        self.assertTrue((attenuated > 0).all() and (attenuated <= 1).all())
        self.assertTrue((attenuated <= rank + 1e-12).all())
        self.assertTrue((attenuated >= rank * 0.25 - 1e-12).all())
        # hotter places, alike otherwise, are less walkable
        pair = frame.iloc[[0, 0]].copy()
        pair['h_t'] = [40.0, 50.0]
        pair.index = [0, 1]
        both = pd.concat([frame, pair], ignore_index=True)
        scored = wv.compute_variants(both, config)['sp_walk_idx_300_gtm']
        self.assertGreater(scored.iloc[-2], scored.iloc[-1])
        # the percentile bounds each heat measure was re-scaled between are
        # recorded, in its own units, so that attenuation can be explained
        bounds = out.attrs['heat_bounds']
        self.assertEqual(set(bounds), {'g', 't'})
        np.testing.assert_allclose(
            bounds['t']['bounds'],
            np.nanpercentile(frame['h_t'], [5, 95]),
        )
        self.assertEqual(bounds['t']['basis'], 'percentiles')
        # a fixed range judges heat absolutely, whatever the city's spread
        fixed = wv.normalise_config(
            {
                'distances': [300],
                'heat': {'t': {'variable': 'h_t', 'range': [30, 50]}},
                'sets': ['t'],
                'forms': ['multiplicative'],
            },
        )
        scored = wv.compute_variants(frame, fixed)
        self.assertEqual(scored.attrs['heat_bounds']['t']['bounds'], [30, 50])
        self.assertEqual(scored.attrs['heat_bounds']['t']['basis'], 'range')
        expected = expected.rank(pct=True) * (
            1 - 0.5 * ((frame['h_t'] - 30) / 20).clip(0, 1)
        )
        np.testing.assert_allclose(scored['sp_walk_idx_300_tm'], expected)
        with self.assertRaises(ValueError):
            wv.normalise_config(
                {'heat': {'t': {'variable': 'x', 'range': [5, 1]}}},
            )
        recorded = wv.parameters(config, bounds)
        self.assertEqual(recorded['attenuation'], 0.5)
        self.assertEqual(recorded['percentiles'], [5.0, 95.0])
        self.assertEqual(recorded['heat']['t']['variable'], 'h_t')
        with self.assertRaises(ValueError):
            wv.normalise_config({'heat': {'a': 'x'}})
        with self.assertRaises(ValueError):
            wv.normalise_config({'heat': {'g': 'x'}, 'sets': ['gz']})

    def test_0_54_composite_variants_and_steps(self):
        """Composite index variants, and stepped scoring of a distance."""
        import warnings

        import numpy as np
        import pandas as pd
        from subprocesses import _composite_index as ci

        steps = [[200, 100], [500, 90], [1000, 80], [1500, 60]]
        scored = ci.stepped_score(
            pd.Series([0, 200, 201, 1000, 1500, np.nan, 5000]),
            steps,
            60,
        )
        self.assertEqual(scored.tolist(), [100, 100, 90, 80, 60, 60, 60])
        with self.assertRaises(ValueError):
            ci.normalise_indicator(
                {
                    'variable': 'sp_x_nearest_node_y',
                    'transform': {'steps': [[500, 1], [200, 2]]},
                },
                'i',
            )
        block = {
            'uli': {
                'domains': {
                    'mob': {
                        'indicators': [
                            {
                                'variable': 'sp_walk_idx_300',
                                'name': 'walkability',
                            },
                        ],
                    },
                    'amb': {
                        'indicators': [
                            {
                                'variable': 'sp_walk_nearest_node_blue',
                                'transform': {'steps': steps, 'beyond': 60},
                            },
                            {'variable': 'sp_heat', 'polarity': 'negative'},
                        ],
                    },
                },
                'variants': {
                    'replace': 'walkability',
                    'base': {'walk': 300},
                    'options': {
                        'ga': {
                            'variable': 'sp_walk_idx_300_ga',
                            'heat': ['g'],
                        },
                        'w5': {'variable': 'sp_walk_idx_500', 'walk': 500},
                    },
                },
            },
        }
        specs = ci.normalise_config(block)
        self.assertEqual(list(specs), ['uli', 'uli_ga', 'uli_w5'])
        variant = specs['uli_ga']
        # a variant writes its own scores and the indicator it swaps only
        self.assertEqual(
            ci.index_columns(variant),
            [
                'index_uli_ga',
                'index_uli_ga_mean',
                'index_uli_ga_penalty',
                'index_uli_ga_n',
                'index_uli_ga__mob',
                'index_uli_ga__amb',
                'index_uli_ga__walkability',
            ],
        )
        # and reads the scores it shares from its base index
        structure = ci.index_structure(variant)
        columns = {
            i['id']: i['column']
            for d in structure['domains']
            for i in d['indicators']
        }
        self.assertEqual(columns['blue'], 'index_uli__blue')
        self.assertEqual(
            [v['name'] for v in ci.index_structure(specs['uli'])['variants']],
            ['uli', 'uli_ga', 'uli_w5'],
        )
        rng = np.random.default_rng(5)
        n = 300
        frame = pd.DataFrame(
            {
                'sp_walk_idx_300': rng.normal(size=n),
                'sp_walk_idx_300_ga': rng.normal(size=n),
                'sp_walk_idx_500': rng.normal(size=n),
                'sp_walk_nearest_node_blue': rng.uniform(0, 1600, n),
                'sp_heat': rng.normal(size=n),
            },
        )
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for name, spec in specs.items():
                prepared = ci.prepare(frame, spec)
                params = ci.resolve_parameters([prepared], spec)
                result = ci.score(prepared, spec, params)
                self.assertEqual(
                    sorted(result.columns),
                    sorted(
                        ci.index_columns(spec, prefix=ci.SAMPLE_POINT_PREFIX),
                    ),
                )
        # the columns of a variant no longer configured are retired
        self.assertEqual(
            ci.retired_variant_columns(
                specs,
                [
                    'index_uli_ga',
                    'pop_index_uli_old_mean',
                    'index_uli_old__amb',
                    'index_uli__amb',
                    'index_ulix',
                ],
            ),
            ['pop_index_uli_old_mean', 'index_uli_old__amb'],
        )
        # a variant may not collide with a configured index
        clash = dict(block, uli_ga={'indicators': ['sp_walk_idx_300']})
        with self.assertRaises(ValueError):
            ci.normalise_config(clash)
        # an inactive indicator is described but not scored, until a
        # variant activates it: thermal comfort, where walkability is not
        # attenuated by it
        amb = block['uli']['domains']['amb']['indicators']
        activating = {
            'uli': {
                'description': {'en': 'A short definition'},
                'domains': {
                    'mob': block['uli']['domains']['mob'],
                    'amb': {
                        'about': {'en': 'Ambient'},
                        'indicators': amb
                        + [
                            {
                                'variable': 'sp_utci',
                                'name': 'thermal',
                                'polarity': 'negative',
                                'active': False,
                                'inactive_reason': {'en': 'In walkability'},
                                'sources': ['WP02'],
                            },
                        ],
                    },
                },
                'variants': {
                    'replace': 'walkability',
                    'base': {'attenuation': True},
                    'options': {
                        'plain': {
                            'variable': 'sp_walk_idx_300_ga',
                            'activate': ['thermal'],
                            'attenuation': False,
                        },
                    },
                },
            },
        }
        specs = ci.normalise_config(activating)
        self.assertEqual(
            [i['id'] for i in ci.iter_indicators(specs['uli'])],
            ['walkability', 'blue', 'heat'],
        )
        self.assertNotIn(
            'index_uli__thermal',
            ci.index_columns(specs['uli']),
        )
        self.assertEqual(
            ci.index_columns(specs['uli_plain'])[-2:],
            ['index_uli_plain__walkability', 'index_uli_plain__thermal'],
        )
        structure = ci.index_structure(specs['uli'])
        self.assertEqual(
            structure['description'],
            {'en': 'A short definition'},
        )
        thermal = structure['domains'][1]['indicators'][-1]
        self.assertFalse(thermal['active'])
        self.assertEqual(thermal['inactive_reason'], {'en': 'In walkability'})
        self.assertEqual(thermal['sources'], ['WP02'])
        # read from the variant that scores it
        self.assertEqual(thermal['column'], 'index_uli_plain__thermal')
        self.assertEqual(structure['domains'][1]['about'], {'en': 'Ambient'})
        self.assertEqual(
            [
                (v['name'], v['activates'], v['attenuation'])
                for v in structure['variants']
            ],
            [('uli', [], True), ('uli_plain', ['thermal'], False)],
        )
        frame['sp_utci'] = rng.normal(size=n)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for name, spec in specs.items():
                prepared = ci.prepare(frame, spec)
                params = ci.resolve_parameters([prepared], spec)
                self.assertEqual(
                    'thermal' in params['indicators'],
                    name == 'uli_plain',
                )
                result = ci.score(prepared, spec, params)
                self.assertEqual(
                    sorted(result.columns),
                    sorted(
                        ci.index_columns(spec, prefix=ci.SAMPLE_POINT_PREFIX),
                    ),
                )
        # only an inactive indicator may be activated
        bad = {
            'uli': dict(
                activating['uli'],
                variants={
                    'replace': 'walkability',
                    'options': {
                        'x': {'variable': 'sp_y', 'activate': ['blue']},
                    },
                },
            ),
        }
        with self.assertRaises(ValueError):
            ci.normalise_config(bad)

    def test_0_55_dashboard_types_and_tile_groups(self):
        """Dashboard types, tile groups, raw columns and smoothed densities."""
        import numpy as np

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        sys.path.insert(0, os.path.abspath('subprocesses'))
        import _export_dashboard as ed

        # the configured type is exported under the configured slug, the
        # other under its own
        config = {'slug': 'mx', 'type': 'composite', 'general': {'slug': 'g'}}
        self.assertEqual(ed.dashboard_type(config), ('composite', 'mx'))
        self.assertEqual(
            ed.dashboard_type(config, 'general'),
            ('general', 'g'),
        )
        self.assertEqual(
            ed.dashboard_type({'slug': 'mx'}, 'composite'),
            ('composite', 'mx_composite'),
        )
        with self.assertRaises(ValueError):
            ed.dashboard_type({'slug': 'mx'}, 'other')

        # columns are tiled by theme, a wide theme split into chunks, and a
        # family never split across groups
        def family(name, theme, n):
            return {
                'id': name,
                'theme': theme,
                'columns': [f'{name}_{i}' for i in range(n)],
            }

        families = [
            family('a', 'Calor y confort', 30),
            family('b', 'Calor y confort', 20),
            family('c', 'Calor y confort', 25),
            family('d', None, 5),
            family('e', 'Movilidad', 70),
        ]
        groups = ed.tile_groups(families, max_columns=60)
        self.assertEqual(
            {k: len(v) for k, v in groups.items()},
            {
                'calor_y_confort': 50,
                'calor_y_confort_2': 25,
                'other': 5,
                'movilidad': 70,
            },
        )
        every = [c for f in families for c in f['columns']]
        self.assertEqual(
            sorted(c for g in groups.values() for c in g),
            sorted(every),
        )

        # a general dashboard leaves out composite indices; a composite one
        # keeps only its index
        def vocabulary():
            return {
                'families': [
                    {'id': 'walk', 'domain': 'Walking', 'columns': ['w']},
                    {
                        'id': 'composite_uli',
                        'domain': 'Composite indices',
                        'composite': {'name': 'uli'},
                        'columns': ['index_uli', 'u_raw'],
                    },
                ],
                'themes': [{'id': 't', 'families': ['walk', 'composite_uli']}],
                'interventions': [{'id': 1}],
                'domains': [{'id': 'Walking'}, {'id': 'Composite indices'}],
                'descriptions': {'w': {}, 'index_uli': {}, 'u_raw': {}},
            }

        general = ed.select_dashboard(vocabulary(), 'general')
        self.assertEqual([f['id'] for f in general['families']], ['walk'])
        self.assertEqual(general['themes'][0]['families'], ['walk'])
        self.assertEqual(set(general['descriptions']), {'w'})
        composite = ed.select_dashboard(vocabulary(), 'composite', 'uli')
        self.assertEqual(
            [f['id'] for f in composite['families']],
            ['composite_uli'],
        )
        self.assertEqual(composite['themes'], [])
        self.assertEqual(composite['interventions'], [])
        self.assertEqual(
            set(composite['descriptions']),
            {'index_uli', 'u_raw'},
        )
        # a combined one keeps both, the index as a theme of its own
        combined = ed.select_dashboard(vocabulary(), 'combined', 'uli')
        self.assertEqual(
            [f['id'] for f in combined['families']],
            ['walk', 'composite_uli'],
        )
        self.assertEqual(
            combined['themes'][0]['families'],
            ['walk', 'composite_uli'],
        )

        # an area with nothing within the distance searched is counted apart,
        # not dropped: here 2 people valued, 6 beyond, 2 unmeasured
        import pandas as pd

        weights = np.array([1.0, 1.0, 3.0, 3.0, 2.0])
        distances = pd.Series([200.0, 900.0, np.nan, np.nan, np.nan])
        access = pd.Series([100.0, 100.0, 0.0, 0.0, np.nan])
        stats = ed.column_stats(
            distances,
            weights,
            None,
            {
                'kind': 'classes',
                'edges': [0, 500, 1000, 1500],
                'open_low': False,
                'open_high': False,
            },
        )
        stats = ed.censored_shares(stats, distances, access, weights)
        self.assertEqual(stats['beyond'], 75.0)
        self.assertEqual(stats['class_shares'], [12.5, 12.5, 0.0])
        self.assertEqual(stats['n_beyond'], 2)
        # every area beyond: a summary of its own
        alone = ed.censored_shares(
            None,
            pd.Series([np.nan]),
            pd.Series([0.0]),
            np.array([1.0]),
        )
        self.assertEqual(alone['beyond'], 100.0)
        # a censored distance is classed by the bands searched
        breaks = ed.all_class_breaks(
            {
                'descriptions': {'avg_walk_dist_x': {'units': 'metres'}},
                'families': [],
                'censored': {
                    'avg_walk_dist_x': {
                        'distance': 1500,
                        'bands': [300, 500, 1000, 1500],
                        'access': 'pct_access_walk_x_1500m',
                    },
                },
            },
            {'avg_walk_dist_x': (0.0, 2988.0)},
            {},
            {},
        )
        self.assertEqual(
            breaks['avg_walk_dist_x']['edges'],
            [0.0, 300.0, 500.0, 1000.0, 1500.0],
        )

        # a regular grid is written back as a raster of its cells
        import tempfile

        import geopandas as gpd
        from shapely.geometry import box

        cells = [(0, 0), (1, 0), (2, 1)]  # (column, row) from the upper left
        grid = gpd.GeoDataFrame(
            {
                'area_id': ['a', 'b', 'c'],
                'x1': [1.0, None, 3.0],
                'x2': [10.0, 20.0, 30.0],
            },
            geometry=[
                box(
                    500000 + c * 100,
                    3600000 - (r + 1) * 100,
                    500000 + (c + 1) * 100,
                    3600000 - r * 100,
                )
                for c, r in cells
            ],
            crs=32611,
        )
        tiles = {'g': {'columns': ['x1', 'x2']}}
        with tempfile.TemporaryDirectory() as folder:
            raster = ed.grid_raster(grid, tiles, folder, 'scale_grid')
            self.assertEqual(
                (raster['nx'], raster['ny'], raster['cell']),
                (3, 2, 100.0),
            )
            index = np.fromfile(os.path.join(folder, raster['index']), '<i4')
            self.assertEqual(index.tolist(), [0, 1, 5])
            values = np.fromfile(
                os.path.join(folder, raster['groups']['g']['file']),
                '<f4',
            ).reshape(2, 3)
            self.assertTrue(np.isnan(values[0, 1]))
            self.assertEqual(values[1].tolist(), [10.0, 20.0, 30.0])
            self.assertEqual(len(raster['corners']), 4)
            # not a grid: no raster
            irregular = grid.copy()
            irregular.geometry = [
                box(0, 0, 100, 100),
                box(100, 0, 150, 60),
                box(0, 100, 30, 200),
            ]
            self.assertIsNone(
                ed.grid_raster(irregular, tiles, folder, 'scale_x'),
            )

        # an index indicator's raw value is found under its area name
        available = {
            'avg_walk_dist_denue_fresh_food',
            'avg_diversity_walk_education_500m',
            'pct_beyond_walk_denue_petrol_station_250m',
            'pct_access_walk_denue_manufacturing_1000m',
            'avg_cycle_dist_safe_fresh_food_pooled',
            'pct_access_500m_large_public_green_space_score',
            'walk_idx_300_tm',
            'utci_day_mean',
            'urban_heat_guhvi',
            'ext_ndvi',
        }
        for variable, column in (
            (
                'sp_walk_nearest_node_denue_fresh_food',
                'avg_walk_dist_denue_fresh_food',
            ),
            (
                'sp_walk_diversity_education_500m',
                'avg_diversity_walk_education_500m',
            ),
            (
                'sp_walk_beyond_denue_petrol_station_250m',
                'pct_beyond_walk_denue_petrol_station_250m',
            ),
            (
                'sp_walk_access_denue_manufacturing_1000m',
                'pct_access_walk_denue_manufacturing_1000m',
            ),
            (
                'sp_cycle_safe_nearest_node_fresh_food_pooled',
                'avg_cycle_dist_safe_fresh_food_pooled',
            ),
            (
                'sp_access_large_public_green_space_score',
                'pct_access_500m_large_public_green_space_score',
            ),
            ('sp_walk_idx_300_tm', 'walk_idx_300_tm'),
            ('sp_utci_day_mean', 'utci_day_mean'),
            ('sp_urban_heat_guhvi', 'urban_heat_guhvi'),
            ('sp_ext_ndvi', 'ext_ndvi'),
            ('sp_missing', None),
        ):
            with self.subTest(variable=variable):
                self.assertEqual(
                    ed.area_column_for(variable, available),
                    column,
                )

        # a weighted density integrates to one, and follows the weights
        rng = np.random.default_rng(7)
        values = np.concatenate(
            [rng.normal(90, 3, 500), rng.normal(110, 3, 500)],
        )
        grid = np.linspace(70, 130, 241)
        step = grid[1] - grid[0]
        even = ed.weighted_kde(values, np.ones(1000), grid)
        self.assertAlmostEqual(float(even.sum() * step), 1.0, places=2)
        tilted = ed.weighted_kde(
            values,
            np.r_[np.full(500, 9.0), np.ones(500)],
            grid,
        )
        self.assertGreater(
            tilted[np.abs(grid - 90).argmin()],
            3 * tilted[np.abs(grid - 110).argmin()],
        )
        self.assertIsNone(ed.weighted_kde([1.0], [1.0], grid))
        self.assertIsNone(ed.weighted_kde([1.0, np.nan], [1.0, 1.0], grid))

    def test_0_56_composite_shared_domains(self):
        """An indicator in several domains counts a share of its weight in each."""
        import warnings

        import numpy as np
        import pandas as pd
        from subprocesses import _composite_index as ci

        rng = np.random.default_rng(11)
        n = 200
        frame = pd.DataFrame(
            {
                'walk': rng.normal(size=n),
                'pt': rng.normal(size=n),
                'park': rng.normal(size=n),
                'roads': rng.normal(size=n),
            },
        )
        shared = {
            'domains': {
                'built': {'label': {'en': 'Built environment'}},
                'mobility': {},
                'safety': {},
                'housing': {'about': {'en': 'Not yet measured'}},
            },
            'indicators': [
                {
                    'variable': 'walk',
                    'polarity': 'positive',
                    'domains': ['built', 'mobility', 'safety'],
                    'group': {'en': 'Walkability'},
                },
                {
                    'variable': 'pt',
                    'polarity': 'positive',
                    'domains': 'mobility',
                },
                {
                    'variable': 'park',
                    'polarity': 'positive',
                    'domains': ['built'],
                },
                {
                    'variable': 'roads',
                    'polarity': 'negative',
                    'domains': {'safety': 2, 'built': 1},
                },
            ],
        }
        with self.assertWarns(UserWarning):
            spec = ci.normalise_index_spec('uli', shared)
        walk = next(i for i in spec['indicators'] if i['id'] == 'walk')
        self.assertEqual(
            walk['domains'],
            {'built': 1 / 3, 'mobility': 1 / 3, 'safety': 1 / 3},
        )
        roads = next(i for i in spec['indicators'] if i['id'] == 'roads')
        self.assertAlmostEqual(roads['domains']['safety'], 2 / 3)
        # a domain listing no indicators is described, not scored
        housing = spec['domains'][-1]
        self.assertFalse(housing['scored'])
        self.assertNotIn('index_uli__housing', ci.index_columns(spec))
        # each indicator is scored once, and its score written once
        self.assertEqual(
            [i['id'] for i in ci.iter_indicators(spec)],
            ['walk', 'pt', 'park', 'roads'],
        )
        self.assertEqual(
            ci.index_columns(spec)[4:],
            [
                'index_uli__built',
                'index_uli__mobility',
                'index_uli__safety',
                'index_uli__walk',
                'index_uli__pt',
                'index_uli__park',
                'index_uli__roads',
            ],
        )
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            prepared = ci.prepare(frame, spec)
            params = ci.resolve_parameters(prepared, spec)
        self.assertEqual(
            params['indicators']['walk']['domains'],
            walk['domains'],
        )
        scores = ci.score(prepared, spec, params)
        normalised = ci.normalise(prepared, params)
        # the same as weighting each domain's members by their shares
        for domain, members in (
            ('built', {'walk': 1 / 3, 'park': 1, 'roads': 1 / 3}),
            ('mobility', {'walk': 1 / 3, 'pt': 1}),
            ('safety', {'walk': 1 / 3, 'roads': 2 / 3}),
        ):
            with self.subTest(domain=domain):
                expected = ci.mpi_aggregate(
                    normalised[list(members)],
                    list(members.values()),
                )['index']
                np.testing.assert_allclose(
                    scores[f'sp_index_uli__{domain}'],
                    expected,
                )
        np.testing.assert_allclose(
            scores['sp_index_uli__walk'],
            normalised['walk'],
        )
        # effective weights: shares of the index's mean level, summing to one
        weights = ci.effective_weights(spec, params)
        self.assertAlmostEqual(
            sum(w['effective'] for w in weights.values()),
            1.0,
        )
        self.assertAlmostEqual(
            weights['walk']['effective'],
            ((1 / 3) / (5 / 3) + (1 / 3) / (4 / 3) + (1 / 3) / 1) / 3,
        )
        self.assertAlmostEqual(
            params['effective_weights']['pt'],
            weights['pt']['effective'],
            places=6,
        )
        # the structure lists each indicator once, and each domain its members
        structure = ci.index_structure(spec, params)
        self.assertTrue(structure['shared'])
        self.assertEqual(
            sorted(structure['order']),
            ['park', 'pt', 'roads', 'walk'],
        )
        self.assertEqual(
            [i['id'] for i in structure['indicators']],
            structure['order'],
        )
        built = structure['domains'][0]
        self.assertEqual(
            {i['id']: round(i['share'], 4) for i in built['indicators']},
            {'walk': 0.3333, 'park': 1.0, 'roads': 0.3333},
        )
        self.assertEqual(
            {i['column'] for i in built['indicators']},
            {'index_uli__walk', 'index_uli__park', 'index_uli__roads'},
        )
        self.assertIsNone(structure['domains'][-1]['column'])
        # the order found makes no more separate domain arcs than listing
        order = structure['order']
        by_id = {i['id']: i for i in spec['indicators']}
        names = [d['name'] for d in spec['domains']]

        def arcs(ids):
            return ci._track_breaks(
                [set(by_id[i]['domains']) for i in ids],
                names,
            )

        self.assertLessEqual(arcs(order), arcs(list(by_id)))
        # a configured order is followed
        ordered = ci.normalise_index_spec(
            'uli',
            {**shared, 'order': ['roads', 'park']},
        )
        self.assertEqual(ci.display_order(ordered)[:2], ['roads', 'park'])
        # the form with indicators nested under domains is the special case of
        # one domain each, and scores identically
        nested = ci.normalise_index_spec(
            'uli',
            {
                'domains': {
                    'mobility': {
                        'indicators': [
                            {'variable': 'walk', 'polarity': 'positive'},
                            {'variable': 'pt', 'polarity': 'positive'},
                        ],
                    },
                },
            },
        )
        listed = ci.normalise_index_spec(
            'uli',
            {
                'domains': {'mobility': {}},
                'indicators': [
                    {
                        'variable': 'walk',
                        'polarity': 'positive',
                        'domains': 'mobility',
                    },
                    {
                        'variable': 'pt',
                        'polarity': 'positive',
                        'domains': 'mobility',
                    },
                ],
            },
        )
        results = []
        for form in (nested, listed):
            prepared = ci.prepare(frame, form)
            results.append(
                ci.score(
                    prepared,
                    form,
                    ci.resolve_parameters(prepared, form),
                ),
            )
        pd.testing.assert_frame_equal(results[0], results[1])
        # scores reported as differences from the reference: calculated with
        # the reference at 100 (the penalty divides by the mean), then less
        # 100 -- all but the penalty and count, which are not scores
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            centred = ci.normalise_index_spec('uli', {**shared, 'centre': 0})
        self.assertEqual(centred['centre'], 0)
        prepared_shared = ci.prepare(frame, centred)
        difference = ci.score(prepared_shared, centred, params)
        standard = ci.score(prepared_shared, spec, params)
        for column in standard:
            with self.subTest(column=column):
                shift = 0 if column.endswith(('_penalty', '_n')) else 100
                np.testing.assert_allclose(
                    difference[column],
                    standard[column] - shift,
                )
        structure = ci.index_structure(centred, params)
        self.assertEqual(structure['reference_value'], 0)
        classes = ci.composite_classes(
            structure,
            {'index_uli': (-9.0, 8.0), 'index_uli__built': (-20.0, 21.0)},
        )
        edges = classes['index_uli']['edges']
        self.assertAlmostEqual((edges[2] + edges[3]) / 2, 0.0)
        with self.assertRaises(ValueError):
            ci.normalise_index_spec('uli', {**shared, 'centre': 'zero'})
        # configuration checks
        for bad in (
            # a domain the index does not define
            {
                **shared,
                'indicators': [
                    {
                        'variable': 'walk',
                        'polarity': '+',
                        'domains': ['parks'],
                    },
                ],
            },
            # no domains named
            {**shared, 'indicators': [{'variable': 'walk', 'polarity': '+'}]},
            # listed twice
            {
                **shared,
                'indicators': [
                    {'variable': 'walk', 'polarity': '+', 'domains': 'built'},
                    {'variable': 'walk', 'polarity': '+', 'domains': 'safety'},
                ],
            },
            # an indicator named as a domain is
            {
                **shared,
                'indicators': [
                    {
                        'variable': 'safety',
                        'polarity': '+',
                        'domains': 'built',
                    },
                ],
            },
            # an order naming an indicator the index does not have
            {**shared, 'order': ['nothing']},
        ):
            with self.subTest(bad=bad), warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with self.assertRaises(ValueError):
                    ci.normalise_index_spec('uli', bad)

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

    def test_6_example_generate(self):
        """Generate resources for example region."""
        r = ghsci.example()
        r.generate()

    def test_6_z_longitudinal_pseudo_series(self):
        """Longitudinal series over a cloned pseudo-timepoint of the example region.

        Creates a second configuration for the example region with the
        year advanced, clones its database as a pseudo-timepoint (a
        cheap alternative to full re-analysis), and exercises the
        longitudinal workflow end-to-end: alignment validation (grids
        identical by construction), panel assembly, change metrics
        (zero change expected), equity summary, and generation of a
        spatial_longitudinal report PDF.
        """
        from sqlalchemy import create_engine, text

        reference = 'ES_Las_Palmas_2025'
        pseudo = 'ES_Las_Palmas_2025_t2'
        # pseudo-timepoint configuration: same data, year advanced
        with open(ghsci.get_region_config_path(reference)) as file:
            configuration = file.read()
        self.assertIn('year: 2025', configuration)
        # only the first occurrence: the region year, not gtfs_year
        configuration = configuration.replace('year: 2025', 'year: 2026', 1)
        with open(f'./configuration/regions/{pseudo}.yml', 'w') as file:
            file.write(configuration)
        r = ghsci.Region(reference)
        if r.config['grid_summary'] not in r.tables:
            self.skipTest(
                'example region analysis outputs not available '
                '(run test_5_example_analysis first)',
            )
        r2 = ghsci.Region(pseudo)
        # clone the example database as the pseudo-timepoint
        sql = ghsci.settings['sql']
        admin = create_engine(
            f"postgresql://{sql['db_user']}:{sql['db_pwd']}"
            f"@{sql['db_host']}/postgres",
            isolation_level='AUTOCOMMIT',
        )
        r.engine.dispose()
        r2.engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS {r2.config["db"]}'),
            )
            connection.execute(
                text(
                    'SELECT pg_terminate_backend(pid) '
                    'FROM pg_stat_activity '
                    f"WHERE datname = '{r.config['db']}' "
                    'AND pid <> pg_backend_pid()',
                ),
            )
            connection.execute(
                text(
                    f'CREATE DATABASE {r2.config["db"]} '
                    f'TEMPLATE {r.config["db"]}',
                ),
            )
        admin.dispose()
        if not os.path.exists(f"{r2.config['region_dir']}/figures"):
            os.makedirs(f"{r2.config['region_dir']}/figures")
        # longitudinal workflow
        s = ghsci.Series([reference, pseudo])
        report = s.validate_alignment()
        self.assertTrue(
            all(result['status'] == 'ok' for result in report.values()),
            report,
        )
        panel = s.get_grid_panel()
        self.assertGreater(len(panel), 0)
        self.assertEqual(
            list(panel.attrs['timepoints']),
            ['2025', '2026'],
        )
        change = s.compute_change(panel)
        pp_change = change.query("metric == 'pp_change'")['change'].dropna()
        self.assertTrue(
            (pp_change.abs() < 1e-9).all(),
            'cloned timepoint should show zero change',
        )
        equity = s.equity_summary(save=True)
        for key in ['quantiles', 'gaps', 'concentration', 'thresholds']:
            self.assertGreater(len(equity[key]), 0, key)
        # longitudinal report generation
        s.generate_report(template='spatial_longitudinal')
        reports_dir = f'{s.output_dir}/reports'
        self.assertTrue(
            os.path.exists(reports_dir)
            and any(f.endswith('.pdf') for f in os.listdir(reports_dir)),
            f'expected a longitudinal report PDF in {reports_dir}',
        )

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

    def test_0_58_database_backup_helpers(self):
        """Database dump names, version checks, TOC parsing and fallbacks."""
        import datetime

        from subprocesses import _database_backup as backup

        date = datetime.date(2026, 9, 26)
        self.assertEqual(
            backup.dump_filename('mx_mexicali_2025_uli', date),
            'mx_mexicali_2025_uli_20260926.dump',
        )
        # a folder, a file, or nothing (the default folder)
        self.assertEqual(
            backup.resolve_dump_path('/backups', 'db', '/default', date),
            os.path.join('/backups', 'db_20260926.dump'),
        )
        self.assertEqual(
            backup.resolve_dump_path('/x/mine.dump', 'db', '/default', date),
            '/x/mine.dump',
        )
        self.assertTrue(
            backup.resolve_dump_path(None, 'db', '/default', date).endswith(
                'db_20260926.dump',
            ),
        )

        # client versions must be at least the server's major version
        self.assertEqual(
            backup.major_version(
                'pg_dump (PostgreSQL) 15.13 (Debian 15.13-1.pgdg110+1)',
            ),
            15,
        )
        self.assertEqual(backup.major_version('150013'), 15)
        self.assertEqual(backup.major_version('9.6.24'), 9)
        self.assertTrue(backup.client_supports(17, 15))
        self.assertTrue(backup.client_supports(15, 15))
        self.assertFalse(backup.client_supports(14, 15))
        self.assertFalse(backup.client_supports(None, 15))

        # header and tables of a pg_restore -l listing
        toc = '\n'.join(
            [
                ';',
                '; Archive created at 2026-09-26 06:13:58 UTC',
                ';     dbname: mx_mexicali_2025_uli',
                ';     TOC Entries: 499',
                ';     Compression: 6',
                ';     Dump Version: 1.14-0',
                ';     Format: CUSTOM',
                ';     Dumped from database version: 15.13 (Debian 15.13-1.pgdg110+1)',
                ';     Dumped by pg_dump version: 15.13 (Debian 15.13-1.pgdg110+1)',
                ';',
                '; Selected TOC Entries:',
                ';',
                '6; 3079 71249 EXTENSION - hstore ',
                '280; 1259 71472 TABLE public edges postgres',
                '281; 1259 71480 TABLE public nodes postgres',
                '5990; 0 71472 TABLE DATA public edges postgres',
            ],
        )
        header = backup.parse_toc_header(toc)
        self.assertEqual(header['dbname'], 'mx_mexicali_2025_uli')
        self.assertEqual(header['format'], 'CUSTOM')
        self.assertEqual(header['dump_version'], '1.14-0')
        self.assertEqual(
            backup.major_version(header['dumped_from_database_version']),
            15,
        )
        self.assertEqual(header['tables'], 2)

        # host fallbacks copy files through the container (never redirect
        # binary output in PowerShell) and use the container's port
        dump = backup.host_dump_commands('db', 'db_20260926.dump')
        restore = backup.host_restore_commands('db_20260926.dump', 'db')
        for command in dump + restore:
            self.assertNotIn('>', command)
            self.assertIn('ghscic_postgis', command)
        self.assertTrue(any('docker cp' in c for c in dump))
        self.assertTrue(any('docker cp' in c for c in restore))
        self.assertIn('-p 5433', dump[0])
        self.assertIn('--create', restore[1])
        self.assertIn('-p 5433', restore[1])

        # a newer pg_restore's transaction_timeout errors are benign
        stderr = '\n'.join(
            [
                'pg_restore: error: could not execute query: ERROR:  unrecognized configuration parameter "transaction_timeout"',
                'Command was: SET transaction_timeout = 0;',
                'pg_restore: error: could not execute query: ERROR:  relation "edges" already exists',
                'pg_restore: warning: errors ignored on restore: 2',
                'pg_restore: error: could not open input file "x.dump": No such file or directory',
            ],
        )
        self.assertEqual(
            backup.restore_errors(stderr),
            [
                'pg_restore: error: could not execute query: ERROR:  relation "edges" already exists',
                'pg_restore: error: could not open input file "x.dump": No such file or directory',
            ],
        )


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
