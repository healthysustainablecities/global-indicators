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

    def test_0_4_cycling_parse_speed_kmh(self):
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

    def test_0_5_cycling_classify_cycleway(self):
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

    def test_0_6_cycling_assign_lts(self):
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

    def test_0_9_activity_centre_config(self):
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

    def test_0_12_cycling_motor_restriction(self):
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

    def test_0_13_cycling_bike_permitted_override(self):
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

    def test_0_11_combined_and_named_sets(self):
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

    def test_0_14_pedestrian_inmemory_semantics(self):
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

    def test_0_16_neighbourhood_reachable_nodes(self):
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
                    types.SimpleNamespace(),
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

    def test_0_10_r_python_comparison_metrics(self):
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

    def test_9_custom_open_space_supplement_and_replace(self):
        """Custom areas_of_interest public_open_space supplements or replaces OSM.

        Using mock Regions (no database), asserts that:

        - get_custom_open_space_config resolves the public_open_space entry
          under the areas_of_interest parent key, and returns None when the
          key is absent or has no data configured
        - with the default replace: false, supplement_open_space_setup loads
          data to a custom_open_space_areas staging table, deletes previously
          appended custom areas (idempotent re-runs), inserts new areas with
          offset aos_id values treated as fully public, and drops the staging
          table
        - with replace: true, custom_open_space_setup loads data directly as
          the open_space_areas table and derives geom_public/aos_ha_public
        """
        from unittest.mock import MagicMock

        sys.modules.setdefault('ghsci', sys.modules['subprocesses.ghsci'])
        import _06_open_space_areas_setup as aos_setup

        def mock_region(pos_entry):
            r = MagicMock()
            r.config = {
                'crs_srid': 'EPSG:32615',
                'areas_of_interest': {'public_open_space': pos_entry},
            }
            mock_connection = MagicMock()
            # First execute is the study region bounding box query; iterating
            # its result must yield one row of four coordinates.
            mock_connection.execute.side_effect = lambda *args, **kwargs: [
                (0.0, 0.0, 100.0, 100.0),
            ]
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_connection)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            r.engine.begin.return_value = mock_ctx
            return r, mock_connection

        # --- config resolution -------------------------------------------
        r, _ = mock_region({'data': 'pos.gpkg', 'replace': False})
        pos = aos_setup.get_custom_open_space_config(r)
        self.assertEqual(pos['data'], 'pos.gpkg')
        for config in [
            {},
            {'areas_of_interest': None},
            {'areas_of_interest': {'public_open_space': {'data': None}}},
        ]:
            empty = MagicMock()
            empty.config = config
            self.assertIsNone(aos_setup.get_custom_open_space_config(empty))

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
