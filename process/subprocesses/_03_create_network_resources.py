"""
OpenStreetMap network setup.

Create active travel street network for specified city.
"""

import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import time
import xml.sax
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

import geopandas as gpd

# Set up project and region parameters for GHSCIC analyses
import ghsci
import networkx as nx
import numpy as np
import osmnx as ox
import shapely
from osmnx import _osm_xml, _overpass
from script_running_log import script_running_log
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import text
from tqdm import tqdm


def overpass_date(r):
    """Return the Overpass [date:...] timestamp matching the region's OpenStreetMap data.

    The network is retrieved from Overpass, while other OpenStreetMap layers
    are imported from the configured extract; both should describe the same
    moment.  A Geofabrik extract named for its publication date holds edits up
    to its replication timestamp, late on that day, so the start of the day
    would miss that day's edits (e.g. streets mapped in the Condesa
    development at 04:43 on the publication date of Mexicali's extract).  The
    replication timestamp recorded by osm2pgsql in _02 is used where
    available, falling back to the start of the publication date.
    """
    if 'osm2pgsql_properties' in r.tables:
        timestamp = r.get_df(
            """
            SELECT value FROM osm2pgsql_properties
            WHERE property = 'replication_timestamp'
            """,
        )
        if len(timestamp) > 0 and timestamp['value'][0]:
            return (
                timestamp['value'][0],
                'OpenStreetMap extract replication timestamp',
            )
    publication_date = datetime.strptime(
        str(r.config['OpenStreetMap']['publication_date']),
        '%Y%m%d',
    ).strftime('%Y-%m-%d')
    return f'{publication_date}T00:00:00Z', 'OpenStreetMap publication date'


def osmnx_configuration(r):
    """Set up OSMnx for network retrieval and analysis, given a configured ghsci.Region (r)."""
    ox.settings.use_cache = True
    ox.settings.log_console = True
    # Optionally use an alternative Overpass API endpoint, e.g. one of the
    # servers behind overpass-api.de (gall.openstreetmap.de or
    # lambert.openstreetmap.de) should the other be unavailable
    if os.environ.get('GHSCI_OVERPASS_URL'):
        ox.settings.overpass_url = os.environ['GHSCI_OVERPASS_URL']
        print(f'Overpass API endpoint: {ox.settings.overpass_url}')
    # Include additional attributes in the 'node' outputs for LTS analysis
    ox.settings.useful_tags_node += ['highway', 'crossing', 'traffic_calming']
    # Include additional attributes in the 'edges' outputs for bicycle routing and LTS analysis
    ox.settings.useful_tags_way += [
        'foot',
        'sidewalk',
        'bicycle',
        'cycleway',
        'cycleway:left',
        'cycleway:right',
        'maxspeed',
        'motor_vehicle',
    ]
    # set OSMnx to retrieve filtered network to match the OpenStreetMap data
    osm_date, osm_date_source = overpass_date(r)
    if r.config['network'].get('from_pbf'):
        print(
            f"Network extracted from {r.config['OpenStreetMap']['data']} "
            f'(Overpass-equivalent query as at {osm_date}; {osm_date_source}).',
        )
    else:
        print(
            f'Network retrieved from Overpass as at {osm_date} ({osm_date_source}).',
        )
    ox.settings.overpass_settings = (
        '[out:json][timeout:{timeout}]' + f'[date:"{osm_date}"]' + '{maxsize}'
    )
    if not r.config['network']['osmnx_retain_all']:
        print(
            """Note: "osmnx_retain_all = False" ie. only main network segment is retained. Please ensure this is appropriate for your study region (ie. networks on real islands may be excluded).""",
        )
    elif r.config['network']['osmnx_retain_all']:
        print(
            """Note: "osmnx_retain_all = True" ie. all network segments will be retained. Please ensure this is appropriate for your study region (ie. networks on real islands will be included, however network artifacts resulting in isolated network segments, or network islands, may also exist.  These could be problematic if sample points are snapped to erroneous, mal-connected segments.  Check results.).""",
        )
    else:
        sys.exit(
            "Please ensure the osmnx_retain_all has been defined for this region with values of either 'False' or 'True'",
        )


# Optional extraction of the network from the configured OpenStreetMap .pbf
# ('network: from_pbf: true'), as an alternative to the Overpass API.
#
# OSMnx's graph_from_polygon is used unchanged: it buffers and subdivides the
# polygon, requests '(way<filter>(poly:...);>;);out;' for each part, builds
# the graph from the responses, then truncates, simplifies and counts streets
# per node.  Only the source of each response differs: while the graph is
# built, OSMnx's Overpass request function is replaced by one answering the
# same query from the .pbf, which holds the OpenStreetMap data as at the
# replication timestamp used to date the Overpass query (see overpass_date).
# Responses are neither read from nor saved to the OSMnx cache, so Overpass
# and .pbf results are never mixed.

_OVERPASS_CLAUSE = re.compile(
    r'\[\s*(?P<negate_key>!)?\s*"(?P<key>[^"\\]+)"\s*'
    r'(?:(?P<op>!=|!~|=|~)\s*"(?P<value>[^"\\]*)"\s*)?\]',
)
# Overpass evaluates regular expressions as POSIX extended expressions; those
# limited to literal alternatives (optionally anchored) behave identically
# with Python's re.search, so other regular expressions are not accepted
_LITERAL_ALTERNATIVES = re.compile(r'^\^?[\w:;. -]+(\|[\w:;. -]+)*\$?$')
_pbf_extracts = {}
# osmfilter and osmconvert track the objects to keep in hash tables sized by
# --hash-memory (MB); the defaults are too small for recent OpenStreetMap IDs
# (node IDs exceeded 14 billion in 2026), dropping or misattributing objects,
# so a generous allocation is set (sufficient for node IDs to ~3e10)
_OSM_TOOL_HASH_MEMORY = '--hash-memory=4000'


def parse_overpass_way_filter(way_filter: str) -> list:
    """
    Parse an Overpass way filter (e.g. 'openstreetmap_query') into tag tests.

    Supports ["key"], ["!key"], ["key"="value"], ["key"!="value"],
    ["key"~"regex"] and ["key"!~"regex"], with Overpass semantics: regular
    expressions match anywhere in a value (so "motorway" also matches
    "motorway_link"), and negated tests are met by objects lacking the key.
    Anything else raises a RuntimeError, rather than risk a filter that differs
    from Overpass.

    Returns a list of functions, each taking a dictionary of tags and
    returning True where the tags meet that clause.
    """
    tests = []
    position = 0
    for match in _OVERPASS_CLAUSE.finditer(way_filter):
        skipped = way_filter[position : match.start()]
        if skipped.strip():
            raise RuntimeError(
                f'Unsupported Overpass filter syntax for from_pbf: {skipped.strip()!r}',
            )
        position = match.end()
        key, op, value = match['key'], match['op'], match['value']
        if match['negate_key']:
            if op is not None:
                raise RuntimeError(
                    f'Unsupported Overpass filter clause for from_pbf: {match.group(0)!r}',
                )
            tests.append(lambda tags, k=key: k not in tags)
        elif op is None:
            tests.append(lambda tags, k=key: k in tags)
        elif op == '=':
            tests.append(lambda tags, k=key, v=value: tags.get(k) == v)
        elif op == '!=':
            tests.append(lambda tags, k=key, v=value: tags.get(k) != v)
        else:
            if not _LITERAL_ALTERNATIVES.match(value):
                raise RuntimeError(
                    f'Unsupported regular expression for from_pbf: {value!r} '
                    '(only literal alternatives separated by | are supported)',
                )
            pattern = re.compile(value)
            if op == '~':
                tests.append(
                    lambda tags, k=key, p=pattern: k in tags
                    and p.search(tags[k]) is not None,
                )
            else:
                tests.append(
                    lambda tags, k=key, p=pattern: k not in tags
                    or p.search(tags[k]) is None,
                )
    if way_filter[position:].strip():
        raise RuntimeError(
            f'Unsupported Overpass filter syntax for from_pbf: {way_filter[position:].strip()!r}',
        )
    if not tests:
        raise RuntimeError(f'No Overpass filter clauses found in {way_filter!r}')
    return tests


def _file_sha256(path: str) -> str:
    """Return the SHA-256 checksum of a file."""
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        for block in iter(lambda: file.read(2**20), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare_pbf_network_extract(r, polygon) -> dict:
    """
    Extract highway ways, and all their nodes, from the configured .pbf.

    The configured OpenStreetMap data (not the study region excerpt, which
    is clipped to the buffered study region without complete ways) is cut to
    a large outer bounding box (osmconvert), reduced to ways with a highway
    tag and the nodes they reference (osmfilter), then cut to the bounding
    box of the polygon, with a margin exceeding the 500 m buffer OSMnx adds,
    keeping complete ways (osmconvert).  The result is parsed with OSMnx's
    own OSM XML parser into Overpass-like elements, held in arrays for
    selection by sub-polygon.  The .pbf timestamp must match the osm2pgsql
    replication timestamp used to date the Overpass query.
    """
    pbf = r.config['OpenStreetMap']['data']
    margin = 0.05  # degrees; well beyond OSMnx's 500 m buffer
    xmin, ymin, xmax, ymax = polygon.bounds
    bbox = (
        round(xmin - margin, 4),
        round(ymin - margin, 4),
        round(xmax + margin, 4),
        round(ymax + margin, 4),
    )
    key = (pbf, bbox)
    if key in _pbf_extracts:
        return _pbf_extracts[key]
    osm_date, _ = overpass_date(r)
    pbf_timestamp = subprocess.run(
        ['osmconvert', '--out-timestamp', pbf],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if pbf_timestamp != osm_date:
        raise RuntimeError(
            f'The timestamp of {pbf} ({pbf_timestamp}) does not match the date '
            f'used for the network ({osm_date}), so the network cannot be '
            'extracted from it as an equivalent of the Overpass query.',
        )
    print(
        f'\n  - Extracting highway ways from {pbf} for bounding box {bbox}...',
    )
    # A way reaching from the bounding box beyond the outer box (see
    # _extract_highway_elements) would be incomplete; the outer margin is then
    # enlarged until all ways are complete, as Overpass returns whole ways
    for outer_margin in _OUTER_MARGINS:
        elements = _extract_highway_elements(
            pbf,
            bbox,
            outer_margin,
            r.config['region_dir'],
        )
        try:
            extract = extract_from_elements(
                elements,
                source=pbf,
                timestamp=pbf_timestamp,
                bbox=bbox,
            )
            break
        except IncompleteWaysError as e:
            if outer_margin == _OUTER_MARGINS[-1]:
                raise
            print(
                f'  - {e} (outer margin {outer_margin} degrees); retrying with '
                'a larger outer margin...',
            )
        finally:
            del elements
    print(
        f"  - {len(extract['way_ids']):,} highway ways and "
        f"{len(extract['node_ids']):,} nodes extracted.",
    )
    _pbf_extracts[key] = extract
    return extract


class IncompleteWaysError(RuntimeError):
    """Raised where ways reference nodes missing from an extract."""


# outer bounding box margins (degrees; approximately 10, 50, 100 and 200 km)
_OUTER_MARGINS = (0.1, 0.5, 1.0, 2.0)


def _extract_highway_elements(pbf, bbox, outer_margin, region_dir) -> list:
    """
    Extract highway ways with complete node lists for a bounding box.

    osmconvert does not complete ways crossing a bounding box when reading
    .pbf.  So the data are first cut to a larger outer bounding box (avoiding
    processing of the whole extract, e.g. a country), converted to .o5m,
    reduced to highway ways and the nodes they reference (osmfilter), and only
    then cut to the bounding box with complete ways (osmconvert).  The result
    is parsed with OSMnx's own OSM XML parser into Overpass-like elements.
    """
    outer = (
        round(bbox[0] - outer_margin, 4),
        round(bbox[1] - outer_margin, 4),
        round(bbox[2] + outer_margin, 4),
        round(bbox[3] + outer_margin, 4),
    )
    o5m = f'{region_dir}/_network_extract.o5m'
    highways = f'{region_dir}/_network_extract_highways.o5m'
    osm = f'{region_dir}/_network_extract.osm'
    try:
        subprocess.run(
            [
                'osmconvert',
                pbf,
                f'-b={outer[0]},{outer[1]},{outer[2]},{outer[3]}',
                '--drop-author',
                '--drop-relations',
                _OSM_TOOL_HASH_MEMORY,
                f'-o={o5m}',
            ],
            check=True,
        )
        subprocess.run(
            [
                'osmfilter',
                o5m,
                '--keep-ways=highway=',
                '--keep-nodes=',
                '--keep-relations=',
                '--drop-relations',
                _OSM_TOOL_HASH_MEMORY,
                f'-o={highways}',
            ],
            check=True,
        )
        subprocess.run(
            [
                'osmconvert',
                highways,
                f'-b={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}',
                '--complete-ways',
                _OSM_TOOL_HASH_MEMORY,
                f'-o={osm}',
            ],
            check=True,
        )
        handler = _osm_xml._OSMContentHandler()
        with open(osm, 'rb') as file:
            xml.sax.parse(file, handler)
    finally:
        for path in (o5m, highways, osm):
            if os.path.exists(path):
                os.remove(path)
    return handler.object['elements']


def extract_from_elements(elements, source, timestamp, bbox=None) -> dict:
    """
    Index Overpass-like node and way elements for selection by polygon.

    Nodes are sorted by ID with coordinate arrays, and each way's nodes are
    held as indices into these (flattened, with offsets), so that ways may be
    selected by polygon with vectorised operations.  Every node a way
    references must be present, as Overpass returns complete ways.
    """
    node_ids, lats, lons, node_tags = [], [], [], {}
    way_ids, way_nodes, way_tags = [], [], []
    for element in elements:
        if element['type'] == 'node':
            node_ids.append(element['id'])
            lats.append(element['lat'])
            lons.append(element['lon'])
            if element.get('tags'):
                node_tags[element['id']] = element['tags']
        elif element['type'] == 'way':
            way_ids.append(element['id'])
            way_nodes.append(element['nodes'])
            way_tags.append(element.get('tags', {}))
    node_ids = np.array(node_ids, dtype=np.int64)
    order = np.argsort(node_ids)
    node_ids = node_ids[order]
    lats = np.array(lats)[order]
    lons = np.array(lons)[order]
    # flattened way node indices, for vectorised selection by polygon
    flat_ids = np.fromiter(
        (n for nodes in way_nodes for n in nodes),
        dtype=np.int64,
    )
    flat_index = np.searchsorted(node_ids, flat_ids)
    flat_index[flat_index >= len(node_ids)] = 0
    missing = node_ids[flat_index] != flat_ids
    if missing.any():
        raise IncompleteWaysError(
            f'{int(missing.sum())} way node references are missing from the '
            f'extract of {source}; ways must be complete to match Overpass.',
        )
    lengths = np.array([len(nodes) for nodes in way_nodes])
    offsets = np.concatenate([[0], np.cumsum(lengths)[:-1]])
    extract = {
        'pbf': source,
        'timestamp': timestamp,
        'bbox': bbox,
        'node_ids': node_ids,
        'lats': lats,
        'lons': lons,
        'node_tags': node_tags,
        'way_ids': np.array(way_ids, dtype=np.int64),
        'way_nodes': way_nodes,
        'way_tags': way_tags,
        'flat_index': flat_index,
        'lengths': lengths,
        'offsets': offsets,
        'responses': [],
    }
    return extract


def overpass_response_from_extract(extract: dict, query_str: str) -> dict:
    """
    Answer an OSMnx Overpass network query from a .pbf extract.

    The query takes the form OSMnx generates,
    '<settings>;(way<filter>(poly:'<lat lon ...>');>;);out;', selecting ways
    meeting the filter that have a node within the polygon, or a segment
    crossing it, and then ('>') all nodes of those ways.  As for Overpass
    ('out;'), elements are returned as nodes then ways, each sorted by ID,
    with tags omitted for untagged elements.
    """
    filter_start = query_str.index('(way') + len('(way')
    poly_start = query_str.rindex("(poly:'")
    poly_end = query_str.rindex("');>;);out;")
    way_filter = query_str[filter_start:poly_start]
    coords = np.array(
        query_str[poly_start + len("(poly:'") : poly_end].split(),
        dtype=float,
    ).reshape(-1, 2)
    polygon = Polygon(coords[:, ::-1])  # Overpass coordinates are lat lon
    shapely.prepare(polygon)
    tests = parse_overpass_way_filter(way_filter)
    tag_match = np.array(
        [all(test(tags) for test in tests) for tags in extract['way_tags']],
        dtype=bool,
    )
    lons, lats = extract['lons'], extract['lats']
    flat_index, offsets = extract['flat_index'], extract['offsets']
    # ways with a node within the polygon
    xmin, ymin, xmax, ymax = polygon.bounds
    in_bounds = (lons >= xmin) & (lons <= xmax) & (lats >= ymin) & (lats <= ymax)
    inside = np.zeros(len(lons), dtype=bool)
    candidates = np.flatnonzero(in_bounds)
    inside[candidates] = shapely.intersects_xy(
        polygon,
        lons[candidates],
        lats[candidates],
    )
    selected = np.logical_or.reduceat(inside[flat_index], offsets) & tag_match
    # ways without a node inside, but with a segment crossing the polygon
    way_xmin = np.minimum.reduceat(lons[flat_index], offsets)
    way_xmax = np.maximum.reduceat(lons[flat_index], offsets)
    way_ymin = np.minimum.reduceat(lats[flat_index], offsets)
    way_ymax = np.maximum.reduceat(lats[flat_index], offsets)
    crossing_candidates = np.flatnonzero(
        tag_match
        & ~selected
        & (extract['lengths'] > 1)
        & (way_xmax >= xmin)
        & (way_xmin <= xmax)
        & (way_ymax >= ymin)
        & (way_ymin <= ymax),
    )
    if len(crossing_candidates) > 0:
        lines = [
            shapely.LineString(
                np.column_stack(
                    [
                        lons[flat_index[offsets[i] : offsets[i] + extract['lengths'][i]]],
                        lats[flat_index[offsets[i] : offsets[i] + extract['lengths'][i]]],
                    ],
                ),
            )
            for i in crossing_candidates
        ]
        selected[crossing_candidates] = shapely.intersects(polygon, lines)
    way_indices = np.flatnonzero(selected)
    node_indices = np.unique(
        np.concatenate(
            [
                flat_index[offsets[i] : offsets[i] + extract['lengths'][i]]
                for i in way_indices
            ],
        )
        if len(way_indices) > 0
        else np.array([], dtype=np.int64),
    )
    elements = []
    for i in node_indices:
        node_id = int(extract['node_ids'][i])
        node = {
            'type': 'node',
            'id': node_id,
            'lat': float(lats[i]),
            'lon': float(lons[i]),
        }
        if node_id in extract['node_tags']:
            node['tags'] = extract['node_tags'][node_id]
        elements.append(node)
    for i in way_indices[np.argsort(extract['way_ids'][way_indices])]:
        way = {
            'type': 'way',
            'id': int(extract['way_ids'][i]),
            'nodes': extract['way_nodes'][i],
        }
        if extract['way_tags'][i]:
            way['tags'] = extract['way_tags'][i]
        elements.append(way)
    extract['responses'].append(
        {'ways': len(way_indices), 'nodes': len(node_indices)},
    )
    return {
        'version': 0.6,
        'generator': f"GHSCI from_pbf ({extract['pbf']}, {extract['timestamp']})",
        'osm3s': {
            'timestamp_osm_base': extract['timestamp'],
            'copyright': 'The data included in this document is from www.openstreetmap.org. The data is made available under ODbL.',
        },
        'elements': elements,
    }


@contextmanager
def pbf_overpass_requests(r, polygon):
    """
    Answer OSMnx's Overpass network requests from the configured .pbf.

    Within this context, osmnx._overpass._overpass_request (called by
    graph_from_polygon for each subdivision of the buffered polygon) is
    replaced by overpass_response_from_extract, without use of the OSMnx
    cache.  The replaced function is private to OSMnx, so its signature is
    checked first, to fail loudly should OSMnx change.
    """
    parameters = list(
        inspect.signature(_overpass._overpass_request).parameters,
    )
    if parameters != ['data'] or not hasattr(
        _overpass,
        '_download_overpass_network',
    ):
        raise RuntimeError(
            f'OSMnx {ox.__version__} differs from the version for which '
            'from_pbf network extraction was developed (2.1.1); please check '
            'osmnx._overpass before using from_pbf.',
        )
    extract = prepare_pbf_network_extract(r, polygon)

    def _request_from_extract(data):
        return overpass_response_from_extract(extract, data['data'])

    with mock.patch.object(
        _overpass,
        '_overpass_request',
        _request_from_extract,
    ):
        yield extract
    record = {
        'pbf': extract['pbf'],
        'pbf_sha256': _file_sha256(extract['pbf']),
        'timestamp': extract['timestamp'],
        'bbox': extract['bbox'],
        'osmnx': ox.__version__,
        'openstreetmap_query': r.config['network']['openstreetmap_query'],
        'responses': extract['responses'],
    }
    record_path = f"{r.config['region_dir']}/_network_from_pbf.json"
    with open(record_path, 'w') as file:
        json.dump(record, file, indent=2)
    print(
        f"  - Network extracted from .pbf in {len(extract['responses'])} "
        f"request(s); details recorded in {os.path.basename(record_path)}",
    )


def graph_from_polygon(r, polygon, **kwargs):
    """Get a network graph using ox.graph_from_polygon, from the .pbf if configured ('network: from_pbf')."""
    if r.config['network'].get('from_pbf'):
        with pbf_overpass_requests(r, polygon):
            return ox.graph_from_polygon(polygon, **kwargs)
    return ox.graph_from_polygon(polygon, **kwargs)


def generate_network_nodes_edges(r):

    """Generate routable active travel network using OSMnx and store in a PostGIS database, or otherwise retrieve it, given a configured ghsci.Region (r)."""
    if r.config['network']['buffered_region']:
        network_study_region = r.config['buffered_urban_study_region']
    else:
        network_study_region = 'urban_study_region'
    if {'nodes', 'edges'}.issubset(r.tables):
        print(
            f'Routable active travel network for {network_study_region} has already been processed.',
        )
        print('\nLoading the routable active travel network.')
        nodes = r.get_gdf('nodes', index_col='osmid')
        edges = r.get_gdf('edges', index_col=['u', 'v', 'key'])
        G_proj = ox.graph_from_gdfs(nodes, edges, graph_attrs=None)
        return G_proj
    else:
        G = derive_active_travel_network(r, network_study_region)
        # Prune sub-sampling-resolution dead-end stubs before saving, so that sample
        # points (generated in _07 along the edges at the sampling interval) are never
        # placed on network artifacts that would falsely isolate them from destinations.
        # Threshold = half the sample-point interval (a stub shorter than this cannot
        # carry a distinct interior sample anyway).
        interval = ghsci.settings['sample_points']['point_sampling_interval']
        dangle_threshold = interval / 2.0
        n_dangle_edges, n_dangle_nodes = prune_short_dangles(
            G,
            dangle_threshold,
        )
        print(
            f'  - Pruned {n_dangle_edges} short dangle edges (degree-1 endpoint and '
            f'< {dangle_threshold:g} m, half the {interval} m sample interval) and '
            f'{n_dangle_nodes} orphaned nodes.',
        )
        print(
            '  - Save edges with geometry to postgis prior to simplification',
        )
        graph_to_postgis(
            G,
            r.engine,
            'edges',
            nodes=False,
            geometry_name='geom_4326',
        )

        print('  - Remove unnecessary key data from edges')
        att_list = {
            k
            for n in G.edges
            for k in G.edges[n].keys()
            if k
            not in [
                'osmid',
                'length',
                'geometry',
                'highway',
                'name',
                'oneway',
                'foot',
                'sidewalk',
                'bicycle',
                'cycleway',
                'cycleway:left',
                'cycleway:right',
                'maxspeed',
                'motor_vehicle',
            ]
        }
        capture_output = [
            [d.pop(att, None) for att in att_list]
            for n1, n2, d in tqdm(G.edges(data=True), desc=' ' * 18)
        ]
        del capture_output
        print('  - Project graph')
        G_proj = ox.project_graph(G, to_crs=r.config['crs']['srid'])
        if G_proj.is_directed():
            G_proj = G_proj.to_undirected()
        print(
            '  - Save simplified, projected, undirected graph edges and node GeoDataFrames to PostGIS',
        )
        graph_to_postgis(
            G_proj,
            r.engine,
            nodes_table='nodes',
            edges_table='edges_simplified',
        )
        return G_proj


def derive_active_travel_network(
    r,
    network_study_region,
):
    """Derive routable active travel network using OSMnx."""
    print(
        'Creating and saving routable active travel network... ',
        end='',
        flush=True,
    )
    openstreetmap_query = r.config['network']['openstreetmap_query']
    # load buffered study region in EPSG4326 from postgis
    sql = f"""SELECT ST_Transform(geom,4326) AS geom FROM {network_study_region}"""
    polygon = r.get_gdf(text(sql), geom_col='geom')['geom'][0]
    if not r.config['network']['polygon_iteration']:
        G = graph_from_polygon(
            r,
            polygon,
            custom_filter=openstreetmap_query,
            retain_all=r.config['network']['osmnx_retain_all'],
        )
    else:
        # We allow for the possibility that multiple legitimate network islands may exist in this region (e.g. Hong Kong).
        # These are accounted for by retrieving the network for each polygon in the buffered study region boundary,
        # and then taking the union of these using network compose if more than one network was retrieved.
        N = list()
        # Handle both Polygon and MultiPolygon cases
        polygons = (
            polygon.geoms if isinstance(polygon, MultiPolygon) else [polygon]
        )
        for poly in polygons:
            try:
                N.append(
                    graph_from_polygon(
                        r,
                        poly,
                        custom_filter=openstreetmap_query,
                        retain_all=r.config['network']['osmnx_retain_all'],
                    ),
                )
            except (ValueError, TypeError):
                # if the polygon results in no return results from overpass, an error is thrown
                pass

        G = N[0]
        if len(N) > 1:
            for additional_network in N[1:]:
                G = nx.compose(G, additional_network)

        if isinstance(r.config['network']['connection_threshold'], int):
            # A minimum total distance has been set for each induced network island; so, extract the node IDs of network components exceeding this threshold distance
            # get all connected graph components, sorted by size
            cc = sorted(
                nx.weakly_connected_components(G),
                key=len,
                reverse=True,
            )
            nodes = []
            for c in cc:
                if len(c) >= r.config['network']['connection_threshold']:
                    nodes.extend(c)

            nodes = set(nodes)

            # induce a subgraph on those nodes
            G = nx.MultiDiGraph(G.subgraph(nodes))

    G = G.to_undirected()

    # Remove edges that are neither walkable nor bikeable
    remove_edges = []
    for u, v, k, data in G.edges(keys=True, data=True):
        foot = str(data.get('foot', '')).lower()
        bicycle = str(data.get('bicycle', '')).lower()

        if foot == 'no' and bicycle == 'no':
            remove_edges.append((u, v, k))

    for e in remove_edges:
        G.remove_edge(*e)

    print('Done.')
    return G


def prune_short_dangles(G, threshold_m):
    """Remove short dead-end (dangle) edges and their orphaned end nodes (single pass).

    A dangle is an edge with a degree-1 (dead-end) endpoint; those shorter than
    ``threshold_m`` (set by the caller to half the sample-point interval) are
    sub-sampling-resolution stubs -- e.g. a few-metre stair, driveway or footway spur --
    that a sample point can snap onto and then be reported as falsely isolated in
    downstream (particularly cycling) routing.  Removing them before sample points are
    generated keeps origins on the meaningful network.

    A single pass over the original degrees is used deliberately: it trims the leaf
    stubs without cascading up a chain of short segments, so a longer dead-end appendage
    made of several sub-threshold edges is retained rather than progressively eaten away
    (only its own leaf stub, if under threshold, is removed).  Returns
    ``(edges_removed, nodes_removed)``.
    """
    to_remove = [
        (u, v, k)
        for u, v, k, data in G.edges(keys=True, data=True)
        if float(data.get('length', float('inf'))) < threshold_m
        and (G.degree(u) == 1 or G.degree(v) == 1)
    ]
    G.remove_edges_from(to_remove)
    orphans = list(nx.isolates(G))
    G.remove_nodes_from(orphans)
    return len(to_remove), len(orphans)


def graph_to_postgis(
    G,
    engine,
    nodes_table='nodes',
    edges_table='edges',
    nodes=True,
    edges=True,
    geometry_name='geom',
):
    """Save graph nodes and/or edges to postgis database."""
    if nodes is True and edges is False:
        nodes = ox.graph_to_gdfs(G, edges=False)
        gdf_to_postgis_format(nodes, engine, nodes_table, geometry_name)
    if edges is True and nodes is False:
        edges = ox.graph_to_gdfs(G, nodes=False)
        gdf_to_postgis_format(edges, engine, edges_table, geometry_name)
    else:
        nodes, edges = ox.graph_to_gdfs(G)
        gdf_to_postgis_format(nodes, engine, nodes_table, geometry_name)
        gdf_to_postgis_format(edges, engine, edges_table, geometry_name)


def gdf_to_postgis_format(gdf, engine, table, geometry_name='geom'):
    """Sets geometry with optional new name (e.g. 'geom') and writes to PostGIS, returning the reformatted GeoDataFrame."""
    gdf.columns = [
        geometry_name if x == 'geometry' else x for x in gdf.columns
    ]
    gdf = gdf.set_geometry(geometry_name)
    with engine.connect() as connection:
        gdf.to_postgis(
            table,
            connection,
            index=True,
            if_exists='replace',
        )


def load_intersections(r, G_proj):
    """Prepare intersections using a configured data source, or OSMnx to derive these, and store in postgis database."""
    if r.config['intersections_table'] not in r.tables:
        if (
            r.config['intersections_table']
            == f"intersections_osmnx_{r.config['network']['intersection_tolerance']}m"
        ):
            print(
                f"\nRepresent intersections using OpenStreetMap derived data using OSMnx consolidate intersections function with tolerance of {r.config['network']['intersection_tolerance']} metres... ",
            )
            # Restrict to pedestrian-accessible edges for intersection derivation:
            # the full G_proj now includes bicycle-only segments (foot=no), but
            # street connectivity intersections should reflect the pedestrian network only.
            ped_edge_keys = [
                (u, v, k)
                for u, v, k, d in G_proj.edges(keys=True, data=True)
                if str(d.get('foot', '')).lower() != 'no'
            ]
            # Copy rather than use the subgraph view, so that recalculating
            # 'street_count' below does not write through to G_proj.
            G_ped = G_proj.edge_subgraph(ped_edge_keys).copy()
            # consolidate_intersections(dead_ends=False) identifies dead ends from
            # the 'street_count' node attribute, not the graph's current degree.
            # OSMnx sets that attribute at retrieval time, before the graph was
            # made undirected, non-active edges were removed, short dangles were
            # pruned and this pedestrian subgraph was taken -- so it is stale here.
            # Graphs built from a local file (e.g. ox.pbf.graph_from_pbf, or
            # ox.graph_from_gdfs when reloading from PostGIS) never receive it at
            # all, in which case no dead ends are excluded and intersections are
            # substantially over-counted.  Recalculate it so dead ends are dropped.
            if G_ped.is_directed():
                street_count = ox.stats.count_streets_per_node(G_ped)
            else:
                # count_streets_per_node requires a MultiDiGraph; for an already
                # undirected graph the incident edge degree is the equivalent
                # count of physical streets connecting to each node.
                street_count = {n: G_ped.degree(n) for n in G_ped.nodes}
            nx.set_node_attributes(G_ped, street_count, name='street_count')
            intersections = ox.consolidate_intersections(
                G_ped,
                tolerance=r.config['network']['intersection_tolerance'],
                rebuild_graph=False,
                dead_ends=False,
            )
            intersections = gpd.GeoDataFrame(
                intersections,
                columns=['geom'],
            ).set_geometry('geom')
            with r.engine.connect() as connection:
                intersections.to_postgis(
                    r.config['intersections_table'],
                    connection,
                    index=True,
                )
        else:
            print(
                f"\nRepresent intersections using configured data {r.config['network']['intersections']['data']}... ",
            )
            r.ogr_to_db(
                source=f"/home/ghsci/process/data/{r.config['network']['intersections']['data']}",
                layer=r.config['intersections_table'],
            )
        print('  - Done.')
    else:
        print(
            'It appears that intersection data has already been prepared and imported for this region.',
        )


def create_pgrouting_network_topology(r):
    """Create network topology for pgrouting for later analysis of node relations for sample points."""
    sql = """SELECT 1 WHERE to_regclass('public.edges_target_idx') IS NOT NULL;"""
    with r.engine.begin() as connection:
        res = connection.execute(text(sql)).first()
    if res is None:
        print('\nCreate network topology...')
        sql = f"""
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "geom" geometry;
        UPDATE edges SET geom = ST_Transform(geom_4326, {r.config['crs']['srid']});
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "from" bigint;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "to" bigint;
        UPDATE edges SET "from" = v, "to" = u WHERE key != 2;
        UPDATE edges SET "from" = u, "to" = v WHERE key = 2;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "source" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "target" INTEGER;
        ALTER TABLE edges ADD COLUMN IF NOT EXISTS "ogc_fid" SERIAL PRIMARY KEY;
        SELECT MIN(ogc_fid), MAX(ogc_fid) FROM edges;
        """
        with r.engine.begin() as connection:
            min_id, max_id = connection.execute(text(sql)).first()
        print(f'there are {max_id - min_id + 1} edges to be processed')
        interval = 10000
        for x in range(min_id, max_id + 1, interval):
            sql = f"select pgr_createTopology('edges', 1, 'geom', 'ogc_fid', rows_where:='ogc_fid>={x} and ogc_fid<{x + interval}');"
            with r.engine.begin() as connection:
                connection.execute(text(sql))
            x_max = x + interval - 1
            if x_max > max_id:
                x_max = max_id
            print(f'edges {x} - {x_max} processed')

        sql = """
        CREATE INDEX IF NOT EXISTS edges_source_idx ON edges("source");
        CREATE INDEX IF NOT EXISTS edges_target_idx ON edges("target");
        """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
    else:
        print(
            '\nIt appears that the routable active travel network has already been set up for use by pgRouting.',
        )


def create_network_resources(codename):
    # simple timer for log file
    start = time.time()
    script = '_03_create_network_resources'
    task = 'Create network resources'
    r = ghsci.Region(codename)
    if {'edges', 'nodes', r.config['intersections_table']}.issubset(r.tables):
        print(
            '\nIt appears that edges, nodes and intersections have been prepared and imported for this region.',
        )
    else:
        osmnx_configuration(r)
        G_proj = generate_network_nodes_edges(r)
        create_pgrouting_network_topology(r)
        load_intersections(r, G_proj)
        # ensure user is granted access to the newly created tables
        with r.engine.begin() as connection:
            connection.execute(text(ghsci.grant_query))

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    create_network_resources(codename)


if __name__ == '__main__':
    main()
